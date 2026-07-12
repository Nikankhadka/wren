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
from seeds.seed_tenant1_phoneshop import (
    CATALOG_ITEMS,
    ORDER_STATUSES,
    PRICING_RULES,
    REPAIR_STATUSES,
)
from tests.conftest import _app_dsn_for

_RULE_CODES = {code for code, *_ in PRICING_RULES}
_ITEM_NAMES = {name for name, *_ in CATALOG_ITEMS}


def _seeded_status(ref_code: str) -> str | None:
    """Recomputes the exact status seed_tenant1_phoneshop.py assigns a
    ref_code, mirroring its seeding loop precisely (i%len(STATUSES))."""
    code = ref_code.upper()
    if code.startswith("R-"):
        i = int(code.removeprefix("R-")) - 1001
        if 0 <= i <= 14:
            return REPAIR_STATUSES[i % len(REPAIR_STATUSES)]
    elif code.startswith("ORD-"):
        i = int(code.removeprefix("ORD-")) - 2001
        if 0 <= i <= 4:
            return ORDER_STATUSES[i % len(ORDER_STATUSES)]
    return None


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


def test_order_status_cases_match_the_real_seeded_status_formula() -> None:
    """A wrong-by-one seeded status here would silently mis-score every
    future T-026 run against this case - recompute it from the exact
    formula seed_tenant1_phoneshop.py uses, don't just check a field exists."""
    cases = load_cases()
    order_cases = [c for c in cases if c.category == "order_status"]
    assert len(order_cases) >= 4
    for case in order_cases:
        assert case.expected_lookup is not None
        ref_code = case.expected_lookup.get("ref_code")
        if ref_code is None or not case.expected_lookup.get("found"):
            continue  # "no ref given" / "unknown ref" cases have no status to check
        expected_status = _seeded_status(ref_code)
        assert expected_status is not None, f"{case.case_id}: {ref_code!r} isn't in the seed range"
        assert case.expected_lookup["status"] == expected_status, (
            f"{case.case_id}: {ref_code!r} should be {expected_status!r}, "
            f"not {case.expected_lookup['status']!r}"
        )


def test_expected_and_forbidden_selections_reference_real_seeded_names() -> None:
    """A typo'd rule code or item name would make a future T-026 exact-match
    scorer silently always fail (or always pass, on a loose match) - catch
    it here instead."""
    cases = load_cases()
    for case in cases:
        for selection in case.expected_selections + case.forbidden_selections:
            if selection["kind"] == "rule":
                assert selection["code"] in _RULE_CODES, (
                    f"{case.case_id}: unknown rule code {selection['code']!r}"
                )
            elif "item_name_any" in selection:
                for name in selection["item_name_any"]:
                    assert name in _ITEM_NAMES, f"{case.case_id}: unknown item name {name!r}"
            else:
                assert selection["item_name"] in _ITEM_NAMES, (
                    f"{case.case_id}: unknown item name {selection['item_name']!r}"
                )


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
