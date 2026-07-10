"""T-004: tenant signup and the authed tenant-admin "me" probe.

``POST /api/tenants`` is the one legitimate caller of ``app.role = 'service'``
(database.md section 2.3, Shape C): the frontend signs a user up with Supabase
first, then calls this endpoint with that user's access token to provision the
tenant/tenant_config/users rows in a single transaction. Every call is logged as
an audited service action (actor user id + action), per the ticket.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.core import auth, db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

# Mirrors the DDL check on tenants.slug (database.md section 3) exactly, so a bad
# slug is rejected at the API layer (422) before it can ever reach the insert.
_SLUG_RE = re.compile(r"^[a-z0-9](-?[a-z0-9])*$")


class TenantSignupRequest(BaseModel):
    slug: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("slug")
    @classmethod
    def _valid_slug(cls, value: str) -> str:
        if not _SLUG_RE.fullmatch(value):
            raise ValueError("slug must match ^[a-z0-9](-?[a-z0-9])*$")
        return value


class TenantSignupResponse(BaseModel):
    tenant_id: UUID
    slug: str


class TenantMeResponse(BaseModel):
    tenant_id: UUID
    slug: str
    name: str


@router.post("", response_model=TenantSignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    body: TenantSignupRequest,
    user_id: Annotated[UUID, Depends(auth.authenticate)],
) -> TenantSignupResponse:
    pool = db.get_pool()

    # A user already belonging to a tenant is rejected before the write
    # transaction opens - the service role's Shape C policy is INSERT-only, so
    # this membership check must be its own pre-context read (0009's resolver),
    # the same as the tenant-admin dependency.
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("select tenant_id from resolve_user_tenant($1)", user_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="user already has a tenant"
        )

    # Generated here, not via the column default + RETURNING: Postgres enforces a
    # table's SELECT policies on RETURNING even for INSERT, and Shape C grants the
    # service role INSERT only (database.md section 2.3) - it has no SELECT policy
    # on tenants, so `insert ... returning id` would itself raise "new row violates
    # row-level security policy". Supplying the id up front sidesteps that read.
    tenant_id = uuid4()
    try:
        async with db.tenant_context(None, "service") as conn:
            await conn.execute(
                "insert into tenants (id, slug, name, status) values ($1, $2, $3, 'active')",
                tenant_id,
                body.slug,
                body.name,
            )
            await conn.execute("insert into tenant_config (tenant_id) values ($1)", tenant_id)
            await conn.execute(
                "insert into users (id, tenant_id, role) values ($1, $2, 'owner')",
                user_id,
                tenant_id,
            )
    except asyncpg.UniqueViolationError as exc:
        # users_pkey means a same-user double-submit raced past the pre-check;
        # anything else is the tenants slug uniqueness.
        detail = (
            "user already has a tenant"
            if exc.constraint_name == "users_pkey"
            else "slug already taken"
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc

    logger.info(
        "audited service action: tenant_signup",
        extra={
            "action": "tenant_signup",
            "actor_user_id": str(user_id),
            "tenant_id": str(tenant_id),
            "slug": body.slug,
            "role": "service",
        },
    )
    return TenantSignupResponse(tenant_id=tenant_id, slug=body.slug)


@router.get("/me", response_model=TenantMeResponse)
async def me(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> TenantMeResponse:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        row = await conn.fetchrow("select slug, name from tenants where id = $1", admin.tenant_id)
    if row is None:
        # Should not happen for a resolved tenant_admin (FK guarantees the tenant
        # row exists), but fail closed rather than return a null-filled body.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return TenantMeResponse(tenant_id=admin.tenant_id, slug=row["slug"], name=row["name"])
