"""Shared helpers for the direct-DB seeds (F-3 dedup).

Every seed repeats the same skeleton: pool creation/teardown, wipe-by-slug,
the service-context tenants + tenant_config insert, the offerings /
pricing_rules / orders loops, and the storage + ingestion-pipeline knowledge
upload. These helpers keep the seeds to their data and their story; behavior
is byte-identical to what each seed did inline (seed tests pin the counts).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from app.ingestion.pipeline import ingest_offerings, process_document
from app.llm.embedder import Embedder
from app.onboarding.agent import OnboardingRecord
from app.onboarding.flow import ProfileDraft, customer_voice_for, system_prompt_for
from app.shared import db
from app.shared.storage import document_key, get_storage

if TYPE_CHECKING:
    from app.shared.db import AppConnection


@asynccontextmanager
async def seed_pool() -> AsyncIterator[None]:
    """The pool boilerplate every direct-DB seed repeats: create the wren_app
    pool if none exists, close it on exit if this call created it."""
    created_pool = False
    try:
        db.get_pool()
    except RuntimeError:
        await db.create_pool()
        created_pool = True
    try:
        yield
    finally:
        if created_pool:
            await db.close_pool()


async def wipe_tenant(conn: AppConnection, slug: str) -> None:
    """Delete a tenant by slug (cascade wipes its data). A no-op when the
    slug is not present, which is what makes re-seeding idempotent."""
    existing_id = await conn.fetchval("select id from tenants where slug = $1", slug)
    if existing_id is not None:
        await conn.execute("delete from tenants where id = $1", existing_id)


async def insert_tenant_core(
    *,
    tenant_id: UUID,
    slug: str,
    name: str,
    system_prompt: str = "",
    tone: str = "friendly",
    brand: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    enabled_tools: list[str] | None = None,
    business_name: str | None = None,
    profile: dict[str, Any] | None = None,
) -> None:
    """The service-context tenants + tenant_config insert every seed starts with.

    ``enabled_tools`` is only included when given - the column's lean default
    (D-2) is the honest value for a tenant that never opted into the commerce
    tools, and writing it explicitly would blur that signal.

    ``profile`` pre-onboards the tenant: when given, the tenants row gains its
    ``business_name`` and the tenant_config row is written exactly as a real
    onboarding confirm leaves it (system_prompt from the profile, ``profile``,
    ``customer_voice`` and a completed ``onboarding`` record in ``config``), so a
    seeded demo tenant never shows the interview. Built from the same dataclasses
    the confirm path uses - no duplicated shape to drift.
    """
    merged_config = dict(config or {})
    if profile is not None:
        business_name = business_name or profile.get("business_name")
        draft = ProfileDraft(**profile)
        merged_config["profile"] = draft.model_dump()
        merged_config["customer_voice"] = customer_voice_for(draft)
        merged_config["onboarding"] = OnboardingRecord(draft=profile, completed=True).to_jsonb()
        if not system_prompt and profile.get("business_type"):
            system_prompt = system_prompt_for(
                business_name or name, profile.get("business_type", "")
            )

    async with db.tenant_context(None, "service") as conn:
        await conn.execute(
            "insert into tenants (id, slug, name, business_name, status) "
            "values ($1, $2, $3, $4, 'active')",
            tenant_id,
            slug,
            name,
            business_name,
        )
        if enabled_tools is None:
            await conn.execute(
                "insert into tenant_config (tenant_id, system_prompt, tone, brand, config) "
                "values ($1, $2, $3, $4, $5)",
                tenant_id,
                system_prompt,
                tone,
                json.dumps(brand) if brand is not None else "{}",
                json.dumps(merged_config),
            )
        else:
            await conn.execute(
                "insert into tenant_config "
                "(tenant_id, system_prompt, tone, brand, config, enabled_tools) "
                "values ($1, $2, $3, $4, $5, $6)",
                tenant_id,
                system_prompt,
                tone,
                json.dumps(brand) if brand is not None else "{}",
                json.dumps(merged_config),
                json.dumps(enabled_tools),
            )


async def insert_offerings(
    conn: AppConnection,
    tenant_id: UUID,
    catalog: list[tuple[str, str, int | None, str | None]],
) -> None:
    """(name, description, price_cents, category) rows, position = list order."""
    for position, (name, description, price_cents, category) in enumerate(catalog):
        await conn.execute(
            "insert into offerings (tenant_id, name, description, price_cents, position, category) "
            "values ($1, $2, $3, $4, $5, $6)",
            tenant_id,
            name,
            description,
            price_cents,
            position,
            category,
        )


async def insert_pricing_rules(
    conn: AppConnection, tenant_id: UUID, rules: list[tuple[str, str, int, str]]
) -> None:
    """(code, label, unit_amount_cents, unit) rows."""
    for code, label, unit_amount_cents, unit in rules:
        await conn.execute(
            "insert into pricing_rules (tenant_id, code, label, unit_amount_cents, unit) "
            "values ($1, $2, $3, $4, $5)",
            tenant_id,
            code,
            label,
            unit_amount_cents,
            unit,
        )


async def insert_orders(
    conn: AppConnection,
    tenant_id: UUID,
    rows: list[tuple[str, str, str, str, dict[str, Any]]],
) -> None:
    """(ref_code, kind, customer_ref, status, details) rows."""
    for ref_code, kind, customer_ref, status, details in rows:
        await conn.execute(
            "insert into orders (tenant_id, ref_code, kind, customer_ref, status, details) "
            "values ($1, $2, $3, $4, $5, $6)",
            tenant_id,
            ref_code,
            kind,
            customer_ref,
            status,
            json.dumps(details),
        )


async def ingest_documents(
    conn: AppConnection,
    tenant_id: UUID,
    docs: list[tuple[str, str, str]],
    embedder: Embedder,
) -> None:
    """(filename, doc_type, content) rows through the real ingestion pipeline:
    storage.put, a 'pending' documents row, process_document for each, then
    the synthetic catalog document from the tenant's offerings."""
    for filename, doc_type, content in docs:
        document_id = uuid4()
        await get_storage().put(
            document_key(tenant_id, document_id, ".md"), content.encode("utf-8")
        )
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

    await ingest_offerings(conn, tenant_id=tenant_id, embedder=embedder)
