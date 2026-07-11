"""T-012 stub - T-015 implements the Recommendation Agent. Pass-through:
the supervisor never routes here yet (T-013), so this exists only so the
graph topology is complete and the conditional edge map has somewhere to
point once real routing lands."""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState


async def run(state: AgentState) -> dict[str, Any]:
    return {}
