"""T-010: the Tenant 1 seed script, run against wren_test with a stub embedder.

`seed()` reuses whatever pool already exists (it only creates/closes its own
pool if none is set up yet) - so pointing a pool at wren_test first, then
calling `seed()`, exercises the exact same code path the real
`uv run python -m seeds.seed_tenant1_phoneshop` entrypoint uses, without
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
from seeds.seed_tenant1_phoneshop import (
    BYTEFIX_PROFILE,
    CATALOG_ITEMS,
    PRICING_RULES,
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
        assert orders_count == 20

        ready_docs = await conn.fetchval(
            "select count(*) from documents where tenant_id = $1 and status = 'ready'", tenant_id
        )
        assert ready_docs == 4  # policy.md, faq.md, price_list.md, + synthetic catalog doc

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
    """The seed writes the same end-state a real onboarding confirm leaves.

    The demo world lands in the console, not the interview, so the tenant is
    born with a completed onboarding record, a profile, a business_name, and a
    persona - exactly the four rows the confirm write path produces.
    """
    tenant_id = await seed(embedder=ZeroEmbedder())

    row = await superuser_conn.fetchrow(
        "select t.business_name, c.system_prompt, c.config "
        "from tenants t join tenant_config c on c.tenant_id = t.id where t.id = $1",
        tenant_id,
    )
    assert row is not None
    assert row["business_name"] == TENANT_NAME
    assert "Bytefix Repairs" in row["system_prompt"]

    config = json.loads(row["config"])
    assert config["onboarding"]["completed"] is True
    assert config["onboarding"]["version"] == 4
    assert config["onboarding"]["draft"] == BYTEFIX_PROFILE
    assert config["profile"] == BYTEFIX_PROFILE


async def test_lean_default_and_tenant_one_opt_in(
    app_pool: None, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """D-2: the column's default is lean, and tenant 1 says otherwise on purpose.

    Two halves of one decision. A business that never asked for quoting must
    not have it, so the default is search + escalate; reference tenant 1 is
    where the commerce tools get demonstrated, so it opts in explicitly. Tenant
    2 takes the default untouched, which is the I8 proof - two verticals, one
    codebase, different config.

    Nothing reads `enabled_tools` yet (D-1 wires it in Phase 2). That is exactly
    why this is pinned now: the data has to be honest before the reader exists,
    or D-1's arrival would switch quoting on for every tenant onboarded before
    it, silently.
    """
    lean = ["search_knowledge", "create_escalation"]

    # The default, taken by any row that does not state a set - which is every
    # tenant that onboards through signup.
    default_sql = await superuser_conn.fetchval(
        "select column_default from information_schema.columns "
        "where table_name = 'tenant_config' and column_name = 'enabled_tools'"
    )
    assert json.loads(default_sql.split("::")[0].strip("'")) == lean

    tenant_id = await seed(embedder=ZeroEmbedder())
    tools = await superuser_conn.fetchval(
        "select enabled_tools from tenant_config where tenant_id = $1", tenant_id
    )
    assert json.loads(tools) == [
        "search_knowledge",
        "recommend_items",
        "get_quote_inputs",
        "lookup_order_or_ticket",
        "create_escalation",
    ]
