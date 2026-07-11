"""T-013: real intent routing, replacing T-012's always-knowledge stub.

One structured extraction call turns the conversation tail into a route +
confidence + reason. Below the tenant's configured escalation threshold, the
route is forced to 'escalation' regardless of what the model guessed - low
confidence never gets to guess, per the ticket's own wording. The routing
prompt describes intents by capability ("wants a price for something",
"asking about a policy"), never by vertical - a vertical-named intent would
violate the domain-agnostic hard rule (Wren_AGENTS.md section 9).
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.runtime import get_runtime
from pydantic import BaseModel

from app.agents.state import AgentState, GraphContext
from app.core import db

_SYSTEM_PROMPT = (
    "You are the routing supervisor for a customer support assistant. Given the "
    "customer's message, decide which specialist should handle it:\n"
    "- knowledge: answering a question using general information, policies, or FAQs\n"
    "- recommendation: helping the customer choose between products or services\n"
    "- quoting: the customer wants a price or quote for something specific\n"
    "- order_status: checking on an existing order, repair, or ticket\n"
    "- escalation: anything requiring a human, or too ambiguous/unclear to route "
    "confidently\n"
    "Give your confidence (0 to 1) honestly - if the message is unclear, gibberish, "
    "or doesn't fit any capability well, use a low confidence rather than guessing."
)


class RouteDecision(BaseModel):
    route: Literal["knowledge", "recommendation", "quoting", "order_status", "escalation"]
    confidence: float
    reason: str


def _conversation_tail(messages: list[dict[str, str]]) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages)


async def run(state: AgentState) -> dict[str, Any]:
    runtime = get_runtime(GraphContext)
    ctx = runtime.context

    async with db.tenant_context(ctx.tenant_id, "customer") as conn:
        threshold: float = await conn.fetchval(
            "select escalation_threshold from tenant_config where tenant_id = $1", ctx.tenant_id
        )

    decision = await ctx.provider.extract(
        system_prompt=_SYSTEM_PROMPT,
        user_input=_conversation_tail(state["messages"]),
        schema=RouteDecision,
    )

    route = decision.route if decision.confidence >= threshold else "escalation"
    return {"route": route, "route_confidence": decision.confidence}
