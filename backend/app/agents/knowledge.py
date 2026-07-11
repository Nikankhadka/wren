"""The Knowledge specialist - T-011's straight RAG logic, moved here so the
graph (T-012) is what /api/chat actually invokes. Behavior is unchanged from
T-011: refuse deterministically on no relevant context (the model never gets
a chance to invent an answer from nothing), otherwise stream a cited answer.

Opens its own short-lived ``tenant_context`` for retrieval only - never for
the generation call - so a slow LLM stream never holds a pooled connection
(same rule T-011 established, still true now that this runs as a graph node).
"""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer
from langgraph.runtime import get_runtime

from app.agents.state import AgentState, GraphContext
from app.core import db
from app.llm.provider import ChatMessage
from app.retrieval.service import retrieve
from app.retrieval.types import RetrievedChunk

REFUSAL_SCORE_THRESHOLD = 0.0
REFUSAL_MESSAGE = (
    "I don't have information about that. Please contact the business directly for help."
)


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


async def run(state: AgentState) -> dict[str, Any]:
    runtime = get_runtime(GraphContext)
    ctx = runtime.context
    writer = get_stream_writer()
    query = state["messages"][-1]["content"]

    async with db.tenant_context(ctx.tenant_id, "customer") as conn:
        config_row = await conn.fetchrow(
            "select system_prompt, tone from tenant_config where tenant_id = $1", ctx.tenant_id
        )
        results = await retrieve(
            conn,
            tenant_id=ctx.tenant_id,
            query=query,
            embedder=ctx.embedder,
            reranker=ctx.reranker,
            top_k=5,
        )

    relevant = [chunk for chunk in results if chunk.score > REFUSAL_SCORE_THRESHOLD]
    if not relevant:
        writer({"type": "refusal", "text": REFUSAL_MESSAGE})
        return {"draft_response": REFUSAL_MESSAGE, "retrieved_chunks": []}

    citations = [
        {"index": i + 1, "source": _citation_source(chunk), "snippet": chunk.content[:200]}
        for i, chunk in enumerate(relevant)
    ]
    writer({"type": "citations", "citations": citations})

    system_prompt = _build_system_prompt(
        relevant,
        tenant_prompt=config_row["system_prompt"] if config_row else "",
        tone=config_row["tone"] if config_row else "",
    )
    messages: list[ChatMessage] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    full_text = ""
    async for delta in ctx.provider.chat_stream(messages):
        full_text += delta
        writer({"type": "token", "text": delta})

    return {
        "draft_response": full_text,
        "retrieved_chunks": [
            {"id": str(chunk.id), "content": chunk.content, "metadata": chunk.metadata}
            for chunk in relevant
        ],
    }
