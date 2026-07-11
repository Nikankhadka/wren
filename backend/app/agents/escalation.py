"""T-020: the Escalation Agent - terminal by design.

Creates the escalations row, flips the conversation to 'escalated' (chat.py
checks this before ever invoking the graph again - see
``_stream_escalated_response``), and drafts the handoff message. Reason
comes from ``state.get("escalation_reason")``, set upstream by whichever
path routed here (supervisor.py's low-confidence override or explicit
"talk to a human" routing; price_gate.py's second-violation escalation) -
this node never guesses why it's running, it only records what it's told.
No further agent turn ever runs in an escalated conversation; the human
handoff itself (Surface 2 replying as ``human_agent``) is a later ticket -
this one only needs to not block it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.config import get_stream_writer
from langgraph.runtime import get_runtime

from app.agents.state import AgentState, GraphContext
from app.core import db

HANDOFF_MESSAGE = (
    "Thanks for your patience - a human will pick this up from here and follow up with you."
)

_DEFAULT_REASON = "unspecified"


async def run(state: AgentState) -> dict[str, Any]:
    runtime = get_runtime(GraphContext)
    ctx = runtime.context
    writer = get_stream_writer()

    reason = state.get("escalation_reason") or _DEFAULT_REASON
    conversation_id = UUID(state["conversation_id"])

    async with db.tenant_context(ctx.tenant_id, "customer") as conn:
        # 0011_escalations_dedupe.sql's partial unique index makes this a
        # no-op if a concurrent turn on the same conversation already
        # escalated it - the conditional update below then also becomes a
        # no-op, so only the first of two racing turns actually records
        # anything.
        await conn.execute(
            "insert into escalations (tenant_id, conversation_id, reason) values ($1, $2, $3) "
            "on conflict (tenant_id, conversation_id) where status = 'open' do nothing",
            ctx.tenant_id,
            conversation_id,
            reason,
        )
        await conn.execute(
            "update conversations set status = 'escalated' "
            "where id = $1 and tenant_id = $2 and status <> 'escalated'",
            conversation_id,
            ctx.tenant_id,
        )

    # A producing node upstream (price_gate on its second violation) may have
    # already streamed and set a handoff message - don't stream a second one.
    if state["draft_response"]:
        writer({"type": "escalated"})
        return {"escalated": True}

    writer({"type": "refusal", "text": HANDOFF_MESSAGE})
    writer({"type": "escalated"})
    return {"escalated": True, "draft_response": HANDOFF_MESSAGE}
