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


async def test_catalog_payload_keeps_the_id_out_of_the_fields_the_card_renders(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """W-9 box 1: show_catalog's structured payload is exactly what
    CatalogCard.tsx (frontend/src/components/ui/CatalogCard.tsx) renders. The
    offering id has to be on the payload - the card uses it as the row's
    React `key`, and a follow-up turn needs it to resolve "the second one" -
    but it must never leak into a field the card actually prints as text:
    name, category, or description. It stays confined to its own `id` key."""
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

    offerings = final_state["response"]["catalog"]["offerings"]
    assert len(offerings) == 2, "sanity: both offerings came through"
    for offering in offerings:
        assert offering["id"], "sanity: the id is present on the payload"
        for field_name in ("name", "category", "description"):
            value = offering[field_name] or ""
            assert offering["id"] not in value, (
                f"catalog_id leaked into the rendered field {field_name!r}"
            )


async def test_price_summary_payload_keeps_the_item_id_out_of_the_rendered_label(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Same guarantee as the catalog test above, for calculate_quote's
    payload - what PriceSummaryCard.tsx renders directly. `item_id` is a
    React `key` and the field a follow-up turn re-selects by
    (test_follow_up_sees_the_latest_summary_item_ids below); the printed line
    is `label`, the tenant-authored item name, which must never contain it."""
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

    line_items = final_state["response"]["summary"]["line_items"]
    assert len(line_items) == 2, "sanity: both selections came through"
    for item in line_items:
        assert item["item_id"], "sanity: the id is present on the payload"
        assert item["item_id"] not in item["label"]


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


async def test_follow_up_add_recalculates_the_complete_basket(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """W-9 box 5: adding a second item on a follow-up turn must produce the
    full two-item total, not the old total plus a delta and not the new
    item's price alone. calculate_quote is called fresh every turn with
    whatever selections it is given (agent_node.py's calculate_quote handler,
    around line 635) - nothing carries a running total between turns - so the
    only way this passes is if the complete basket reaches the engine both
    times."""
    tenant_id, conversation_id, item_id = await _seed_quoting_tenant(superuser_conn)
    second_item_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into offerings (tenant_id, name, description, price_cents) "
        "values ($1, 'Pita pocket', 'Fresh pita', 2000) returning id",
        tenant_id,
    )

    turn1 = await build_graph().ainvoke(
        _initial_state("one glass protector", conversation_id),
        context=_context(
            tenant_id,
            _summary_provider(selections=[{"catalog_item_id": str(item_id), "quantity": 1}]),
        ),
    )
    assert turn1["response"]["summary"]["total_cents"] == 1500

    state2 = _initial_state("add a pita pocket too", conversation_id)
    state2["messages"] = [
        {
            "role": "assistant",
            "content": "Here is the current price summary.",
            "response": turn1["response"],
        },
        {"role": "customer", "content": "add a pita pocket too"},
    ]
    turn2 = await build_graph().ainvoke(
        state2,
        context=_context(
            tenant_id,
            _summary_provider(
                selections=[
                    {"catalog_item_id": str(item_id), "quantity": 1},
                    {"catalog_item_id": str(second_item_id), "quantity": 1},
                ]
            ),
        ),
    )
    summary = turn2["response"]["summary"]
    assert summary["total_cents"] == 1500 + 2000
    assert len(summary["line_items"]) == 2


async def test_follow_up_remove_recalculates_the_complete_basket(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Removing an item on a follow-up must drop it from the total entirely -
    the basket calculate_quote receives on turn 2 is the complete remaining
    set, and the total must match it exactly, not the old total minus the
    removed item's price computed some other way."""
    tenant_id, conversation_id, item_id = await _seed_quoting_tenant(superuser_conn)
    second_item_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into offerings (tenant_id, name, description, price_cents) "
        "values ($1, 'Pita pocket', 'Fresh pita', 2000) returning id",
        tenant_id,
    )

    turn1 = await build_graph().ainvoke(
        _initial_state("a protector and a pita pocket", conversation_id),
        context=_context(
            tenant_id,
            _summary_provider(
                selections=[
                    {"catalog_item_id": str(item_id), "quantity": 1},
                    {"catalog_item_id": str(second_item_id), "quantity": 1},
                ]
            ),
        ),
    )
    assert turn1["response"]["summary"]["total_cents"] == 3500

    state2 = _initial_state("actually drop the pita pocket", conversation_id)
    state2["messages"] = [
        {
            "role": "assistant",
            "content": "Here is the current price summary.",
            "response": turn1["response"],
        },
        {"role": "customer", "content": "actually drop the pita pocket"},
    ]
    turn2 = await build_graph().ainvoke(
        state2,
        context=_context(
            tenant_id,
            _summary_provider(selections=[{"catalog_item_id": str(item_id), "quantity": 1}]),
        ),
    )
    summary = turn2["response"]["summary"]
    assert summary["total_cents"] == 1500
    assert len(summary["line_items"]) == 1


async def test_follow_up_quantity_change_recalculates_the_complete_basket(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """A quantity change on a follow-up must recompute the whole line - the
    new quantity times the current unit price - not scale a stored total."""
    tenant_id, conversation_id, item_id = await _seed_quoting_tenant(superuser_conn)

    turn1 = await build_graph().ainvoke(
        _initial_state("one glass protector", conversation_id),
        context=_context(
            tenant_id,
            _summary_provider(selections=[{"catalog_item_id": str(item_id), "quantity": 1}]),
        ),
    )
    assert turn1["response"]["summary"]["total_cents"] == 1500

    state2 = _initial_state("make that three", conversation_id)
    state2["messages"] = [
        {
            "role": "assistant",
            "content": "Here is the current price summary.",
            "response": turn1["response"],
        },
        {"role": "customer", "content": "make that three"},
    ]
    turn2 = await build_graph().ainvoke(
        state2,
        context=_context(
            tenant_id,
            _summary_provider(selections=[{"catalog_item_id": str(item_id), "quantity": 3}]),
        ),
    )
    summary = turn2["response"]["summary"]
    assert summary["total_cents"] == 1500 * 3
    assert summary["line_items"][0]["quantity"] == 3


async def test_follow_up_uses_the_price_at_the_moment_of_the_second_turn(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """The amendment's explicit claim: if the owner changes a price between
    turns, a same-basket follow-up must use the new price, not the one quoted
    a moment ago. compute_quote reads offerings fresh on every call
    (backend/app/pricing/engine.py never caches a price) so nothing in the
    agent layer should reintroduce staleness - this is the case the amendment
    names and W-9's own test suite never actually ran before now."""
    tenant_id, conversation_id, item_id = await _seed_quoting_tenant(superuser_conn)

    turn1 = await build_graph().ainvoke(
        _initial_state("one glass protector", conversation_id),
        context=_context(
            tenant_id,
            _summary_provider(selections=[{"catalog_item_id": str(item_id), "quantity": 1}]),
        ),
    )
    assert turn1["response"]["summary"]["total_cents"] == 1500

    await superuser_conn.execute("update offerings set price_cents = 1800 where id = $1", item_id)

    state2 = _initial_state("is that still the price?", conversation_id)
    state2["messages"] = [
        {
            "role": "assistant",
            "content": "Here is the current price summary.",
            "response": turn1["response"],
        },
        {"role": "customer", "content": "is that still the price?"},
    ]
    turn2 = await build_graph().ainvoke(
        state2,
        context=_context(
            tenant_id,
            _summary_provider(selections=[{"catalog_item_id": str(item_id), "quantity": 1}]),
        ),
    )
    summary = turn2["response"]["summary"]
    assert summary["total_cents"] == 1800
    assert summary["line_items"][0]["unit_amount_cents"] == 1800


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


# W-9 box 3's deterministic clarification (agent_node.py's exception path,
# around line 768) - fixed regardless of which selection was bad.
_CALCULATE_QUOTE_CLARIFICATION = (
    "I couldn't match every item to a confirmed offering. Which items would you like me to include?"
)


async def _assert_no_partial_total_or_quote(
    conn: asyncpg.Connection[Any],
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    final_state: dict[str, Any],
) -> None:
    """Shared assertions for every calculate_quote bad-selection case: the
    fixed clarification is what reaches the customer, no structured payload
    or engine quote lands in state, and no quotes row was created - the
    'never a partial total, never a substituted item' claim, checked from
    every angle a leak could show up."""
    assert final_state["draft_response"] == _CALCULATE_QUOTE_CLARIFICATION
    assert "response" not in final_state
    assert final_state["engine_quote"] is None
    assert (
        await conn.fetchval(
            "select count(*) from quotes where tenant_id = $1 and conversation_id = $2",
            tenant_id,
            conversation_id,
        )
        == 0
    )


async def test_calculate_quote_with_an_unsupported_item_produces_no_partial_total(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """W-9 box 3: a catalog_item_id naming nothing this tenant offers must
    never reach the customer as a total, partial or otherwise -
    compute_quote raises before calculate_quote returns anything
    (backend/app/pricing/engine.py's compute_quote, around lines 144-168)."""
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn)
    provider = _summary_provider(selections=[{"catalog_item_id": str(uuid.uuid4()), "quantity": 1}])
    final_state = await build_graph().ainvoke(
        _initial_state("how much for that thing?", conversation_id),
        context=_context(tenant_id, provider),
    )
    await _assert_no_partial_total_or_quote(superuser_conn, tenant_id, conversation_id, final_state)


async def test_calculate_quote_with_an_unpriced_item_produces_no_partial_total(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """An offering with no price_cents is not fixed-price - compute_quote
    refuses it (engine.py's _price_item), and calculate_quote must fall back
    to the clarification rather than any total."""
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn)
    unpriced_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into offerings (tenant_id, name, description, price_cents) "
        "values ($1, 'Custom engraving', 'Priced by rule, not directly', null) returning id",
        tenant_id,
    )
    provider = _summary_provider(selections=[{"catalog_item_id": str(unpriced_id), "quantity": 1}])
    final_state = await build_graph().ainvoke(
        _initial_state("how much for the engraving?", conversation_id),
        context=_context(tenant_id, provider),
    )
    await _assert_no_partial_total_or_quote(superuser_conn, tenant_id, conversation_id, final_state)


async def test_calculate_quote_with_a_mixed_priceability_basket_does_not_return_the_priced_half(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """The important case: one selection is fully priceable and would sum to
    a real total on its own, but compute_quote is all-or-nothing - it raises
    on the first bad selection and never returns partial line_items
    (engine.py's compute_quote loop). The priced item's 1500 cents must not
    leak out as a 'partial' total just because the rest of the basket
    failed."""
    tenant_id, conversation_id, priced_item_id = await _seed_quoting_tenant(superuser_conn)
    unpriced_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into offerings (tenant_id, name, description, price_cents) "
        "values ($1, 'Custom engraving', 'Priced by rule, not directly', null) returning id",
        tenant_id,
    )
    provider = _summary_provider(
        selections=[
            {"catalog_item_id": str(priced_item_id), "quantity": 1},
            {"catalog_item_id": str(unpriced_id), "quantity": 1},
        ]
    )
    final_state = await build_graph().ainvoke(
        _initial_state("a glass protector and the engraving", conversation_id),
        context=_context(tenant_id, provider),
    )
    await _assert_no_partial_total_or_quote(superuser_conn, tenant_id, conversation_id, final_state)
    assert "1500" not in final_state["draft_response"], "the priced half must not leak as text"


async def test_calculate_quote_with_an_inactive_offering_produces_no_partial_total(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """An inactive offering is not currently sold - compute_quote's WHERE
    clause (engine.py's _price_item) excludes it exactly like an unknown id,
    and the engine never substitutes an active alternative."""
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn)
    inactive_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into offerings (tenant_id, name, description, price_cents, active) "
        "values ($1, 'Discontinued case', 'No longer sold', 1000, false) returning id",
        tenant_id,
    )
    provider = _summary_provider(selections=[{"catalog_item_id": str(inactive_id), "quantity": 1}])
    final_state = await build_graph().ainvoke(
        _initial_state("how much for the discontinued case?", conversation_id),
        context=_context(tenant_id, provider),
    )
    await _assert_no_partial_total_or_quote(superuser_conn, tenant_id, conversation_id, final_state)


async def test_calculate_quote_with_a_different_tenants_offering_produces_no_partial_total(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Tenant isolation: an offering id that is real and priced, but belongs
    to a different tenant, must be refused exactly like an unknown id -
    compute_quote's queries are always scoped by tenant_id (engine.py's
    _price_item), so a leaked or guessed id from another tenant's catalog can
    never price against this one's basket."""
    tenant_id, conversation_id, _ = await _seed_quoting_tenant(superuser_conn)
    other_tenant_id, _, other_item_id = await _seed_quoting_tenant(superuser_conn)
    assert other_tenant_id != tenant_id
    provider = _summary_provider(
        selections=[{"catalog_item_id": str(other_item_id), "quantity": 1}]
    )
    final_state = await build_graph().ainvoke(
        _initial_state("how much for that other business's item?", conversation_id),
        context=_context(tenant_id, provider),
    )
    await _assert_no_partial_total_or_quote(superuser_conn, tenant_id, conversation_id, final_state)


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
