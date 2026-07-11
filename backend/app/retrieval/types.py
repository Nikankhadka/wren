"""Shared retrieval types (T-009)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class RetrievedChunk:
    id: UUID
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
