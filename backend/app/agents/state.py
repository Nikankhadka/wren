"""T-012: LangGraph state schema and per-invocation context (shared contract,
docs/phases/phase-2-agents-pricing.md).

``AgentState`` is the graph's data - plain, serializable, passed between
nodes. ``GraphContext`` is run-scoped dependencies (DB access info, LLM
provider, reranker) - never put live connections in state; nodes open their
own short-lived ``tenant_context`` as needed (see app/agents/knowledge.py),
matching T-011's rule of never holding a pooled connection for the duration
of an LLM stream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypedDict
from uuid import UUID

if TYPE_CHECKING:
    from app.llm.provider import LLMProvider
    from app.retrieval.rerank import Reranker


class AgentState(TypedDict):
    conversation_id: str
    tenant_id: str
    messages: list[dict[str, str]]
    route: str | None
    route_confidence: float | None
    retrieved_chunks: list[dict[str, Any]]
    selections: list[dict[str, Any]]
    engine_quote: dict[str, Any] | None
    draft_response: str
    inspection: dict[str, Any] | None
    escalated: bool


@dataclass(frozen=True)
class GraphContext:
    tenant_id: UUID
    provider: LLMProvider
    reranker: Reranker
