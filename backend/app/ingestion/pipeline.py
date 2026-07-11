"""T-008: pending document -> processing -> chunks (embedded) -> ready.

Triggered synchronously from the upload endpoint (T-007) and from a
reprocess endpoint (retry button); idempotent - old chunks for a document are
always replaced, never appended to, so re-running never doubles them up.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.ingestion.chunker import Chunk, chunk_catalog_item, chunk_document
from app.ingestion.embedder import embed_texts
from app.llm.embedder import Embedder

if TYPE_CHECKING:
    from app.core.db import AppConnection


def _read_file(path: Path) -> bytes:
    return path.read_bytes()


async def _replace_chunks(
    conn: AppConnection,
    *,
    document_id: UUID,
    tenant_id: UUID,
    chunks: list[Chunk],
    embedder: Embedder,
) -> None:
    vectors = await embed_texts(embedder, [chunk.content for chunk in chunks])
    await conn.execute("delete from knowledge_chunks where document_id = $1", document_id)
    for chunk, vector in zip(chunks, vectors, strict=True):
        await conn.execute(
            "insert into knowledge_chunks (tenant_id, document_id, content, embedding, metadata) "
            "values ($1, $2, $3, $4, $5)",
            tenant_id,
            document_id,
            chunk.content,
            vector,
            json.dumps(chunk.metadata),
        )


async def process_document(
    conn: AppConnection, *, tenant_id: UUID, document_id: UUID, embedder: Embedder
) -> None:
    """Chunk + embed one document's file, replacing any existing chunks.

    Marks the document ``failed`` (with a readable error) on any exception
    rather than letting it propagate, so a bad upload never crashes the
    caller - the admin sees the failure in the documents table.
    """
    row = await conn.fetchrow(
        "select filename from documents where id = $1 and tenant_id = $2", document_id, tenant_id
    )
    if row is None:
        raise ValueError(f"document {document_id} not found for tenant {tenant_id}")

    await conn.execute("update documents set status = 'processing' where id = $1", document_id)

    try:
        ext = Path(row["filename"]).suffix.lower()
        path = Path(get_settings().uploads_dir) / str(tenant_id) / f"{document_id}{ext}"
        body = await run_in_threadpool(_read_file, path)
        chunks = chunk_document(body, ext, source=row["filename"])
        if not chunks:
            raise ValueError("no extractable content in this file")  # noqa: TRY301

        await _replace_chunks(
            conn, document_id=document_id, tenant_id=tenant_id, chunks=chunks, embedder=embedder
        )
        await conn.execute(
            "update documents set status = 'ready', error = null where id = $1", document_id
        )
    except Exception as exc:  # noqa: BLE001 - always recorded on the document, never re-raised
        await conn.execute(
            "update documents set status = 'failed', error = $2 where id = $1",
            document_id,
            str(exc),
        )


async def ingest_catalog_items(conn: AppConnection, *, tenant_id: UUID, embedder: Embedder) -> None:
    """Re-derive the tenant's synthetic 'catalog' document from catalog_items.

    Called from onboarding's confirm step (T-006) and safe to call again any
    time the catalog changes - it always replaces the existing catalog
    document's chunks rather than appending. A no-op if the tenant has no
    active catalog items.
    """
    items = await conn.fetch(
        "select id, name, description, price_cents from catalog_items "
        "where tenant_id = $1 and active",
        tenant_id,
    )
    if not items:
        return

    document_id = await conn.fetchval(
        "select id from documents where tenant_id = $1 and doc_type = 'catalog' "
        "order by uploaded_at desc limit 1",
        tenant_id,
    )
    if document_id is None:
        document_id = uuid4()
        await conn.execute(
            "insert into documents (id, tenant_id, filename, doc_type, status) "
            "values ($1, $2, 'catalog', 'catalog', 'processing')",
            document_id,
            tenant_id,
        )
    else:
        await conn.execute("update documents set status = 'processing' where id = $1", document_id)

    try:
        chunks = [
            chunk_catalog_item(
                str(item["id"]), item["name"], item["description"], item["price_cents"]
            )
            for item in items
        ]
        await _replace_chunks(
            conn, document_id=document_id, tenant_id=tenant_id, chunks=chunks, embedder=embedder
        )
        await conn.execute(
            "update documents set status = 'ready', error = null where id = $1", document_id
        )
    except Exception as exc:  # noqa: BLE001 - always recorded on the document, never re-raised
        await conn.execute(
            "update documents set status = 'failed', error = $2 where id = $1",
            document_id,
            str(exc),
        )
