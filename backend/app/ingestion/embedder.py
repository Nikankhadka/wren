"""T-008: batch embedding calls through an LLMProvider.

A separate thin module (rather than inlining the batching loop in
pipeline.py) so both document ingestion and catalog-item ingestion share the
exact same batch-size behavior.
"""

from __future__ import annotations

from app.llm.provider import LLMProvider

BATCH_SIZE = 64


async def embed_texts(provider: LLMProvider, texts: list[str]) -> list[list[float]]:
    """Embed ``texts`` in batches of ``BATCH_SIZE``, preserving order."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        vectors.extend(await provider.embed(batch))
    return vectors
