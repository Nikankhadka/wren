"""T-025: dataset loader tests + the ticket's own accept criterion -
"covers every specialist at least 4 times" and "loadable into eval_cases".
Scoring cases against a real graph run is T-026's job, not this ticket's.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest

from app.core import db
from evals.trajectory_dataset import load_cases, sync_eval_cases
from tests.conftest import _app_dsn_for

pytestmark = pytest.mark.db


def test_dataset_has_20_to_30_cases() -> None:
    cases = load_cases()
    assert 20 <= len(cases) <= 30


def test_dataset_covers_every_specialist_at_least_four_times() -> None:
    cases = load_cases()
    routes_seen: dict[str, int] = {}
    for case in cases:
        for route in case.expected_route:
            routes_seen[route] = routes_seen.get(route, 0) + 1
    for specialist in ("knowledge", "recommendation", "quoting", "order_status", "escalation"):
        assert routes_seen.get(specialist, 0) >= 4, (
            f"{specialist} only appears {routes_seen.get(specialist, 0)} times"
        )


def test_dataset_case_ids_are_unique() -> None:
    cases = load_cases()
    ids = [case.case_id for case in cases]
    assert len(ids) == len(set(ids))


def test_order_status_cases_use_real_seeded_ref_codes() -> None:
    cases = load_cases()
    order_cases = [c for c in cases if c.category == "order_status"]
    assert len(order_cases) >= 4
    for case in order_cases:
        assert case.expected_lookup is not None


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def test_sync_eval_cases_writes_and_replaces_rows(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Trajectory Dataset Test Co') returning id",
        f"trajectory-{uuid.uuid4().hex[:8]}",
    )
    await superuser_conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)

    cases = load_cases()
    await sync_eval_cases(superuser_conn, tenant_id, cases)

    rows = await superuser_conn.fetch(
        "select count(*) as n from eval_cases where tenant_id = $1 and case_type = 'trajectory'",
        tenant_id,
    )
    assert rows[0]["n"] == len(cases)

    # Re-running wipes and reinserts rather than accumulating duplicates.
    await sync_eval_cases(superuser_conn, tenant_id, cases)
    rows_again = await superuser_conn.fetch(
        "select count(*) as n from eval_cases where tenant_id = $1 and case_type = 'trajectory'",
        tenant_id,
    )
    assert rows_again[0]["n"] == len(cases)
