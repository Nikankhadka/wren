"""T-012: graph topology - given a forced route, the right node sequence runs.

`build_graph(supervisor_node=...)` lets tests force a route without real
intent classification (T-013), and `stream_mode="updates"` reports exactly
which node produced each state delta, so the test observes the actual
execution order rather than asserting on wiring it can't see. DB-backed
since T-015: the recommendation node does a real (possibly empty) catalog
query even when nothing is seeded.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import asyncpg
import pytest
import pytest_asyncio

from app.agents.graph import _SPECIALISTS, build_graph
from app.agents.state import AgentState, GraphContext
from app.core import db
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


@pytest_asyncio.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


class FakeReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


class FakeProvider(BaseFakeProvider):
    """Returns a schema-shaped dummy for whatever extract() call a
    specialist happens to make - only the shape matters for these topology
    tests, not the content."""

    async def extract(self, *, system_prompt: str, user_input: str, schema: type[Any]) -> Any:
        if "needs" in schema.model_fields:
            return schema.model_validate({"needs": [], "constraints": []})
        return schema.model_validate({"route": "knowledge", "confidence": 1.0, "reason": "test"})


def _initial_state(*, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> AgentState:
    return {
        "conversation_id": str(conversation_id),
        "tenant_id": str(tenant_id),
        "messages": [{"role": "customer", "content": "hi"}],
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


async def _seed_tenant_with_conversation(
    conn: asyncpg.Connection[Any],
) -> tuple[uuid.UUID, uuid.UUID]:
    """escalation.py writes real rows (escalations FK's conversations, updates
    conversations.status), so any test routing there needs both to exist -
    a bare uuid4() is no longer enough once a stub gains real logic (the
    exact trap flagged since T-015)."""
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Topology Test Co') returning id",
        f"topology-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    return tenant_id, conversation_id


async def _run_and_collect_node_order(
    route: str, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[str]:
    graph = build_graph(supervisor_node=_forced_route(route))
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeProvider(),
        embedder=ZeroEmbedder(),
        reranker=FakeReranker(),
    )
    order: list[str] = []
    initial_state = _initial_state(tenant_id=tenant_id, conversation_id=conversation_id)
    async for update in graph.astream(initial_state, context=context, stream_mode="updates"):
        order.extend(update.keys())
    return order


@pytest.mark.parametrize("route", ["recommendation", "quoting", "order_status", "escalation"])
async def test_forced_route_runs_supervisor_specialist_inspection(
    route: str, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    order = await _run_and_collect_node_order(
        route, tenant_id=tenant_id, conversation_id=conversation_id
    )
    if route in ("recommendation", "quoting"):
        # T-018: money-carrying specialists pass the price-provenance gate
        # before inspection.
        assert order == ["supervisor", route, "price_gate", "inspection"]
    else:
        assert order == ["supervisor", route, "inspection"]


async def test_escalation_route_sets_escalated_flag(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    graph = build_graph(supervisor_node=_forced_route("escalation"))
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeProvider(),
        embedder=ZeroEmbedder(),
        reranker=FakeReranker(),
    )
    initial_state = _initial_state(tenant_id=tenant_id, conversation_id=conversation_id)
    final_state = await graph.ainvoke(initial_state, context=context)
    assert final_state["escalated"] is True

    status = await superuser_conn.fetchval(
        "select status from conversations where id = $1", conversation_id
    )
    assert status == "escalated"


async def test_every_specialist_is_reachable_from_the_supervisor() -> None:
    graph = build_graph()
    node_names = set(graph.get_graph().nodes.keys())
    for specialist in _SPECIALISTS:
        assert specialist in node_names
    assert "supervisor" in node_names
    assert "inspection" in node_names
