"""Knowledge persistence: document-row queries + the upload pipeline.

Moved from api/knowledge.py. Raw files land on local disk under
``{uploads_dir}/{tenant_id}/`` (path from settings); only the ``documents`` row
is queried by the rest of the app. Stored filenames are always
``{document_id}{ext}`` - the admin's original filename is kept only as a column
value, never used to build a filesystem path, so a crafted filename
(``../../etc/passwd``) can't escape the tenant's upload directory. Chunking and
embedding run through app.ingestion.pipeline.process_document, which needs an
open ``tenant_context`` connection - it is called inside the context here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from app.features.business.offering_candidates import normalize_name
from app.features.business.service import create_offerings_batch
from app.features.knowledge.models import normalize_sections
from app.features.knowledge.offering_extraction import extract_offerings
from app.features.knowledge.structuring import render_sections, structure_document
from app.ingestion.chunker import extract_text
from app.ingestion.pipeline import ingest_offerings, process_document
from app.ingestion.url import AllowedTarget, extract_main_text, extract_title, fetch_page
from app.llm.embedder import Embedder
from app.llm.provider import LLMProvider
from app.onboarding.flow import normalize_pending_offerings
from app.shared import db
from app.shared.config import get_settings
from app.shared.storage import document_key, get_storage

_SELECT_COLUMNS = "id, filename, doc_type, status, error"
_RECORD_COLUMNS = f"{_SELECT_COLUMNS}, structured, offerings"


class OfferingPriceConflict(ValueError):
    """A reviewed source proposes changing an existing owner's price."""

    def __init__(self, changes: list[dict[str, Any]]) -> None:
        self.changes = changes
        details = ", ".join(
            f"{change['name']}: {change['current_price_cents']} -> "
            f"{change['proposed_price_cents']} cents"
            for change in changes
        )
        super().__init__(f"Offering price changes need confirmation: {details}")


async def list_documents(*, tenant_id: UUID) -> list[dict[str, Any]]:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            f"select {_SELECT_COLUMNS} from documents "
            "where tenant_id = $1 order by uploaded_at desc",
            tenant_id,
        )
    return [dict(row) for row in rows]


async def upload_document(
    *,
    tenant_id: UUID,
    document_id: UUID,
    filename: str,
    doc_type: str,
    body: bytes,
    embedder: Embedder,
    extension: str,
) -> dict[str, Any] | None:
    """Write the upload to disk (never trusting the client filename for the
    path - the disk name is always ``{document_id}{extension}``), insert the
    pending documents row keeping the admin's original filename as the display
    column, then run the ingestion pipeline to completion. Returns the
    resulting row."""
    await get_storage().put(document_key(tenant_id, document_id, extension), body)
    await _save_original_text(
        tenant_id=tenant_id,
        document_id=document_id,
        text=await run_in_threadpool(extract_text, body, extension),
    )

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await conn.execute(
            "insert into documents (id, tenant_id, filename, doc_type, status) "
            "values ($1, $2, $3, $4, 'pending')",
            document_id,
            tenant_id,
            filename,
            doc_type,
        )
        await process_document(
            conn, tenant_id=tenant_id, document_id=document_id, embedder=embedder
        )
        row = await conn.fetchrow(
            f"select {_SELECT_COLUMNS} from documents where id = $1", document_id
        )
    return dict(row) if row is not None else None


async def scrape_url(*, url: str) -> tuple[str, str]:
    """Fetch a page and return its (main_text, title). Raises ``ValueError``
    when the page has no extractable text (or on a bad scheme/oversize body,
    which ``fetch_page`` surfaces as ``ValueError``)."""
    allowed_targets = _url_fetch_allowlist()
    if allowed_targets:
        html = await fetch_page(url, allowed_targets=allowed_targets)
    else:
        html = await fetch_page(url)
    text = extract_main_text(html)
    if not text:
        raise ValueError("no extractable content at this URL")
    title = extract_title(html) or url
    return text, title


def _url_fetch_allowlist() -> set[AllowedTarget]:
    configured = get_settings().url_fetch_allowlist
    targets: set[AllowedTarget] = set()
    for value in configured.split(","):
        host, separator, port_text = value.strip().rpartition(":")
        if not separator or not host or not port_text.isdigit():
            continue
        targets.add((host.casefold(), int(port_text)))
    return targets


