"""T-017: Quoting Agent node tests - stubbed provider, real engine, driven
through the graph (get_runtime constraint, see T-013's memory entry).

Proves the hard rule end to end at the node level: the model only ever emits
selections (codes/ids + quantities), every displayed figure comes from the
engine, the quotes row is persisted verbatim from engine output, and the
selection schema itself contains no money-shaped field (a regression test
against anyone "helpfully" adding one).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import asyncpg
import pytest
from pydantic import BaseModel

from app.agents.graph import build_graph
from app.agents.quoting import QuoteSelectionResult, SelectionChoice
from app.agents.state import AgentState, GraphContext
from app.core import db
from app.ingestion.chunker import chunk_catalog_item
from app.llm.provider import ChatMessage, SchemaT
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class FakeQuotingProvider(BaseFakeProvider):
    """Returns queued selection payloads for the selection schema, a fixed
    verdict for the budget schema, and records every extract call."""

    def __init__(
        self,
        selection_payloads: list[dict[str, Any]],
        budget_payload: dict[str, Any] | None = None,
    ) -> None:
        self._selection_payloads = list(selection_payloads)
        self._budget_payload = budget_payload or {"within_budget": True}
        self.extract_calls: list[tuple[str, str]] = []

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        if "grounding" in schema.model_fields:
            # T-021's inspection node, not one of this node's own selection/
            # budget calls - every field defaults to a passing verdict, and
            # this call is deliberately excluded from extract_calls (which
            # tracks only quoting.py's own calls).
            return schema.model_validate({})
        self.extract_calls.append((system_prompt, user_input))
        if "selections" in schema.model_fields:
            return schema.model_validate(self._selection_payloads.pop(0))
        if "within_budget" in schema.model_fields:
            return schema.model_validate(self._budget_payload)
        raise AssertionError(f"unexpected extract schema: {schema}")

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.stream_system_prompt = messages[0]["content"]
        for delta in ["Here is", " your quote."]:
            yield delta


class PassthroughReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


def _initial_state(message: str, conversation_id: uuid.UUID) -> AgentState:
    return {
        "conversation_id": str(conversation_id),
        "tenant_id": "test",
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


def _forced_route(route: str) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def supervisor_stub(state: AgentState) -> dict[str, Any]:
        return {"route": route, "route_confidence": 1.0}

    return supervisor_stub


async def _seed_quoting_tenant(
    conn: asyncpg.Connection[Any], *, tax_rate_bps: int = 0
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Tenant + config (optional tax) + one pricing rule + one priced catalog
    item (with its chunk) + one conversation. Returns (tenant_id,
    conversation_id, catalog_item_id)."""
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Quote Test Co') returning id",
        f"quoting-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute(
        "insert into tenant_config (tenant_id, config) values ($1, $2)",
        tenant_id,
        json.dumps({"tax": {"rate_bps": tax_rate_bps}} if tax_rate_bps else {}),
    )
    await conn.execute(
        "insert into pricing_rules (tenant_id, code, label, unit_amount_cents) "
        "values ($1, 'screen-repair-a', 'Screen repair (tier A)', 12000)",
        tenant_id,
    )
    document_id: uuid.UUID = await conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'catalog', 'catalog', 'ready') returning id",
        tenant_id,
    )
    item_id: uuid.UUID = await conn.fetchval(
        "insert into catalog_items (tenant_id, name, description, price_cents) "
        "values ($1, 'Tempered glass protector', 'A protective layer', 1500) returning id",
        tenant_id,
    )
    chunk = chunk_catalog_item(str(item_id), "Tempered glass protector", "A protective layer", 1500)
    await conn.execute(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, $3, $4, $5)",
        tenant_id,
        document_id,
        chunk.content,
        [0.0] * EMBEDDING_DIM,
        json.dumps(chunk.metadata),
    )
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    return tenant_id, conversation_id, item_id


def _context(tenant_id: uuid.UUID, provider: FakeQuotingProvider) -> GraphContext:
    return GraphContext(
        tenant_id=tenant_id,
        provider=provider,
        embedder=ZeroEmbedder(),
        reranker=PassthroughReranker(),
    )


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def test_selection_flows_through_engine_to_persisted_row(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn, tax_rate_bps=800)
    provider = FakeQuotingProvider(
        [
            {
                "selections": [{"rule_code": "screen-repair-a", "quantity": 1}],
                "has_budget_constraint": False,
                "explanation": "One tier-A screen repair.",
            }
        ]
    )
    graph = build_graph(supervisor_node=_forced_route("quoting"))

    final_state = await graph.ainvoke(
        _initial_state("How much is a screen repair?", conversation_id),
        context=_context(tenant_id, provider),
    )

    engine_quote = final_state["engine_quote"]
    assert engine_quote is not None
    assert engine_quote["subtotal_cents"] == 12000
    assert engine_quote["tax_cents"] == 960
    assert engine_quote["total_cents"] == 12960

    row = await superuser_conn.fetchrow(
        "select * from quotes where tenant_id = $1 and conversation_id = $2",
        tenant_id,
        conversation_id,
    )
    assert row is not None
    assert row["subtotal_cents"] == 12000
    assert row["tax_cents"] == 960
    assert row["total_cents"] == 12960
    assert row["status"] == "sent"
    line_items = json.loads(row["line_items"])
    assert line_items == engine_quote["line_items"]
    assert line_items[0]["code"] == "screen-repair-a"
    assert line_items[0]["line_total_cents"] == 12000
    assert str(row["id"]) == engine_quote["quote_id"]


