"""T-020/C-5: the Escalation Agent - a recorded handoff, not a dead end.

Creates the escalations row and drafts the handoff message. Reason comes
from ``state.get("escalation_reason")``, set upstream by whichever path
routed here (the agent's ``create_escalation`` tool; price_gate.py's
second-violation escalation; inspection's second failure) - this node never
guesses why it's running, it only records what it's told.

**C-5: this no longer flips ``conversations.status``.** It used to, which
made every handoff terminal: the next customer message got a bare
``escalated`` event with no agent turn, and the composer locked. One
unanswerable pricing question could therefore end an entire support session
that was working fine for everything else. An escalation is a notification -
"a human should look at this" - not a statement about who is replying. The
conversation stays open, the next message gets a full agent turn, and the
owner's reply reaches a live chat instead of a closed one.

Limit escalations (T-028: budget, step cap, turn budget, provider error)
still flip the status and stay terminal. Those are a hard stop by design -
see ``service.record_limit_escalation``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.config import get_stream_writer
from langgraph.runtime import get_runtime

from app.agents.state import AgentState, GraphContext
from app.shared import db

# Names what is being handed off and keeps the door open. Deliberately not a
# sign-off: "someone will get back to you" reads as the end of a conversation,
# and after C-5 the conversation is not over.
HANDOFF_MESSAGE = "I’ve forwarded your query to the business. They can reply to you here."

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
        # escalated it, so only the first of two racing turns records a row.
        # It also means a second handoff on a still-open escalation adds
        # nothing to the owner's queue - which is what C-5 wants, since the
        # conversation now continues and may well hand off again.
        await conn.execute(
            "insert into escalations (tenant_id, conversation_id, reason) values ($1, $2, $3) "
            "on conflict (tenant_id, conversation_id) where status = 'open' do nothing",
            ctx.tenant_id,
            conversation_id,
            reason,
        )
    # A producing node upstream (price_gate on its second violation) may have
    # already streamed and set a handoff message - don't stream a second one.
    if state["draft_response"]:
        writer({"type": "handoff"})
        return {"escalated": True}

    writer({"type": "refusal", "text": HANDOFF_MESSAGE})
    writer({"type": "handoff"})
    return {"escalated": True, "draft_response": HANDOFF_MESSAGE, "author_node": "escalation"}