async def ingest_website(
    *,
    tenant_id: UUID,
    document_id: UUID,
    url: str,
    text: str,
    title: str,
    embedder: Embedder,
) -> dict[str, Any] | None:
    """Ingest already-scraped page text as a 'website' document.

    The text is written to disk as ``{document_id}.txt`` (never a
    client-controlled path - same posture as ``upload_document``); the documents
    row stores the URL as its display filename only. Idempotent: re-pasting a
    URL this tenant already ingested returns the existing row untouched.
    """
    await get_storage().put(document_key(tenant_id, document_id, ".txt"), text.encode("utf-8"))
    await _save_original_text(tenant_id=tenant_id, document_id=document_id, text=text)

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        existing = await conn.fetchrow(
            f"select {_SELECT_COLUMNS} from documents "
            "where tenant_id = $1 and doc_type = 'website' and filename = $2",
            tenant_id,
            url,
        )
        if existing is not None:
            return dict(existing)
        await conn.execute(
            "insert into documents (id, tenant_id, filename, doc_type, status) "
            "values ($1, $2, $3, 'website', 'pending')",
            document_id,
            tenant_id,
            url,
        )
        await process_document(
            conn,
            tenant_id=tenant_id,
            document_id=document_id,
            embedder=embedder,
            extension=".txt",
            source=title,
        )
        row = await conn.fetchrow(
            f"select {_SELECT_COLUMNS} from documents where id = $1", document_id
        )
    return dict(row) if row is not None else None


async def upload_url(
    *,
    tenant_id: UUID,
    document_id: UUID,
    url: str,
    embedder: Embedder,
) -> dict[str, Any] | None:
    """Fetch a URL, extract its main text, and ingest it as a 'website' document.

    Raises ``ValueError`` when the page has no extractable text.
    """
    text, title = await scrape_url(url=url)
    return await ingest_website(
        tenant_id=tenant_id,
        document_id=document_id,
        url=url,
        text=text,
        title=title,
        embedder=embedder,
    )


async def reprocess_document(
    *, tenant_id: UUID, document_id: UUID, embedder: Embedder
) -> dict[str, Any] | None:
    """Re-run the ingest pipeline for one document; None when the document is
    not this tenant's."""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        exists = await conn.fetchval(
            "select 1 from documents where id = $1 and tenant_id = $2",
            document_id,
            tenant_id,
        )
        if not exists:
            return None
        await process_document(
            conn, tenant_id=tenant_id, document_id=document_id, embedder=embedder
        )
        row = await conn.fetchrow(
            f"select {_SELECT_COLUMNS} from documents where id = $1", document_id
        )
    return dict(row) if row is not None else None


def _record(row: Any) -> dict[str, Any]:
    """One document as the knowledge screen reads it: the row plus its readable
    sections and its offering candidates (both jsonb, so they arrive as strings
    from asyncpg).

    W-6: candidates are read back, not recomputed. They used to be re-derived on
    every call by splitting section lines at their first monetary figure, which
    made every list request redo the parse and produced sentence fragments from
    prose. Extraction now needs a model call, so it belongs to ingest; this
    function only reads what ingest stored.
    """
    record = dict(row)
    raw = record.pop("structured", None)
    sections = json.loads(raw) if isinstance(raw, str) else (raw or [])
    record["sections"] = normalize_sections(sections)
    stored = record.pop("offerings", None)
    extraction = json.loads(stored) if isinstance(stored, str) else stored
    record["offering_candidates"] = [
        item.model_dump()
        for item in normalize_pending_offerings((extraction or {}).get("candidates", []))
    ]
    # Null on a row ingested before this column existed; get_record extracts it
    # on first view, the same way it backfills `sections`.
    record["extraction_status"] = (extraction or {}).get("status", "pending")
    return record


async def list_records(*, tenant_id: UUID) -> list[dict[str, Any]]:
    """Every document with its sections - what the assistant knows, in reading
    order (newest first, matching the upload order the owner remembers)."""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            f"select {_RECORD_COLUMNS} from documents "
            "where tenant_id = $1 order by uploaded_at desc",
            tenant_id,
        )
    return [_record(row) for row in rows]


