"""T-025: dataset loader tests + the ticket's own accept criterion -
"covers every specialist at least 4 times". Scoring cases against a real
graph run is T-026's job, not this ticket's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.shared import db
from evals.trajectory_dataset import load_cases
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


def test_dataset_size_and_lean_weighting() -> None:
    """G-1: big enough to mean something, and weighted to the shape that ships.

    The upper bound used to be 30, sized for T-025's five-specialist topology.
    The lean default (D-2) makes "answered straight from the corpus, no tool"
    the common case, so the set now carries enough of those to measure it - the
    old weighting had four knowledge cases against seventeen commerce ones,
    which measured a product that is now opt-in.
    """
    cases = load_cases()
    assert 20 <= len(cases) <= 45

    knowledge = [c for c in cases if c.expected_route == ["knowledge"]]
    assert len(knowledge) >= 8, "the lean path is the common one; measure it like it"


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


def test_persona_cases_cover_single_and_multi_turn_with_both_halves() -> None:
    """W-9: the transcript simulations carry a deterministic half every run
    can score and a judged half only a provider can score. A persona case
    with no deterministic terminal expectation measures nothing without an
    LLM, which is the failure mode this test exists to prevent."""
    persona = [c for c in load_cases() if c.category == "persona"]
    assert len(persona) >= 5
    assert any(len(c.messages) == 1 for c in persona), "no single-turn simulation"
    assert any(len(c.messages) > 1 for c in persona), "no multi-turn simulation"
    for case in persona:
        assert case.expected_terminal, f"{case.case_id}: no deterministic terminal state"
        assert "escalation_exists" in case.expected_terminal, (
            f"{case.case_id}: escalation_exists is how consent is proved without a judge"
        )
        assert case.persona, f"{case.case_id}: no judged criteria"


def test_the_disclosure_case_is_exempt_from_the_copy_rule() -> None:
    """Amendment 3's copy rule keeps "AI" out of routine copy and requires an
    honest answer to a direct question. Flagging the word in the one case that
    asks the question outright would grade the contract against itself."""
    cases = {c.case_id: c for c in load_cases()}
    assert cases["persona-disclosure-01"].forbidden.get("copy_rule_words") is None
    other_persona = [
        c
        for c in cases.values()
        if c.category == "persona" and c.case_id != "persona-disclosure-01"
    ]
    assert other_persona
    for case in other_persona:
        assert case.forbidden.get("copy_rule_words") is True, case.case_id


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
