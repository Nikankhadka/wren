"""T-009: dense (embedding-similarity) retrieval.

``where tenant_id = $1`` is explicit here even though RLS also enforces it
(database.md section 4: "RLS is the net, not the filter" - the explicit
predicate is what lets the planner combine the HNSW index with tenant
scoping efficiently, and belt-and-braces is the point).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import UUID

from app.retrieval.types import RetrievedChunk

if TYPE_CHECKING:
    from app.core.db import AppConnection

DEFAULT_LIMIT = 20


async def dense_search(
    conn: AppConnection,
    *,
    tenant_id: UUID,
    query_embedding: list[float],
    limit: int = DEFAULT_LIMIT,
    metadata_kind: str | None = None,
) -> list[RetrievedChunk]:
    """``metadata_kind`` scopes results to chunks whose ``metadata.kind``
    matches exactly (T-015: the Recommendation Agent searches only
    ``catalog_item`` chunks, never prose)."""
    if metadata_kind is None:
        rows = await conn.fetch(
            "select id, content, metadata, 1 - (embedding <=> $2) as score "
            "from knowledge_chunks where tenant_id = $1 "
            "order by embedding <=> $2 limit $3",
            tenant_id,
            query_embedding,
            limit,
        )
    else:
        rows = await conn.fetch(
            "select id, content, metadata, 1 - (embedding <=> $2) as score "
            "from knowledge_chunks where tenant_id = $1 and metadata->>'kind' = $4 "
            "order by embedding <=> $2 limit $3",
            tenant_id,
            query_embedding,
            limit,
            metadata_kind,
        )
    return [
        RetrievedChunk(
            id=row["id"],
            content=row["content"],
            metadata=json.loads(row["metadata"]),
            score=row["score"],
        )
        for row in rows
    ]
