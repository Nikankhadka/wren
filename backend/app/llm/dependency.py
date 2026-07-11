"""FastAPI dependency for the configured LLMProvider (T-006/T-008).

Shared by every router that needs a provider (onboarding, knowledge) so
tests can override this single callable and stub every call site at once.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.llm.azure import AzureOpenAIProvider
from app.llm.provider import LLMProvider


def get_llm_provider() -> LLMProvider:
    return AzureOpenAIProvider(get_settings())
