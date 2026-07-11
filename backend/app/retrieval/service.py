"""T-009: the single retrieval entry point.

Bare chat (T-011), agents, and recommendation (phase 2) all call
``retrieve`` - none of them touch dense/sparse/fuse/rerank directly, so
swapping any one stage never touches a caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.retrieval.dense import dense_search
from app.retrieval.fuse import reciprocal_rank_fusion
from app.retrieval.sparse import sparse_search
from app.retrieval.types import RetrievedChunk

if TYPE_CHECKING:
    from app.core.db import AppConnection
    from app.llm.provider import LLMProvider
    from app.retrieval.rerank import Reranker

DEFAULT_TOP_K = 5


async def retrieve(
    conn: AppConnection,
    *,
    tenant_id: UUID,
    query: str,
    provider: LLMProvider,
    reranker: Reranker,
    top_k: int = DEFAULT_TOP_K,
    metadata_kind: str | None = None,
) -> list[RetrievedChunk]:
    """``metadata_kind`` scopes both dense and sparse search to chunks whose
    ``metadata.kind`` matches exactly - e.g. ``'catalog_item'`` for the
    Recommendation Agent (T-015), which must never recommend from prose."""
    query_embedding = (await provider.embed([query]))[0]

    dense_results = await dense_search(
        conn, tenant_id=tenant_id, query_embedding=query_embedding, metadata_kind=metadata_kind
    )
    sparse_results = await sparse_search(
        conn, tenant_id=tenant_id, query=query, metadata_kind=metadata_kind
    )
    fused = reciprocal_rank_fusion([dense_results, sparse_results])

    return await reranker.rerank(query=query, candidates=fused, top_k=top_k)
