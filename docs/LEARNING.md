# Learning Wren

**This is a guided tour + glossary for someone reading the codebase for the first time.** It walks you through how the system works, what each piece does, and where to find it in the source.

This is NOT a retrospective on what building the project taught. That is [`../LEARNINGS.md`](../LEARNINGS.md) (written for an external reviewer). These two files cross-reference but serve different readers - this one teaches the system, that one reflects on building it.

---

## 1. Start here

Wren is a domain-agnostic, multi-tenant SaaS: any small business (dentist, butcher, phone repair shop) self-onboards through a conversation and gets its own private, branded AI support-and-sales agent at `{slug}.wren.app`. The agent answers questions from the business's own uploaded knowledge, recommends products, produces quotes (with deterministic pricing - no LLM ever invents a dollar amount), and hands off to a human when it should.

Three surfaces, one codebase:

- **Customer chat** at `{slug}.wren.app` - streaming Q&A with citations, product recommendations, quotes, order status lookups, human handoff
- **Tenant admin** at `app.wren.app` - onboarding, knowledge upload, conversations (with traces), pricing editor, dashboards
- **Platform owner** at `admin.wren.app` - all-tenants view, provisioning, suspend/reactivate

The one command to see it running: `make demo`. This starts a local GoTrue (Supabase Auth), the database, seeds two demo tenants, and brings up both dev servers. See [`docs/DEMO.md`](DEMO.md) for the full walkthrough, credentials, and troubleshooting.

---

## 2. Glossary

| Term | What it means | Where to find it |
|---|---|---|
| `T-XXX` | A ticket number (T-001 through T-040). One ticket = one commit; `git log --oneline` reads as a build diary. | `docs/phases/` (40 tickets in 4 phase files) |
| MoSCoW | Must / Should / Could / Won't - the prioritisation scheme used in planning | `docs/source/sprint-plan.md` |
| E-story | User story codes (E0 through E14) from the PRD | `docs/source/product-requirements.md` |
| RLS | Row-Level Security - Postgres feature ensuring one tenant can never read another's data. Every tenant-scoped table has it enforced. | `docs/design/database.md`, `backend/migrations/0003_tenancy.sql` |
| RRF | Reciprocal Rank Fusion - the algorithm that merges dense (vector) and sparse (keyword) retrieval results into one ranked list | `backend/app/retrieval/fuse.py` |
| Fable review | An automated code review pass the agent ran against its own work; findings were fixed and regression-tested | See commit history for T-019..T-032 entries mentioning "Fable review finding" |
| LuxeStay | The code name for the Material 3 visual rebrand (commits `cc30fc5`/`86b03d9`/`5d2bb7d`) - crimson primary, Inter font, bento cards. Not a business vertical | `frontend/src/styles/theme.css` |
| contextvars / tenant_context | Python's `contextvars` (task-local storage) used to set the current tenant + role on every asyncpg connection, so RLS policies filter automatically | `backend/app/core/db.py` |
| Hybrid RAG | Retrieval combining three layers: dense (pgvector cosine search), sparse (Postgres full-text search), and cross-encoder rerank (local or Cohere) | `backend/app/retrieval/{dense,sparse,rerank}.py` |

---

## 3. How a request flows through the system

### Subdomain-to-tenant resolution

When a browser hits `bytefix.wren.app`:

1. **`frontend/src/proxy.ts`** reads the `Host` header, extracts the subdomain via `resolveHost()` in `lib/tenant.ts`, and determines which "surface" this is (customer / tenant-admin / platform / marketing). It rewrites the URL into the matching route group segment.
2. The frontend calls the backend API with the `wren-slug: bytefix` header.
3. **`backend/app/core/auth.py`** resolves the slug to a `tenant_id` via the `wren_resolver` role (the one sanctioned RLS bypass).
4. **`backend/app/core/db.py`** sets `tenant_context(tenant_id, role)` - a contextvar that tells asyncpg which tenant and role to scope queries under. From this point on, every SQL query is transparently filtered by Postgres RLS.

### The agent graph

The chat endpoint (`backend/app/api/chat.py`) creates a `GraphContext` (carrying the LLM provider, embedder, reranker, DB pool, and tenant id) and invokes the LangGraph agent graph.

**`backend/app/agents/graph.py`** - builds and compiles the graph. Flow: supervisor -> one of five specialists -> price_gate (if money is involved) -> inspection -> response.

**`backend/app/agents/supervisor.py`** - the router. One LLM call classifies the customer's intent. Returns a `RouteDecision {route, confidence, reason}`. If confidence is below the tenant's escalation threshold, the route is overridden to "escalation" - enforced in code, not left to the prompt.

