"""T-010: unit tests for the eval script's metric functions, known-answer
fixtures - pure functions, no DB."""

from __future__ import annotations

import uuid

from app.retrieval.types import RetrievedChunk
from evals.retrieval_eval import (
    is_relevant,
    mrr,
    ndcg_at_k,
    recall_at_k,
)


def test_recall_at_k_counts_hits_within_k() -> None:
    ranks = [1, 3, None, 7]
    assert recall_at_k(ranks, 3) == 0.5  # rank 1 and 3 are within 3; None and 7 aren't
    assert recall_at_k(ranks, 5) == 0.5  # 7 still misses at k=5
    assert recall_at_k(ranks, 10) == 0.75  # only the None miss remains


def test_recall_at_k_empty_is_zero() -> None:
    assert recall_at_k([], 5) == 0.0


def test_mrr_known_answer() -> None:
    # 1/1 + 1/2 + 0 + 1/4, averaged over 4 cases
    ranks = [1, 2, None, 4]
    expected = (1.0 + 0.5 + 0.0 + 0.25) / 4
    assert mrr(ranks) == expected


def test_mrr_all_first_rank_is_one() -> None:
    assert mrr([1, 1, 1]) == 1.0


def test_mrr_all_missing_is_zero() -> None:
    assert mrr([None, None]) == 0.0


def test_ndcg_at_k_known_answer() -> None:
    import math

    ranks = [1, 2, None]
    expected = (1.0 + 1.0 / math.log2(3) + 0.0) / 3
    assert ndcg_at_k(ranks, 5) == expected


def test_ndcg_at_k_excludes_ranks_beyond_k() -> None:
    assert ndcg_at_k([10], 5) == 0.0
    assert ndcg_at_k([5], 5) > 0.0


def test_is_relevant_matches_catalog_item_by_name_prefix() -> None:
    chunk = RetrievedChunk(
        id=uuid.uuid4(),
        content="Screen Repair - Flagship (OEM): Original display ($179.00)",
        metadata={"kind": "catalog_item", "catalog_item_id": "abc"},
    )
    assert is_relevant(chunk, {"catalog_item_name": "Screen Repair - Flagship (OEM)"})
    assert not is_relevant(chunk, {"catalog_item_name": "Battery Replacement - Standard"})


def test_is_relevant_matches_prose_chunk_by_source_and_index() -> None:
    chunk = RetrievedChunk(
        id=uuid.uuid4(),
        content="policy text",
        metadata={"kind": "prose", "source": "policy.md", "chunk_index": 1},
    )
    assert is_relevant(chunk, {"source": "policy.md", "chunk_index": 1})
    assert not is_relevant(chunk, {"source": "policy.md", "chunk_index": 0})
    assert not is_relevant(chunk, {"source": "faq.md", "chunk_index": 1})


def test_is_relevant_unknown_expected_shape_is_false() -> None:
    chunk = RetrievedChunk(id=uuid.uuid4(), content="x", metadata={})
    assert not is_relevant(chunk, {"something_else": "value"})
