"""The LLM provider abstraction (T-006).

Every call site that needs a model (onboarding extraction now; agents,
embeddings, and the pricing-adjacent generation calls in later phases) goes
through this interface, never a vendor SDK directly - so tests stub a
provider instead of hitting a real API, and swapping providers never touches
call sites. See docs/design/... architecture note: "Azure OpenAI behind a
thin provider abstraction."
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


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
