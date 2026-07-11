"""FastAPI dependency for the configured Reranker (T-011).

Mirrors app/llm/dependency.py's pattern - tests override this one callable
to stub reranking everywhere it's used.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.retrieval.rerank import Reranker, get_reranker


def get_reranker_dependency() -> Reranker:
    return get_reranker(get_settings())
