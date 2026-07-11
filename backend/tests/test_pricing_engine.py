"""T-016: the pricing engine's exhaustive unit coverage - this file IS the
ticket's deliverable proof. Every case reads real seeded pricing_rules/
catalog_items/tenant_config from Postgres; nothing here mocks the DB layer,
since the whole point of the engine is that it reads authoritative,
un-stale data.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.core import db
from app.pricing.engine import (
    MAX_QUANTITY,
    MIN_QUANTITY,
    EngineQuote,
    Selection,
    SelectionError,
    compute_quote,
)
from tests.conftest import _app_dsn_for

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def _seed_tenant(
    conn: asyncpg.Connection[Any], *, tax_rate_bps: int | None = None
) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Pricing Test Co') returning id",
        f"pricing-{uuid.uuid4().hex[:8]}",
    )
    config = {"tax": {"rate_bps": tax_rate_bps, "label": "Sales tax"}} if tax_rate_bps else {}
    await conn.execute(
        "insert into tenant_config (tenant_id, config) values ($1, $2)",
        tenant_id,
        json.dumps(config),
    )
    return tenant_id


async def _seed_rule(
    conn: asyncpg.Connection[Any],
    tenant_id: uuid.UUID,
    *,
    code: str,
    label: str = "Rule",
    unit_amount_cents: int = 1000,
    unit: str = "each",
    active: bool = True,
    conditions: dict[str, Any] | None = None,
) -> None:
    await conn.execute(
        "insert into pricing_rules (tenant_id, code, label, unit_amount_cents, unit, active, "
        "conditions) values ($1, $2, $3, $4, $5, $6, $7)",
        tenant_id,
        code,
        label,
        unit_amount_cents,
        unit,
        active,
        json.dumps(conditions or {}),
    )


async def _seed_item(
    conn: asyncpg.Connection[Any],
    tenant_id: uuid.UUID,
    *,
    name: str = "Widget",
    price_cents: int | None = 500,
    active: bool = True,
) -> uuid.UUID:
    item_id: uuid.UUID = await conn.fetchval(
        "insert into catalog_items (tenant_id, name, price_cents, active) "
        "values ($1, $2, $3, $4) returning id",
        tenant_id,
        name,
        price_cents,
        active,
    )
    return item_id


async def _quote(tenant_id: uuid.UUID, selections: list[Selection]) -> EngineQuote:
    """compute_quote is called through a real tenant_context-scoped
    connection (tenant_admin role), matching how the Quoting Agent (T-017)
    will actually invoke it - proves the engine works under real RLS, not
    just as an all-powerful superuser bypass."""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        return await compute_quote(conn, tenant_id, selections)


# --- single/multi line, both selection kinds ------------------------------------


async def test_single_rule_line(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(superuser_conn, tenant_id, code="rule-a", unit_amount_cents=1000)

    quote = await _quote(tenant_id, [Selection(kind="rule", code_or_id="rule-a", quantity=2)])

    assert len(quote.line_items) == 1
    assert quote.line_items[0].line_total_cents == 2000
    assert quote.subtotal_cents == 2000
    assert quote.total_cents == 2000


async def test_single_item_line(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    item_id = await _seed_item(superuser_conn, tenant_id, price_cents=750)

    quote = await _quote(tenant_id, [Selection(kind="item", code_or_id=str(item_id), quantity=3)])

    assert quote.line_items[0].line_total_cents == 2250
    assert quote.subtotal_cents == 2250


async def test_multi_line_mixed_kinds(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(superuser_conn, tenant_id, code="rule-a", unit_amount_cents=1000)
    item_id = await _seed_item(superuser_conn, tenant_id, price_cents=500)

    quote = await _quote(
        tenant_id,
        [
            Selection(kind="rule", code_or_id="rule-a", quantity=2),
            Selection(kind="item", code_or_id=str(item_id), quantity=1),
        ],
    )

    assert len(quote.line_items) == 2
    assert quote.subtotal_cents == 2000 + 500
    assert quote.subtotal_cents == sum(li.line_total_cents for li in quote.line_items)


# --- tax on/off, rounding --------------------------------------------------------


async def test_tax_off_by_default(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(superuser_conn, tenant_id, code="rule-a", unit_amount_cents=1000)

    quote = await _quote(tenant_id, [Selection(kind="rule", code_or_id="rule-a", quantity=1)])

    assert quote.tax_cents == 0
    assert quote.total_cents == quote.subtotal_cents


async def test_tax_on_exact_division(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn, tax_rate_bps=1000)  # 10%
    await _seed_rule(superuser_conn, tenant_id, code="rule-a", unit_amount_cents=1000)

    quote = await _quote(tenant_id, [Selection(kind="rule", code_or_id="rule-a", quantity=1)])

    assert quote.tax_cents == 100
    assert quote.total_cents == 1100


async def test_tax_rounding_floors_down(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn, tax_rate_bps=875)  # 8.75%
    await _seed_rule(superuser_conn, tenant_id, code="rule-a", unit_amount_cents=333)

    quote = await _quote(tenant_id, [Selection(kind="rule", code_or_id="rule-a", quantity=1)])

    # 333 * 875 // 10000 = 291375 // 10000 = 29 (floors, never rounds up)
    assert quote.tax_cents == 29
    assert quote.total_cents == quote.subtotal_cents + quote.tax_cents


# --- unknown codes, inactive rows -------------------------------------------------


async def test_unknown_rule_code_raises(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    with pytest.raises(SelectionError, match="unknown or inactive pricing rule"):
        await _quote(
            tenant_id,
            [Selection(kind="rule", code_or_id="no-such-rule", quantity=1)],
        )


async def test_inactive_rule_raises(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(superuser_conn, tenant_id, code="rule-a", active=False)
    with pytest.raises(SelectionError, match="unknown or inactive pricing rule"):
        await _quote(tenant_id, [Selection(kind="rule", code_or_id="rule-a", quantity=1)])


async def test_unknown_catalog_item_raises(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    with pytest.raises(SelectionError, match="unknown or inactive catalog item"):
        await _quote(
            tenant_id,
            [Selection(kind="item", code_or_id=str(uuid.uuid4()), quantity=1)],
        )


async def test_inactive_catalog_item_raises(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    item_id = await _seed_item(superuser_conn, tenant_id, active=False)
    with pytest.raises(SelectionError, match="unknown or inactive catalog item"):
        await _quote(tenant_id, [Selection(kind="item", code_or_id=str(item_id), quantity=1)])


async def test_catalog_item_without_direct_price_raises(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    item_id = await _seed_item(superuser_conn, tenant_id, price_cents=None)
    with pytest.raises(SelectionError, match="no direct price"):
        await _quote(tenant_id, [Selection(kind="item", code_or_id=str(item_id), quantity=1)])


async def test_malformed_item_id_raises(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    with pytest.raises(SelectionError, match="malformed catalog item id"):
        await _quote(tenant_id, [Selection(kind="item", code_or_id="not-a-uuid", quantity=1)])


async def test_empty_selections_raises(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    with pytest.raises(SelectionError, match="no selections"):
        await _quote(tenant_id, [])


# --- zero-amount rules -----------------------------------------------------------


async def test_zero_amount_rule_is_valid(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(superuser_conn, tenant_id, code="free-rule", unit_amount_cents=0)

    quote = await _quote(tenant_id, [Selection(kind="rule", code_or_id="free-rule", quantity=5)])

    assert quote.line_items[0].line_total_cents == 0
    assert quote.subtotal_cents == 0
    assert quote.total_cents == 0


# --- quantity bounds ---------------------------------------------------------------


@pytest.mark.parametrize("quantity", [0, -1, 1000, 5000])
async def test_quantity_out_of_bounds_raises(
    superuser_conn: asyncpg.Connection[Any], quantity: int
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(superuser_conn, tenant_id, code="rule-a")
    with pytest.raises(SelectionError, match="out of bounds"):
        await _quote(
            tenant_id,
            [Selection(kind="rule", code_or_id="rule-a", quantity=quantity)],
        )


@pytest.mark.parametrize("quantity", [MIN_QUANTITY, MAX_QUANTITY])
async def test_quantity_at_bounds_is_valid(
    superuser_conn: asyncpg.Connection[Any], quantity: int
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(superuser_conn, tenant_id, code="rule-a", unit_amount_cents=100)

    quote = await _quote(
        tenant_id, [Selection(kind="rule", code_or_id="rule-a", quantity=quantity)]
    )
    assert quote.subtotal_cents == 100 * quantity


# --- conditions.min_qty ------------------------------------------------------------


async def test_below_min_qty_raises(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(
        superuser_conn,
        tenant_id,
        code="bulk-rule",
        unit_amount_cents=100,
        conditions={"min_qty": 5},
    )
    with pytest.raises(SelectionError, match="below rule .* minimum"):
        await _quote(tenant_id, [Selection(kind="rule", code_or_id="bulk-rule", quantity=3)])


async def test_at_min_qty_succeeds(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(
        superuser_conn,
        tenant_id,
        code="bulk-rule",
        unit_amount_cents=100,
        conditions={"min_qty": 5},
    )

    quote = await _quote(tenant_id, [Selection(kind="rule", code_or_id="bulk-rule", quantity=5)])
    assert quote.subtotal_cents == 500


# --- to_dict shape -------------------------------------------------------------


async def test_line_item_to_dict_matches_quotes_schema_shape(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    await _seed_rule(
        superuser_conn, tenant_id, code="rule-a", label="Rule A", unit_amount_cents=100
    )

    quote = await _quote(tenant_id, [Selection(kind="rule", code_or_id="rule-a", quantity=2)])
    line_dict = quote.line_items[0].to_dict()
    assert line_dict == {
        "kind": "rule",
        "code": "rule-a",
        "label": "Rule A",
        "quantity": 2,
        "unit_amount_cents": 100,
        "line_total_cents": 200,
    }


# --- property test: total always equals sum of parts ------------------------------


@given(
    quantities=st.lists(
        st.integers(min_value=MIN_QUANTITY, max_value=MAX_QUANTITY), min_size=1, max_size=5
    ),
    tax_rate_bps=st.integers(min_value=0, max_value=2000),
)
@settings(max_examples=25, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_total_always_equals_subtotal_plus_tax(
    superuser_conn: asyncpg.Connection[Any], quantities: list[int], tax_rate_bps: int
) -> None:
    tenant_id = await _seed_tenant(superuser_conn, tax_rate_bps=tax_rate_bps or None)
    await _seed_rule(superuser_conn, tenant_id, code="prop-rule", unit_amount_cents=317)

    selections = [Selection(kind="rule", code_or_id="prop-rule", quantity=q) for q in quantities]
    # compute_quote only accepts one selection per rule_code in a real quote
    # conceptually, but nothing stops re-selecting the same rule at different
    # quantities here - each selection produces its own line item either way,
    # which is exactly what the property under test cares about.
    quote = await _quote(tenant_id, selections)

    assert quote.subtotal_cents == sum(li.line_total_cents for li in quote.line_items)
    assert quote.total_cents == quote.subtotal_cents + quote.tax_cents
