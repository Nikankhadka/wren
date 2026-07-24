# Wren Backend

Python 3.12 + FastAPI + uv. Runs the LangGraph agent graph, hybrid RAG, deterministic pricing engine, DB migrations, seeds, and eval suite.

Package layout (`app/`):

- `agents/` - LangGraph supervisor + five specialist agents (knowledge, recommendation, quoting, order_status, escalation) plus inspection gate
- `api/` - FastAPI routers: chat, onboarding, tenants, platform, dashboards, escalations, knowledge
- `core/` - config, DB pool + tenancy context, auth (Supabase JWT), forward-only migrate runner, step/token/cost limits
- `llm/` - provider abstraction (`LLMProvider`, `Embedder`, `Reranker`) with `openai_compat` and Azure backends
- `pricing/` - deterministic engine (integer cents) + validation gate
- `retrieval/` - hybrid RAG: dense (pgvector) + sparse (FTS) + rerank
- `observability/` - cost accounting + tracing (Langfuse-ready)

## Conventions

See [`../AGENTS.md`](../AGENTS.md) at the repo root for the stack, hard rules (deterministic pricing, domain-agnostic), and verified commands.

## Running

```bash
# From repo root:
make dev-backend     # backend dev server only (:8000)
make dev             # backend + frontend concurrently
make install-backend # uv sync
make migrate         # apply forward-only migrations
make seed            # seed full demo world
make lint-backend    # ruff check
make format          # ruff format (writes changes)
make typecheck-backend # mypy strict
make test-backend    # pytest
make eval            # eval gate
```

See `../docs/DEMO.md` for the full demo walkthrough and `../Makefile` for all targets.
