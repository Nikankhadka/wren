"""T-024: pure metric/parsing tests for evals/judge_calibration.py - no DB,
no LLM call. The real calibration run (judge vs. hand-labels) requires a
live LLM - same not-CI-deterministic caveat as T-023's generation_eval.py;
the script is the test for that part.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.judge_calibration import agreement, cohens_kappa, load_cases


def test_agreement_perfect_is_one() -> None:
    assert agreement([True, False, True], [True, False, True]) == 1.0


def test_agreement_partial() -> None:
    assert agreement([True, True, False, False], [True, False, False, False]) == 0.75


def test_agreement_empty_raises() -> None:
    with pytest.raises(ValueError, match="zero labels"):
        agreement([], [])


def test_agreement_mismatched_length_raises() -> None:
    with pytest.raises(ValueError):
        agreement([True, False], [True])


def test_cohens_kappa_known_textbook_value() -> None:
    # a=20 (both True), b=5 (human True/judge False), c=10, d=15 -> po=0.7, pe=0.5, kappa=0.4
    human = [True] * 25 + [False] * 25
    judge = [True] * 20 + [False] * 5 + [True] * 10 + [False] * 15
    assert cohens_kappa(human, judge) == pytest.approx(0.4)


def test_cohens_kappa_perfect_agreement_is_one() -> None:
    assert cohens_kappa([True, False, True, False], [True, False, True, False]) == 1.0


def test_cohens_kappa_degenerate_single_class_agrees() -> None:
    assert cohens_kappa([True, True, True], [True, True, True]) == 1.0


def test_cohens_kappa_degenerate_single_class_disagrees() -> None:
    assert cohens_kappa([True, True, True], [False, False, False]) == 0.0


def test_cohens_kappa_empty_raises() -> None:
    with pytest.raises(ValueError):
        cohens_kappa([], [])


def test_load_cases_valid_dataset_positions_align() -> None:
    cases = load_cases()
    assert len(cases) >= 25
    for case in cases:
        assert len(case.claims) == len(case.claim_labels)
        assert case.label_source in ("founder", "agent_placeholder")


def test_load_cases_rejects_claim_label_length_mismatch(tmp_path: Path) -> None:
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(
        '{"question": "Q", "answer": "A [1].", "chunks": [{"content": "c"}], '
        '"claims": ["one", "two"], "claim_labels": [true], "citation_labels": [true], '
        '"label_source": "agent_placeholder"}\n'
    )
    with pytest.raises(ValueError, match="claim/claim_labels length mismatch"):
        load_cases(dataset)


def test_load_cases_rejects_citation_label_count_mismatch(tmp_path: Path) -> None:
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(
        '{"question": "Q", "answer": "A [1]. B [1].", "chunks": [{"content": "c"}], '
        '"claims": [], "claim_labels": [], "citation_labels": [true], '
        '"label_source": "agent_placeholder"}\n'
    )
    with pytest.raises(ValueError, match="citation_labels length"):
        load_cases(dataset)


def test_load_cases_rejects_conflicting_labels_on_identical_citation_unit(tmp_path: Path) -> None:
    # One sentence carrying [1] twice is the SAME judged unit twice - the
    # judge sees the identical sentence/chunk pair for both positions, so
    # labeling them [true, false] (per-clause intent) is incoherent and
    # would silently cap agreement at 50% on that row.
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(
        '{"question": "Q", "answer": "X is a [1], and Y is b [1].", '
        '"chunks": [{"content": "c"}], '
        '"claims": [], "claim_labels": [], "citation_labels": [true, false], '
        '"label_source": "agent_placeholder"}\n'
    )
    with pytest.raises(ValueError, match="conflicting labels"):
        load_cases(dataset)


def test_load_cases_accepts_identical_citation_unit_with_matching_labels(tmp_path: Path) -> None:
    dataset = tmp_path / "ok.jsonl"
    dataset.write_text(
        '{"question": "Q", "answer": "X is a [1], and Y is b [1].", '
        '"chunks": [{"content": "c"}], '
        '"claims": [], "claim_labels": [], "citation_labels": [true, true], '
        '"label_source": "agent_placeholder"}\n'
    )
    assert len(load_cases(dataset)) == 1


def test_load_cases_rejects_out_of_range_citation(tmp_path: Path) -> None:
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(
        '{"question": "Q", "answer": "A [9].", "chunks": [{"content": "c"}], '
        '"claims": [], "claim_labels": [], "citation_labels": [true], '
        '"label_source": "agent_placeholder"}\n'
    )
    with pytest.raises(ValueError, match="out of range"):
        load_cases(dataset)


def test_load_cases_rejects_unknown_label_source(tmp_path: Path) -> None:
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text(
        '{"question": "Q", "answer": "A [1].", "chunks": [{"content": "c"}], '
        '"claims": [], "claim_labels": [], "citation_labels": [true], '
        '"label_source": "made_up"}\n'
    )
    with pytest.raises(ValueError, match="unknown label_source"):
        load_cases(dataset)


def test_load_cases_skips_comment_line(tmp_path: Path) -> None:
    dataset = tmp_path / "with_comment.jsonl"
    dataset.write_text(
        '{"_comment": "this is a header comment, not a case"}\n'
        '{"question": "Q", "answer": "A [1].", "chunks": [{"content": "c"}], '
        '"claims": ["c1"], "claim_labels": [true], "citation_labels": [true], '
        '"label_source": "founder"}\n'
    )
    cases = load_cases(dataset)
    assert len(cases) == 1