**`backend/app/agents/knowledge.py`** - the Q&A specialist. Retrieves relevant chunks from the tenant's uploaded documents (hybrid RAG), builds a prompt from them, and streams a grounded answer with citations. If nothing relevant is found, responds with a polite refusal.

**`backend/app/agents/recommendation.py`** - the "what should I buy?" specialist. Retrieves only `metadata.kind='catalog_item'` chunks, then re-fetches each item's name, description, and price fresh from `catalog_items` - never trusting the chunk's embedded text for prices.

**`backend/app/agents/quoting.py`** - the "how much for X?" specialist. The model selects pricing rule codes and quantities (it never sees prices). The deterministic pricing engine computes the total. The model writes a prose explanation that references the quote card but states no dollar amounts.

**`backend/app/agents/order_status.py`** - the "where's my order?" specialist. Extracts a reference code from the customer's message (via LLM, since the format varies by business), then does a plain SQL lookup via `tools.py::lookup_order_or_ticket`. The response is a filled template - deterministic, no generation call.

**`backend/app/agents/escalation.py`** - the terminal handoff. Creates an `escalations` row, flips `conversations.status = 'escalated'`, and emits a handoff message. Once escalated, `/api/chat` short-circuits - no more AI calls ever happen in that conversation.

### Retrieval

**`backend/app/retrieval/service.py`** orchestrates three stages:

1. **Dense** (`dense.py`): pgvector cosine similarity over `knowledge_chunks.embedding`. Returns top-k by vector distance.
2. **Sparse** (`sparse.py`): PostgreSQL full-text search (`tsvector`/`tsquery`) over `knowledge_chunks.content`. Returns top-k by text relevance.
3. **Fuse** (`fuse.py`): Reciprocal Rank Fusion merges the two result sets.
4. **Rerank** (`rerank.py`): Cross-encoder (local `ms-marco-MiniLM` or Cohere API) rescored the fused candidates for final ordering. Both backends return normalized [0,1] relevance scores.

### The inspection layer

**`backend/app/agents/inspection.py`** - the final gate before the customer sees a response. One LLM call checks:

- **Grounding**: does every claim trace to retrieved business content? No invented facts.
- **Policy**: does the response match the business's tone?
- **Injection**: are there signs of prompt injection in the response?
- **Prompt leak**: did the model reveal its own instructions?

A failing response gets one rewrite; a second failure hands off to a human. Nothing streams to the customer until inspection passes.

**`backend/app/agents/price_gate.py`** - a deterministic (non-LLM) provenance check: every dollar figure in the response must trace to what the pricing engine actually computed. Unexplained figures trigger rewrite-then-escalate.

### Pricing

**`backend/app/pricing/engine.py`** - the deterministic quote calculator. A pure function: `compute_quote(tenant_id, selections)` -> `EngineQuote {line_items, subtotal_cents, tax_cents, total_cents}`. Reads active `pricing_rules` and `catalog_items` from the database. Unknown codes -> typed error. Integer math only - no float rounding anywhere near money.

**`backend/app/pricing/validation_gate.py`** - validates that computed line items match the selections, totals reconcile, and no model-authored figures exist.

### Observability

**`backend/app/observability/cost.py`** - contextvar-based per-turn usage sink. Every LLM call reports token counts; after the turn, cost is persisted to `cost_logs`. Concurrent turns never cross-contaminate.

**`backend/app/observability/tracing.py`** - Tracer/Turn/Span protocol. Every graph node opens a span (scalar-only attributes, never raw text). Default is NoOp; wiring real Langfuse is a founder step.

---

## 4. How the frontend is organized

The frontend is a single Next.js 16 app. Three surfaces are served from the same codebase using route groups:

```
src/app/
  (customer)/        customer chat at {slug}.*
  (tenant-admin)/    tenant console at app.*
  (platform)/        platform console at admin.*
  admin-surface/     proxy-rewritten platform (route groups can't segment URLs)
  marketing-surface/ proxy-rewritten marketing pages (apex/www host)
```

**`frontend/src/proxy.ts`** handles host-based routing. It reads the `Host` header, resolves which surface this is, and rewrites the URL into the matching segment.

**`frontend/src/styles/theme.css`** is the single source of truth for all visual values. It's a 3-layer token system:

- **Layer 1**: tonal role ramps (`--primary-*`, `--secondary-*`, `--tertiary-*`, `--error-*`, `--neutral-*`) - Material 3 tone steps
- **Layer 2**: semantic tokens (`--color-primary`, `--color-surface`, `--color-on-surface`) - mapped from Layer 1, different for light/dark
- **Layer 3**: utility classes consumed by Tailwind and components

Components reference ONLY semantic token names - never hardcoded colors. This is CI-enforced by **`frontend/scripts/check-tokens.mjs`**, which flags any hex color literal outside `theme.css`. This system proved itself during the LuxeStay rebrand: re-pointing Layer 2 tokens carried the entire visual change without touching component code.

