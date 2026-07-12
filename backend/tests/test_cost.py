"""T-030: LLM cost accounting tests.

Pure-function/contextvar tests need no DB; record_costs()/aggregation need
a real cost_logs table.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from uuid import uuid4

import asyncpg
import pytest

from app.core import db
from app.observability.cost import (
    TokenUsage,
    collect_usage,
    compute_cost_usd,
    cost_for_conversation,
    cost_for_tenant_day,
    record_costs,
    report_usage,
)
from tests.conftest import _app_dsn_for

# --- pure functions -----------------------------------------------------------


def test_compute_cost_usd_known_model() -> None:
    # gpt-4o-mini: $0.15/1M input, $0.60/1M output
    cost = compute_cost_usd("gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == Decimal("0.750000")


def test_compute_cost_usd_unknown_model_is_zero() -> None:
    assert compute_cost_usd("some-free-model", input_tokens=5000, output_tokens=5000) == Decimal(
        "0"
    )


def test_compute_cost_usd_quantizes_to_six_decimal_places() -> None:
    cost = compute_cost_usd("gpt-4o-mini", input_tokens=1, output_tokens=1)
    assert cost == cost.quantize(Decimal("0.000001"))


def test_report_usage_with_no_active_sink_is_silently_dropped() -> None:
    # No collect_usage() context active - must not raise.
    report_usage("gpt-4o-mini", 10, 5)


def test_collect_usage_captures_reported_calls() -> None:
    with collect_usage() as usages:
        report_usage("gpt-4o-mini", 100, 50)
        report_usage("text-embedding-3-small", 20, 0)
    assert usages == [
        TokenUsage(model="gpt-4o-mini", input_tokens=100, output_tokens=50),
        TokenUsage(model="text-embedding-3-small", input_tokens=20, output_tokens=0),
    ]


def test_collect_usage_nesting_restores_outer_sink() -> None:
    with collect_usage() as outer:
        report_usage("outer-model", 1, 1)
        with collect_usage() as inner:
            report_usage("inner-model", 2, 2)
        assert inner == [TokenUsage(model="inner-model", input_tokens=2, output_tokens=2)]
        report_usage("outer-model-again", 3, 3)
    assert outer == [
        TokenUsage(model="outer-model", input_tokens=1, output_tokens=1),
        TokenUsage(model="outer-model-again", input_tokens=3, output_tokens=3),
    ]


async def test_collect_usage_concurrent_turns_do_not_cross_contaminate() -> None:
    """contextvars are task-local - two concurrent 'turns' must never see
    each other's reported usage, matching cost.py's own docstring claim."""

    async def _turn(model: str) -> list[TokenUsage]:
        with collect_usage() as usages:
            await asyncio.sleep(0)
            report_usage(model, 1, 1)
            await asyncio.sleep(0)
            report_usage(model, 2, 2)
        return usages

    results = await asyncio.gather(_turn("model-a"), _turn("model-b"))
    assert results[0] == [
        TokenUsage(model="model-a", input_tokens=1, output_tokens=1),
        TokenUsage(model="model-a", input_tokens=2, output_tokens=2),
    ]
    assert results[1] == [
        TokenUsage(model="model-b", input_tokens=1, output_tokens=1),
        TokenUsage(model="model-b", input_tokens=2, output_tokens=2),
    ]


# --- DB-backed persistence/aggregation -----------------------------------------

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def _seed_tenant_and_conversation(
    conn: asyncpg.Connection[Any],
) -> tuple[Any, Any]:
    tenant_id = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Cost Test Co') returning id",
        f"cost-{uuid4().hex[:8]}",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    conversation_id = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    return tenant_id, conversation_id


async def test_record_costs_writes_rows_and_returns_matching_total(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed_tenant_and_conversation(superuser_conn)
    async with db.tenant_context(tenant_id, "customer") as conn:
        total = await record_costs(
            conn,
            tenant_id,
            conversation_id,
            [
                TokenUsage(model="gpt-4o-mini", input_tokens=1000, output_tokens=500),
                TokenUsage(model="text-embedding-3-small", input_tokens=200, output_tokens=0),
            ],
        )

    rows = await superuser_conn.fetch(
        "select model, input_tokens, output_tokens, cost_usd from cost_logs "
        "where conversation_id = $1 order by created_at",
        conversation_id,
    )
    assert len(rows) == 2
    assert rows[0]["model"] == "gpt-4o-mini"
    assert rows[0]["input_tokens"] == 1000
    assert rows[0]["output_tokens"] == 500
    expected_total = compute_cost_usd("gpt-4o-mini", 1000, 500) + compute_cost_usd(
        "text-embedding-3-small", 200, 0
    )
    assert total == expected_total


async def test_record_costs_empty_list_writes_nothing(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed_tenant_and_conversation(superuser_conn)
    async with db.tenant_context(tenant_id, "customer") as conn:
        total = await record_costs(conn, tenant_id, conversation_id, [])
    assert total == Decimal("0")
    count = await superuser_conn.fetchval(
        "select count(*) from cost_logs where conversation_id = $1", conversation_id
    )
    assert count == 0


async def test_cost_for_conversation_sums_across_turns(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed_tenant_and_conversation(superuser_conn)
    async with db.tenant_context(tenant_id, "customer") as conn:
        await record_costs(
            conn, tenant_id, conversation_id, [TokenUsage("gpt-4o-mini", 1_000_000, 0)]
        )
        await record_costs(
            conn, tenant_id, conversation_id, [TokenUsage("gpt-4o-mini", 1_000_000, 0)]
        )
        total = await cost_for_conversation(conn, conversation_id)
    assert total == Decimal("0.300000")  # 2 x $0.15 per 1M input tokens


async def test_cost_for_tenant_day_scopes_to_today(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id = await _seed_tenant_and_conversation(superuser_conn)
    async with db.tenant_context(tenant_id, "customer") as conn:
        await record_costs(
            conn, tenant_id, conversation_id, [TokenUsage("gpt-4o-mini", 1_000_000, 0)]
        )
        total = await cost_for_tenant_day(conn, tenant_id)
    assert total == Decimal("0.150000")
