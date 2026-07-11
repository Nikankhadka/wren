"""Shared LLMProvider / Embedder test doubles.

``BaseFakeProvider`` implements every abstract method with a
``NotImplementedError`` stub - subclasses override only the method(s) their
test actually exercises, so adding a new abstract method to ``LLMProvider``
never forces every test double in the suite to grow a matching no-op.

``ZeroEmbedder`` is the standard embedder double: dimensionally correct
(``settings.embedding_dim``, matching knowledge_chunks.embedding's
vector(N)) but content-blind - fine for tests that only need ingestion or
retrieval plumbing to work, not meaningful dense rankings.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.config import get_settings
from app.llm.embedder import Embedder
from app.llm.provider import ChatMessage, LLMProvider, SchemaT

EMBEDDING_DIM = get_settings().embedding_dim


class BaseFakeProvider(LLMProvider):
    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        raise NotImplementedError

    async def chat(self, messages: list[ChatMessage]) -> str:
        raise NotImplementedError

    async def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # pragma: no cover - unreachable; makes this an async generator function


class ZeroEmbedder(Embedder):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * EMBEDDING_DIM for _ in texts]
