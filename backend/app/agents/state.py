"""T-012: LangGraph state schema and per-invocation context (shared contract).

``AgentState`` is the graph's data - plain, serializable, passed between
nodes. ``GraphContext`` is run-scoped dependencies (DB access info, LLM
provider, reranker) - never put live connections in state; nodes open their
own short-lived ``tenant_context`` as needed (see app/agents/draft_node.py),
matching T-011's rule of never holding a pooled connection for the duration
of an LLM stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict
from uuid import UUID

from app.observability.tracing import NOOP_TURN

if TYPE_CHECKING:
    from app.llm.embedder import Embedder
    from app.llm.provider import LLMProvider
    from app.observability.tracing import Turn
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
    # C-1: the owner's profile text as it went into the prompt. The gate's
    # allowed set is built from the material the turn actually saw, and the
    # profile is the one piece of that which is never a retrieved chunk.
    owner_material: NotRequired[str]
    # W-5: the confirmed offering catalog as it went into the turn's prompt.
    # State-borne for the same reason as owner_material above: price_gate and
    # inspection both re-enter draft on a redraft, and draft has no context
    # package of its own at that point - only what the agent node already put
    # in state on its first pass through. Recomputing it at the draft call site
    # would mean re-fetching the package there too, which is exactly the extra
    # catalog query this ticket rules out.
    offerings_text: NotRequired[str]
    # W-9: the code-owned customer contract plus the tenant's voice, exactly as
    # the agent node rendered them for this turn. State-borne for the same
    # reason as owner_material and offerings_text above: every prose route runs
    # the same contract, and the draft node reaches its routes on a redraft with
    # no context package in hand. Carrying it is what lets the two per-turn
    # tenant_config reads (draft_node, inspection) go away rather than move.
    contract: NotRequired[str]
    # T-021 reasoning-inspection gate: violations text fed back to the
    # producing specialist on redraft, whether the one allowed redraft was
    # already spent, the gate's routing decision, and a marker a specialist
    # sets on any non-LLM-authored draft (template/refusal constants) so
    # inspection can skip every check - nothing about them can fail
    # grounding/policy/injection/prompt-leak since no LLM produced them.
    inspection_violations: NotRequired[list[str]]
    inspection_attempted: NotRequired[bool]
    inspection_decision: NotRequired[str]
    draft_deterministic: NotRequired[bool]
    # T-026 trajectory observability: the supervisor's own stated reason for
    # its route pick (judged by the trajectory eval's reasoning-quality
    # grade), and order_status's structured lookup outcome (ref_code/found/
    # status/kind) - previously both existed only inside their node and were
    # unscoreable from outside.
    route_reason: NotRequired[str]
    lookup: NotRequired[dict[str, Any]]
    # T-027 input scan: the customer's message matched an injection-attempt
    # pattern. Advisory - the turn is still answered; Inspection reads this to
    # scrutinize the draft more strictly.
    injection_suspected: NotRequired[bool]
    # F-3: which graph node produced the final draft_response ("agent" fast
    # path, "draft" prose, or one of the deterministic handoffs). Persisted on
    # the assistant message's agent_node column for the Surface-2 trace
    # viewer; the inspection node carries it out on its stream event because
    # the custom-stream controller cannot read final graph state.
    author_node: NotRequired[str]


@dataclass(frozen=True)
class GraphContext:
    tenant_id: UUID
    provider: LLMProvider
    embedder: Embedder
    reranker: Reranker
    # T-028: per-tool timeout (seconds). Default keeps every existing
    # constructor (evals, tests) valid; chat.py overrides it from the tenant's
    # resolved limits. LLM-call timeouts are applied separately by wrapping the
    # provider (app/core/limits.py's TimeLimitedProvider), so no field here.
    tool_timeout_s: float = 15.0
    # T-030: the active tracing turn nodes open spans against. Defaults to the
    # stateless no-op singleton so every existing constructor (evals, tests)
    # stays valid; chat.py passes the real turn opened around the graph run.
    turn: Turn = field(default=NOOP_TURN)
