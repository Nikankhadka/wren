"""T-033: the platform-owner surface API - admin-gated tenants list/provision/
suspend/reactivate and aggregate metrics.

Mirrors test_auth_api.py's fixture setup (own ASGI client against wren_test,
locally-minted HS256 tokens) rather than importing from it - each test file
here is self-contained by convention.
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


def _make_token(user_id: uuid.UUID, *, secret: str = TEST_JWT_SECRET) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def _insert_platform_admin(conn: asyncpg.Connection[Any], user_id: uuid.UUID) -> None:
    async with conn.transaction():
        await conn.execute("select set_config('app.role', 'platform_admin', true)")
        await conn.execute("insert into platform_admins (user_id) values ($1)", user_id)


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
        await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    return tenant_id


def _admin_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


# --- auth gating ----------------------------------------------------------


async def test_non_admin_gets_403_on_tenants_list(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/platform/tenants", headers=_admin_headers(uuid.uuid4()))
    assert response.status_code == 403


async def test_no_token_is_unauthorized(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/platform/tenants")
    assert response.status_code == 401


# --- list + metrics ---------------------------------------------------------


async def test_list_tenants_includes_seeded_rows(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)
    slug = f"list-{uuid.uuid4().hex[:8]}"
    await _seed_tenant(superuser_conn, slug=slug, name="List Co")

    response = await client.get("/api/platform/tenants", headers=_admin_headers(admin_id))
    assert response.status_code == 200
    rows = response.json()
    matching = [r for r in rows if r["slug"] == slug]
    assert len(matching) == 1
    assert matching[0]["conversation_count"] == 0
    assert matching[0]["cost_usd"] == 0.0


async def test_metrics_counts_are_sane(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)
    await _seed_tenant(superuser_conn, slug=f"metrics-{uuid.uuid4().hex[:8]}", name="Metrics Co")

    response = await client.get("/api/platform/metrics", headers=_admin_headers(admin_id))
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_count"] >= 1
    assert body["total_cost_usd"] >= 0.0


# --- slug availability -------------------------------------------------------


async def test_slug_availability_true_for_unused_slug(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)

    response = await client.get(
        "/api/platform/tenants/slug-availability",
        params={"slug": f"unused-{uuid.uuid4().hex[:8]}"},
        headers=_admin_headers(admin_id),
    )
    assert response.status_code == 200
    assert response.json() == {"available": True}


async def test_slug_availability_false_for_taken_slug(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)
    slug = f"taken-{uuid.uuid4().hex[:8]}"
    await _seed_tenant(superuser_conn, slug=slug, name="Taken Co")

    response = await client.get(
        "/api/platform/tenants/slug-availability",
        params={"slug": slug},
        headers=_admin_headers(admin_id),
    )
    assert response.status_code == 200
    assert response.json() == {"available": False}


# --- provision ---------------------------------------------------------------


async def test_provision_creates_tenant_and_config(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)
    slug = f"provision-{uuid.uuid4().hex[:8]}"

    response = await client.post(
        "/api/platform/tenants",
        json={"slug": slug, "name": "Provisioned Co"},
        headers=_admin_headers(admin_id),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "provisioning"
    assert body["note"]

    async with superuser_conn.transaction():
        await superuser_conn.execute("select set_config('app.role', 'platform_admin', true)")
        tenant_row = await superuser_conn.fetchrow(
            "select status from tenants where id = $1", uuid.UUID(body["id"])
        )
        config_row = await superuser_conn.fetchrow(
            "select tenant_id from tenant_config where tenant_id = $1", uuid.UUID(body["id"])
        )
    assert tenant_row is not None and tenant_row["status"] == "provisioning"
    assert config_row is not None


async def test_provision_duplicate_slug_is_conflict(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)
    slug = f"dupe-{uuid.uuid4().hex[:8]}"
    await _seed_tenant(superuser_conn, slug=slug, name="Original Co")

    response = await client.post(
        "/api/platform/tenants",
        json={"slug": slug, "name": "Duplicate Co"},
        headers=_admin_headers(admin_id),
    )
    assert response.status_code == 409


async def test_provision_bad_slug_is_unprocessable(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)

    response = await client.post(
        "/api/platform/tenants",
        json={"slug": "Not A Slug!", "name": "Bad Co"},
        headers=_admin_headers(admin_id),
    )
    assert response.status_code == 422


async def test_non_admin_cannot_provision(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/platform/tenants",
        json={"slug": f"blocked-{uuid.uuid4().hex[:8]}", "name": "Blocked Co"},
        headers=_admin_headers(uuid.uuid4()),
    )
    assert response.status_code == 403


# --- suspend / reactivate -----------------------------------------------------


async def test_suspend_then_reactivate_round_trips(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)
    slug = f"toggle-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant(superuser_conn, slug=slug, name="Toggle Co")

    suspend = await client.patch(
        f"/api/platform/tenants/{tenant_id}",
        json={"status": "suspended"},
        headers=_admin_headers(admin_id),
    )
    assert suspend.status_code == 200
    assert suspend.json()["status"] == "suspended"

    reactivate = await client.patch(
        f"/api/platform/tenants/{tenant_id}",
        json={"status": "active"},
        headers=_admin_headers(admin_id),
    )
    assert reactivate.status_code == 200
    assert reactivate.json()["status"] == "active"


async def test_suspend_takes_effect_on_public_resolve_endpoint(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """The accept criterion: suspend takes effect on the live customer
    surface. Resolve once first (warms public.py's 60s cache), then suspend,
    then resolve again - the cache invalidation must make the second resolve
    see 'suspended' immediately, not a stale cached 'active'."""
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)
    slug = f"suspend-live-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant(superuser_conn, slug=slug, name="Suspend Live Co")

    warm = await client.get(f"/api/public/tenant/{slug}")
    assert warm.status_code == 200
    assert warm.json()["status"] == "active"

    suspend = await client.patch(
        f"/api/platform/tenants/{tenant_id}",
        json={"status": "suspended"},
        headers=_admin_headers(admin_id),
    )
    assert suspend.status_code == 200

    after = await client.get(f"/api/public/tenant/{slug}")
    assert after.status_code == 200
    assert after.json()["status"] == "suspended"


async def test_status_update_unknown_tenant_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)

    response = await client.patch(
        f"/api/platform/tenants/{uuid.uuid4()}",
        json={"status": "suspended"},
        headers=_admin_headers(admin_id),
    )
    assert response.status_code == 404


async def test_status_update_invalid_value_is_unprocessable(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    admin_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_id)
    tenant_id = await _seed_tenant(
        superuser_conn, slug=f"badstatus-{uuid.uuid4().hex[:8]}", name="Bad Status Co"
    )

    response = await client.patch(
        f"/api/platform/tenants/{tenant_id}",
        json={"status": "deleted"},
        headers=_admin_headers(admin_id),
    )
    assert response.status_code == 422


async def test_non_admin_cannot_suspend(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_id = await _seed_tenant(
        superuser_conn, slug=f"protected-{uuid.uuid4().hex[:8]}", name="Protected Co"
    )

    response = await client.patch(
        f"/api/platform/tenants/{tenant_id}",
        json={"status": "suspended"},
        headers=_admin_headers(uuid.uuid4()),
    )
    assert response.status_code == 403
