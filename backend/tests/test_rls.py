"""T-003: RLS enforcement - the leakage test (database.md sections 2.2, 2.3, 11).

Seeds two tenants (A, B) with one row in every tenant-scoped table, then proves,
as the unprivileged ``wren_app`` role:

1. a tenant_admin scoped to A sees only A's rows, everywhere;
2. no tenant context (customer, tenant_id=None) sees nothing;
3. the one sanctioned RLS bypass - resolve_tenant_slug - never exposes more than
   its four documented columns, for either tenant's slug;
4. ``tenant_context`` refuses an unrecognized role;
5. a cross-tenant write (inserting a B-tenanted row while scoped to A) is rejected
   by the ``tenant_isolation`` policy's ``with check``, not merely filtered on read.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio

from app.core import db
from app.core.config import get_settings

pytestmark = pytest.mark.db


@dataclass(frozen=True)
class SeedTenants:
    a_id: uuid.UUID
    a_slug: str
    b_id: uuid.UUID
    b_slug: str


async def _seed_tenant(conn: asyncpg.Connection[Any], slug: str, name: str) -> uuid.UUID:
    """Insert one row into every tenant-scoped table for a fresh tenant, respecting
    FKs (including the composite (tenant_id, id) FKs on messages/tool_calls/quotes/
    escalations - database.md section 6)."""
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, $2) returning id", slug, name
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    await conn.execute(
        "insert into users (id, tenant_id, role) values (gen_random_uuid(), $1, 'owner')",
        tenant_id,
    )
    document_id: uuid.UUID = await conn.fetchval(
        """
        insert into documents (tenant_id, filename, doc_type, status)
        values ($1, 'policy.pdf', 'policy', 'ready')
        returning id
        """,
        tenant_id,
    )
    # embedding passed as a literal (not a bound param) - asyncpg has no built-in
    # pgvector codec, and NULL is an explicitly allowed value for this column.
    await conn.execute(
        """
        insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata)
        values ($1, $2, 'seed content', null, '{}')
        """,
        tenant_id,
        document_id,
    )
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id, customer_ref) values ($1, 'seed-customer') "
        "returning id",
        tenant_id,
    )
    message_id: uuid.UUID = await conn.fetchval(
        """
        insert into messages (tenant_id, conversation_id, role, content)
        values ($1, $2, 'customer', 'hello') returning id
        """,
        tenant_id,
        conversation_id,
    )
    await conn.execute(
        """
        insert into tool_calls (tenant_id, message_id, tool_name, success)
        values ($1, $2, 'search_knowledge', true)
        """,
        tenant_id,
        message_id,
    )
    await conn.execute(
        "insert into catalog_items (tenant_id, name, price_cents) values ($1, 'Widget', 500)",
        tenant_id,
    )
    await conn.execute(
        """
        insert into pricing_rules (tenant_id, code, label, unit_amount_cents)
        values ($1, 'seed-rule', 'Seed Rule', 1000)
        """,
        tenant_id,
    )
    await conn.execute(
        """
        insert into quotes (tenant_id, conversation_id, line_items,
                            subtotal_cents, tax_cents, total_cents)
        values ($1, $2, '[]', 1000, 100, 1100)
        """,
        tenant_id,
        conversation_id,
    )
    await conn.execute(
        """
        insert into orders (tenant_id, ref_code, kind, status)
        values ($1, 'R-1', 'repair', 'open')
        """,
        tenant_id,
    )
    await conn.execute(
        "insert into escalations (tenant_id, conversation_id, reason) values ($1, $2, 'seed')",
        tenant_id,
        conversation_id,
    )
    await conn.execute(
        """
        insert into eval_cases (tenant_id, case_type, input, expected)
        values ($1, 'retrieval', '{}', '{}')
        """,
        tenant_id,
    )
    await conn.execute(
        "insert into eval_runs (tenant_id, run_type, metrics) values ($1, 'retrieval', '{}')",
        tenant_id,
    )
    await conn.execute(
        "insert into cost_logs (tenant_id, conversation_id, model) values ($1, $2, 'gpt-4o-mini')",
        tenant_id,
        conversation_id,
    )
    return tenant_id


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seeded_tenants(migrated_db: str) -> SeedTenants:
    """Seed tenants A/B once for the whole session, on migrated_db's session loop.

    All awaiting happens before this returns (nothing awaited afterwards), the same
    discipline conftest.py's ``migrated_db`` follows, so the plain data returned
    (ids/slugs) is safe to reuse from tests running on their own per-function loops.
    """
    conn = await asyncpg.connect(migrated_db)
    try:
        a_slug, b_slug = "t003-rls-tenant-a", "t003-rls-tenant-b"
        a_id = await _seed_tenant(conn, a_slug, "RLS Tenant A")
        b_id = await _seed_tenant(conn, b_slug, "RLS Tenant B")
    finally:
        await conn.close()
    return SeedTenants(a_id=a_id, a_slug=a_slug, b_id=b_id, b_slug=b_slug)


def _app_dsn_for(base_dsn: str) -> str:
    """The same database as ``base_dsn``, but as the wren_app role.

    Swaps credentials only (host/port/dbname come from ``base_dsn``, i.e. from
    ``migrated_db`` - so this always targets wren_test, never the dev database);
    the password comes from settings, never hardcoded.
    """
    settings = get_settings()
    parts = urlsplit(base_dsn)
    netloc = f"wren_app:{quote(settings.wren_app_db_password, safe='')}@{parts.hostname}"
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@pytest_asyncio.fixture
async def app_pool(migrated_db: str) -> AsyncIterator[db.AppPool]:
    """A wren_app pool against wren_test, fresh per test (own event loop, own pool)."""
    pool = await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        yield pool
    finally:
        await db.close_pool()


async def _tenant_scoped_tables(conn: asyncpg.Connection[Any]) -> list[tuple[str, str]]:
    """(table_name, tenant-identifier column) for every tenant-scoped table.

    Derived from information_schema rather than hardcoded, so a table added later
    is automatically covered. ``tenants`` is special-cased: it carries no tenant_id
    column, its own ``id`` *is* the tenant identifier (database.md section 3).
    """
    rows = await conn.fetch(
        """
        select table_name from information_schema.columns
         where table_schema = 'public' and column_name = 'tenant_id'
         order by table_name
        """
    )
    tables = [(str(r["table_name"]), "tenant_id") for r in rows]
    tables.append(("tenants", "id"))
    return tables


async def test_tenant_admin_sees_only_own_tenant_everywhere(
    superuser_conn: asyncpg.Connection[Any],
    app_pool: db.AppPool,
    seeded_tenants: SeedTenants,
) -> None:
    tables = await _tenant_scoped_tables(superuser_conn)
    assert len(tables) == 16, f"expected 16 tenant-scoped tables, found {len(tables)}: {tables}"

    async with db.tenant_context(seeded_tenants.a_id, "tenant_admin", pool=app_pool) as conn:
        for table, id_col in tables:
            rows = await conn.fetch(f"select {id_col} from {table}")
            ids = {r[id_col] for r in rows}
            assert ids, f"{table}: expected tenant A's seeded row to be visible"
            assert ids == {seeded_tenants.a_id}, f"{table}: leaked non-A rows: {ids}"


async def test_no_tenant_context_returns_zero_rows_everywhere(
    superuser_conn: asyncpg.Connection[Any],
    app_pool: db.AppPool,
    seeded_tenants: SeedTenants,  # ensure data exists to *not* see
) -> None:
    tables = await _tenant_scoped_tables(superuser_conn)
    async with db.tenant_context(None, "customer", pool=app_pool) as conn:
        for table, id_col in tables:
            rows = await conn.fetch(f"select {id_col} from {table}")
            assert rows == [], f"{table}: expected zero rows with no tenant context, got {rows}"


async def test_resolver_exposes_only_the_four_public_columns(
    app_pool: db.AppPool,
    seeded_tenants: SeedTenants,
) -> None:
    """Fishing through the one sanctioned RLS bypass, with no tenant context at all."""
    async with app_pool.acquire() as conn:
        for slug, tenant_id in (
            (seeded_tenants.a_slug, seeded_tenants.a_id),
            (seeded_tenants.b_slug, seeded_tenants.b_id),
        ):
            row = await conn.fetchrow("select * from resolve_tenant_slug($1)", slug)
            assert row is not None
            assert set(row.keys()) == {"id", "name", "status", "brand"}, (
                f"resolver leaked columns beyond the public four for slug {slug!r}: "
                f"{set(row.keys())}"
            )
            assert row["id"] == tenant_id


async def test_tenant_context_rejects_invalid_role(
    app_pool: db.AppPool,
    seeded_tenants: SeedTenants,
) -> None:
    with pytest.raises(ValueError, match="invalid role"):
        async with db.tenant_context(seeded_tenants.a_id, "superuser", pool=app_pool):
            pass


async def test_cross_tenant_insert_is_rejected_by_rls(
    app_pool: db.AppPool,
    seeded_tenants: SeedTenants,
) -> None:
    """Write isolation: RLS's with-check, not just the read-side filter."""
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError, match="row-level security"):
        async with db.tenant_context(seeded_tenants.a_id, "tenant_admin", pool=app_pool) as conn:
            await conn.execute(
                "insert into catalog_items (tenant_id, name) values ($1, 'leaked-in')",
                seeded_tenants.b_id,
            )


