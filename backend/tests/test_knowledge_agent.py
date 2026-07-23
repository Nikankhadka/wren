"""T-014: Knowledge Agent node test - stubbed retrieval/provider, driven
through the graph (get_runtime() requires an actual node execution, see
T-013's memory entry). Confirms parity with T-011's behavior and that chunk
provenance lands in state for Inspection to use later.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import asyncpg
import pytest

from app.agents.graph import build_graph
from app.agents.state import AgentState, GraphContext
from app.core import db
from app.llm.provider import ChatMessage, SchemaT
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class FakeKnowledgeProvider(BaseFakeProvider):
    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        # Only the supervisor's routing call reaches extract() here.
        return schema.model_validate({"route": "knowledge", "confidence": 1.0, "reason": "test"})

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        for delta in ["An", " answer", " [1]", "."]:
            yield delta


class PassthroughReranker(Reranker):
    """Keeps input order but honors the Reranker [0, 1] relevance contract:
    the candidates handed to it in these tests are the intended-relevant
    chunk, so it scores them at the top of the range (1.0). Returning the raw
    RRF-fused score instead would land near 0.016 and now be refused, which
    would test the threshold rather than the node."""

    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return [replace(chunk, score=1.0) for chunk in candidates[:top_k]]


def _initial_state(message: str) -> AgentState:
    return {
        "conversation_id": "test",
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


async def _seed_tenant_with_chunk(conn: asyncpg.Connection[Any], *, content: str) -> uuid.UUID:
    tenant_id: uuid.UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Knowledge Agent Test Co') returning id",
        f"knowledge-agent-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    document_id: uuid.UUID = await conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'faq.md', 'faq', 'ready') returning id",
        tenant_id,
    )
    await conn.execute(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, $3, $4, $5)",
        tenant_id,
        document_id,
        content,
        [0.0] * EMBEDDING_DIM,
        json.dumps({"source": "faq.md", "chunk_index": 0, "kind": "prose"}),
    )
    return tenant_id


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def test_knowledge_node_returns_provenance_and_draft_response(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id = await _seed_tenant_with_chunk(superuser_conn, content="We are open weekdays 9-5.")
    graph = build_graph()
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeKnowledgeProvider(),
        embedder=ZeroEmbedder(),
        reranker=PassthroughReranker(),
    )

    final_state = await graph.ainvoke(_initial_state("What are your hours?"), context=context)

    assert final_state["draft_response"] == "An answer [1]."
    assert len(final_state["retrieved_chunks"]) == 1
    chunk = final_state["retrieved_chunks"][0]
    assert chunk["content"] == "We are open weekdays 9-5."
    assert chunk["metadata"]["source"] == "faq.md"
    assert "id" in chunk


async def test_knowledge_node_refuses_with_empty_provenance_when_no_chunks(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    tenant_id: uuid.UUID = await superuser_conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Empty Co') returning id",
        f"knowledge-agent-empty-{uuid.uuid4().hex[:8]}",
    )
    await superuser_conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)

    graph = build_graph()
    context = GraphContext(
        tenant_id=tenant_id,
        provider=FakeKnowledgeProvider(),
        embedder=ZeroEmbedder(),
        reranker=PassthroughReranker(),
    )

    final_state = await graph.ainvoke(_initial_state("anything at all"), context=context)

    assert "I don't have information about that" in final_state["draft_response"]
    assert final_state["retrieved_chunks"] == []
