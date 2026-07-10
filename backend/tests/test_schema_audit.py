"""T-003: schema audit (database.md section 11).

Turns principles 1-2 of database.md section 1 into a failing test:

- every table with a ``tenant_id`` column has RLS enabled *and* forced, and at
  least a ``tenant_isolation`` policy (``tenants``/``platform_admins`` are
  special-cased: no ``tenant_id`` column, different policy names);
- every monetary-looking column matches ``%_cents`` and is integer/bigint typed,
  except the one pinned exception (``cost_logs.cost_usd``);
- no table in ``public`` lacks RLS, except ``schema_migrations`` (not application
  data - it has no tenant dimension at all).

The audit assertions live in helper functions (``_tables_missing_rls`` etc.) so the
acceptance-proof test below can reuse them against a deliberately broken scratch
table without duplicating the logic.
"""

from __future__ import annotations

import re
from typing import Any

import asyncpg
import pytest

pytestmark = pytest.mark.db

# tables carrying tenant_id are covered generically; these two carry tenant
# identity differently and get their own named-policy assertions instead.
SPECIAL_CASED_TABLES = {"tenants", "platform_admins"}

EXPECTED_TENANTS_POLICIES = {"tenant_self_read", "platform_admin_all", "service_signup_insert"}
EXPECTED_PLATFORM_ADMINS_POLICIES = {"platform_admin_only"}

# The single allowed exception to "every monetary column is *_cents integer"
# (database.md principle 2) - observability metadata, never customer-facing pricing.
ALLOWED_MONETARY_EXCEPTIONS = {("cost_logs", "cost_usd")}

# "Looks monetary": cents-suffixed columns plus the common money-ish name stems, so
# a column like cost_usd (no "cents" in it at all) still gets caught by the audit
# instead of the exception list being vacuous. Stems are deliberately broad; the
# pinned-exception mechanism absorbs any legitimate false positive.
_MONETARY_NAME_RE = re.compile(
    r"(cents|price|amount|cost|total|tax|fee|discount|refund|charge|balance|deposit"
    r"|subtotal|usd|dollar)",
    re.IGNORECASE,
)


async def _tenant_id_tables(conn: asyncpg.Connection[Any]) -> set[str]:
    rows = await conn.fetch(
        """
        select table_name from information_schema.columns
         where table_schema = 'public' and column_name = 'tenant_id'
        """
    )
    return {str(r["table_name"]) for r in rows}


async def _rls_status(conn: asyncpg.Connection[Any]) -> dict[str, tuple[bool, bool]]:
    """table_name -> (relrowsecurity, relforcerowsecurity) for every table in public."""
    rows = await conn.fetch(
        """
        select c.relname as table_name, c.relrowsecurity, c.relforcerowsecurity
          from pg_class c
          join pg_namespace n on n.oid = c.relnamespace
         where c.relkind in ('r', 'p') and n.nspname = 'public'
        """
    )
    return {
        str(r["table_name"]): (bool(r["relrowsecurity"]), bool(r["relforcerowsecurity"]))
        for r in rows
    }


async def _policy_names(conn: asyncpg.Connection[Any], table_name: str) -> set[str]:
    rows = await conn.fetch(
        "select policyname from pg_policies where schemaname = 'public' and tablename = $1",
        table_name,
    )
    return {str(r["policyname"]) for r in rows}


async def _tables_missing_rls(conn: asyncpg.Connection[Any], *, tables: set[str]) -> list[str]:
    """Tables in ``tables`` that lack RLS enabled+forced or the tenant_isolation policy."""
    rls = await _rls_status(conn)
    bad: list[str] = []
    for table in sorted(tables):
        enabled, forced = rls.get(table, (False, False))
        if not (enabled and forced):
            bad.append(f"{table}: rls enabled={enabled} forced={forced}")
            continue
        policies = await _policy_names(conn, table)
        if "tenant_isolation" not in policies:
            bad.append(f"{table}: missing tenant_isolation policy (has {sorted(policies)})")
    return bad


async def _tables_without_rls_at_all(
    conn: asyncpg.Connection[Any], *, exempt: set[str]
) -> list[str]:
    """Every table in public that has RLS off (enabled or forced), excluding exempt."""
    rls = await _rls_status(conn)
    return [
        table
        for table, (enabled, forced) in sorted(rls.items())
        if table not in exempt and not (enabled and forced)
    ]


