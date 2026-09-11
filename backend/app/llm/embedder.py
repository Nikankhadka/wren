"""The embedding seam, split out of ``LLMProvider``.

Chat and embeddings are independently swappable on purpose: the default $0
stack pairs a local sentence-transformers embedder (no API key, no rate
limit) with any hosted chat provider, and production can rebind either side
by env alone. ``get_embedder`` picks the implementation from
``settings.embedder`` ('local', 'azure' or 'google'), matching ``get_reranker``'s
pattern (app/retrieval/rerank.py).

Every implementation must produce vectors of exactly
``settings.embedding_dim`` dimensions - that is the schema contract with
``knowledge_chunks.embedding vector(N)`` (migration 0010). AzureOpenAIEmbedder
meets it by asking the API to truncate (text-embedding-3 models support a
``dimensions`` parameter), so local<->azure swaps need no migration;
GoogleEmbedder does the same through ``outputDimensionality``; LocalEmbedder
fails loudly on first use if the configured model's native dimension disagrees.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import httpx
from starlette.concurrency import run_in_threadpool

if TYPE_CHECKING:
    from openai import AsyncAzureOpenAI
    from sentence_transformers import SentenceTransformer

    from app.shared.config import Settings

_AZURE_API_VERSION = "2024-10-21"

# The native embeddings endpoint, not the OpenAI-compatible one LLM_BASE_URL
# points at: only the native API exposes outputDimensionality, which is what
# keeps a hosted embedder inside the vector(384) schema contract.
_GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class Embedder(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returned in the same order as ``texts``.

        Every vector has exactly ``settings.embedding_dim`` dimensions."""
        raise NotImplementedError

    async def warm(self) -> None:
        """Pre-load any lazily initialized model so the first real request does
        not pay for it. Deliberately concrete (not abstract) and a no-op by
        default: hosted backends have nothing to warm, and making it abstract
        would break every existing test double for no benefit."""
        return None


class LocalEmbedder(Embedder):
    """sentence-transformers embedder - the free, keyless default.

    The model is loaded lazily (and only once) on first use, same reasoning
    as LocalCrossEncoderReranker: importing sentence_transformers/torch at
    module import time would slow down every process that imports this
    module, even ones that never embed anything."""

    def __init__(self, model_name: str, expected_dim: int) -> None:
        self._model_name = model_name
        self._expected_dim = expected_dim
        self._model: SentenceTransformer | None = None

    def _load_model(self) -> SentenceTransformer:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    async def warm(self) -> None:
        await run_in_threadpool(self._load_model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = await run_in_threadpool(self._load_model)

        def _encode(texts: list[str]) -> list[list[float]]:
            vectors = model.encode(texts, normalize_embeddings=True)
            return [[float(value) for value in vector] for vector in vectors]

        vectors = await run_in_threadpool(_encode, texts)
        if vectors and len(vectors[0]) != self._expected_dim:
            raise ValueError(
                f"embedding model '{self._model_name}' produced "
                f"{len(vectors[0])}-dim vectors but EMBEDDING_DIM={self._expected_dim} "
                f"(and knowledge_chunks.embedding is vector({self._expected_dim})); "
                "pick a matching model or add a migration + re-ingest"
            )
        return vectors


class AzureOpenAIEmbedder(Embedder):
    """Azure OpenAI embeddings, truncated server-side to ``expected_dim``
    (Matryoshka truncation - supported by the text-embedding-3 family), so it
    stays schema-compatible with the local default without a migration."""

    def __init__(self, settings: Settings) -> None:
        from openai import AsyncAzureOpenAI

        self._client: AsyncAzureOpenAI = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=_AZURE_API_VERSION,
        )
        self._deployment = settings.azure_openai_embed_deployment
        self._expected_dim = settings.embedding_dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=self._deployment,
            input=texts,
            dimensions=self._expected_dim,
        )
        return [item.embedding for item in response.data]


class GoogleEmbedder(Embedder):
    """Google's native embeddings API, truncated server-side to ``expected_dim``
    via ``outputDimensionality`` (Matryoshka truncation), so it stays
    schema-compatible with the local default without a migration.

    Reuses ``LLM_API_KEY`` rather than introducing a second Google credential:
    the same AI Studio key serves chat and embeddings, and a second field would
    be one more thing to get out of sync in the deploy."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.llm_api_key
        self._model = settings.google_embed_model
        self._expected_dim = settings.embedding_dim
        # Lazily created and then held for the process, the same lifecycle
        # AzureOpenAIEmbedder's client has: get_embedder_dependency is
        # lru_cached, so there is one embedder and one pool per process.
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._get_client().post(
            f"{_GOOGLE_API_BASE}/models/{self._model}:batchEmbedContents",
            headers={"x-goog-api-key": self._api_key},
            json={
                "requests": [
                    {
                        "model": f"models/{self._model}",
                        "content": {"parts": [{"text": text}]},
                        # Top-level, not nested under `embedContentConfig`: the
                        # batch endpoint silently ignores the nested form for
                        # gemini-embedding-001 and returns the model's native
                        # 3072 dims (observed against the live API 2026-09-12).
                        "outputDimensionality": self._expected_dim,
                    }
                    for text in texts
                ]
            },
        )
        response.raise_for_status()
        vectors = [item["values"] for item in response.json()["embeddings"]]

        if vectors and len(vectors[0]) != self._expected_dim:
            raise ValueError(
                f"google embedding model {self._model!r} returned "
                f"{len(vectors[0])}-dim vectors but EMBEDDING_DIM={self._expected_dim} "
                f"(and knowledge_chunks.embedding is vector({self._expected_dim})); "
                "the endpoint ignored outputDimensionality - check the model name"
            )
        # Truncating a Matryoshka embedding costs it its unit norm, and the local
        # default normalizes (LocalEmbedder passes normalize_embeddings=True).
        # Renormalizing here keeps the two interchangeable for anything that
        # reads raw magnitudes, not just for cosine distance.
        return [_normalize(vector) for vector in vectors]


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def get_embedder(settings: Settings) -> Embedder:
    if settings.embedder == "azure":
        return AzureOpenAIEmbedder(settings)
    if settings.embedder == "google":
        return GoogleEmbedder(settings)
    return LocalEmbedder(settings.local_embed_model, settings.embedding_dim)
