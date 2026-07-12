"""T-026: trajectory scorer - drives every T-025 golden case through the
REAL graph (real supervisor routing, real specialists, real tenant seed)
and scores what the agent actually did, not just what it said.

Per case:
- **tool/argument correctness** - the supervisor picked an expected route,
  every expected selection (rule code / catalog item name, quantity)
  appears in what the agent actually selected, no forbidden selection
  appears, order lookups hit the expected ref_code/found/status, and the
  terminal DB state matches (quote row exists / escalation row exists).
  The ``forbidden.unsourced_figures`` check reuses the T-018 validation
  gate's monetary-figure extraction: every figure in the final draft must
  reconcile to engine-quote output, DB-sourced selection provenance, or a
  figure present verbatim in a retrieved chunk.
- **step efficiency** - actual node executions vs the route's known
  minimum (supervisor + specialist [+ price_gate for money routes]
  + inspection), as a <=1.0 ratio.
- **cost-per-task** - sum of cost_logs for the case's conversation.
  Honest zero until T-030 wires cost accounting; the query is real.
- **reasoning quality** - an LLM judge grades whether the supervisor's own
  stated route reason actually justifies the route it picked.

Trajectories are observed via ``graph.astream(stream_mode="updates")`` -
one event per node execution, no app instrumentation needed - plus two
observability keys T-026 added to state (``route_reason``, ``lookup``).
Aggregates to eval_runs (run_type trajectory); ``--gate`` fails below 90%
tool-call correctness. Failing cases always print their full trajectory
(accept criterion), passing ones only under ``--verbose``.

Like generation_eval.py (and unlike the leakage test), this needs a real
LLM provider - it measures behavior quality, not a structural invariant.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from openai import RateLimitError
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from app.agents.graph import build_graph
from app.agents.state import AgentState, GraphContext
from app.core import config, db
from app.llm.dependency import get_llm_provider
from app.llm.embedder import Embedder, get_embedder
from app.llm.provider import LLMProvider
from app.pricing.validation_gate import allowed_cents, extract_monetary_figures
from app.retrieval.rerank import Reranker, get_reranker
from evals.trajectory_dataset import TrajectoryCase, load_cases, sync_eval_cases
from seeds.seed_tenant1_phoneshop import SLUG

TOOL_CORRECTNESS_GATE = 0.90

# Minimum node executions for a clean pass through each route: supervisor +
# specialist + inspection, with price_gate added for the two money routes
# (see app/agents/graph.py's topology).
_MIN_STEPS_BY_ROUTE = {
    "knowledge": 3,
    "order_status": 3,
    "escalation": 3,
    "recommendation": 4,
    "quoting": 4,
}


@dataclass(frozen=True)
class TrajectoryStep:
    node: str
    update: dict[str, Any]


@dataclass
class CaseTrajectory:
    steps: list[TrajectoryStep]
    final_state: dict[str, Any]
    quote_exists: bool
    escalation_exists: bool
    cost_usd: float


@dataclass
class CaseScore:
    case_id: str
    category: str
    correct: bool
    failures: list[str]
    steps_actual: int
    steps_expected_min: int
    efficiency: float
    cost_usd: float
    reasoning_grade: float | None = None
    trajectory: CaseTrajectory | None = field(default=None, repr=False)


# --- pure scoring functions (unit-tested on fixture trajectories) ---------------


def normalize_selections(final_state: dict[str, Any]) -> list[dict[str, Any]]:
    """One common shape for what the agent actually selected, from either
    money route. Quoting's ground truth is the engine quote's line items
    (kind/code or item label + quantity - the engine resolved them from the
    DB); recommendation's is its DB-refetched selections (name)."""
    normalized: list[dict[str, Any]] = []
    engine_quote = final_state.get("engine_quote")
    if engine_quote:
        for item in engine_quote.get("line_items", []):
            normalized.append(
                {
                    "kind": item["kind"],
                    "code": item.get("code"),
                    "item_name": item["label"],
                    "quantity": item["quantity"],
                }
            )
    if not engine_quote:
        for selection in final_state.get("selections") or []:
            if "name" in selection:  # recommendation's DB-refetched shape
                normalized.append({"kind": "item", "item_name": selection["name"]})
    return normalized


def selection_matches(actual: dict[str, Any], matcher: dict[str, Any]) -> bool:
    if "kind" in matcher and actual.get("kind") != matcher["kind"]:
        return False
    if "code" in matcher and actual.get("code") != matcher["code"]:
        return False
    if "item_name" in matcher and actual.get("item_name") != matcher["item_name"]:
        return False
    if "item_name_any" in matcher and actual.get("item_name") not in matcher["item_name_any"]:
        return False
    return not ("quantity" in matcher and actual.get("quantity") != matcher["quantity"])


