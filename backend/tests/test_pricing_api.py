"""T-031: pricing_rules inline editing + catalog_items list, the tenant-admin
Pricing tab. Same JWT pattern as test_escalations_api.py.
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
    slug = f"pricing-api-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/tenants",
        json={"slug": slug, "name": "Pricing API Test Co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return token, uuid.UUID(response.json()["tenant_id"])


async def _seed_rule(
    conn: asyncpg.Connection[Any], tenant_id: uuid.UUID, *, code: str = "screen-repair-a"
) -> uuid.UUID:
    rule_id: uuid.UUID = await conn.fetchval(
        "insert into pricing_rules (tenant_id, code, label, unit_amount_cents) "
        "values ($1, $2, 'Screen repair (tier A)', 12000) returning id",
        tenant_id,
        code,
    )
    return rule_id


async def test_list_pricing_rules_returns_only_this_tenants_rows(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    other_token, other_tenant_id = await _signup_tenant_admin(client)
    await _seed_rule(superuser_conn, tenant_id)
    await _seed_rule(superuser_conn, other_tenant_id)

    response = await client.get("/api/pricing/rules", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert len(response.json()) == 1

    other_response = await client.get(
        "/api/pricing/rules", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert len(other_response.json()) == 1


async def test_update_pricing_rule_converts_dollars_to_cents(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    rule_id = await _seed_rule(superuser_conn, tenant_id)

    response = await client.patch(
        f"/api/pricing/rules/{rule_id}",
        json={"unit_amount_dollars": "12.34"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["unit_amount_cents"] == 1234

    stored = await superuser_conn.fetchval(
        "select unit_amount_cents from pricing_rules where id = $1", rule_id
    )
    assert stored == 1234


@pytest.mark.parametrize("bad_amount", ["-1", "1.999", "abc", "NaN", "1000001"])
async def test_update_pricing_rule_rejects_invalid_amounts(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any], bad_amount: str
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    rule_id = await _seed_rule(superuser_conn, tenant_id)

    response = await client.patch(
        f"/api/pricing/rules/{rule_id}",
        json={"unit_amount_dollars": bad_amount},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["code", "label", "unit"])
async def test_update_pricing_rule_rejects_blank_text_fields(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any], field: str
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    rule_id = await _seed_rule(superuser_conn, tenant_id)

    response = await client.patch(
        f"/api/pricing/rules/{rule_id}",
        json={field: "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_update_pricing_rule_duplicate_code_is_409(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    await _seed_rule(superuser_conn, tenant_id, code="rule-a")
    rule_b_id = await _seed_rule(superuser_conn, tenant_id, code="rule-b")

    response = await client.patch(
        f"/api/pricing/rules/{rule_b_id}",
        json={"code": "rule-a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 409


async def test_update_pricing_rule_empty_body_is_422(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    rule_id = await _seed_rule(superuser_conn, tenant_id)

    response = await client.patch(
        f"/api/pricing/rules/{rule_id}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_update_another_tenants_rule_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    _other_token, other_tenant_id = await _signup_tenant_admin(client)
    rule_id = await _seed_rule(superuser_conn, other_tenant_id)

    response = await client.patch(
        f"/api/pricing/rules/{rule_id}",
        json={"active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_editing_a_rule_never_changes_an_already_sent_quote(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """The deterministic-pricing hard rule's other half: a sent quote is
    frozen the instant it's created (quotes_immutable trigger, T-002/T-016) -
    editing the rule it was built from must never retroactively change it."""
    token, tenant_id = await _signup_tenant_admin(client)
    rule_id = await _seed_rule(superuser_conn, tenant_id)
    conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    line_items = [
        {
            "kind": "rule",
            "code": "screen-repair-a",
            "label": "Screen repair (tier A)",
            "quantity": 1,
            "unit_amount_cents": 12000,
            "line_total_cents": 12000,
        }
    ]
    import json

    quote_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into quotes (tenant_id, conversation_id, line_items, subtotal_cents, "
        "tax_cents, total_cents, status) "
        "values ($1, $2, $3, 12000, 0, 12000, 'sent') returning id",
        tenant_id,
        conversation_id,
        json.dumps(line_items),
    )

    response = await client.patch(
        f"/api/pricing/rules/{rule_id}",
        json={"unit_amount_dollars": "199.00"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["unit_amount_cents"] == 19900

    quote_row = await superuser_conn.fetchrow(
        "select subtotal_cents, total_cents, line_items from quotes where id = $1", quote_id
    )
    assert quote_row is not None
    assert quote_row["subtotal_cents"] == 12000
    assert quote_row["total_cents"] == 12000
    assert json.loads(quote_row["line_items"])[0]["unit_amount_cents"] == 12000

    new_rule_amount = await superuser_conn.fetchval(
        "select unit_amount_cents from pricing_rules where id = $1", rule_id
    )
    assert new_rule_amount == 19900


async def test_list_catalog_items_returns_only_this_tenants_rows(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    other_token, other_tenant_id = await _signup_tenant_admin(client)
    await superuser_conn.execute(
        "insert into catalog_items (tenant_id, name, price_cents) values ($1, 'Widget', 500)",
        tenant_id,
    )
    await superuser_conn.execute(
        "insert into catalog_items (tenant_id, name, price_cents) values ($1, 'Other', 500)",
        other_tenant_id,
    )

    response = await client.get(
        "/api/pricing/catalog", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Widget"

    other_response = await client.get(
        "/api/pricing/catalog", headers={"Authorization": f"Bearer {other_token}"}
    )
    assert len(other_response.json()) == 1


async def test_pricing_endpoints_require_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/pricing/rules")
    assert response.status_code == 401
    response = await client.get("/api/pricing/catalog")
    assert response.status_code == 401
