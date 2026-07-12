"""T-029: the CI eval gate orchestrator.

Runs the eval suite against a seeded database and decides pass/fail with two
kinds of check, matching the ticket's design:

- **Absolute gates** (security + retrieval): each eval enforces its own
  ``--gate`` threshold and we hard-fail on a non-zero exit. Leakage and
  price-provenance are zero-tolerance - they must be 100%. Retrieval recall
  has a fixed floor. These are deterministic enough to gate on an absolute
  number every run.
- **Regression gates** (LLM-judged quality: generation, trajectory,
  injection): the absolute score of an LLM-judged eval depends on which model
  answered, so gating CI on a fixed number would either rubber-stamp
  regressions or perpetually fail on a weak dev model. Instead we compare this
  run's metric to the previous run of the same type (the last main-branch
  baseline in practice) and fail only on a drop beyond a tolerance
  (``_REGRESSION_TOLERANCE`` points). The first ever run has no baseline and
  is recorded, not gated.

LLM-dependent evals only run when a chat provider is actually configured
(``LLM_API_KEY``/Azure key present) - CI without the secret still runs the
full deterministic security gate. Pure decision helpers
(:func:`absolute_pass`, :func:`regression_pass`) are unit-tested; the
subprocess/DB orchestration is the integration surface CI exercises.

Usage: ``uv run python -m evals.run_gate`` (exit 0 = gate passed).
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from dataclasses import dataclass, field
from uuid import UUID

from app.core import config, db

# Regression tolerance in absolute metric points (0-1 scale) for LLM-judged
# evals - a drop larger than this vs the previous run fails the gate.
_REGRESSION_TOLERANCE = 0.03

# Deterministic evals gated on their own absolute --gate threshold. Order is
# cheapest-first so a fast security failure surfaces before the slow ones.
_ABSOLUTE_GATES = ("leakage_eval", "retrieval_eval")

# LLM-judged evals: (module, metric key in eval_runs, run_type). Compared in
# regression mode against the previous run of the same run_type.
_REGRESSION_GATES = (
    ("generation_eval", "faithfulness", "generation"),
    ("trajectory_eval", "tool_correctness", "trajectory"),
    ("injection_eval", "pass_rate", "injection"),
)


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str


@dataclass
class GateReport:
    results: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.results.append(GateResult(name=name, passed=passed, detail=detail))


# --- pure decision helpers (unit-tested) ----------------------------------------


def absolute_pass(exit_code: int) -> bool:
    """A deterministic eval's own --gate already encodes its threshold; a zero
    exit means it passed."""
    return exit_code == 0


def regression_pass(
    current: float | None, baseline: float | None, tolerance: float = _REGRESSION_TOLERANCE
) -> tuple[bool, str]:
    """An LLM-judged metric passes if it hasn't dropped more than ``tolerance``
    below the baseline. No current metric = the eval didn't produce one (fail
    closed). No baseline = first run, nothing to regress against (pass, record
    it)."""
    if current is None:
        return False, "no current metric produced"
    if baseline is None:
        return True, f"{current:.3f} (no baseline - recorded)"
    delta = current - baseline
    # 1e-9 epsilon so a drop of exactly the tolerance (fp-representation noise
    # and all) counts as within tolerance, not beyond it.
    if delta < -tolerance - 1e-9:
        return False, f"{current:.3f} vs baseline {baseline:.3f} (drop {-delta:.3f} > {tolerance})"
    return True, f"{current:.3f} vs baseline {baseline:.3f} (delta {delta:+.3f})"


# --- orchestration --------------------------------------------------------------


def _llm_configured() -> bool:
    settings = config.get_settings()
    if settings.llm_provider == "azure":
        return bool(settings.azure_openai_api_key)
    return bool(settings.llm_api_key)


def _run_eval_subprocess(module: str, *args: str) -> int:
    print(f"\n=== running evals.{module} {' '.join(args)} ===", flush=True)
    result = subprocess.run(  # noqa: S603 - fixed module names, no shell
        [sys.executable, "-m", f"evals.{module}", *args], check=False
    )
    return result.returncode


async def _last_two_metrics(
    tenant_id: UUID, run_type: str, metric_key: str
) -> tuple[float | None, float | None]:
    """(current, baseline) - the two most recent eval_runs metric values for a
    run_type, newest first. Fewer than two rows -> baseline is None."""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select metrics ->> $2 as value from eval_runs "
            "where tenant_id = $1 and run_type = $3 order by created_at desc limit 2",
            tenant_id,
            metric_key,
            run_type,
        )
    values = [float(r["value"]) if r["value"] is not None else None for r in rows]
    current = values[0] if values else None
    baseline = values[1] if len(values) > 1 else None
    return current, baseline


async def _seeded_tenant_id() -> UUID | None:
    from seeds.seed_tenant1_phoneshop import SLUG

    async with db.tenant_context(None, "platform_admin") as conn:
        tenant_id: UUID | None = await conn.fetchval("select id from tenants where slug = $1", SLUG)
    return tenant_id


async def run_gate(*, skip_llm: bool) -> GateReport:
    report = GateReport()

    # 1. Absolute deterministic gates - hard fail on non-zero exit.
    for module in _ABSOLUTE_GATES:
        exit_code = _run_eval_subprocess(module, "--gate")
        report.add(
            module,
            absolute_pass(exit_code),
            "passed" if absolute_pass(exit_code) else f"exit {exit_code}",
        )

    # 2. LLM-judged regression gates - only when a provider is configured.
    run_llm = not skip_llm and _llm_configured()
    if not run_llm:
        for module, _metric, _run_type in _REGRESSION_GATES:
            report.add(module, True, "skipped (no LLM provider configured)")
        return report

    tenant_id = await _seeded_tenant_id()
    if tenant_id is None:
        report.add("regression-baseline", False, "seeded tenant not found")
        return report

    for module, metric_key, run_type in _REGRESSION_GATES:
        # Run without --gate: we want the eval_runs row written, then judge it
        # in regression mode ourselves rather than on its absolute threshold.
        exit_code = _run_eval_subprocess(module)
        if exit_code != 0:
            report.add(module, False, f"eval errored (exit {exit_code})")
            continue
        current, baseline = await _last_two_metrics(tenant_id, run_type, metric_key)
        passed, detail = regression_pass(current, baseline)
        report.add(module, passed, f"{metric_key}: {detail}")

    return report


def _print_report(report: GateReport) -> None:
    print("\n" + "=" * 52)
    print(f"{'gate':<28}{'status':<8}detail")
    print("-" * 52)
    for result in report.results:
        print(f"{result.name:<28}{'PASS' if result.passed else 'FAIL':<8}{result.detail}")
    print("=" * 52)
    print("GATE PASSED" if report.passed else "GATE FAILED")


async def main_async(*, skip_llm: bool) -> int:
    created_pool = False
    try:
        db.get_pool()
    except RuntimeError:
        await db.create_pool()
        created_pool = True
    try:
        report = await run_gate(skip_llm=skip_llm)
        _print_report(report)
        return 0 if report.passed else 1
    finally:
        if created_pool:
            await db.close_pool()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="run only the deterministic security/retrieval gates",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(skip_llm=args.skip_llm)))


if __name__ == "__main__":
    main()
