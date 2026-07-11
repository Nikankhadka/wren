"""T-009: hybrid retrieval integration tests against real Postgres.

Seeds two tenants with hand-picked embeddings/content (real pgvector +
tsvector math, not mocked) via the superuser connection (matching
test_rls.py's seeding pattern - bypasses RLS as table owner), then proves
dense/sparse/retrieve return the right chunks and never leak across tenants
through the app pool's RLS-scoped connections - the ticket's own accept
criteria ("obvious queries return the right chunks", "zero cross-tenant
results with two tenants seeded").
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import pytest
import pytest_asyncio

from app.core import db
from app.retrieval.dense import dense_search
from app.retrieval.rerank import Reranker
from app.retrieval.service import retrieve
from app.retrieval.sparse import sparse_search
from app.retrieval.types import RetrievedChunk
from tests.conftest import _app_dsn_for
from tests.fakes import BaseFakeProvider

pytestmark = pytest.mark.db

DIMENSIONS = 1536


def _basis_vector(index: int) -> list[float]:
    """An orthogonal unit vector along dimension `index` - two basis vectors
    are exactly as dissimilar as two embeddings can be, so cosine distance
    ordering is unambiguous without needing a real embedding model."""
    vector = [0.0] * DIMENSIONS
    vector[index] = 1.0
    return vector


class FakeEmbedProvider(BaseFakeProvider):
    """Always embeds a query as basis vector 0 - paired with seeding the
    "right" chunk at basis vector 0 too, so dense search has an unambiguous
    correct answer to converge on."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_basis_vector(0) for _ in texts]


class FakeReranker(Reranker):
    """Identity passthrough, sorted by the fused score - proves retrieve()'s
    wiring without loading a real cross-encoder model in the test suite."""

    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        return sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]


@pytest_asyncio.fixture
async def pool(migrated_db: str) -> AsyncIterator[Any]:
    created = await db.create_pool(dsn=_app_dsn_for(migrated_db), min_size=1, max_size=4)
    try:
        yield created
    finally:
        await db.close_pool()


async def _seed_tenant_with_chunk(
    conn: asyncpg.Connection[Any], *, slug: str, content: str, embedding: list[float]
) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = await conn.fetchval(
        "insert into tenants (slug, name) values ($1, $2) returning id", slug, "Retrieval Test Co"
    )
    await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    document_id = await conn.fetchval(
        "insert into documents (tenant_id, filename, doc_type, status) "
        "values ($1, 'doc.md', 'policy', 'ready') returning id",
        tenant_id,
    )
    chunk_id = await conn.fetchval(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, $3, $4, '{}') returning id",
        tenant_id,
        document_id,
        content,
        embedding,
    )
    return tenant_id, chunk_id


async def _seed_chunk(
    conn: asyncpg.Connection[Any],
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    content: str,
    embedding: list[float],
) -> uuid.UUID:
    chunk_id: uuid.UUID = await conn.fetchval(
        "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
        "values ($1, $2, $3, $4, '{}') returning id",
        tenant_id,
        document_id,
        content,
        embedding,
    )
    return chunk_id


async def test_dense_search_ranks_the_closer_embedding_first(
    pool: Any, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_id, close_id = await _seed_tenant_with_chunk(
        superuser_conn,
        slug=f"dense-{uuid.uuid4().hex[:8]}",
        content="close match",
        embedding=_basis_vector(0),
    )
    document_id = await superuser_conn.fetchval(
        "select document_id from knowledge_chunks where id = $1", close_id
    )
    far_id = await _seed_chunk(
        superuser_conn,
        tenant_id=tenant_id,
        document_id=document_id,
        content="far match",
        embedding=_basis_vector(1),
    )

    async with db.tenant_context(tenant_id, "customer") as conn:
        results = await dense_search(conn, tenant_id=tenant_id, query_embedding=_basis_vector(0))

    assert results[0].id == close_id
    assert results[-1].id == far_id
    assert results[0].score > results[-1].score


async def test_sparse_search_finds_matching_keywords(
    pool: Any, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_id, matching_id = await _seed_tenant_with_chunk(
        superuser_conn,
        slug=f"sparse-{uuid.uuid4().hex[:8]}",
        content="We offer screen repair for cracked phones",
        embedding=_basis_vector(0),
    )
    document_id = await superuser_conn.fetchval(
        "select document_id from knowledge_chunks where id = $1", matching_id
    )
    await _seed_chunk(
        superuser_conn,
        tenant_id=tenant_id,
        document_id=document_id,
        content="Our opening hours are nine to five",
        embedding=_basis_vector(1),
    )

    async with db.tenant_context(tenant_id, "customer") as conn:
        results = await sparse_search(conn, tenant_id=tenant_id, query="screen repair")

    assert len(results) == 1
    assert results[0].id == matching_id


async def test_dense_and_sparse_never_cross_tenants(
    pool: Any, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_a, chunk_a = await _seed_tenant_with_chunk(
        superuser_conn,
        slug=f"iso-a-{uuid.uuid4().hex[:8]}",
        content="tenant a secret",
        embedding=_basis_vector(0),
    )
    _tenant_b, chunk_b = await _seed_tenant_with_chunk(
        superuser_conn,
        slug=f"iso-b-{uuid.uuid4().hex[:8]}",
        content="tenant a secret",
        embedding=_basis_vector(0),
    )

    async with db.tenant_context(tenant_a, "customer") as conn:
        dense_results = await dense_search(
            conn, tenant_id=tenant_a, query_embedding=_basis_vector(0)
        )
        sparse_results = await sparse_search(conn, tenant_id=tenant_a, query="secret")

    dense_ids = {r.id for r in dense_results}
    sparse_ids = {r.id for r in sparse_results}
    assert chunk_a in dense_ids
    assert chunk_b not in dense_ids
    assert chunk_a in sparse_ids
    assert chunk_b not in sparse_ids


async def test_retrieve_end_to_end_is_tenant_scoped(
    pool: Any, superuser_conn: asyncpg.Connection[Any]
) -> None:
    tenant_a, chunk_a = await _seed_tenant_with_chunk(
        superuser_conn,
        slug=f"e2e-a-{uuid.uuid4().hex[:8]}",
        content="Screen repairs start at fifty dollars",
        embedding=_basis_vector(0),
    )
    await _seed_tenant_with_chunk(
        superuser_conn,
        slug=f"e2e-b-{uuid.uuid4().hex[:8]}",
        content="Screen repairs start at fifty dollars",
        embedding=_basis_vector(0),
    )

    provider = FakeEmbedProvider()
    reranker = FakeReranker()
    async with db.tenant_context(tenant_a, "customer") as conn:
        results = await retrieve(
            conn,
            tenant_id=tenant_a,
            query="screen repair",
            provider=provider,
            reranker=reranker,
            top_k=5,
        )

    assert len(results) == 1
    assert results[0].id == chunk_a
