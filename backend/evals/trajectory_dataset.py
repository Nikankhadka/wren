"""T-025: loader for datasets/tenant1_trajectory.jsonl - the golden
agent-task set T-026's trajectory scorer drives through the real graph.

This module owns only the dataset schema and the loader; actually driving
each case through the graph and scoring the result is T-026's job, which
imports ``load_cases``/``TrajectoryCase`` from here rather than
re-authoring the schema.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    persona: list[str] = field(default_factory=list)
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
                persona=raw.get("persona", []),
                notes=raw.get("notes", ""),
            )
        )
    return cases
