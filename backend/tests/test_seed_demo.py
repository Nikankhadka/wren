"""Tests for the demo world seed (seeds/seed_demo.py).

Runs GoTrue-free: ``create_auth_user`` is a fake returning deterministic UUIDs
(uuid5 by email), and the embedder is ZeroEmbedder - so the full seed exercises
its real DB code path against wren_test without any external service. Mirrors
test_seed_tenant1.py's pool/migrated_db pattern.

The cost-attribution test drives the REAL ``GET /api/conversations/{id}``
endpoint via httpx's ASGITransport (test_auth_api's pattern) with a locally
minted tenant-admin token, proving the seeded cost_logs attribute to assistant
messages through the same lateral-join shape the console renders.
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
from seeds import seed_demo
from seeds.seed_tenant1_phoneshop import SLUG as BYTEFIX_SLUG
from tests.conftest import _app_dsn_for
from tests.fakes import ZeroEmbedder

pytestmark = pytest.mark.db

TEST_JWT_SECRET = "test-only-supabase-jwt-secret-do-not-use-in-prod"  # noqa: S105

_FAKE_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "wren-demo-seed")


async def _fake_create_auth_user(email: str, password: str) -> uuid.UUID:
    """Deterministic UUID per email - no GoTrue, no network."""
    return uuid.uuid5(_FAKE_NS, email)


@pytest.fixture(autouse=True)
def _supabase_jwt_secret_env() -> Iterator[None]:
    """Force a known JWT secret for the cost-attribution test's minted token.

    ``get_settings`` is lru_cached, so clear it before/after to stay robust to
    test ordering (same pattern as test_auth_api).
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
async def app_pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        yield
    finally:
        await db.close_pool()


@pytest_asyncio.fixture
async def seeded(app_pool: None) -> AsyncIterator[dict[str, uuid.UUID]]:
    ids = await seed_demo.seed(embedder=ZeroEmbedder(), create_auth_user=_fake_create_auth_user)
    yield ids


def _make_token(user_id: uuid.UUID) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "aud": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


@pytest_asyncio.fixture
async def client(app_pool: None) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- both tenants + data --------------------------------------------------------


async def test_both_tenants_exist_with_data(
    seeded: dict[str, uuid.UUID], superuser_conn: asyncpg.Connection[Any]
) -> None:
    bytefix_id = seeded["bytefix_id"]
    lumident_id = seeded["lumident_id"]

    lumident_catalog_n = len(seed_demo.LUMIDENT_CATALOG)
    lumident_rules_n = len(seed_demo.LUMIDENT_PRICING_RULES)
    for tenant_id, slug, catalog_n, rules_n in [
        (bytefix_id, BYTEFIX_SLUG, 15, 12),
        (lumident_id, seed_demo.LUMIDENT_SLUG, lumident_catalog_n, lumident_rules_n),
    ]:
        row = await superuser_conn.fetchrow(
            "select slug, name from tenants where id = $1", tenant_id
        )
        assert row is not None
        assert row["slug"] == slug

        config = await superuser_conn.fetchval(
            "select config from tenant_config where tenant_id = $1", tenant_id
        )
        assert config is not None  # tenant_config row exists

        assert (
            await superuser_conn.fetchval(
                "select count(*) from catalog_items where tenant_id = $1", tenant_id
            )
            == catalog_n
        )
        assert (
            await superuser_conn.fetchval(
                "select count(*) from pricing_rules where tenant_id = $1", tenant_id
            )
            == rules_n
        )
        # Knowledge chunks ingested through the real pipeline.
        assert (
            await superuser_conn.fetchval(
                "select count(*) from knowledge_chunks where tenant_id = $1", tenant_id
            )
            > 0
        )


async def test_lumident_differs_only_in_data(
    seeded: dict[str, uuid.UUID], superuser_conn: asyncpg.Connection[Any]
) -> None:
    """Domain-agnostic proof stays data-side: lumident is dental, bytefix is
    phone repair, but both run identical code - differ only in config + docs."""
    bytefix_cfg = await superuser_conn.fetchval(
        "select config from tenant_config where tenant_id = $1", seeded["bytefix_id"]
    )
    lumident_cfg = await superuser_conn.fetchval(
        "select config from tenant_config where tenant_id = $1", seeded["lumident_id"]
    )
    # Distinct greetings + starter questions - the data-side difference.
    assert bytefix_cfg != lumident_cfg
    bytefix_names = {
        r["name"]
        for r in await superuser_conn.fetch(
            "select name from catalog_items where tenant_id = $1", seeded["bytefix_id"]
        )
    }
    lumident_names = {
        r["name"]
        for r in await superuser_conn.fetch(
            "select name from catalog_items where tenant_id = $1", seeded["lumident_id"]
        )
    }
    assert bytefix_names.isdisjoint(lumident_names)  # no overlap - two verticals