async def _extraction(text: str, *, provider: LLMProvider, document_id: UUID) -> dict[str, Any]:
    """Run W-6's offering extraction and shape it for the ``offerings`` column."""
    candidates, status = await extract_offerings(text, provider=provider, document_id=document_id)
    return {"status": status, "candidates": [item.model_dump() for item in candidates]}


async def _insert_draft(
    *,
    tenant_id: UUID,
    document_id: UUID,
    filename: str,
    doc_type: str,
    sections: list[dict[str, str]],
    extraction: dict[str, Any],
) -> dict[str, Any] | None:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await conn.execute(
            "insert into documents "
            "(id, tenant_id, filename, doc_type, status, structured, offerings) "
            "values ($1, $2, $3, $4, 'draft', $5, $6)",
            document_id,
            tenant_id,
            filename,
            doc_type,
            json.dumps(sections),
            json.dumps(extraction),
        )
        row = await conn.fetchrow(
            f"select {_RECORD_COLUMNS} from documents where id = $1", document_id
        )
    return _record(row) if row is not None else None


async def draft_from_upload(
    *,
    tenant_id: UUID,
    document_id: UUID,
    filename: str,
    body: bytes,
    extension: str,
    provider: LLMProvider,
) -> dict[str, Any] | None:
    """Extract, structure, and park an uploaded file as a draft.

    Nothing is chunked here, so the document answers nothing until the owner
    reads it back and saves it. The raw file is kept on disk under the same
    ``{document_id}{ext}`` rule as every other upload, so a re-structure never
    needs the browser to send it again.
    """
    await get_storage().put(document_key(tenant_id, document_id, extension), body)
    raw_text = await run_in_threadpool(extract_text, body, extension)
    await _save_original_text(tenant_id=tenant_id, document_id=document_id, text=raw_text)
    sections = await structure_document(raw_text, provider=provider)
    return await _insert_draft(
        tenant_id=tenant_id,
        document_id=document_id,
        filename=filename,
        doc_type="other",
        sections=sections,
        extraction=await _extraction(raw_text, provider=provider, document_id=document_id),
    )


async def draft_from_url(
    *, tenant_id: UUID, document_id: UUID, url: str, provider: LLMProvider
) -> dict[str, Any] | None:
    """Scrape, structure, and park a page as a draft. ``ValueError`` on any
    fetch or extraction failure, exactly as ``upload_url`` raises it.

    A URL already added is re-read in place rather than added twice: the same
    address is the same source, and pasting it again means the site changed.
    The previous text keeps answering until the owner saves the new one.
    (Uploads are not deduplicated this way - two files can share a name and be
    different documents, while a URL cannot.)
    """
    text, title = await scrape_url(url=url)
    return await draft_from_url_text(
        tenant_id=tenant_id,
        document_id=document_id,
        url=url,
        text=text,
        title=title,
        provider=provider,
    )


async def draft_from_url_text(
    *,
    tenant_id: UUID,
    document_id: UUID,
    url: str,
    text: str,
    title: str,
    provider: LLMProvider,
) -> dict[str, Any] | None:
    """Store one already-fetched page as a draft."""
    sections = await structure_document(text, provider=provider)

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        existing = await conn.fetchval(
            "select id from documents where tenant_id = $1 and filename = $2",
            tenant_id,
            url,
        )
    target = existing or document_id
    await get_storage().put(document_key(tenant_id, target, ".txt"), text.encode("utf-8"))
    await _save_original_text(tenant_id=tenant_id, document_id=target, text=text)

    extraction = await _extraction(text, provider=provider, document_id=target)
    if existing is None:
        return await _insert_draft(
            tenant_id=tenant_id,
            document_id=document_id,
            filename=url,
            doc_type="website",
            sections=sections,
            extraction=extraction,
        )

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await conn.execute(
            "update documents set structured = $2, offerings = $3, "
            "status = 'draft', error = null where id = $1",
            existing,
            json.dumps(sections),
            json.dumps(extraction),
        )
        row = await conn.fetchrow(
            f"select {_RECORD_COLUMNS} from documents where id = $1", existing
        )
    return _record(row) if row is not None else None


