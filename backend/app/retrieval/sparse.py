"""T-009: sparse (full-text search) retrieval.

Same explicit ``tenant_id`` predicate as dense.py, for the same reason.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import UUID

from app.retrieval.types import RetrievedChunk

if TYPE_CHECKING:
    from app.core.db import AppConnection

DEFAULT_LIMIT = 20


async def sparse_search(
    conn: AppConnection,
    *,
    tenant_id: UUID,
    query: str,
    limit: int = DEFAULT_LIMIT,
    metadata_kind: str | None = None,
) -> list[RetrievedChunk]:
    if metadata_kind is None:
        rows = await conn.fetch(
            "select id, content, metadata, "
            "ts_rank(tsv, websearch_to_tsquery('english', $2)) as score "
            "from knowledge_chunks where tenant_id = $1 "
            "and tsv @@ websearch_to_tsquery('english', $2) "
            "order by score desc limit $3",
            tenant_id,
            query,
            limit,
        )
    else:
        rows = await conn.fetch(
            "select id, content, metadata, "
            "ts_rank(tsv, websearch_to_tsquery('english', $2)) as score "
            "from knowledge_chunks where tenant_id = $1 and metadata->>'kind' = $4 "
            "and tsv @@ websearch_to_tsquery('english', $2) "
            "order by score desc limit $3",
            tenant_id,
            query,
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
