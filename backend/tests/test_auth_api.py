"""T-004: Supabase auth + tenant-context middleware, exercised at the API level.

Uses httpx's ``ASGITransport`` against the real app (no lifespan - the app pool is
created/closed by the ``client`` fixture below, pointed at ``wren_test`` via the
wren_app-role DSN from ``tests.conftest._app_dsn_for``, matching test_rls.py's
pattern). JWTs are minted locally with a fixed test secret injected into
``Settings`` before any code path can call the lru_cached ``get_settings()`` with
the real (empty, in ``.env``) one.
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
    """Force a known SUPABASE_JWT_SECRET for every test in this module.

    ``get_settings`` is ``lru_cache``d process-wide, so setting the env var alone
    is not enough if some earlier test already triggered a cache hit with the
    real (empty) value from .env - clearing the cache here, before and after,
    makes this robust to test ordering.
    """
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
    """A wren_app pool pointed at wren_test, plus an httpx client for the real app.

    ``ASGITransport`` does not send ASGI lifespan events, so ``app``'s lifespan
    (app/main.py) never runs here and never double-creates the pool this fixture
    owns; it is closed unconditionally in the finally block.
    """
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await db.close_pool()


def _make_token(
    user_id: uuid.UUID,
    *,
    secret: str = TEST_JWT_SECRET,
    audience: str = "authenticated",
    expires_in: int = 3600,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "aud": audience,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def _signup(client: httpx.AsyncClient, *, token: str, slug: str, name: str) -> httpx.Response:
    return await client.post(
        "/api/tenants",
        json={"slug": slug, "name": name},
        headers={"Authorization": f"Bearer {token}"},
    )


async def _insert_platform_admin(conn: asyncpg.Connection[Any], user_id: uuid.UUID) -> None:
    """Bootstrap a platform_admins row per database.md's bootstrap note: platform_admins
    is FORCE RLS'd platform-admin-only, so even the migrating connection needs the
    app.role setting to satisfy the policy's with-check."""
    async with conn.transaction():
        await conn.execute("select set_config('app.role', 'platform_admin', true)")
        await conn.execute("insert into platform_admins (user_id) values ($1)", user_id)


# --- signup -------------------------------------------------------------------