# --- membership -----------------------------------------------------------------


async def test_membership_rows(
    seeded: dict[str, uuid.UUID], superuser_conn: asyncpg.Connection[Any]
) -> None:
    bytefix_owner_row = await superuser_conn.fetchrow(
        "select tenant_id, role from users where id = $1", seeded["bytefix_owner"]
    )
    assert bytefix_owner_row is not None
    assert bytefix_owner_row["tenant_id"] == seeded["bytefix_id"]
    assert bytefix_owner_row["role"] == "owner"

    lumident_owner_row = await superuser_conn.fetchrow(
        "select tenant_id, role from users where id = $1", seeded["lumident_owner"]
    )
    assert lumident_owner_row is not None
    assert lumident_owner_row["tenant_id"] == seeded["lumident_id"]
    assert lumident_owner_row["role"] == "owner"

    admin_count = await superuser_conn.fetchval(
        "select count(*) from platform_admins where user_id = $1", seeded["founder"]
    )
    assert admin_count == 1  # the founder is a platform admin, exactly once
    # (A global platform_admins count is not asserted here: the session-shared
    # wren_test accumulates rows from other tests' _insert_platform_admin calls,
    # and the real seed deliberately only manages the founder's row - it must
    # not nuke other admins in the dev DB.)


# --- conversations, messages, tool calls, escalations ---------------------------


async def test_conversation_counts_and_statuses(
    seeded: dict[str, uuid.UUID], superuser_conn: asyncpg.Connection[Any]
) -> None:
    bytefix_statuses = {
        r["status"]: r["n"]
        for r in await superuser_conn.fetch(
            "select status, count(*) as n from conversations where tenant_id = $1 group by status",
            seeded["bytefix_id"],
        )
    }
    assert bytefix_statuses.get("closed") == 2
    assert bytefix_statuses.get("open") == 1
    assert bytefix_statuses.get("escalated") == 2

    lumident_count = await superuser_conn.fetchval(
        "select count(*) from conversations where tenant_id = $1", seeded["lumident_id"]
    )
    assert lumident_count == 2


async def test_message_ordering_strictly_increasing(
    seeded: dict[str, uuid.UUID], superuser_conn: asyncpg.Connection[Any]
) -> None:
    conv_ids = await superuser_conn.fetch(
        "select id from conversations where tenant_id = $1", seeded["bytefix_id"]
    )
    for row in conv_ids:
        times = [
            r["created_at"]
            for r in await superuser_conn.fetch(
                "select created_at from messages where conversation_id = $1 "
                "order by created_at asc",
                row["id"],
            )
        ]
        assert len(times) >= 2
        assert all(times[i] < times[i + 1] for i in range(len(times) - 1))


async def test_inspection_metadata_parseable(
    seeded: dict[str, uuid.UUID], superuser_conn: asyncpg.Connection[Any]
) -> None:
    """At least one assistant message carries the inspection shape TraceTree renders."""
    import json

    rows = await superuser_conn.fetch(
        "select metadata from messages where tenant_id = $1 and role = 'assistant' "
        "and metadata is not null",
        seeded["bytefix_id"],
    )
    found = False
    for row in rows:
        meta = json.loads(row["metadata"])
        inspection = meta.get("inspection")
        if isinstance(inspection, dict) and inspection:
            for verdict in inspection.values():
                assert isinstance(verdict, dict)
                assert "passed" in verdict
                assert isinstance(verdict["passed"], bool)
            found = True
    assert found, "no assistant message with parseable inspection metadata"


async def test_tool_calls_join_to_assistant_messages(
    seeded: dict[str, uuid.UUID], superuser_conn: asyncpg.Connection[Any]
) -> None:
    n = await superuser_conn.fetchval(
        "select count(*) from tool_calls tc "
        "join messages m on m.id = tc.message_id "
        "where tc.tenant_id = $1 and m.role = 'assistant'",
        seeded["bytefix_id"],
    )
    assert n == 3  # quoting + search_knowledge + lookup_order_or_ticket


async def test_escalation_states(
    seeded: dict[str, uuid.UUID], superuser_conn: asyncpg.Connection[Any]
) -> None:
    rows = await superuser_conn.fetch(
        "select status, resolved_at from escalations where tenant_id = $1",
        seeded["bytefix_id"],
    )
    by_status = {r["status"] for r in rows}
    assert by_status == {"open", "claimed", "resolved"}
    for r in rows:
        if r["status"] == "resolved":
            assert r["resolved_at"] is not None
        else:
            assert r["resolved_at"] is None
    # The 0011 partial unique index: at most one open escalation per conversation.
    open_dupes = await superuser_conn.fetchval(
        "select count(*) from ("
        "  select conversation_id, count(*) as n from escalations "
        "  where tenant_id = $1 and status = 'open' group by conversation_id"
        ") t where n > 1",
        seeded["bytefix_id"],
    )
    assert open_dupes == 0


