"""T-034: Surface 2's Dashboards tab - cost/volume metrics from cost_logs and
conversations/escalations, plus the latest eval_runs row per run_type shown
against this project's own gate thresholds.

Threshold constants below are mirrored from evals/*.py's own gate constants
(RECALL_AT_5_GATE, FAITHFULNESS_GATE, etc.) - app/ deliberately does not
import evals/ at runtime (evals/ imports app/, never the reverse, everywhere
else in this codebase). test_dashboards_api.py's threshold-sync test keeps
the two from drifting apart. Note these are each eval's own absolute target,
not necessarily what CI's regression gate checks for generation/trajectory/
injection (run_gate.py gates those three against the previous run, not the
absolute number, since an LLM-judged score depends on which model answered).

A real tenant provisioned through onboarding will typically have ZERO
eval_runs rows - evals run in CI against seeded/scratch tenants (bytefix,
throwaway leakage/injection probes), not automatically against every tenant.
An empty eval section is the common case, not an edge case.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core import auth, db

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])

_DAILY_SERIES_DAYS = 30

# Mirrored from evals/*.py - see module docstring.
GATE_THRESHOLDS: dict[str, dict[str, float]] = {
    "retrieval": {"recall_at_5": 0.85},  # retrieval_eval.RECALL_AT_5_GATE
    "generation": {
        "faithfulness": 0.85,  # generation_eval.FAITHFULNESS_GATE
        "answer_relevancy": 0.85,  # generation_eval.RELEVANCY_GATE
    },
    "trajectory": {"tool_correctness": 0.90},  # trajectory_eval.TOOL_CORRECTNESS_GATE
    "injection": {"pass_rate": 0.80},  # injection_eval.PASS_GATE
    "leakage": {"pass_rate": 1.0},  # zero-tolerance
}


class DailyCost(BaseModel):
    day: date
    cost_usd: float


class CostDashboard(BaseModel):
    cost_today_usd: float
    cost_yesterday_usd: float
    cost_this_month_usd: float
    cost_prev_month_usd: float
    avg_cost_per_conversation_usd: float | None
    conversation_count: int
    escalated_conversation_count: int
    escalation_rate: float | None
    daily_costs: list[DailyCost]


class EvalCheck(BaseModel):
    metric: str
    value: float | None
    threshold: float
    passed: bool


class EvalRunSummary(BaseModel):
    run_type: str
    created_at: datetime
    git_sha: str
    metrics: dict[str, Any]
    checks: list[EvalCheck]
    passed: bool


class EvalDashboard(BaseModel):
    runs: list[EvalRunSummary]


@router.get("/costs", response_model=CostDashboard)
async def get_cost_dashboard(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> CostDashboard:
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    month_start = today_start.replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    series_start = today_start - timedelta(days=_DAILY_SERIES_DAYS - 1)

    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        cost_row = await conn.fetchrow(
            "select "
            "  coalesce(sum(cost_usd) filter (where created_at >= $2), 0) as cost_today, "
            "  coalesce(sum(cost_usd) filter ("
            "    where created_at >= $3 and created_at < $2), 0) as cost_yesterday, "
            "  coalesce(sum(cost_usd) filter (where created_at >= $4), 0) as cost_this_month, "
            "  coalesce(sum(cost_usd) filter ("
            "    where created_at >= $5 and created_at < $4), 0) as cost_prev_month, "
            "  coalesce(sum(cost_usd) filter ("
            "    where conversation_id is not null), 0) as conv_cost_total, "
            "  count(distinct conversation_id) filter ("
            "    where conversation_id is not null) as costed_conversations "
            "from cost_logs where tenant_id = $1",
            admin.tenant_id,
            today_start,
            yesterday_start,
            month_start,
            prev_month_start,
        )
        assert cost_row is not None

        volume_row = await conn.fetchrow(
            "select "
            "  (select count(*) from conversations where tenant_id = $1) as conversation_count, "
            "  (select count(distinct conversation_id) from escalations "
            "   where tenant_id = $1) as escalated_conversations",
            admin.tenant_id,
        )
        assert volume_row is not None

        daily_rows = await conn.fetch(
            "select (created_at at time zone 'utc')::date as day, sum(cost_usd) as cost_usd "
            "from cost_logs where tenant_id = $1 and created_at >= $2 "
            "group by 1 order by 1",
            admin.tenant_id,
            series_start,
        )

    costed_conversations = cost_row["costed_conversations"]
    avg_cost = (
        float(cost_row["conv_cost_total"]) / costed_conversations
        if costed_conversations > 0
        else None
    )
    conversation_count = volume_row["conversation_count"]
    escalated_count = volume_row["escalated_conversations"]
    escalation_rate = escalated_count / conversation_count if conversation_count > 0 else None

    by_day = {row["day"]: float(row["cost_usd"]) for row in daily_rows}
    daily_costs = [
        DailyCost(day=day, cost_usd=by_day.get(day, 0.0))
        for day in ((series_start + timedelta(days=i)).date() for i in range(_DAILY_SERIES_DAYS))
    ]

    return CostDashboard(
        cost_today_usd=float(cost_row["cost_today"]),
        cost_yesterday_usd=float(cost_row["cost_yesterday"]),
        cost_this_month_usd=float(cost_row["cost_this_month"]),
        cost_prev_month_usd=float(cost_row["cost_prev_month"]),
        avg_cost_per_conversation_usd=avg_cost,
        conversation_count=conversation_count,
        escalated_conversation_count=escalated_count,
        escalation_rate=escalation_rate,
        daily_costs=daily_costs,
    )


@router.get("/evals", response_model=EvalDashboard)
async def get_eval_dashboard(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> EvalDashboard:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select distinct on (run_type) run_type, metrics, git_sha, created_at "
            "from eval_runs where tenant_id = $1 "
            "  and run_type = any($2::text[]) "
            "order by run_type, created_at desc",
            admin.tenant_id,
            list(GATE_THRESHOLDS.keys()),
        )

    runs: list[EvalRunSummary] = []
    for row in rows:
        run_type = row["run_type"]
        metrics = json.loads(row["metrics"])
        checks: list[EvalCheck] = []
        for metric_name, threshold in GATE_THRESHOLDS[run_type].items():
            raw_value = metrics.get(metric_name)
            value = float(raw_value) if isinstance(raw_value, (int, float)) else None
            checks.append(
                EvalCheck(
                    metric=metric_name,
                    value=value,
                    threshold=threshold,
                    # Missing/non-numeric metric fails closed, matching
                    # run_gate.regression_pass's treatment of an absent metric.
                    passed=value is not None and value >= threshold,
                )
            )
        runs.append(
            EvalRunSummary(
                run_type=run_type,
                created_at=row["created_at"],
                git_sha=row["git_sha"],
                metrics=metrics,
                checks=checks,
                passed=all(check.passed for check in checks),
            )
        )

    return EvalDashboard(runs=runs)
