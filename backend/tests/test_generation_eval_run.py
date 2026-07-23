"""T-023: DB-backed integration test for evals/generation_eval.py's
orchestration (run_eval, _sync_eval_cases, _write_eval_run) using a fake
provider/embedder - proves the wiring is correct without depending on a
real (rate-limited, free-tier) LLM. Real-LLM numbers are a separate,
manual concern (same convention as T-013's "live-model accuracy check
pending real credentials" - see .agents/memory.md).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any, get_args
from uuid import UUID

import asyncpg
import pytest

from app.agents.knowledge import REFUSAL_MESSAGE
from app.core import db
from app.llm.provider import ChatMessage, SchemaT
from app.retrieval.rerank import Reranker
from app.retrieval.types import RetrievedChunk
from evals.generation_eval import GenerationCase, run_eval, score_case
from tests.conftest import _app_dsn_for
from tests.fakes import EMBEDDING_DIM, BaseFakeProvider, ZeroEmbedder

pytestmark = pytest.mark.db


class FakeGenerationProvider(BaseFakeProvider):
    """Dispatches on schema shape rather than call order, since
    ClaimVerdicts/CitationVerdicts share a top-level 'verdicts' field. Falls
    back to an empty-dict validate() for anything unrecognized - T-021's
    InspectionVerdicts (the graph always runs Inspection too) defaults every
    field to a passing verdict, so this still produces a sane all-pass
    result rather than needing its own branch here."""

    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        fields = schema.model_fields
        if "route" in fields:
            return schema.model_validate({"route": "knowledge", "confidence": 1.0, "reason": "t"})
        if "claims" in fields:
            return schema.model_validate({"claims": ["We are open weekdays."]})
        if "questions" in fields:
            return schema.model_validate({"questions": ["When are you open?"]})
        if "verdicts" in fields:
            item_type = get_args(fields["verdicts"].annotation)[0]
            if "claim" in item_type.model_fields:
                return schema.model_validate(
                    {"verdicts": [{"claim": "We are open weekdays.", "supported": True}]}
                )
            return schema.model_validate({"verdicts": [{"citation_index": 1, "supported": True}]})
        return schema.model_validate({})

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        for delta in ["We are ", "open weekdays", " [1]."]:
            yield delta


class PassthroughReranker(Reranker):
    # Scores the kept chunk at the top of the [0, 1] relevance contract so it
    # clears the knowledge refusal threshold; the raw fused score would not.
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return [replace(chunk, score=1.0) for chunk in candidates[:top_k]]


@pytest.fixture(autouse=True)
async def _pool(migrated_db: str) -> AsyncIterator[None]:
    await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    yield
    await db.close_pool()


async def _seed_tenant_with_chunk(conn: asyncpg.Connection[Any]) -> UUID:
    tenant_id: UUID = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, 'Generation Eval Test Co') returning id",
        f"generation-eval-{uuid.uuid4().hex[:8]}",
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    document_id = await conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'faq.md', 'faq', 'ready') returning id",
        tenant_id,
    )
    await conn.execute(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, $3, $4, $5)",
        tenant_id,
        document_id,
        "We are open weekdays 9am to 5pm.",
        [0.0] * EMBEDDING_DIM,
        json.dumps({"source": "faq.md", "chunk_index": 0, "kind": "prose"}),
    )
    return tenant_id


async def test_run_eval_orchestration_produces_metrics_and_writes_eval_cases(
    superuser_conn: asyncpg.Connection[Any],
) -> None:
    """Proves run_eval's wiring (graph drive, scoring, eval_cases sync) is
    correct without depending on a real, rate-limited LLM. Only the
    positive-case path is exercised here - whether ZeroEmbedder's uniform
    vectors spuriously "match" an unrelated out-of-domain query is not a
    reliable signal either way, so refusal behavior is unit-tested directly
    against score_case() instead (test_negative_case_refusal_is_scored_correctly)."""
    tenant_id = await _seed_tenant_with_chunk(superuser_conn)
    cases = [
        GenerationCase(
            question="What are your hours?",
            reference_facts=["open weekdays"],
            expected_sources=["faq.md"],
        )
    ]

    metrics, results = await run_eval(
        tenant_id=tenant_id,
        cases=cases,
        provider=FakeGenerationProvider(),
        embedder=ZeroEmbedder(),
        reranker=PassthroughReranker(),
    )

    assert metrics["cases"] == 1
    assert metrics["positive_cases"] == 1
    # Exact values, not ranges - the fakes are deterministic: one claim
    # judged supported (1.0), one citation judged supported (1.0), and
    # ZeroEmbedder's zero vectors make every cosine similarity 0.0.
    assert metrics["faithfulness"] == 1.0
    assert metrics["answer_relevancy"] == 0.0
    assert metrics["citation_faithfulness"] == 1.0
    assert results[0].answer == "We are open weekdays [1]."

    case_rows = await superuser_conn.fetch(
        "select input from eval_cases where tenant_id = $1 and case_type = 'generation'",
        tenant_id,
    )
    assert len(case_rows) == 1


async def test_negative_case_refusal_is_scored_correctly() -> None:
    case = GenerationCase(question="What's the capital of France?", negative=True)
    result = await score_case(
        case, REFUSAL_MESSAGE, [], provider=FakeGenerationProvider(), embedder=ZeroEmbedder()
    )
    assert result.refusal_correct is True
    assert result.faithfulness is None
