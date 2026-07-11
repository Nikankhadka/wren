"""T-020: GET /api/escalations, the tenant-admin read endpoint. Same JWT
pattern as test_auth_api.py; seeds escalations directly since triggering a
real one end-to-end is test_escalation_agent.py's job, not this file's.
"""

from __future__ import annotations

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
    slug = f"escalations-api-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/tenants",
        json={"slug": slug, "name": "Escalations API Test Co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return token, uuid.UUID(response.json()["tenant_id"])


async def test_list_escalations_returns_only_this_tenants_rows(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    other_token, other_tenant_id = await _signup_tenant_admin(client)

    conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id, status) values ($1, 'escalated') returning id",
        tenant_id,
    )
    await superuser_conn.execute(
        "insert into escalations (tenant_id, conversation_id, reason) values ($1, $2, $3)",
        tenant_id,
        conversation_id,
        "customer_request",
    )
    other_conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id, status) values ($1, 'escalated') returning id",
        other_tenant_id,
    )
    await superuser_conn.execute(
        "insert into escalations (tenant_id, conversation_id, reason) values ($1, $2, $3)",
        other_tenant_id,
        other_conversation_id,
        "low_confidence",
    )

    response = await client.get("/api/escalations", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["conversation_id"] == str(conversation_id)
    assert body[0]["reason"] == "customer_request"
    assert body[0]["status"] == "open"

    other_response = await client.get(
        "/api/escalations", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert len(other_response.json()) == 1
    assert other_response.json()[0]["conversation_id"] == str(other_conversation_id)


async def test_list_escalations_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/escalations")
    assert response.status_code == 401


async def test_list_escalations_empty_for_fresh_tenant(client: httpx.AsyncClient) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    response = await client.get("/api/escalations", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == []
