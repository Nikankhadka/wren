"""T-008: batch embedding calls through an Embedder.

A separate thin module (rather than inlining the batching loop in
pipeline.py) so both document ingestion and catalog-item ingestion share the
exact same batch-size behavior.
"""

from __future__ import annotations

from app.llm.embedder import Embedder

BATCH_SIZE = 64


async def embed_texts(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    """Embed ``texts`` in batches of ``BATCH_SIZE``, preserving order."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        vectors.extend(await embedder.embed(batch))
    return vectors
