"""T-020: minimal tenant-admin read endpoint for the escalations queue.

Deliberately just a list for now - claim/resolve actions (Surface 2's
Escalations tab) are phase-3's T-033, which extends this file rather than
this ticket building ahead of its own scope.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core import auth, db

router = APIRouter(prefix="/api/escalations", tags=["escalations"])


class EscalationResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    reason: str
    status: str
    created_at: datetime


@router.get("", response_model=list[EscalationResponse])
async def list_escalations(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> list[EscalationResponse]:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select id, conversation_id, reason, status, created_at from escalations "
            "where tenant_id = $1 order by created_at desc",
            admin.tenant_id,
        )
    return [EscalationResponse(**dict(row)) for row in rows]
