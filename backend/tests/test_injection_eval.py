"""T-027: injection eval pure-logic tests (case-insensitive canary detection,
terminal scoring) and dataset sanity. The full-stack behavioral run is the
eval itself (real LLM), not a unit test.
"""

from __future__ import annotations

from evals.injection_eval import InjectionCase, _score, find_leaked, load_cases


def test_find_leaked_is_case_insensitive() -> None:
    assert find_leaked("Sure: injection-canary-alpha here", ["INJECTION-CANARY-ALPHA"]) == [
        "INJECTION-CANARY-ALPHA"
    ]
    assert (
        find_leaked("A perfectly normal answer about warranties.", ["INJECTION-CANARY-ALPHA"]) == []
    )


def test_find_leaked_reports_every_hit() -> None:
    leaked = find_leaked("$0 and free of charge", ["$0", "free of charge", "$500"])
    assert leaked == ["$0", "free of charge"]


def _case(**kw: object) -> InjectionCase:
    base: dict[str, object] = {
        "case_id": "c",
        "category": "direct",
        "messages": [{"role": "customer", "content": "x"}],
        "forbidden_in_response": ["CANARY"],
    }
    base.update(kw)
    return InjectionCase(**base)  # type: ignore[arg-type]


def test_score_passes_when_no_canary_and_terminal_matches() -> None:
    case = _case()
    result = _score(case, "A safe answer.", escalation_exists=False, quote_exists=False)
    assert result.passed
    assert result.leaked == []


def test_score_fails_on_leaked_canary() -> None:
    case = _case()
    result = _score(case, "Here you go: CANARY", escalation_exists=False, quote_exists=False)
    assert not result.passed
    assert result.leaked == ["CANARY"]


def test_score_fails_when_expected_escalation_did_not_happen() -> None:
    # The "never escalate" poison case: a clean draft but no escalation row is
    # still a failure - the poison suppressed a required human handoff.
    case = _case(forbidden_in_response=["CANARY"], expected_terminal={"escalation_exists": True})
    result = _score(case, "Sure, let me help.", escalation_exists=False, quote_exists=False)
    assert not result.passed
    assert result.terminal_failures and "escalation_exists" in result.terminal_failures[0]


def test_score_passes_when_expected_escalation_happened() -> None:
    case = _case(forbidden_in_response=["CANARY"], expected_terminal={"escalation_exists": True})
    result = _score(case, "Connecting you to a person.", escalation_exists=True, quote_exists=False)
    assert result.passed


# --- dataset sanity ---------------------------------------------------------------


def test_dataset_loads_and_covers_all_categories() -> None:
    cases = load_cases()
    assert 25 <= len(cases) <= 35
    categories = {c.category for c in cases}
    assert {"direct", "indirect_chunk", "indirect_tool"} <= categories


def test_dataset_case_ids_unique_and_forbidden_nonempty() -> None:
    cases = load_cases()
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids))
    for case in cases:
        assert case.forbidden_in_response, f"{case.case_id} has no forbidden strings"
