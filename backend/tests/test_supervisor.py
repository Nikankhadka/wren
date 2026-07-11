"""T-013: supervisor routing unit tests with a stubbed provider.

``get_runtime()`` only works inside an actual graph node execution, so
these drive the real supervisor through ``build_graph()`` (not mocked out,
unlike test_agent_graph.py's forced-route tests) with a controllable fake
provider, and inspect the resulting state's route/route_confidence. Needs a
real tenant_config row for the escalation_threshold read, so these are DB
tests.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

from app.agents.graph import build_graph
from app.agents.state import AgentState, GraphContext
from app.core import db
from app.llm.provider import SchemaT
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider

pytestmark = pytest.mark.db


class FakeRouteProvider(BaseFakeProvider):
    def __init__(self, *, route: str, confidence: float) -> None:
        self._route = route
        self._confidence = confidence

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        return schema.model_validate(
            {"route": self._route, "confidence": self._confidence, "reason": "test"}
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Only reached when routed to "knowledge" - these test tenants have no
        # knowledge_chunks seeded, so retrieve() takes the refusal path
        # without ever needing a real embedding or chat_stream() call.
        return [[0.0] * 1536 for _ in texts]


class NoopReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


def _initial_state(message: str = "hi") -> AgentState:
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


async def _seed_tenant(conn: asyncpg.Connection[Any], *, escalation_threshold: float) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Routing Test Co') returning id",
        f"routing-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute(
        "insert into tenant_config (tenant_id, escalation_threshold) values ($1, $2)",
        tenant_id,
        escalation_threshold,
    )
    return tenant_id


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


@pytest.mark.parametrize(
    "route", ["knowledge", "recommendation", "quoting", "order_status", "escalation"]
)
async def test_high_confidence_routes_pass_through(
    superuser_conn: asyncpg.Connection[Any], route: str
) -> None:
    tenant_id = await _seed_tenant(superuser_conn, escalation_threshold=0.5)
    graph = build_graph()
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeRouteProvider(route=route, confidence=0.9),
        reranker=NoopReranker(),
    )

    final_state = await graph.ainvoke(_initial_state(), context=context)

    assert final_state["route"] == route
    assert final_state["route_confidence"] == 0.9


async def test_low_confidence_is_overridden_to_escalation(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn, escalation_threshold=0.5)
    graph = build_graph()
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeRouteProvider(route="quoting", confidence=0.2),
        reranker=NoopReranker(),
    )

    final_state = await graph.ainvoke(_initial_state("asdkjfh asdkjfh gibberish"), context=context)

    assert final_state["route"] == "escalation"
    assert final_state["escalated"] is True


async def test_confidence_exactly_at_threshold_is_not_escalated(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn, escalation_threshold=0.5)
    graph = build_graph()
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeRouteProvider(route="knowledge", confidence=0.5),
        reranker=NoopReranker(),
    )

    final_state = await graph.ainvoke(_initial_state(), context=context)

    assert final_state["route"] == "knowledge"


async def test_lower_tenant_threshold_lets_lower_confidence_through(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn, escalation_threshold=0.1)
    graph = build_graph()
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeRouteProvider(route="recommendation", confidence=0.2),
        reranker=NoopReranker(),
    )

    final_state = await graph.ainvoke(_initial_state(), context=context)

    assert final_state["route"] == "recommendation"
