"""T-011: bare customer chat - one straight LLM call, no agents yet.

``POST /api/chat`` is unauthenticated (the customer surface has no login) -
tenant scope comes entirely from the slug, resolved the same way T-005's
public tenant lookup does, then everything else runs under
``tenant_context(tenant_id, 'customer')``.

Grounding is deterministic at the boundary: if reranking finds nothing above
``REFUSAL_SCORE_THRESHOLD``, the customer gets a canned refusal message and
no LLM call happens at all - the model is never given the chance to invent
an answer from nothing. When there is relevant context, the model is
instructed to cite every claim with a bracket number keyed to the numbered
context block, and citations are sent to the client before any tokens so it
can resolve `[1]`-style markers as they stream in.

The DB connection is only held for the two short-lived steps (retrieval,
and the final persist) - not for the whole duration of the LLM stream -
so a slow generation doesn't tie up a pooled connection.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core import db
from app.llm.dependency import get_llm_provider
from app.llm.provider import ChatMessage, LLMProvider
from app.retrieval.dependency import get_reranker_dependency
from app.retrieval.rerank import Reranker
from app.retrieval.service import retrieve
from app.retrieval.types import RetrievedChunk

router = APIRouter(prefix="/api/chat", tags=["chat"])

REFUSAL_SCORE_THRESHOLD = 0.0
REFUSAL_MESSAGE = (
    "I don't have information about that. Please contact the business directly for help."
)


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


def _citation_source(chunk: RetrievedChunk) -> str:
    if chunk.metadata.get("kind") == "catalog_item":
        return "catalog"
    source = chunk.metadata.get("source")
    return str(source) if source else "knowledge base"


def _build_system_prompt(chunks: list[RetrievedChunk], *, tenant_prompt: str, tone: str) -> str:
    context_block = "\n\n".join(f"[{i + 1}] {chunk.content}" for i, chunk in enumerate(chunks))
    base = tenant_prompt or "You are the AI support and sales assistant for this business."
    return (
        f"{base}\n"
        f"Tone: {tone or 'friendly'}.\n"
        "Answer the customer's question using ONLY the numbered context below. "
        "Cite every factual claim with its bracket number, e.g. [1]. If the "
        "context doesn't fully answer the question, say what you don't know - "
        "never invent information.\n\n"
        f"Context:\n{context_block}"
    )


async def _stream_chat_response(
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    message: str,
    provider: LLMProvider,
    reranker: Reranker,
) -> AsyncIterator[str]:
    async with db.tenant_context(tenant_id, "customer") as conn:
        config_row = await conn.fetchrow(
            "select system_prompt, tone from tenant_config where tenant_id = $1", tenant_id
        )
        results = await retrieve(
            conn, tenant_id=tenant_id, query=message, provider=provider, reranker=reranker, top_k=5
        )

    yield _sse({"type": "conversation", "conversation_id": str(conversation_id)})

    relevant = [chunk for chunk in results if chunk.score > REFUSAL_SCORE_THRESHOLD]
    if not relevant:
        async with db.tenant_context(tenant_id, "customer") as conn:
            await conn.execute(
                "insert into messages (tenant_id, conversation_id, role, content) "
                "values ($1, $2, 'assistant', $3)",
                tenant_id,
                conversation_id,
                REFUSAL_MESSAGE,
            )
        yield _sse({"type": "refusal", "text": REFUSAL_MESSAGE})
        yield _sse({"type": "done"})
        return

    citations = [
        {"index": i + 1, "source": _citation_source(chunk), "snippet": chunk.content[:200]}
        for i, chunk in enumerate(relevant)
    ]
    yield _sse({"type": "citations", "citations": citations})

    system_prompt = _build_system_prompt(
        relevant,
        tenant_prompt=config_row["system_prompt"] if config_row else "",
        tone=config_row["tone"] if config_row else "",
    )
    messages: list[ChatMessage] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    full_text = ""
    async for delta in provider.chat_stream(messages):
        full_text += delta
        yield _sse({"type": "token", "text": delta})

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
