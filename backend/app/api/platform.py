"""T-004/T-033: the platform-owner surface (admin.wren.app).

Deliberately minimal per frontend.md 7.3: one tenants table with aggregate
metrics, a provision flow, and suspend/reactivate - "nothing else at core
scope". Every query here runs under ``tenant_context(None, "platform_admin")``
(no single-tenant scope - the whole point of this surface is reading across
tenants) through the ``platform_admin_all`` RLS policy on both ``tenants`` and
``tenant_config`` (migration 0013 widened the latter from read-only to match -
provisioning needs to insert a config row, database.md section 3), never the
resolver-function bypass pattern ``public.py``/``auth.py`` use for pre-auth
reads.

KNOWN GAP (flagged, not solved here - see .agents/memory.md T-033): a
platform-admin-provisioned tenant has no owner (no ``users`` row) because
creating a Supabase auth user server-side needs Admin API credentials this
project doesn't have yet (no hosted Supabase project - same gap as T-004/T-006).
The self-serve ``POST /api/tenants`` signup flow can't attach an owner to a
pre-existing tenant either: the service role's RLS grant on ``tenants`` is
INSERT-only (database.md section 2.3, Shape C) by deliberate design, so it
can't SELECT or UPDATE an existing row to "claim" it - punching that hole
would be a real security-boundary change, not something to make silently in
this ticket. Provisioned tenants therefore land in `status='provisioning'`
and stay there until a founder decision on the claim mechanism (narrow RLS
carve-out vs. real Supabase Admin API user creation once that project
exists). This means T-033's literal accept criterion ("provisioning yields a
tenant that can complete onboarding with zero founder code/DB touches") is
not fully met - the tenant shell exists, but nothing can complete onboarding
against it yet without that follow-up.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.api.public import invalidate_slug_cache
from app.core import auth, db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform", tags=["platform"])

# Mirrors the DDL check on tenants.slug (database.md section 3), same as
# app/api/tenants.py's signup validator.
_SLUG_RE = re.compile(r"^[a-z0-9](-?[a-z0-9])*$")
_VALID_STATUSES = frozenset({"provisioning", "active", "suspended"})


@router.get("/ping")
async def ping(
    _admin: Annotated[auth.AuthedPlatformAdmin, Depends(auth.require_platform_admin)],
) -> dict[str, bool]:
    return {"ok": True}


class TenantSummary(BaseModel):
    id: UUID
    slug: str
    name: str
    status: str
    created_at: datetime
    conversation_count: int
    cost_usd: float


class PlatformMetrics(BaseModel):
    tenant_count: int
    total_cost_usd: float


class ProvisionTenantRequest(BaseModel):
    slug: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("slug")
    @classmethod
    def _valid_slug(cls, value: str) -> str:
        if not _SLUG_RE.fullmatch(value):
            raise ValueError("slug must match ^[a-z0-9](-?[a-z0-9])*$")
        return value


class ProvisionTenantResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    status: str
    note: str


class SlugAvailabilityResponse(BaseModel):
    available: bool


class UpdateTenantStatusRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str) -> str:
        if value not in _VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}")
        return value


_PROVISION_NOTE = (
    "Tenant shell created with no owner yet - the self-serve signup flow can't "
    "currently attach an owner to a pre-provisioned tenant (a known, flagged "
    "gap; see .agents/memory.md T-033). Share the business's details with the "
    "founder to complete onboarding by hand for now."
)


@router.get("/metrics", response_model=PlatformMetrics)
async def get_metrics(
    _admin: Annotated[auth.AuthedPlatformAdmin, Depends(auth.require_platform_admin)],
) -> PlatformMetrics:
    async with db.tenant_context(None, "platform_admin") as conn:
        row = await conn.fetchrow(
            "select (select count(*) from tenants) as tenant_count, "
            "  (select coalesce(sum(cost_usd), 0) from cost_logs) as total_cost_usd"
        )
    assert row is not None
    return PlatformMetrics(
        tenant_count=row["tenant_count"], total_cost_usd=float(row["total_cost_usd"])
    )


@router.get("/tenants", response_model=list[TenantSummary])
async def list_tenants(
    _admin: Annotated[auth.AuthedPlatformAdmin, Depends(auth.require_platform_admin)],
) -> list[TenantSummary]:
    async with db.tenant_context(None, "platform_admin") as conn:
        rows = await conn.fetch(
            "select t.id, t.slug, t.name, t.status, t.created_at, "
            "  (select count(*) from conversations c where c.tenant_id = t.id) "
            "    as conversation_count, "
            "  (select coalesce(sum(cl.cost_usd), 0) from cost_logs cl "
            "    where cl.tenant_id = t.id) as cost_usd "
            "from tenants t "
            "order by t.created_at desc"
        )
    return [TenantSummary(**{**dict(row), "cost_usd": float(row["cost_usd"])}) for row in rows]


@router.get("/tenants/slug-availability", response_model=SlugAvailabilityResponse)
async def check_slug_availability(
    _admin: Annotated[auth.AuthedPlatformAdmin, Depends(auth.require_platform_admin)],
    slug: Annotated[str, Query(min_length=1, max_length=40)],
) -> SlugAvailabilityResponse:
    async with db.tenant_context(None, "platform_admin") as conn:
        exists = await conn.fetchval("select 1 from tenants where slug = $1", slug)
    return SlugAvailabilityResponse(available=exists is None)


@router.post(
    "/tenants", response_model=ProvisionTenantResponse, status_code=status.HTTP_201_CREATED
)
async def provision_tenant(
    body: ProvisionTenantRequest,
    admin: Annotated[auth.AuthedPlatformAdmin, Depends(auth.require_platform_admin)],
) -> ProvisionTenantResponse:
    tenant_id = uuid4()
    try:
        async with db.tenant_context(None, "platform_admin") as conn:
            await conn.execute(
                "insert into tenants (id, slug, name, status) values ($1, $2, $3, 'provisioning')",
                tenant_id,
                body.slug,
                body.name,
            )
            await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="slug already taken"
        ) from exc

    logger.info(
        "audited platform action: tenant_provisioned",
        extra={
            "action": "tenant_provisioned",
            "actor_user_id": str(admin.user_id),
            "tenant_id": str(tenant_id),
            "slug": body.slug,
            "role": "platform_admin",
        },
    )
    return ProvisionTenantResponse(
        id=tenant_id, slug=body.slug, name=body.name, status="provisioning", note=_PROVISION_NOTE
    )


@router.patch("/tenants/{tenant_id}", response_model=TenantSummary)
async def update_tenant_status(
    tenant_id: UUID,
    body: UpdateTenantStatusRequest,
    admin: Annotated[auth.AuthedPlatformAdmin, Depends(auth.require_platform_admin)],
) -> TenantSummary:
    async with db.tenant_context(None, "platform_admin") as conn:
        row = await conn.fetchrow(
            "update tenants set status = $1 where id = $2 "
            "returning id, slug, name, status, created_at",
            body.status,
            tenant_id,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
        counts = await conn.fetchrow(
            "select "
            "  (select count(*) from conversations c "
            "     where c.tenant_id = $1) as conversation_count, "
            "  (select coalesce(sum(cl.cost_usd), 0) from cost_logs cl "
            "     where cl.tenant_id = $1) as cost_usd",
            tenant_id,
        )
    assert counts is not None

    # The customer surface caches positive slug resolutions for 60s (public.py)
    # - a suspend/reactivate from this surface must be visible immediately, not
    # after a stale-cache window, so invalidate the one slug that changed.
    invalidate_slug_cache(row["slug"])

    logger.info(
        "audited platform action: tenant_status_changed",
        extra={
            "action": "tenant_status_changed",
            "actor_user_id": str(admin.user_id),
            "tenant_id": str(tenant_id),
            "new_status": body.status,
            "role": "platform_admin",
        },
    )
    return TenantSummary(**{**dict(row), **dict(counts), "cost_usd": float(counts["cost_usd"])})
