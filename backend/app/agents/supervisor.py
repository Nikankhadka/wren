"""T-012 stub - T-013 implements real intent routing.

Always routes to 'knowledge' for now, so swapping /api/chat to invoke the
graph reproduces T-011's straight RAG behavior exactly (nothing regresses).
"""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState


async def run(state: AgentState) -> dict[str, Any]:
    return {"route": "knowledge", "route_confidence": 1.0}
