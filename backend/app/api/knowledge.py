"""T-007: knowledge document upload and listing.

Raw files land on local disk under ``{uploads_dir}/{tenant_id}/`` at core
scope (path from settings); only the ``documents`` row (filename, doc_type,
status) is queried by the rest of the app. Stored filenames are always
``{document_id}{ext}`` - the admin's original filename is kept only as a
column value, never used to build a filesystem path, so a crafted filename
(``../../etc/passwd``) can't escape the tenant's upload directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core import auth, db
from app.core.config import get_settings

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_EXTENSIONS = frozenset({".md", ".txt", ".pdf", ".csv", ".json"})
ALLOWED_DOC_TYPES = frozenset({"policy", "faq", "catalog", "price_list", "other"})
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    doc_type: str
    status: str
    error: str | None


def _write_upload(path: Path, body: bytes) -> None:
    """Blocking filesystem write - always run via ``run_in_threadpool``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _row_to_response(row: asyncpg.Record) -> DocumentResponse:
    return DocumentResponse(
        id=row["id"],
        filename=row["filename"],
        doc_type=row["doc_type"],
        status=row["status"],
        error=row["error"],
    )


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> list[DocumentResponse]:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select id, filename, doc_type, status, error from documents "
            "where tenant_id = $1 order by uploaded_at desc",
            admin.tenant_id,
        )
    return [_row_to_response(row) for row in rows]


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
    file: Annotated[UploadFile, File()],
    doc_type: Annotated[str, Form()],
) -> DocumentResponse:
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"doc_type must be one of {sorted(ALLOWED_DOC_TYPES)}",
        )

    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unsupported file type {ext!r} - allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    body = await file.read()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB upload limit",
        )
    if not body:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="empty file")

    document_id = uuid4()
    document_path = Path(get_settings().uploads_dir) / str(admin.tenant_id) / f"{document_id}{ext}"
    await run_in_threadpool(_write_upload, document_path, body)

    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        row = await conn.fetchrow(
            "insert into documents (id, tenant_id, filename, doc_type, status) "
            "values ($1, $2, $3, $4, 'pending') "
            "returning id, filename, doc_type, status, error",
            document_id,
            admin.tenant_id,
            filename,
            doc_type,
        )
    if row is None:
        # Cannot happen: the insert above either succeeds (and RETURNING sees
        # the same tenant-scoped row under Shape A's select policy) or raises.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="document not created"
        )
    return _row_to_response(row)
