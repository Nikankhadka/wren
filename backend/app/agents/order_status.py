"""T-019: order/repair/ticket status lookups.

The draft is fully deterministic - a template filled from one DB row, never
a generation call - so it can never invent a status or detail that isn't in
the row. Only the ref-code extraction itself needs the model: a regex would
have to assume a code format, which would hardcode an assumption about a
tenant's vocabulary (domain-agnostic hard rule) - codes are free-text data,
not a fixed pattern. Every return sets ``draft_deterministic`` (T-021) so
Inspection skips its checks entirely - none of them can meaningfully fail
against a templated string no LLM authored.
"""

from __future__ import annotations

import time
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.runtime import get_runtime
from pydantic import BaseModel

from app.agents.state import AgentState, GraphContext
from app.agents.tools import lookup_order_or_ticket
from app.core import db
from app.core.limits import with_timeout

ASK_FOR_CODE_MESSAGE = "Could you share the order, repair, or ticket code so I can look it up?"
NOT_FOUND_TEMPLATE = "I can't find {ref_code} - please double-check the code."
FOUND_TEMPLATE = 'Your {kind} {ref_code} is currently "{status}".'

_EXTRACTION_PROMPT = (
    "Extract the order, repair, or ticket reference code the customer is "
    "asking about (e.g. a code like 'R-1042' or 'ORD-2001') from their "
    "message. If they also mentioned their own customer reference, extract "
    "that as customer_ref. If no code is mentioned, leave ref_code empty - "
    "never invent one."
)


class RefExtraction(BaseModel):
    ref_code: str | None = None
    customer_ref: str | None = None


async def run(state: AgentState) -> dict[str, Any]:
    runtime = get_runtime(GraphContext)
    ctx = runtime.context
    writer = get_stream_writer()
    query = state["messages"][-1]["content"]

    extraction = await ctx.provider.extract(
        system_prompt=_EXTRACTION_PROMPT, user_input=query, schema=RefExtraction
    )

    if not extraction.ref_code:
        writer({"type": "refusal", "text": ASK_FOR_CODE_MESSAGE})
        return {
            "draft_response": ASK_FOR_CODE_MESSAGE,
            "draft_deterministic": True,
            "lookup": {"ref_code": None, "found": False},
        }

    async with db.tenant_context(ctx.tenant_id, "customer") as conn:
        # T-028: the one real tool call in the graph is time-bounded so a slow
        # or hung DB lookup can't stall the turn indefinitely.
        with ctx.turn.span("tool:lookup_order_or_ticket") as span:
            started = time.perf_counter()
            result = await with_timeout(
                lookup_order_or_ticket(
                    conn, ctx.tenant_id, extraction.ref_code, extraction.customer_ref
                ),
                ctx.tool_timeout_s,
                what="order lookup",
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            span.set(found=result.found, latency_ms=latency_ms)
    # T-030: record the tool invocation for the Surface-2 trace (chat.py
    # persists it against the assistant message once that row exists).
    writer(
        {
            "type": "tool_call",
            "name": "lookup_order_or_ticket",
            "arguments": {"ref_code": extraction.ref_code, "customer_ref": extraction.customer_ref},
            "result": {"found": result.found, "status": result.status, "kind": result.kind},
            "success": True,
            "latency_ms": latency_ms,
        }
    )

    if not result.found:
        text = NOT_FOUND_TEMPLATE.format(ref_code=extraction.ref_code)
        writer({"type": "refusal", "text": text})
        return {
            "draft_response": text,
            "draft_deterministic": True,
            "lookup": {"ref_code": extraction.ref_code, "found": False},
        }

    text = FOUND_TEMPLATE.format(kind=result.kind, ref_code=result.ref_code, status=result.status)
    writer({"type": "token", "text": text})
    return {
        "draft_response": text,
        "draft_deterministic": True,
        "lookup": {
            "ref_code": result.ref_code,
            "found": True,
            "status": result.status,
            "kind": result.kind,
        },
    }
