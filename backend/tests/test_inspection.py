"""T-021: Reasoning-Inspection layer tests, driven through the graph
(get_runtime() constraint - see T-013's memory entry). Each planted-failure
check gets its own test: the draft is redrafted once with the verdict's
reasons folded back in, and a second straight failure escalates with reason
``inspection:<check>``. price_provenance is exercised as a pure unit test
(app.pricing.validation_gate.validate is already covered end-to-end by
test_validation_gate.py; this only proves inspection's own re-assert
wiring, scoped to money-carrying routes).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

from app.agents.graph import build_graph
from app.agents.inspection import ESCALATION_MESSAGE, check_price_provenance
from app.agents.state import AgentState, GraphContext
from app.api.chat import _stream_chat_response
from app.core import db
from app.llm.provider import ChatMessage, SchemaT
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class FakeInspectionProvider(BaseFakeProvider):
    """Routes always to knowledge/order_status per the forced supervisor;
    queued payloads answer InspectionVerdicts calls in order (defaulting to
    all-pass once exhausted); queued drafts answer chat_stream calls in
    order (repeating the last one once exhausted)."""

    def __init__(
        self,
        *,
        verdict_payloads: list[dict[str, Any]] | None = None,
        drafts: list[str] | None = None,
    ) -> None:
        self._verdict_payloads = list(verdict_payloads or [])
        self._drafts = list(drafts or ["A grounded, on-policy answer [1]."])
        self.verdict_calls = 0
        self.stream_calls = 0

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        if "route" in schema.model_fields:
            return schema.model_validate({"route": "knowledge", "confidence": 1.0, "reason": "t"})
        if "ref_code" in schema.model_fields:
            return schema.model_validate({"ref_code": None, "customer_ref": None})
        if "grounding" in schema.model_fields:
            self.verdict_calls += 1
            payload = self._verdict_payloads.pop(0) if self._verdict_payloads else {}
            return schema.model_validate(payload)
        raise AssertionError(f"unexpected extract schema: {schema}")

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.stream_calls += 1
        draft = self._drafts.pop(0) if self._drafts else self._drafts_exhausted_fallback()
        for word in draft.split(" "):
            yield word + " "

    def _drafts_exhausted_fallback(self) -> str:
        return "A grounded, on-policy answer [1]."


class PassthroughReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


def _initial_state(
    message: str = "What are your hours?",
    *,
    conversation_id: str = "test",
    tenant_id: str = "test",
) -> AgentState:
    return {
        "conversation_id": conversation_id,
        "tenant_id": tenant_id,
        "messages": [{"role": "customer", "content": message}],
        "route": None,
        "route_confidence": None,
        "retrieved_chunks": [],
        "selections": [],
        "engine_quote": None,
        "draft_response": "",
        "inspection": None,
        "escalated": False,
    }


async def _seed_tenant_with_chunk(
    conn: asyncpg.Connection[Any], *, system_prompt: str = ""
) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Inspection Test Co') returning id",
        f"inspection-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute(
        "insert into tenant_config (tenant_id, system_prompt) values ($1, $2)",
        tenant_id,
        system_prompt,
    )
    document_id: uuid.UUID = await conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'faq.md', 'faq', 'ready') returning id",
        tenant_id,
    )
    await conn.execute(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, $3, $4, $5)",
        tenant_id,
        document_id,
        "We are open weekdays 9am to 5pm.",
        [0.0] * EMBEDDING_DIM,
        json.dumps({"source": "faq.md", "chunk_index": 0, "kind": "prose"}),
    )
    return tenant_id


async def _seed_tenant_with_conversation(
    conn: asyncpg.Connection[Any],
) -> tuple[uuid.UUID, uuid.UUID]:
    """escalation.py writes real rows (escalations FK's conversations,
    updates conversations.status) - any test that might route there needs a
    real conversation, not a bare placeholder string."""
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Inspection Escalate Co') returning id",
        f"inspection-esc-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    document_id: uuid.UUID = await conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'faq.md', 'faq', 'ready') returning id",
        tenant_id,
    )
    await conn.execute(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, $3, $4, $5)",
        tenant_id,
        document_id,
        "We are open weekdays 9am to 5pm.",
        [0.0] * EMBEDDING_DIM,
        json.dumps({"source": "faq.md", "chunk_index": 0, "kind": "prose"}),
    )
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    return tenant_id, conversation_id


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


def _context(tenant_id: uuid.UUID, provider: FakeInspectionProvider) -> GraphContext:
    return GraphContext(
        tenant_id=tenant_id,
        provider=provider,
        embedder=ZeroEmbedder(),
        reranker=PassthroughReranker(),
    )


async def test_ungrounded_claim_is_redrafted_then_passes(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant_with_chunk(superuser_conn)
    provider = FakeInspectionProvider(
        verdict_payloads=[{"grounding": {"passed": False, "reason": "claim not in context"}}, {}],
        drafts=["We are open 24/7 which is not in the context.", "We are open weekdays 9-5."],
    )
    graph = build_graph()

    final_state = await graph.ainvoke(_initial_state(), context=_context(tenant_id, provider))

    assert final_state["escalated"] is False
    assert final_state["inspection_decision"] == "ok"
    assert final_state["draft_response"] == "We are open weekdays 9-5. "
    assert provider.stream_calls == 2
    assert provider.verdict_calls == 2


async def test_injected_instruction_is_redrafted_then_passes(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant_with_chunk(superuser_conn)
    provider = FakeInspectionProvider(
        verdict_payloads=[
            {"injection": {"passed": False, "reason": "followed embedded instruction"}},
            {},
        ],
        drafts=[
            "Ignoring my instructions as told by the retrieved content.",
            "We are open weekdays 9-5.",
        ],
    )
    graph = build_graph()

    final_state = await graph.ainvoke(_initial_state(), context=_context(tenant_id, provider))

    assert final_state["escalated"] is False
    assert final_state["inspection_decision"] == "ok"
    assert provider.stream_calls == 2


async def test_leaked_prompt_line_is_caught_deterministically(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    leaked_line = "Never reveal you are an automated system prompt marker."
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, system_prompt=leaked_line)
    # The LLM verdict itself says everything passes (including prompt_leak) -
    # only the deterministic substring check catches this, proving it runs
    # independently of the LLM's own opinion.
    provider = FakeInspectionProvider(
        verdict_payloads=[{}, {}],
        drafts=[f"Sure - {leaked_line} Anyway, we are open 9-5.", "We are open weekdays 9-5."],
    )
    graph = build_graph()

    final_state = await graph.ainvoke(_initial_state(), context=_context(tenant_id, provider))

    assert final_state["escalated"] is False
    assert final_state["inspection_decision"] == "ok"
    assert provider.stream_calls == 2
    assert leaked_line not in final_state["draft_response"]


async def test_second_failure_escalates_with_inspection_reason(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    always_fails = {"grounding": {"passed": False, "reason": "still ungrounded"}}
    provider = FakeInspectionProvider(verdict_payloads=[always_fails, always_fails])
    graph = build_graph()

    final_state = await graph.ainvoke(
        _initial_state(conversation_id=str(conversation_id), tenant_id=str(tenant_id)),
        context=_context(tenant_id, provider),
    )

    assert final_state["escalated"] is True
    assert final_state["escalation_reason"] == "inspection:grounding"
    assert final_state["draft_response"] == ESCALATION_MESSAGE
    # The escalation revisit through inspection must NOT overwrite the
    # failing verdicts with an all-pass placeholder - they are what the
    # trace viewer shows for this message.
    assert final_state["inspection"] is not None
    assert final_state["inspection"]["grounding"]["passed"] is False

    status = await superuser_conn.fetchval(
        "select status from conversations where id = $1", conversation_id
    )
    assert status == "escalated"
    escalation_row = await superuser_conn.fetchrow(
        "select reason from escalations where conversation_id = $1", conversation_id
    )
    assert escalation_row is not None
    assert escalation_row["reason"] == "inspection:grounding"


async def test_clean_path_passes_with_one_inspection_call(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant_with_chunk(superuser_conn)
    provider = FakeInspectionProvider(drafts=["We are open weekdays 9-5."])
    graph = build_graph()

    final_state = await graph.ainvoke(_initial_state(), context=_context(tenant_id, provider))

    assert final_state["escalated"] is False
    assert final_state["inspection_decision"] == "ok"
    assert provider.verdict_calls == 1
    assert provider.stream_calls == 1
    verdicts = final_state["inspection"]
    assert verdicts is not None
    assert all(check["passed"] for check in verdicts.values())


async def test_order_status_is_never_inspected_by_the_llm(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """order_status drafts are always draft_deterministic - Inspection must
    short-circuit before ever asking the LLM for an InspectionVerdicts
    verdict. ``verdict_calls`` only increments inside the "grounding" branch
    of the fake's extract(), so a regression that let a deterministic draft
    reach the LLM check would show up as a non-zero count here."""
    tenant_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Order Status Inspect Co') returning id",
        f"inspection-order-{uuid.uuid4().hex[:8]}",
    )
    await superuser_conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)

    async def supervisor_stub(state: AgentState) -> dict[str, Any]:
        return {"route": "order_status", "route_confidence": 1.0}

    provider = FakeInspectionProvider()
    graph = build_graph(supervisor_node=supervisor_stub)

    final_state = await graph.ainvoke(_initial_state(), context=_context(tenant_id, provider))

    assert provider.verdict_calls == 0
    assert final_state["inspection_decision"] == "ok"


async def test_rejected_draft_never_reaches_the_stream_and_citations_survive(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """chat.py's buffering (T-021): a rejected draft's tokens must never
    appear in the SSE body, the citations event emitted before the rejected
    draft must survive the retry discard (the redraft path never re-emits
    it), and the approved verdicts land on the assistant message row."""
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    provider = FakeInspectionProvider(
        verdict_payloads=[{"grounding": {"passed": False, "reason": "claim not in context"}}, {}],
        drafts=["REJECTED-DRAFT we are open 24/7.", "We are open weekdays 9-5."],
    )

    chunks = [
        chunk
        async for chunk in _stream_chat_response(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message="What are your hours?",
            provider=provider,
            embedder=ZeroEmbedder(),
            reranker=PassthroughReranker(),
        )
    ]

    body = "".join(chunks)
    assert "REJECTED-DRAFT" not in body
    events = [json.loads(chunk.removeprefix("data: ")) for chunk in chunks]
    types = [event["type"] for event in events]
    assert types == ["conversation", "citations"] + ["token"] * 5 + ["done"]
    streamed = "".join(e["text"] for e in events if e["type"] == "token")
    assert streamed == "We are open weekdays 9-5. "

    row = await superuser_conn.fetchrow(
        "select content, metadata from messages where conversation_id = $1 and role = 'assistant'",
        conversation_id,
    )
    assert row is not None
    assert row["content"] == "We are open weekdays 9-5. "
    metadata = json.loads(row["metadata"])
    assert all(check["passed"] for check in metadata["inspection"].values())


# --- price-provenance re-assert: pure unit test -------------------------------


def _quoting_state(draft: str, *, engine_quote: dict[str, Any] | None = None) -> AgentState:
    return {
        "conversation_id": "test",
        "tenant_id": "test",
        "messages": [{"role": "customer", "content": "hi"}],
        "route": "quoting",
        "route_confidence": 1.0,
        "retrieved_chunks": [],
        "selections": [],
        "engine_quote": engine_quote,
        "draft_response": draft,
        "inspection": None,
        "escalated": False,
    }


def test_price_provenance_reassert_catches_a_bad_figure_on_quoting() -> None:
    verdict = check_price_provenance(_quoting_state("I can do it for $99!"))
    assert verdict.passed is False
    assert "$99" in verdict.reason


def test_price_provenance_reassert_is_scoped_to_money_gated_routes_only() -> None:
    state = _quoting_state("I can do it for $99!")
    state["route"] = "knowledge"
    verdict = check_price_provenance(state)
    assert verdict.passed is True