async def test_resolved_escalation_has_trailing_human_agent_message(
    seeded: dict[str, uuid.UUID], superuser_conn: asyncpg.Connection[Any]
) -> None:
    conv_id = await superuser_conn.fetchval(
        "select conversation_id from escalations where tenant_id = $1 and status = 'resolved'",
        seeded["bytefix_id"],
    )
    assert conv_id is not None
    has_human = await superuser_conn.fetchval(
        "select exists(select 1 from messages where conversation_id = $1 and role = 'human_agent')",
        conv_id,
    )
    assert has_human


# --- cost attribution via the real endpoint ------------------------------------


async def test_cost_attribution_through_real_endpoint(
    seeded: dict[str, uuid.UUID],
    client: httpx.AsyncClient,
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """GET /api/conversations/{id} attributes cost_logs to assistant messages."""
    conv_id = await superuser_conn.fetchval(
        "select c.id from conversations c "
        "where c.tenant_id = $1 and exists ("
        "  select 1 from messages m where m.conversation_id = c.id and m.role = 'assistant'"
        ") and exists (select 1 from cost_logs cl where cl.conversation_id = c.id) "
        "limit 1",
        seeded["bytefix_id"],
    )
    assert conv_id is not None

    token = _make_token(seeded["bytefix_owner"])
    resp = await client.get(
        f"/api/conversations/{conv_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assistant_msgs = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert assistant_msgs, "expected at least one assistant message"
    # Every assistant message has a cost attributed (cost_logs placed in its
    # lateral-join window), and the conversation total is non-zero.
    assert all(m["cost_usd"] is not None for m in assistant_msgs)
    assert detail["total_cost_usd"] > 0


async def test_platform_tenants_table_shows_nonzero_for_both(
    seeded: dict[str, uuid.UUID],
    client: httpx.AsyncClient,
) -> None:
    """The platform surface's tenants table (admin.localhost) shows both tenants
    with non-zero conversation and cost columns - demo criterion #3."""
    token = _make_token(seeded["founder"])
    resp = await client.get("/api/platform/tenants", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    tenants = {t["slug"]: t for t in resp.json()}
    assert set(tenants) >= {BYTEFIX_SLUG, seed_demo.LUMIDENT_SLUG}
    for slug in (BYTEFIX_SLUG, seed_demo.LUMIDENT_SLUG):
        assert tenants[slug]["conversation_count"] > 0, slug
        assert tenants[slug]["cost_usd"] > 0, slug


# --- idempotency ----------------------------------------------------------------


async def test_seed_is_idempotent(app_pool: None, superuser_conn: asyncpg.Connection[Any]) -> None:
    await seed_demo.seed(embedder=ZeroEmbedder(), create_auth_user=_fake_create_auth_user)
    counts1 = await _snapshot_counts(superuser_conn)
    await seed_demo.seed(embedder=ZeroEmbedder(), create_auth_user=_fake_create_auth_user)
    counts2 = await _snapshot_counts(superuser_conn)
    assert counts1 == counts2

    # Exactly one tenant per slug (wipes, not duplicates), and the founder is
    # a platform admin exactly once (global count not asserted - session-shared
    # wren_test accumulates other tests' admin rows, and the real seed only
    # manages the founder's row by design).
    for slug in (BYTEFIX_SLUG, seed_demo.LUMIDENT_SLUG):
        assert (
            await superuser_conn.fetchval("select count(*) from tenants where slug = $1", slug) == 1
        )
    founder_id = uuid.uuid5(_FAKE_NS, seed_demo.FOUNDER_EMAIL)
    assert (
        await superuser_conn.fetchval(
            "select count(*) from platform_admins where user_id = $1", founder_id
        )
        == 1
    )


async def _snapshot_counts(conn: asyncpg.Connection[Any]) -> dict[str, int]:
    rows = await conn.fetch(
        "select (select count(*) from tenants) as tenants, "
        "(select count(*) from users) as users, "
        "(select count(*) from platform_admins) as platform_admins, "
        "(select count(*) from conversations) as conversations, "
        "(select count(*) from messages) as messages, "
        "(select count(*) from tool_calls) as tool_calls, "
        "(select count(*) from cost_logs) as cost_logs, "
        "(select count(*) from escalations) as escalations"
    )
    return {k: int(v) for k, v in dict(rows[0]).items()}
