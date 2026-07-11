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
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict
from uuid import UUID

if TYPE_CHECKING:
    from app.llm.embedder import Embedder
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
    # T-018 price-provenance gate bookkeeping (NotRequired so the shared
    # contract's constructors stay valid): violations found in the last
    # draft, whether the one allowed redraft was already spent, the gate's
    # routing decision, and the reason attached when escalating.
    price_violations: NotRequired[list[str]]
    price_gate_attempted: NotRequired[bool]
    price_gate_decision: NotRequired[str]
    escalation_reason: NotRequired[str]


@dataclass(frozen=True)
class GraphContext:
    tenant_id: UUID
    provider: LLMProvider
    embedder: Embedder
    reranker: Reranker