def check_selections(
    actuals: list[dict[str, Any]],
    expected: list[dict[str, Any]],
    forbidden: list[dict[str, Any]],
) -> list[str]:
    failures = []
    for matcher in expected:
        if not any(selection_matches(actual, matcher) for actual in actuals):
            failures.append(f"expected selection not made: {matcher}")
    for matcher in forbidden:
        if any(selection_matches(actual, matcher) for actual in actuals):
            failures.append(f"forbidden selection made: {matcher}")
    return failures


def check_lookup(actual: dict[str, Any] | None, expected: dict[str, Any] | None) -> list[str]:
    if expected is None:
        return []
    if actual is None:
        return [f"expected a lookup {expected} but no lookup happened"]
    failures = []
    expected_ref = expected.get("ref_code")
    actual_ref = actual.get("ref_code")
    # Case-insensitive: the customer may type 'r-1010', the DB row holds
    # 'R-1010' - both refer to the same order.
    if (expected_ref or "").casefold() != (actual_ref or "").casefold():
        failures.append(f"lookup ref_code {actual_ref!r} != expected {expected_ref!r}")
    if actual.get("found") != expected.get("found"):
        failures.append(f"lookup found={actual.get('found')} != expected {expected.get('found')}")
    if "status" in expected and actual.get("status") != expected["status"]:
        failures.append(
            f"lookup status {actual.get('status')!r} != expected {expected['status']!r}"
        )
    return failures


def check_unsourced_figures(final_state: dict[str, Any]) -> list[str]:
    """Every monetary figure in the final draft must reconcile to the
    engine quote, recommendation's DB-sourced price provenance, or a figure
    stated verbatim in a retrieved chunk (a knowledge answer quoting a real
    KB price is sourced - T-021's precedent)."""
    provenance = [
        int(selection["price_cents"])
        for selection in final_state.get("selections") or []
        if "price_cents" in selection
    ]
    allowed = allowed_cents(final_state.get("engine_quote"), provenance)
    for chunk in final_state.get("retrieved_chunks") or []:
        allowed |= {figure.cents for figure in extract_monetary_figures(chunk["content"])}
    return [
        f"unsourced monetary figure in draft: {figure.raw!r}"
        for figure in extract_monetary_figures(final_state.get("draft_response", ""))
        if figure.cents not in allowed
    ]


def expected_min_steps(expected_routes: list[str]) -> int:
    return min(_MIN_STEPS_BY_ROUTE[route] for route in expected_routes)


def step_efficiency(actual_steps: int, minimum: int) -> float:
    if actual_steps <= 0:
        return 0.0
    return min(1.0, minimum / actual_steps)


def score_case(case: TrajectoryCase, trajectory: CaseTrajectory) -> CaseScore:
    final_state = trajectory.final_state
    failures: list[str] = []

    route = final_state.get("route")
    if route not in case.expected_route:
        failures.append(f"routed to {route!r}, expected one of {case.expected_route}")

    failures += check_selections(
        normalize_selections(final_state), case.expected_selections, case.forbidden_selections
    )
    failures += check_lookup(final_state.get("lookup"), case.expected_lookup)

    for key, expected_value in case.expected_terminal.items():
        actual_value = {
            "quote_exists": trajectory.quote_exists,
            "escalation_exists": trajectory.escalation_exists,
        }[key]
        if actual_value != expected_value:
            failures.append(f"terminal {key}={actual_value}, expected {expected_value}")

    if case.forbidden.get("unsourced_figures"):
        failures += check_unsourced_figures(final_state)

    minimum = expected_min_steps(case.expected_route)
    actual_steps = len(trajectory.steps)
    return CaseScore(
        case_id=case.case_id,
        category=case.category,
        correct=not failures,
        failures=failures,
        steps_actual=actual_steps,
        steps_expected_min=minimum,
        efficiency=step_efficiency(actual_steps, minimum),
        cost_usd=trajectory.cost_usd,
        trajectory=trajectory,
    )


# --- reasoning-quality judge ----------------------------------------------------


class ReasoningVerdict(BaseModel):
    justified: bool = False
    reason: str = ""


