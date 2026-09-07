"""P-3: the context package, its cache, and the one-call turn.

Three things have to hold and each is tested where it actually lives: the
package is assembled from real tenant rows (Postgres), the cache is keyed by
knowledge version so an upload is never answered from stale material, and a turn
against a fast-path package makes exactly one model call whose prose still goes
through the full gate chain.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from typing import Any

import asyncpg
import pytest
import pytest_asyncio

from app.agents.graph import build_graph
from app.agents.state import AgentState, GraphContext
from app.llm.provider import ChatMessage, SchemaT, ToolCall, ToolSpec, ToolTurn
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from app.services import context_package
from app.services.context_package import build_package, clear_cache, get_package
from app.shared import db
from app.shared.config import get_settings
from app.shared.voice import CustomerVoice
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, ToolAwareFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class PassthroughReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


class RecordingProvider(ToolAwareFakeProvider):
    """Answers in one turn and records the prompts it was given."""

    def __init__(self, answer: str = "We are open weekdays 9-5 [1].") -> None:
        super().__init__(tool_call_sequence=[ToolTurn(text=answer)], extract_route="knowledge")
        self.tool_calls_offered: list[list[str]] = []

    async def chat_with_tools(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        tool_choice: str = "auto",
    ) -> ToolTurn:
        self.tool_calls_offered.append([tool.name for tool in tools])
        return await super().chat_with_tools(
            messages=messages, tools=tools, tool_choice=tool_choice
        )


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    clear_cache()
    yield
    clear_cache()


@pytest_asyncio.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def _seed_tenant(
    conn: asyncpg.Connection[Any],
    *,
    contents: tuple[str, ...] = ("We are open weekdays 9-5.",),
    profile: dict[str, str] | None = None,
    offerings: tuple[tuple[str, str, int | None], ...] = (),
) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Package Test Co') returning id",
        f"pkg-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute(
        "insert into tenant_config (tenant_id, system_prompt, tone, config) "
        "values ($1, $2, 'warm', $3::jsonb)",
        tenant_id,
        "You are the assistant for Package Test Co.",
        json.dumps(
            {
                "profile": profile
                or {
                    "business_name": "Package Test Co",
                    "hours": "Mon-Fri 9-5",
                    "services": "Repairs",
                },
                "customer_voice": {"preset": "direct_concise", "custom_style": None},
            }
        ),
    )
    if contents:
        document_id = await conn.fetchval(
            "insert into documents (tenant_id, filename, doc_type, status) "
            "values ($1, 'faq.md', 'faq', 'ready') returning id",
            tenant_id,
        )
        for index, content in enumerate(contents):
            await conn.execute(
                "insert into knowledge_chunks "
                "(tenant_id, document_id, content, embedding, metadata) "
                "values ($1, $2, $3, $4, $5::jsonb)",
                tenant_id,
                document_id,
                content,
                [0.0] * EMBEDDING_DIM,
                json.dumps({"source": "faq.md", "chunk_index": index, "kind": "prose"}),
            )
    for position, (name, description, price_cents) in enumerate(offerings):
        await conn.execute(
            "insert into offerings "
            "(tenant_id, name, description, price_cents, position) "
            "values ($1, $2, $3, $4, $5)",
            tenant_id,
            name,
            description,
            price_cents,
            position,
        )
    return tenant_id


def _initial_state(tenant_id: uuid.UUID, conversation_id: uuid.UUID, message: str) -> AgentState:
    return {
        "conversation_id": str(conversation_id),
        "tenant_id": str(tenant_id),
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


async def _conversation_for(conn: asyncpg.Connection[Any], tenant_id: uuid.UUID) -> uuid.UUID:
    conversation_id: uuid.UUID = await conn.fetchval(
        "insert into conversations (tenant_id) values ($1) returning id", tenant_id
    )
    return conversation_id


# --- assembly ------------------------------------------------------------------


async def test_package_carries_voice_profile_and_corpus(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)

    async with db.tenant_context(tenant_id, "customer") as conn:
        package = await build_package(conn, tenant_id)

    # W-9: the structured voice and the public business name, never the
    # free-text system_prompt/tone pair - those columns are read by nothing now.
    assert package.business_name == "Package Test Co"
    assert package.voice == CustomerVoice(preset="direct_concise")
    assert package.fast_path is True
    assert [c.content for c in package.chunks] == ["We are open weekdays 9-5."]
    assert "Mon-Fri 9-5" in package.profile_text()


async def test_package_carries_active_offerings_in_storefront_order(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(
        superuser_conn,
        contents=(),
        offerings=(
            ("Coffee", "Freshly brewed", 350),
            ("Pita bowls", "Choose your filling", None),
        ),
    )
    await superuser_conn.execute(
        "insert into offerings (tenant_id, name, description, price_cents, position, active) "
        "values ($1, 'Retired special', '', 999, 0, false)",
        tenant_id,
    )

    async with db.tenant_context(tenant_id, "customer") as conn:
        package = await build_package(conn, tenant_id)

    assert [offering.name for offering in package.offerings] == ["Coffee", "Pita bowls"]
    assert package.offerings_text() == (
        "Current confirmed offerings:\n"
        "- Coffee: Freshly brewed ($3.50)\n"
        "- Pita bowls: Choose your filling"
    )
    assert package.owner_material().endswith(package.offerings_text())


async def test_hybrid_package_also_carries_active_offerings(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(
        superuser_conn,
        offerings=(("Coffee", "Freshly brewed", 350),),
    )
    original = os.environ.get("CORPUS_FAST_PATH_MAX_TOKENS")
    os.environ["CORPUS_FAST_PATH_MAX_TOKENS"] = "1"
    get_settings.cache_clear()
    try:
        async with db.tenant_context(tenant_id, "customer") as conn:
            package = await build_package(conn, tenant_id)
    finally:
        if original is None:
            os.environ.pop("CORPUS_FAST_PATH_MAX_TOKENS", None)
        else:
            os.environ["CORPUS_FAST_PATH_MAX_TOKENS"] = original
        get_settings.cache_clear()

    assert package.fast_path is False
    assert package.offerings[0].name == "Coffee"
    assert "Coffee: Freshly brewed ($3.50)" in package.offerings_text()


async def test_offering_change_invalidates_the_cached_package(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(
        superuser_conn, contents=(), offerings=(("Coffee", "Freshly brewed", 350),)
    )
    async with db.tenant_context(tenant_id, "customer") as conn:
        before = await get_package(conn, tenant_id)

    await superuser_conn.execute(
        "update offerings set price_cents = 400 where tenant_id = $1", tenant_id
    )

    async with db.tenant_context(tenant_id, "customer") as conn:
        after = await get_package(conn, tenant_id)

    assert after is not before
    assert after.offerings[0].price_cents == 400


async def test_package_without_a_profile_still_assembles(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    # A tenant provisioned but not yet through onboarding: no profile, no
    # documents. The package must still be valid rather than blowing up a turn.
    tenant_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Bare Co') returning id",
        f"bare-{uuid.uuid4().hex[:8]}",
    )
    await superuser_conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)

    async with db.tenant_context(tenant_id, "customer") as conn:
        package = await build_package(conn, tenant_id)

    assert package.profile_text() == ""
    assert package.chunks == []
    # No profile means no confirmed public name yet, and the default voice - the
    # contract renders both without a tenant having to supply either.
    assert package.business_name == ""
    assert package.voice == CustomerVoice()


# --- the cache -----------------------------------------------------------------


async def test_second_lookup_is_a_cache_hit(superuser_conn: asyncpg.Connection[Any]) -> None:
    tenant_id = await _seed_tenant(superuser_conn)

    async with db.tenant_context(tenant_id, "customer") as conn:
        first = await get_package(conn, tenant_id)
        second = await get_package(conn, tenant_id)

    assert first is second


async def test_upload_invalidates_the_cached_package(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    async with db.tenant_context(tenant_id, "customer") as conn:
        before = await get_package(conn, tenant_id)

    document_id = await superuser_conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'menu.md', 'faq', 'ready') returning id",
        tenant_id,
    )
    await superuser_conn.execute(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, 'Catering starts at 10 people.', $3, '{}'::jsonb)",
        tenant_id,
        document_id,
        [0.0] * EMBEDDING_DIM,
    )

    async with db.tenant_context(tenant_id, "customer") as conn:
        after = await get_package(conn, tenant_id)

    assert after is not before
    assert after.version > before.version
    assert any("Catering" in chunk.content for chunk in after.chunks)


async def test_profile_change_invalidates_the_cached_package(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    async with db.tenant_context(tenant_id, "customer") as conn:
        assert "Mon-Fri 9-5" in (await get_package(conn, tenant_id)).profile_text()

    await superuser_conn.execute(
        "update tenant_config set config = $2::jsonb where tenant_id = $1",
        tenant_id,
        json.dumps({"profile": {"hours": "Now open Saturdays too"}}),
    )

    async with db.tenant_context(tenant_id, "customer") as conn:
        after = await get_package(conn, tenant_id)

    assert "Saturdays" in after.profile_text()


async def test_packages_are_per_tenant(superuser_conn: asyncpg.Connection[Any]) -> None:
    mine = await _seed_tenant(superuser_conn, contents=("Our warranty is 12 months.",))
    theirs = await _seed_tenant(superuser_conn, contents=("Their warranty is 3 months.",))

    async with db.tenant_context(mine, "customer") as conn:
        my_package = await get_package(conn, mine)
    async with db.tenant_context(theirs, "customer") as conn:
        their_package = await get_package(conn, theirs)

    assert [c.content for c in my_package.chunks] == ["Our warranty is 12 months."]
    assert [c.content for c in their_package.chunks] == ["Their warranty is 3 months."]


# --- the one-call turn ---------------------------------------------------------


async def test_fast_path_turn_makes_one_model_call_and_skips_the_draft_node(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    conversation_id = await _conversation_for(superuser_conn, tenant_id)
    provider = RecordingProvider()
    graph = build_graph()

    order: list[str] = []
    async for update in graph.astream(
        _initial_state(tenant_id, conversation_id, "What time do you open?"),
        context=GraphContext(
            tenant_id=tenant_id,
            provider=provider,
            embedder=ZeroEmbedder(),
            reranker=PassthroughReranker(),
        ),
        stream_mode="updates",
    ):
        order.extend(update.keys())

    # One tool-calling call for the answer; the draft node never runs, so no
    # second generation call happens at all.
    assert len(provider.tool_call_messages) == 1
    assert provider.draft_prompts == []  # nothing was streamed: no draft call
    # C-2: the money gate is on every path now; it is a regex sweep over a
    # draft with no figures, not a second model call - the one-call claim holds.
    assert order == ["agent", "price_gate", "inspection"]


async def test_fast_path_prompt_carries_the_corpus_and_drops_the_search_tool(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    conversation_id = await _conversation_for(superuser_conn, tenant_id)
    provider = RecordingProvider()

    await build_graph().ainvoke(
        _initial_state(tenant_id, conversation_id, "What time do you open?"),
        context=GraphContext(
            tenant_id=tenant_id,
            provider=provider,
            embedder=ZeroEmbedder(),
            reranker=PassthroughReranker(),
        ),
    )

    system = provider.tool_call_messages[0][0]["content"]
    assert "We are open weekdays 9-5." in system
    assert "Mon-Fri 9-5" in system  # the profile travels with the corpus
    assert "search_knowledge" not in provider.tool_calls_offered[0]
    assert "create_escalation" in provider.tool_calls_offered[0]


async def test_fast_path_prompt_lists_the_complete_confirmed_catalog(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(
        superuser_conn,
        contents=("Our menu may change seasonally.",),
        offerings=(("Coffee", "Freshly brewed", 350), ("Pita bowls", "", 1200)),
    )
    conversation_id = await _conversation_for(superuser_conn, tenant_id)
    provider = RecordingProvider(answer="We offer coffee and pita bowls.")

    await build_graph().ainvoke(
        _initial_state(tenant_id, conversation_id, "What do you offer?"),
        context=GraphContext(
            tenant_id=tenant_id,
            provider=provider,
            embedder=ZeroEmbedder(),
            reranker=PassthroughReranker(),
        ),
    )

    system = provider.tool_call_messages[0][0]["content"]
    assert "Current confirmed offerings:" in system
    assert "Coffee: Freshly brewed ($3.50)" in system
    assert "Pita bowls ($12.00)" in system
    assert "Our menu may change seasonally." in system


async def test_fast_path_answer_still_passes_through_inspection(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    conversation_id = await _conversation_for(superuser_conn, tenant_id)
    provider = RecordingProvider()

    final_state = await build_graph().ainvoke(
        _initial_state(tenant_id, conversation_id, "What time do you open?"),
        context=GraphContext(
            tenant_id=tenant_id,
            provider=provider,
            embedder=ZeroEmbedder(),
            reranker=PassthroughReranker(),
        ),
    )

    assert final_state["draft_response"] == "We are open weekdays 9-5 [1]."
    assert final_state["route"] == "knowledge"
    assert final_state["inspection_decision"] == "ok"
    assert final_state["inspection"]["grounding"]["passed"] is True
    # The corpus the answer was written from is what inspection judged it
    # against - a one-call answer is not exempt from grounding.
    assert final_state["retrieved_chunks"][0]["content"] == "We are open weekdays 9-5."


async def test_corpus_over_budget_keeps_the_search_tool(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant(superuser_conn)
    conversation_id = await _conversation_for(superuser_conn, tenant_id)
    provider = RecordingProvider()
    original = os.environ.get("CORPUS_FAST_PATH_MAX_TOKENS")
    os.environ["CORPUS_FAST_PATH_MAX_TOKENS"] = "1"
    get_settings.cache_clear()
    context_package.clear_cache()
    try:
        await build_graph().ainvoke(
            _initial_state(tenant_id, conversation_id, "What time do you open?"),
            context=GraphContext(
                tenant_id=tenant_id,
                provider=provider,
                embedder=ZeroEmbedder(),
                reranker=PassthroughReranker(),
            ),
        )
    finally:
        if original is None:
            os.environ.pop("CORPUS_FAST_PATH_MAX_TOKENS", None)
        else:
            os.environ["CORPUS_FAST_PATH_MAX_TOKENS"] = original
        get_settings.cache_clear()

    assert "search_knowledge" in provider.tool_calls_offered[0]
    assert "We are open weekdays 9-5." not in provider.tool_call_messages[0][0]["content"]


# --- W-5: answer from confirmed offerings and knowledge together ---------------


class HighScoreReranker(Reranker):
    """A reranker that scores every candidate well above the search_knowledge
    relevance floor (T-044's ``_REFUSAL_SCORE_THRESHOLD``). Real reranked
    scores would work too, but a single-chunk corpus never earns more than one
    RRF contribution per ranked list, which sits below that floor - a real
    reranker would legitimately treat that as too weak to answer from, which
    is not what these tests are checking."""

    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return [replace(chunk, score=1.0) for chunk in candidates[:top_k]]


def _search_knowledge_turns(query: str, answer: str) -> list[ToolTurn]:
    call = ToolCall(id="call_s", name="search_knowledge", args={"query": query})
    return [
        ToolTurn(tool_calls=[call]),
        ToolTurn(text=answer, tool_calls=[]),
    ]


async def test_hybrid_knowledge_answer_carries_the_confirmed_offerings(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """W-5: on the hybrid path, a search_knowledge turn's draft prompt must
    carry the confirmed catalog alongside the retrieved chunks - today
    ``_build_knowledge_prompt`` only ever sees ``retrieved_chunks``, so this
    assertion is false before the fix."""
    tenant_id = await _seed_tenant(
        superuser_conn,
        contents=("We are open weekdays 9-5.",),
        offerings=(("Coffee", "Freshly brewed", 350),),
    )
    conversation_id = await _conversation_for(superuser_conn, tenant_id)
    provider = ToolAwareFakeProvider(
        tool_call_sequence=_search_knowledge_turns(
            "hours", "We open weekdays 9-5 and also sell Coffee [1]."
        ),
        extract_route="knowledge",
    )
    original = os.environ.get("CORPUS_FAST_PATH_MAX_TOKENS")
    os.environ["CORPUS_FAST_PATH_MAX_TOKENS"] = "1"
    get_settings.cache_clear()
    context_package.clear_cache()
    try:
        await build_graph().ainvoke(
            _initial_state(tenant_id, conversation_id, "When are you open and what do you sell?"),
            context=GraphContext(
                tenant_id=tenant_id,
                provider=provider,
                embedder=ZeroEmbedder(),
                reranker=HighScoreReranker(),
            ),
        )
    finally:
        if original is None:
            os.environ.pop("CORPUS_FAST_PATH_MAX_TOKENS", None)
        else:
            os.environ["CORPUS_FAST_PATH_MAX_TOKENS"] = original
        get_settings.cache_clear()

    assert provider.draft_prompts
    draft_prompt = provider.draft_prompts[0]
    assert "Current confirmed offerings:" in draft_prompt
    assert "Coffee" in draft_prompt


async def test_fast_path_prompt_no_longer_sequences_catalog_before_detail(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Sibling to test_fast_path_prompt_lists_the_complete_confirmed_catalog:
    that test only asserts the catalog content is present, which must stay
    true. This asserts the sequencing instruction that caused the two-step
    answer (catalog first, detail only on a second, more insistent question)
    is gone."""
    tenant_id = await _seed_tenant(
        superuser_conn,
        contents=("Our menu may change seasonally.",),
        offerings=(("Coffee", "Freshly brewed", 350), ("Pita bowls", "", 1200)),
    )
    conversation_id = await _conversation_for(superuser_conn, tenant_id)
    provider = RecordingProvider(answer="We offer coffee and pita bowls.")

    await build_graph().ainvoke(
        _initial_state(tenant_id, conversation_id, "What do you offer?"),
        context=GraphContext(
            tenant_id=tenant_id,
            provider=provider,
            embedder=ZeroEmbedder(),
            reranker=PassthroughReranker(),
        ),
    )

    system = provider.tool_call_messages[0][0]["content"]
    assert "Current confirmed offerings:" in system  # unchanged: catalog still authoritative
    assert "before offering to share more detail" not in system


class GroundingSensitiveProvider(RecordingProvider):
    """Unlike the base fake's ``extract()``, which always hands back a
    passing ``InspectionVerdicts`` regardless of what it was given, this
    provider's grounding verdict actually depends on whether ``must_ground``
    appears in the judge's context - the exact thing W-5 part C's
    ``_provenance_text`` fix controls. Before that fix, a fast-path answer
    naming a confirmed offering has no supporting text in the judge's prompt
    (catalog chunks are excluded from retrieval by design), so this fails;
    after the fix, the offerings block is there and it passes.
    """

    def __init__(self, answer: str, must_ground: str) -> None:
        super().__init__(answer=answer)
        self._must_ground = must_ground

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        if "grounding" in schema.model_fields:
            grounded = self._must_ground in system_prompt
            return schema.model_validate(
                {"grounding": {"passed": grounded, "reason": "" if grounded else "not grounded"}}
            )
        return await super().extract(
            system_prompt=system_prompt, user_input=user_input, schema=schema
        )


async def test_fast_path_answer_naming_offering_and_knowledge_detail_does_not_escalate(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """W-5 part C regression: a single reply naming both a confirmed offering
    and a knowledge-chunk-only detail must clear the grounding check, not
    escalate for lack of provenance the catalog chunk never carries."""
    tenant_id = await _seed_tenant(
        superuser_conn,
        contents=("We are open weekdays 9-5.",),
        offerings=(("Coffee", "Freshly brewed", 350),),
    )
    conversation_id = await _conversation_for(superuser_conn, tenant_id)
    provider = GroundingSensitiveProvider(
        answer="We serve Coffee, and we're open weekdays 9-5 [1].",
        must_ground="Coffee",
    )

    final_state = await build_graph().ainvoke(
        _initial_state(tenant_id, conversation_id, "What do you offer and when are you open?"),
        context=GraphContext(
            tenant_id=tenant_id,
            provider=provider,
            embedder=ZeroEmbedder(),
            reranker=PassthroughReranker(),
        ),
    )

    assert final_state["escalated"] is False
    assert final_state["inspection_decision"] == "ok"
    assert final_state["inspection"]["grounding"]["passed"] is True
