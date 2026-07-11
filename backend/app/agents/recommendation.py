"""T-015: the Recommendation Agent.

Extracts generic needs/constraints from the conversation (never vertical-
specific keys - domain-agnostic hard rule), retrieves scoped to
``metadata.kind='catalog_item'`` chunks only, then re-fetches each
recommended item's authoritative row from ``catalog_items`` so the
displayed price always comes from the DB column, never from the model or
from the chunk's embedded text - that value is what lands in ``selections``
for Inspection, and is what any future rendering must use verbatim.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.config import get_stream_writer
from langgraph.runtime import get_runtime
from pydantic import BaseModel, Field

from app.agents.state import AgentState, GraphContext
from app.core import db
from app.llm.provider import ChatMessage
from app.retrieval.service import retrieve

REFUSAL_MESSAGE = (
    "I don't have anything that matches what you're looking for. "
    "Please contact the business directly for help."
)

_EXTRACTION_PROMPT = (
    "Extract what the customer is looking for from their message. Use generic "
    "keys only - 'needs' (what they want) and 'constraints' (budget, size, or "
    "any other limitation they mentioned). Never assume a specific business "
    "type; describe only what they actually said."
)


class PreferenceExtraction(BaseModel):
    needs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


def _search_query(original_message: str, preferences: PreferenceExtraction) -> str:
    parts = [original_message, *preferences.needs, *preferences.constraints]
    return " ".join(part for part in parts if part)


async def run(state: AgentState) -> dict[str, Any]:
    runtime = get_runtime(GraphContext)
    ctx = runtime.context
    writer = get_stream_writer()
    query = state["messages"][-1]["content"]

    preferences = await ctx.provider.extract(
        system_prompt=_EXTRACTION_PROMPT, user_input=query, schema=PreferenceExtraction
    )
    search_query = _search_query(query, preferences)

    async with db.tenant_context(ctx.tenant_id, "customer") as conn:
        results = await retrieve(
            conn,
            tenant_id=ctx.tenant_id,
            query=search_query,
            embedder=ctx.embedder,
            reranker=ctx.reranker,
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
                "select id, name, description, price_cents from catalog_items "
                "where tenant_id = $1 and id = any($2::uuid[]) and active",
                ctx.tenant_id,
                item_ids,
            )
            if item_ids
            else []
        )

    if not rows:
        writer({"type": "refusal", "text": REFUSAL_MESSAGE})
        return {"draft_response": REFUSAL_MESSAGE, "selections": []}

    selections = [
        {
            "catalog_item_id": str(row["id"]),
            "name": row["name"],
            "description": row["description"],
            "price_cents": row["price_cents"],
        }
        for row in rows
    ]

    items_block = "\n".join(
        f"[{i + 1}] {row['name']}: {row['description']}"
        + (f" (${row['price_cents'] / 100:.2f})" if row["price_cents"] is not None else "")
        for i, row in enumerate(rows)
    )
    system_prompt = (
        "You are a sales assistant recommending items to a customer. Recommend "
        "ONLY from the numbered list below, with a short reason for each - never "
        "invent an item or a price that isn't listed.\n\n"
        f"Available items:\n{items_block}"
    )
    messages: list[ChatMessage] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    full_text = ""
    async for delta in ctx.provider.chat_stream(messages):
        full_text += delta
        writer({"type": "token", "text": delta})

    return {"draft_response": full_text, "selections": selections}
