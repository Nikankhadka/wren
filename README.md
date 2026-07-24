# Wren

Wren is a multi-tenant SaaS: any small business - a dentist, a butcher, a phone repair shop, an online store - signs up, describes itself in a conversation, and gets its own private, branded AI support-and-sales agent at `{slug}.wren.app`. The agent answers questions from the business's own uploaded knowledge (with citations), recommends products, produces quotes, and hands off to a human when it should.

**Where the build is right now: see [`docs/PROGRESS.md`](docs/PROGRESS.md)** - one page listing every ticket, its status, its commit, and what that commit did in plain English.

## Architecture at a glance

One Next.js app serves three surfaces on three host patterns; one FastAPI
service runs the agents; one Postgres holds every tenant's data behind
row-level security. Vertical behavior lives entirely in configuration and
uploaded knowledge - never in code.

```
   SURFACE 1                 SURFACE 2                  SURFACE 3
   Platform owner            Tenant admin               Customer chat
   admin.wren.app            app.wren.app               {slug}.wren.app
   all-tenants view,         onboarding, knowledge,     streaming Q&A,
   provisioning              conversations + traces,    quotes, citations,
                             pricing, dashboards        human handoff
        \                         |                          /
         \________________________|_________________________/
                                  |
                    Next.js frontend (Vercel)
                    tokens-only theming, per-tenant branding
                                  |
                             HTTPS / bearer JWT
                                  |
                    FastAPI backend  (AWS ECS Fargate)
        +-------------------------------------------------------+
        |  Supervisor (LangGraph)                               |
        |    -> Knowledge  (hybrid RAG + citations)             |
        |    -> Recommendation (catalog, DB-sourced)            |
        |    -> Quoting    (selects; engine computes $)         |
        |    -> Order/Status (deterministic tool lookup)        |
        |    -> Escalation (terminal human handoff)             |
        |  Pricing engine (integer cents, no LLM math)          |
        |  Inspection gate (grounding/policy/injection/leak)    |
        +-------------------------------------------------------+
              |                    |                     |
        Supabase Postgres     LLM provider          Embedder / Reranker
        pgvector + RLS        (Azure / OpenAI-       (local by default,
        (tenant isolation)     compatible, swappable) hosted by config)
```

The three specialist safety properties - deterministic pricing, cross-tenant
isolation, and the inspection gate - are the parts to look at first; each has a
dedicated eval and a non-negotiable test. See the artifacts below.

## Artifacts (the portfolio evidence)

| Document | What it proves |
|---|---|
| [`docs/artifacts/eval-report.md`](docs/artifacts/eval-report.md) | Every quality number traced to its `eval_runs` row: retrieval, generation, injection, leakage, trajectory, with honest analysis of the free-tier misses |
| [`docs/artifacts/security.md`](docs/artifacts/security.md) | OWASP LLM Top 10 mapping, each control pointing at the code and the test that proves it; deliberate deferrals stated as decisions |
| [`docs/artifacts/generalization-proof.md`](docs/artifacts/generalization-proof.md) | A dental clinic brought live on identical code through the public API alone - the domain-agnostic hard rule, demonstrated |

**Demo walkthrough video:** _to be recorded_ (a 5-10 minute pass over the three
surfaces, a quote with trace drill-down, the generalization proof, and the eval
report) - the one release-criteria item that needs a person, not the codebase.

## How this repo is organized

```
frontend/   Next.js + TypeScript + Tailwind - one app serving all three surfaces
backend/    Python + FastAPI - agents, RAG, pricing engine, migrations, seeds, evals
infra/      Terraform (7-file AWS stack: VPC, ALB, ECR, ECS Fargate, IAM, Secrets Manager)
docs/       All documentation - see the guide below
.agents/    Working files for AI coding agents (file map, session memory)
```

See [`.agents/map.md`](.agents/map.md) for the full generated file tree.

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

## What was deliberately deferred (and why)

The 30-day core delivers one polished end-to-end path (Tenant 1 across all three
surfaces, plus the Tenant 2 config-only proof). Everything below was a
considered decision, not an omission - each is written up as "considered, out of
scope, and why" per the project's own rule.

| Deferred | Why |
|---|---|
| Subscriptions / billing automation | Phase 2. The platform-owner surface proves the SaaS shape without a billing product eating the clock. |
| SMS / voice / email channels | Phase 2. The chat surface already proves the agent; extra channels are integration volume, low incremental AI signal. |
| Custom domains (vs subdomains) | Phase 2. Subdomains prove private-per-tenant access; custom domains are DNS/cert plumbing. |
| Open-ended "magic" onboarding interviewer | Guided-conversational onboarding proves the concept; a fully open interviewer that reliably configures any business is itself a hard agent-research problem. |
| Fine-tuning, SSO / SOC2 certs, multi-language | Poor time-to-signal for a solo 30-day portfolio core; documented as deliberate. |

The security-specific deferrals (guardrails framework, formal red team,
automated dependency scanning) are in [`docs/artifacts/security.md`](docs/artifacts/security.md),
each stated as a decision with when it would matter.
