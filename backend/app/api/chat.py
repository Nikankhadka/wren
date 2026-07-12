"""T-011/T-012: bare customer chat, now routed through the agent graph.

``POST /api/chat`` is unauthenticated (the customer surface has no login) -
tenant scope comes entirely from the slug, resolved the same way T-005's
public tenant lookup does. The actual retrieval/generation logic lives in
app/agents/graph.py's compiled graph; this module resolves the
tenant/conversation, invokes the graph, and translates its custom-streamed
events into SSE.

T-021: nothing is customer-visible until Inspection clears a draft, so this
module now buffers every graph event instead of forwarding it immediately.
A "redraft" (price_gate) or "inspection" event with decision "retry" means
the buffered draft was rejected and discarded - the producing node is about
to stream a fresh one. An "inspection" event with any other decision means
the run is done accumulating for this pass: flush whatever is buffered
(the approved draft, or an escalation handoff message) and persist its
verdicts onto the assistant message row for the Surface-2 trace viewer.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field

from app.agents.graph import get_graph
from app.agents.spotlight import scan_input
from app.agents.state import AgentState, GraphContext
from app.core import config, db
from app.core.limits import (
    BUDGET_ESCALATION_REASON,
    BUDGET_UNAVAILABLE_MESSAGE,
    STEP_CAP_ESCALATION_REASON,
    TenantLimits,
    TimeLimitedProvider,
    tenant_over_budget,
)
from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.embedder import Embedder
from app.llm.provider import LLMProvider
from app.retrieval.dependency import get_reranker_dependency
from app.retrieval.rerank import Reranker

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    slug: str
    conversation_id: UUID | None = None
    message: str = Field(min_length=1)


async def _resolve_active_tenant(slug: str) -> UUID:
    pool = db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("select id, status from resolve_tenant_slug($1)", slug)
    if row is None or row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown tenant slug")
    tenant_id: UUID = row["id"]
    return tenant_id


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _initial_state(*, conversation_id: UUID, tenant_id: UUID, message: str) -> AgentState:
    return {
        "conversation_id": str(conversation_id),
        "tenant_id": str(tenant_id),
        "messages": [{"role": "customer", "content": message}],
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


async def _stream_escalated_response(*, conversation_id: UUID) -> AsyncIterator[str]:
    """T-020: an already-escalated conversation is terminal - no agent turn
    runs, the graph is never invoked. The customer's message is still
    persisted (kept in T-020's chat() caller) so the transcript stays
    complete for whoever picks it up on Surface 2."""
    yield _sse({"type": "conversation", "conversation_id": str(conversation_id)})
    yield _sse({"type": "escalated"})
    yield _sse({"type": "done"})


async def _record_limit_escalation(
    *, tenant_id: UUID, conversation_id: UUID, reason: str, message: str
) -> None:
    """T-028: a tenant hit a cap - record the escalation (same terminal
    machinery as escalation.py, deduped by 0011's partial unique index) and
    persist the graceful handoff as the assistant message. No graph runs."""
    async with db.tenant_context(tenant_id, "customer") as conn:
        await conn.execute(
            "insert into escalations (tenant_id, conversation_id, reason) values ($1, $2, $3) "
            "on conflict (tenant_id, conversation_id) where status = 'open' do nothing",
            tenant_id,
            conversation_id,
            reason,
        )
        await conn.execute(
            "update conversations set status = 'escalated' "
            "where id = $1 and tenant_id = $2 and status <> 'escalated'",
            conversation_id,
            tenant_id,
        )
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content, metadata) "
            "values ($1, $2, 'assistant', $3, $4)",
            tenant_id,
            conversation_id,
            message,
            json.dumps({"limit_escalation": reason}),
        )


async def _stream_budget_escalation(
    *, tenant_id: UUID, conversation_id: UUID
) -> AsyncIterator[str]:
    """T-028: over the daily budget - a polite handoff, never a stack trace,
    and the graph is never invoked."""
    yield _sse({"type": "conversation", "conversation_id": str(conversation_id)})
    await _record_limit_escalation(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        reason=BUDGET_ESCALATION_REASON,
        message=BUDGET_UNAVAILABLE_MESSAGE,
    )
    yield _sse({"type": "refusal", "text": BUDGET_UNAVAILABLE_MESSAGE})
    yield _sse({"type": "escalated"})
    yield _sse({"type": "done"})


async def _stream_chat_response(
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    message: str,
    provider: LLMProvider,
    embedder: Embedder,
    reranker: Reranker,
    limits: TenantLimits,
) -> AsyncIterator[str]:
    yield _sse({"type": "conversation", "conversation_id": str(conversation_id)})

    graph = get_graph()
    # T-028: every LLM call the graph makes is time-bounded by the tenant's
    # llm_timeout via this wrapper - no node has to remember to wrap its own.
    context = GraphContext(
        tenant_id=tenant_id,
        provider=TimeLimitedProvider(provider, limits.llm_timeout_s),
        embedder=embedder,
        reranker=reranker,
        tool_timeout_s=limits.tool_timeout_s,
    )
    initial_state = _initial_state(
        conversation_id=conversation_id, tenant_id=tenant_id, message=message
    )

    full_text = ""
    buffer: list[dict[str, object]] = []
    verdicts: dict[str, object] = {}
    try:
        # T-028 step cap: recursion_limit bounds node executions per turn, so a
        # pathological retry/route cycle can't spin forever. Overflow is caught
        # below and turned into the same graceful handoff as a budget stop.
        stream = graph.astream(
            initial_state,
            context=context,
            stream_mode="custom",
            config={"recursion_limit": limits.max_steps},
        )
        events = [event async for event in stream]
    except GraphRecursionError:
        await _record_limit_escalation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            reason=STEP_CAP_ESCALATION_REASON,
            message=BUDGET_UNAVAILABLE_MESSAGE,
        )
        yield _sse({"type": "refusal", "text": BUDGET_UNAVAILABLE_MESSAGE})
        yield _sse({"type": "escalated"})
        yield _sse({"type": "done"})
        return

    for event in events:
        etype = event["type"]
        if etype == "token":
            full_text += str(event["text"])
            buffer.append(event)
        elif etype == "refusal":
            # A refusal is always a complete, standalone message for its
            # attempt - never combined with prior token events.
            full_text = str(event["text"])
            buffer = [event]
        elif etype == "redraft":
            # T-018/T-021: a gate rejected the draft text already
            # accumulated; the producing node is about to stream fresh
            # prose. Structured events (quote, citations) survive the
            # discard - the quote row / retrieved chunks the redraft stays
            # grounded in are unchanged, and the redraft paths never
            # re-emit them.
            full_text = ""
            buffer = [e for e in buffer if e["type"] not in ("token", "refusal")]
        elif etype == "inspection":
            verdicts = dict(event.get("verdicts", {}))
            if event.get("decision") == "retry":
                full_text = ""
                buffer = [e for e in buffer if e["type"] not in ("token", "refusal")]
            else:
                for buffered_event in buffer:
                    yield _sse(buffered_event)
                buffer = []
            # The raw "inspection" event is internal bookkeeping, never
            # forwarded to the customer surface.
        else:
            buffer.append(event)

    async with db.tenant_context(tenant_id, "customer") as conn:
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content, metadata) "
            "values ($1, $2, 'assistant', $3, $4)",
            tenant_id,
            conversation_id,
            full_text,
            json.dumps({"inspection": verdicts} if verdicts else {}),
        )
    yield _sse({"type": "done"})


@router.post("")
async def chat(
    body: ChatRequest,
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
    reranker: Annotated[Reranker, Depends(get_reranker_dependency)],
) -> StreamingResponse:
    tenant_id = await _resolve_active_tenant(body.slug)

    async with db.tenant_context(tenant_id, "customer") as conn:
        if body.conversation_id is not None:
            row = await conn.fetchrow(
                "select status from conversations where id = $1 and tenant_id = $2",
                body.conversation_id,
                tenant_id,
            )
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
                )
            conversation_id = body.conversation_id
            already_escalated = row["status"] == "escalated"
        else:
            conversation_id = await conn.fetchval(
                "insert into conversations (tenant_id) values ($1) returning id", tenant_id
            )
            already_escalated = False
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content) "
            "values ($1, $2, 'customer', $3)",
            tenant_id,
            conversation_id,
            body.message,
        )

        # T-028: resolve this tenant's caps and check the daily budget before
        # any LLM call. Both reads happen inside the customer context so RLS
        # scopes them to this tenant.
        config_row = await conn.fetchrow(
            "select config from tenant_config where tenant_id = $1", tenant_id
        )
        limits = TenantLimits.resolve(
            json.loads(config_row["config"]) if config_row and config_row["config"] else {},
            config.get_settings(),
        )
        over_budget = await tenant_over_budget(conn, tenant_id, limits)

    # T-020: escalation is terminal - an already-escalated conversation never
    # gets another agent turn (the customer's message above is still kept,
    # so the transcript is complete for whoever picks it up on Surface 2).
    if already_escalated:
        return StreamingResponse(
            _stream_escalated_response(conversation_id=conversation_id),
            media_type="text/event-stream",
        )

    # T-028: over the daily budget - graceful handoff, graph never invoked.
    if over_budget:
        return StreamingResponse(
            _stream_budget_escalation(tenant_id=tenant_id, conversation_id=conversation_id),
            media_type="text/event-stream",
        )

    return StreamingResponse(
        _stream_chat_response(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message=body.message,
            provider=provider,
            embedder=embedder,
            reranker=reranker,
            limits=limits,
        ),
        media_type="text/event-stream",
    )