async def judge_route_reason(
    customer_message: str,
    route: str | None,
    route_reason: str | None,
    *,
    provider: LLMProvider,
) -> float | None:
    """1.0 if an LLM judge finds the supervisor's stated reason actually
    justifies the route it picked for this message, else 0.0. None when
    there is nothing to judge (no reason recorded)."""
    if not route or not route_reason:
        return None
    verdict = await provider.extract(
        system_prompt=(
            "A routing supervisor read a customer message, picked a specialist "
            "route, and stated its reason. Judge whether the stated reason is "
            "coherent and actually justifies that route for that message - not "
            "whether you would have routed differently, only whether the "
            "reasoning holds together.\n\n"
            f"Customer message: {customer_message!r}\n"
            f"Chosen route: {route}\n"
            f"Stated reason: {route_reason!r}"
        ),
        user_input="Is the stated reason a coherent justification for the chosen route?",
        schema=ReasoningVerdict,
    )
    return 1.0 if verdict.justified else 0.0


# --- graph driving ---------------------------------------------------------------


async def run_case(
    case: TrajectoryCase,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    provider: LLMProvider,
    embedder: Embedder,
    reranker: Reranker,
) -> CaseTrajectory:
    graph = build_graph()  # the REAL supervisor - routing itself is under test
    context = GraphContext(
        tenant_id=tenant_id, provider=provider, embedder=embedder, reranker=reranker
    )
    initial_state: AgentState = {
        "conversation_id": str(conversation_id),
        "tenant_id": str(tenant_id),
        "messages": list(case.messages),
        "route": None,
        "route_confidence": None,
        "retrieved_chunks": [],
        "selections": [],
        "engine_quote": None,
        "draft_response": "",
        "inspection": None,
        "escalated": False,
    }

    steps: list[TrajectoryStep] = []
    final_state: dict[str, Any] = dict(initial_state)
    async for event in graph.astream(initial_state, context=context, stream_mode="updates"):
        for node, update in event.items():
            steps.append(TrajectoryStep(node=node, update=update or {}))
            final_state.update(update or {})

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        quote_exists: bool = await conn.fetchval(
            "select exists(select 1 from quotes where conversation_id = $1)", conversation_id
        )
        escalation_exists: bool = await conn.fetchval(
            "select exists(select 1 from escalations where conversation_id = $1)", conversation_id
        )
        cost_usd = await conn.fetchval(
            "select coalesce(sum(cost_usd), 0) from cost_logs where conversation_id = $1",
            conversation_id,
        )

    return CaseTrajectory(
        steps=steps,
        final_state=final_state,
        quote_exists=quote_exists,
        escalation_exists=escalation_exists,
        cost_usd=float(cost_usd),
    )


_RETRY_ATTEMPTS = 6


def _retry_after_seconds(error: RateLimitError, attempt: int) -> float:
    """Honor the provider's Retry-After header when present, else back off
    exponentially. Capped so a pathological header can't stall the run."""
    header: str | None = error.response.headers.get("Retry-After")
    if header is not None:
        try:
            seconds = float(header)
        except ValueError:
            pass
        else:
            return min(120.0, max(1.0, seconds))
    return min(120.0, 5.0 * float(2**attempt))


async def _with_rate_limit_retry[T](coro_factory: Callable[[], Awaitable[T]]) -> T:
    """Free-tier models fail transiently in two documented ways (T-017/T-020
    memory entries): upstream 429s, and occasionally emitting malformed JSON
    for a structured-output call (surfaces as pydantic ValidationError from
    the openai SDK's parse). Without retry, either one aborts the whole eval
    and burns every LLM call already spent on earlier cases. RateLimitError
    is the openai-SDK type both current provider bindings raise; a resample
    usually fixes malformed JSON, so it gets a short fixed delay."""
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return await coro_factory()
        except RateLimitError as error:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            delay = _retry_after_seconds(error, attempt)
            print(
                f"  rate-limited; retrying in {delay:.0f}s "
                f"(attempt {attempt + 1}/{_RETRY_ATTEMPTS})",
                flush=True,
            )
            await asyncio.sleep(delay)
        except ValidationError:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            print(
                f"  malformed structured output; resampling "
                f"(attempt {attempt + 1}/{_RETRY_ATTEMPTS})",
                flush=True,
            )
            await asyncio.sleep(2.0)
    raise AssertionError("unreachable")  # pragma: no cover