async def save_record(
    *,
    tenant_id: UUID,
    document_id: UUID,
    sections: list[dict[str, str]],
    offerings: list[dict[str, Any]],
    accept_price_changes: bool = False,
    embedder: Embedder,
) -> dict[str, Any] | None:
    """Make the owner's reviewed text the knowledge: store the sections, write
    them to disk, and run the ingest pipeline over them.

    The assistant answers from what the owner saved, not from the original
    scrape - an edit here is the correction, not a note beside it.
    """
    sections = normalize_sections(sections)
    keys: set[str] = set()
    for offering in offerings:
        key = normalize_name(str(offering.get("name", "")))
        if not key or key in keys:
            raise ValueError("offering names must be unique")
        keys.add(key)

    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        source = await conn.fetchval(
            "select filename from documents where id = $1 and tenant_id = $2",
            document_id,
            tenant_id,
        )
        if source is None:
            return None
        existing_rows = await conn.fetch(
            "select id, name, price_cents from offerings where tenant_id = $1 and active",
            tenant_id,
        )
        existing = {normalize_name(str(row["name"])): row for row in existing_rows}
        changes = []
        for offering in offerings:
            name = str(offering.get("name", "")).strip()
            row = existing.get(normalize_name(name))
            proposed = offering.get("price_cents")
            if row is not None and proposed is not None and proposed != row["price_cents"]:
                changes.append(
                    {
                        "name": name,
                        "current_price_cents": row["price_cents"],
                        "proposed_price_cents": proposed,
                    }
                )
        if changes and not accept_price_changes:
            raise OfferingPriceConflict(changes)
        await _publish_record(
            conn,
            document_id=document_id,
            tenant_id=tenant_id,
            sections=sections,
            embedder=embedder,
            source=source,
        )
        updated_existing = False
        for change in changes:
            await conn.execute(
                "update offerings set description = $3, price_cents = $4 "
                "where tenant_id = $1 and id = $2",
                tenant_id,
                existing[normalize_name(change["name"])]["id"],
                str(
                    next(item for item in offerings if item.get("name") == change["name"]).get(
                        "description", ""
                    )
                ),
                change["proposed_price_cents"],
            )
            updated_existing = True
        for offering in offerings:
            row = existing.get(normalize_name(str(offering.get("name", ""))))
            if row is not None and not any(
                change["name"] == offering["name"] for change in changes
            ):
                await conn.execute(
                    "update offerings set description = $3 where tenant_id = $1 and id = $2",
                    tenant_id,
                    row["id"],
                    str(offering.get("description", "")),
                )
                updated_existing = True
        created = (
            await create_offerings_batch(
                conn=conn, tenant_id=tenant_id, offerings=offerings, embedder=embedder
            )
            if offerings
            else []
        )
        if updated_existing and not created:
            await ingest_offerings(conn, tenant_id=tenant_id, embedder=embedder)
        await conn.execute(
            "update documents set offerings = $2 where id = $1",
            document_id,
            json.dumps({"status": "full", "candidates": offerings}),
        )
        row = await conn.fetchrow(
            f"select {_RECORD_COLUMNS} from documents where id = $1", document_id
        )
    return _record(row) if row is not None else None


async def _publish_record(
    conn: Any,
    *,
    tenant_id: UUID,
    document_id: UUID,
    sections: list[dict[str, str]],
    embedder: Embedder,
    source: str,
) -> None:
    """Publish reviewed sections and rebuild only this document's chunks."""
    sections = normalize_sections(sections)
    text = render_sections(sections)
    await get_storage().put(document_key(tenant_id, document_id, ".txt"), text.encode("utf-8"))
    await conn.execute(
        "update documents set structured = $2 where id = $1",
        document_id,
        json.dumps([dict(section) for section in sections]),
    )
    await process_document(
        conn,
        tenant_id=tenant_id,
        document_id=document_id,
        embedder=embedder,
        extension=".txt",
        source=source,
    )
    failure = await conn.fetchval(
        "select error from documents where id = $1 and status = 'failed'", document_id
    )
    if failure:
        raise ValueError(str(failure))


