"""T-002: the migration runner applies 0001-0008 to a fresh database, idempotently."""

from __future__ import annotations

from typing import Any

import asyncpg
import pytest

from app.core.migrate import MIGRATIONS_DIR, run_migrations

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "tenants",
    "tenant_config",
    "users",
    "platform_admins",
    "documents",
    "knowledge_chunks",
    "conversations",
    "messages",
    "tool_calls",
    "catalog_items",
    "pricing_rules",
    "quotes",
    "orders",
    "escalations",
    "eval_cases",
    "eval_runs",
    "cost_logs",
}


async def test_all_migrations_recorded(superuser_conn: asyncpg.Connection[Any]) -> None:
    on_disk = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
    # 0001-0008 per phase 1 (T-002); 0009 adds T-004's auth pre-context
    # resolvers; 0010 retargets embeddings to the 384-dim provider-agnostic
    # contract.
    assert len(on_disk) == 10, "expected migrations 0001-0010"
    applied = await superuser_conn.fetch("select version from schema_migrations order by version")
    assert [r["version"] for r in applied] == on_disk


async def test_rerun_is_idempotent(migrated_db: str) -> None:
    assert await run_migrations(migrated_db) == []


async def test_every_designed_table_exists(superuser_conn: asyncpg.Connection[Any]) -> None:
    rows = await superuser_conn.fetch("select tablename from pg_tables where schemaname = 'public'")
    tables = {r["tablename"] for r in rows}
    missing = EXPECTED_TABLES - tables
    assert not missing, f"tables missing from migrations: {missing}"


async def test_rls_enabled_and_forced_everywhere(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    rows = await superuser_conn.fetch(
        """
        select relname, relrowsecurity, relforcerowsecurity
          from pg_class
         where relkind = 'r' and relnamespace = 'public'::regnamespace
           and relname <> 'schema_migrations'
        """
    )
    bad = [r["relname"] for r in rows if not (r["relrowsecurity"] and r["relforcerowsecurity"])]
    assert not bad, f"RLS not enabled+forced on: {bad}"


async def test_wren_app_role_has_no_bypassrls(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    row = await superuser_conn.fetchrow(
        "select rolbypassrls, rolsuper, rolcanlogin from pg_roles where rolname = 'wren_app'"
    )
    assert row is not None, "wren_app role missing"
    assert not row["rolbypassrls"] and not row["rolsuper"] and row["rolcanlogin"]


async def test_resolver_role_and_function_surface(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Pin the single sanctioned RLS bypass: role shape, ownership, ACL, column set."""
    role = await superuser_conn.fetchrow(
        "select rolcanlogin, rolbypassrls, rolsuper from pg_roles where rolname = 'wren_resolver'"
    )
    assert role is not None, "wren_resolver role missing"
    assert not role["rolcanlogin"] and role["rolbypassrls"] and not role["rolsuper"]

    fn = await superuser_conn.fetchrow(
        """
        select p.proowner::regrole::text as owner, p.prosecdef, p.proacl::text as acl
          from pg_proc p
         where p.proname = 'resolve_tenant_slug'
        """
    )
    assert fn is not None, "resolve_tenant_slug missing"
    assert fn["owner"] == "wren_resolver"
    assert fn["prosecdef"], "resolver must be SECURITY DEFINER"
    acl = fn["acl"] or ""
    assert "wren_app=X" in acl, "wren_app must keep EXECUTE"
    assert "=X/" not in acl.replace("wren_app=X/", "").replace("wren_resolver=X/", ""), (
        f"PUBLIC must not hold EXECUTE on the resolver: {acl}"
    )

    tenant_id = await superuser_conn.fetchval(
        """
        insert into tenants (slug, name) values ('t002-resolver', 'Resolver Probe')
        on conflict (slug) do update set name = excluded.name
        returning id
        """
    )
    row = await superuser_conn.fetchrow("select * from resolve_tenant_slug('t002-resolver')")
    assert row is not None
    assert set(row.keys()) == {"id", "name", "status", "brand"}, (
        "resolver must return exactly its four public columns"
    )
    await superuser_conn.execute("delete from tenants where id = $1", tenant_id)


async def test_wren_app_cannot_delete_quotes(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Quotes are tamper-proof records: the app role holds no DELETE privilege."""
    can_delete = await superuser_conn.fetchval(
        "select has_table_privilege('wren_app', 'quotes', 'delete')"
    )
    assert can_delete is False


async def test_quotes_total_check_rejects_mismatch(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Spot-check a CHECK constraint: total_cents must equal subtotal + tax."""
    tenant_id = await superuser_conn.fetchval(
        """
        insert into tenants (slug, name) values ('t002-check', 'T002')
        on conflict (slug) do update set name = excluded.name
        returning id
        """
    )
    conv = await superuser_conn.fetchrow(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    assert conv is not None
    with pytest.raises(asyncpg.CheckViolationError):
        await superuser_conn.execute(
            """
            insert into quotes (tenant_id, conversation_id, line_items,
                                subtotal_cents, tax_cents, total_cents)
            values ($1, $2, '[]', 1000, 100, 9999)
            """,
            tenant_id,
            conv["id"],
        )
    await superuser_conn.execute("delete from tenants where id = $1", tenant_id)


async def test_quote_immutability_trigger(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await superuser_conn.fetchval(
        """
        insert into tenants (slug, name) values ('t002-immutable', 'T002')
        on conflict (slug) do update set name = excluded.name
        returning id
        """
    )
    conv = await superuser_conn.fetchrow(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    assert conv is not None
    quote = await superuser_conn.fetchrow(
        """
        insert into quotes (tenant_id, conversation_id, line_items,
                            subtotal_cents, tax_cents, total_cents)
        values ($1, $2, '[]', 1000, 100, 1100) returning id
        """,
        tenant_id,
        conv["id"],
    )
    assert quote is not None
    # amounts are frozen
    with pytest.raises(asyncpg.RaiseError, match="immutable"):
        await superuser_conn.execute(
            "update quotes set subtotal_cents = 1, tax_cents = 0, total_cents = 1 where id = $1",
            quote["id"],
        )
    # legal status walk: draft -> sent -> expired
    await superuser_conn.execute("update quotes set status = 'sent' where id = $1", quote["id"])
    await superuser_conn.execute("update quotes set status = 'expired' where id = $1", quote["id"])
    # illegal transition
    with pytest.raises(asyncpg.RaiseError, match="status transition"):
        await superuser_conn.execute(
            "update quotes set status = 'draft' where id = $1", quote["id"]
        )
    await superuser_conn.execute("delete from tenants where id = $1", tenant_id)
