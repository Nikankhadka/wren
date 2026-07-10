"""T-004: platform-admin probe endpoint.

Minimal authed route exercising ``require_platform_admin`` end to end; the
real platform surface (tenant listing/suspension etc.) lands in a later ticket.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core import auth

router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/ping")
async def ping(
    _admin: Annotated[auth.AuthedPlatformAdmin, Depends(auth.require_platform_admin)],
) -> dict[str, bool]:
    return {"ok": True}
