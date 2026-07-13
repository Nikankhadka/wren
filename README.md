# Wren

Wren is a multi-tenant SaaS: any small business - a dentist, a butcher, a phone repair shop, an online store - signs up, describes itself in a conversation, and gets its own private, branded AI support-and-sales agent at `{slug}.wren.app`. The agent answers questions from the business's own uploaded knowledge (with citations), recommends products, produces quotes, and hands off to a human when it should.

**Where the build is right now: see [`docs/PROGRESS.md`](docs/PROGRESS.md)** - one page listing every ticket, its status, its commit, and what that commit did in plain English.

## How this repo is organized

```
frontend/   Next.js + TypeScript + Tailwind - one app serving all three surfaces
            (platform owner, tenant admin, customer chat). All colors/spacing
            live as design tokens in src/styles/theme.css (CI-enforced).
backend/    Python + FastAPI - the agents (LangGraph), search over uploaded
            knowledge (RAG), the deterministic pricing engine, DB migrations,
            seeds, and evals.
infra/      Terraform for AWS - empty until the deploy phase (ticket T-035).
docs/       All documentation - see the guide below.
.agents/    Working files for AI coding agents (file map, session memory,
            overnight-build instructions). Useful to skim, not required reading.
```

## How the docs work

The project was fully planned up front, then built ticket by ticket. The docs split into three layers, from "why" to "do this now":

| Read this... | ...to answer |
|---|---|
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Where is the build right now? What did each commit do? |
| [`docs/INDEX.md`](docs/INDEX.md) | Which docs do I need for the phase I'm working on? (the router - every work session starts here) |
| [`docs/conventions.md`](docs/conventions.md) | What rules bind all work here? (style, git, testing, the two hard rules) |
| [`docs/phases/`](docs/phases/) | What exactly do I build next? 40 tickets (T-001..T-040) in 4 weekly phase files, each with steps, files, and acceptance criteria |
| [`docs/design/`](docs/design/) | How is it designed? `database.md` (schema, security policies) and `frontend.md` (design system, components, screens) |
| [`docs/source/`](docs/source/) | Why was it planned this way? The original frozen planning docs: `product-requirements.md`, `architecture.md`, `sprint-plan.md`, `research.md`. Reference only - the layers above already distill them |

## How to follow progress

- **One ticket = one commit.** Commit messages start with the ticket number (`T-015: Recommendation Agent`), so `git log --oneline` reads as a build diary. Commit bodies explain what changed and why in plain language - `git show <hash>` for the full story.
- [`docs/PROGRESS.md`](docs/PROGRESS.md) is the same diary as a table, updated with every ticket commit.
- Inside each `docs/phases/` file, tickets carry status markers: `[ ]` not started, `[~]` in progress, `[x]` done, `[!]` blocked, `[-]` deferred.
- Decisions and gotchas discovered along the way are logged with dates in [`.agents/memory.md`](.agents/memory.md).

## Running it locally

Prerequisites: Node 22+, [uv](https://docs.astral.sh/uv/), Docker.

### One command (demo-ready)

```bash
./scripts/demo.sh
```

Starts a local GoTrue (Supabase Auth) + the database, fixes env files, runs
migrations and a seeded demo world (two tenants, three logins), and brings up
the backend + frontend. See [`docs/DEMO.md`](docs/DEMO.md) for the full
walkthrough, credentials, and troubleshooting.

### Manual

```bash
# database (Postgres + pgvector)
docker compose up -d db

# backend
cd backend
uv sync
uv run python -m app.core.migrate
uv run uvicorn app.main:app --reload          # http://localhost:8000/health

# frontend
cd frontend
npm install
npm run dev                                   # http://localhost:3000
```

Copy `.env.example` to `.env` and fill in values as tickets wire up each service (Supabase, Azure OpenAI, Langfuse). To seed the sample tenant: `cd backend && uv run python -m seeds.seed_tenant1_phoneshop`, then open http://bytefix.localhost:3000. For the full demo world (two tenants + auth users + conversations), run `./scripts/demo.sh` or `cd backend && uv run python -m seeds.seed_demo` (needs local GoTrue - see docs/DEMO.md).

The verified build/lint/test commands live in [`AGENTS.md`](AGENTS.md).

## The two rules everything else bends around

1. **Deterministic pricing:** no language model ever produces a monetary amount. Agents only *select* pricing rules, items, and quantities; a pure pricing engine computes all totals in integer cents, and a validation gate rejects anything else.
2. **Domain-agnostic:** one codebase, zero vertical-specific branches. A dentist and a phone shop run identical code and differ only in configuration and uploaded knowledge.

Full text: [`docs/conventions.md`](docs/conventions.md), sections 8 and 9.
