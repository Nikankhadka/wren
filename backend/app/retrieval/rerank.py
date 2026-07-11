"""T-009: cross-encoder reranking, one interface with two implementations.

``get_reranker`` picks the implementation from ``settings.reranker`` ('cohere'
or 'local') - never a literal at the call site, matching the LLM provider
abstraction's pattern (app/llm/provider.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import TYPE_CHECKING

import httpx
from starlette.concurrency import run_in_threadpool

from app.retrieval.types import RetrievedChunk

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

    from app.core.config import Settings

_LOCAL_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"
_COHERE_MODEL = "rerank-v3.5"


class Reranker(ABC):
    @abstractmethod
    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        """Re-score ``candidates`` against ``query`` and return the top ``top_k``,
        each with ``score`` replaced by the reranker's own relevance score."""
        raise NotImplementedError


class CohereReranker(Reranker):
    """Cohere Rerank free tier, called directly over HTTP (no SDK dependency
    for a single endpoint)."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _COHERE_RERANK_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": _COHERE_MODEL,
                    "query": query,
                    "documents": [c.content for c in candidates],
                    "top_n": top_k,
                },
            )
            response.raise_for_status()
            body = response.json()

        return [
            replace(candidates[result["index"]], score=result["relevance_score"])
            for result in body["results"]
        ]


class LocalCrossEncoderReranker(Reranker):
    """``cross-encoder/ms-marco-MiniLM-L-6-v2`` fallback - no external API key
    needed. The model is loaded lazily (and only once) on first use, since
    importing sentence_transformers/torch at module import time would slow
    down every process that imports this module, even ones that never
    rerank anything (e.g. the migration runner)."""

    def __init__(self) -> None:
        self._model: CrossEncoder | None = None

    def _load_model(self) -> CrossEncoder:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(_LOCAL_MODEL_NAME)
        return self._model

    async def rerank(
        self, *, query: str, candidates: list[RetrievedChunk], top_k: int
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        model = await run_in_threadpool(self._load_model)
        pairs = [(query, c.content) for c in candidates]

        def _predict(pairs: list[tuple[str, str]]) -> list[float]:
            # sentence-transformers' predict() type stubs cover its full
            # multi-modal (text/image/audio/video) input union, which mypy
            # can't reconcile with the plain (str, str) pairs a cross-encoder
            # text rerank actually takes.
            return list(model.predict(pairs))  # type: ignore[arg-type]

        scores = await run_in_threadpool(_predict, pairs)
        ranked = sorted(
            zip(candidates, scores, strict=True), key=lambda pair: pair[1], reverse=True
        )
        return [replace(chunk, score=float(score)) for chunk, score in ranked[:top_k]]


def get_reranker(settings: Settings) -> Reranker:
    if settings.reranker == "cohere":
        return CohereReranker(settings.cohere_api_key)
    return LocalCrossEncoderReranker()
