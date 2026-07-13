"""T-005: unauthenticated slug -> tenant resolution for the customer surface.

``GET /api/public/tenant/{slug}`` is the one pre-auth read the customer surface
needs before any ``tenant_context`` exists: it goes through ``resolve_tenant_slug``
(migration 0003), the sole wren_resolver-owned RLS bypass, matching the pattern
``auth.py`` already uses for ``resolve_user_tenant`` / ``resolve_platform_admin``.
Unknown slugs are 404; known slugs return 200 with their ``status`` (including
``suspended``) so the frontend renders the right customer-surface state rather
than treating a suspended tenant as an error.

T-032 adds ``customer`` to the response: the tenant-configured greeting and
starter questions (``tenant_config.config -> 'customer'``) the empty-conversation
state renders (frontend.md 7.1). Deliberately NOT read through the resolver
function - widening the audited RLS-bypass's four-column contract (pinned by
test_rls.py / test_migrations.py) is a bigger privilege change than this needs.
Instead, once the slug resolves to a tenant id, the read happens under a normal
``tenant_context(tenant_id, "customer")`` like every other customer-surface
query, and only the ``customer`` subkey ever leaves this endpoint - the rest of
``config`` (limits, tax, onboarding state) stays private.

Results are cached in-process for 60s per slug (only positive resolutions - a
negative result is never cached, so a slug becoming valid via signup is visible
immediately rather than waiting out a stale 404).
"""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core import db

router = APIRouter(prefix="/api/public", tags=["public"])

_CACHE_TTL_SECONDS = 60.0


class TenantResolveResponse(BaseModel):
    id: UUID
    name: str
    status: str
    brand: dict[str, Any]
    customer: dict[str, Any]


_cache: dict[str, tuple[float, TenantResolveResponse]] = {}


async def _customer_config(tenant_id: UUID) -> dict[str, Any]:
    """The tenant-configured customer-surface bits (greeting, starter
    questions) - read under the customer tenant context, never through the
    resolver bypass. Missing/unset config is an empty dict, never an error."""
    async with db.tenant_context(tenant_id, "customer") as conn:
        raw = await conn.fetchval(
            "select config -> 'customer' from tenant_config where tenant_id = $1",
            tenant_id,
        )
    if raw is None:
        return {}
    # asyncpg returns jsonb as raw text without an explicit codec registered.
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


async def _resolve(slug: str) -> TenantResolveResponse | None:
    now = time.monotonic()
    cached = _cache.get(slug)
    if cached is not None and cached[0] > now:
        return cached[1]

    pool = db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select id, name, status, brand from resolve_tenant_slug($1)", slug
        )
    if row is None:
        _cache.pop(slug, None)
        return None

    # asyncpg returns jsonb as raw text without an explicit codec registered.
    brand = json.loads(row["brand"])
    result = TenantResolveResponse(
        id=row["id"],
        name=row["name"],
        status=row["status"],
        brand=brand,
        customer=await _customer_config(row["id"]),
    )
    _cache[slug] = (now + _CACHE_TTL_SECONDS, result)
    return result


@router.get("/tenant/{slug}", response_model=TenantResolveResponse)
async def resolve_tenant(slug: str) -> TenantResolveResponse:
    result = await _resolve(slug)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown tenant slug")
    return result
