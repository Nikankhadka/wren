"""T-008: pending document -> processing -> chunks (embedded) -> ready.

Triggered synchronously from the upload endpoint (T-007) and from a
reprocess endpoint (retry button); idempotent - old chunks for a document are
always replaced, never appended to, so re-running never doubles them up.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import asyncpg

from app.ingestion.chunker import Chunk, chunk_catalog_item, chunk_document
from app.ingestion.embedder import embed_texts
from app.llm.embedder import Embedder
from app.shared.storage import document_key, get_storage

if TYPE_CHECKING:
    from app.shared.db import AppConnection


logger = logging.getLogger("app.ingestion.pipeline")
_SAFE_EMBED_FAILURE_MESSAGE = "We could not make this document searchable. Please retry."


class _NoExtractableContent(ValueError):
    """The chunker produced zero chunks - the file has nothing to search over.
    Deterministic: this fails identically on every retry, so it is the one
    embed-stage failure ``_mark_failed`` must not mark retryable."""


async def _mark_failed(
    conn: AppConnection,
    *,
    tenant_id: UUID,
    document_id: UUID,
    retryable: bool = True,
) -> None:
    """Record a chunk+embed failure - W-11's 'embed' stage - the same failure
    metadata a draft's own structuring/extraction failure gets. ``retryable``
    is False only for a failure that will recur identically on every retry (a
    file with no extractable content); every other embed/chunk failure (a
    transient provider error, say) keeps the default of True."""
    await conn.execute(
        "update documents set status = 'failed', error = $2, failure_stage = 'embed', "
        "failure_retryable = $4, failed_at = now() where id = $1 and tenant_id = $3",
        document_id,
        _SAFE_EMBED_FAILURE_MESSAGE,
        tenant_id,
        retryable,
    )


async def _replace_chunks(
    conn: AppConnection,
    *,
    document_id: UUID,
    tenant_id: UUID,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> None:
    """Delete and reinsert one document's chunks - DB writes only. Callers embed
    first (a network call) and pass the resulting ``vectors`` in, so this can
    run entirely inside a DB transaction without holding it open across that
    network round-trip."""
    await conn.execute(
        "delete from knowledge_chunks where document_id = $1 and tenant_id = $2",
        document_id,
        tenant_id,
    )
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
    conn: AppConnection,
    *,
    tenant_id: UUID,
    document_id: UUID,
    embedder: Embedder,
    extension: str | None = None,
    source: str | None = None,
) -> None:
    """Chunk + embed one document's file, replacing any existing chunks.

    Marks the document ``failed`` (with a readable error) on any exception
    rather than letting it propagate, so a bad upload never crashes the
    caller - the admin sees the failure in the documents table.

    ``extension``/``source`` default to values derived from the documents row's
    ``filename``; URL ingestion (T-056) overrides both because its stored
    filename is a URL, not a disk path, and its disk file is always ``.txt``.
    """
    row = await conn.fetchrow(
        "select filename from documents where id = $1 and tenant_id = $2", document_id, tenant_id
    )
    if row is None:
        raise ValueError(f"document {document_id} not found for tenant {tenant_id}")

    await conn.execute(
        "update documents set status = 'processing' where id = $1 and tenant_id = $2",
        document_id,
        tenant_id,
    )

    try:
        ext = extension if extension is not None else Path(row["filename"]).suffix.lower()
        body = await get_storage().get(document_key(tenant_id, document_id, ext))
        if body is None:
            raise FileNotFoundError(f"no stored file for document {document_id}")  # noqa: TRY301
        chunks = chunk_document(body, ext, source=source or row["filename"])
        if not chunks:
            raise _NoExtractableContent("no extractable content in this file")  # noqa: TRY301

        # Embedding is a network call to the provider; it runs before the DB
        # transaction opens so a slow or failing embed call never holds a
        # transaction open (W-11a review fix 9).
        vectors = await embed_texts(embedder, [chunk.content for chunk in chunks])
        async with conn.transaction():
            await _replace_chunks(
                conn, document_id=document_id, tenant_id=tenant_id, chunks=chunks, vectors=vectors
            )
            await conn.execute(
                "update documents set status = 'ready', error = null, failure_stage = null, "
                "failure_retryable = null, failed_at = null where id = $1 and tenant_id = $2",
                document_id,
                tenant_id,
            )
    except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError):
        raise
    except _NoExtractableContent:
        logger.exception(
            "knowledge document processing failed tenant_id=%s document_id=%s stage=embed",
            tenant_id,
            document_id,
        )
        await _mark_failed(conn, tenant_id=tenant_id, document_id=document_id, retryable=False)
    except Exception:  # noqa: BLE001 - always recorded on the document, never re-raised
        logger.exception(
            "knowledge document processing failed tenant_id=%s document_id=%s stage=embed",
            tenant_id,
            document_id,
        )
        await _mark_failed(conn, tenant_id=tenant_id, document_id=document_id)


async def ingest_offerings(conn: AppConnection, *, tenant_id: UUID, embedder: Embedder) -> None:
    """Re-derive the tenant's synthetic 'catalog' document from offerings.

    Called from onboarding's confirm step (T-006) and safe to call again any
    time the catalog changes - it always replaces the existing catalog
    document's chunks rather than appending. A no-op if the tenant has no
    active offerings.
    """
    items = await conn.fetch(
        "select id, name, description, price_cents from offerings where tenant_id = $1 and active",
        tenant_id,
    )
    document_id = await conn.fetchval(
        "select id from documents where tenant_id = $1 and doc_type = 'catalog' "
        "order by uploaded_at desc limit 1",
        tenant_id,
    )
    if not items:
        if document_id is not None:
            await conn.execute(
                "delete from documents where id = $1 and tenant_id = $2", document_id, tenant_id
            )
        return

    if document_id is None:
        document_id = uuid4()
        await conn.execute(
            "insert into documents (id, tenant_id, filename, doc_type, status) "
            "values ($1, $2, 'catalog', 'catalog', 'processing')",
            document_id,
            tenant_id,
        )
    else:
        await conn.execute(
            "update documents set status = 'processing' where id = $1 and tenant_id = $2",
            document_id,
            tenant_id,
        )

    try:
        chunks = [
            chunk_catalog_item(
                str(item["id"]), item["name"], item["description"], item["price_cents"]
            )
            for item in items
        ]
        # See process_document: embed before opening the transaction so it is
        # never held across the embedding provider's network call.
        vectors = await embed_texts(embedder, [chunk.content for chunk in chunks])
        async with conn.transaction():
            await _replace_chunks(
                conn, document_id=document_id, tenant_id=tenant_id, chunks=chunks, vectors=vectors
            )
            await conn.execute(
                "update documents set status = 'ready', error = null, failure_stage = null, "
                "failure_retryable = null, failed_at = null where id = $1 and tenant_id = $2",
                document_id,
                tenant_id,
            )
    except (asyncpg.PostgresConnectionError, asyncpg.InterfaceError):
        raise
    except Exception:  # noqa: BLE001 - always recorded on the document, never re-raised
        logger.exception(
            "knowledge document processing failed tenant_id=%s document_id=%s stage=embed",
            tenant_id,
            document_id,
        )
        await _mark_failed(conn, tenant_id=tenant_id, document_id=document_id)
