"""T-009: Reciprocal Rank Fusion unit tests - pure function, no DB."""

from __future__ import annotations

import uuid

from app.retrieval.fuse import reciprocal_rank_fusion
from app.retrieval.types import RetrievedChunk


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(id=uuid.uuid4(), content="x", score=score)


def test_chunk_ranked_first_in_both_lists_wins() -> None:
    a, b, c = _chunk(0.9), _chunk(0.8), _chunk(0.7)
    dense = [a, b, c]
    sparse = [a, c, b]

    fused = reciprocal_rank_fusion([dense, sparse])

    assert fused[0].id == a.id


def test_chunk_appearing_in_both_lists_outranks_single_list_chunk() -> None:
    a, b = _chunk(0.9), _chunk(0.9)
    dense = [a, b]
    sparse = [a]  # a appears in both lists, b only in one

    fused = reciprocal_rank_fusion([dense, sparse])

    assert fused[0].id == a.id
    assert len(fused) == 2


def test_fused_score_is_rrf_not_original_score() -> None:
    a = _chunk(score=0.123)
    fused = reciprocal_rank_fusion([[a]], k=60)

    # rank 1 in a single list: 1 / (60 + 1)
    assert fused[0].score == 1.0 / 61
    assert fused[0].score != 0.123


def test_empty_result_lists_produce_no_chunks() -> None:
    assert reciprocal_rank_fusion([[], []]) == []


def test_disjoint_lists_include_all_chunks() -> None:
    a, b = _chunk(1.0), _chunk(1.0)
    fused = reciprocal_rank_fusion([[a], [b]])
    assert {c.id for c in fused} == {a.id, b.id}
