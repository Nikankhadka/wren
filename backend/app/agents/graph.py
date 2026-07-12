"""T-012: Supervisor -> conditional edge on route -> one specialist ->
[price_gate for money-carrying specialists] -> Inspection -> END, retry, or
Escalation. Inspection (T-021) is the last gate every draft crosses: a
failure re-enters its producing specialist for one redraft, a second
failure escalates - the same shape as price_gate's own retry/escalate
loop, one level up.

Compiled once at import time (langgraph graphs are meant to be reused
across invocations, not rebuilt per request) - state and context carry
everything request-specific.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents import (
    escalation,
    inspection,
    knowledge,
    order_status,
    price_gate,
    quoting,
    recommendation,
    supervisor,
)
from app.agents.state import AgentState, GraphContext

_SPECIALISTS = ("knowledge", "recommendation", "quoting", "order_status", "escalation")
# The two specialists whose drafts carry money route through the T-018
# price-provenance gate before inspection; the rest go straight to inspection.
_PRICE_GATED = ("recommendation", "quoting")

SupervisorNode = Callable[[AgentState], Awaitable[dict[str, Any]]]


def _price_gate_route(state: AgentState) -> str:
    decision = state.get("price_gate_decision")
    if decision == "retry":
        route = state["route"]
        assert route in _PRICE_GATED  # the gate only ever follows these nodes
        return route
    if decision == "escalate":
        return "escalation"
    return "inspection"


def _inspection_route(state: AgentState) -> str:
    decision = state.get("inspection_decision")
    if decision == "retry":
        route = state["route"]
        # order_status/escalation drafts are always draft_deterministic (or
        # already escalated) and short-circuit inspection before a retry
        # decision is ever possible - only these three ever reach a real,
        # retryable LLM-authored draft.
        assert route in ("knowledge", "recommendation", "quoting")
        return route
    if decision == "escalate":
        return "escalation"
    return "ok"


def build_graph(
    *, supervisor_node: SupervisorNode = supervisor.run
) -> CompiledStateGraph[AgentState, GraphContext, AgentState, AgentState]:
    """Build the graph. ``supervisor_node`` is swappable so tests can force a
    specific route without needing real intent-classification logic (T-013)
    - production always uses the default (the real supervisor stub/impl)."""
    graph = StateGraph(AgentState, context_schema=GraphContext)
    # supervisor_node's type (a plain Callable alias, for test swappability)
    # doesn't structurally match add_node's narrow _Node[...] protocol
    # overloads the way a directly-referenced function does.
    graph.add_node("supervisor", supervisor_node)  # type: ignore[call-overload]
    graph.add_node("knowledge", knowledge.run)
    graph.add_node("recommendation", recommendation.run)
    graph.add_node("quoting", quoting.run)
    graph.add_node("order_status", order_status.run)
    graph.add_node("escalation", escalation.run)
    graph.add_node("price_gate", price_gate.run)
    graph.add_node("inspection", inspection.run)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: state["route"],
        dict(zip(_SPECIALISTS, _SPECIALISTS, strict=True)),
    )
    for specialist in _SPECIALISTS:
        if specialist in _PRICE_GATED:
            graph.add_edge(specialist, "price_gate")
        else:
            graph.add_edge(specialist, "inspection")
    graph.add_conditional_edges(
        "price_gate",
        _price_gate_route,
        {
            "inspection": "inspection",
            "recommendation": "recommendation",
            "quoting": "quoting",
            "escalation": "escalation",
        },
    )
    graph.add_conditional_edges(
        "inspection",
        _inspection_route,
        {
            "ok": END,
            "knowledge": "knowledge",
            "recommendation": "recommendation",
            "quoting": "quoting",
            "escalation": "escalation",
        },
    )

    return graph.compile()


_compiled_graph = build_graph()


def get_graph() -> CompiledStateGraph[AgentState, GraphContext, AgentState, AgentState]:
    return _compiled_graph
