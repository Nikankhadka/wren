"""T-005: GET /api/public/tenant/{slug}, the pre-auth slug -> tenant resolve.

Same client-fixture pattern as test_auth_api.py: httpx ASGITransport against the
real app, a dedicated wren_app pool pointed at wren_test. No JWTs needed here -
the endpoint is unauthenticated by design (it is what resolves a tenant before
any auth/tenant_context exists).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import httpx
import pytest
import pytest_asyncio

from app.core import db
from app.main import app
from tests.conftest import _app_dsn_for

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def client(migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await db.close_pool()


async def _seed_tenant(
    conn: asyncpg.Connection[Any], *, slug: str, name: str, status: str = "active"
) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    async with conn.transaction():
        await conn.execute("select set_config('app.role', 'platform_admin', true)")
        await conn.execute(
            "insert into tenants (id, slug, name, status) values ($1, $2, $3, $4)",
            tenant_id,
            slug,
            name,
            status,
        )
        await conn.execute(
            "insert into tenant_config (tenant_id, brand) values ($1, $2)",
            tenant_id,
            '{"display_name": "Bytefix Repairs", "accent": "#D97757"}',
        )
    return tenant_id


async def test_resolve_known_active_slug(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"active-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant(superuser_conn, slug=slug, name="Active Co")

    response = await client.get(f"/api/public/tenant/{slug}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(tenant_id)
    assert body["name"] == "Active Co"
    assert body["status"] == "active"
    assert body["brand"] == {"display_name": "Bytefix Repairs", "accent": "#D97757"}


async def test_resolve_suspended_slug_is_200_with_status(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"suspended-{uuid.uuid4().hex[:8]}"
    await _seed_tenant(superuser_conn, slug=slug, name="Suspended Co", status="suspended")

    response = await client.get(f"/api/public/tenant/{slug}")
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"


async def test_resolve_unknown_slug_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/public/tenant/no-such-{uuid.uuid4().hex[:8]}")
    assert response.status_code == 404


async def test_resolve_never_leaks_columns_beyond_the_four(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"leaktest-{uuid.uuid4().hex[:8]}"
    await _seed_tenant(superuser_conn, slug=slug, name="Leak Test Co")

    response = await client.get(f"/api/public/tenant/{slug}")
    assert response.status_code == 200
    assert set(response.json().keys()) == {"id", "name", "status", "brand"}
