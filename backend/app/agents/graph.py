"""T-012: Supervisor -> conditional edge on route -> one specialist ->
Inspection -> END. All specialist/inspection nodes are stubs except
knowledge (T-011's straight RAG, moved here) - the supervisor always routes
there for now (T-013 implements real routing), so the graph reproduces
T-011's behavior exactly.

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
    quoting,
    recommendation,
    supervisor,
)
from app.agents.state import AgentState, GraphContext

_SPECIALISTS = ("knowledge", "recommendation", "quoting", "order_status", "escalation")

SupervisorNode = Callable[[AgentState], Awaitable[dict[str, Any]]]


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
    graph.add_node("inspection", inspection.run)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: state["route"],
        dict(zip(_SPECIALISTS, _SPECIALISTS, strict=True)),
    )
    for specialist in _SPECIALISTS:
        graph.add_edge(specialist, "inspection")
    graph.add_edge("inspection", END)

    return graph.compile()


_compiled_graph = build_graph()


def get_graph() -> CompiledStateGraph[AgentState, GraphContext, AgentState, AgentState]:
    return _compiled_graph
