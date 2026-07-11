"""T-019: lookup_order_or_ticket unit tests - found, not-found, wrong-tenant
(the ticket's own three cases), plus case-insensitivity and customer_ref
scoping. Seeded via superuser_conn, called through a real tenant_context
(tenant_admin role) - same pattern as test_pricing_engine.py's `_quote`
helper, proving the tool works under real RLS, not just as a superuser.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

from app.agents.tools import OrderLookup, lookup_order_or_ticket
from app.core import db
from tests.conftest import _app_dsn_for

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def _seed_tenant_with_order(
    conn: asyncpg.Connection[Any],
    *,
    ref_code: str = "R-1042",
    kind: str = "repair",
    status: str = "in_progress",
    customer_ref: str | None = "cust-1",
    details: dict[str, Any] | None = None,
) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Orders Test Co') returning id",
        f"orders-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    await conn.execute(
        "insert into orders (tenant_id, ref_code, kind, customer_ref, status, details) "
        "values ($1, $2, $3, $4, $5, $6)",
        tenant_id,
        ref_code,
        kind,
        customer_ref,
        status,
        json.dumps(details or {"device": "phone"}),
    )
    return tenant_id


async def _lookup(
    tenant_id: uuid.UUID, ref_code: str, customer_ref: str | None = None
) -> OrderLookup:
    async with db.tenant_context(tenant_id, "customer") as conn:
        return await lookup_order_or_ticket(conn, tenant_id, ref_code, customer_ref)


async def test_found_returns_seeded_state(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant_with_order(
        superuser_conn, ref_code="R-1042", status="in_progress"
    )

    result = await _lookup(tenant_id, "R-1042")

    assert result.found is True
    assert result.ref_code == "R-1042"
    assert result.kind == "repair"
    assert result.status == "in_progress"
    assert result.details == {"device": "phone"}


async def test_lookup_is_case_insensitive(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant_with_order(superuser_conn, ref_code="R-1042")

    result = await _lookup(tenant_id, "r-1042")

    assert result.found is True


async def test_unknown_ref_code_is_not_found(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant_with_order(superuser_conn, ref_code="R-1042")

    result = await _lookup(tenant_id, "R-9999")

    assert result.found is False
    assert result.ref_code == "R-9999"
    assert result.status is None


async def test_wrong_tenant_never_leaks(superuser_conn: asyncpg.Connection[Any]) -> None:
    await _seed_tenant_with_order(superuser_conn, ref_code="R-1042", status="ready_for_pickup")
    tenant_b: uuid.UUID = await superuser_conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Other Tenant') returning id",
        f"orders-b-{uuid.uuid4().hex[:8]}",
    )
    await superuser_conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_b)

    result = await _lookup(tenant_b, "R-1042")

    assert result.found is False
    assert result.status is None
    assert result.kind is None


async def test_customer_ref_mismatch_is_not_found(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant_with_order(
        superuser_conn, ref_code="R-1042", customer_ref="cust-1"
    )

    result = await _lookup(tenant_id, "R-1042", customer_ref="cust-2")

    assert result.found is False


async def test_customer_ref_match_is_found(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant_with_order(
        superuser_conn, ref_code="R-1042", customer_ref="cust-1"
    )

    result = await _lookup(tenant_id, "R-1042", customer_ref="cust-1")

    assert result.found is True


@pytest.mark.parametrize("blank", ["", "   "])
async def test_blank_customer_ref_is_treated_as_not_given(
    superuser_conn: asyncpg.Connection[Any], blank: str
) -> None:
    """A structured-output model is prone to returning "" instead of
    omitting an optional field - that must not be treated as a literal
    empty-string filter, or a real order would spuriously not-found."""
    tenant_id = await _seed_tenant_with_order(
        superuser_conn, ref_code="R-1042", customer_ref="cust-1"
    )

    result = await _lookup(tenant_id, "R-1042", customer_ref=blank)

    assert result.found is True
