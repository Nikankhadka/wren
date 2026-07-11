"""T-012 stub - T-020 implements the Escalation Agent. Pass-through until then."""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState


async def run(state: AgentState) -> dict[str, Any]:
    return {"escalated": True}