async def _monetary_column_violations(
    conn: asyncpg.Connection[Any], *, allowed_exceptions: set[tuple[str, str]]
) -> list[str]:
    """Columns that look monetary but aren't ``%_cents`` integer/bigint, minus exceptions."""
    rows = await conn.fetch(
        """
        select table_name, column_name, data_type
          from information_schema.columns
         where table_schema = 'public'
        """
    )
    bad: list[str] = []
    for r in rows:
        table_name, column_name, data_type = (
            str(r["table_name"]),
            str(r["column_name"]),
            str(r["data_type"]),
        )
        if not _MONETARY_NAME_RE.search(column_name):
            continue
        if (table_name, column_name) in allowed_exceptions:
            continue
        if not column_name.endswith("_cents") or data_type not in ("integer", "bigint"):
            bad.append(f"{table_name}.{column_name} ({data_type})")
    return bad


async def test_every_tenant_id_table_has_rls_enabled_forced_and_tenant_isolation(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tables = await _tenant_id_tables(superuser_conn)
    assert tables, "expected at least one table with a tenant_id column"
    assert tables.isdisjoint(SPECIAL_CASED_TABLES)
    bad = await _tables_missing_rls(superuser_conn, tables=tables)
    assert not bad, f"tenant_id tables failing the audit: {bad}"


async def test_tenants_table_has_its_special_cased_policies(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    enabled, forced = (await _rls_status(superuser_conn))["tenants"]
    assert enabled and forced
    assert await _policy_names(superuser_conn, "tenants") == EXPECTED_TENANTS_POLICIES


async def test_platform_admins_table_has_its_special_cased_policy(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    enabled, forced = (await _rls_status(superuser_conn))["platform_admins"]
    assert enabled and forced
    assert await _policy_names(superuser_conn, "platform_admins") == (
        EXPECTED_PLATFORM_ADMINS_POLICIES
    )


async def test_monetary_columns_are_cents_integers_except_the_one_pinned_exception(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    # Pin the exception explicitly, per the ticket: prove it exists and is exactly
    # this one column, not just "whatever the exclusion set happens to contain".
    exception_row = await superuser_conn.fetchrow(
        """
        select data_type from information_schema.columns
         where table_schema = 'public' and table_name = 'cost_logs' and column_name = 'cost_usd'
        """
    )
    assert exception_row is not None, "cost_logs.cost_usd must exist to be the pinned exception"
    assert exception_row["data_type"] == "numeric"

    bad = await _monetary_column_violations(
        superuser_conn, allowed_exceptions=ALLOWED_MONETARY_EXCEPTIONS
    )
    assert not bad, f"monetary columns not '%_cents' integer/bigint: {bad}"


async def test_no_table_lacks_rls_except_schema_migrations(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    bad = await _tables_without_rls_at_all(superuser_conn, exempt={"schema_migrations"})
    assert not bad, f"tables with RLS not enabled+forced: {bad}"


async def test_audit_catches_a_tenant_id_table_with_no_rls(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Acceptance proof: the audit helpers actually fail on a real violation.

    Creates a scratch table with a tenant_id column and no RLS, asserts both audit
    helpers flag it, then drops it - proving the audit isn't vacuously passing
    without leaving anything behind.
    """
    await superuser_conn.execute(
        """
        create table schema_audit_scratch_violation (
          id uuid primary key default gen_random_uuid(),
          tenant_id uuid not null
        )
        """
    )
    try:
        tables = await _tenant_id_tables(superuser_conn)
        assert "schema_audit_scratch_violation" in tables

        missing_rls = await _tables_missing_rls(superuser_conn, tables=tables)
        assert any("schema_audit_scratch_violation" in entry for entry in missing_rls), (
            f"audit failed to catch the scratch violation: {missing_rls}"
        )

        no_rls_at_all = await _tables_without_rls_at_all(
            superuser_conn, exempt={"schema_migrations"}
        )
        assert "schema_audit_scratch_violation" in no_rls_at_all
    finally:
        await superuser_conn.execute("drop table if exists schema_audit_scratch_violation")

    # And the artifact is really gone.
    tables_after = await _tenant_id_tables(superuser_conn)
    assert "schema_audit_scratch_violation" not in tables_after
