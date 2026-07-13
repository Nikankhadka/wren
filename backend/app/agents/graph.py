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
from langgraph.runtime import get_runtime

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

# T-030: scalar-only whitelist for span attributes - never a raw draft/message/
# chunk-content field, which could carry cross-tenant-sensitive text into a
# tracing backend outside the app's own tenant-scoping (T-022's concern, one
# level removed). Keys not present in a node's return are simply skipped.
_SPAN_ATTR_KEYS = (
    "route",
    "route_confidence",
    "route_reason",
    "price_gate_decision",
    "inspection_decision",
    "escalated",
    "escalation_reason",
    "draft_deterministic",
)


def _span_attrs(result: dict[str, Any]) -> dict[str, Any]:
    attrs = {key: result[key] for key in _SPAN_ATTR_KEYS if key in result}
    if "retrieved_chunks" in result:
        attrs["chunks"] = len(result["retrieved_chunks"])
    if "selections" in result:
        attrs["selections"] = len(result["selections"])
    if "inspection" in result and result["inspection"]:
        for check, verdict in result["inspection"].items():
            attrs[f"inspection_{check}"] = verdict.get("passed")
    return attrs


def _traced(name: str, node: Callable[[AgentState], Awaitable[dict[str, Any]]]) -> Any:
    """Wraps a node in a tracing span instead of editing every node body -
    mechanical, applies uniformly to all 8 nodes (including a test's forced
    supervisor_node), and costs nothing when the tracer is the T-030 no-op
    default. get_runtime() works here since the wrapper IS the node LangGraph
    executes (T-013's get_runtime()-only-inside-a-node constraint still holds).

    Declared ``Any`` rather than the callable's real type because langgraph's
    ``add_node`` protocol overloads (``_Node[NodeInputT]`` with a StateLike
    bound) reject TypedDict-typed callables under mypy 2.2, and the emitted
    error code flip-flops between ``call-overload`` and ``arg-type`` across
    incremental-cache states - so no per-line ``type: ignore[code]`` is stable
    (CI runs cold and local runs warm; each sees a different code). Erasing the
    type at this one boundary is deterministic; the parameter side stays fully
    typed."""

    async def wrapped(state: AgentState) -> dict[str, Any]:
        turn = get_runtime(GraphContext).context.turn
        with turn.span(name) as span:
            result = await node(state)
            span.set(**_span_attrs(result))
            return result

    return wrapped


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
    # No type: ignore needed on these registrations - see _traced's docstring
    # for why its return type is erased at the add_node boundary.
    graph.add_node("supervisor", _traced("supervisor", supervisor_node))
    graph.add_node("knowledge", _traced("knowledge", knowledge.run))
    graph.add_node("recommendation", _traced("recommendation", recommendation.run))
    graph.add_node("quoting", _traced("quoting", quoting.run))
    graph.add_node("order_status", _traced("order_status", order_status.run))
    graph.add_node("escalation", _traced("escalation", escalation.run))
    graph.add_node("price_gate", _traced("price_gate", price_gate.run))
    graph.add_node("inspection", _traced("inspection", inspection.run))

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
