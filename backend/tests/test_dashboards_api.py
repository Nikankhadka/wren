"""T-034: GET /api/dashboards/costs and /evals, the tenant-admin Dashboards
tab. Same JWT pattern as test_conversations_api.py.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx
import jwt
import pytest
import pytest_asyncio

from app.api.dashboards import GATE_THRESHOLDS
from app.core import db
from app.core.config import get_settings
from app.main import app
from tests.conftest import _app_dsn_for

pytestmark = pytest.mark.db

TEST_JWT_SECRET = "test-only-supabase-jwt-secret-do-not-use-in-prod"  # noqa: S105


@pytest.fixture(autouse=True)
def _supabase_jwt_secret_env() -> Iterator[None]:
    original = os.environ.get("SUPABASE_JWT_SECRET")
    os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
    get_settings.cache_clear()
    yield
    if original is None:
        os.environ.pop("SUPABASE_JWT_SECRET", None)
    else:
        os.environ["SUPABASE_JWT_SECRET"] = original
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await db.close_pool()


def _make_token(user_id: uuid.UUID) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "aud": "authenticated", "iat": now, "exp": now + 3600}
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


async def _signup_tenant_admin(client: httpx.AsyncClient) -> tuple[str, uuid.UUID]:
    user_id = uuid.uuid4()
    token = _make_token(user_id)
    slug = f"dashboards-api-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/tenants",
        json={"slug": slug, "name": "Dashboards API Test Co"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return token, uuid.UUID(response.json()["tenant_id"])


async def _insert_cost(
    conn: asyncpg.Connection[Any],
    tenant_id: uuid.UUID,
    *,
    created_at: datetime,
    cost_usd: float,
    conversation_id: uuid.UUID | None,
) -> None:
    await conn.execute(
        "insert into cost_logs (tenant_id, conversation_id, model, input_tokens, "
        "output_tokens, cost_usd, created_at) values ($1, $2, 'gpt-4o-mini', 10, 5, $3, $4)",
        tenant_id,
        conversation_id,
        cost_usd,
        created_at,
    )


async def test_dashboards_require_auth(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/dashboards/costs")).status_code == 401
    assert (await client.get("/api/dashboards/evals")).status_code == 401


async def test_cost_dashboard_empty_tenant_is_all_zeros(
    client: httpx.AsyncClient,
) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    response = await client.get(
        "/api/dashboards/costs", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cost_today_usd"] == 0
    assert body["cost_this_month_usd"] == 0
    assert body["avg_cost_per_conversation_usd"] is None
    assert body["conversation_count"] == 0
    assert body["escalation_rate"] is None
    assert len(body["daily_costs"]) == 30


async def test_eval_dashboard_empty_tenant_is_empty_list(
    client: httpx.AsyncClient,
) -> None:
    token, _tenant_id = await _signup_tenant_admin(client)
    response = await client.get(
        "/api/dashboards/evals", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["runs"] == []


async def test_cost_dashboard_reconciles_against_direct_sums(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    other_conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    series_start = today_start - timedelta(days=29)

    today_ts = today_start + timedelta(hours=1)
    yesterday_ts = today_start - timedelta(hours=1)
    # Derived from the SAME boundaries the endpoint computes (not guessed
    # day offsets), so this test is correct regardless of which calendar day
    # `now` falls on - e.g. if today is the 1st of the month, this_month_ts
    # and today_ts legitimately land in the same bucket, and the expected
    # sums below (computed from these same boundaries) account for that.
    this_month_ts = month_start + timedelta(hours=1)
    prev_month_ts = prev_month_start + timedelta(hours=1)
    old_ts = series_start - timedelta(days=1)  # just outside the 30-day window

    # (timestamp, cost_usd, conversation_id)
    rows: list[tuple[datetime, float, uuid.UUID | None]] = [
        (today_ts, 1.5, conversation_id),
        (yesterday_ts, 0.5, conversation_id),
        (this_month_ts, 2.0, other_conversation_id),
        (prev_month_ts, 9.0, None),
        (old_ts, 100.0, None),
        # A cost row with no conversation_id (e.g. an onboarding extraction
        # call) must not count toward the per-conversation average.
        (today_ts, 3.0, None),
    ]
    for ts, cost, conv in rows:
        await _insert_cost(
            superuser_conn, tenant_id, created_at=ts, cost_usd=cost, conversation_id=conv
        )

    await superuser_conn.execute(
        "insert into escalations (tenant_id, conversation_id, reason) "
        "values ($1, $2, 'customer_request')",
        tenant_id,
        conversation_id,
    )

    response = await client.get(
        "/api/dashboards/costs", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()

    expected_today = sum(cost for ts, cost, _ in rows if ts >= today_start)
    expected_yesterday = sum(
        cost for ts, cost, _ in rows if today_start - timedelta(days=1) <= ts < today_start
    )
    expected_this_month = sum(cost for ts, cost, _ in rows if ts >= month_start)
    expected_prev_month = sum(cost for ts, cost, _ in rows if prev_month_start <= ts < month_start)
    conv_rows = [(cost, conv) for _, cost, conv in rows if conv is not None]
    expected_avg = sum(cost for cost, _ in conv_rows) / len({conv for _, conv in conv_rows})
    expected_daily_total = sum(cost for ts, cost, _ in rows if ts >= series_start)

    assert body["cost_today_usd"] == pytest.approx(expected_today)
    assert body["cost_yesterday_usd"] == pytest.approx(expected_yesterday)
    assert body["cost_this_month_usd"] == pytest.approx(expected_this_month)
    assert body["cost_prev_month_usd"] == pytest.approx(expected_prev_month)
    assert body["avg_cost_per_conversation_usd"] == pytest.approx(expected_avg)
    assert body["conversation_count"] == 2
    assert body["escalated_conversation_count"] == 1
    assert body["escalation_rate"] == pytest.approx(0.5)

    daily_total = sum(row["cost_usd"] for row in body["daily_costs"])
    assert daily_total == pytest.approx(expected_daily_total)
    assert len(body["daily_costs"]) == 30


async def test_cost_dashboard_scoped_to_this_tenant_only(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    _other_token, other_tenant_id = await _signup_tenant_admin(client)

    await _insert_cost(
        superuser_conn,
        other_tenant_id,
        created_at=datetime.now(UTC),
        cost_usd=500.0,
        conversation_id=None,
    )

    response = await client.get(
        "/api/dashboards/costs", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["cost_today_usd"] == 0


async def test_escalation_rate_counts_distinct_conversations_not_rows(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    await superuser_conn.execute(
        "insert into conversations (tenant_id) values ($1), ($1), ($1)", tenant_id
    )
    # Two escalation rows on the SAME conversation must count once. A partial
    # unique index allows only one 'open' escalation per conversation
    # (migration 0011), so the second row here is already resolved.
    await superuser_conn.execute(
        "insert into escalations (tenant_id, conversation_id, reason, status) "
        "values ($1, $2, 'customer_request', 'open'), "
        "       ($1, $2, 'low_confidence', 'resolved')",
        tenant_id,
        conversation_id,
    )

    response = await client.get(
        "/api/dashboards/costs", headers={"Authorization": f"Bearer {token}"}
    )
    body = response.json()
    assert body["conversation_count"] == 4
    assert body["escalated_conversation_count"] == 1
    assert body["escalation_rate"] == pytest.approx(0.25)


async def _insert_eval_run(
    conn: asyncpg.Connection[Any],
    tenant_id: uuid.UUID,
    *,
    run_type: str,
    metrics: dict[str, Any],
    created_at: datetime,
    git_sha: str = "abc123",
) -> None:
    await conn.execute(
        "insert into eval_runs (tenant_id, run_type, metrics, git_sha, created_at) "
        "values ($1, $2, $3, $4, $5)",
        tenant_id,
        run_type,
        json.dumps(metrics),
        git_sha,
        created_at,
    )


async def test_eval_dashboard_returns_latest_row_per_run_type_with_checks(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    now = datetime.now(UTC)

    await _insert_eval_run(
        superuser_conn,
        tenant_id,
        run_type="generation",
        metrics={"faithfulness": 0.95, "answer_relevancy": 0.90},
        created_at=now - timedelta(days=1),
        git_sha="older",
    )
    await _insert_eval_run(
        superuser_conn,
        tenant_id,
        run_type="generation",
        metrics={"faithfulness": 0.60, "answer_relevancy": 0.90},
        created_at=now,
        git_sha="newer",
    )
    # A metric key this run_type doesn't gate on should be passed through in
    # `metrics` but not turned into a check.
    await _insert_eval_run(
        superuser_conn,
        tenant_id,
        run_type="leakage",
        metrics={"pass_rate": 1.0, "cases": 4},
        created_at=now,
    )
    # run_type 'full' is a valid DB value but nothing writes it today and it
    # has no threshold entry - must be excluded, not crash.
    await _insert_eval_run(superuser_conn, tenant_id, run_type="full", metrics={}, created_at=now)

    response = await client.get(
        "/api/dashboards/evals", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    runs = {row["run_type"]: row for row in response.json()["runs"]}

    assert set(runs.keys()) == {"generation", "leakage"}

    generation = runs["generation"]
    assert generation["git_sha"] == "newer"
    assert generation["passed"] is False
    checks = {c["metric"]: c for c in generation["checks"]}
    assert checks["faithfulness"]["value"] == pytest.approx(0.60)
    assert checks["faithfulness"]["passed"] is False
    assert checks["answer_relevancy"]["passed"] is True

    leakage = runs["leakage"]
    assert leakage["passed"] is True
    assert leakage["metrics"]["cases"] == 4


async def test_eval_dashboard_missing_metric_key_fails_closed(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    token, tenant_id = await _signup_tenant_admin(client)
    await _insert_eval_run(
        superuser_conn,
        tenant_id,
        run_type="trajectory",
        metrics={"step_efficiency": 0.9},  # no tool_correctness key at all
        created_at=datetime.now(UTC),
    )

    response = await client.get(
        "/api/dashboards/evals", headers={"Authorization": f"Bearer {token}"}
    )
    trajectory = next(r for r in response.json()["runs"] if r["run_type"] == "trajectory")
    check = trajectory["checks"][0]
    assert check["metric"] == "tool_correctness"
    assert check["value"] is None
    assert check["passed"] is False
    assert trajectory["passed"] is False


def test_gate_thresholds_match_each_evals_module_constant() -> None:
    """Keeps app/dashboards.py's mirrored thresholds honest against the real
    gate constants in evals/*.py without app/ importing evals/ at runtime."""
    from evals.generation_eval import FAITHFULNESS_GATE, RELEVANCY_GATE
    from evals.injection_eval import PASS_GATE
    from evals.retrieval_eval import RECALL_AT_5_GATE
    from evals.trajectory_eval import TOOL_CORRECTNESS_GATE

    assert GATE_THRESHOLDS["retrieval"]["recall_at_5"] == RECALL_AT_5_GATE
    assert GATE_THRESHOLDS["generation"]["faithfulness"] == FAITHFULNESS_GATE
    assert GATE_THRESHOLDS["generation"]["answer_relevancy"] == RELEVANCY_GATE
    assert GATE_THRESHOLDS["trajectory"]["tool_correctness"] == TOOL_CORRECTNESS_GATE
    assert GATE_THRESHOLDS["injection"]["pass_rate"] == PASS_GATE
    assert GATE_THRESHOLDS["leakage"]["pass_rate"] == 1.0
