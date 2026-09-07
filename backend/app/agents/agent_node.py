"""T-044/P-3: tool-driven agent node - one call per turn in the common case.

One node that replaces the old supervisor + six-specialist topology. Runs a
tool-calling loop (max 8 iterations) - the LLM decides which tools to call,
each gets executed in Python, results feed back to the conversation. When the
model returns prose instead of tool calls, the loop ends and a route is
determined from the set of tools that were invoked.

P-3 puts the tenant's context package (system prompt + owner profile + confirmed catalog + corpus)
into that first call. When the corpus fits the budget (O-4's fast path) it is
already in the prompt, so ``search_knowledge`` is not offered at all - there is
nothing for it to fetch - and the model's prose answer *is* the draft: the turn
is one LLM call, and the draft node is skipped entirely. Everything after the
draft is unchanged: the price gate and inspection still run, in the same order,
with the same authority, and nothing reaches the customer until inspection
passes.

Above the budget the package carries no corpus, ``search_knowledge`` is offered,
and the turn keeps its previous shape (agent call -> tool -> draft call).

The draft is not streamed token by token here, and that costs the customer
nothing: the inspection buffer (T-021/US-060) holds every token until the whole
draft has been judged, so streaming out of this node would only stream into a
buffer. The prose is emitted as one ``token`` event when the call returns.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from uuid import UUID

from langgraph.config import get_stream_writer
from langgraph.runtime import get_runtime
from pydantic import BaseModel, Field

from app.agents.contract import contract_prelude
from app.agents.draft_node import citation_source
from app.agents.drafting import MONEY_GUIDANCE
from app.agents.spotlight import Spotlight, new_spotlight
from app.agents.state import AgentState, GraphContext
from app.agents.tools import lookup_order_or_ticket
from app.llm.provider import ChatMessage, ToolSpec
from app.retrieval.service import retrieve
from app.services.context_package import ContextPackage, get_package
from app.services.retrieval import get_business_context
from app.shared import db
from app.shared.limits import with_timeout
from app.shared.text import plain_dashes

logger = logging.getLogger("app.agents.agent_node")

_CITATION_RE = re.compile(r"\[(\d+)\]")

_MAX_ITERATIONS = 8
_REFUSAL_SCORE_THRESHOLD = 0.05

# How much of the conversation goes back into the prompt. Enough for a customer
# to say "and how much is that one?" and be understood, short enough that a long
# thread never crowds out the business material it has to share the budget with.
_HISTORY_MESSAGES = 10

# The per-tool bullet list this used to carry duplicated the ToolSpec
# descriptions the model already receives, and went stale the moment _tools_for
# stopped offering a tool. What is left is the part the specs cannot say: when
# to reach for a tool at all, and when to hand off.
#
# It no longer says "if you are unsure, escalate". That line turned every
# question the material answered indirectly into a handoff - including the most
# ordinary question a customer asks, "what do you offer?" - because guessing at
# a tool felt riskier to the model than escalating. Not knowing is a reason to
# say so and offer a handoff, not a reason to end the turn.
_TOOL_GUIDANCE = (
    "Answer from the business facts and material in this prompt first. Reach for "
    "a tool only when the answer genuinely is not here - a specific order to look "
    "up, a quote to compute.\n"
    "When the customer asks what the business offers, or for a list of its "
    "services, items, or prices, the answer is in the material in this prompt - "
    "the confirmed catalog and the published material together. Answer from "
    "there rather than searching for a tool, and do not hand off.\n"
    "If the material does not cover what they asked, say so plainly and offer to "
    "have someone from the business follow up. Greetings, thanks, and questions "
    "about what you can do need no tool at all.\n"
    "If the customer asks to speak to a person, call create_escalation straight "
    "away - do not try to talk them out of it. Tell them someone from the "
    "business has been notified, and carry on helping with anything else they "
    "ask in the meantime."
)

# The customer bubble renders plain text with citation chips - it does not parse
# markdown, so asterisks and hyphens arrive on screen as asterisks and hyphens.
# frontend.md section 9 makes that a rule rather than a rendering accident: chat
# output is prose, and anything structured belongs in a UI component.
_STYLE_GUIDANCE = (
    "Write the way a person types in a chat: plain sentences, no markdown, no "
    "bullet points, no headings, no bold or italic markers, no tables, no code "
    "blocks. When you have several things to say, say them in sentences. Keep "
    "answers short - a few sentences unless the customer asked for detail."
)

_FAST_PATH_GUIDANCE = (
    "The business's own material is included below in full - it is everything "
    "the business has published to you except the confirmed offering catalog, "
    "which is provided separately above. Do not look for a search tool. Answer "
    "from that material and from the business facts above it, citing each factual "
    "claim with its bracket number, e.g. [1]. If the answer is not there, say so "
    "plainly and offer to have someone from the business follow up - never "
    "invent an answer, a policy, or a price.\n"
    "You are this business's assistant, not a general assistant: answer only "
    "questions about the business, its products, services, policies, and orders. "
    "For anything else - general knowledge, trivia, other companies, advice "
    "unrelated to this business - do not answer it even if you know it. Say that "
    "you can only help with this business and offer to help with something you "
    "can. Greetings, thanks, and questions about what you can do are fine to "
    "answer directly."
)


def _tool_result(spotlight: Spotlight, payload: dict[str, Any]) -> str:
    """Serialize a tool result for the model, spotlight-wrapped (T-027).

    Everything a tool returns is ultimately tenant-authored - catalog names and
    descriptions, pricing-rule labels, order statuses, even an exception string
    that may quote a row. The agent loop feeds these straight back as ``tool``
    messages and then decides which tool to call next, so undelimited tool
    output is an instruction channel. Wrapping the whole payload rather than
    hand-picking fields means a later change to what a tool returns cannot
    silently open that channel again.
    """
    return spotlight.wrap(json.dumps(payload))


class _SearchKnowledgeArgs(BaseModel):
    query: str = Field(description="What to search the knowledge base for")


class _RecommendItemsArgs(BaseModel):
    preferences: str = Field(description="What the customer is looking for - needs, constraints")


# F-1: the selection schema moved here from the deleted quoting specialist.
# Public so the deterministic-pricing guard test can pin the no-money-fields
# invariant on the live schema instead of a copy.
class SelectionChoice(BaseModel):
    rule_code: str | None = None
    catalog_item_id: str | None = None
    quantity: int = Field(ge=1, le=999)


class GetQuoteInputsArgs(BaseModel):
    selections: list[SelectionChoice] = Field(description="Items/services to quote")


class _LookupOrderArgs(BaseModel):
    ref_code: str = Field(description="The order/repair/ticket reference code")
    customer_ref: str | None = Field(default=None, description="Customer reference if known")


class _CreateEscalationArgs(BaseModel):
    reason: str = Field(description="Why this needs human attention")
    # C-6: what the owner reads in their Chats list instead of a reason code.
    # Captured in the tool call the model is already making - no extra call,
    # no second prompt pass. Optional so an older/edge model that omits it
    # still escalates; the row falls back to ``reason``.
    summary: str = Field(
        default="",
        description=(
            "One plain line of what the customer wants, for the business owner "
            "to read - e.g. 'Catering for 20 on Friday, wants a price'"
        ),
    )


async def _search_knowledge_impl(
    conn: Any,
    tenant_id: UUID,
    query: str,
    embedder: Any,
    reranker: Any,
) -> list[dict[str, Any]]:
    """Turn-time retrieval, through O-4's seam.

    Only reached on the hybrid path (a fast-path package already carries the
    corpus, so this tool is not offered), but it calls the seam rather than
    ``retrieve`` directly so there is exactly one way grounding material is
    fetched. The relevance threshold applies to scored results only - nothing
    unscored ever comes back here.
    """
    context = await get_business_context(
        conn,
        tenant_id=tenant_id,
        query=query,
        embedder=embedder,
        reranker=reranker,
        top_k=5,
    )
    relevant = [
        chunk
        for chunk in context.chunks
        if context.fast_path or chunk.score > _REFUSAL_SCORE_THRESHOLD
    ]
    return [
        {"id": str(chunk.id), "content": chunk.content, "metadata": chunk.metadata}
        for chunk in relevant
    ]


async def _recommend_items_impl(
    conn: Any,
    tenant_id: UUID,
    preferences: str,
    embedder: Any,
    reranker: Any,
) -> list[dict[str, Any]]:
    results = await retrieve(
        conn,
        tenant_id=tenant_id,
        query=preferences,
        embedder=embedder,
        reranker=reranker,
        top_k=5,
        metadata_kind="catalog_item",
    )
    item_ids = [
        UUID(chunk.metadata["catalog_item_id"])
        for chunk in results
        if chunk.metadata.get("catalog_item_id")
    ]
    rows = (
        await conn.fetch(
            "select id, name, description, price_cents from offerings "
            "where tenant_id = $1 and id = any($2::uuid[]) and active",
            tenant_id,
            item_ids,
        )
        if item_ids
        else []
    )
    return [
        {
            "catalog_item_id": str(row["id"]),
            "name": row["name"],
            "description": row["description"],
            "price_cents": row["price_cents"],
        }
        for row in rows
    ]


async def _get_quote_inputs_impl(
    conn: Any,
    tenant_id: UUID,
    selections: list[dict[str, Any]],
) -> dict[str, Any]:
    from app.pricing.engine import Selection, SelectionError, compute_quote

    engine_selections = []
    for sel in selections:
        if sel.get("rule_code"):
            engine_selections.append(Selection("rule", sel["rule_code"], sel["quantity"]))
        elif sel.get("catalog_item_id"):
            engine_selections.append(Selection("item", sel["catalog_item_id"], sel["quantity"]))
        else:
            raise SelectionError("a selection must name a rule_code or a catalog_item_id")
    quote = await compute_quote(conn, tenant_id, engine_selections)
    return {
        "line_items": [item.to_dict() for item in quote.line_items],
        "subtotal_cents": quote.subtotal_cents,
        "tax_cents": quote.tax_cents,
        "total_cents": quote.total_cents,
    }


async def _create_escalation_impl(
    conn: Any,
    tenant_id: UUID,
    conversation_id: UUID,
    reason: str,
    summary: str = "",
) -> None:
    # C-5: records the handoff, does not end the conversation. The status flip
    # that used to live here is gone from every agent-side path - see
    # app/agents/escalation.py for why. Only limit escalations still terminate.
    await conn.execute(
        "insert into escalations (tenant_id, conversation_id, reason, summary) "
        "values ($1, $2, $3, $4) "
        "on conflict (tenant_id, conversation_id) where status = 'open' do nothing",
        tenant_id,
        conversation_id,
        reason,
        summary or None,
    )


def _determine_route(called_tools: set[str], *, has_corpus: bool = False) -> str:
    if not called_tools:
        # With the corpus already in the prompt (fast path), an answer with no
        # tool call is a grounded answer, not small talk - inspection must judge
        # it against that material, which the "knowledge" route is what selects.
        return "knowledge" if has_corpus else "conversation"
    if "create_escalation" in called_tools:
        return "escalation"
    if "get_quote_inputs" in called_tools:
        return "quoting"
    if "recommend_items" in called_tools:
        return "recommendation"
    if "lookup_order_or_ticket" in called_tools:
        return "order_status"
    if "search_knowledge" in called_tools:
        return "knowledge"
    return "conversation"


# messages rows carry the transcript's own roles; the wire takes user/assistant.
# A human agent replying for the business is the assistant side of the
# conversation as far as the model is concerned.
_WIRE_ROLES = {"customer": "user", "assistant": "assistant", "human_agent": "assistant"}


def _system_prompt(package: ContextPackage, spotlight: Spotlight) -> str:
    """The turn's system prompt, built fresh so the spotlight token is fresh.

    W-9: it opens with the code-owned contract and the tenant's voice, and
    everything after that is business data - which is exactly what the
    contract's own BUSINESS KNOWLEDGE section tells the model to expect.
    """
    parts = [contract_prelude(package.business_name, package.voice)]
    profile = package.profile_text()
    if profile:
        parts.append(f"Business facts the owner gave you:\n{profile}")
    offerings = package.offerings_text()
    if offerings:
        parts.append(
            "The active offering catalog below is authoritative for what the business "
            "currently offers, including names, availability, and prices. Use reviewed "
            "knowledge for additional descriptions and supporting details. When both "
            "are relevant, answer from the catalog and the business material together "
            "in one reply, naming the offerings relevant to the question rather than "
            "enumerating the complete catalog.\n" + spotlight.wrap(offerings)
        )
    parts.append(_TOOL_GUIDANCE)
    parts.append(_STYLE_GUIDANCE)
    # Unconditional: a figure can appear in any answer, on any path, whether or
    # not the corpus made it into this turn's prompt.
    parts.append(MONEY_GUIDANCE)
    if package.fast_path and package.chunks:
        parts.append(_FAST_PATH_GUIDANCE)
        parts.append(
            "Business material:\n"
            + "\n\n".join(
                f"[{i + 1}] {spotlight.wrap(chunk.content)}"
                for i, chunk in enumerate(package.chunks)
            )
        )
    elif package.fast_path:
        # Fast path with nothing in it: the tenant has published no material at
        # all. Say so rather than letting the model fill the gap.
        parts.append(
            "The business has not published any material to you yet. Answer only "
            "from the business facts above; for anything else, say you do not "
            "have that information and offer to have someone from the business "
            "follow up."
        )
    parts.append(spotlight.instruction())
    return "\n\n".join(parts)


def _tools_for(package: ContextPackage) -> list[ToolSpec]:
    """The tool set for this turn.

    The two retrieval tools are offered only when the package did not already
    bring the corpus: on the fast path there is nothing left for them to find,
    and offering them would buy a round trip for material already in the prompt.

    ``recommend_items`` joins ``search_knowledge`` under that rule. It searches
    only catalog projections, while the authoritative active offering rows are
    already included in the prompt for enumeration and pricing. Offering it on
    the fast path would add an embedding round trip for a question the package
    can already answer.
    """
    tools = [
        ToolSpec(
            name="get_quote_inputs",
            description="Produce a price quote for selected items/services",
            args_schema=GetQuoteInputsArgs,
        ),
        ToolSpec(
            name="lookup_order_or_ticket",
            description="Look up the status of an existing order, repair, or ticket by code",
            args_schema=_LookupOrderArgs,
        ),
        ToolSpec(
            name="create_escalation",
            description="Hand off to someone at the business when you cannot help confidently",
            args_schema=_CreateEscalationArgs,
        ),
    ]
    if package.fast_path:
        return tools
    return [
        ToolSpec(
            name="search_knowledge",
            description="Search the business knowledge base for policies or FAQs",
            args_schema=_SearchKnowledgeArgs,
        ),
        ToolSpec(
            name="recommend_items",
            description="Recommend products/services based on customer preferences",
            args_schema=_RecommendItemsArgs,
        ),
        *tools,
    ]


def _cited_chunks(answer: str, chunks: list[Any]) -> list[dict[str, Any]]:
    """The chunks the answer actually cited, in citation order.

    A fast-path package can hold the whole corpus; the customer's citation chips
    should name what the answer used, not everything the model could have read.
    """
    seen: list[int] = []
    for match in _CITATION_RE.finditer(answer):
        index = int(match.group(1))
        if 1 <= index <= len(chunks) and index not in seen:
            seen.append(index)
    return [
        {
            "id": str(chunks[index - 1].id),
            "content": chunks[index - 1].content,
            "metadata": chunks[index - 1].metadata,
        }
        for index in seen
    ]


async def run(state: AgentState) -> dict[str, Any]:
    runtime = get_runtime(GraphContext)
    ctx = runtime.context
    writer = get_stream_writer()

    # One spotlight per turn: every tool result below is wrapped with it, and
    # the instruction that explains the delimiters ships in the same prompt.
    spotlight = new_spotlight()

    called_tools: set[str] = set()
    retrieved_chunks: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    engine_quote: dict[str, Any] | None = None
    lookup_result: dict[str, Any] | None = None
    answer_text = ""

    async with db.tenant_context(ctx.tenant_id, "customer") as conn:
        # P-3: assembled at chat open and cached by (tenant, knowledge_version),
        # so this is normally a version check, not an assembly.
        package = await get_package(conn, ctx.tenant_id)
        # W-5/W-9: state-borne for the same reason as offerings_text below - the
        # draft node re-enters on a redraft with no package of its own, and
        # re-reading the tenant there is the per-turn query this ticket removes.
        contract = contract_prelude(package.business_name, package.voice)
        tools = _tools_for(package)
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=_system_prompt(package, spotlight)),
        ]
        tail = state["messages"][-_HISTORY_MESSAGES:]
        for m in tail:
            messages.append(
                ChatMessage(role=_WIRE_ROLES.get(m["role"], "user"), content=m["content"])
            )

        for iteration in range(_MAX_ITERATIONS):
            with ctx.turn.span("agent_tool_call") as span:
                model_started = time.perf_counter()
                turn = await ctx.provider.chat_with_tools(
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
                model_ms = round((time.perf_counter() - model_started) * 1000, 1)
                span.set(tool_calls=len(turn.tool_calls))
            logger.info(
                "agent model call",
                extra={
                    "iteration": iteration,
                    "duration_ms": model_ms,
                    "tool_calls": len(turn.tool_calls),
                },
            )

            if not turn.tool_calls:
                # conventions.md 1 bans the em dash, and a prompt rule alone does
                # not hold it (Appendix D item 3). Normalized here, where the
                # one-call answer is complete, and in drafting.stream_draft for
                # every other prose route.
                answer_text = plain_dashes((turn.text or "").strip())
                break

            if turn.history_message is None:
                logger.error("provider returned tool calls without history message")
                answer_text = (
                    "I can help with this business's published information, "
                    "or connect you with a person."
                )
                break

            called_tools.update(call.name for call in turn.tool_calls)
            tool_result_messages: list[ChatMessage] = []

            for call in turn.tool_calls:
                started = time.perf_counter()
                failed = False
                try:
                    if call.name == "search_knowledge":
                        sk_args = _SearchKnowledgeArgs.model_validate(call.args)
                        chunks = await _search_knowledge_impl(
                            conn,
                            ctx.tenant_id,
                            sk_args.query,
                            ctx.embedder,
                            ctx.reranker,
                        )
                        retrieved_chunks = chunks
                        result_text = _tool_result(spotlight, {"found": len(chunks)})
                        writer(
                            {
                                "type": "tool_call",
                                "name": "search_knowledge",
                                "arguments": call.args,
                                "result": {"chunks": len(chunks)},
                                "success": True,
                                "latency_ms": int((time.perf_counter() - started) * 1000),
                            }
                        )
                    elif call.name == "recommend_items":
                        ri_args = _RecommendItemsArgs.model_validate(call.args)
                        items = await _recommend_items_impl(
                            conn,
                            ctx.tenant_id,
                            ri_args.preferences,
                            ctx.embedder,
                            ctx.reranker,
                        )
                        selections = items
                        result_text = _tool_result(spotlight, {"found": len(items), "items": items})
                        writer(
                            {
                                "type": "tool_call",
                                "name": "recommend_items",
                                "arguments": call.args,
                                "result": {"items": len(items)},
                                "success": True,
                                "latency_ms": int((time.perf_counter() - started) * 1000),
                            }
                        )
                    elif call.name == "get_quote_inputs":
                        qi_args = GetQuoteInputsArgs.model_validate(call.args)
                        raw_sel = [s.model_dump(exclude_none=True) for s in qi_args.selections]
                        quote = await _get_quote_inputs_impl(conn, ctx.tenant_id, raw_sel)
                        engine_quote = quote
                        result_text = _tool_result(
                            spotlight,
                            {
                                "total_cents": quote["total_cents"],
                                "line_items": quote["line_items"],
                            },
                        )
                        writer(
                            {
                                "type": "tool_call",
                                "name": "get_quote_inputs",
                                "arguments": call.args,
                                "result": {"total_cents": quote["total_cents"]},
                                "success": True,
                                "latency_ms": int((time.perf_counter() - started) * 1000),
                            }
                        )
                    elif call.name == "lookup_order_or_ticket":
                        lo_args = _LookupOrderArgs.model_validate(call.args)
                        result = await with_timeout(
                            lookup_order_or_ticket(
                                conn,
                                ctx.tenant_id,
                                lo_args.ref_code,
                                lo_args.customer_ref,
                            ),
                            ctx.tool_timeout_s,
                            what="order lookup",
                        )
                        lookup_result = {
                            "ref_code": result.ref_code,
                            "found": result.found,
                            "status": result.status,
                            "kind": result.kind,
                        }
                        result_text = _tool_result(
                            spotlight,
                            {
                                "found": result.found,
                                "status": result.status,
                                "kind": result.kind,
                            },
                        )
                        writer(
                            {
                                "type": "tool_call",
                                "name": "lookup_order_or_ticket",
                                "arguments": call.args,
                                "result": {
                                    "found": result.found,
                                    "status": result.status,
                                    "kind": result.kind,
                                },
                                "success": True,
                                "latency_ms": int((time.perf_counter() - started) * 1000),
                            }
                        )
                    elif call.name == "create_escalation":
                        ce_args = _CreateEscalationArgs.model_validate(call.args)
                        await _create_escalation_impl(
                            conn,
                            ctx.tenant_id,
                            UUID(state["conversation_id"]),
                            ce_args.reason,
                            ce_args.summary,
                        )
                        writer({"type": "handoff"})
                        result_text = _tool_result(
                            spotlight, {"escalated": True, "reason": ce_args.reason}
                        )
                        writer(
                            {
                                "type": "tool_call",
                                "name": "create_escalation",
                                "arguments": call.args,
                                "result": {"escalated": True},
                                "success": True,
                                "latency_ms": int((time.perf_counter() - started) * 1000),
                            }
                        )
                    else:
                        logger.warning("unknown tool requested: %s", call.name)
                        result_text = _tool_result(
                            spotlight, {"error": f"unknown tool: {call.name}"}
                        )
                except Exception as exc:
                    failed = True
                    logger.exception("tool %s failed", call.name)
                    result_text = _tool_result(spotlight, {"error": str(exc)})
                    writer(
                        {
                            "type": "tool_call",
                            "name": call.name,
                            "arguments": call.args,
                            "result": {"error": str(exc)},
                            "success": False,
                            "latency_ms": int((time.perf_counter() - started) * 1000),
                        }
                    )

                logger.info(
                    "agent tool",
                    extra={
                        # Not "name": that is a reserved LogRecord attribute, and
                        # logging raises KeyError rather than shadowing it. This
                        # line sits outside the try above, so that KeyError used
                        # to escape the node and kill every turn that called any
                        # tool - but only where logging is enabled for INFO,
                        # which is production (config.log_level) and not the
                        # default test level. pyproject pins the suite to INFO
                        # so the next one of these fails a test instead.
                        "tool": call.name,
                        "duration_ms": int((time.perf_counter() - started) * 1000),
                        "success": not failed,
                    },
                )

                tool_result_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result_text,
                    }
                )

            messages.append(turn.history_message)
            messages.extend(tool_result_messages)

            if "create_escalation" in called_tools:
                break

    route = _determine_route(called_tools, has_corpus=bool(package.chunks))

    if route == "escalation":
        return {
            "route": route,
            "escalated": True,
            "escalation_reason": "tool_requested",
        }

    if answer_text and not called_tools:
        # P-3: the model answered straight from the package, so its prose is the
        # draft and the draft node is skipped - one LLM call for the whole turn.
        #
        # Only a turn that called no tools qualifies, for two hard reasons.
        # Prose after ``search_knowledge`` is not grounded in anything the model
        # read: that tool hands back a match *count*, never the chunks, and
        # draft_node is where the retrieved text actually enters a prompt. And
        # prose after a money tool would bypass draft_node's quoting rules,
        # which are what keep figures off the model (the quote card is the sole
        # source of numbers). Saving a call is never worth either.
        #
        # Everything after the draft is untouched: this text still goes through
        # inspection before a customer sees any of it.
        grounding = [
            {"id": str(chunk.id), "content": chunk.content, "metadata": chunk.metadata}
            for chunk in package.chunks
        ]
        cited = _cited_chunks(answer_text, package.chunks) if package.chunks else []
        if cited:
            writer(
                {
                    "type": "citations",
                    "citations": [
                        {
                            "index": i + 1,
                            "source": citation_source(chunk),
                            "snippet": chunk["content"][:200],
                        }
                        for i, chunk in enumerate(cited)
                    ],
                }
            )
        writer({"type": "token", "text": answer_text})
        logger.info(
            "agent direct answer",
            extra={"route": route, "chars": len(answer_text), "cited": len(cited)},
        )
        return {
            "route": route,
            "draft_response": answer_text,
            "draft_deterministic": False,
            "retrieved_chunks": grounding,
            "selections": selections,
            "engine_quote": engine_quote,
            "lookup": lookup_result,
            "owner_material": package.owner_material(),
            "offerings_text": package.offerings_text(),
            "contract": contract,
            "author_node": "agent",
        }

    if route == "knowledge" and not retrieved_chunks:
        # The package brought the corpus but the model returned no prose to use
        # it (an empty completion, or it stopped after a non-search tool). The
        # draft node can still write a grounded answer from that material, so
        # hand it over rather than letting the turn refuse with nothing in hand.
        retrieved_chunks = [
            {"id": str(chunk.id), "content": chunk.content, "metadata": chunk.metadata}
            for chunk in package.chunks
        ]

    return {
        "route": route,
        "retrieved_chunks": retrieved_chunks,
        "selections": selections,
        "engine_quote": engine_quote,
        "lookup": lookup_result,
        "owner_material": package.owner_material(),
        "offerings_text": package.offerings_text(),
        "contract": contract,
    }
