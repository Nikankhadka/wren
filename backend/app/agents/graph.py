"""T-044/P-3/C-2: tool-driven agent -> draft -> price_gate -> inspection ->
END/retry/escalation.

P-3 adds one edge: when the agent node already produced the answer from its
context package (the one-call turn), the draft node is skipped and the draft
goes straight to the gates. Everything downstream of the draft - the price gate,
inspection, the redraft-once-then-escalate rule - is unchanged, and a redraft
still runs through the draft node, which knows how to rebuild any route's prompt
from the state the agent left behind.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents import (
    escalation,
    inspection,
    price_gate,
)
from app.agents.agent_node import run as agent_node_run
from app.agents.draft_node import run as draft_node_run
from app.agents.state import AgentState, GraphContext
from app.agents.tracing import traced


def _price_gate_route(state: AgentState) -> str:
    decision = state.get("price_gate_decision")
    if decision == "retry":
        route = state["route"]
        # Only a real (non-deterministic) draft can violate, and those are
        # exactly the retryable routes - same rule inspection asserts.
        assert route in inspection.RETRYABLE_ROUTES
        return "draft"
    if decision == "escalate":
        return "escalation"
    return "inspection"


def _agent_route(state: AgentState) -> str:
    """Straight to the gates when the agent already wrote the draft (P-3)."""
    if state.get("response"):
        return "structured"
    if state.get("escalated") or not state.get("draft_response"):
        return "draft"
    return "price_gate"


def _inspection_route(state: AgentState) -> str:
    decision = state.get("inspection_decision")
    if decision == "retry":
        route = state["route"]
        assert route in inspection.RETRYABLE_ROUTES
        return "draft"
    if decision == "escalate":
        return "escalation"
    return "ok"


def build_graph() -> CompiledStateGraph[AgentState, GraphContext, AgentState, AgentState]:
    graph = StateGraph(AgentState, context_schema=GraphContext)

    graph.add_node("agent", traced("agent", agent_node_run))
    graph.add_node("draft", traced("draft", draft_node_run))
    graph.add_node("price_gate", traced("price_gate", price_gate.run))
    graph.add_node("inspection", traced("inspection", inspection.run))
    graph.add_node("escalation", traced("escalation", escalation.run))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        _agent_route,
        {"draft": "draft", "price_gate": "price_gate", "structured": "inspection"},
    )
    # C-2: every draft passes the money gate, not only the two money routes.
    # A knowledge answer is where figures now come from, so leaving that route
    # unchecked was the hole, not a scope cut.
    graph.add_edge("draft", "price_gate")
    graph.add_conditional_edges(
        "price_gate",
        _price_gate_route,
        {"draft": "draft", "inspection": "inspection", "escalation": "escalation"},
    )
    graph.add_conditional_edges(
        "inspection",
        _inspection_route,
        {"ok": END, "draft": "draft", "escalation": "escalation"},
    )

    graph.add_edge("escalation", "inspection")

    return graph.compile()


_compiled_graph = build_graph()


def get_graph() -> CompiledStateGraph[AgentState, GraphContext, AgentState, AgentState]:
    return _compiled_graph