async def test_signup_happy_path_creates_all_three_rows(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    user_id = uuid.uuid4()
    token = _make_token(user_id)
    slug = f"signup-{uuid.uuid4().hex[:8]}"

    response = await _signup(client, token=token, slug=slug, name="Signup Co")
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == slug
    tenant_id = uuid.UUID(body["tenant_id"])

    tenant_row = await superuser_conn.fetchrow(
        "select slug, name, status from tenants where id = $1", tenant_id
    )
    assert tenant_row is not None
    assert tenant_row["slug"] == slug
    assert tenant_row["status"] == "active"

    config_row = await superuser_conn.fetchrow(
        "select tenant_id from tenant_config where tenant_id = $1", tenant_id
    )
    assert config_row is not None

    user_row = await superuser_conn.fetchrow(
        "select tenant_id, role from users where id = $1", user_id
    )
    assert user_row is not None
    assert user_row["tenant_id"] == tenant_id
    assert user_row["role"] == "owner"


async def test_signup_duplicate_slug_is_conflict(client: httpx.AsyncClient) -> None:
    slug = f"dup-slug-{uuid.uuid4().hex[:8]}"
    first = await _signup(client, token=_make_token(uuid.uuid4()), slug=slug, name="First")
    assert first.status_code == 201

    second = await _signup(client, token=_make_token(uuid.uuid4()), slug=slug, name="Second")
    assert second.status_code == 409


async def test_signup_same_user_twice_is_conflict(client: httpx.AsyncClient) -> None:
    token = _make_token(uuid.uuid4())
    first = await _signup(client, token=token, slug=f"once-{uuid.uuid4().hex[:8]}", name="Once")
    assert first.status_code == 201

    second = await _signup(client, token=token, slug=f"twice-{uuid.uuid4().hex[:8]}", name="Twice")
    assert second.status_code == 409


@pytest.mark.parametrize("bad_slug", ["ab", "Has-Upper", "-leading-dash", "has_underscore"])
async def test_signup_bad_slug_is_unprocessable(client: httpx.AsyncClient, bad_slug: str) -> None:
    response = await _signup(
        client, token=_make_token(uuid.uuid4()), slug=bad_slug, name="Bad Slug Co"
    )
    assert response.status_code == 422


async def test_signup_no_token_is_unauthorized(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/tenants", json={"slug": f"notoken-{uuid.uuid4().hex[:8]}", "name": "No Token"}
    )
    assert response.status_code == 401


async def test_signup_garbage_token_is_unauthorized(client: httpx.AsyncClient) -> None:
    response = await _signup(
        client, token="not-a-real-jwt", slug=f"garbage-{uuid.uuid4().hex[:8]}", name="Garbage"
    )
    assert response.status_code == 401


async def test_signup_expired_token_is_unauthorized(client: httpx.AsyncClient) -> None:
    token = _make_token(uuid.uuid4(), expires_in=-3600)
    response = await _signup(
        client, token=token, slug=f"expired-{uuid.uuid4().hex[:8]}", name="Expired"
    )
    assert response.status_code == 401


async def test_signup_token_without_exp_is_unauthorized(client: httpx.AsyncClient) -> None:
    # PyJWT only validates exp when the claim is present; verify_token requires it
    # so a token minted without one is never a forever-valid credential.
    payload = {"sub": str(uuid.uuid4()), "aud": "authenticated", "iat": int(time.time())}
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    response = await _signup(
        client, token=token, slug=f"noexp-{uuid.uuid4().hex[:8]}", name="No Exp"
    )
    assert response.status_code == 401


async def test_signup_wrong_audience_token_is_unauthorized(client: httpx.AsyncClient) -> None:
    token = _make_token(uuid.uuid4(), audience="not-authenticated")
    response = await _signup(
        client, token=token, slug=f"wrongaud-{uuid.uuid4().hex[:8]}", name="Wrong Audience"
    )
    assert response.status_code == 401


# --- tenant isolation at the API level ------------------------------------------


async def test_tenant_admin_me_is_isolated_per_tenant(client: httpx.AsyncClient) -> None:
    token_a = _make_token(uuid.uuid4())
    token_b = _make_token(uuid.uuid4())
    slug_a = f"me-a-{uuid.uuid4().hex[:8]}"
    slug_b = f"me-b-{uuid.uuid4().hex[:8]}"

    signup_a = await _signup(client, token=token_a, slug=slug_a, name="Tenant A")
    signup_b = await _signup(client, token=token_b, slug=slug_b, name="Tenant B")
    assert signup_a.status_code == 201
    assert signup_b.status_code == 201
    tenant_a_id = signup_a.json()["tenant_id"]
    tenant_b_id = signup_b.json()["tenant_id"]

    me_a = await client.get("/api/tenants/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me_a.status_code == 200
    assert me_a.json() == {"tenant_id": tenant_a_id, "slug": slug_a, "name": "Tenant A"}
    assert me_a.json()["tenant_id"] != tenant_b_id

    me_b = await client.get("/api/tenants/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_b.status_code == 200
    assert me_b.json() == {"tenant_id": tenant_b_id, "slug": slug_b, "name": "Tenant B"}


async def test_tenant_admin_me_with_no_users_row_is_forbidden(client: httpx.AsyncClient) -> None:
    token = _make_token(uuid.uuid4())  # never signed up
    response = await client.get("/api/tenants/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


# --- platform admin --------------------------------------------------------------


async def test_platform_ping_requires_platform_admin(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_user_id = uuid.uuid4()
    tenant_token = _make_token(tenant_user_id)
    signup = await _signup(
        client, token=tenant_token, slug=f"notadmin-{uuid.uuid4().hex[:8]}", name="Not Admin"
    )
    assert signup.status_code == 201

    forbidden = await client.get(
        "/api/platform/ping", headers={"Authorization": f"Bearer {tenant_token}"}
    )
    assert forbidden.status_code == 403

    admin_user_id = uuid.uuid4()
    await _insert_platform_admin(superuser_conn, admin_user_id)
    admin_token = _make_token(admin_user_id)

    ok = await client.get("/api/platform/ping", headers={"Authorization": f"Bearer {admin_token}"})
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}
