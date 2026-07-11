"""T-018: price-provenance validation gate tests.

RELEASE CRITERION (docs/phases/phase-2-agents-pricing.md T-018): this test
file is never deleted or skipped. It proves a planted model-authored figure
is caught, redrafted away or escalated, and that clean engine-derived
responses pass with zero false positives.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, get_type_hints

import asyncpg
import pytest

from app.agents.graph import build_graph
from app.agents.price_gate import GATE_ESCALATION_MESSAGE
from app.agents.state import AgentState, GraphContext
from app.api.chat import ChatRequest
from app.core import db
from app.llm.provider import ChatMessage, SchemaT
from app.pricing.validation_gate import extract_monetary_figures, validate
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider, ZeroEmbedder

# --- extraction unit tests (pure, no db) -------------------------------------


def _cents(text: str) -> list[int]:
    return [figure.cents for figure in extract_monetary_figures(text)]


def test_extracts_currency_symbol_amounts() -> None:
    assert _cents("that will be $1,299.00 total") == [129900]
    assert _cents("a $99 special") == [9900]
    assert _cents("$ 12.5 handling") == [1250]


def test_extracts_dollars_word_amounts() -> None:
    assert _cents("about 1299 dollars all in") == [129900]
    assert _cents("just 20 bucks") == [2000]
    assert _cents("129.60 USD") == [12960]


def test_extracts_spelled_out_amounts() -> None:
    assert _cents("roughly twelve hundred for the lot") == [120000]
    assert _cents("twenty dollars flat") == [2000]
    assert _cents("one thousand two hundred fifty dollars") == [125000]


def test_ignores_non_monetary_numbers() -> None:
    assert _cents("your order R-1042 ships in 3 days") == []
    assert _cents("two protectors and five cables") == []
    assert _cents("open nine to five") == []


def test_no_double_report_for_symbol_plus_word() -> None:
    assert _cents("$120 dollars") == [12000]


# --- validate() unit tests ----------------------------------------------------

_ENGINE_QUOTE = {
    "quote_id": "q",
    "line_items": [
        {
            "kind": "rule",
            "code": "screen-repair-a",
            "label": "Screen repair (tier A)",
            "quantity": 1,
            "unit_amount_cents": 12000,
            "line_total_cents": 12000,
        }
    ],
    "subtotal_cents": 12000,
    "tax_cents": 960,
    "total_cents": 12960,
    "status": "sent",
}


def test_clean_no_figure_draft_passes() -> None:
    assert validate("The quote card above shows the full breakdown.", _ENGINE_QUOTE) == []


def test_engine_derived_figures_pass() -> None:
    draft = "That's $120.00 for the repair, $9.60 tax, $129.60 total."
    assert validate(draft, _ENGINE_QUOTE) == []


def test_planted_model_authored_figure_is_caught() -> None:
    violations = validate("I can do it for $99!", _ENGINE_QUOTE)
    assert len(violations) == 1
    assert "$99" in violations[0]


def test_db_provenance_figures_pass_without_engine_quote() -> None:
    assert validate("The protector is $15.00.", None, provenance=[1500]) == []
    assert validate("The protector is $19.00.", None, provenance=[1500]) != []


def test_customer_budget_restated_is_a_violation() -> None:
    # Deliberate strictness: generated text states no amounts at all unless
    # they reconcile - even the customer's own stated budget.
    assert validate("That's over your $125 budget.", _ENGINE_QUOTE) != []


# --- API-layer half: no request schema accepts money -------------------------


def test_chat_request_schema_carries_no_money_fields() -> None:
    hints = get_type_hints(ChatRequest)
    forbidden = ("price", "cent", "amount", "total", "cost", "subtotal", "tax")
    for name in hints:
        assert not any(bad in name.lower() for bad in forbidden)


# --- graph-level: redraft loop and escalation ---------------------------------

pytestmark_db = pytest.mark.db


class GateTestProvider(BaseFakeProvider):
    """Selection call returns a fixed rule pick; successive chat_stream calls
    yield queued drafts (first can be planted-violation text)."""

    def __init__(self, drafts: list[str]) -> None:
        self._drafts = list(drafts)
        self.stream_calls: list[str] = []

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        return schema.model_validate(
            {
                "selections": [{"rule_code": "screen-repair-a", "quantity": 1}],
                "has_budget_constraint": False,
                "explanation": "One tier-A screen repair.",
            }
        )

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        self.stream_calls.append(messages[0]["content"])
        yield self._drafts.pop(0)


class PassthroughReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


def _initial_state(message: str, conversation_id: uuid.UUID) -> AgentState:
    return {
        "conversation_id": str(conversation_id),
        "tenant_id": "test",
        "messages": [{"role": "customer", "content": message}],
        "route": None,
        "route_confidence": None,
        "retrieved_chunks": [],
        "selections": [],
        "engine_quote": None,
        "draft_response": "",
        "inspection": None,
        "escalated": False,
    }


def _forced_route(route: str) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def supervisor_stub(state: AgentState) -> dict[str, Any]:
        return {"route": route, "route_confidence": 1.0}

    return supervisor_stub


async def _seed_rule_tenant(conn: asyncpg.Connection[Any]) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Gate Test Co') returning id",
        f"gate-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute(
        "insert into tenant_config (tenant_id, config) values ($1, $2)",
        tenant_id,
        json.dumps({"tax": {"rate_bps": 800}}),
    )
    await conn.execute(
        "insert into pricing_rules (tenant_id, code, label, unit_amount_cents) "
        "values ($1, 'screen-repair-a', 'Screen repair (tier A)', 12000)",
        tenant_id,
    )
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    return tenant_id, conversation_id


@pytest.fixture
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


@pytest.mark.db
async def test_planted_violation_is_redrafted_away(
    _pool: None, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_id, conversation_id = await _seed_rule_tenant(superuser_conn)
    provider = GateTestProvider(
        drafts=["I can do it for $99!", "The quote card shows the full breakdown."]
    )
    graph = build_graph(supervisor_node=_forced_route("quoting"))
    context = GraphContext(
        tenant_id=tenant_id,
        provider=provider,
        embedder=ZeroEmbedder(),
        reranker=PassthroughReranker(),
    )

    final_state = await graph.ainvoke(
        _initial_state("How much is a screen repair?", conversation_id), context=context
    )

    assert final_state["draft_response"] == "The quote card shows the full breakdown."
    assert final_state["escalated"] is False
    # The redraft prompt carried the violation back to the model.
    assert "$99" in provider.stream_calls[1]
    # Only ONE quote row was ever persisted - the redraft regenerates prose,
    # never re-runs selection or the engine.
    count = await superuser_conn.fetchval(
        "select count(*) from quotes where tenant_id = $1", tenant_id
    )
    assert count == 1


@pytest.mark.db
async def test_second_violation_escalates_with_price_provenance_reason(
    _pool: None, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_id, conversation_id = await _seed_rule_tenant(superuser_conn)
    provider = GateTestProvider(drafts=["I can do it for $99!", "Fine, $89 then!"])
    graph = build_graph(supervisor_node=_forced_route("quoting"))
    context = GraphContext(
        tenant_id=tenant_id,
        provider=provider,
        embedder=ZeroEmbedder(),
        reranker=PassthroughReranker(),
    )

    final_state = await graph.ainvoke(
        _initial_state("How much is a screen repair?", conversation_id), context=context
    )

    assert final_state["escalated"] is True
    assert final_state["escalation_reason"] == "price_provenance"
    assert final_state["draft_response"] == GATE_ESCALATION_MESSAGE


@pytest.mark.db
async def test_clean_engine_derived_response_passes_untouched(
    _pool: None, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_id, conversation_id = await _seed_rule_tenant(superuser_conn)
    # The draft restates engine figures exactly - allowed, zero false positives.
    provider = GateTestProvider(drafts=["That's $120.00 plus $9.60 tax: $129.60 total."])
    graph = build_graph(supervisor_node=_forced_route("quoting"))
    context = GraphContext(
        tenant_id=tenant_id,
        provider=provider,
        embedder=ZeroEmbedder(),
        reranker=PassthroughReranker(),
    )

    final_state = await graph.ainvoke(
        _initial_state("How much is a screen repair?", conversation_id), context=context
    )

    assert final_state["escalated"] is False
    assert len(provider.stream_calls) == 1
    assert final_state["draft_response"] == "That's $120.00 plus $9.60 tax: $129.60 total."
