"""T-028: end-to-end graceful-path tests for the cost/step caps, driven
through app.api.chat._stream_chat_response and the DB.

Proves the two acceptance criteria that need real wiring: a tenant at its
step cap gets the graceful handoff (escalation row + polite message, never a
stack trace), and an over-budget tenant is short-circuited before the graph
runs. Budget math and the timeout/step-cap primitives are unit-tested in
test_limits.py.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

from app.api.chat import _stream_budget_escalation, _stream_chat_response
from app.core import db
from app.core.config import get_settings
from app.core.limits import (
    BUDGET_ESCALATION_REASON,
    STEP_CAP_ESCALATION_REASON,
    TenantLimits,
    clear_usage_cache,
    tenant_over_budget,
)
from app.llm.provider import ChatMessage, SchemaT
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class _AlwaysRouteKnowledge(BaseFakeProvider):
    """Routes to knowledge and streams a normal answer - enough for the graph
    to execute the several nodes a step cap of 2 will overrun."""

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        if "route" in schema.model_fields:
            return schema.model_validate(
                {"route": "knowledge", "confidence": 0.99, "reason": "a plain question"}
            )
        return schema.model_validate({})

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        for token in ("We are ", "open ", "weekdays."):
            yield token


class _PassthroughReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


async def _seed(conn: asyncpg.Connection[Any]) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Limits Test Co') returning id",
        f"limits-{uuid.uuid4().hex[:8]}",
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
    clear_usage_cache()
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()
    clear_usage_cache()


async def test_step_cap_yields_graceful_handoff_not_a_stack_trace(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed(superuser_conn)
    # max_steps=2 is fewer nodes than any real turn needs (supervisor + at
    # least one specialist + inspection), so the cap trips.
    limits = TenantLimits.resolve({"limits": {"max_steps": 2}}, get_settings())

    chunks = [
        chunk
        async for chunk in _stream_chat_response(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message="What are your hours?",
            provider=_AlwaysRouteKnowledge(),
            embedder=ZeroEmbedder(),
            reranker=_PassthroughReranker(),
            limits=limits,
        )
    ]
    body = "".join(chunks)
    assert "escalated" in body
    assert "Traceback" not in body

    # The graceful path recorded a step_cap escalation and flipped the
    # conversation to escalated.
    row = await superuser_conn.fetchrow(
        "select reason from escalations where conversation_id = $1", conversation_id
    )
    assert row is not None and row["reason"] == STEP_CAP_ESCALATION_REASON
    status = await superuser_conn.fetchval(
        "select status from conversations where id = $1", conversation_id
    )
    assert status == "escalated"


async def test_over_budget_tenant_is_detected_and_escalated(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed(superuser_conn)
    # Seed today's cost_logs above a $1 daily cap.
    await superuser_conn.execute(
        "insert into cost_logs (tenant_id, conversation_id, model, cost_usd) "
        "values ($1, $2, 'test-model', 2.50)",
        tenant_id,
        conversation_id,
    )
    limits = TenantLimits.resolve({"limits": {"daily_cost_usd": 1.0}}, get_settings())

    async with db.tenant_context(tenant_id, "customer") as conn:
        assert await tenant_over_budget(conn, tenant_id, limits)

    # The graceful budget path records the escalation and persists the handoff.
    chunks = [
        chunk
        async for chunk in _stream_budget_escalation(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
    ]
    body = "".join(chunks)
    assert "escalated" in body

    reason = await superuser_conn.fetchval(
        "select reason from escalations where conversation_id = $1", conversation_id
    )
    assert reason == BUDGET_ESCALATION_REASON
    role_content = await superuser_conn.fetchrow(
        "select role, metadata from messages where conversation_id = $1 and role = 'assistant'",
        conversation_id,
    )
    assert role_content is not None
    assert json.loads(role_content["metadata"])["limit_escalation"] == BUDGET_ESCALATION_REASON


async def test_under_budget_tenant_is_not_flagged(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed(superuser_conn)
    await superuser_conn.execute(
        "insert into cost_logs (tenant_id, conversation_id, model, cost_usd) "
        "values ($1, $2, 'test-model', 0.10)",
        tenant_id,
        conversation_id,
    )
    limits = TenantLimits.resolve({"limits": {"daily_cost_usd": 5.0}}, get_settings())
    async with db.tenant_context(tenant_id, "customer") as conn:
        assert not await tenant_over_budget(conn, tenant_id, limits)
