"""T-017: the Quoting Agent.

The hard rule lives here in agent form: the model's output schema
(``QuoteSelectionResult``) contains no money field of any kind - it selects
``rule_code``/``catalog_item_id`` + quantity from candidates whose prompt
block deliberately omits prices, and the deterministic engine (T-016)
computes every cent. On a bad selection the engine's typed error goes back
to the model exactly once for a re-select; a second failure escalates
instead of guessing. The quotes row is persisted verbatim from engine
output - this is the only code path that writes quotes (database.md
section 5) - and the customer-facing figures render from that row in the
frontend's QuoteCard, never from generated text.

Budget questions ("under $120?") are answered by handing the model the
engine total formatted server-side and asking for a verdict - the model
compares, it never computes or authors a figure.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from langgraph.config import get_stream_writer
from langgraph.runtime import get_runtime
from pydantic import BaseModel, Field

from app.agents.spotlight import new_spotlight
from app.agents.state import AgentState, GraphContext
from app.core import db
from app.llm.provider import ChatMessage
from app.pricing.engine import EngineQuote, Selection, SelectionError, compute_quote
from app.retrieval.service import retrieve

NO_CANDIDATES_MESSAGE = (
    "I can't put together a quote for that - the business hasn't listed "
    "anything I could price it from. Please contact them directly."
)
CLARIFY_MESSAGE = (
    "I couldn't match that to anything the business offers. Could you "
    "describe what you need a price for in a bit more detail?"
)
ESCALATION_MESSAGE = (
    "I wasn't able to put together an accurate quote for that, so I'm "
    "handing this to a human who can. They'll pick it up from here."
)

_SELECTION_PROMPT = (
    "You prepare price quotes for a business. From the candidate services "
    "and items below, select what matches the customer's request: emit each "
    "choice's exact code or item id plus a quantity (a count of things, "
    "never an amount of money). Prices are computed elsewhere - you never "
    "see or produce them. Set has_budget_constraint to true only if the "
    "customer stated a budget or price cap. If nothing matches, return no "
    "selections.\n\nCandidates:\n{candidates}"
)
_BUDGET_PROMPT = (
    "The customer stated a budget constraint. You are given the final "
    "computed quote total (already calculated - do not do any arithmetic) "
    "and the customer's message. Decide whether the total satisfies the "
    "customer's stated constraint."
)
_EXPLANATION_PROMPT = (
    "You are presenting a price quote to a customer. A quote card showing "
    "the exact line items, quantities, and totals is displayed alongside "
    "your message. Briefly explain what the quote covers, referring to the "
    "card for figures. Do NOT state any prices, totals, or other monetary "
    "amounts yourself - the card is the single source of numbers.\n\n"
    "The quote covers:\n{coverage}{budget_line}"
)


class SelectionChoice(BaseModel):
    """One agent selection - a code or an id plus a count. No money, ever."""

    rule_code: str | None = None
    catalog_item_id: str | None = None
    quantity: int = Field(ge=1, le=999)


class QuoteSelectionResult(BaseModel):
    selections: list[SelectionChoice] = Field(default_factory=list)
    has_budget_constraint: bool = False
    explanation: str = ""


class BudgetVerdict(BaseModel):
    within_budget: bool


def _conversation_tail(state: AgentState) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in state["messages"][-6:])


def _to_engine_selections(choices: list[SelectionChoice]) -> list[Selection]:
    selections: list[Selection] = []
    for choice in choices:
        if choice.rule_code:
            selections.append(Selection("rule", choice.rule_code, choice.quantity))
        elif choice.catalog_item_id:
            selections.append(Selection("item", choice.catalog_item_id, choice.quantity))
        else:
            raise SelectionError("a selection must name a rule_code or a catalog_item_id")
    return selections


def _format_cents(cents: int) -> str:
    """Server-side money formatting for model-facing prompts (the budget
    verdict) - plain Python arithmetic on engine output, never the model."""
    return f"${cents / 100:,.2f}"


def _quote_payload(quote_id: UUID, quote: EngineQuote) -> dict[str, Any]:
    return {
        "quote_id": str(quote_id),
        "line_items": [item.to_dict() for item in quote.line_items],
        "subtotal_cents": quote.subtotal_cents,
        "tax_cents": quote.tax_cents,
        "total_cents": quote.total_cents,
        "status": "sent",
    }


def _redraft_note(violations: list[str]) -> str:
    return (
        "\n\nYour previous draft was rejected: "
        + "; ".join(violations)
        + ". Redraft now, addressing this - state no monetary amounts yourself either way."
    )


async def run(state: AgentState) -> dict[str, Any]:
    runtime = get_runtime(GraphContext)
    ctx = runtime.context
    writer = get_stream_writer()
    query = state["messages"][-1]["content"]

    # T-018/T-021 redraft path: a gate (price_gate or inspection) bounced
    # the previous draft. The quote itself is engine-computed and already
    # persisted - only the prose gets regenerated, with the violations
    # spelled out.
    violations = state.get("price_violations") or state.get("inspection_violations")
    engine_quote = state["engine_quote"]
    if violations and engine_quote is not None:
        coverage = "\n".join(
            f"- {item['label']} x{item['quantity']}" for item in engine_quote["line_items"]
        )
        redraft_messages: list[ChatMessage] = [
            {
                "role": "system",
                "content": _EXPLANATION_PROMPT.format(coverage=coverage, budget_line="")
                + _redraft_note(violations),
            },
            {"role": "user", "content": query},
        ]
        redraft_text = ""
        async for delta in ctx.provider.chat_stream(redraft_messages):
            redraft_text += delta
            writer({"type": "token", "text": delta})
        # Clear both gates' violation keys - whichever gate re-checks this
        # redraft (price_gate, then possibly inspection) must only ever see
        # the violations IT found, never a stale set from the other gate's
        # earlier pass.
        return {
            "draft_response": redraft_text,
            "price_violations": [],
            "inspection_violations": [],
        }

    async with db.tenant_context(ctx.tenant_id, "customer") as conn:
        rules = await conn.fetch(
            "select code, label, unit from pricing_rules where tenant_id = $1 and active",
            ctx.tenant_id,
        )
        with ctx.turn.span("retrieval") as span:
            chunks = await retrieve(
                conn,
                tenant_id=ctx.tenant_id,
                query=query,
                embedder=ctx.embedder,
                reranker=ctx.reranker,
                top_k=5,
                metadata_kind="catalog_item",
            )
            span.set(chunks=len(chunks))
        item_ids = [
            UUID(chunk.metadata["catalog_item_id"])
            for chunk in chunks
            if chunk.metadata.get("catalog_item_id")
        ]
        items = (
            await conn.fetch(
                "select id, name, description from catalog_items "
                "where tenant_id = $1 and id = any($2::uuid[]) and active "
                "and price_cents is not null",
                ctx.tenant_id,
                item_ids,
            )
            if item_ids
            else []
        )

    if not rules and not items:
        writer({"type": "refusal", "text": NO_CANDIDATES_MESSAGE})
        return {
            "draft_response": NO_CANDIDATES_MESSAGE,
            "selections": [],
            "draft_deterministic": True,
        }

    # Candidate block deliberately carries no prices - the model picks WHAT,
    # the engine alone knows HOW MUCH. Rule labels and item names/descriptions
    # are tenant-authored data, so spotlight-wrap them (T-027) - codes and ids
    # are system-generated identifiers and stay outside the wrap so the model
    # can echo them back cleanly as its selection.
    spotlight = new_spotlight()
    candidate_lines = [
        f"rule code={rule['code']!r}: {spotlight.wrap(rule['label'])} (per {rule['unit']})"
        for rule in rules
    ]
    for item in items:
        item_text = spotlight.wrap(f"{item['name']} - {item['description'] or ''}")
        candidate_lines.append(f"item id={item['id']}: {item_text}")
    selection_prompt = (
        _SELECTION_PROMPT.format(candidates="\n".join(candidate_lines))
        + "\n"
        + spotlight.instruction()
    )
    tail = _conversation_tail(state)

    result = await ctx.provider.extract(
        system_prompt=selection_prompt, user_input=tail, schema=QuoteSelectionResult
    )
    if not result.selections:
        writer({"type": "refusal", "text": CLARIFY_MESSAGE})
        return {"draft_response": CLARIFY_MESSAGE, "selections": [], "draft_deterministic": True}

    quote: EngineQuote | None = None
    async with db.tenant_context(ctx.tenant_id, "customer") as conn:
        try:
            with ctx.turn.span("pricing_engine") as span:
                quote = await compute_quote(
                    conn, ctx.tenant_id, _to_engine_selections(result.selections)
                )
                span.set(total_cents=quote.total_cents)
        except SelectionError as error:
            # One re-select with the typed error in context; the engine never
            # substitutes, so a still-bad second attempt escalates.
            result = await ctx.provider.extract(
                system_prompt=selection_prompt,
                user_input=(
                    f"{tail}\n\nYour previous selection failed: {error}. "
                    "Select again from the candidates."
                ),
                schema=QuoteSelectionResult,
            )
            try:
                if not result.selections:
                    raise SelectionError("no selections on re-attempt")
                with ctx.turn.span("pricing_engine") as span:
                    quote = await compute_quote(
                        conn, ctx.tenant_id, _to_engine_selections(result.selections)
                    )
                    span.set(total_cents=quote.total_cents)
            except SelectionError:
                writer({"type": "refusal", "text": ESCALATION_MESSAGE})
                return {
                    "draft_response": ESCALATION_MESSAGE,
                    "selections": [],
                    "escalated": True,
                }

        quote_id: UUID = await conn.fetchval(
            "insert into quotes (tenant_id, conversation_id, line_items, "
            "subtotal_cents, tax_cents, total_cents, status) "
            "values ($1, $2, $3, $4, $5, $6, 'sent') returning id",
            ctx.tenant_id,
            UUID(state["conversation_id"]),
            json.dumps([item.to_dict() for item in quote.line_items]),
            quote.subtotal_cents,
            quote.tax_cents,
            quote.total_cents,
        )

    payload = _quote_payload(quote_id, quote)
    writer({"type": "quote", "quote": payload})

    budget_line = ""
    if result.has_budget_constraint:
        verdict = await ctx.provider.extract(
            system_prompt=_BUDGET_PROMPT,
            user_input=(
                f"customer message: {query}\n"
                f"computed quote total: {_format_cents(quote.total_cents)}"
            ),
            schema=BudgetVerdict,
        )
        budget_line = (
            "\nBudget: the total fits within the customer's stated budget."
            if verdict.within_budget
            else "\nBudget: the total exceeds the customer's stated budget - "
            "acknowledge this honestly."
        )

    coverage = "\n".join(f"- {item.label} x{item.quantity}" for item in quote.line_items)
    messages: list[ChatMessage] = [
        {
            "role": "system",
            "content": _EXPLANATION_PROMPT.format(coverage=coverage, budget_line=budget_line),
        },
        {"role": "user", "content": query},
    ]
    full_text = ""
    async for delta in ctx.provider.chat_stream(messages):
        full_text += delta
        writer({"type": "token", "text": delta})

    return {
        "draft_response": full_text,
        "selections": [choice.model_dump() for choice in result.selections],
        "engine_quote": payload,
    }
