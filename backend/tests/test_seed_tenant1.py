"""T-010: the Tenant 1 seed script, run against wren_test with a stub provider.

`seed()` reuses whatever pool already exists (it only creates/closes its own
pool if none is set up yet) - so pointing a pool at wren_test first, then
calling `seed()`, exercises the exact same code path the real
`uv run python -m seeds.seed_tenant1_phoneshop` entrypoint uses, without
needing real Azure credentials.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
import pytest_asyncio

from app.core import db
from seeds.seed_tenant1_phoneshop import CATALOG_ITEMS, PRICING_RULES, SLUG, seed
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider

pytestmark = pytest.mark.db


class FakeEmbedProvider(BaseFakeProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


@pytest_asyncio.fixture
async def app_pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        yield
    finally:
        await db.close_pool()


async def test_seed_creates_tenant_with_expected_counts(app_pool: None) -> None:
    tenant_id = await seed(provider=FakeEmbedProvider())

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        slug = await conn.fetchval("select slug from tenants where id = $1", tenant_id)
        assert slug == SLUG

        catalog_count = await conn.fetchval(
            "select count(*) from catalog_items where tenant_id = $1", tenant_id
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
    first_id = await seed(provider=FakeEmbedProvider())
    second_id = await seed(provider=FakeEmbedProvider())

    assert first_id != second_id  # re-seeding recreates the tenant with a fresh id

    count = await superuser_conn.fetchval("select count(*) from tenants where slug = $1", SLUG)
    assert count == 1  # the first tenant was wiped, not left behind

    leftover_catalog = await superuser_conn.fetchval(
        "select count(*) from catalog_items where tenant_id = $1", first_id
    )
    assert leftover_catalog == 0  # cascaded away with the first tenant
