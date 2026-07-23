"""The Reranker [0, 1] relevance contract (regression guard).

The local cross-encoder emits raw logits, routinely negative for a genuinely
relevant passage. A single absolute refusal threshold is applied to whatever
score a reranker returns, so if the local backend leaks raw logits the
knowledge agent refuses correct answers (a warranty passage that ranked #1 at
logit -0.11 used to be discarded). These tests pin the fix: the score handed
back is a [0, 1] probability, and rank order is preserved.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.retrieval.rerank import LocalCrossEncoderReranker, _sigmoid
from app.retrieval.types import RetrievedChunk


def _chunk(content: str) -> RetrievedChunk:
    return RetrievedChunk(id=uuid4(), content=content, score=0.0, metadata={})


@pytest.mark.parametrize(
    "logit, expected",
    [(0.0, 0.5), (-0.1122, 0.472), (1.4446, 0.809), (-8.8, 0.00015)],
)
def test_sigmoid_maps_logits_into_unit_interval(logit: float, expected: float) -> None:
    result = _sigmoid(logit)
    assert 0.0 <= result <= 1.0
    assert result == pytest.approx(expected, abs=1e-3)


def test_sigmoid_survives_extreme_logits_without_overflow() -> None:
    # Very negative logits are the norm for the irrelevant candidates in a
    # fused batch; the guarded form must not raise on them.
    assert _sigmoid(-1000.0) == pytest.approx(0.0, abs=1e-9)
    assert _sigmoid(1000.0) == pytest.approx(1.0, abs=1e-9)


class _StubModel:
    """Stands in for the CrossEncoder so no weights are loaded: returns a
    fixed logit per candidate, in input order."""

    def __init__(self, logits: list[float]) -> None:
        self._logits = logits

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        return self._logits


async def test_local_reranker_returns_probabilities_and_keeps_order() -> None:
    reranker = LocalCrossEncoderReranker()
    # A relevant passage (negative logit) and clear noise (very negative).
    reranker._model = _StubModel([-0.1122, -8.8])  # type: ignore[assignment]

    ranked = await reranker.rerank(
        query="warranty?",
        candidates=[_chunk("relevant"), _chunk("noise")],
        top_k=5,
    )

    assert [c.content for c in ranked] == ["relevant", "noise"]
    assert all(0.0 <= c.score <= 1.0 for c in ranked)
    # The relevant passage clears a small positive refusal bar; the noise does not.
    assert ranked[0].score > 0.05
    assert ranked[1].score < 0.05
