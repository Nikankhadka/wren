"""T-011: bare /api/chat, exercised at the API level.

Seeds a tenant + one knowledge chunk directly via superuser_conn (matching
test_retrieval.py's pattern - no signup/auth needed, the customer surface
has none). A `ControllableReranker` fixes the rerank score so the happy
path and the refusal path are both deterministic, rather than depending on
the real local cross-encoder's actual judgment.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from typing import Any

import asyncpg
import httpx
import pytest
import pytest_asyncio

from app.agents.draft_node import REFUSAL_MESSAGE
from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.provider import SchemaT, ToolCall, ToolTurn
from app.main import app
from app.observability.cost import report_usage
from app.retrieval.dependency import get_reranker_dependency
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from app.services import context_package
from app.shared import db
from app.shared.config import get_settings
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, ToolAwareFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class FakeChatProvider(ToolAwareFakeProvider):
    def __init__(self) -> None:
        from app.llm.provider import ToolCall, ToolTurn

        super().__init__(
            tool_call_sequence=[
                ToolTurn(
                    tool_calls=[
                        ToolCall(id="call_s", name="search_knowledge", args={"query": "test"}),
                    ]
                ),
                ToolTurn(text="ok", tool_calls=[]),
            ],
            extract_route="knowledge",
        )

    async def chat_stream(self, messages: list[Any]) -> AsyncIterator[str]:
        for delta in ["Sure", ", ", "here's ", "the ", "answer", " [1]", "."]:
            yield delta


class ControllableReranker(Reranker):
    def __init__(self, score: float) -> None:
        self._score = score

    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return [replace(chunk, score=self._score) for chunk in candidates[:top_k]]


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def _without_progress(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the D5 progress events (one per graph node, carrying only a stage
    key and never any model text) so a test can assert the sequence of prose
    the customer actually receives. Their own contract is pinned in
    test_inspection.py rather than re-asserted in every stream test."""
    return [event for event in events if event["type"] != "progress"]


@pytest.fixture
def hybrid_path() -> Iterator[None]:
    """Force retrieval scoring on, whatever the corpus size.

    O-4's fast path hands a small corpus to the model whole and does no
    scoring at all, so a relevance threshold means nothing there - the model
    decides, backstopped by grounding inspection. A test whose subject *is* the
    threshold has to put the tenant on the hybrid path, which is what a real
    tenant with a large corpus gets.
    """
    original = os.environ.get("CORPUS_FAST_PATH_MAX_TOKENS")
    os.environ["CORPUS_FAST_PATH_MAX_TOKENS"] = "1"
    get_settings.cache_clear()
    context_package.clear_cache()
    yield
    if original is None:
        os.environ.pop("CORPUS_FAST_PATH_MAX_TOKENS", None)
    else:
        os.environ["CORPUS_FAST_PATH_MAX_TOKENS"] = original
    get_settings.cache_clear()
    context_package.clear_cache()


@pytest_asyncio.fixture
async def client(migrated_db: str) -> AsyncIterator[httpx.AsyncClient]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    app.dependency_overrides[get_llm_provider] = FakeChatProvider
    app.dependency_overrides[get_embedder_dependency] = ZeroEmbedder
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)
        app.dependency_overrides.pop(get_embedder_dependency, None)
        app.dependency_overrides.pop(get_reranker_dependency, None)
        await db.close_pool()


async def _seed_tenant_with_chunk(
    conn: asyncpg.Connection[Any], *, slug: str, status: str = "active"
) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name, status) values ($1, $2, $3) returning id",
        slug,
        "Chat Test Co",
        status,
    )
    await conn.execute(
        "insert into tenant_config (tenant_id, system_prompt, tone) values ($1, $2, 'friendly')",
        tenant_id,
        "You help customers of Chat Test Co.",
    )
    document_id = await conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'faq.md', 'faq', 'ready') returning id",
        tenant_id,
    )
    await conn.execute(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, 'We are open weekdays 9-5.', $3, $4)",
        tenant_id,
        document_id,
        [0.0] * EMBEDDING_DIM,
        json.dumps({"source": "faq.md", "chunk_index": 0, "kind": "prose"}),
    )
    return tenant_id


