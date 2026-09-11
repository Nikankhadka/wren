"""The Sabbaba seed script, run against wren_test with a stub embedder.

Mirrors test_seed_tenant1.py: ``seed()`` reuses whatever pool already
exists, so pointing a pool at wren_test first exercises the exact code
path the real ``python -m seeds.seed_sababa`` entrypoint uses, without
loading a real embedding model.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
import pytest_asyncio

from app.shared import db
from seeds.seed_sababa import (
    CATALOG_ITEMS,
    PRICING_RULES,
    SABABA_PROFILE,
    SLUG,
    TENANT_NAME,
    seed,
)
from tests.conftest import _app_dsn_for
from tests.fakes import ZeroEmbedder

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def app_pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        yield
    finally:
        await db.close_pool()


async def test_seed_creates_tenant_with_expected_counts(app_pool: None) -> None:
    tenant_id = await seed(embedder=ZeroEmbedder())

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        slug = await conn.fetchval("select slug from tenants where id = $1", tenant_id)
        assert slug == SLUG

        catalog_count = await conn.fetchval(
            "select count(*) from offerings where tenant_id = $1", tenant_id
        )
        assert catalog_count == len(CATALOG_ITEMS)

        rules_count = await conn.fetchval(
            "select count(*) from pricing_rules where tenant_id = $1", tenant_id
        )
        assert rules_count == len(PRICING_RULES)

        orders_count = await conn.fetchval(
            "select count(*) from orders where tenant_id = $1", tenant_id
        )
        assert orders_count == 5

        ready_docs = await conn.fetchval(
            "select count(*) from documents where tenant_id = $1 and status = 'ready'", tenant_id
        )
        assert ready_docs == 3  # menu.md, faq.md, + synthetic catalog doc

        chunk_count = await conn.fetchval(
            "select count(*) from knowledge_chunks where tenant_id = $1", tenant_id
        )
        assert chunk_count > len(CATALOG_ITEMS)  # catalog chunks + at least the prose chunks


async def test_seed_is_idempotent(app_pool: None, superuser_conn: asyncpg.Connection[Any]) -> None:
    first_id = await seed(embedder=ZeroEmbedder())
    second_id = await seed(embedder=ZeroEmbedder())

    assert first_id != second_id  # re-seeding recreates the tenant with a fresh id

    count = await superuser_conn.fetchval("select count(*) from tenants where slug = $1", SLUG)
    assert count == 1  # the first tenant was wiped, not left behind

    leftover_catalog = await superuser_conn.fetchval(
        "select count(*) from offerings where tenant_id = $1", first_id
    )
    assert leftover_catalog == 0  # cascaded away with the first tenant


async def test_seed_pre_onboards_the_tenant(
    app_pool: None, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_id = await seed(embedder=ZeroEmbedder())

    row = await superuser_conn.fetchrow(
        "select t.business_name, c.system_prompt, c.config "
        "from tenants t join tenant_config c on c.tenant_id = t.id where t.id = $1",
        tenant_id,
    )
    assert row is not None
    assert row["business_name"] == TENANT_NAME
    assert TENANT_NAME in row["system_prompt"]

    config = json.loads(row["config"])
    assert config["onboarding"]["completed"] is True
    assert config["onboarding"]["version"] == 4
    assert config["onboarding"]["draft"] == SABABA_PROFILE
    assert config["profile"] == SABABA_PROFILE


async def test_seed_takes_the_lean_tool_default(
    app_pool: None, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """D-2: sababa writes no enabled_tools, like lumident - only bytefix opts in."""
    tenant_id = await seed(embedder=ZeroEmbedder())
    row = await superuser_conn.fetchrow(
        "select enabled_tools from tenant_config where tenant_id = $1", tenant_id
    )
    assert row is not None
    lean = ["search_knowledge", "create_escalation"]
    assert json.loads(row["enabled_tools"]) == lean


async def test_ranged_items_carry_no_price(app_pool: None) -> None:
    """The money rule, seed-side: Plate and base Pita Pocket share a $20-$30
    range in the source, so neither gets a number picked out of it."""
    tenant_id = await seed(embedder=ZeroEmbedder())

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select name, price_cents from offerings where tenant_id = $1", tenant_id
        )
    by_name = {r["name"]: r["price_cents"] for r in rows}
    assert by_name["Plate"] is None
    assert by_name["Pita Pocket"] is None
    assert by_name["Bowl"] == 2700
    assert by_name["Super Plate"] == 3700
    assert by_name["Six Falafel"] == 1090
