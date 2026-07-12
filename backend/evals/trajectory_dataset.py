"""T-025: loader for datasets/tenant1_trajectory.jsonl - the golden
agent-task set T-026's trajectory scorer drives through the real graph.

This module owns only the dataset schema and the eval_cases sync (T-025's
own accept criterion: "dataset committed, loadable into eval_cases") -
actually driving each case through the graph and scoring the result is
T-026's job, which imports ``load_cases``/``TrajectoryCase`` from here
rather than re-authoring the schema.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

DATASET_PATH = Path(__file__).parent / "datasets" / "tenant1_trajectory.jsonl"


@dataclass(frozen=True)
class TrajectoryCase:
    case_id: str
    category: str
    messages: list[dict[str, str]]
    expected_route: list[str]
    expected_selections: list[dict[str, Any]] = field(default_factory=list)
    forbidden_selections: list[dict[str, Any]] = field(default_factory=list)
    expected_lookup: dict[str, Any] | None = None
    expected_terminal: dict[str, bool] = field(default_factory=dict)
    forbidden: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


def load_cases(path: Path = DATASET_PATH) -> list[TrajectoryCase]:
    cases = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        if "_comment" in raw:
            continue
        cases.append(
            TrajectoryCase(
                case_id=raw["case_id"],
                category=raw["category"],
                messages=raw["messages"],
                expected_route=raw["expected_route"],
                expected_selections=raw.get("expected_selections", []),
                forbidden_selections=raw.get("forbidden_selections", []),
                expected_lookup=raw.get("expected_lookup"),
                expected_terminal=raw.get("expected_terminal", {}),
                forbidden=raw.get("forbidden", {}),
                notes=raw.get("notes", ""),
            )
        )
    return cases


async def sync_eval_cases(conn: Any, tenant_id: UUID, cases: list[TrajectoryCase]) -> None:
    """Mirrors evals/retrieval_eval.py's ``_sync_eval_cases`` pattern:
    wipe-and-reinsert this tenant's trajectory cases each run."""
    await conn.execute(
        "delete from eval_cases where tenant_id = $1 and case_type = 'trajectory'", tenant_id
    )
    for case in cases:
        await conn.execute(
            "insert into eval_cases (tenant_id, case_type, input, expected) "
            "values ($1, 'trajectory', $2, $3)",
            tenant_id,
            json.dumps({"case_id": case.case_id, "messages": case.messages}),
            json.dumps(
                {
                    "category": case.category,
                    "expected_route": case.expected_route,
                    "expected_selections": case.expected_selections,
                    "forbidden_selections": case.forbidden_selections,
                    "expected_lookup": case.expected_lookup,
                    "expected_terminal": case.expected_terminal,
                    "forbidden": case.forbidden,
                }
            ),
        )