@pytest_asyncio.fixture
async def single_conn_pool(migrated_db: str) -> AsyncIterator[db.AppPool]:
    """A max_size=1 wren_app pool: every acquire returns the same physical connection,
    which is exactly what the pool-reuse leak tests need."""
    pool = await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=1)
    try:
        yield pool
    finally:
        await db.close_pool()


async def _assert_connection_carries_no_tenant_context(
    pool: db.AppPool, expected_pid: int, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tables = await _tenant_scoped_tables(superuser_conn)
    async with pool.acquire() as conn:
        pid: int = await conn.fetchval("select pg_backend_pid()")
        assert pid == expected_pid, "expected the same physical connection to be reused"
        tenant_setting = await conn.fetchval("select current_setting('app.tenant_id', true)")
        role_setting = await conn.fetchval("select current_setting('app.role', true)")
        assert tenant_setting in (None, ""), (
            f"app.tenant_id leaked across release: {tenant_setting}"
        )
        assert role_setting in (None, ""), f"app.role leaked across release: {role_setting}"
        for table, id_col in tables:
            rows = await conn.fetch(f"select {id_col} from {table}")
            assert rows == [], f"{table}: rows visible on a released connection: {rows}"


async def test_tenant_context_does_not_leak_across_pool_reuse_after_commit(
    superuser_conn: asyncpg.Connection[Any],
    single_conn_pool: db.AppPool,
    seeded_tenants: SeedTenants,
) -> None:
    """The primary threat model: a pooled connection previously scoped to tenant A must
    carry nothing over when reused. Would catch set_config(..., false) or the settings
    being applied outside the transaction."""
    async with db.tenant_context(seeded_tenants.a_id, "tenant_admin", pool=single_conn_pool) as c:
        pid: int = await c.fetchval("select pg_backend_pid()")
        assert await c.fetchval("select count(*) from catalog_items") == 1  # context works
    await _assert_connection_carries_no_tenant_context(single_conn_pool, pid, superuser_conn)


async def test_tenant_context_does_not_leak_across_pool_reuse_after_rollback(
    superuser_conn: asyncpg.Connection[Any],
    single_conn_pool: db.AppPool,
    seeded_tenants: SeedTenants,
) -> None:
    pid = 0
    with pytest.raises(RuntimeError, match="boom"):
        async with db.tenant_context(
            seeded_tenants.a_id, "tenant_admin", pool=single_conn_pool
        ) as c:
            pid = await c.fetchval("select pg_backend_pid()")
            raise RuntimeError("boom")
    await _assert_connection_carries_no_tenant_context(single_conn_pool, pid, superuser_conn)
