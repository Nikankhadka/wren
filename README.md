# Wren -> Agencx

This repo is **Agencx**: a multi-tenant SaaS where any small business - a
dentist, a butcher, a phone repair shop, an online store - signs up, describes
itself in a conversation, and gets its own private, branded support-and-sales
agent at `agencx.app/{slug}`. The agent answers questions from the business's
own uploaded knowledge (with citations), hands off to a human when it should,
and can recommend, quote, and track orders when the owner turns those on. The
codebase and its roles keep the `wren` names it was built with (standing names
note in [`docs/agencx/README.md`](docs/agencx/README.md)); the product is
Agencx on every user-facing surface.

**Where the build is right now: see [`docs/agencx/progress.md`](docs/agencx/progress.md)** - one page marking every feature BUILT (with commit evidence), CHANGING, or NEW, plus the status of every Agencx ticket.

## Architecture at a glance

One Next.js app serves three surfaces on one origin, split by path; one FastAPI
service runs the agents; one Postgres holds every tenant's data behind
row-level security. Vertical behavior lives entirely in configuration and
uploaded knowledge - never in code.

```
   SURFACE 1                 SURFACE 2                  SURFACE 3
   Platform owner            Tenant admin               Customer chat
   agencx.app/admin          agencx.app/login           agencx.app/{slug}
   all-tenants view,         onboarding, knowledge,     streaming Q&A,
   tenant listing, metrics,  conversations + traces,    quotes, citations,
   status controls           knowledge + citations      human handoff
        \                         |                          /
         \________________________|_________________________/
                                  |
                    Next.js frontend (Vercel container service)
                    tokens-only theming, per-tenant name/logo
                                  |
                        same-origin /api/* rewrite
                                  |
                    FastAPI backend (Vercel container service)
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
| [`docs/archive/artifacts/eval-report.md`](docs/archive/artifacts/eval-report.md) | Every quality number traced to its `eval_runs` row: retrieval, generation, injection, leakage, trajectory, with honest analysis of the free-tier misses |
| [`docs/archive/artifacts/security.md`](docs/archive/artifacts/security.md) | OWASP LLM Top 10 mapping, each control pointing at the code and the test that proves it; deliberate deferrals stated as decisions |
| [`docs/archive/artifacts/generalization-proof.md`](docs/archive/artifacts/generalization-proof.md) | A dental clinic brought live on identical code through the public API alone - the domain-agnostic hard rule, demonstrated |

## How this repo is organized

```
frontend/   Next.js + TypeScript + Tailwind - one app serving all three surfaces
backend/    Python + FastAPI - agents, RAG, pricing engine, migrations, seeds, evals
infra/      Terraform (7-file AWS stack, dormant since B-4 - kept as evidence, deployed by nothing)
docs/       All documentation - see the guide below
.agents/    Working files for AI coding agents (file map, session memory)
```

See [`.agents/map.md`](.agents/map.md) for the full generated file tree.

## How the docs work

The canonical set lives in `docs/agencx/`; everything pre-Agencx is archived in `docs/archive/` (indexed there) and is reference-only.

| Read this... | ...to answer |
|---|---|
| [`docs/agencx/progress.md`](docs/agencx/progress.md) | Where is the build right now? What is built, changing, or new? |
| [`docs/agencx/prd.md`](docs/agencx/prd.md) | What is Agencx? Why, who, what is in Stage 1 scope, and what signals decide next steps? |
| [`docs/agencx/architecture.md`](docs/agencx/architecture.md) | How does it work? Invariants, agent flow, providers, latency budget, eval gates |
| [`docs/agencx/design/api-contract.md`](docs/agencx/design/api-contract.md) | What JSON and SSE errors and success responses look like |
| [`docs/agencx/design/`](docs/agencx/design/) | How is it designed? `database.md`, `frontend.md`, `decisions.md` (the decision ledger + ADRs) |
| [`docs/agencx/spec/active/`](docs/agencx/spec/active/) | What work remains? Open and deferred tickets |
| [`docs/agencx/spec/completed/`](docs/agencx/spec/completed/) | What was delivered? Completed phase records |
| [`docs/agencx/design/conventions.md`](docs/agencx/design/conventions.md) | What rules bind all work here? (style, git, testing, the two hard rules) |
| [`docs/archive/`](docs/archive/) | What came before? The pre-Agencx planning and design docs, kept for provenance |

## How to follow progress

- **One ticket = one commit.** Commit messages start with the ticket number (`T-015: Recommendation Agent`, or the Agencx ids like `P-2: ...`), so `git log --oneline` reads as a build diary. Commit bodies explain what changed and why in plain language - `git show <hash>` for the full story.
- [`docs/agencx/progress.md`](docs/agencx/progress.md) is the same diary as a table, updated with every ticket commit.
- Decisions and gotchas discovered along the way are logged with dates in [`.agents/memory.md`](.agents/memory.md).

## Running it locally

Prerequisite: Docker. Everything else (Node, Python, uv, Postgres, GoTrue,
Mailpit) runs inside containers - the host installs nothing.

### One command (demo-ready)

```bash
make demo
```

Starts the whole stack as compose services (database + GoTrue auth + auth-proxy
+ backend + frontend), fixes env files, runs migrations and a seeded demo world
(two tenants, three logins). `make stop` brings it down; `make dev` restarts it
without reseeding.

### Manual (step by step)

```bash
make install    # deps into their container volumes
make services   # Postgres + pgvector, GoTrue, auth-proxy
make migrate    # apply schema
make seed       # full demo world (two tenants + auth users)
make dev        # backend :8000 + frontend :3000 as containers
```

`make services` alone is not enough to log in for fresh seeds - `make seed`
needs GoTrue, which `services` starts. Open http://localhost:3000/bytefix after
seeding, or http://localhost:3000/login for the tenant console.

Config lives in `backend/.env` (created from the repo-root `.env.example` by
`scripts/dev.sh`) and `frontend/.env.local`. Live reload works: edit source on
the host, the containers pick it up.

**Full walkthrough - logins, which command needs which service, and
troubleshooting: [`docs/agencx/running.md`](docs/agencx/running.md).** See
[`AGENTS.md`](AGENTS.md) for the complete command reference.

## The two rules everything else bends around

1. **Deterministic pricing:** no language model ever produces a monetary amount. Agents only *select* pricing rules, items, and quantities; a pure pricing engine computes all totals in integer cents, and a validation gate rejects anything else.
2. **Domain-agnostic:** one codebase, zero vertical-specific branches. A dentist and a phone shop run identical code and differ only in configuration and uploaded knowledge.

Full text: [`docs/agencx/design/conventions.md`](docs/agencx/design/conventions.md), sections 8 and 9.

## What was deliberately deferred (and why)

The 30-day core delivers one polished end-to-end path (Tenant 1 across all three
surfaces, plus the Tenant 2 config-only proof). Everything below was a
considered decision, not an omission - each is written up as "considered, out of
scope, and why" per the project's own rule.

| Deferred | Why |
|---|---|
| Subscriptions / billing automation | Phase 2. The platform-owner surface proves the SaaS shape without a billing product eating the clock. |
| SMS / voice / email channels | Phase 2. The chat surface already proves the agent; extra channels are integration volume, low incremental AI signal. |
| Per-tenant custom domains | Phase 2. A tenant is a path on one origin (D22), which is what makes the link work with no DNS step; a business bringing its own domain is DNS/cert plumbing on top. |
| Open-ended "magic" onboarding interviewer | Guided-conversational onboarding proves the concept; a fully open interviewer that reliably configures any business is itself a hard agent-research problem. |
| Fine-tuning, SSO / SOC2 certs, multi-language | Poor time-to-signal for a solo 30-day portfolio core; documented as deliberate. |

The security-specific deferrals (guardrails framework, formal red team,
automated dependency scanning) are in [`docs/archive/artifacts/security.md`](docs/archive/artifacts/security.md),
each stated as a decision with when it would matter.
