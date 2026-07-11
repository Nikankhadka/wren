"""T-012 stub - T-018/T-021 implement real price-provenance and
reasoning-inspection checks. Pass-through (always passes) until then."""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState


async def run(state: AgentState) -> dict[str, Any]:
    return {"inspection": {"verdict": "pass", "reasons": []}}
