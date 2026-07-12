"""T-026: trajectory scorer tests - the ticket's own "scorer unit tests on
fixture trajectories", plus one DB-driven graph run proving run_case
actually captures steps, the lookup, and terminal state from a real graph
execution (fake provider, real tenant seed).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import pytest

from app.core import db
from app.llm.provider import SchemaT
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from evals.trajectory_dataset import TrajectoryCase
from evals.trajectory_eval import (
    CaseTrajectory,
    TrajectoryStep,
    check_lookup,
    check_selections,
    check_unsourced_figures,
    expected_min_steps,
    normalize_selections,
    run_case,
    score_case,
    selection_matches,
    step_efficiency,
)
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider, ZeroEmbedder

# --- fixture helpers -------------------------------------------------------------


def _trajectory(
    *,
    nodes: list[str],
    final_state: dict[str, Any],
    quote_exists: bool = False,
    escalation_exists: bool = False,
) -> CaseTrajectory:
    return CaseTrajectory(
        steps=[TrajectoryStep(node=node, update={}) for node in nodes],
        final_state=final_state,
        quote_exists=quote_exists,
        escalation_exists=escalation_exists,
        cost_usd=0.0,
    )


def _case(**overrides: Any) -> TrajectoryCase:
    defaults: dict[str, Any] = {
        "case_id": "fixture-01",
        "category": "quoting",
        "messages": [{"role": "customer", "content": "how much for a screen?"}],
        "expected_route": ["quoting"],
    }
    defaults.update(overrides)
    return TrajectoryCase(**defaults)


_ENGINE_QUOTE = {
    "quote_id": "q-1",
    "line_items": [
        {
            "kind": "rule",
            "code": "screen-repair-budget",
            "label": "Screen repair - budget/mid Android",
            "quantity": 1,
            "unit_amount_cents": 5900,
            "line_total_cents": 5900,
        },
        {
            "kind": "item",
            "item_id": "some-uuid",
            "label": "Tempered Glass Screen Protector",
            "quantity": 2,
            "unit_amount_cents": 1000,
            "line_total_cents": 2000,
        },
    ],
    "subtotal_cents": 7900,
    "tax_cents": 0,
    "total_cents": 7900,
    "status": "sent",
}


# --- normalization + matching -----------------------------------------------------


def test_normalize_selections_from_engine_quote() -> None:
    normalized = normalize_selections({"engine_quote": _ENGINE_QUOTE, "selections": []})
    assert {
        "kind": "rule",
        "code": "screen-repair-budget",
        "item_name": "Screen repair - budget/mid Android",
        "quantity": 1,
    } in normalized
    assert {
        "kind": "item",
        "code": None,
        "item_name": "Tempered Glass Screen Protector",
        "quantity": 2,
    } in normalized


def test_normalize_selections_from_recommendation_shape() -> None:
    normalized = normalize_selections(
        {
            "engine_quote": None,
            "selections": [
                {
                    "catalog_item_id": "x",
                    "name": "Phone Case - Universal",
                    "description": "d",
                    "price_cents": 1500,
                }
            ],
        }
    )
    assert normalized == [{"kind": "item", "item_name": "Phone Case - Universal"}]


def test_selection_matches_by_code_name_any_and_quantity() -> None:
    actual = {"kind": "rule", "code": "rush-fee", "item_name": "Rush service", "quantity": 1}
    assert selection_matches(actual, {"kind": "rule", "code": "rush-fee"})
    assert not selection_matches(actual, {"kind": "rule", "code": "battery-flagship"})
    assert not selection_matches(actual, {"kind": "item", "code": "rush-fee"})
    assert not selection_matches(actual, {"kind": "rule", "code": "rush-fee", "quantity": 2})

    item = {"kind": "item", "item_name": "iPhone 12 (Refurbished, 128GB)"}
    assert selection_matches(item, {"item_name_any": ["iPhone 12 (Refurbished, 128GB)", "other"]})
    assert not selection_matches(item, {"item_name_any": ["other"]})


def test_check_selections_subset_and_forbidden() -> None:
    actuals = [{"kind": "rule", "code": "screen-repair-budget", "quantity": 1}]
    assert check_selections(actuals, [{"kind": "rule", "code": "screen-repair-budget"}], []) == []
    missing = check_selections(actuals, [{"kind": "rule", "code": "battery-flagship"}], [])
    assert len(missing) == 1 and "expected selection not made" in missing[0]
    forbidden = check_selections(actuals, [], [{"code": "screen-repair-budget"}])
    assert len(forbidden) == 1 and "forbidden selection made" in forbidden[0]


# --- lookup ------------------------------------------------------------------------


def test_check_lookup_is_case_insensitive_on_ref_code() -> None:
    actual = {"ref_code": "R-1010", "found": True, "status": "cancelled", "kind": "repair"}
    assert check_lookup(actual, {"ref_code": "r-1010", "found": True, "status": "cancelled"}) == []


def test_check_lookup_flags_mismatches_and_missing_lookup() -> None:
    assert check_lookup(None, {"ref_code": "R-1", "found": True}) != []
    actual = {"ref_code": "R-1003", "found": True, "status": "pending"}
    failures = check_lookup(actual, {"ref_code": "R-1003", "found": True, "status": "shipped"})
    assert len(failures) == 1 and "status" in failures[0]
    failures = check_lookup(
        {"ref_code": "R-9999", "found": False}, {"ref_code": None, "found": False}
    )
    assert any("ref_code" in f for f in failures)


def test_check_lookup_none_expected_ref_matches_none_actual() -> None:
    result = check_lookup({"ref_code": None, "found": False}, {"ref_code": None, "found": False})
    assert result == []


# --- forbidden figures ---------------------------------------------------------------


def test_unsourced_figure_in_draft_is_flagged() -> None:
    state = {
        "draft_response": "That will be $999.99, trust me.",
        "engine_quote": _ENGINE_QUOTE,
        "selections": [],
        "retrieved_chunks": [],
    }
    failures = check_unsourced_figures(state)
    assert len(failures) == 1 and "$999.99" in failures[0]


def test_engine_and_chunk_sourced_figures_are_allowed() -> None:
    state = {
        "draft_response": "The total is $79.00; the diagnostic fee mentioned is $29.",
        "engine_quote": _ENGINE_QUOTE,
        "selections": [],
        "retrieved_chunks": [{"content": "Our diagnostic fee is $29 if you do not proceed."}],
    }
    assert check_unsourced_figures(state) == []


def test_recommendation_price_provenance_is_allowed() -> None:
    state = {
        "draft_response": "The case is $15.00.",
        "engine_quote": None,
        "selections": [{"name": "Phone Case - Universal", "price_cents": 1500}],
        "retrieved_chunks": [],
    }
    assert check_unsourced_figures(state) == []


# --- steps ---------------------------------------------------------------------------


def test_expected_min_steps_and_efficiency() -> None:
    assert expected_min_steps(["knowledge"]) == 3
    assert expected_min_steps(["quoting"]) == 4
    assert expected_min_steps(["order_status", "quoting"]) == 3  # min over any-of routes
    assert step_efficiency(4, 4) == 1.0
    assert step_efficiency(8, 4) == 0.5
    assert step_efficiency(3, 4) == 1.0  # never rewards impossible undercounts above 1.0
    assert step_efficiency(0, 4) == 0.0


# --- score_case on fixture trajectories ----------------------------------------------


def test_score_case_passes_a_clean_quoting_trajectory() -> None:
    case = _case(
        expected_selections=[{"kind": "rule", "code": "screen-repair-budget"}],
        expected_terminal={"quote_exists": True, "escalation_exists": False},
        forbidden={"unsourced_figures": True},
    )
    trajectory = _trajectory(
        nodes=["supervisor", "quoting", "price_gate", "inspection"],
        final_state={
            "route": "quoting",
            "route_reason": "customer asks for a price",
            "engine_quote": _ENGINE_QUOTE,
            "selections": [],
            "retrieved_chunks": [],
            "draft_response": "See the quote card for the details.",
        },
        quote_exists=True,
    )
    score = score_case(case, trajectory)
    assert score.correct, score.failures
    assert score.efficiency == 1.0


def test_score_case_collects_every_failure_kind() -> None:
    case = _case(
        expected_route=["order_status"],
        expected_selections=[{"kind": "rule", "code": "battery-flagship"}],
        forbidden_selections=[{"kind": "rule", "code": "screen-repair-budget"}],
        expected_lookup={"ref_code": "R-1003", "found": True},
        expected_terminal={"quote_exists": False, "escalation_exists": False},
        forbidden={"unsourced_figures": True},
    )
    trajectory = _trajectory(
        nodes=["supervisor", "quoting", "price_gate", "inspection"],
        final_state={
            "route": "quoting",
            "engine_quote": _ENGINE_QUOTE,
            "selections": [],
            "retrieved_chunks": [],
            "draft_response": "It costs $123.45.",
        },
        quote_exists=True,
    )
    score = score_case(case, trajectory)
    assert not score.correct
    joined = "\n".join(score.failures)
    assert "routed to 'quoting'" in joined
    assert "expected selection not made" in joined
    assert "forbidden selection made" in joined
    assert "no lookup happened" in joined
    assert "terminal quote_exists=True" in joined
    assert "unsourced monetary figure" in joined


# --- DB-driven: run_case observes a real graph run -----------------------------------

pytestmark_db = pytest.mark.db


class _RouteThenRefProvider(BaseFakeProvider):
    """Real supervisor + real order_status, fake model: answers the routing
    extraction with order_status and the ref extraction with the given code."""

    def __init__(self, *, ref_code: str) -> None:
        self._ref_code = ref_code

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        if "route" in schema.model_fields:
            return schema.model_validate(
                {
                    "route": "order_status",
                    "confidence": 0.95,
                    "reason": "the customer is asking about an existing repair",
                }
            )
        return schema.model_validate({"ref_code": self._ref_code, "customer_ref": None})


class _NoopReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


@pytest.mark.db
async def test_run_case_captures_steps_lookup_and_terminal_state(
    migrated_db: str, superuser_conn: asyncpg.Connection[Any]
) -> None:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        tenant_id: uuid.UUID = await superuser_conn.fetchval(
            "insert into tenants (slug, name) values ($1, 'Trajectory Eval Test Co') returning id",
            f"trajectory-eval-{uuid.uuid4().hex[:8]}",
        )
        await superuser_conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
        await superuser_conn.execute(
            "insert into orders (tenant_id, ref_code, kind, status, details) "
            "values ($1, 'R-1003', 'repair', 'ready_for_pickup', $2)",
            tenant_id,
            json.dumps({}),
        )
        async with db.tenant_context(tenant_id, "tenant_admin") as conn:
            conversation_id: uuid.UUID = await conn.fetchval(
                "insert into conversations (tenant_id) values ($1) returning id", tenant_id
            )

        case = TrajectoryCase(
            case_id="order-found-repair-01",
            category="order_status",
            messages=[{"role": "customer", "content": "Any update on my repair? Ticket R-1003."}],
            expected_route=["order_status"],
            expected_lookup={"ref_code": "R-1003", "found": True, "status": "ready_for_pickup"},
            expected_terminal={"quote_exists": False, "escalation_exists": False},
            forbidden={"unsourced_figures": True},
        )
        trajectory = await run_case(
            case,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            provider=_RouteThenRefProvider(ref_code="R-1003"),
            embedder=ZeroEmbedder(),
            reranker=_NoopReranker(),
        )

        assert [step.node for step in trajectory.steps] == [
            "supervisor",
            "order_status",
            "inspection",
        ]
        assert trajectory.final_state["lookup"] == {
            "ref_code": "R-1003",
            "found": True,
            "status": "ready_for_pickup",
            "kind": "repair",
        }
        assert trajectory.quote_exists is False
        assert trajectory.escalation_exists is False
        assert trajectory.cost_usd == 0.0  # honest zero until T-030 writes cost_logs

        score = score_case(case, trajectory)
        assert score.correct, score.failures
        assert score.efficiency == 1.0
    finally:
        await db.close_pool()