async def test_chat_happy_path_streams_citations_and_tokens(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=1.0)

    response = await client.post(
        "/api/chat", json={"slug": slug, "message": "What are your hours?"}
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)

    prose = _without_progress(events)
    types = [event["type"] for event in prose]
    assert types == ["conversation", "citations"] + ["token"] * 7 + ["done"]
    assert prose[1]["citations"][0]["source"] == "faq.md"
    full_text = "".join(e["text"] for e in events if e["type"] == "token")
    assert full_text == "Sure, here's the answer [1]."


async def test_chat_persists_customer_and_assistant_messages(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=1.0)

    response = await client.post(
        "/api/chat", json={"slug": slug, "message": "What are your hours?"}
    )
    events = _parse_sse(response.text)
    conversation_id = events[0]["conversation_id"]

    rows = await superuser_conn.fetch(
        "select role, content, agent_node from messages where tenant_id = $1 "
        "and conversation_id = $2 order by created_at",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert [r["role"] for r in rows] == ["customer", "assistant"]
    assert rows[0]["content"] == "What are your hours?"
    assert rows[1]["content"] == "Sure, here's the answer [1]."
    # F-3: the trace's author column is populated by the graph, not only by
    # seeds - this knowledge turn went through the search tool, so the draft
    # node authored the answer.
    assert rows[1]["agent_node"] == "draft"


async def test_chat_refuses_when_nothing_is_relevant(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any], hybrid_path: None
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=-5.0)

    response = await client.post(
        "/api/chat", json={"slug": slug, "message": "What's the capital of France?"}
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)

    prose = _without_progress(events)
    assert prose[1]["type"] == "refusal"
    assert prose[1]["text"] == REFUSAL_MESSAGE
    assert prose[-1]["type"] == "done"
    assert not any(e["type"] == "citations" for e in events)


async def test_chat_resumes_an_existing_conversation(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=1.0)

    first = await client.post("/api/chat", json={"slug": slug, "message": "Hi"})
    conversation_id = _parse_sse(first.text)[0]["conversation_id"]

    second = await client.post(
        "/api/chat",
        json={"slug": slug, "conversation_id": conversation_id, "message": "Follow-up question"},
    )
    assert second.status_code == 200
    assert _parse_sse(second.text)[0]["conversation_id"] == conversation_id

    count = await superuser_conn.fetchval(
        "select count(*) from messages where tenant_id = $1 and conversation_id = $2",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert count == 4  # 2 customer + 2 assistant across both turns


async def test_chat_unknown_slug_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/chat", json={"slug": f"no-such-{uuid.uuid4().hex[:8]}", "message": "hi"}
    )
    assert response.status_code == 404


async def test_chat_suspended_tenant_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-suspended-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug, status="suspended")

    response = await client.post("/api/chat", json={"slug": slug, "message": "hi"})
    assert response.status_code == 404


