# Wren

A domain-agnostic, multi-tenant SaaS where any business - a dentist, a butcher, a phone repair shop, an online store - signs up, describes itself in a conversation, and gets its own private, branded AI support-and-sales agent at `{slug}.wren.app` that recommends, answers from the business's own knowledge, produces deterministic quotes, and escalates to a human when it should.

**Status: phase 0 (scaffold).** The full work-order documentation lives in [`docs/`](docs/INDEX.md) - start at `docs/INDEX.md`, which routes each build phase to exactly the documents it needs.

## Layout

```
frontend/   Next.js + TypeScript + Tailwind - one app serving all three surfaces
            (platform owner, tenant admin, customer chat), themed entirely by
            design tokens in src/styles/theme.css
backend/    Python + FastAPI - agents (LangGraph), hybrid RAG, deterministic
            pricing engine, eval harness
infra/      Terraform - AWS ECS Fargate backend (populated in phase 4)
docs/       PRD, architecture, design docs, phase-by-phase ticket files
```

## Quickstart (local)

Prerequisites: Node 22+, [uv](https://docs.astral.sh/uv/), Docker.

```bash
# database (Postgres + pgvector)
docker compose up -d db

# backend
cd backend
uv sync
uv run uvicorn app.main:app --reload          # http://localhost:8000/health

# frontend
cd frontend
npm install
npm run dev                                   # http://localhost:3000
```

Copy `.env.example` to `.env` and fill in values as tickets wire up each service (Supabase, Azure OpenAI, Langfuse).

## Commands

The verified command table lives in [`AGENTS.md`](AGENTS.md). Conventions - including the two hard rules (no model-authored prices, no vertical-specific code) - live in [`docs/Wren_AGENTS.md`](docs/Wren_AGENTS.md).

## The two invariants

1. **Deterministic pricing:** no language model ever produces a monetary amount. Agents select pricing rules and quantities; a pure pricing engine computes totals in integer cents, and a validation gate rejects anything else.
2. **Domain-agnostic:** one codebase, zero vertical branches. A dentist and a phone shop run identical code and differ only in configuration and uploaded knowledge.
