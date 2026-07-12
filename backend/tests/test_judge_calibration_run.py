"""T-024: fake-provider integration test for run_calibration() - no DB
needed (unlike test_generation_eval_run.py, this script never drives the
graph or touches eval_cases; it only calls judge_claims/
score_citation_faithfulness directly against frozen units)."""

from __future__ import annotations

from typing import get_args

from app.llm.provider import SchemaT
from evals.judge_calibration import CalibrationCase, run_calibration
from tests.fakes import BaseFakeProvider


class ScriptedJudge(BaseFakeProvider):
    """Returns verdicts in a fixed order per schema type, one call per
    invocation - lets a test assert exact agreement/kappa numbers."""

    def __init__(self, claim_supported: list[bool], citation_supported: list[bool]) -> None:
        self._claim_supported = iter(claim_supported)
        self._citation_supported = iter(citation_supported)

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        fields = schema.model_fields
        if "verdicts" in fields:
            item_type = get_args(fields["verdicts"].annotation)[0]
            if "claim" in item_type.model_fields:
                return schema.model_validate(
                    {"verdicts": [{"claim": "c", "supported": next(self._claim_supported)}]}
                )
            return schema.model_validate(
                {"verdicts": [{"citation_index": 1, "supported": next(self._citation_supported)}]}
            )
        raise AssertionError(f"unexpected schema: {schema}")


def _case(
    *,
    claim_labels: list[bool],
    citation_labels: list[bool],
    label_source: str = "agent_placeholder",
) -> CalibrationCase:
    return CalibrationCase(
        question="Q",
        answer="Claim one [1].",
        chunks=[{"content": "supporting context"}],
        claims=["claim one"] * len(claim_labels),
        claim_labels=claim_labels,
        citation_labels=citation_labels,
        label_source=label_source,
    )


async def test_run_calibration_computes_pooled_and_per_type_metrics() -> None:
    cases = [
        _case(claim_labels=[True], citation_labels=[True]),
        _case(claim_labels=[False], citation_labels=[True]),
    ]
    # Judge agrees on both claims (True, then False) but disagrees on both
    # citations (judge says False both times, human said True both times).
    provider = ScriptedJudge(claim_supported=[True, False], citation_supported=[False, False])

    metrics, comparisons = await run_calibration(cases, provider=provider)

    assert metrics["claim_agreement"] == 1.0
    assert metrics["citation_agreement"] == 0.0
    assert metrics["judge_agreement"] == 0.5  # 2/4 pooled labels match
    assert metrics["founder_labeled_fraction"] == 0.0
    assert len(comparisons) == 2


async def test_run_calibration_founder_labeled_fraction() -> None:
    cases = [
        _case(claim_labels=[True], citation_labels=[True], label_source="founder"),
        _case(claim_labels=[True], citation_labels=[True], label_source="agent_placeholder"),
    ]
    provider = ScriptedJudge(claim_supported=[True, True], citation_supported=[True, True])

    metrics, _ = await run_calibration(cases, provider=provider)

    assert metrics["founder_labeled_fraction"] == 0.5
