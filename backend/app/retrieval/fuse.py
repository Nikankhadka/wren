"""T-009: Reciprocal Rank Fusion (RRF), k=60.

Combines multiple ranked result lists (dense, sparse) into one ranking by
rank position alone, not raw scores - dense cosine similarity and FTS
ts_rank are on incomparable scales, so fusing by rank (not by score value)
is what makes combining them meaningful.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from app.retrieval.types import RetrievedChunk

DEFAULT_K = 60


def reciprocal_rank_fusion(
    result_lists: list[list[RetrievedChunk]], *, k: int = DEFAULT_K
) -> list[RetrievedChunk]:
    """Fuse ranked lists; a chunk appearing in multiple lists gets the summed
    contribution from each. Returns chunks sorted by fused score, descending,
    each with ``score`` replaced by its RRF score."""
    rrf_scores: dict[UUID, float] = {}
    chunks_by_id: dict[UUID, RetrievedChunk] = {}

    for results in result_lists:
        for rank, chunk in enumerate(results, start=1):
            rrf_scores[chunk.id] = rrf_scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
            chunks_by_id[chunk.id] = chunk

    ordered_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
    return [replace(chunks_by_id[cid], score=rrf_scores[cid]) for cid in ordered_ids]
