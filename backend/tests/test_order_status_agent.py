"""T-019: order_status node tests, driven through the graph (get_runtime()
only works inside an actual node execution - see T-013's memory entry).
Confirms the draft is deterministic - built entirely from the DB row - and
never invents a status when nothing or the wrong thing is found.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import asyncpg
import pytest

from app.agents.graph import build_graph
from app.agents.order_status import ASK_FOR_CODE_MESSAGE
from app.agents.state import AgentState, GraphContext
from app.core import db
from app.llm.provider import SchemaT
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class FakeRefProvider(BaseFakeProvider):
    def __init__(self, *, ref_code: str | None) -> None:
        self._ref_code = ref_code

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        return schema.model_validate({"ref_code": self._ref_code, "customer_ref": None})


class NoopReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


def _forced_route(route: str) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def supervisor_stub(state: AgentState) -> dict[str, Any]:
        return {"route": route, "route_confidence": 1.0}

    return supervisor_stub


def _initial_state(message: str) -> AgentState:
    return {
        "conversation_id": "test",
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


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def _seed_tenant_with_order(
    conn: asyncpg.Connection[Any], *, ref_code: str, status: str
) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Order Status Test Co') returning id",
        f"order-status-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    await conn.execute(
        "insert into orders (tenant_id, ref_code, kind, status, details) "
        "values ($1, $2, 'repair', $3, $4)",
        tenant_id,
        ref_code,
        status,
        json.dumps({}),
    )
    return tenant_id


async def test_found_ref_produces_a_deterministic_draft(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant_with_order(
        superuser_conn, ref_code="R-1042", status="ready_for_pickup"
    )
    graph = build_graph(supervisor_node=_forced_route("order_status"))
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeRefProvider(ref_code="R-1042"),
        embedder=ZeroEmbedder(),
        reranker=NoopReranker(),
    )

    final_state = await graph.ainvoke(_initial_state("where is R-1042"), context=context)

    assert "R-1042" in final_state["draft_response"]
    assert "ready_for_pickup" in final_state["draft_response"]


async def test_unknown_ref_never_invents_a_status(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant_with_order(superuser_conn, ref_code="R-1042", status="pending")
    graph = build_graph(supervisor_node=_forced_route("order_status"))
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeRefProvider(ref_code="R-9999"),
        embedder=ZeroEmbedder(),
        reranker=NoopReranker(),
    )

    final_state = await graph.ainvoke(_initial_state("where is R-9999"), context=context)

    assert "R-9999" in final_state["draft_response"]
    assert "double-check" in final_state["draft_response"]


async def test_no_ref_extracted_asks_for_one(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'No Ref Co') returning id",
        f"order-status-noref-{uuid.uuid4().hex[:8]}",
    )
    await superuser_conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)

    graph = build_graph(supervisor_node=_forced_route("order_status"))
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeRefProvider(ref_code=None),
        embedder=ZeroEmbedder(),
        reranker=NoopReranker(),
    )

    final_state = await graph.ainvoke(_initial_state("hi"), context=context)

    assert final_state["draft_response"] == ASK_FOR_CODE_MESSAGE


async def test_wrong_tenant_ref_is_treated_as_not_found(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    await _seed_tenant_with_order(superuser_conn, ref_code="R-1042", status="ready_for_pickup")
    other_tenant_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Other Co') returning id",
        f"order-status-other-{uuid.uuid4().hex[:8]}",
    )
    await superuser_conn.execute(
        "insert into tenant_config (tenant_id) values ($1)", other_tenant_id
    )

    graph = build_graph(supervisor_node=_forced_route("order_status"))
    context = GraphContext(
        tenant_id=other_tenant_id,
        provider=FakeRefProvider(ref_code="R-1042"),
        embedder=ZeroEmbedder(),
        reranker=NoopReranker(),
    )

    final_state = await graph.ainvoke(_initial_state("where is R-1042"), context=context)

    assert "double-check" in final_state["draft_response"]
    assert "ready_for_pickup" not in final_state["draft_response"]
