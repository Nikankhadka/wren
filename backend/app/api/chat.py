"""T-011/T-012: bare customer chat, now routed through the agent graph.

``POST /api/chat`` is unauthenticated (the customer surface has no login) -
tenant scope comes entirely from the slug, resolved the same way T-005's
public tenant lookup does. As of T-012 the actual retrieval/generation logic
lives in app/agents/graph.py's compiled graph (supervisor -> knowledge ->
inspection for now, since the supervisor stub always routes to knowledge) -
this module just resolves the tenant/conversation, invokes the graph, and
translates its custom-streamed events into SSE. Behavior is unchanged from
T-011 (same event shape, same refusal-on-no-context rule, same
conversation/message persistence) - only the internals moved.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.graph import get_graph
from app.agents.state import AgentState, GraphContext
from app.core import db
from app.llm.dependency import get_llm_provider
from app.llm.provider import LLMProvider
from app.retrieval.dependency import get_reranker_dependency
from app.retrieval.rerank import Reranker

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    slug: str
    conversation_id: UUID | None = None
    message: str = Field(min_length=1)


async def _resolve_active_tenant(slug: str) -> UUID:
    pool = db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("select id, status from resolve_tenant_slug($1)", slug)
    if row is None or row["status"] != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown tenant slug")
    tenant_id: UUID = row["id"]
    return tenant_id


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _initial_state(*, conversation_id: UUID, tenant_id: UUID, message: str) -> AgentState:
    return {
        "conversation_id": str(conversation_id),
        "tenant_id": str(tenant_id),
        "messages": [{"role": "customer", "content": message}],
        "route": None,
        "route_confidence": None,
        "retrieved_chunks": [],
        "selections": [],
        "engine_quote": None,
        "draft_response": "",
        "inspection": None,
        "escalated": False,
    }


async def _stream_chat_response(
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    message: str,
    provider: LLMProvider,
    reranker: Reranker,
) -> AsyncIterator[str]:
    yield _sse({"type": "conversation", "conversation_id": str(conversation_id)})

    graph = get_graph()
    context = GraphContext(tenant_id=tenant_id, provider=provider, reranker=reranker)
    initial_state = _initial_state(
        conversation_id=conversation_id, tenant_id=tenant_id, message=message
    )

    full_text = ""
    async for event in graph.astream(initial_state, context=context, stream_mode="custom"):
        if event["type"] == "token":
            full_text += event["text"]
        elif event["type"] == "refusal":
            full_text = str(event["text"])
        yield _sse(event)

    async with db.tenant_context(tenant_id, "customer") as conn:
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content) "
            "values ($1, $2, 'assistant', $3)",
            tenant_id,
            conversation_id,
            full_text,
        )
    yield _sse({"type": "done"})


@router.post("")
async def chat(
    body: ChatRequest,
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    reranker: Annotated[Reranker, Depends(get_reranker_dependency)],
) -> StreamingResponse:
    tenant_id = await _resolve_active_tenant(body.slug)

    async with db.tenant_context(tenant_id, "customer") as conn:
        if body.conversation_id is not None:
            exists = await conn.fetchval(
                "select 1 from conversations where id = $1 and tenant_id = $2",
                body.conversation_id,
                tenant_id,
            )
            if not exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
                )
            conversation_id = body.conversation_id
        else:
            conversation_id = await conn.fetchval(
                "insert into conversations (tenant_id) values ($1) returning id", tenant_id
            )
        await conn.execute(
            "insert into messages (tenant_id, conversation_id, role, content) "
            "values ($1, $2, 'customer', $3)",
            tenant_id,
            conversation_id,
            body.message,
        )

    return StreamingResponse(
        _stream_chat_response(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message=body.message,
            provider=provider,
            reranker=reranker,
        ),
        media_type="text/event-stream",
    )
