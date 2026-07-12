"""T-023: pure metric/parsing tests for evals/generation_eval.py - no DB, no
LLM call. The LLM-in-the-loop scorers and the graph-driving helper are
deliberately untested here (same convention as evals/retrieval_eval.py's
live path); the graph itself is already covered by test_knowledge_agent.py.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.inspection import ESCALATION_MESSAGE
from app.llm.provider import SchemaT
from evals.generation_eval import (
    GenerationCase,
    citation_faithfulness_score,
    cosine_similarity,
    extract_cited_sentences,
    faithfulness_score,
    load_cases,
    relevancy_score,
    score_case,
    score_citation_faithfulness,
    score_faithfulness,
)
from tests.fakes import BaseFakeProvider, ZeroEmbedder


def test_faithfulness_score_ratio() -> None:
    assert faithfulness_score([True, True, False, True]) == 0.75


def test_faithfulness_empty_claims_is_one() -> None:
    assert faithfulness_score([]) == 1.0


def test_cosine_similarity_identical_vectors_is_one() -> None:
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_is_zero() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_relevancy_score_mean() -> None:
    assert relevancy_score([1.0, 0.5, 0.75]) == 0.75


def test_relevancy_empty_is_zero() -> None:
    assert relevancy_score([]) == 0.0


def test_citation_faithfulness_score_ratio() -> None:
    assert citation_faithfulness_score([True, False]) == 0.5


def test_citation_faithfulness_no_citations_is_one() -> None:
    assert citation_faithfulness_score([]) == 1.0


def test_extract_cited_sentences_segments_and_indexes() -> None:
    answer = (
        "We are open weekdays [1]. No screen protectors in stock right now. "
        "Repairs take 3 days [2][3]."
    )
    result = extract_cited_sentences(answer)
    assert result == [
        ("We are open weekdays [1].", [1]),
        ("Repairs take 3 days [2][3].", [2, 3]),
    ]


def test_extract_cited_sentences_no_citations_returns_empty() -> None:
    assert extract_cited_sentences("Nothing here has any markers at all.") == []


def test_load_cases_parses_fields(tmp_path: Path) -> None:
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        '{"question": "Q1", "reference_facts": ["fact one"], "expected_sources": ["policy.md"]}\n'
        '{"question": "Q2", "reference_facts": [], "expected_sources": [], "negative": true}\n'
    )
    cases = load_cases(dataset)
    assert len(cases) == 2
    assert cases[0].question == "Q1"
    assert cases[0].reference_facts == ["fact one"]
    assert cases[0].expected_sources == ["policy.md"]
    assert cases[0].negative is False
    assert cases[1].negative is True


async def test_out_of_range_citation_fails_deterministically_without_an_llm_call() -> None:
    """A citation index beyond the retrieved chunk list is a bug, not a
    judgment call - it fails without ever reaching the LLM. BaseFakeProvider
    raises NotImplementedError on any extract() call, so this test would
    fail loudly if that guarantee were ever broken. No in-range citation is
    present, so score_citation_faithfulness never needs to judge anything."""
    answer = "This part is not stocked here [9]."
    chunks = [{"content": "We are open weekdays 9-5."}]

    verdicts = await score_citation_faithfulness(answer, chunks, provider=BaseFakeProvider())

    assert len(verdicts) == 1
    assert verdicts[0].citation_index == 9
    assert verdicts[0].supported is False
    assert "out of range" in verdicts[0].reason


async def test_escalated_positive_case_scores_zero_without_an_llm_call() -> None:
    """An escalation handoff has no verifiable claims and no citations, so
    the normal scoring path would grade it a perfect 1.0 - it must instead be
    scored as a failed case, deterministically (BaseFakeProvider raises on
    any extract() call, proving no LLM is consulted)."""
    case = GenerationCase(question="What's covered under your repair warranty?")

    result = await score_case(
        case, ESCALATION_MESSAGE, [], provider=BaseFakeProvider(), embedder=ZeroEmbedder()
    )

    assert result.faithfulness == 0.0
    assert result.relevancy == 0.0
    assert result.citation_faithfulness == 0.0
    assert result.refused is False


class _NoVerdictJudge(BaseFakeProvider):
    """Extracts two claims, then returns zero verdicts for them - the
    denominator-shrinking judge failure mode."""

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        if "claims" in schema.model_fields:
            return schema.model_validate({"claims": ["claim one", "claim two"]})
        return schema.model_validate({"verdicts": []})


async def test_missing_judge_verdicts_fail_closed_as_unsupported() -> None:
    """A judge returning fewer verdicts than claims must not silently shrink
    the denominator toward a passing score - missing verdicts count as
    unsupported (zero verdicts would otherwise score 1.0)."""
    verdicts = await score_faithfulness("some answer", "some context", provider=_NoVerdictJudge())

    assert len(verdicts) == 2
    assert all(v.supported is False for v in verdicts)
    assert faithfulness_score([v.supported for v in verdicts]) == 0.0
