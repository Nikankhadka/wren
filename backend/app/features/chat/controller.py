"""Chat orchestration: the agent-graph streaming turn.

The actual retrieval/generation logic lives in app/agents/graph.py's compiled
graph; this layer resolves the tenant/conversation, invokes the graph, and
translates its custom-streamed events into plain JSON events for api.py to
frame as SSE.

T-021: nothing is customer-visible until Inspection clears a draft, so every
graph event is buffered instead of forwarded immediately. A "redraft"
(price_gate) or "inspection" event with decision "retry" means the buffered
draft was rejected and discarded - the producing node is about to stream a
fresh one. An "inspection" event with any other decision means the run is
done accumulating for this pass: flush whatever is buffered (the approved
draft, or an escalation handoff message) and persist its verdicts onto the
assistant message row for the Surface-2 trace viewer.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from uuid import UUID

from langgraph.errors import GraphRecursionError

from app.agents import escalation_summary
from app.agents.graph import get_graph
from app.agents.spotlight import scan_input
from app.agents.state import AgentState, GraphContext
from app.features.chat import service
from app.llm.embedder import Embedder
from app.llm.failover import collect_legs
from app.llm.provider import LLMProvider
from app.observability.cost import TokenUsage, collect_usage
from app.observability.tracing import get_tracer
from app.retrieval.rerank import Reranker
from app.shared import config
from app.shared.limits import (
    BUDGET_ESCALATION_REASON,
    BUDGET_UNAVAILABLE_MESSAGE,
    PROVIDER_ERROR_ESCALATION_REASON,
    PROVIDER_UNAVAILABLE_MESSAGE,
    STEP_CAP_ESCALATION_REASON,
    TURN_BUDGET_ESCALATION_REASON,
    TenantLimits,
    TimeLimitedProvider,
)

logger = logging.getLogger("app.features.chat.controller")


# How much of the transcript goes into the turn. The customer message itself is
# already the last row (resolve_conversation persisted it), so this is the whole
# window the agent sees, not a window plus one.
HISTORY_MESSAGES = 10


def _ms_since(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def initial_state(
    *,
    conversation_id: str,
    tenant_id: str,
    message: str,
    history: list[dict[str, str]] | None = None,
) -> AgentState:
    return {
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "messages": history or [{"role": "customer", "content": message}],
        "route": None,
        "route_confidence": None,
        "retrieved_chunks": [],
        "selections": [],
        "engine_quote": None,
        "draft_response": "",
        "inspection": None,
        "escalated": False,
        "injection_suspected": scan_input(message),
    }


async def stream_escalated_response(*, conversation_id: UUID) -> AsyncIterator[dict[str, object]]:
    """T-020/C-5: a conversation stopped by a *limit* is terminal - no agent
    turn runs, the graph is never invoked. The customer's message is still
    persisted (kept in api.py's resolve_conversation caller) so the transcript
    stays complete for whoever picks it up on Surface 2.

    Since C-5 only ``record_limit_escalation`` writes the ``escalated`` status
    this path keys off, so only budget/step-cap/turn-budget/provider-error
    stops reach it. An agent or guardrail handoff leaves the conversation open
    and streams a non-terminal ``handoff`` event instead - the composer stays
    live and the next message gets a full turn."""
    yield {"type": "conversation", "conversation_id": str(conversation_id)}
    yield {"type": "escalated"}
    yield {"type": "done"}


async def stream_human_handled(*, conversation_id: UUID) -> AsyncIterator[dict[str, object]]:
    """C-6: a staff member is answering this conversation, so the assistant
    says nothing rather than talking over them.

    Deliberately not the escalated stream: no terminal event, so the customer's
    composer stays live. Their message was already persisted by
    ``resolve_conversation`` and reaches the owner in the Chats thread; the
    reply comes back as a ``human_agent`` message through the transcript poll.
    A handback returns the conversation to 'open' and the next turn runs
    normally.
    """
    yield {"type": "conversation", "conversation_id": str(conversation_id)}
    yield {"type": "handoff"}
    yield {"type": "done"}


async def stream_budget_escalation(
    *, tenant_id: UUID, conversation_id: UUID
) -> AsyncIterator[dict[str, object]]:
    """T-028: over the daily budget - a polite handoff, never a stack trace,
    and the graph is never invoked."""
    yield {"type": "conversation", "conversation_id": str(conversation_id)}
    await service.record_limit_escalation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        reason=BUDGET_ESCALATION_REASON,
        message=BUDGET_UNAVAILABLE_MESSAGE,
    )
    yield {"type": "refusal", "text": BUDGET_UNAVAILABLE_MESSAGE}
    yield {"type": "escalated"}
    yield {"type": "done"}


async def stream_chat_response(
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    message: str,
    provider: LLMProvider,
    embedder: Embedder,
    reranker: Reranker,
    limits: TenantLimits,
) -> AsyncIterator[dict[str, object]]:
    yield {"type": "conversation", "conversation_id": str(conversation_id)}

    graph = get_graph()
    # P-3/US-2: the turn is one call against the package *and the conversation*,
    # so the recent transcript goes in with it - without it "and how much is
    # that one?" has nothing to refer to. Falls back to the bare message if the
    # read fails; a turn is worth more than its history.
    try:
        history = await service.recent_messages(
            tenant_id=tenant_id, conversation_id=conversation_id, limit=HISTORY_MESSAGES
        )
    except Exception:
        logger.warning("could not load conversation history; answering from this message alone")
        history = None
    initial_state_dict = initial_state(
        conversation_id=str(conversation_id),
        tenant_id=str(tenant_id),
        message=message,
        history=history,
    )

    full_text = ""
    buffer: list[dict[str, object]] = []
    verdicts: dict[str, object] = {}
    tool_calls: list[dict[str, object]] = []
    author_node: str | None = None
    response_payload: dict[str, object] | None = None
    price_summary_ms: float | None = None
    # Every in-graph escalation path (create_escalation tool, price_gate,
    # inspection) routes through escalation.py's node, which always emits
    # this - the one reliable signal, from inside the custom stream, that
    # this turn wrote an escalation row worth summarising.
    handoff_seen = False
    tracer = get_tracer(config.get_settings())
    # Latency baseline. The gap between first_model_token_ms (the model started
    # producing prose) and first_prose_ms (the customer was first allowed to see
    # any of it) is exactly what the T-021 inspection buffer costs in perceived
    # latency - measured rather than asserted, since the buffer is a ratified
    # scope decision (US-060) and is not going to be removed to chase it.
    turn_started = time.perf_counter()
    first_model_token_ms: float | None = None
    first_prose_ms: float | None = None
    usages: list[TokenUsage] | None = None
    try:
        # T-030: one trace per turn (a no-op unless Langfuse keys are set),
        # and collect every LLM call's token usage for the whole turn so a
        # single cost_logs write can reconcile it against the assistant
        # message - both spans outlive the whole graph invocation below.
        with (
            tracer.turn(tenant_id=tenant_id, conversation_id=conversation_id) as turn,
            collect_usage() as usages,
            # P-2: which leg answered, how fast it produced anything, and whether
            # the race was needed. Scalars only - no prompts, no completions.
            collect_legs() as legs,
        ):
            # T-028: every LLM call the graph makes is time-bounded by the
            # tenant's llm_timeout via this wrapper - no node has to remember
            # to wrap its own.
            context = GraphContext(
                tenant_id=tenant_id,
                provider=TimeLimitedProvider(provider, limits.llm_timeout_s),
                embedder=embedder,
                reranker=reranker,
                tool_timeout_s=limits.tool_timeout_s,
                turn=turn,
            )
            # T-028 step cap: recursion_limit bounds node executions per turn,
            # so a pathological retry/route cycle can't spin forever. Overflow
            # is caught below and turned into the same graceful handoff as a
            # budget stop.
            stream = graph.astream(
                initial_state_dict,
                context=context,
                stream_mode="custom",
                config={"recursion_limit": limits.max_steps},
            )
            # Process events as they arrive rather than draining the whole
            # graph first. Structured, deterministic events (citations, quote)
            # stream live for responsiveness; prose (token/refusal) stays
            # buffered behind Inspection, so nothing the LLM *wrote* reaches
            # the customer until a draft is approved - the T-021 invariant is
            # unchanged.
            # P-2: the whole turn is capped, not each call - the cap is a promise
            # about the answer, and a turn is what the customer is waiting for. A
            # turn that blows it raises TimeoutError, which the handler below turns
            # into the same graceful handoff every other dead end gets.
            async with asyncio.timeout(limits.turn_budget_s):
                async for event in stream:
                    etype = event["type"]
                    if etype == "progress":
                        # D5: a fixed stage key naming the node now running.
                        # Carries no model output at all, so streaming it live
                        # narrates the wait without letting any unverified prose
                        # reach the customer - the T-021/US-060 invariant is
                        # untouched.
                        yield event
                    elif etype in ("citations", "quote"):
                        # Non-prose, and unchanged by a redraft (the quote row and
                        # the retrieved chunks a redraft stays grounded in don't
                        # move, and the redraft paths never re-emit them), so it
                        # is safe to show immediately instead of holding it back.
                        yield event
                    elif etype in ("price_summary", "catalog"):
                        response_payload = dict(event)
                        if etype == "price_summary":
                            price_summary_ms = _ms_since(turn_started)
                        buffer.append(event)
                    elif etype == "token":
                        if first_model_token_ms is None:
                            first_model_token_ms = _ms_since(turn_started)
                        full_text += str(event["text"])
                        buffer.append(event)
                    elif etype == "refusal":
                        # A refusal is always a complete, standalone message for
                        # its attempt - never combined with prior token events.
                        full_text = str(event["text"])
                        buffer = [event]
                    elif etype == "tool_call":
                        # T-030: a node invoked a tool - persisted against the
                        # assistant message below for the Surface-2 trace, never
                        # streamed to the customer.
                        tool_calls.append(event)
                    elif etype == "handoff":
                        handoff_seen = True
                        buffer.append(event)
                    elif etype == "redraft":
                        # T-018/T-021: a gate rejected the draft text already
                        # accumulated; the producing node is about to stream fresh
                        # prose. Only prose is discarded - the citations/quote
                        # already streamed live stay valid.
                        full_text = ""
                        buffer = [e for e in buffer if e["type"] not in ("token", "refusal")]
                    elif etype == "inspection":
                        verdicts = dict(event.get("verdicts", {}))
                        # F-3: which node authored the final draft rides the
                        # inspection event - it is the last node to run in
                        # every path, and the custom stream cannot read final
                        # graph state. The escalate branch carries
                        # "inspection" explicitly; all others pass through the
                        # producer's own claim.
                        author = event.get("author_node")
                        if author:
                            author_node = str(author)
                        if event.get("decision") == "retry":
                            full_text = ""
                            buffer = [e for e in buffer if e["type"] not in ("token", "refusal")]
                        else:
                            if first_prose_ms is None and any(
                                e["type"] in ("token", "refusal") for e in buffer
                            ):
                                first_prose_ms = _ms_since(turn_started)
                            for buffered_event in buffer:
                                yield buffered_event
                            buffer = []
                        # The raw "inspection" event is internal bookkeeping, never
                        # forwarded to the customer surface.
                    else:
                        buffer.append(event)
    except TimeoutError:
        # P-2: no leg produced a complete answer inside the turn budget. The
        # customer gets the handoff rather than a longer wait, and the reason
        # says which limit stopped it.
        logger.warning("chat turn exceeded its %.1fs budget; escalating", limits.turn_budget_s)
        await service.record_limit_escalation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            reason=TURN_BUDGET_ESCALATION_REASON,
            message=BUDGET_UNAVAILABLE_MESSAGE,
        )
        escalation_summary.schedule(
            tenant_id=tenant_id, conversation_id=conversation_id, provider=provider
        )
        if usages:
            await service.record_turn_costs(
                tenant_id=tenant_id, conversation_id=conversation_id, usages=usages
            )
        yield {"type": "refusal", "text": BUDGET_UNAVAILABLE_MESSAGE}
        yield {"type": "escalated"}
        yield {"type": "done"}
        return
    except GraphRecursionError:
        await service.record_limit_escalation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            reason=STEP_CAP_ESCALATION_REASON,
            message=BUDGET_UNAVAILABLE_MESSAGE,
        )
        escalation_summary.schedule(
            tenant_id=tenant_id, conversation_id=conversation_id, provider=provider
        )
        # T-030: the overflow turn still made real LLM calls before the cap
        # tripped - by definition more than a normal turn's worth. Its usage
        # must land in cost_logs or step-capped turns are invisible to the
        # T-028 daily budget, which sums exactly that table.
        if usages:
            await service.record_turn_costs(
                tenant_id=tenant_id, conversation_id=conversation_id, usages=usages
            )
        yield {"type": "refusal", "text": BUDGET_UNAVAILABLE_MESSAGE}
        yield {"type": "escalated"}
        yield {"type": "done"}
        return
    except Exception:
        # Anything else that kills a turn mid-flight (observed live:
        # OpenRouter forwarding an upstream failure as a 200 with
        # choices=null). Without this the generator simply stopped: the SSE
        # stream ended with no terminal event and the customer's chat bubble
        # span forever, which reads as infinite latency. Escalate like any
        # other dead end so the turn always terminates.
        logger.exception("chat turn failed mid-stream; handing off")
        # Non-terminal, unlike the three cap paths above. A provider falling
        # over is not a limit the tenant hit - it is a transient upstream fault
        # the customer had no part in, and ending their conversation over one
        # is the dead end C-5 removed everywhere else. The owner still gets the
        # queue item; the customer can just ask again.
        await service.record_limit_escalation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            reason=PROVIDER_ERROR_ESCALATION_REASON,
            message=PROVIDER_UNAVAILABLE_MESSAGE,
            terminal=False,
        )
        escalation_summary.schedule(
            tenant_id=tenant_id, conversation_id=conversation_id, provider=provider
        )
        # The failed turn still burned tokens before it died; they belong in
        # cost_logs for the same reason the step-cap path records its own.
        if usages:
            await service.record_turn_costs(
                tenant_id=tenant_id, conversation_id=conversation_id, usages=usages
            )
        yield {"type": "refusal", "text": PROVIDER_UNAVAILABLE_MESSAGE}
        yield {"type": "handoff"}
        yield {"type": "done"}
        return

    await service.persist_assistant_turn(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        full_text=full_text,
        verdicts=verdicts,
        tool_calls=tool_calls,
        usages=usages,
        author_node=author_node,
        response=response_payload,
        price_summary_ms=price_summary_ms,
    )
    if handoff_seen:
        escalation_summary.schedule(
            tenant_id=tenant_id, conversation_id=conversation_id, provider=provider
        )
    logger.info(
        "chat turn",
        extra={
            "total_ms": _ms_since(turn_started),
            # None when the turn produced no prose at all (a deterministic
            # order_status/escalation draft never emits token events).
            "first_model_token_ms": first_model_token_ms,
            "first_prose_ms": first_prose_ms,
            # What the inspection buffer costs this turn: prose existed this
            # much earlier than the customer was allowed to see it.
            "buffer_hold_ms": (
                round(first_prose_ms - first_model_token_ms, 1)
                if first_model_token_ms is not None and first_prose_ms is not None
                else None
            ),
            "chars": len(full_text),
            # P-2: which leg answered and whether the race was needed. The rest
            # of the turn's latency story is on this line already; the provider
            # half belongs next to it, not in a separate stream.
            **legs.as_attributes(),
        },
    )
    yield {"type": "done"}
