"""Shared LLMProvider test doubles.

``BaseFakeProvider`` implements every abstract method with a
``NotImplementedError`` stub - subclasses override only the method(s) their
test actually exercises, so adding a new abstract method to ``LLMProvider``
never forces every test double in the suite to grow a matching no-op.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.llm.provider import ChatMessage, LLMProvider, SchemaT


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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
