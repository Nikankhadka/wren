"""T-020: minimal tenant-admin read endpoint for the escalations queue.
T-031 extends it with claim/resolve actions (Surface 2's Escalations tab).

Claim/resolve use a conditional UPDATE (``where status = 'open'``/``where
status in (...)``) rather than read-then-write, so two admins racing on the
same row can't both "win" a claim - the loser's UPDATE simply matches zero
rows, and a follow-up read distinguishes "someone else already moved it"
(409) from "not this tenant's row" (404).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator

from app.core import auth, db

router = APIRouter(prefix="/api/escalations", tags=["escalations"])


class EscalationResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    reason: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class ResolveRequest(BaseModel):
    message: str | None = None

    @field_validator("message")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        # A structured client (or a human typing then deleting) may send an
        # empty/whitespace-only string rather than omitting the field -
        # treat it the same as "no message" (same convention as T-019's
        # blank customer_ref handling).
        if value is not None and not value.strip():
            return None
        return value


async def _fetch_one(
    conn: db.AppConnection, tenant_id: UUID, escalation_id: UUID
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "select id, conversation_id, reason, status, created_at, resolved_at "
        "from escalations where tenant_id = $1 and id = $2",
        tenant_id,
        escalation_id,
    )


@router.get("", response_model=list[EscalationResponse])
async def list_escalations(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EscalationResponse]:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select id, conversation_id, reason, status, created_at, resolved_at "
            "from escalations where tenant_id = $1 order by created_at desc "
            "limit $2 offset $3",
            admin.tenant_id,
            limit,
            offset,
        )
    return [EscalationResponse(**dict(row)) for row in rows]


@router.post("/{escalation_id}/claim", response_model=EscalationResponse)
async def claim_escalation(
    escalation_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> EscalationResponse:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        claimed = await conn.fetchrow(
            "update escalations set status = 'claimed' "
            "where tenant_id = $1 and id = $2 and status = 'open' "
            "returning id, conversation_id, reason, status, created_at, resolved_at",
            admin.tenant_id,
            escalation_id,
        )
        if claimed is not None:
            return EscalationResponse(**dict(claimed))

        existing = await _fetch_one(conn, admin.tenant_id, escalation_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="escalation not found")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"escalation is already {existing['status']}, not open",
    )


@router.post("/{escalation_id}/resolve", response_model=EscalationResponse)
async def resolve_escalation(
    escalation_id: UUID,
    body: ResolveRequest,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> EscalationResponse:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        resolved = await conn.fetchrow(
            "update escalations set status = 'resolved', resolved_at = now() "
            "where tenant_id = $1 and id = $2 and status in ('open', 'claimed') "
            "returning id, conversation_id, reason, status, created_at, resolved_at",
            admin.tenant_id,
            escalation_id,
        )
        if resolved is None:
            existing = await _fetch_one(conn, admin.tenant_id, escalation_id)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="escalation not found"
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="escalation is already resolved"
            )

        if body.message is not None:
            # T-031: a human_agent reply lands in the transcript the same
            # way any other message does - the customer surface picks it up
            # by polling (no push mechanism exists in this codebase; see
            # CustomerChat.tsx's escalated-state poll).
            await conn.execute(
                "insert into messages (tenant_id, conversation_id, role, content) "
                "values ($1, $2, 'human_agent', $3)",
                admin.tenant_id,
                resolved["conversation_id"],
                body.message,
            )

    return EscalationResponse(**dict(resolved))
