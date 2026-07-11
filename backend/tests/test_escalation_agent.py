"""T-020: Escalation Agent node tests, driven through the graph (get_runtime()
constraint - see T-013's memory entry). Confirms the escalations row,
conversations.status flip, and reason plumbing from each upstream path.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import asyncpg
import pytest

from app.agents.escalation import HANDOFF_MESSAGE
from app.agents.graph import build_graph
from app.agents.state import AgentState, GraphContext
from app.core import db
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class NoopReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


def _forced_route(
    route: str, *, escalation_reason: str | None = None
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def supervisor_stub(state: AgentState) -> dict[str, Any]:
        update: dict[str, Any] = {"route": route, "route_confidence": 1.0}
        if escalation_reason is not None:
            update["escalation_reason"] = escalation_reason
        return update

    return supervisor_stub


def _initial_state(*, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> AgentState:
    return {
        "conversation_id": str(conversation_id),
        "tenant_id": str(tenant_id),
        "messages": [{"role": "customer", "content": "I want to talk to a human"}],
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


async def _seed_tenant_with_conversation(
    conn: asyncpg.Connection[Any],
) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Escalation Test Co') returning id",
        f"escalation-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    return tenant_id, conversation_id


async def test_escalation_creates_row_and_flips_conversation_status(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    graph = build_graph(
        supervisor_node=_forced_route("escalation", escalation_reason="customer_request")
    )
    context = GraphContext(
        tenant_id=tenant_id,
        provider=BaseFakeProvider(),
        embedder=ZeroEmbedder(),
        reranker=NoopReranker(),
    )

    final_state = await graph.ainvoke(
        _initial_state(tenant_id=tenant_id, conversation_id=conversation_id), context=context
    )

    assert final_state["escalated"] is True
    assert final_state["draft_response"] == HANDOFF_MESSAGE

    escalation_row = await superuser_conn.fetchrow(
        "select reason, status from escalations where conversation_id = $1", conversation_id
    )
    assert escalation_row is not None
    assert escalation_row["reason"] == "customer_request"
    assert escalation_row["status"] == "open"

    conversation_status = await superuser_conn.fetchval(
        "select status from conversations where id = $1", conversation_id
    )
    assert conversation_status == "escalated"


async def test_escalation_without_reason_uses_unspecified(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    graph = build_graph(supervisor_node=_forced_route("escalation"))
    context = GraphContext(
        tenant_id=tenant_id,
        provider=BaseFakeProvider(),
        embedder=ZeroEmbedder(),
        reranker=NoopReranker(),
    )

    await graph.ainvoke(
        _initial_state(tenant_id=tenant_id, conversation_id=conversation_id), context=context
    )

    reason = await superuser_conn.fetchval(
        "select reason from escalations where conversation_id = $1", conversation_id
    )
    assert reason == "unspecified"


async def test_escalation_is_scoped_to_its_own_tenant(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_a, conversation_a = await _seed_tenant_with_conversation(superuser_conn)
    tenant_b, conversation_b = await _seed_tenant_with_conversation(superuser_conn)

    graph = build_graph(
        supervisor_node=_forced_route("escalation", escalation_reason="low_confidence")
    )
    context = GraphContext(
        tenant_id=tenant_a,
        provider=BaseFakeProvider(),
        embedder=ZeroEmbedder(),
        reranker=NoopReranker(),
    )
    await graph.ainvoke(
        _initial_state(tenant_id=tenant_a, conversation_id=conversation_a), context=context
    )

    # Tenant B's conversation is untouched by tenant A's escalation.
    status_b = await superuser_conn.fetchval(
        "select status from conversations where id = $1", conversation_b
    )
    assert status_b == "open"
    escalations_for_b = await superuser_conn.fetchval(
        "select count(*) from escalations where conversation_id = $1", conversation_b
    )
    assert escalations_for_b == 0


async def test_concurrent_escalations_on_same_conversation_do_not_duplicate(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """0011_escalations_dedupe.sql's partial unique index guards the
    check-then-act race between chat.py's status read and this node's
    write - two racing turns on the same conversation must only produce
    one open escalations row."""
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    graph = build_graph(
        supervisor_node=_forced_route("escalation", escalation_reason="low_confidence")
    )
    context = GraphContext(
        tenant_id=tenant_id,
        provider=BaseFakeProvider(),
        embedder=ZeroEmbedder(),
        reranker=NoopReranker(),
    )

    await asyncio.gather(
        graph.ainvoke(
            _initial_state(tenant_id=tenant_id, conversation_id=conversation_id), context=context
        ),
        graph.ainvoke(
            _initial_state(tenant_id=tenant_id, conversation_id=conversation_id), context=context
        ),
    )

    open_escalations = await superuser_conn.fetchval(
        "select count(*) from escalations where conversation_id = $1 and status = 'open'",
        conversation_id,
    )
    assert open_escalations == 1

    status = await superuser_conn.fetchval(
        "select status from conversations where id = $1", conversation_id
    )
    assert status == "escalated"