async def test_chat_blocks_agent_turn_on_already_escalated_conversation(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """T-020/C-5: a conversation stopped by a tenant limit is terminal - no
    agent turn runs (the graph is never invoked), but the customer's message is
    still persisted so the transcript stays complete.

    Since C-5 the 'escalated' status is written only by
    ``record_limit_escalation``, so this seeded row stands for a budget or cap
    stop. An agent or guardrail handoff leaves the status 'open' and is covered
    in test_escalation_agent.py."""
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id, status) values ($1, 'escalated') returning id",
        tenant_id,
    )

    response = await client.post(
        "/api/chat",
        json={
            "slug": slug,
            "conversation_id": str(conversation_id),
            "message": "are you still there?",
        },
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    types = [event["type"] for event in events]
    assert types == ["conversation", "escalated", "done"]
    assert not any(event["type"] == "token" for event in events)

    customer_message = await superuser_conn.fetchval(
        "select content from messages where tenant_id = $1 and conversation_id = $2 "
        "and role = 'customer'",
        tenant_id,
        conversation_id,
    )
    assert customer_message == "are you still there?"

    status = await superuser_conn.fetchval(
        "select status from conversations where id = $1", conversation_id
    )
    assert status == "escalated"


async def test_chat_wrong_tenant_conversation_id_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug_a = f"chat-a-{uuid.uuid4().hex[:8]}"
    slug_b = f"chat-b-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug_a)
    await _seed_tenant_with_chunk(superuser_conn, slug=slug_b)
    app.dependency_overrides[get_reranker_dependency] = lambda: ControllableReranker(score=1.0)

    first = await client.post("/api/chat", json={"slug": slug_a, "message": "hi"})
    conversation_id = _parse_sse(first.text)[0]["conversation_id"]

    response = await client.post(
        "/api/chat",
        json={"slug": slug_b, "conversation_id": conversation_id, "message": "hi again"},
    )
    assert response.status_code == 404


class FakeOrderStatusProvider(ToolAwareFakeProvider):
    """T-030: routes to order_status and reports fake token usage on every
    call, so a real /api/chat turn exercises both the tool_calls
    persistence (order_status's real DB lookup) and cost_logs recording
    (report_usage -> chat.py's collect_usage()/record_costs())."""

    def __init__(self) -> None:
        from app.llm.provider import ToolCall, ToolTurn

        super().__init__(
            tool_call_sequence=[
                ToolTurn(
                    tool_calls=[
                        ToolCall(
                            id="call_o", name="lookup_order_or_ticket", args={"ref_code": "R-1001"}
                        ),
                    ]
                ),
                ToolTurn(text="ok", tool_calls=[]),
            ],
            extract_route="order_status",
        )

    async def chat_with_tools(
        self,
        *,
        messages: list[Any],
        tools: list[Any],
        tool_choice: str = "auto",
    ) -> Any:
        report_usage("fake-model", 10, 5)
        return await super().chat_with_tools(
            messages=messages, tools=tools, tool_choice=tool_choice
        )

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        report_usage("fake-model", 10, 5)
        return await super().extract(
            system_prompt=system_prompt, user_input=user_input, schema=schema
        )


async def _seed_tenant_with_order(conn: asyncpg.Connection[Any], *, slug: str) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name, status) values ($1, $2, 'active') returning id",
        slug,
        "Order Status Chat Test Co",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    await conn.execute(
        "insert into orders (tenant_id, ref_code, kind, status, details) "
        "values ($1, 'R-1001', 'repair', 'ready_for_pickup', '{}')",
        tenant_id,
    )
    return tenant_id


