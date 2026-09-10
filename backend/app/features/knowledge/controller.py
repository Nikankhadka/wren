"""Knowledge feature orchestration for the API surface.

Pass-through layer between api.py (HTTP boundary, upload validation) and
service.py (persistence + ingestion pipeline). Keeps the document row
handling in one place so upload and reprocess share the same 404/500 logic.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.features.knowledge import service
from app.llm.embedder import Embedder
from app.llm.provider import LLMProvider
from app.shared import db


async def list_documents(*, tenant_id: UUID) -> list[dict[str, Any]]:
    return await service.list_documents(tenant_id=tenant_id)


async def upload_document(
    *,
    tenant_id: UUID,
    document_id: UUID,
    filename: str,
    doc_type: str,
    body: bytes,
    embedder: Embedder,
    extension: str,
) -> dict[str, Any]:
    row = await service.upload_document(
        tenant_id=tenant_id,
        document_id=document_id,
        filename=filename,
        doc_type=doc_type,
        body=body,
        embedder=embedder,
        extension=extension,
    )
    if row is None:
        # Cannot happen: process_document only updates the row it was given;
        # it never deletes it.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="document not created"
        )
    return row


async def reprocess_document(
    *, tenant_id: UUID, document_id: UUID, embedder: Embedder
) -> dict[str, Any]:
    row = await service.reprocess_document(
        tenant_id=tenant_id, document_id=document_id, embedder=embedder
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    if row.get("status") == "failed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=row.get("error") or "document could not be published",
        )
    return row


async def upload_url(
    *,
    tenant_id: UUID,
    document_id: UUID,
    url: str,
    embedder: Embedder,
) -> dict[str, Any]:
    """URL ingestion pass-through. ValueError (bad scheme, oversize, no content)
    becomes a 422; a missing resulting row a 500."""
    try:
        row = await service.upload_url(
            tenant_id=tenant_id, document_id=document_id, url=url, embedder=embedder
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="document not created"
        )
    return row


async def list_records(*, tenant_id: UUID) -> list[dict[str, Any]]:
    return await service.list_records(tenant_id=tenant_id)


def _created(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        # Cannot happen: the insert and the read-back share one transaction.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="document not created"
        )
    return row


async def draft_from_upload(
    *,
    tenant_id: UUID,
    document_id: UUID,
    filename: str,
    body: bytes,
    extension: str,
    provider: LLMProvider,
) -> dict[str, Any]:
    """A file rejected at validation (api.py's _reject_upload, before storage)
    stays a 422 with nothing stored - that half of the old rule is unchanged.
    A file accepted and then failing during processing (structuring or
    extraction) is now stored as a 'failed' draft instead of raised: the raw
    upload already sits in storage by that point, so the owner can retry it
    through retry-draft rather than lose it. Embed failures are also accepted
    by retry-draft and returned to review without publishing."""
    row = await service.draft_from_upload(
        tenant_id=tenant_id,
        document_id=document_id,
        filename=filename,
        body=body,
        extension=extension,
        provider=provider,
    )
    return _created(row)


async def retry_draft(
    *, tenant_id: UUID, document_id: UUID, provider: LLMProvider
) -> dict[str, Any]:
    row = await service.retry_draft(tenant_id=tenant_id, document_id=document_id, provider=provider)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return row


async def draft_from_url(
    *, tenant_id: UUID, document_id: UUID, url: str, provider: LLMProvider
) -> dict[str, Any]:
    try:
        row = await service.draft_from_url(
            tenant_id=tenant_id, document_id=document_id, url=url, provider=provider
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return _created(row)


async def get_record(
    *, tenant_id: UUID, document_id: UUID, provider: LLMProvider
) -> dict[str, Any]:
    row = await service.get_record(tenant_id=tenant_id, document_id=document_id, provider=provider)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return row


async def source_detail(*, tenant_id: UUID, document_id: UUID) -> dict[str, object]:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        filename = await conn.fetchval(
            "select filename from documents where id = $1 and tenant_id = $2",
            document_id,
            tenant_id,
        )
    if filename is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    text, is_fallback = await service.source_text(
        tenant_id=tenant_id, filename=str(filename), document_id=document_id
    )
    return {"text": text, "is_fallback": is_fallback}


async def save_record(
    *,
    tenant_id: UUID,
    document_id: UUID,
    sections: list[dict[str, Any]],
    offerings: list[dict[str, Any]] | None = None,
    accept_price_changes: bool = False,
    embedder: Embedder,
) -> dict[str, Any]:
    try:
        row = await service.save_record(
            tenant_id=tenant_id,
            document_id=document_id,
            sections=sections,
            offerings=offerings or [],
            accept_price_changes=accept_price_changes,
            embedder=embedder,
        )
    except service.OfferingPriceConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    if row.get("status") == "failed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=row.get("error") or "document could not be published",
        )
    return row


async def delete_record(*, tenant_id: UUID, document_id: UUID) -> None:
    if not await service.delete_record(tenant_id=tenant_id, document_id=document_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
