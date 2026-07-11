"""FastAPI dependencies for the configured LLMProvider and Embedder.

Shared by every router that needs one (onboarding, knowledge, chat) so tests
override a single callable and stub every call site at once. Both factories
key off settings enums (LLM_PROVIDER, EMBEDDER) - the reranker's pattern
(app/retrieval/rerank.py) - so providers are swapped by env, never by code.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.llm.azure import AzureOpenAIProvider
from app.llm.embedder import Embedder, get_embedder
from app.llm.openai_compat import OpenAICompatProvider
from app.llm.provider import LLMProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "openai_compat":
        return OpenAICompatProvider(settings)
    return AzureOpenAIProvider(settings)


@lru_cache
def get_embedder_dependency() -> Embedder:
    # Cached (unlike the stateless chat providers) so LocalEmbedder's lazily
    # loaded sentence-transformers model is shared process-wide instead of
    # being re-loaded per request.
    return get_embedder(get_settings())
