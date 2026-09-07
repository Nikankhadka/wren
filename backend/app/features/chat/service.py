"""Chat persistence: conversation/message rows, tenant and budget resolution,
and turn persistence (assistant message, tool_calls, cost_logs).

Moved out of api/chat.py. The ticket-level rules stay in the handler docs:
nothing is customer-visible until Inspection clears a draft, only limit stops
are terminal (C-5), and step caps/budget stops hand off gracefully instead of
erroring.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from app.observability.cost import TokenUsage, record_costs
from app.shared import config, db
from app.shared.limits import TenantLimits, tenant_over_budget


async def resolve_active_tenant(slug: str) -> UUID:
    """T-005: public tenant lookup - no auth, scope comes from the slug.
    Raises ValueError when the slug is unknown or not active."""
    pool = db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("select id, status from resolve_tenant_slug($1)", slug)
    if row is None or row["status"] != "active":
        raise ValueError("unknown tenant slug")
    return UUID(str(row["id"]))


async def resolve_conversation(
    *,
    tenant_id: UUID,
    conversation_id: UUID | None,
    message: str,
) -> tuple[UUID, str, TenantLimits, bool]:
    """Open or fetch the conversation, persist the customer message, and
    resolve this tenant's limits and remaining daily budget - all inside one
    customer-scoped transaction. Raises ValueError when the conversation id
    belongs to someone else. Returns
    (conversation_id, status, limits, over_budget).

    C-6 returns the status rather than an ``already_escalated`` boolean. Two
    different states now stop the graph for two different reasons - a limit
    stop ends the conversation, a human takeover just means someone else is
    replying - and a boolean per state is how a status column gets
    reimplemented one flag at a time."""
    async with db.tenant_context(tenant_id, "customer") as conn:
        if conversation_id is not None:
            row = await conn.fetchrow(
                "select status from conversations where id = $1 and tenant_id = $2",
                conversation_id,
                tenant_id,
            )
            if row is None:
                raise ValueError("conversation not found")
            status = str(row["status"])
        else:
            conversation_id = await conn.fetchval(
                "insert into conversations (tenant_id) values ($1) returning id", tenant_id
            )
            status = "open"
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content) "
            "values ($1, $2, 'customer', $3)",
            tenant_id,
            conversation_id,
            message,
        )
        # T-028: resolve this tenant's caps and check the daily budget before
        # any LLM call. Both reads happen inside the customer context so RLS
        # scopes them to this tenant.
        config_row = await conn.fetchrow(
            "select config from tenant_config where tenant_id = $1", tenant_id
        )
        limits = TenantLimits.resolve(
            json.loads(config_row["config"]) if config_row and config_row["config"] else {},
            config.get_settings(),
        )
        over_budget = await tenant_over_budget(conn, tenant_id, limits)
    return conversation_id, status, limits, over_budget


async def record_limit_escalation(
    *, tenant_id: UUID, conversation_id: UUID, reason: str, message: str, terminal: bool = True
) -> None:
    """T-028: a turn ended without an answer - record the escalation (deduped
    by 0011's partial unique index) and persist the graceful handoff as the
    assistant message. No graph runs.

    ``terminal`` decides whether the conversation is also closed to further
    turns, and C-5 left this the only place that can do it. A cap the tenant
    actually hit - daily budget, step cap, turn budget - is a hard stop by
    design: the chat ends, the composer locks, and that is the behaviour being
    paid for.

    A provider failure is not that. It is a transient upstream fault the
    customer had no part in, and ending their conversation over it is exactly
    the dead end C-5 removed everywhere else - so that path passes
    ``terminal=False`` and the customer can simply ask again."""
    async with db.tenant_context(tenant_id, "customer") as conn:
        await conn.execute(
            "insert into escalations (tenant_id, conversation_id, reason) values ($1, $2, $3) "
            "on conflict (tenant_id, conversation_id) where status = 'open' do nothing",
            tenant_id,
            conversation_id,
            reason,
        )
        if terminal:
            await conn.execute(
                "update conversations set status = 'escalated' "
                "where id = $1 and tenant_id = $2 and status <> 'escalated'",
                conversation_id,
                tenant_id,
            )
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content, "
            "agent_node, metadata) "
            "values ($1, $2, 'assistant', $3, 'limit_escalation', $4)",
            tenant_id,
            conversation_id,
            message,
            json.dumps({"limit_escalation": reason}),
        )


TAKEOVER_STAMP = "You took over this conversation"
HANDBACK_STAMP = "Handed back to Agencx"


async def set_conversation_handler(
    *, tenant_id: UUID, conversation_id: UUID, human: bool, role: str = "tenant_admin"
) -> bool:
    """C-6: switch a conversation between the assistant and a staff member.

    Returns False when the conversation does not exist, or when a tenant limit
    already ended it - a cap is a hard stop and taking it over would quietly
    reopen a conversation the tenant is not paying to continue. Idempotent: a
    second takeover of an already-taken-over conversation changes nothing and
    adds no second stamp.

    The stamp is written as a ``system`` message so the transcript reads
    honestly to whoever scrolls it later - who was speaking, and from when.
    """
    target = "human" if human else "open"
    previous = "open" if human else "human"
    async with db.tenant_context(tenant_id, role) as conn:
        updated = await conn.fetchval(
            "update conversations set status = $3 "
            "where id = $1 and tenant_id = $2 and status = $4 returning id",
            conversation_id,
            tenant_id,
            target,
            previous,
        )
        if updated is None:
            return False
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content) "
            "values ($1, $2, 'system', $3)",
            tenant_id,
            conversation_id,
            TAKEOVER_STAMP if human else HANDBACK_STAMP,
        )
    return True


async def post_human_reply(
    *, tenant_id: UUID, conversation_id: UUID, message: str, role: str = "tenant_admin"
) -> None:
    """A staff member's own words, into an open conversation. The customer's
    client picks it up on the poll C-5 left running."""
    async with db.tenant_context(tenant_id, role) as conn:
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content) "
            "values ($1, $2, 'human_agent', $3)",
            tenant_id,
            conversation_id,
            message,
        )


async def record_turn_costs(
    *, tenant_id: UUID, conversation_id: UUID, usages: list[TokenUsage]
) -> None:
    async with db.tenant_context(tenant_id, "customer") as conn:
        await record_costs(conn, tenant_id, conversation_id, usages)


async def persist_assistant_turn(
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    full_text: str,
    verdicts: dict[str, object],
    tool_calls: list[dict[str, object]],
    usages: list[TokenUsage],
    author_node: str | None = None,
    response: dict[str, Any] | None = None,
    price_summary_ms: float | None = None,
) -> None:
    """Persist the approved assistant message, its tool-call trace rows, and
    per-turn token costs in one transaction.

    ``author_node`` names the graph node that produced the message (F-3) and
    lands on the ``agent_node`` column the Surface-2 trace viewer renders;
    None when no graph ran (the limit-escalation paths write their own rows).
    """
    async with db.tenant_context(tenant_id, "customer") as conn:
        metadata: dict[str, Any] = {"inspection": verdicts} if verdicts else {}
        if response:
            metadata["response"] = response
        if price_summary_ms is not None:
            metadata["price_summary_ms"] = price_summary_ms
        message_id = await conn.fetchval(
            "insert into messages (tenant_id, conversation_id, role, content, "
            "agent_node, metadata) "
            "values ($1, $2, 'assistant', $3, $4, $5) returning id",
            tenant_id,
            conversation_id,
            full_text,
            author_node,
            json.dumps(metadata),
        )
        # T-030: tool_calls rows (the Surface-2 TraceTree) and cost_logs rows
        # (per-turn token accounting, backing the T-028 daily budget).
        for call in tool_calls:
            await conn.execute(
                "insert into tool_calls "
                "(tenant_id, message_id, tool_name, arguments, result, success, latency_ms) "
                "values ($1, $2, $3, $4, $5, $6, $7)",
                tenant_id,
                message_id,
                str(call.get("name", "")),
                json.dumps(call.get("arguments", {})),
                json.dumps(call.get("result")),
                bool(call.get("success", True)),
                call.get("latency_ms"),
            )
        await record_costs(conn, tenant_id, conversation_id, usages)


async def recent_messages(
    *, tenant_id: UUID, conversation_id: UUID, limit: int
) -> list[dict[str, Any]]:
    """The tail of a conversation, oldest first, as plain role/content dicts.

    The agent's view of the thread (P-3). Ordered newest-first in SQL so the
    limit keeps the *recent* messages, then reversed for the prompt, where
    chronological order is what the model needs.
    """
    async with db.tenant_context(tenant_id, "customer") as conn:
        rows = await conn.fetch(
            "select role, content, metadata from messages "
            "where tenant_id = $1 and conversation_id = $2 "
            "and role in ('customer', 'assistant', 'human_agent') "
            "order by created_at desc, id desc "
            "limit $3",
            tenant_id,
            conversation_id,
            limit,
        )
    messages: list[dict[str, Any]] = []
    for row in reversed(rows):
        message: dict[str, Any] = {"role": row["role"], "content": row["content"]}
        if row["metadata"]:
            raw_metadata = row["metadata"]
            metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
            if isinstance(metadata, dict) and metadata.get("response"):
                message["response"] = metadata["response"]
        messages.append(message)
    return messages


async def list_messages(
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    after: datetime | None,
    limit: int,
) -> list[dict[str, Any]]:
    """T-031: unauthenticated transcript poll for the customer surface. Trust
    model matches POST /api/chat's conversation_id: knowing the UUID is the
    capability. Raises ValueError when the conversation is not this tenant's."""
    async with db.tenant_context(tenant_id, "customer") as conn:
        exists = await conn.fetchval(
            "select 1 from conversations where tenant_id = $1 and id = $2",
            tenant_id,
            conversation_id,
        )
        if exists is None:
            raise ValueError("conversation not found")
        rows = await conn.fetch(
            "select id, role, content, created_at from messages "
            "where tenant_id = $1 and conversation_id = $2 "
            "and role in ('customer', 'assistant', 'human_agent') "
            "and ($3::timestamptz is null or created_at > $3) "
            "order by created_at asc "
            "limit $4",
            tenant_id,
            conversation_id,
            after,
            limit,
        )
    return [dict(row) for row in rows]
