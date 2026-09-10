"""T-007: knowledge document upload and listing.

Handlers only: request parsing and validation (doc_type whitelist, file
extension and size) plus response shaping. The upload pipeline lives in
controller.py / service.py. Stored filenames are always ``{document_id}{ext}``
so a crafted filename can never escape the tenant's upload directory.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.features.knowledge import controller
from app.features.knowledge.models import KnowledgeSection
from app.llm.dependency import get_embedder_dependency, get_llm_provider
from app.llm.embedder import Embedder
from app.llm.provider import LLMProvider
from app.onboarding.flow import PendingOffering
from app.shared import auth

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_EXTENSIONS = frozenset({".md", ".txt", ".pdf", ".csv", ".json", ".docx"})
ALLOWED_DOC_TYPES = frozenset({"policy", "faq", "catalog", "price_list", "other", "website"})
# B-4: bounded by the deploy target, not by ingestion. Vercel Functions reject
# request bodies over 4.5MB at the edge, so a limit above that would trade this
# endpoint's clear 422 for an opaque platform 413 the user cannot act on.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    doc_type: str
    status: str
    error: str | None


class UrlIngestRequest(BaseModel):
    url: str


class KnowledgeRecord(DocumentResponse):
    """A document as the knowledge screen reads it - the row plus its sections."""

    sections: list[KnowledgeSection]
    offering_candidates: list[PendingOffering] = []
    # W-6: how completely the document could be read. "partial" and "failed" mean
    # the candidate list is not the whole document, and the review sheet says so
    # rather than presenting a truncated list as if it were complete. "pending"
    # is a row ingested before extraction existed, filled in on first view.
    extraction_status: Literal["full", "partial", "failed", "pending"] = "pending"
    # W-11: which processing step failed, and whether it can be retried through
    # retry-draft. Both null except on a 'failed' row.
    failure_stage: Literal["structure", "extract", "embed"] | None = None
    failure_retryable: bool | None = None
    failed_at: datetime | None = None


class SourceDetail(BaseModel):
    text: str
    is_fallback: bool


class SaveRecordRequest(BaseModel):
    sections: list[KnowledgeSection] = []
    offerings: list[PendingOffering] = []
    accept_price_changes: bool = False


def _absolute_url(url: str) -> str:
    if urlparse(url).scheme.lower() not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="url must be an absolute http:// or https:// URL",
        )
    return url


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> list[DocumentResponse]:
    rows = await controller.list_documents(tenant_id=admin.tenant_id)
    return [DocumentResponse(**row) for row in rows]


def _reject_upload(file: UploadFile, body: bytes, doc_type: str) -> str:
    """Validate the upload; returns the lowercased file extension. Raises
    422s for every rejection path so the admin surface shows the exact reason
    without touching the database."""
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"doc_type must be one of {sorted(ALLOWED_DOC_TYPES)}",
        )
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unsupported file type {ext!r} - allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB upload limit",
        )
    if not body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="empty file")
    return ext


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[str, Form()],
) -> DocumentResponse:
    body = await file.read()
    ext = _reject_upload(file, body, doc_type)
    document_id = uuid4()
    row = await controller.upload_document(
        tenant_id=admin.tenant_id,
        document_id=document_id,
        # Display name: the admin's original filename, kept only as a column
        # value. service.py derives the disk path from {document_id}{ext}, so
        # the original filename is never used to build a filesystem path.
        filename=file.filename or "",
        doc_type=doc_type,
        body=body,
        embedder=embedder,
        extension=ext,
    )
    return DocumentResponse(**row)


@router.post("/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    document_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
) -> DocumentResponse:
    row = await controller.reprocess_document(
        tenant_id=admin.tenant_id, document_id=document_id, embedder=embedder
    )
    return DocumentResponse(**row)


@router.post("/{document_id}/retry-draft", response_model=KnowledgeRecord)
async def retry_draft(
    document_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> KnowledgeRecord:
    """Retry a failed draft, including embed failures, and return it to review.
    Re-reads stored source data when needed and never publishes anything -
    saving is still a separate owner action."""
    row = await controller.retry_draft(
        tenant_id=admin.tenant_id, document_id=document_id, provider=provider
    )
    return KnowledgeRecord(**row)


@router.post("/urls", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def ingest_url(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
    payload: UrlIngestRequest,
) -> DocumentResponse:
    url = _absolute_url(payload.url.strip())
    document_id = uuid4()
    row = await controller.upload_url(
        tenant_id=admin.tenant_id, document_id=document_id, url=url, embedder=embedder
    )
    return DocumentResponse(**row)


@router.get("/records", response_model=list[KnowledgeRecord])
async def list_records(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> list[KnowledgeRecord]:
    """Everything the assistant knows, as readable sections."""
    rows = await controller.list_records(tenant_id=admin.tenant_id)
    return [KnowledgeRecord(**row) for row in rows]


@router.post("/drafts/upload", response_model=KnowledgeRecord, status_code=status.HTTP_201_CREATED)
async def draft_from_upload(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    file: Annotated[UploadFile, File()],
) -> KnowledgeRecord:
    """Read a file and return it as sections to review. Nothing is embedded yet -
    a draft answers no customer question until it is saved."""
    body = await file.read()
    ext = _reject_upload(file, body, "other")
    row = await controller.draft_from_upload(
        tenant_id=admin.tenant_id,
        document_id=uuid4(),
        filename=file.filename or "",
        body=body,
        extension=ext,
        provider=provider,
    )
    return KnowledgeRecord(**row)


@router.post("/drafts/url", response_model=KnowledgeRecord, status_code=status.HTTP_201_CREATED)
async def draft_from_url(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    payload: UrlIngestRequest,
) -> KnowledgeRecord:
    """Read a page and return it as sections to review (see /drafts/upload)."""
    row = await controller.draft_from_url(
        tenant_id=admin.tenant_id,
        document_id=uuid4(),
        url=_absolute_url(payload.url.strip()),
        provider=provider,
    )
    return KnowledgeRecord(**row)


@router.get("/records/{document_id}", response_model=KnowledgeRecord)
async def get_record(
    document_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> KnowledgeRecord:
    row = await controller.get_record(
        tenant_id=admin.tenant_id, document_id=document_id, provider=provider
    )
    return KnowledgeRecord(**row)


@router.get("/records/{document_id}/source", response_model=SourceDetail)
async def get_source_detail(
    document_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> SourceDetail:
    detail = await controller.source_detail(tenant_id=admin.tenant_id, document_id=document_id)
    return SourceDetail(text=str(detail["text"]), is_fallback=bool(detail["is_fallback"]))


@router.put("/records/{document_id}", response_model=KnowledgeRecord)
async def save_record(
    document_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
    embedder: Annotated[Embedder, Depends(get_embedder_dependency)],
    payload: SaveRecordRequest,
) -> KnowledgeRecord:
    """Save the owner's reviewed sections and make them answerable."""
    row = await controller.save_record(
        tenant_id=admin.tenant_id,
        document_id=document_id,
        sections=[section.model_dump() for section in payload.sections],
        offerings=[offering.model_dump() for offering in payload.offerings],
        accept_price_changes=payload.accept_price_changes,
        embedder=embedder,
    )
    return KnowledgeRecord(**row)


@router.delete("/records/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    document_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_owner)],
) -> None:
    await controller.delete_record(tenant_id=admin.tenant_id, document_id=document_id)
