"""T-044: Escalation agent tests - tool-driven agent node calls
create_escalation tool, escalation node creates DB rows.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

from app.agents.escalation import HANDOFF_MESSAGE
from app.agents.graph import build_graph
from app.agents.state import AgentState, GraphContext
from app.llm.provider import ToolCall, ToolTurn
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from app.shared import db
from tests.conftest import _app_dsn_for
from tests.fakes import ToolAwareFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class NoopReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


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


def _escalation_provider(*, reason: str) -> ToolAwareFakeProvider:
    return ToolAwareFakeProvider(
        tool_call_sequence=[
            ToolTurn(
                tool_calls=[
                    ToolCall(id="call_e", name="create_escalation", args={"reason": reason}),
                ]
            ),
        ],
        stream_text="",
        extract_route="escalation",
    )


async def test_escalation_records_the_handoff_and_leaves_the_chat_open(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """C-5's core claim: escalating notifies a human without ending the chat."""
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    graph = build_graph()
    context = GraphContext(
        tenant_id=tenant_id,
        provider=_escalation_provider(reason="customer_request"),
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
    assert conversation_status == "open"


async def test_escalation_is_scoped_to_its_own_tenant(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_a, conversation_a = await _seed_tenant_with_conversation(superuser_conn)
    tenant_b, conversation_b = await _seed_tenant_with_conversation(superuser_conn)
    graph = build_graph()
    context = GraphContext(
        tenant_id=tenant_a,
        provider=_escalation_provider(reason="low_confidence"),
        embedder=ZeroEmbedder(),
        reranker=NoopReranker(),
    )
    await graph.ainvoke(
        _initial_state(tenant_id=tenant_a, conversation_id=conversation_a), context=context
    )
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
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    graph = build_graph()
    context = GraphContext(
        tenant_id=tenant_id,
        provider=_escalation_provider(reason="low_confidence"),
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
    assert status == "open"


# --- C-5: what happens *after* a handoff ------------------------------------


async def test_the_conversation_keeps_working_after_a_handoff(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Escalate, then ask something else on the same conversation and get a
    real answer.

    This is the failure C-5 exists to remove: one unanswerable question used to
    end a session that was working fine for everything else.
    """
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    graph = build_graph()

    await graph.ainvoke(
        _initial_state(tenant_id=tenant_id, conversation_id=conversation_id),
        context=GraphContext(
            tenant_id=tenant_id,
            provider=_escalation_provider(reason="customer_request"),
            embedder=ZeroEmbedder(),
            reranker=NoopReranker(),
        ),
    )

    follow_up = _initial_state(tenant_id=tenant_id, conversation_id=conversation_id)
    follow_up["messages"] = [{"role": "customer", "content": "what are your hours?"}]
    second_state = await graph.ainvoke(
        follow_up,
        context=GraphContext(
            tenant_id=tenant_id,
            provider=ToolAwareFakeProvider(
                tool_call_sequence=[ToolTurn(text="We're open 9 to 5.", tool_calls=[])],
                stream_text="We're open 9 to 5.",
                extract_route="conversation",
            ),
            embedder=ZeroEmbedder(),
            reranker=NoopReranker(),
        ),
    )

    assert second_state["escalated"] is False
    assert second_state["draft_response"] == "We're open 9 to 5."
    assert (
        await superuser_conn.fetchval(
            "select status from conversations where id = $1", conversation_id
        )
        == "open"
    )


async def test_a_second_handoff_does_not_queue_a_duplicate_for_the_owner(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """The chat continues, so it may hand off again - the owner should still
    see one open item, not one per attempt."""
    tenant_id, conversation_id = await _seed_tenant_with_conversation(superuser_conn)
    graph = build_graph()
    for reason in ("customer_request", "customer_request_again"):
        await graph.ainvoke(
            _initial_state(tenant_id=tenant_id, conversation_id=conversation_id),
            context=GraphContext(
                tenant_id=tenant_id,
                provider=_escalation_provider(reason=reason),
                embedder=ZeroEmbedder(),
                reranker=NoopReranker(),
            ),
        )
    open_rows = await superuser_conn.fetchval(
        "select count(*) from escalations where conversation_id = $1 and status = 'open'",
        conversation_id,
    )
    assert open_rows == 1