async def test_chat_persists_tool_calls_and_cost_logs_for_order_status_turn(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-order-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_order(superuser_conn, slug=slug)
    # Override the client fixture's default FakeChatProvider - this turn needs
    # to route to order_status, not knowledge.
    app.dependency_overrides[get_llm_provider] = FakeOrderStatusProvider

    chat_response = await client.post(
        "/api/chat", json={"slug": slug, "message": "any news on repair R-1001?"}
    )
    assert chat_response.status_code == 200
    conversation_id = _parse_sse(chat_response.text)[0]["conversation_id"]

    tool_call_row = await superuser_conn.fetchrow(
        "select tc.tool_name, tc.arguments, tc.result, tc.success, tc.latency_ms "
        "from tool_calls tc join messages m on m.id = tc.message_id "
        "where m.tenant_id = $1 and m.conversation_id = $2",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert tool_call_row is not None
    assert tool_call_row["tool_name"] == "lookup_order_or_ticket"
    assert json.loads(tool_call_row["arguments"])["ref_code"] == "R-1001"
    assert json.loads(tool_call_row["result"])["found"] is True
    assert tool_call_row["success"] is True
    assert tool_call_row["latency_ms"] is not None

    assistant_row = await superuser_conn.fetchrow(
        "select agent_node from messages where tenant_id = $1 and conversation_id = $2 "
        "and role = 'assistant'",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert assistant_row is not None
    # F-3: a tool-driven turn is authored by the draft node, and the persisted
    # row now says so (it used to be NULL for every production message).
    assert assistant_row["agent_node"] == "draft"

    cost_rows = await superuser_conn.fetch(
        "select model, input_tokens, output_tokens, cost_usd from cost_logs "
        "where tenant_id = $1 and conversation_id = $2",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert len(cost_rows) >= 1
    assert all(row["model"] == "fake-model" for row in cost_rows)
    assert sum(row["input_tokens"] for row in cost_rows) >= 10
    assert all(row["cost_usd"] == 0 for row in cost_rows)  # unknown model prices at $0


class FakeQuoteProvider(ToolAwareFakeProvider):
    """Routes straight to calculate_quote, same as test_quoting_agent.py's
    ``_summary_provider`` - no drafting happens for a price summary, so the
    stream_text below must never actually reach the customer."""

    def __init__(self, item_id: uuid.UUID) -> None:
        super().__init__(
            tool_call_sequence=[
                ToolTurn(
                    tool_calls=[
                        ToolCall(
                            id="call_summary",
                            name="calculate_quote",
                            args={"selections": [{"catalog_item_id": str(item_id), "quantity": 1}]},
                        )
                    ]
                )
            ],
            extract_route="quoting",
            stream_text="This text must never be generated for a summary.",
        )


async def _seed_tenant_with_offering(
    conn: asyncpg.Connection[Any], *, slug: str, price_cents: int
) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name, status) values ($1, $2, 'active') returning id",
        slug,
        "Quote Chat Test Co",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    item_id = uuid.uuid4()
    await conn.execute(
        "insert into offerings (id, tenant_id, name, description, price_cents) "
        "values ($1, $2, 'Tempered glass protector', 'A protective layer', $3)",
        item_id,
        tenant_id,
        price_cents,
    )
    return tenant_id, item_id


async def test_chat_persists_the_price_summary_payload_on_the_message_row(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """W-9 box 2 (thin slice): test_quoting_agent.py already proves the
    graph-level contract for a basket quote (one payload, correct total, no
    quote row, one model call). What that test cannot see is the HTTP
    boundary - whether the emitted price_summary actually lands where a page
    reload reads it back from, ``messages.metadata.response``
    (backend/app/features/chat/service.py persist_assistant_turn,
    around lines 212-216). This drives a real /api/chat turn and checks the
    persisted row instead of graph state.
    """
    slug = f"chat-quote-{uuid.uuid4().hex[:8]}"
    tenant_id, item_id = await _seed_tenant_with_offering(
        superuser_conn, slug=slug, price_cents=1500
    )
    app.dependency_overrides[get_llm_provider] = lambda: FakeQuoteProvider(item_id)

    response = await client.post(
        "/api/chat", json={"slug": slug, "message": "how much for a glass protector?"}
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    conversation_id = events[0]["conversation_id"]

    price_events = [e for e in events if e["type"] == "price_summary"]
    assert len(price_events) == 1, "exactly one price_summary event reaches the customer stream"
    assert price_events[0]["summary"]["total_cents"] == 1500
    # agent_node.py emits one fixed, non-model acknowledgement token alongside
    # a structured response (`draft_deterministic=True`) - a real second model
    # call would instead have produced FakeQuoteProvider's stream_text.
    token_texts = [e["text"] for e in events if e["type"] == "token"]
    assert token_texts == ["Here is the current price summary."]

    row = await superuser_conn.fetchrow(
        "select metadata from messages where tenant_id = $1 and conversation_id = $2 "
        "and role = 'assistant'",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert row is not None
    metadata = json.loads(row["metadata"])
    assert metadata["response"] == price_events[0]
    assert metadata["response"]["summary"]["total_cents"] == 1500

    assert (
        await superuser_conn.fetchval(
            "select count(*) from quotes where tenant_id = $1 and conversation_id = $2",
            tenant_id,
            uuid.UUID(conversation_id),
        )
        == 0
    ), "a price summary is not a formal quote - no quotes row"


async def test_chat_records_price_summary_ms_on_the_message_row(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """W-9 box 5: price_summary_ms had zero references anywhere under
    backend/tests/ before this test. The controller computes it
    (app/features/chat/controller.py, around lines 248-252, timed from turn
    start to the price_summary event) and persist_assistant_turn is supposed
    to write it onto the message row (app/features/chat/service.py, around
    lines 212-216) - nothing previously drove a real turn and read it back.
    """
    slug = f"chat-quote-ms-{uuid.uuid4().hex[:8]}"
    tenant_id, item_id = await _seed_tenant_with_offering(
        superuser_conn, slug=slug, price_cents=1500
    )
    app.dependency_overrides[get_llm_provider] = lambda: FakeQuoteProvider(item_id)

    response = await client.post(
        "/api/chat", json={"slug": slug, "message": "how much for a glass protector?"}
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    conversation_id = events[0]["conversation_id"]

    row = await superuser_conn.fetchrow(
        "select metadata from messages where tenant_id = $1 and conversation_id = $2 "
        "and role = 'assistant'",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert row is not None
    metadata = json.loads(row["metadata"])
    assert "price_summary_ms" in metadata, "price_summary_ms was never persisted on the message row"
    price_summary_ms = metadata["price_summary_ms"]
    assert isinstance(price_summary_ms, int | float)
    # Plausible, not exact: a wall-clock measurement of the turn up to the
    # price_summary event, against a fake provider with no real network
    # latency. Zero or negative would mean the clock never actually started;
    # tens of seconds would mean it measured the wrong thing entirely.
    assert 0 < price_summary_ms < 30_000


class FakeCatalogProvider(ToolAwareFakeProvider):
    """Routes straight to show_catalog, same shape as FakeQuoteProvider above -
    no drafting happens for a catalog listing either, so stream_text below
    must never actually reach the customer."""

    def __init__(self) -> None:
        super().__init__(
            tool_call_sequence=[
                ToolTurn(
                    tool_calls=[
                        ToolCall(id="call_catalog", name="show_catalog", args={}),
                    ]
                )
            ],
            extract_route="knowledge",
            stream_text="This text must never be generated for a catalog listing.",
        )


async def _seed_tenant_with_catalog(
    conn: asyncpg.Connection[Any], *, slug: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Two active offerings, inserted out of storefront order and one of them
    unpriced - so the "ordered active catalog... including unpriced rows" half
    of W-9 box 4's claim is exercised at the HTTP boundary, not only against
    the query in isolation. Returns (tenant_id, unpriced_offering_id,
    priced_offering_id) in the order they should appear on the wire.
    """
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name, status) values ($1, $2, 'active') returning id",
        slug,
        "Catalog Chat Test Co",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    unpriced_id = uuid.uuid4()
    priced_id = uuid.uuid4()
    # Inserted priced-then-unpriced, positioned unpriced-then-priced: only
    # `position` decides the wire order, never insertion order.
    await conn.execute(
        "insert into offerings (id, tenant_id, name, description, price_cents, position) "
        "values ($1, $2, 'Battery replacement', 'Genuine part, 1yr warranty', 6000, 1)",
        priced_id,
        tenant_id,
    )
    await conn.execute(
        "insert into offerings (id, tenant_id, name, description, price_cents, position) "
        "values ($1, $2, 'Custom engraving', 'Ask in store for a quote', null, 0)",
        unpriced_id,
        tenant_id,
    )
    return tenant_id, unpriced_id, priced_id


async def test_chat_persists_the_catalog_payload_identical_to_the_stream(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """W-9 box 4 (slice 1.3): the persisted `messages.metadata.response` for a
    `catalog` turn must equal the payload emitted on the SSE stream - the same
    parity `test_chat_persists_the_price_summary_payload_on_the_message_row`
    above proves for `price_summary`. An unpriced offering rides along so the
    "ordered active catalog... including unpriced rows" half of the box 4
    claim is covered at the HTTP boundary too, not just at the query level.
    """
    slug = f"chat-catalog-{uuid.uuid4().hex[:8]}"
    tenant_id, unpriced_id, priced_id = await _seed_tenant_with_catalog(superuser_conn, slug=slug)
    app.dependency_overrides[get_llm_provider] = FakeCatalogProvider

    response = await client.post("/api/chat", json={"slug": slug, "message": "what's on the menu?"})
    assert response.status_code == 200
    events = _parse_sse(response.text)
    conversation_id = events[0]["conversation_id"]

    catalog_events = [e for e in events if e["type"] == "catalog"]
    assert len(catalog_events) == 1, "exactly one catalog event reaches the customer stream"
    offerings = catalog_events[0]["catalog"]["offerings"]
    assert [o["id"] for o in offerings] == [
        str(unpriced_id),
        str(priced_id),
    ], "the catalog is in storefront position order, not insertion order"
    assert offerings[0]["price_cents"] is None, "the unpriced row is included, not dropped"
    assert offerings[1]["price_cents"] == 6000
    # agent_node.py emits one fixed, non-model acknowledgement token alongside
    # a structured response (`draft_deterministic=True`) - a real second model
    # call would instead have produced FakeCatalogProvider's stream_text.
    token_texts = [e["text"] for e in events if e["type"] == "token"]
    assert token_texts == ["Here is the current catalog."]

    row = await superuser_conn.fetchrow(
        "select metadata from messages where tenant_id = $1 and conversation_id = $2 "
        "and role = 'assistant'",
        tenant_id,
        uuid.UUID(conversation_id),
    )
    assert row is not None
    metadata = json.loads(row["metadata"])
    assert metadata["response"] == catalog_events[0], (
        "the persisted response payload must equal the payload actually streamed - "
        "this is what lets the owner and customer transcript views render the same "
        "persisted response payload, whichever surface reads it back later"
    )


async def _seed_transcript(conn: asyncpg.Connection[Any], tenant_id: uuid.UUID) -> uuid.UUID:
    """A conversation holding one message of every role, including 'system' -
    the public poll endpoint must return everything except the system one."""
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    for role, content in [
        ("customer", "where is my order?"),
        ("assistant", "let me check."),
        ("system", "internal prompt - never customer-visible"),
        ("human_agent", "A team member will call you shortly."),
    ]:
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content) "
            "values ($1, $2, $3, $4)",
            tenant_id,
            conversation_id,
            role,
            content,
        )
    return conversation_id


async def test_public_messages_returns_transcript_without_system_messages(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """T-031: the unauthenticated transcript poll returns customer, assistant
    and human_agent messages in order - and never a system-role message."""
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    conversation_id = await _seed_transcript(superuser_conn, tenant_id)

    response = await client.get(f"/api/chat/{conversation_id}/messages", params={"slug": slug})
    assert response.status_code == 200
    body = response.json()
    assert [m["role"] for m in body] == ["customer", "assistant", "human_agent"]
    assert body[2]["content"] == "A team member will call you shortly."
    assert not any(m["role"] == "system" for m in body)


async def test_public_messages_wrong_tenant_slug_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """A valid conversation UUID paired with another tenant's slug must 404 -
    the slug scopes the lookup, so a leaked UUID alone crosses no tenant."""
    slug_a = f"chat-a-{uuid.uuid4().hex[:8]}"
    slug_b = f"chat-b-{uuid.uuid4().hex[:8]}"
    tenant_a = await _seed_tenant_with_chunk(superuser_conn, slug=slug_a)
    await _seed_tenant_with_chunk(superuser_conn, slug=slug_b)
    conversation_id = await _seed_transcript(superuser_conn, tenant_a)

    response = await client.get(f"/api/chat/{conversation_id}/messages", params={"slug": slug_b})
    assert response.status_code == 404


async def test_public_messages_unknown_conversation_or_slug_is_404(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    await _seed_tenant_with_chunk(superuser_conn, slug=slug)

    response = await client.get(f"/api/chat/{uuid.uuid4()}/messages", params={"slug": slug})
    assert response.status_code == 404

    response = await client.get(
        f"/api/chat/{uuid.uuid4()}/messages",
        params={"slug": f"no-such-{uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 404


async def test_public_messages_after_cursor_returns_only_newer_messages(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """A client that already has the transcript up to some timestamp should
    be able to poll for only what's new, instead of re-fetching everything
    on every 5s tick."""
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    conversation_id = await _seed_transcript(superuser_conn, tenant_id)

    full = await client.get(f"/api/chat/{conversation_id}/messages", params={"slug": slug})
    assert full.status_code == 200
    cutoff = full.json()[0]["created_at"]

    response = await client.get(
        f"/api/chat/{conversation_id}/messages",
        params={"slug": slug, "after": cutoff},
    )
    assert response.status_code == 200
    body = response.json()
    assert [m["role"] for m in body] == ["assistant", "human_agent"]


# --- C-6: while a human has the conversation -------------------------------


async def test_chat_stays_silent_but_open_while_a_human_has_it(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """C-6: the assistant does not talk over the staff member who took over.

    The distinction from a limit stop is the whole point: the message is kept,
    no agent turn runs, and no terminal event is sent - so the customer's
    composer stays live and a handback resumes normal turns.
    """
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id, status) values ($1, 'human') returning id",
        tenant_id,
    )

    response = await client.post(
        "/api/chat",
        json={"slug": slug, "conversation_id": str(conversation_id), "message": "still there?"},
    )
    assert response.status_code == 200
    types = [event["type"] for event in _parse_sse(response.text)]
    assert types == ["conversation", "handoff", "done"]
    assert "escalated" not in types

    kept = await superuser_conn.fetchval(
        "select count(*) from messages where conversation_id = $1 and role = 'customer'",
        conversation_id,
    )
    assert kept == 1
    # No agent turn ran, so nothing was drafted.
    drafted = await superuser_conn.fetchval(
        "select count(*) from messages where conversation_id = $1 and role = 'assistant'",
        conversation_id,
    )
    assert drafted == 0
    status = await superuser_conn.fetchval(
        "select status from conversations where id = $1", conversation_id
    )
    assert status == "human"


async def test_the_owners_summary_never_reaches_a_customer(
    client: httpx.AsyncClient, superuser_conn: asyncpg.Connection[Any]
) -> None:
    """C-6 exempts the summary from the money guardrail on the grounds that no
    customer reads it. That only holds if no public endpoint returns it, so it
    is asserted rather than assumed."""
    slug = f"chat-{uuid.uuid4().hex[:8]}"
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, slug=slug)
    conversation_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    secret = "Catering for 20 on Friday, quoted 480 last time"
    await superuser_conn.execute(
        "insert into escalations (tenant_id, conversation_id, reason, summary) "
        "values ($1, $2, 'customer_request', $3)",
        tenant_id,
        conversation_id,
        secret,
    )

    transcript = await client.get(f"/api/chat/{conversation_id}/messages?slug={slug}")
    assert transcript.status_code == 200
    assert secret not in transcript.text
