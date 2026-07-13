"""T-031: Surface 2's Conversations tab - list + full-transcript detail with
per-message trace (tool calls, inspection verdicts, cost).

cost_logs has no message_id column (only conversation_id) - the cost of one
turn is attributed to the assistant message that immediately preceded it,
via a lateral join on created_at. This is exact, not approximate: every
cost_logs write happens right after the assistant message insert on every
code path in chat.py (the happy path and the step-cap overflow path both
insert the message, then record costs). A durable fix (a message_id column
on cost_logs) is a future migration, not built here - flagged rather than
silently worked around with a schema change this ticket doesn't call for.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core import auth, db

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationSummary(BaseModel):
    id: UUID
    customer_ref: str | None
    status: str
    created_at: datetime
    message_count: int


class ToolCallDetail(BaseModel):
    id: UUID
    tool_name: str
    arguments: dict[str, Any]
    result: Any
    success: bool
    latency_ms: int | None


class MessageDetail(BaseModel):
    id: UUID
    role: str
    content: str
    agent_node: str | None
    created_at: datetime
    metadata: dict[str, Any]
    cost_usd: float | None
    tool_calls: list[ToolCallDetail]


class ConversationDetail(BaseModel):
    id: UUID
    customer_ref: str | None
    channel: str
    status: str
    created_at: datetime
    total_cost_usd: float
    messages: list[MessageDetail]


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
    status_filter: Annotated[
        Literal["open", "escalated", "closed"] | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationSummary]:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        rows = await conn.fetch(
            "select c.id, c.customer_ref, c.status, c.created_at, "
            "  (select count(*) from messages m "
            "   where m.tenant_id = $1 and m.conversation_id = c.id and m.role <> 'system') "
            "   as message_count "
            "from conversations c "
            "where c.tenant_id = $1 and ($2::text is null or c.status = $2) "
            "order by c.created_at desc "
            "limit $3 offset $4",
            admin.tenant_id,
            status_filter,
            limit,
            offset,
        )
    return [ConversationSummary(**dict(row)) for row in rows]


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    admin: Annotated[auth.AuthedTenantAdmin, Depends(auth.require_tenant_admin)],
) -> ConversationDetail:
    async with db.tenant_context(admin.tenant_id, "tenant_admin") as conn:
        conversation = await conn.fetchrow(
            "select id, customer_ref, channel, status, created_at from conversations "
            "where tenant_id = $1 and id = $2",
            admin.tenant_id,
            conversation_id,
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
            )

        message_rows = await conn.fetch(
            "select id, role, content, agent_node, created_at, metadata "
            "from messages where tenant_id = $1 and conversation_id = $2 "
            "order by created_at asc",
            admin.tenant_id,
            conversation_id,
        )
        tool_call_rows = await conn.fetch(
            "select tc.id, tc.message_id, tc.tool_name, tc.arguments, tc.result, "
            "  tc.success, tc.latency_ms "
            "from tool_calls tc "
            "join messages m on m.id = tc.message_id and m.tenant_id = tc.tenant_id "
            "where tc.tenant_id = $1 and m.conversation_id = $2",
            admin.tenant_id,
            conversation_id,
        )
        # Attribute each cost_logs row to the assistant message immediately
        # preceding it (see module docstring) - a lateral join per message.
        cost_rows = await conn.fetch(
            "select m.id as message_id, coalesce(sum(cl.cost_usd), 0) as cost_usd "
            "from messages m "
            "left join lateral ( "
            "  select cost_usd from cost_logs cl "
            "  where cl.tenant_id = m.tenant_id and cl.conversation_id = m.conversation_id "
            "    and cl.created_at >= m.created_at "
            "    and cl.created_at < coalesce("
            "      (select min(m2.created_at) from messages m2 "
            "       where m2.tenant_id = m.tenant_id and m2.conversation_id = m.conversation_id "
            "         and m2.created_at > m.created_at), "
            "      'infinity'::timestamptz)"
            ") cl on true "
            "where m.tenant_id = $1 and m.conversation_id = $2 and m.role = 'assistant' "
            "group by m.id",
            admin.tenant_id,
            conversation_id,
        )
        total_cost = await conn.fetchval(
            "select coalesce(sum(cost_usd), 0) from cost_logs "
            "where tenant_id = $1 and conversation_id = $2",
            admin.tenant_id,
            conversation_id,
        )

    tool_calls_by_message: dict[UUID, list[ToolCallDetail]] = {}
    for row in tool_call_rows:
        tool_calls_by_message.setdefault(row["message_id"], []).append(
            ToolCallDetail(
                id=row["id"],
                tool_name=row["tool_name"],
                arguments=json.loads(row["arguments"]),
                result=json.loads(row["result"]) if row["result"] is not None else None,
                success=row["success"],
                latency_ms=row["latency_ms"],
            )
        )
    cost_by_message: dict[UUID, float] = {
        row["message_id"]: float(row["cost_usd"]) for row in cost_rows
    }

    messages = [
        MessageDetail(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            agent_node=row["agent_node"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            cost_usd=cost_by_message.get(row["id"]),
            tool_calls=tool_calls_by_message.get(row["id"], []),
        )
        for row in message_rows
    ]

    return ConversationDetail(
        id=conversation["id"],
        customer_ref=conversation["customer_ref"],
        channel=conversation["channel"],
        status=conversation["status"],
        created_at=conversation["created_at"],
        total_cost_usd=float(total_cost),
        messages=messages,
    )
