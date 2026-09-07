"""T-044: Quoting agent tests - tool-driven agent node calls get_quote_inputs
tool, draft node persists quote row and composes explanation.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
from pydantic import BaseModel

from app.agents.agent_node import CalculateQuoteArgs, GetQuoteInputsArgs, SelectionChoice
from app.agents.graph import build_graph
from app.agents.state import AgentState, GraphContext
from app.ingestion.chunker import chunk_catalog_item
from app.llm.provider import ToolCall, ToolTurn
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from app.shared import db
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, ToolAwareFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


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


async def _seed_quoting_tenant(
    conn: asyncpg.Connection[Any], *, tax_rate_bps: int = 0
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Quote Test Co') returning id",
        f"quoting-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute(
        "insert into tenant_config (tenant_id, config) values ($1, $2)",
        tenant_id,
        json.dumps({"tax": {"rate_bps": tax_rate_bps}} if tax_rate_bps else {}),
    )
    await conn.execute(
        "insert into pricing_rules (tenant_id, code, label, unit_amount_cents) "
        "values ($1, 'screen-repair-a', 'Screen repair (tier A)', 12000)",
        tenant_id,
    )
    document_id: uuid.UUID = await conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'catalog', 'catalog', 'ready') returning id",
        tenant_id,
    )
    item_id: uuid.UUID = await conn.fetchval(
        "insert into offerings (tenant_id, name, description, price_cents) "
        "values ($1, 'Tempered glass protector', 'A protective layer', 1500) returning id",
        tenant_id,
    )
    chunk = chunk_catalog_item(str(item_id), "Tempered glass protector", "A protective layer", 1500)
    await conn.execute(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, $3, $4, $5)",
        tenant_id,
        document_id,
        chunk.content,
        [0.0] * EMBEDDING_DIM,
        json.dumps(chunk.metadata),
    )
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    return tenant_id, conversation_id, item_id


def _context(tenant_id: uuid.UUID, provider: ToolAwareFakeProvider) -> GraphContext:
    return GraphContext(
        tenant_id=tenant_id,
        provider=provider,
        embedder=ZeroEmbedder(),
        reranker=PassthroughReranker(),
    )


def _quoting_provider(
    *, selections: list[dict[str, Any]], stream_text: str = "Here is your quote."
) -> ToolAwareFakeProvider:
    return ToolAwareFakeProvider(
        tool_call_sequence=[
            ToolTurn(
                tool_calls=[
                    ToolCall(id="call_q", name="get_quote_inputs", args={"selections": selections}),
                ]
            ),
            ToolTurn(text="ok", tool_calls=[]),
        ],
        stream_text=stream_text,
        extract_route="quoting",
    )


def _summary_provider(*, selections: list[dict[str, Any]]) -> ToolAwareFakeProvider:
    return ToolAwareFakeProvider(
        tool_call_sequence=[
            ToolTurn(
                tool_calls=[
                    ToolCall(
                        id="call_summary",
                        name="calculate_quote",
                        args={"selections": selections},
                    )
                ]
            )
        ],
        stream_text="This text must never be generated for a summary.",
    )


def _catalog_provider() -> ToolAwareFakeProvider:
    return ToolAwareFakeProvider(
        tool_call_sequence=[
            ToolTurn(tool_calls=[ToolCall(id="call_catalog", name="show_catalog", args={})])
        ],
        stream_text="This text must never be generated for a catalog.",
    )


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def test_selection_flows_through_engine_to_persisted_row(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn, tax_rate_bps=800)
    provider = _quoting_provider(selections=[{"rule_code": "screen-repair-a", "quantity": 1}])
    graph = build_graph()
    final_state = await graph.ainvoke(
        _initial_state("How much is a screen repair?", conversation_id),
        context=_context(tenant_id, provider),
    )
    engine_quote = final_state["engine_quote"]
    assert engine_quote is not None
    assert engine_quote["subtotal_cents"] == 12000
    assert engine_quote["tax_cents"] == 960
    assert engine_quote["total_cents"] == 12960
    row = await superuser_conn.fetchrow(
        "select * from quotes where tenant_id = $1 and conversation_id = $2",
        tenant_id,
        conversation_id,
    )
    assert row is not None
    assert row["subtotal_cents"] == 12000
    assert row["tax_cents"] == 960
    assert row["total_cents"] == 12960
    assert row["status"] == "sent"
    line_items = json.loads(row["line_items"])
    assert line_items == engine_quote["line_items"]
    assert str(row["id"]) == engine_quote["quote_id"]


async def test_catalog_item_selection_is_priced_from_db(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, item_id = await _seed_quoting_tenant(superuser_conn)
    provider = _quoting_provider(selections=[{"catalog_item_id": str(item_id), "quantity": 2}])
    graph = build_graph()
    final_state = await graph.ainvoke(
        _initial_state("Price for two glass protectors?", conversation_id),
        context=_context(tenant_id, provider),
    )
    engine_quote = final_state["engine_quote"]
    assert engine_quote is not None
    assert engine_quote["total_cents"] == 3000
    assert engine_quote["line_items"][0]["unit_amount_cents"] == 1500


async def test_basket_quote_emits_price_summary_without_quote_row_or_second_generation(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, item_id = await _seed_quoting_tenant(superuser_conn)
    second_item_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into offerings (tenant_id, name, description, price_cents, position) "
        "values ($1, 'Pita pocket', 'Fresh pita', 2000, 1) returning id",
        tenant_id,
    )
    provider = _summary_provider(
        selections=[
            {"catalog_item_id": str(item_id), "quantity": 1},
            {"catalog_item_id": str(second_item_id), "quantity": 2},
        ]
    )

    final_state = await build_graph().ainvoke(
        _initial_state("one protector and two pita pockets", conversation_id),
        context=_context(tenant_id, provider),
    )

    response = final_state["response"]
    assert response["type"] == "price_summary"
    assert response["summary"]["subtotal_cents"] == 5500
    assert response["summary"]["total_cents"] == 5500
    assert "quote_id" not in response["summary"]
    assert provider.tool_call_messages[0][0]["role"] == "system"
    assert len(provider.tool_call_messages) == 1
    assert (
        await superuser_conn.fetchval(
            "select count(*) from quotes where tenant_id = $1 and conversation_id = $2",
            tenant_id,
            conversation_id,
        )
        == 0
    )


async def test_full_catalog_emits_ordered_structured_payload_without_drafting(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, item_id = await _seed_quoting_tenant(superuser_conn)
    await superuser_conn.execute(
        "insert into offerings (tenant_id, name, description, price_cents, category, position) "
        "values ($1, 'Pita pocket', 'Fresh pita', null, 'Food', 1)",
        tenant_id,
    )
    provider = _catalog_provider()

    final_state = await build_graph().ainvoke(
        _initial_state("show me everything", conversation_id),
        context=_context(tenant_id, provider),
    )

    response = final_state["response"]
    offerings = response["catalog"]["offerings"]
    assert response["type"] == "catalog"
    assert [item["id"] for item in offerings] == [str(item_id), offerings[1]["id"]]
    assert offerings[1]["price_cents"] is None
    assert len(provider.tool_call_messages) == 1


async def test_follow_up_sees_the_latest_summary_item_ids(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, item_id = await _seed_quoting_tenant(superuser_conn)
    provider = _summary_provider(selections=[{"catalog_item_id": str(item_id), "quantity": 2}])
    state = _initial_state("make that two", conversation_id)
    state["messages"] = [
        {
            "role": "assistant",
            "content": "Here is the current price summary.",
            "response": {
                "type": "price_summary",
                "summary": {
                    "line_items": [{"item_id": str(item_id), "quantity": 1}],
                },
            },
        },
        {"role": "customer", "content": "make that two"},
    ]

    await build_graph().ainvoke(state, context=_context(tenant_id, provider))

    assert str(item_id) in provider.tool_call_messages[0][0]["content"]


async def test_bad_selection_does_not_produce_quote(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn)
    provider = _quoting_provider(selections=[{"rule_code": "no-such-rule", "quantity": 1}])
    graph = build_graph()
    final_state = await graph.ainvoke(
        _initial_state("How much is a screen repair?", conversation_id),
        context=_context(tenant_id, provider),
    )
    assert final_state["engine_quote"] is None


def test_selection_schema_has_no_money_fields() -> None:
    forbidden = ("price", "cent", "amount", "total", "cost", "money", "dollar", "tax", "subtotal")

    def assert_clean(model: type[BaseModel]) -> None:
        for name, field in model.model_fields.items():
            lowered = name.lower()
            assert not any(bad in lowered for bad in forbidden), (
                f"{model.__name__}.{name} looks like a money field"
            )
            annotation = field.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                assert_clean(annotation)

    # F-1: the schema moved from the deleted quoting specialist into the agent
    # node's get_quote_inputs tool; the invariant it pins did not move.
    assert_clean(GetQuoteInputsArgs)
    assert_clean(CalculateQuoteArgs)
    assert_clean(SelectionChoice)
    int_fields = [
        name
        for name, field in SelectionChoice.model_fields.items()
        if field.annotation in (int, int | None)
    ]
    assert int_fields == ["quantity"]


async def test_quote_line_item_labels_are_spotlight_wrapped(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """T-027: line-item labels come from tenant-authored pricing rules, so the
    quoting draft prompt must delimit them. The pre-T-044 quoting specialist
    wrapped these; the replacement dropped it, which is what this guards."""
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn)
    provider = _quoting_provider(selections=[{"rule_code": "screen-repair-a", "quantity": 1}])
    graph = build_graph()
    initial_state = _initial_state("how much for a screen repair?", conversation_id)
    initial_state["tenant_id"] = str(tenant_id)

    await graph.ainvoke(initial_state, context=_context(tenant_id, provider))

    prompt = provider.draft_prompts[0]
    assert "Screen repair (tier A)" in prompt, "sanity: the label reached the prompt"
    assert "<<data-" in prompt, "line-item label was not spotlight-wrapped"
    assert "never" in prompt.lower(), "the spotlight instruction must accompany the wrapping"
    # The deterministic-pricing rule is unaffected by the wrapping.
    assert "Do NOT state any prices" in prompt