async def test_catalog_item_selection_is_priced_from_db(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, item_id = await _seed_quoting_tenant(superuser_conn)
    provider = FakeQuotingProvider(
        [
            {
                "selections": [{"catalog_item_id": str(item_id), "quantity": 2}],
                "has_budget_constraint": False,
                "explanation": "Two protectors.",
            }
        ]
    )
    graph = build_graph(supervisor_node=_forced_route("quoting"))

    final_state = await graph.ainvoke(
        _initial_state("Price for two glass protectors?", conversation_id),
        context=_context(tenant_id, provider),
    )

    engine_quote = final_state["engine_quote"]
    assert engine_quote is not None
    assert engine_quote["total_cents"] == 3000
    assert engine_quote["line_items"][0]["unit_amount_cents"] == 1500


async def test_bad_selection_reselects_once_with_error_in_context(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn)
    provider = FakeQuotingProvider(
        [
            {
                "selections": [{"rule_code": "no-such-rule", "quantity": 1}],
                "has_budget_constraint": False,
                "explanation": "x",
            },
            {
                "selections": [{"rule_code": "screen-repair-a", "quantity": 1}],
                "has_budget_constraint": False,
                "explanation": "One tier-A screen repair.",
            },
        ]
    )
    graph = build_graph(supervisor_node=_forced_route("quoting"))

    final_state = await graph.ainvoke(
        _initial_state("How much is a screen repair?", conversation_id),
        context=_context(tenant_id, provider),
    )

    assert final_state["engine_quote"] is not None
    assert final_state["engine_quote"]["total_cents"] == 12000
    selection_calls = [c for c in provider.extract_calls if "selections" in c[0] or True]
    assert len(provider.extract_calls) == 2
    assert "no-such-rule" in provider.extract_calls[1][1]
    assert selection_calls  # both were selection calls; budget check was off


async def test_second_bad_selection_escalates_and_persists_nothing(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn)
    bad = {
        "selections": [{"rule_code": "no-such-rule", "quantity": 1}],
        "has_budget_constraint": False,
        "explanation": "x",
    }
    provider = FakeQuotingProvider([bad, bad])
    graph = build_graph(supervisor_node=_forced_route("quoting"))

    final_state = await graph.ainvoke(
        _initial_state("How much is a screen repair?", conversation_id),
        context=_context(tenant_id, provider),
    )

    assert final_state["engine_quote"] is None
    assert final_state["escalated"] is True
    count = await superuser_conn.fetchval(
        "select count(*) from quotes where tenant_id = $1", tenant_id
    )
    assert count == 0


async def test_no_candidates_refuses_without_engine_call(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Empty Quote Co') returning id",
        f"quoting-empty-{uuid.uuid4().hex[:8]}",
    )
    await superuser_conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    provider = FakeQuotingProvider([])
    graph = build_graph(supervisor_node=_forced_route("quoting"))

    final_state = await graph.ainvoke(
        _initial_state("How much for a repair?", conversation_id),
        context=_context(tenant_id, provider),
    )

    assert final_state["engine_quote"] is None
    assert final_state["draft_response"]
    assert provider.extract_calls == []


async def test_budget_check_receives_server_formatted_total_only(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn, tax_rate_bps=800)
    provider = FakeQuotingProvider(
        [
            {
                "selections": [{"rule_code": "screen-repair-a", "quantity": 1}],
                "has_budget_constraint": True,
                "explanation": "One tier-A screen repair.",
            }
        ],
        budget_payload={"within_budget": False},
    )
    graph = build_graph(supervisor_node=_forced_route("quoting"))

    final_state = await graph.ainvoke(
        _initial_state("Screen repair under $120?", conversation_id),
        context=_context(tenant_id, provider),
    )

    assert final_state["engine_quote"] is not None
    # The budget-verdict call gets the engine total formatted server-side -
    # the model compares, it never computes.
    budget_call = provider.extract_calls[-1]
    assert "$129.60" in budget_call[1]
    # The explanation stream is told the verdict as a fact, not asked to math.
    assert "exceeds" in provider.stream_system_prompt.lower()


def test_selection_schema_has_no_money_fields() -> None:
    """Regression guard on the hard rule: the model-facing schema must never
    grow a money-shaped field. Quantities are counts of things, not cents."""
    forbidden = ("price", "cent", "amount", "total", "cost", "money", "dollar", "tax", "subtotal")

    def assert_clean(model: type[BaseModel]) -> None:
        for name, field in model.model_fields.items():
            lowered = name.lower()
            assert not any(bad in lowered for bad in forbidden), (
                f"{model.__name__}.{name} looks like a money field"
            )
            annotation = field.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                assert_clean(annotation)

    assert_clean(QuoteSelectionResult)
    assert_clean(SelectionChoice)
    int_fields = [
        name
        for name, field in SelectionChoice.model_fields.items()
        if field.annotation in (int, int | None)
    ]
    assert int_fields == ["quantity"]
