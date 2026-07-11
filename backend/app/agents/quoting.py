"""T-012 stub - T-017 implements the Quoting Agent. Pass-through until then.

Reminder for whoever implements T-017: this node's output schema must never
contain a money field (root AGENTS.md hard rule 1, restated in this phase's
shared contracts) - it selects rule_code/catalog_item_id + quantity, the
pricing engine (T-016) computes every amount.
"""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState


async def run(state: AgentState) -> dict[str, Any]:
    return {}
