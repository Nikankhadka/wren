"""T-030: tracing interface tests.

The no-op backend is the only one that exists today (Langfuse wiring is a
founder step, deliberately deferred - see tracing.py's own docstring) - these
tests prove it's genuinely inert and that the graph.py wrapper (T-030) opens
a span per node, using a recording fake that implements the same Protocol.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from typing import Any

import asyncpg
import pytest

from app.agents.graph import build_graph
from app.agents.state import AgentState, GraphContext
from app.core import db
from app.core.config import Settings, get_settings
from app.llm.provider import ChatMessage, SchemaT
from app.observability.tracing import NoOpTracer, get_tracer
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider, ZeroEmbedder


def test_noop_span_set_accepts_arbitrary_attributes_and_does_nothing() -> None:
    tracer = NoOpTracer()
    with tracer.turn(tenant_id=uuid.uuid4(), conversation_id=uuid.uuid4()) as turn:
        with turn.span("some_node", route="quoting", tokens=42) as span:
            span.set(anything="goes", nested={"a": 1})  # must not raise


def test_noop_spans_nest_freely() -> None:
    tracer = NoOpTracer()
    with tracer.turn(tenant_id=uuid.uuid4(), conversation_id=uuid.uuid4()) as turn:
        with turn.span("outer") as outer_span:
            with turn.span("inner") as inner_span:
                inner_span.set(x=1)
            outer_span.set(y=2)


def test_get_tracer_returns_noop_with_empty_keys() -> None:
    settings = get_settings()
    assert isinstance(get_tracer(settings), NoOpTracer)


def test_get_tracer_falls_back_to_noop_even_with_keys_set() -> None:
    """Langfuse keys alone don't wire a live backend - the SDK isn't a
    dependency yet (free-first: no paid-service dependency until the founder
    actually provisions it). Configured-but-unwired must not crash a turn."""
    settings = Settings(langfuse_public_key="pk-test", langfuse_secret_key="sk-test")
    assert isinstance(get_tracer(settings), NoOpTracer)


# --- graph.py wrapper: proves a span opens per node --------------------------


class _RecordingSpan:
    def __init__(self, name: str, log: list[tuple[str, dict[str, Any]]]) -> None:
        self._name = name
        self._log = log

    def set(self, **attributes: Any) -> None:
        self._log.append((self._name, attributes))


class _RecordingTurn:
    def __init__(self, log: list[tuple[str, dict[str, Any]]]) -> None:
        self._log = log

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[_RecordingSpan]:
        yield _RecordingSpan(name, self._log)


class FakeKnowledgeProvider(BaseFakeProvider):
    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        return schema.model_validate({"route": "knowledge", "confidence": 1.0, "reason": "t"})

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        for delta in ["An", " answer", "."]:
            yield delta


class PassthroughReranker(Reranker):
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]


@pytest.mark.db
async def test_graph_opens_a_span_per_node(
    superuser_conn: asyncpg.Connection[Any], migrated_db: str
) -> None:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        tenant_id: uuid.UUID = await superuser_conn.fetchval(
            "insert into tenants (slug, name) values ($1, 'Tracing Test Co') returning id",
            f"tracing-{uuid.uuid4().hex[:8]}",
        )
        await superuser_conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)

        log: list[tuple[str, dict[str, Any]]] = []
        turn = _RecordingTurn(log)
        graph = build_graph()
        context = GraphContext(
            tenant_id=tenant_id,
            provider=FakeKnowledgeProvider(),
            embedder=ZeroEmbedder(),
            reranker=PassthroughReranker(),
            turn=turn,
        )
        initial_state: AgentState = {
            "conversation_id": "test",
            "tenant_id": str(tenant_id),
            "messages": [{"role": "customer", "content": "What are your hours?"}],
            "route": None,
            "route_confidence": None,
            "retrieved_chunks": [],
            "selections": [],
            "engine_quote": None,
            "draft_response": "",
            "inspection": None,
            "escalated": False,
        }
        await graph.ainvoke(initial_state, context=context)

        span_names = [name for name, _ in log]
        # supervisor routes to knowledge (no seeded chunk -> refusal, which
        # is draft_deterministic, so inspection short-circuits) - both nodes
        # must have opened a span regardless.
        assert "supervisor" in span_names
        assert "knowledge" in span_names
        assert "inspection" in span_names
    finally:
        await db.close_pool()
