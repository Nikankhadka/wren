"""T-044: Draft node - composes the final customer-facing response from data
collected by the agent node's tool calls.

W-9: every route that asks a model for prose now opens with the same code-owned
contract (``app/agents/contract.py``), carried in graph state by the agent node.
Conversation, recommendation, and quoting saw no tenant configuration at all
before this, and knowledge read ``tenant_config`` itself, once per turn. What is
left per route is only what makes that route different: its grounding material
and the rules that follow from it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.config import get_stream_writer
from langgraph.runtime import get_runtime

from app.agents.drafting import MONEY_GUIDANCE, stream_draft
from app.agents.escalation import HANDOFF_MESSAGE
from app.agents.spotlight import new_spotlight
from app.agents.state import AgentState, GraphContext
from app.llm.provider import ChatMessage
from app.shared import db

# F-1: the one refusal constant for a knowledge route with nothing to answer
# from. Public because evals and API tests assert on the exact customer-facing
# text; this node is where that text is produced.
REFUSAL_MESSAGE = (
    "I don't have information about that. Please contact the business directly for help."
)
_RECOMMENDATION_REFUSAL = (
    "I don't have anything that matches what you're looking for. "
    "Please contact the business directly for help."
)
_QUOTING_NO_CANDIDATES = (
    "I can't put together a quote for that - the business hasn't listed "
    "anything I could price it from. Please contact them directly."
)
_ORDER_NOT_FOUND_TEMPLATE = "I can't find {ref_code} - please double-check the code."
_ORDER_ASK_FOR_CODE = "Could you share the order, repair, or ticket code so I can look it up?"
_ORDER_FOUND_TEMPLATE = 'Your {kind} {ref_code} is currently "{status}".'

# Identity and warmth used to be stated here; both now come from the contract
# and the tenant's voice, so what is left is what this route alone knows: the
# customer asked nothing the business material has to answer.
_SYSTEM_PROMPT_CONVERSATION = (
    "The customer sent a greeting, said thanks, or asked a meta question about "
    "who you are or what you can do. Respond naturally - greet them back and "
    "offer to help with questions about products, services, pricing, or orders. "
    "Keep it short (1-2 sentences). Never answer questions about the business "
    "itself - if they ask what something costs or how something works, say 'I "
    "can help you find out about that' instead of guessing.\n"
    f"{MONEY_GUIDANCE}"
)


def _with_contract(state: AgentState, route_prompt: str) -> str:
    """The contract first, then the route's own instructions.

    Order is the authority statement: the contract is what the model reads
    before anything a tenant configured, and everything after it is business
    data by the contract's own terms.
    """
    contract = state.get("contract", "")
    return f"{contract}\n\n{route_prompt}" if contract else route_prompt


def _redraft_note(violations: list[str] | None, extra: str = "") -> str:
    """The instruction appended to a draft prompt after the price gate or
    inspection rejected the previous attempt. One definition so that every
    retryable route's second attempt actually differs from its first - a
    redraft built from an unchanged prompt is guaranteed to fail the same way.
    """
    if not violations:
        return ""
    return (
        "\n\nYour previous draft was rejected: "
        + "; ".join(violations)
        + ". Redraft now, addressing this"
        + (f" - {extra}" if extra else "")
        + "."
    )


def _build_knowledge_prompt(
    chunks: list[dict[str, Any]],
    violations: list[str] | None,
    *,
    offerings_text: str = "",
) -> str:
    spotlight = new_spotlight()
    context_block = "\n\n".join(
        f"[{i + 1}] {spotlight.wrap(c['content'])}" for i, c in enumerate(chunks)
    )
    # W-5: the confirmed catalog reaches this prompt as a second grounded block
    # alongside the numbered chunks - it is state-borne (see AgentState.
    # offerings_text) rather than fetched here, because the corpus retrieval
    # that produced ``chunks`` deliberately excludes catalog_item rows, and
    # this is the hybrid path's only chance to put the two sources in front of
    # one generation together (agent_node.py's fast path already does this in
    # its own system prompt).
    offerings_block = f"\n\n{spotlight.wrap(offerings_text)}" if offerings_text else ""
    prompt = (
        f"{spotlight.instruction()}\n"
        "Answer the customer's question using ONLY the confirmed offerings and "
        "the numbered context below. Cite every factual claim with its bracket "
        "number, e.g. [1]. If the context doesn't fully answer the question, "
        "say what you don't know - never invent information.\n"
        f"{MONEY_GUIDANCE}\n\n"
        f"Context:\n{context_block}"
        f"{offerings_block}"
    )
    return prompt + _redraft_note(violations)


def _build_recommendation_prompt(
    selections: list[dict[str, Any]],
    violations: list[str] | None,
) -> str:
    spotlight = new_spotlight()
    items_block = "\n".join(
        f"[{i + 1}] {spotlight.wrap(sel['name'] + ': ' + (sel['description'] or ''))}"
        + (f" (${sel['price_cents'] / 100:.2f})" if sel.get("price_cents") is not None else "")
        for i, sel in enumerate(selections)
    )
    prompt = (
        "You are recommending items to a customer. Recommend ONLY from the "
        "numbered list below, with a short reason for each - never invent an "
        "item or a price that isn't listed.\n"
        f"{MONEY_GUIDANCE}\n"
        f"{spotlight.instruction()}\n\nAvailable items:\n{items_block}"
    )
    return prompt + _redraft_note(
        violations, "name prices only exactly as listed above, or leave them out entirely"
    )


def _build_quoting_prompt(
    engine_quote: dict[str, Any],
    violations: list[str] | None,
) -> str:
    # Line-item labels come from tenant-authored pricing rules and catalog
    # items, so they are wrapped like every other piece of tenant data (T-027).
    # Quantities are engine-computed and safe unwrapped.
    spotlight = new_spotlight()
    coverage = "\n".join(
        f"- {spotlight.wrap(item['label'])} x{item['quantity']}"
        for item in engine_quote["line_items"]
    )
    prompt = (
        "You are presenting a price quote to a customer. A quote card showing "
        "the exact line items, quantities, and totals is displayed alongside "
        "your message. Briefly explain what the quote covers, referring to the "
        "card for figures. Do NOT state any prices, totals, or other monetary "
        "amounts yourself - the card is the single source of numbers.\n"
        f"{spotlight.instruction()}\n\n"
        f"The quote covers:\n{coverage}"
    )
    return prompt + _redraft_note(violations, "state no monetary amounts yourself either way")


async def run(state: AgentState) -> dict[str, Any]:
    runtime = get_runtime(GraphContext)
    ctx = runtime.context
    writer = get_stream_writer()
    route = state["route"]
    query = state["messages"][-1]["content"]

    if state.get("escalated"):
        # One handoff message, defined next to the node that owns handoffs -
        # this used to hold its own copy of the text and kept the pre-C-5
        # sign-off after escalation.py had already moved on.
        handoff = state.get("draft_response") or HANDOFF_MESSAGE
        if not state.get("draft_response"):
            writer({"type": "refusal", "text": handoff})
        # An escalation upstream (price_gate/inspection) already named the
        # author; the agent-tool handoff is the escalation node's text, so it
        # claims it here.
        return {
            "draft_response": handoff,
            "draft_deterministic": True,
            "escalated": True,
            "author_node": state.get("author_node") or "escalation",
        }

    violations = state.get("price_violations") or state.get("inspection_violations")
    clear_violations: dict[str, Any] = {}
    if state.get("price_violations"):
        clear_violations["price_violations"] = []
    if state.get("inspection_violations"):
        clear_violations["inspection_violations"] = []

    if route == "conversation":
        messages: list[ChatMessage] = [
            {
                "role": "system",
                "content": _with_contract(
                    state, _SYSTEM_PROMPT_CONVERSATION + _redraft_note(violations)
                ),
            },
            {"role": "user", "content": query},
        ]
        text = await stream_draft(ctx.provider, messages)
        return {
            "draft_response": text,
            "draft_deterministic": False,
            **clear_violations,
            "author_node": "draft",
        }

    if route == "knowledge":
        retrieved_chunks = state.get("retrieved_chunks", [])
        if not retrieved_chunks:
            writer({"type": "refusal", "text": REFUSAL_MESSAGE})
            return {
                "draft_response": REFUSAL_MESSAGE,
                "retrieved_chunks": [],
                "draft_deterministic": True,
                "author_node": "draft",
            }
        citations = [
            {"index": i + 1, "source": citation_source(c), "snippet": c["content"][:200]}
            for i, c in enumerate(retrieved_chunks)
        ]
        writer({"type": "citations", "citations": citations})
        system_prompt = _with_contract(
            state,
            _build_knowledge_prompt(
                retrieved_chunks,
                violations=violations,
                offerings_text=state.get("offerings_text", ""),
            ),
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        text = await stream_draft(ctx.provider, messages)
        return {
            "draft_response": text,
            "retrieved_chunks": retrieved_chunks,
            **clear_violations,
            "author_node": "draft",
        }

    if route == "recommendation":
        selections = state.get("selections", [])
        if not selections:
            writer({"type": "refusal", "text": _RECOMMENDATION_REFUSAL})
            return {
                "draft_response": _RECOMMENDATION_REFUSAL,
                "selections": [],
                "draft_deterministic": True,
                "author_node": "draft",
            }
        system_prompt = _with_contract(state, _build_recommendation_prompt(selections, violations))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        text = await stream_draft(ctx.provider, messages)
        return {
            "draft_response": text,
            "selections": selections,
            **clear_violations,
            "author_node": "draft",
        }

    if route == "quoting":
        engine_quote = state.get("engine_quote")
        if not engine_quote:
            writer({"type": "refusal", "text": _QUOTING_NO_CANDIDATES})
            return {
                "draft_response": _QUOTING_NO_CANDIDATES,
                "selections": [],
                "draft_deterministic": True,
                "author_node": "draft",
            }
        if not engine_quote.get("quote_id"):
            import json as _json

            async with db.tenant_context(ctx.tenant_id, "customer") as conn:
                quote_id = await conn.fetchval(
                    "insert into quotes (tenant_id, conversation_id, line_items, "
                    "subtotal_cents, tax_cents, total_cents, status) "
                    "values ($1, $2, $3, $4, $5, $6, 'sent') returning id",
                    ctx.tenant_id,
                    UUID(state["conversation_id"]),
                    _json.dumps(engine_quote["line_items"]),
                    engine_quote["subtotal_cents"],
                    engine_quote["tax_cents"],
                    engine_quote["total_cents"],
                )
            engine_quote["quote_id"] = str(quote_id)
            engine_quote["status"] = "sent"
        writer({"type": "quote", "quote": engine_quote})
        system_prompt = _with_contract(state, _build_quoting_prompt(engine_quote, violations))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]
        text = await stream_draft(ctx.provider, messages)
        return {
            "draft_response": text,
            "selections": state.get("selections", []),
            "engine_quote": engine_quote,
            **clear_violations,
            "author_node": "draft",
        }

    if route == "order_status":
        lookup = state.get("lookup") or {}
        ref_code = lookup.get("ref_code")
        if not ref_code:
            writer({"type": "refusal", "text": _ORDER_ASK_FOR_CODE})
            return {
                "draft_response": _ORDER_ASK_FOR_CODE,
                "draft_deterministic": True,
                "lookup": {"ref_code": None, "found": False},
                "author_node": "draft",
            }
        if not lookup.get("found"):
            text = _ORDER_NOT_FOUND_TEMPLATE.format(ref_code=ref_code)
            writer({"type": "refusal", "text": text})
            return {
                "draft_response": text,
                "draft_deterministic": True,
                "lookup": {"ref_code": ref_code, "found": False},
                "author_node": "draft",
            }
        text = _ORDER_FOUND_TEMPLATE.format(
            kind=lookup.get("kind", ""),
            ref_code=lookup.get("ref_code", ""),
            status=lookup.get("status", ""),
        )
        writer({"type": "token", "text": text})
        return {
            "draft_response": text,
            "draft_deterministic": True,
            "lookup": lookup,
            "author_node": "draft",
        }

    import logging as _logging

    _logging.getLogger("app.agents.draft_node").warning(
        "draft_node: unknown route %s, falling back to conversation", route
    )
    messages = [
        {
            "role": "system",
            "content": _with_contract(
                state, _SYSTEM_PROMPT_CONVERSATION + _redraft_note(violations)
            ),
        },
        {"role": "user", "content": query},
    ]
    text = await stream_draft(ctx.provider, messages)
    return {
        "draft_response": text,
        "draft_deterministic": False,
        **clear_violations,
        "author_node": "draft",
    }


def citation_source(chunk: dict[str, Any]) -> str:
    """The label a citation chip shows for a chunk. Shared with agent_node,
    whose one-call answers cite from the same chunk shape."""
    metadata = chunk.get("metadata", {})
    if metadata.get("kind") == "catalog_item":
        return "catalog"
    source = metadata.get("source")
    return str(source) if source else "knowledge base"
