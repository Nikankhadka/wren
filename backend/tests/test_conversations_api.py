"""T-031: GET /api/conversations (list + detail), the tenant-admin
Conversations tab. Same JWT pattern as test_escalations_api.py.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import asyncpg
import httpx
import jwt
import pytest
import pytest_asyncio

from app.core import db
from app.core.config import get_settings
from app.main import app
from tests.conftest import _app_dsn_for

pytestmark = pytest.mark.db

TEST_JWT_SECRET = "test-only-supabase-jwt-secret-do-not-use-in-prod"  # noqa: S105


@pytest.fixture(autouse=True)
def _supabase_jwt_secret_env() -> Iterator[None]:
    original = os.environ.get("SUPABASE_JWT_SECRET")
    os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
    get_settings.cache_clear()
    yield
    if original is None:
        os.environ.pop("SUPABASE_JWT_SECRET", None)
    else:
        os.environ["SUPABASE_JWT_SECRET"] = original
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await db.close_pool()


def _make_token(user_id: uuid.UUID) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "aud": "authenticated", "iat": now, "exp": now + 3600}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


async def _signup_tenant_admin(client: httpx.AsyncClient) -> tuple[str, uuid.UUID]:
    user_id = uuid.uuid4()
    token = _make_token(user_id)
    slug = f"conversations-api-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/tenants",
        json={"slug": slug, "name": "Conversations API Test Co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return token, uuid.UUID(response.json()["tenant_id"])


async def _seed_conversation(
    conn: asyncpg.Connection[Any],
    tenant_id: uuid.UUID,
    *,
    status: str = "open",
    customer_ref: str | None = None,
) -> uuid.UUID:
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id, status, customer_ref) values ($1, $2, $3) "
        "returning id",
        tenant_id,
        status,
        customer_ref,
    )
    return conversation_id


async def test_list_conversations_returns_only_this_tenants_rows(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    other_token, other_tenant_id = await _signup_tenant_admin(client)

    conversation_id = await _seed_conversation(superuser_conn, tenant_id, customer_ref="cust-1")
    await superuser_conn.execute(
        "insert into messages (tenant_id, conversation_id, role, content) "
        "values ($1, $2, 'customer', 'hi'), ($1, $2, 'assistant', 'hello')",
        tenant_id,
        conversation_id,
    )
    await _seed_conversation(superuser_conn, other_tenant_id)

    response = await client.get("/api/conversations", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(conversation_id)
    assert body[0]["customer_ref"] == "cust-1"
    assert body[0]["message_count"] == 2

    other_response = await client.get(
        "/api/conversations", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert len(other_response.json()) == 1


async def test_list_conversations_filters_by_status(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    await _seed_conversation(superuser_conn, tenant_id, status="open")
    escalated_id = await _seed_conversation(superuser_conn, tenant_id, status="escalated")

    response = await client.get(
        "/api/conversations?status=escalated", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(escalated_id)


async def test_get_conversation_detail_includes_tool_calls_verdicts_and_cost(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    conversation_id = await _seed_conversation(superuser_conn, tenant_id, customer_ref="cust-2")

    await superuser_conn.execute(
        "insert into messages (tenant_id, conversation_id, role, content) "
        "values ($1, $2, 'customer', 'where is my order?')",
        tenant_id,
        conversation_id,
    )
    assistant_message_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into messages (tenant_id, conversation_id, role, content, agent_node, metadata) "
        "values ($1, $2, 'assistant', 'it is on its way', 'order_status', $3) returning id",
        tenant_id,
        conversation_id,
        json.dumps({"inspection": {"grounding": {"passed": True, "reason": ""}}}),
    )
    await superuser_conn.execute(
        "insert into tool_calls (tenant_id, message_id, tool_name, arguments, result, success, "
        "latency_ms) values ($1, $2, 'lookup_order_or_ticket', $3, $4, true, 42)",
        tenant_id,
        assistant_message_id,
        json.dumps({"ref_code": "R-1001"}),
        json.dumps({"found": True, "status": "shipped"}),
    )
    await superuser_conn.execute(
        "insert into cost_logs (tenant_id, conversation_id, model, input_tokens, output_tokens, "
        "cost_usd) values ($1, $2, 'gpt-4o-mini', 100, 20, 0.5)",
        tenant_id,
        conversation_id,
    )

    response = await client.get(
        f"/api/conversations/{conversation_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["customer_ref"] == "cust-2"
    assert body["total_cost_usd"] == 0.5
    assert len(body["messages"]) == 2

    assistant_message = next(m for m in body["messages"] if m["role"] == "assistant")
    assert assistant_message["agent_node"] == "order_status"
    assert assistant_message["metadata"]["inspection"]["grounding"]["passed"] is True
    assert assistant_message["cost_usd"] == 0.5
    assert len(assistant_message["tool_calls"]) == 1
    assert assistant_message["tool_calls"][0]["tool_name"] == "lookup_order_or_ticket"
    assert assistant_message["tool_calls"][0]["arguments"] == {"ref_code": "R-1001"}
    assert assistant_message["tool_calls"][0]["success"] is True

    customer_message = next(m for m in body["messages"] if m["role"] == "customer")
    assert customer_message["cost_usd"] is None
    assert customer_message["tool_calls"] == []


async def test_get_conversation_detail_cross_tenant_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    _other_token, other_tenant_id = await _signup_tenant_admin(client)
    conversation_id = await _seed_conversation(superuser_conn, other_tenant_id)

    response = await client.get(
        f"/api/conversations/{conversation_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


async def test_list_conversations_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/conversations")
    assert response.status_code == 401