async def run_eval(
    *,
    tenant_id: UUID,
    cases: list[TrajectoryCase],
    provider: LLMProvider,
    embedder: Embedder,
    reranker: Reranker,
) -> tuple[dict[str, float], list[CaseScore]]:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await sync_eval_cases(conn, tenant_id, cases)
        # Real conversation rows, same reason as generation_eval.py: the
        # escalation node UUID()s conversation_id and writes real rows.
        conversation_ids: list[UUID] = [
            await conn.fetchval(
                "insert into conversations (tenant_id) values ($1) returning id", tenant_id
            )
            for _ in cases
        ]

    scores: list[CaseScore] = []
    for index, (case, conversation_id) in enumerate(
        zip(cases, conversation_ids, strict=True), start=1
    ):
        print(f"[{index}/{len(cases)}] {case.case_id}", flush=True)
        trajectory = await _with_rate_limit_retry(
            lambda case=case, conversation_id=conversation_id: run_case(  # type: ignore[misc]
                case,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                provider=provider,
                embedder=embedder,
                reranker=reranker,
            )
        )
        score = score_case(case, trajectory)
        score.reasoning_grade = await _with_rate_limit_retry(
            lambda case=case, trajectory=trajectory: judge_route_reason(  # type: ignore[misc]
                case.messages[-1]["content"],
                trajectory.final_state.get("route"),
                trajectory.final_state.get("route_reason"),
                provider=provider,
            )
        )
        scores.append(score)

    graded = [s.reasoning_grade for s in scores if s.reasoning_grade is not None]
    metrics: dict[str, float] = {
        "cases": float(len(scores)),
        "tool_correctness": (
            sum(1.0 for s in scores if s.correct) / len(scores) if scores else 0.0
        ),
        "step_efficiency": (sum(s.efficiency for s in scores) / len(scores) if scores else 0.0),
        "total_cost_usd": sum(s.cost_usd for s in scores),
    }
    if scores:
        metrics["avg_cost_usd"] = metrics["total_cost_usd"] / len(scores)
    if graded:
        metrics["reasoning_quality"] = sum(graded) / len(graded)
    return metrics, scores


# --- reporting -------------------------------------------------------------------


def _git_sha() -> str:
    result = subprocess.run(  # noqa: S603 - fixed args, no shell, dev-tool only
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


async def _write_eval_run(conn: Any, tenant_id: UUID, metrics: dict[str, float]) -> None:
    git_sha = await run_in_threadpool(_git_sha)
    await conn.execute(
        "insert into eval_runs (tenant_id, run_type, metrics, git_sha) "
        "values ($1, 'trajectory', $2, $3)",
        tenant_id,
        json.dumps(metrics),
        git_sha,
    )


def print_trajectory(score: CaseScore) -> None:
    print(f"\n=== {score.case_id} ({score.category}) - {'PASS' if score.correct else 'FAIL'} ===")
    for failure in score.failures:
        print(f"  FAILURE: {failure}")
    print(
        f"  steps={score.steps_actual} (min {score.steps_expected_min}, "
        f"efficiency {score.efficiency:.2f}) cost=${score.cost_usd:.4f} "
        f"reasoning={score.reasoning_grade if score.reasoning_grade is not None else 'n/a'}"
    )
    if score.trajectory is None:
        return
    for i, step in enumerate(score.trajectory.steps, start=1):
        keys = ", ".join(sorted(step.update)) or "(no update)"
        print(f"  step {i}: {step.node} -> {keys}")
    final = score.trajectory.final_state
    print(f"  route={final.get('route')!r} reason={final.get('route_reason')!r}")
    if final.get("lookup") is not None:
        print(f"  lookup={final.get('lookup')}")
    if final.get("engine_quote"):
        print(f"  engine_quote={json.dumps(final['engine_quote'])}")
    print(f"  draft: {final.get('draft_response', '')!r}")


def _print_table(metrics: dict[str, float]) -> None:
    print(f"{'metric':<24}{'value'}")
    print("-" * 36)
    for key, value in metrics.items():
        print(f"{key:<24}{value:.3f}")


async def main_async(*, gate: bool, verbose: bool) -> int:
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

        settings = config.get_settings()
        metrics, scores = await run_eval(
            tenant_id=tenant_id,
            cases=load_cases(),
            provider=get_llm_provider(),
            embedder=get_embedder(settings),
            reranker=get_reranker(settings),
        )

        async with db.tenant_context(tenant_id, "tenant_admin") as conn:
            await _write_eval_run(conn, tenant_id, metrics)

        _print_table(metrics)
        # Failing cases ALWAYS print their full trajectory (T-026 accept
        # criterion); passing ones only when asked.
        for score in scores:
            if not score.correct or verbose:
                print_trajectory(score)

        if gate and metrics["tool_correctness"] < TOOL_CORRECTNESS_GATE:
            print(
                f"GATE FAILED: tool_correctness {metrics['tool_correctness']:.3f} "
                f"(>= {TOOL_CORRECTNESS_GATE})"
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
        help=f"exit non-zero if tool_correctness < {TOOL_CORRECTNESS_GATE}",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print full trajectories for passing cases too"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(gate=args.gate, verbose=args.verbose)))


if __name__ == "__main__":
    main()
