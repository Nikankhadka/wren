"""T-024 [EDD]: judge calibration - measures whether generation_eval.py's
LLM judge (judge_claims, score_citation_faithfulness) agrees with real
human judgment.

**Every row in datasets/judge_calibration.jsonl currently carries
``label_source: "agent_placeholder"``** - these are agent-authored labels,
not the founder's. The ticket's own text is explicit that "labels are the
founder's" and must be hand-written BEFORE the judge ever sees them; an
agent generating its own "ground truth" would just measure self-consistency
between two LLM calls, which is not what calibration means. This script and
its tests are real and fully wired, but ``run_calibration``'s output does
not yet mean what T-024 wants it to mean until every row is founder-
reviewed and its ``label_source`` flipped to ``"founder"`` - enforced
structurally: ``--gate`` fails on ``founder_labeled_fraction < 1.0``
regardless of the agreement number, so this cannot silently pass as a real
calibration. Use ``--print-blind`` to label fresh without seeing the
agent's placeholder verdicts first (avoids anchoring).

Claim/citation UNITS are frozen in the dataset (not re-extracted at judge
time) - claim extraction and sentence-citation parsing are themselves part
of what would need calibrating, and re-extracting would silently break
positional alignment with the hand-labels every run. ``judge_claims`` and
``score_citation_faithfulness`` (both from generation_eval.py) are called
directly against the frozen units instead.

Agreement and kappa are reported per label type (claim, citation) AND
pooled (judge_agreement/judge_kappa, both being the same binary
supported/unsupported judgment) - two different judge prompts are being
calibrated, and pooling only would hide one being broken while the other
compensates. The 80% gate applies to the pooled judge_agreement.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.core import db
from app.llm.dependency import get_llm_provider
from app.llm.provider import LLMProvider
from evals.generation_eval import (
    CitationVerdict,
    ClaimVerdict,
    extract_cited_sentences,
    judge_claims,
    score_citation_faithfulness,
)
from seeds.seed_tenant1_phoneshop import SLUG

DATASET_PATH = Path(__file__).parent / "datasets" / "judge_calibration.jsonl"
AGREEMENT_GATE = 0.80


@dataclass(frozen=True)
class CalibrationCase:
    question: str
    answer: str
    chunks: list[dict[str, Any]]
    claims: list[str]
    claim_labels: list[bool]
    citation_labels: list[bool]
    label_source: str


def _citation_units(answer: str, chunk_count: int) -> list[tuple[str, int]]:
    """The flattened (sentence, citation_index) pairs
    ``score_citation_faithfulness`` will judge, in the exact order its
    verdicts come back - ``citation_labels[i]`` must describe ``units[i]``."""
    units: list[tuple[str, int]] = []
    for sentence, indices in extract_cited_sentences(answer):
        for index in indices:
            if index < 1 or index > chunk_count:
                raise ValueError(
                    f"citation index {index} out of range for {chunk_count} chunks - "
                    "judge_calibration.jsonl rows must not exercise the out-of-range "
                    "path (that's deterministic, not something a judge is calibrated "
                    "against) - fix the row's answer or chunks"
                )
            units.append((sentence, index))
    return units


def load_cases(path: Path = DATASET_PATH) -> list[CalibrationCase]:
    cases = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        if "_comment" in raw:
            continue
        case = CalibrationCase(
            question=raw["question"],
            answer=raw["answer"],
            chunks=raw["chunks"],
            claims=raw["claims"],
            claim_labels=raw["claim_labels"],
            citation_labels=raw["citation_labels"],
            label_source=raw["label_source"],
        )
        if len(case.claims) != len(case.claim_labels):
            raise ValueError(f"claim/claim_labels length mismatch: {case.question!r}")
        units = _citation_units(case.answer, len(case.chunks))
        if len(units) != len(case.citation_labels):
            raise ValueError(
                f"citation_labels length {len(case.citation_labels)} != "
                f"{len(units)} citations parsed from answer: {case.question!r}"
            )
        # A sentence carrying the same [n] marker twice is ONE judged unit
        # repeated - the judge receives the identical sentence/chunk pair for
        # both positions, so per-clause True/False intent is inexpressible
        # there and conflicting labels would silently cap agreement at 50%.
        # Split the answer into separate sentences to label clauses apart.
        seen: dict[tuple[str, int], bool] = {}
        for unit, label in zip(units, case.citation_labels, strict=True):
            if unit in seen and seen[unit] != label:
                raise ValueError(
                    f"identical citation unit carries conflicting labels "
                    f"(sentence cited the same chunk twice): {case.question!r}"
                )
            seen[unit] = label
        if case.label_source not in ("founder", "agent_placeholder"):
            raise ValueError(f"unknown label_source {case.label_source!r}: {case.question!r}")
        cases.append(case)
    return cases


# --- pure metrics (unit-tested with fixture confusion matrices) ---------------


def agreement(human: list[bool], judge: list[bool]) -> float:
    if not human:
        raise ValueError("agreement() called with zero labels - an empty calibration is a bug")
    matches = sum(1 for h, j in zip(human, judge, strict=True) if h == j)
    return matches / len(human)


def cohens_kappa(human: list[bool], judge: list[bool]) -> float:
    """Standard 2x2 Cohen's kappa. ``pe == 1`` is a degenerate case with no
    meaningful chance-corrected score; it only occurs when both raters used
    a single class AND it's the same class (all-True/all-True or
    all-False/all-False), which forces ``po == 1``, so it returns 1.0 by
    convention (the 0.0 arm is defensive - unreachable in exact arithmetic;
    e.g. human all-True vs judge all-False gives ``pe == 0``, not 1, and
    scores 0.0 through the normal formula)."""
    if not human:
        raise ValueError("cohens_kappa() called with zero labels")
    pairs = list(zip(human, judge, strict=True))
    n = len(pairs)
    a = sum(1 for h, j in pairs if h and j)
    b = sum(1 for h, j in pairs if h and not j)
    c = sum(1 for h, j in pairs if not h and j)
    d = sum(1 for h, j in pairs if not h and not j)
    po = (a + d) / n
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / (n * n)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


@dataclass
class CaseComparison:
    question: str
    claim_human: list[bool]
    claim_judge: list[bool]
    citation_human: list[bool]
    citation_judge: list[bool]


def _claim_verdicts_to_flags(verdicts: list[ClaimVerdict]) -> list[bool]:
    return [v.supported for v in verdicts]


def _citation_verdicts_to_flags(verdicts: list[CitationVerdict]) -> list[bool]:
    return [v.supported for v in verdicts]


async def run_calibration(
    cases: list[CalibrationCase], *, provider: LLMProvider
) -> tuple[dict[str, float], list[CaseComparison]]:
    comparisons: list[CaseComparison] = []

    for case in cases:
        context = "\n\n".join(chunk["content"] for chunk in case.chunks)
        claim_verdicts = await judge_claims(case.claims, context, provider=provider)
        citation_verdicts = await score_citation_faithfulness(
            case.answer, case.chunks, provider=provider
        )
        comparisons.append(
            CaseComparison(
                question=case.question,
                claim_human=case.claim_labels,
                claim_judge=_claim_verdicts_to_flags(claim_verdicts),
                citation_human=case.citation_labels,
                citation_judge=_citation_verdicts_to_flags(citation_verdicts),
            )
        )

    all_claim_human = [h for c in comparisons for h in c.claim_human]
    all_claim_judge = [j for c in comparisons for j in c.claim_judge]
    all_citation_human = [h for c in comparisons for h in c.citation_human]
    all_citation_judge = [j for c in comparisons for j in c.citation_judge]
    pooled_human = all_claim_human + all_citation_human
    pooled_judge = all_claim_judge + all_citation_judge

    founder_labeled_fraction = sum(1 for c in cases if c.label_source == "founder") / len(cases)

    metrics = {
        "cases": float(len(cases)),
        "claim_labels": float(len(all_claim_human)),
        "citation_labels": float(len(all_citation_human)),
        "claim_agreement": agreement(all_claim_human, all_claim_judge),
        "claim_kappa": cohens_kappa(all_claim_human, all_claim_judge),
        "citation_agreement": agreement(all_citation_human, all_citation_judge),
        "citation_kappa": cohens_kappa(all_citation_human, all_citation_judge),
        "judge_agreement": agreement(pooled_human, pooled_judge),
        "judge_kappa": cohens_kappa(pooled_human, pooled_judge),
        "judge_calibration": 1.0,
        "founder_labeled_fraction": founder_labeled_fraction,
    }
    return metrics, comparisons


def _git_sha() -> str:
    result = subprocess.run(  # noqa: S603 - fixed args, no shell, dev-tool only
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


async def _write_eval_run(conn: Any, tenant_id: Any, metrics: dict[str, float]) -> None:
    git_sha = await run_in_threadpool(_git_sha)
    await conn.execute(
        "insert into eval_runs (tenant_id, run_type, metrics, git_sha) "
        "values ($1, 'generation', $2, $3)",
        tenant_id,
        json.dumps(metrics),
        git_sha,
    )


def _print_table(metrics: dict[str, float]) -> None:
    print(f"{'metric':<28}{'value'}")
    print("-" * 40)
    for key, value in metrics.items():
        print(f"{key:<28}{value:.3f}" if isinstance(value, float) else f"{key:<28}{value}")


def _print_disagreements(comparisons: list[CaseComparison]) -> None:
    for comparison in comparisons:
        claim_mismatch = any(
            h != j for h, j in zip(comparison.claim_human, comparison.claim_judge, strict=True)
        )
        citation_mismatch = any(
            h != j
            for h, j in zip(comparison.citation_human, comparison.citation_judge, strict=True)
        )
        if claim_mismatch or citation_mismatch:
            print(f"\nQ: {comparison.question}")
            print(f"  claim human={comparison.claim_human} judge={comparison.claim_judge}")
            print(f"  citation human={comparison.citation_human} judge={comparison.citation_judge}")


def _print_blind(cases: list[CalibrationCase]) -> None:
    for case in cases:
        print(f"\nQ: {case.question}")
        print(f"A: {case.answer}")
        print("Chunks:")
        for i, chunk in enumerate(case.chunks, start=1):
            print(f"  [{i}] {chunk['content']}")
        print(f"Claims to label (True=supported by chunks above): {case.claims}")
        cited = extract_cited_sentences(case.answer)
        print(f"Citations to label (True=chunk supports the specific sentence): {cited}")


async def main_async(*, gate: bool, verbose: bool, print_blind: bool) -> int:
    cases = load_cases()

    if print_blind:
        _print_blind(cases)
        return 0

    created_pool = False
    try:
        db.get_pool()
    except RuntimeError:
        await db.create_pool()
        created_pool = True

    try:
        async with db.tenant_context(None, "platform_admin") as conn:
            tenant_id = await conn.fetchval("select id from tenants where slug = $1", SLUG)
        if tenant_id is None:
            print(f"tenant '{SLUG}' not seeded - run seeds.seed_tenant1_phoneshop first")
            return 1

        provider = get_llm_provider()
        metrics, comparisons = await run_calibration(cases, provider=provider)

        async with db.tenant_context(tenant_id, "tenant_admin") as conn:
            await _write_eval_run(conn, tenant_id, metrics)

        _print_table(metrics)
        if verbose:
            _print_disagreements(comparisons)

        if gate:
            if metrics["founder_labeled_fraction"] < 1.0:
                print(
                    "GATE FAILED: founder_labeled_fraction "
                    f"{metrics['founder_labeled_fraction']:.3f} < 1.0 - dataset still "
                    "contains agent-placeholder labels, not real calibration"
                )
                return 1
            if metrics["judge_agreement"] < AGREEMENT_GATE:
                print(
                    f"GATE FAILED: judge_agreement {metrics['judge_agreement']:.3f} "
                    f"< {AGREEMENT_GATE}"
                )
                return 1
        return 0
    finally:
        if created_pool:
            await db.close_pool()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate",
        action="store_true",
        help=(
            f"exit non-zero if judge_agreement < {AGREEMENT_GATE} or labels aren't founder-reviewed"
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="print per-case disagreements")
    parser.add_argument(
        "--print-blind",
        action="store_true",
        help="print cases without labels (for fresh hand-labeling) and exit",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(main_async(gate=args.gate, verbose=args.verbose, print_blind=args.print_blind))
    )


if __name__ == "__main__":
    main()