**`frontend/src/lib/`**:
- `api.ts` - typed fetch wrapper, attaches Supabase JWT to requests
- `tenant.ts` - `resolveHost()` (maps subdomain -> surface + slug), `surfaceUrl()` (inverse: builds cross-surface links)
- `supabase.ts` - lazy-singleton browser Supabase client
- `brand.ts` - per-tenant runtime accent override with WCAG AA contrast gate

---

## 5. How the database is organized

Wren uses a single Postgres database (with pgvector) serving all tenants. Isolation is structural, not application-level:

- **Every tenant-scoped table has RLS enabled and forced.** Policies use `app_tenant_id()` (a Postgres function reading the session-level `app.tenant_id` setting) to filter every query to the current tenant.
- **The app connects as the `wren_app` role** (not the `postgres` superuser). `wren_app` holds no BYPASSRLS privilege and has scoped grants (SELECT/INSERT/UPDATE on tenant tables, no DELETE on quotes).
- **`wren_resolver`** is a separate role with column-level grants only - the single sanctioned RLS bypass for slug-to-tenant resolution.
- **Migrations are forward-only SQL** files in `backend/migrations/`, applied in filename order by `backend/app/core/migrate.py`.

For the full schema DDL, RLS policies, indexes, and the migration system, see [`docs/design/database.md`](design/database.md).

---

## 6. How testing and eval work

### Unit and integration tests

- **Backend**: pytest (`make test-backend`). Tests are in `backend/tests/`. Files matching the `app/` structure (e.g. `test_knowledge_agent.py` tests `app/agents/knowledge.py`). Tests marked `@pytest.mark.db` require a live Postgres; others use stubbed providers.
- **Frontend**: vitest (`make test-frontend`). Tests are co-located with source or in `frontend/src/__tests__/`.
- **E2E**: Playwright (`make test-e2e`). 6 specs in `frontend/e2e/` covering landing, marketing pages, customer chat, dashboards, and cross-tenant scenarios.

### The eval gate

The eval suite lives in `backend/evals/` and has two categories:

**Deterministic (absolute gates)** - must pass at 100%, never skipped:
- **Retrieval** (`retrieval_eval.py`): recall@k, MRR, nDCG against 50 hand-written golden cases
- **Leakage** (`leakage_eval.py`): cross-tenant probes in both directions (structural + full-conversation)
- **Quote provenance**: enforced by `price_gate.py`, validated by unit tests

**LLM-judged (regression gates)** - need a live LLM, gated on regression (>3% drop vs prior run):
- **Generation** (`generation_eval.py`): faithfulness, answer relevancy, citation faithfulness
- **Trajectory** (`trajectory_scorer.py`): tool-call correctness, step efficiency, cost tracking
- **Injection** (`injection_eval.py`): 29-case prompt-injection attack set
- **Judge calibration** (`judge_calibration.py`): blocked on founder hand-labeling

The orchestrator is `evals/run_gate.py` (`make eval`). CI runs the deterministic gate unconditionally and the LLM-judged gate only when an LLM_API_KEY secret is present (`ci.yml` `eval-gate` job).

---

## 7. How to run things

All commands from the repo root. For the raw command behind each target, see the Commands table in [`../AGENTS.md`](../AGENTS.md).

| Task | Command |
|---|---|
| Full demo (recommended first run) | `make demo` |
| Dev servers (both, for iterating) | `make dev` |
| Backend dev server only | `make dev-backend` |
| Frontend dev server only | `make dev-frontend` |
| Start database | `make db` |
| Apply migrations | `make migrate` |
| Seed demo data | `make seed` |
| Install dependencies | `make install` |
| Lint everything | `make lint` |
| Typecheck everything | `make typecheck` |
| Run all tests | `make test` |
| Run E2E tests | `make test-e2e` |
| Fast inner loop (lint + typecheck + test) | `make check` |
| Full CI locally | `make ci` |
| Run eval gate | `make eval` |
| Clean build artifacts | `make clean` |

Run `make help` for the complete list with descriptions.

---

## 8. Where to go deeper

- **Design docs**: `docs/design/database.md`, `docs/design/frontend.md`
- **Phase ticket files**: `docs/phases/phase-1-foundations.md` through `phase-4-ship.md` (40 tickets with steps, files, and acceptance criteria)
- **Portfolio artifacts**: `docs/artifacts/eval-report.md`, `docs/artifacts/security.md`, `docs/artifacts/generalization-proof.md`
- **Retrospective**: [`../LEARNINGS.md`](../LEARNINGS.md) - what building Wren taught, per subsystem
- **Historical decisions**: `docs/archive/decisions-log.md` - implementation decisions, bug postmortems, and design tradeoffs discovered during the build
