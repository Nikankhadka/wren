"""T-018: the price-provenance gate as a graph node.

Runs after Quoting and Recommendation (the two nodes whose drafts carry
money). Deterministic - delegates to app/pricing/validation_gate.py, no LLM
call. A violating draft gets exactly one redraft (violations listed back to
the producing node via ``price_violations``); a second violation escalates
with reason ``price_provenance``. Emits a ``redraft`` stream event so the
customer surface clears the violating text it already saw - full buffering
until inspection passes is T-021's job and is a recorded latency tradeoff,
not something this node half-implements.
"""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer

from app.agents.state import AgentState
from app.pricing.validation_gate import validate

GATE_ESCALATION_MESSAGE = (
    "I couldn't put together a reliable answer on pricing, so I'm handing "
    "this to a human who can. They'll pick it up from here."
)


async def run(state: AgentState) -> dict[str, Any]:
    provenance = [
        selection["price_cents"]
        for selection in state["selections"]
        if isinstance(selection.get("price_cents"), int)
    ]
    violations = validate(state["draft_response"], state["engine_quote"], provenance)

    if not violations:
        return {"price_gate_decision": "ok"}

    writer = get_stream_writer()
    if not state.get("price_gate_attempted"):
        writer({"type": "redraft"})
        return {
            "price_gate_decision": "retry",
            "price_violations": violations,
            "price_gate_attempted": True,
        }

    writer({"type": "refusal", "text": GATE_ESCALATION_MESSAGE})
    return {
        "price_gate_decision": "escalate",
        "escalated": True,
        "escalation_reason": "price_provenance",
        "draft_response": GATE_ESCALATION_MESSAGE,
    }