async def publish_record(
    *,
    tenant_id: UUID,
    document_id: UUID,
    sections: list[dict[str, str]],
    offerings: list[dict[str, Any]] | None = None,
    embedder: Embedder,
) -> dict[str, Any] | None:
    """Publish reviewed knowledge without touching the offerings table."""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        source = await conn.fetchval(
            "select filename from documents where id = $1 and tenant_id = $2",
            document_id,
            tenant_id,
        )
        if source is None:
            return None
        await _publish_record(
            conn,
            tenant_id=tenant_id,
            document_id=document_id,
            sections=sections,
            embedder=embedder,
            source=source,
        )
        if offerings is not None:
            await conn.execute(
                "update documents set offerings = $2 where id = $1",
                document_id,
                json.dumps({"status": "full", "candidates": offerings}),
            )
        row = await conn.fetchrow(
            f"select {_RECORD_COLUMNS} from documents where id = $1", document_id
        )
    return _record(row) if row is not None else None


async def get_record(
    *, tenant_id: UUID, document_id: UUID, provider: LLMProvider
) -> dict[str, Any] | None:
    """One document with its sections, structuring it on first view.

    Documents ingested before this screen existed (the onboarding URL turn, the
    old console upload) have no sections yet. They are structured on demand and
    the result stored, so the work happens once, when someone actually looks.
    """
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        row = await conn.fetchrow(
            f"select {_RECORD_COLUMNS}, uploaded_at from documents "
            "where id = $1 and tenant_id = $2",
            document_id,
            tenant_id,
        )
        if row is None:
            return None
        record = _record(row)
        record.pop("uploaded_at", None)
        if record["sections"] and record["extraction_status"] != "pending":
            return record
        text = await _source_text_for_processing(
            tenant_id=tenant_id, filename=row["filename"], document_id=document_id
        )
        if not text:
            return record
        # A row from before either column existed: structure it and extract its
        # offerings once, when someone actually looks, rather than backfilling
        # every historical document with a pair of model calls.
        sections = record["sections"] or await structure_document(text, provider=provider)
        extraction = await _extraction(text, provider=provider, document_id=document_id)
        await conn.execute(
            "update documents set structured = $2, offerings = $3 where id = $1",
            document_id,
            json.dumps(sections),
            json.dumps(extraction),
        )
        record["sections"] = sections
        record["offering_candidates"] = extraction["candidates"]
        record["extraction_status"] = extraction["status"]
    return record


async def _stored_text(*, tenant_id: UUID, filename: str, document_id: UUID) -> str:
    """The document's text as last ingested, read back off disk. Empty when the
    file is gone (a catalog document has no file at all)."""
    extension = ".txt" if filename.startswith("http") else Path(filename).suffix.lower()
    storage = get_storage()
    for ext in (extension, ".txt"):
        body = await storage.get(document_key(tenant_id, document_id, ext))
        if body is not None:
            return extract_text(body, ext)
    return ""


async def _save_original_text(*, tenant_id: UUID, document_id: UUID, text: str) -> None:
    """Store extracted source independently of the reviewed retrieval text."""
    await get_storage().put(
        document_key(tenant_id, document_id, ".source.txt"), text.encode("utf-8")
    )


async def _source_text_for_processing(*, tenant_id: UUID, filename: str, document_id: UUID) -> str:
    original = await get_storage().get(document_key(tenant_id, document_id, ".source.txt"))
    if original is not None:
        return original.decode("utf-8", errors="replace")
    return await _stored_text(tenant_id=tenant_id, filename=filename, document_id=document_id)


async def source_text(*, tenant_id: UUID, filename: str, document_id: UUID) -> tuple[str, bool]:
    """Return original extracted text, or a clearly marked legacy fallback."""
    original = await get_storage().get(document_key(tenant_id, document_id, ".source.txt"))
    if original is not None:
        return original.decode("utf-8", errors="replace"), False
    # Pre-W-8 rows did not retain source text separately. Their saved owner
    # review is the only honest fallback, rather than implying it is original.
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        structured = await conn.fetchval(
            "select structured from documents where id = $1 and tenant_id = $2",
            document_id,
            tenant_id,
        )
    sections = json.loads(structured) if isinstance(structured, str) else (structured or [])
    return render_sections(normalize_sections(sections)), True


async def delete_record(*, tenant_id: UUID, document_id: UUID) -> bool:
    """Forget a source: the row (chunks cascade) and its files on disk."""
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        deleted = await conn.fetchval(
            "delete from documents where id = $1 and tenant_id = $2 returning id",
            document_id,
            tenant_id,
        )
    if deleted is None:
        return False
    await get_storage().delete_prefix(document_key(tenant_id, document_id))
    return True
