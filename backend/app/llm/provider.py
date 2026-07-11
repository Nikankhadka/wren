"""The chat LLM provider abstraction (T-006).

Every call site that needs a chat model (onboarding extraction; agents and
the pricing-adjacent generation calls in later phases) goes through this
interface, never a vendor SDK directly - so tests stub a provider instead of
hitting a real API, and swapping providers never touches call sites.
Embeddings are a separate, independently swappable seam: app/llm/embedder.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TypedDict, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ChatMessage(TypedDict):
    role: str
    content: str


class LLMProvider(ABC):
    @abstractmethod
    async def extract(
        self, *, system_prompt: str, user_input: str, schema: type[SchemaT]
    ) -> SchemaT:
        """Extract structured data matching ``schema`` from freeform ``user_input``.

        ``system_prompt`` carries the extraction instructions; ``user_input`` is
        the caller's freeform text (e.g. an onboarding admin's chat reply).
        Implementations must return an instance of exactly ``schema`` - never a
        raw string or dict - so callers never hand-parse model output.
        """
        raise NotImplementedError

    @abstractmethod
    async def chat(self, messages: list[ChatMessage]) -> str:
        """Freeform, non-streamed chat completion - for callers that need the
        whole response before doing anything with it (tool-calling reasoning
        in phase 2's agents). T-011's bare customer chat uses ``chat_stream``
        instead."""
        raise NotImplementedError

    @abstractmethod
    def chat_stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """Freeform chat completion, yielding text deltas as they arrive - for
        callers that stream to a client (T-011's bare customer chat, over SSE)."""
        raise NotImplementedError
