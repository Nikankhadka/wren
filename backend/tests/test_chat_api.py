"""T-011: bare /api/chat, exercised at the API level.

Seeds a tenant + one knowledge chunk directly via superuser_conn (matching
test_retrieval.py's pattern - no signup/auth needed, the customer surface
has none). A `ControllableReranker` fixes the rerank score so the happy
path and the refusal path are both deterministic, rather than depending on
the real local cross-encoder's actual judgment.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import asyncpg
import httpx
import pytest
import pytest_asyncio

from app.agents.knowledge import REFUSAL_MESSAGE
from app.core import db
from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.provider import SchemaT
from app.main import app
from app.observability.cost import report_usage
from app.retrieval.dependency import get_reranker_dependency
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class FakeChatProvider(BaseFakeProvider):
    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        # The only extract() caller in this flow is the supervisor's routing
        # decision (T-013) - always route to knowledge with high confidence
        # so these tests keep exercising T-011's straight RAG path.
        return schema.model_validate({"route": "knowledge", "confidence": 1.0, "reason": "test"})

    async def chat_stream(self, messages: list[Any]) -> AsyncIterator[str]:
        for delta in ["Sure", ", ", "here's ", "the ", "answer", " [1]", "."]:
            yield delta


class ControllableReranker(Reranker):
    def __init__(self, score: float) -> None:
        self._score = score

    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return [replace(chunk, score=self._score) for chunk in candidates[:top_k]]


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


@pytest_asyncio.fixture
async def client(migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    app.dependency_overrides[get_llm_provider] = FakeChatProvider
    app.dependency_overrides[get_embedder_dependency] = ZeroEmbedder
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)
        app.dependency_overrides.pop(get_embedder_dependency, None)
        app.dependency_overrides.pop(get_reranker_dependency, None)
        await db.close_pool()


async def _seed_tenant_with_chunk(
    conn: asyncpg.Connection[Any], *, slug: str, status: str = "active"
) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name, status) values ($1, $2, $3) returning id",
        slug,
        "Chat Test Co",
        status,
    )
    await conn.execute(
        "insert into tenant_config (tenant_id, system_prompt, tone) values ($1, $2, 'friendly')",
        tenant_id,
        "You help customers of Chat Test Co.",
    )
    document_id = await conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'faq.md', 'faq', 'ready') returning id",
        tenant_id,
    )
    await conn.execute(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, 'We are open weekdays 9-5.', $3, $4)",
        tenant_id,
        document_id,
        [0.0] * EMBEDDING_DIM,
        json.dumps({"source": "faq.md", "chunk_index": 0, "kind": "prose"}),
    )
    return tenant_id


async def test_chat_happy_path_streams_citations_and_tokens(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=1.0)

    response = await client.post(
        "/api/chat", json={"slug": slug, "message": "What are your hours?"}
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)

    types = [event["type"] for event in events]
    assert types == ["conversation", "citations"] + ["token"] * 7 + ["done"]
    assert events[1]["citations"][0]["source"] == "faq.md"
    full_text = "".join(e["text"] for e in events if e["type"] == "token")
    assert full_text == "Sure, here's the answer [1]."


async def test_chat_persists_customer_and_assistant_messages(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=1.0)

    response = await client.post(
        "/api/chat", json={"slug": slug, "message": "What are your hours?"}
    )
    events = _parse_sse(response.text)
    conversation_id = events[0]["conversation_id"]

    rows = await superuser_conn.fetch(
        "select role, content from messages where tenant_id = $1 and conversation_id = $2 "
        "order by created_at",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert [r["role"] for r in rows] == ["customer", "assistant"]
    assert rows[0]["content"] == "What are your hours?"
    assert rows[1]["content"] == "Sure, here's the answer [1]."


async def test_chat_refuses_when_nothing_is_relevant(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=-5.0)

    response = await client.post(
        "/api/chat", json={"slug": slug, "message": "What's the capital of France?"}
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)

    assert events[1]["type"] == "refusal"
    assert events[1]["text"] == REFUSAL_MESSAGE
    assert events[-1]["type"] == "done"
    assert not any(e["type"] == "citations" for e in events)


async def test_chat_resumes_an_existing_conversation(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=1.0)

    first = await client.post("/api/chat", json={"slug": slug, "message": "Hi"})
    conversation_id = _parse_sse(first.text)[0]["conversation_id"]

    second = await client.post(
        "/api/chat",
        json={"slug": slug, "conversation_id": conversation_id, "message": "Follow-up question"},
    )
    assert second.status_code == 200
    assert _parse_sse(second.text)[0]["conversation_id"] == conversation_id

    count = await superuser_conn.fetchval(
        "select count(*) from messages where tenant_id = $1 and conversation_id = $2",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert count == 4  # 2 customer + 2 assistant across both turns


async def test_chat_unknown_slug_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/chat", json={"slug": f"no-such-{uuid.uuid4().hex[:8]}", "message": "hi"}
    )
    assert response.status_code == 404


async def test_chat_suspended_tenant_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-suspended-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug, status="suspended")

    response = await client.post("/api/chat", json={"slug": slug, "message": "hi"})
    assert response.status_code == 404


async def test_chat_blocks_agent_turn_on_already_escalated_conversation(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """T-020: escalation is terminal - no agent turn runs (the graph is
    never invoked) once a conversation is escalated, but the customer's
    message is still persisted so the transcript stays complete."""
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id, status) values ($1, 'escalated') returning id",
        tenant_id,
    )

    response = await client.post(
        "/api/chat",
        json={
            "slug": slug,
            "conversation_id": str(conversation_id),
            "message": "are you still there?",
        },
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    types = [event["type"] for event in events]
    assert types == ["conversation", "escalated", "done"]
    assert not any(event["type"] == "token" for event in events)

    customer_message = await superuser_conn.fetchval(
        "select content from messages where tenant_id = $1 and conversation_id = $2 "
        "and role = 'customer'",
        tenant_id,
        conversation_id,
    )
    assert customer_message == "are you still there?"

    status = await superuser_conn.fetchval(
        "select status from conversations where id = $1", conversation_id
    )
    assert status == "escalated"


async def test_chat_wrong_tenant_conversation_id_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug_a = f"chat-a-{uuid.uuid4().hex[:8]}"
    slug_b = f"chat-b-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug_a)
    await _seed_tenant_with_chunk(superuser_conn, slug=slug_b)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=1.0)

    first = await client.post("/api/chat", json={"slug": slug_a, "message": "hi"})
    conversation_id = _parse_sse(first.text)[0]["conversation_id"]

    response = await client.post(
        "/api/chat",
        json={"slug": slug_b, "conversation_id": conversation_id, "message": "hi again"},
    )
    assert response.status_code == 404


class FakeOrderStatusProvider(BaseFakeProvider):
    """T-030: routes to order_status and reports fake token usage on every
    extract() call, so a real /api/chat turn exercises both the tool_calls
    persistence (order_status's real DB lookup) and cost_logs recording
    (report_usage -> chat.py's collect_usage()/record_costs())."""

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        report_usage("fake-model", 10, 5)
        if "route" in schema.model_fields:
            return schema.model_validate(
                {"route": "order_status", "confidence": 1.0, "reason": "test"}
            )
        return schema.model_validate({"ref_code": "R-1001", "customer_ref": None})


async def _seed_tenant_with_order(conn: asyncpg.Connection[Any], *, slug: str) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name, status) values ($1, $2, 'active') returning id",
        slug,
        "Order Status Chat Test Co",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    await conn.execute(
        "insert into orders (tenant_id, ref_code, kind, status, details) "
        "values ($1, 'R-1001', 'repair', 'ready_for_pickup', '{}')",
        tenant_id,
    )
    return tenant_id


async def test_chat_persists_tool_calls_and_cost_logs_for_order_status_turn(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-order-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_order(superuser_conn, slug=slug)
    # Override the client fixture's default FakeChatProvider - this turn needs
    # to route to order_status, not knowledge.
    app.dependency_overrides[get_llm_provider] = FakeOrderStatusProvider

    chat_response = await client.post(
        "/api/chat", json={"slug": slug, "message": "any news on repair R-1001?"}
    )
    assert chat_response.status_code == 200
    conversation_id = _parse_sse(chat_response.text)[0]["conversation_id"]

    tool_call_row = await superuser_conn.fetchrow(
        "select tc.tool_name, tc.arguments, tc.result, tc.success, tc.latency_ms "
        "from tool_calls tc join messages m on m.id = tc.message_id "
        "where m.tenant_id = $1 and m.conversation_id = $2",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert tool_call_row is not None
    assert tool_call_row["tool_name"] == "lookup_order_or_ticket"
    assert json.loads(tool_call_row["arguments"])["ref_code"] == "R-1001"
    assert json.loads(tool_call_row["result"])["found"] is True
    assert tool_call_row["success"] is True
    assert tool_call_row["latency_ms"] is not None

    cost_rows = await superuser_conn.fetch(
        "select model, input_tokens, output_tokens, cost_usd from cost_logs "
        "where tenant_id = $1 and conversation_id = $2",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert len(cost_rows) >= 1
    assert all(row["model"] == "fake-model" for row in cost_rows)
    assert sum(row["input_tokens"] for row in cost_rows) >= 10
    assert all(row["cost_usd"] == 0 for row in cost_rows)  # unknown model prices at $0


async def _seed_transcript(conn: asyncpg.Connection[Any], tenant_id: uuid.UUID) -> uuid.UUID:
    """A conversation holding one message of every role, including 'system' -
    the public poll endpoint must return everything except the system one."""
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    for role, content in [
        ("customer", "where is my order?"),
        ("assistant", "let me check."),
        ("system", "internal prompt - never customer-visible"),
        ("human_agent", "A team member will call you shortly."),
    ]:
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content) "
            "values ($1, $2, $3, $4)",
            tenant_id,
            conversation_id,
            role,
            content,
        )
    return conversation_id


async def test_public_messages_returns_transcript_without_system_messages(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """T-031: the unauthenticated transcript poll returns customer, assistant
    and human_agent messages in order - and never a system-role message."""
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    conversation_id = await _seed_transcript(superuser_conn, tenant_id)

    response = await client.get(f"/api/chat/{conversation_id}/messages", params={"slug": slug})
    assert response.status_code == 200
    body = response.json()
    assert [m["role"] for m in body] == ["customer", "assistant", "human_agent"]
    assert body[2]["content"] == "A team member will call you shortly."
    assert not any(m["role"] == "system" for m in body)


async def test_public_messages_wrong_tenant_slug_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """A valid conversation UUID paired with another tenant's slug must 404 -
    the slug scopes the lookup, so a leaked UUID alone crosses no tenant."""
    slug_a = f"chat-a-{uuid.uuid4().hex[:8]}"
    slug_b = f"chat-b-{uuid.uuid4().hex[:8]}"
    tenant_a = await _seed_tenant_with_chunk(superuser_conn, slug=slug_a)
    await _seed_tenant_with_chunk(superuser_conn, slug=slug_b)
    conversation_id = await _seed_transcript(superuser_conn, tenant_a)

    response = await client.get(f"/api/chat/{conversation_id}/messages", params={"slug": slug_b})
    assert response.status_code == 404


async def test_public_messages_unknown_conversation_or_slug_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug)

    response = await client.get(f"/api/chat/{uuid.uuid4()}/messages", params={"slug": slug})
    assert response.status_code == 404

    response = await client.get(
        f"/api/chat/{uuid.uuid4()}/messages",
        params={"slug": f"no-such-{uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 404


async def test_public_messages_after_cursor_returns_only_newer_messages(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """A client that already has the transcript up to some timestamp should
    be able to poll for only what's new, instead of re-fetching everything
    on every 5s tick."""
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    conversation_id = await _seed_transcript(superuser_conn, tenant_id)

    full = await client.get(f"/api/chat/{conversation_id}/messages", params={"slug": slug})
    assert full.status_code == 200
    cutoff = full.json()[0]["created_at"]

    response = await client.get(
        f"/api/chat/{conversation_id}/messages",
        params={"slug": slug, "after": cutoff},
    )
    assert response.status_code == 200
    body = response.json()
    assert [m["role"] for m in body] == ["assistant", "human_agent"]
