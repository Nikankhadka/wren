"""The embedding seam, split out of ``LLMProvider``.

Chat and embeddings are independently swappable on purpose: the default $0
stack pairs a local sentence-transformers embedder (no API key, no rate
limit) with any hosted chat provider, and production can rebind either side
by env alone. ``get_embedder`` picks the implementation from
``settings.embedder`` ('local' or 'azure'), matching ``get_reranker``'s
pattern (app/retrieval/rerank.py).

Every implementation must produce vectors of exactly
``settings.embedding_dim`` dimensions - that is the schema contract with
``knowledge_chunks.embedding vector(N)`` (migration 0010). AzureOpenAIEmbedder
meets it by asking the API to truncate (text-embedding-3 models support a
``dimensions`` parameter), so local<->azure swaps need no migration;
LocalEmbedder fails loudly on first use if the configured model's native
dimension disagrees.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from starlette.concurrency import run_in_threadpool

if TYPE_CHECKING:
    from openai import AsyncAzureOpenAI
    from sentence_transformers import SentenceTransformer

    from app.core.config import Settings

_AZURE_API_VERSION = "2024-10-21"


class Embedder(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returned in the same order as ``texts``.

        Every vector has exactly ``settings.embedding_dim`` dimensions."""
        raise NotImplementedError


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


def get_embedder(settings: Settings) -> Embedder:
    if settings.embedder == "azure":
        return AzureOpenAIEmbedder(settings)
    return LocalEmbedder(settings.local_embed_model, settings.embedding_dim)
