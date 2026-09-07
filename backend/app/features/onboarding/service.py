"""Onboarding persistence: the ``tenant_config.config->onboarding`` record and
the one-shot confirm writes.

Moved from api/onboarding.py. All confirm writes happen inside one
``tenant_context`` transaction, so a failure never leaves a tenant half
published.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.features.business.service import reconcile_offerings_batch
from app.features.tenants import service as tenant_service
from app.llm.embedder import Embedder
from app.onboarding.flow import PendingOffering
from app.shared import db

_CONFIG_SELECT = "config->'onboarding'"


class PublicSlugTakenError(RuntimeError):
    """The requested public page address belongs to another tenant."""


async def load_record(*, tenant_id: UUID) -> dict[str, Any]:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        raw = await conn.fetchval(
            f"select {_CONFIG_SELECT} from tenant_config where tenant_id = $1",
            tenant_id,
        )
    return json.loads(raw) if raw is not None else {}


async def set_onboarding_json(
    conn: db.AppConnection, tenant_id: UUID, record: dict[str, Any]
) -> None:
    await conn.execute(
        "update tenant_config set config = jsonb_set("
        "config, '{onboarding}', $2::jsonb, true), "
        "updated_at = now() where tenant_id = $1",
        tenant_id,
        json.dumps(record),
    )


async def save_record(*, tenant_id: UUID, record: dict[str, Any]) -> None:
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        await set_onboarding_json(conn, tenant_id, record)


async def apply_confirmation(
    *,
    tenant_id: UUID,
    system_prompt: str,
    business_name: str,
    slug: str,
    profile: dict[str, Any],
    customer_voice: dict[str, Any],
    completed_record: dict[str, Any],
    offering_candidates: list[PendingOffering] | None = None,
    embedder: Embedder | None = None,
) -> None:
    """Persist what confirm() computed in one atomic transaction.

    O-1 captures a business profile, not a priced catalog: onboarding no longer
    writes offerings or pricing_rules, and the columns it used to set from
    the interview (tone, payment_processing_mode) keep
    their schema defaults until a screen edits them. Priced answers come from
    the owner's uploaded material instead (C-1).

    W-9 adds ``customer_voice`` beside ``profile``: the structured voice the
    customer assistant speaks in, written in the same transaction so a confirmed
    tenant is never live without one. The free-text ``tone`` column is left
    exactly as it was - retiring it is its own ticket.
    """
    old_slug: str | None = None
    async with db.tenant_context(tenant_id, "tenant_admin") as conn:
        old_slug = await conn.fetchval("select slug from tenants where id = $1", tenant_id)
        await conn.execute(
            "update tenant_config set system_prompt=$2, "
            "config = jsonb_set("
            "jsonb_set(config, '{profile}', $3::jsonb, true), "
            "'{customer_voice}', $4::jsonb, true), "
            "updated_at=now() where tenant_id=$1",
            tenant_id,
            system_prompt,
            json.dumps(profile),
            json.dumps(customer_voice),
        )
        try:
            await conn.execute(
                "update tenants set business_name=$2, slug=$3 where id=$1",
                tenant_id,
                business_name,
                slug,
            )
        except asyncpg.UniqueViolationError as exc:
            raise PublicSlugTakenError from exc
        await set_onboarding_json(conn, tenant_id, completed_record)
        if offering_candidates:
            if embedder is None:
                raise RuntimeError("an embedder is required to publish offerings")
            await reconcile_offerings_batch(
                conn=conn,
                tenant_id=tenant_id,
                offerings=[item.model_dump() for item in offering_candidates],
                embedder=embedder,
            )
    if old_slug:
        tenant_service.invalidate_slug_cache(old_slug)
    tenant_service.invalidate_slug_cache(slug)
