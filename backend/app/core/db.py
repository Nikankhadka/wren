"""The wren_app connection pool and the tenant-context contract.

The backend's only DB identity is the ``wren_app`` role (database.md section 2.1);
every query must run through a pooled connection that has had two transaction-local
settings applied first (section 2.2), which the RLS policies read via
``app_tenant_id()`` / ``app_is_platform_admin()`` / ``app_is_service()``:

    select set_config('app.tenant_id', :tenant_id, true);  -- '' when none resolved
    select set_config('app.role',      :role,      true);

``tenant_context`` is the single place that sets those two values, inside a
transaction, so RLS is never accidentally left off for a connection reused later
from the pool.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import asyncpg

from app.core.config import get_settings

if TYPE_CHECKING:
    # asyncpg.Pool/PoolConnectionProxy are only generic at the type-stub level
    # (asyncpg-stubs); subscripting them is a TypeError at runtime, so these
    # aliases exist purely for annotations, which `from __future__ import
    # annotations` above keeps lazy (never evaluated at runtime).
    from asyncpg.pool import PoolConnectionProxy

    AppPool = asyncpg.Pool[asyncpg.Record]
    AppConnection = PoolConnectionProxy[asyncpg.Record]

VALID_ROLES = frozenset({"customer", "tenant_admin", "platform_admin", "service"})

_pool: AppPool | None = None


async def create_pool(
    dsn: str | None = None,
    *,
    min_size: int = 1,
    max_size: int = 10,
) -> AppPool:
    """Create the module-level ``wren_app`` pool and store it for ``get_pool()``.

    ``dsn`` defaults to ``get_settings().app_database_url`` (the wren_app-role DSN);
    tests override it to point at the ``wren_test`` database. Call ``close_pool()``
    before creating a new one to avoid leaking the previous pool's connections.
    """
    global _pool
    if _pool is not None:
        raise RuntimeError("db pool already initialized; call close_pool() first")
    resolved_dsn = dsn if dsn is not None else get_settings().app_database_url
    _pool = await asyncpg.create_pool(resolved_dsn, min_size=min_size, max_size=max_size)
    return _pool


async def close_pool() -> None:
    """Close the module-level pool, if one was created. Idempotent."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> AppPool:
    """The module-level pool created by ``create_pool()``.

    Raises ``RuntimeError`` if no pool has been created yet (e.g. app startup
    didn't run, or a test forgot to call ``create_pool``).
    """
    if _pool is None:
        raise RuntimeError("db pool not initialized; call create_pool() first")
    return _pool


@asynccontextmanager
async def tenant_context(
    tenant_id: uuid.UUID | str | None,
    role: str,
    *,
    pool: AppPool | None = None,
) -> AsyncIterator[AppConnection]:
    """Acquire a pooled connection scoped to ``tenant_id``/``role`` for one transaction.

    Sets the two transaction-local settings RLS policies read (database.md section
    2.2), then yields the connection. The transaction commits on normal exit and
    rolls back on exception; the connection is always released back to the pool.

    ``tenant_id`` of ``None`` clears tenant scoping (customer surface pre-resolution,
    or platform-admin/service flows that don't act as a single tenant); it is sent
    to Postgres as ``''``, which ``app_tenant_id()`` treats as NULL.

    ``role`` must be one of ``customer``, ``tenant_admin``, ``platform_admin``,
    ``service`` (database.md section 2.2) - anything else raises ``ValueError``
    before a connection is even acquired.

    Pass ``pool`` to use a pool other than the module-level one (tests point it at
    ``wren_test``); otherwise the pool created by ``create_pool()`` is used.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role {role!r}; must be one of {sorted(VALID_ROLES)}")

    active_pool = pool if pool is not None else get_pool()
    tenant_id_value = "" if tenant_id is None else str(tenant_id)

    # Timeout guards against pool exhaustion deadlock (e.g. accidental nesting, which
    # acquires a second connection per level - do not nest tenant_context per task).
    async with active_pool.acquire(timeout=30) as conn:
        async with conn.transaction():
            await conn.execute("select set_config('app.tenant_id', $1, true)", tenant_id_value)
            await conn.execute("select set_config('app.role', $1, true)", role)
            yield conn
