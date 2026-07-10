# PHASE 1 - Foundations (Week 1) - T-001..T-011

> **Read first:** `docs/INDEX.md` (router + hard rules), repo-root `AGENTS.md` (commands). Each ticket below lists the only other sections you need. Do not load the PRD or Architecture Doc.
> **Goal:** a business can sign up, be resolved by subdomain, be onboarded conversationally into a config, upload knowledge, and get grounded hybrid-RAG answers with real retrieval-eval numbers. RLS enforced from day one.
> **Stories covered:** US-001, US-002, US-003 (E0); US-010, US-011 (E1); US-020, US-021 (E2); US-030 partially (E3).
> Status markers: `[ ]` not started `[~]` in progress `[x]` done `[!]` blocked `[-]` deferred.

## Repository layout contract (all phases rely on these paths)

```
frontend/src/app/            App Router; route groups (customer)/ (tenant-admin)/ (platform)/; middleware.ts
frontend/src/components/ui/  shared components (frontend.md section 6)
frontend/src/styles/theme.css  the ONLY file with raw design values
frontend/src/lib/            api.ts, supabase.ts, money.ts, brand.ts
frontend/scripts/check-tokens.mjs  CI token guard
backend/app/main.py          FastAPI entry; /health
backend/app/core/            config.py, db.py (pool + tenant context), auth.py
backend/app/api/             route modules per feature
backend/app/ingestion/       chunker.py, embedder.py, pipeline.py
backend/app/retrieval/       dense.py, sparse.py, fuse.py, rerank.py, service.py
backend/app/agents/          (phase 2) graph, nodes
backend/app/pricing/         (phase 2) engine.py, validation_gate.py
backend/app/llm/             provider.py (abstraction), azure.py
backend/migrations/          NNNN_name.sql + runner (database.md section 9)
backend/seeds/               idempotent seed scripts (database.md section 10)
backend/evals/               datasets/ + eval scripts
backend/tests/               pytest
infra/                       Terraform (phase 4)
docker-compose.yml           local Postgres + pgvector
```

---

### T-001 `[x]` Monorepo scaffold
Done in phase 0 (planning/scaffolding session). `/frontend` (Next.js + TS + Tailwind + theme.css + token guard), `/backend` (FastAPI + uv, `/health`), `/infra` stub, docker-compose Postgres+pgvector, `.env.example`, README. Verified commands live in root `AGENTS.md` - trust that table.

---

### T-002 `[ ]` Full schema + migrations (4h)
**Deps:** T-001. **Stories:** US-001.
**Read:** `design/database.md` sections 1-2 and 9 fully; sections 3-7 as the DDL source; section 8 (triggers).
**Files:** `backend/migrations/0001..0008_*.sql`, `backend/app/core/migrate.py` (runner), `backend/tests/test_migrations.py`.
**Steps:**
1. Write the migration runner: reads `backend/migrations/*.sql` in filename order, records into `schema_migrations`, wraps each file in a transaction. CLI: `uv run python -m app.core.migrate`.
2. Write migrations 0001-0008 exactly per database.md section 9, copying DDL from sections 3-8 (tables, CHECKs, indexes, RLS enable+force, policies, grants, triggers).
3. Run against the docker-compose database from a clean volume; re-run to prove idempotence of the runner (already-applied files skipped).
**Accept:** clean DB -> `migrate` applies 0001-0008 without error; every table from database.md exists; `\d+` shows RLS enabled AND forced on every tenant table; `wren_app` role can CRUD, has no BYPASSRLS.
**Tests:** `test_migrations.py`: runs the runner against a fresh schema (pytest fixture DB), asserts `schema_migrations` count and a spot-check of tables/columns/checks (e.g. `quotes.total_cents` check constraint rejects a mismatched insert).

---

### T-003 `[ ]` RLS enforcement + schema audit (3h)
**Deps:** T-002. **Stories:** US-001, US-003.
**Read:** `design/database.md` sections 2 and 11.
**Files:** `backend/app/core/db.py`, `backend/tests/test_rls.py`, `backend/tests/test_schema_audit.py`.
**Steps:**
1. In `db.py`: asyncpg pool connecting as `wren_app`; `tenant_context(tenant_id, role)` async context manager that opens a transaction and runs the two `set_config` calls from database.md section 2.2.
2. Write the wrong-tenant check: insert rows for tenant A and B (as seeds within the test), then with context A query every tenant-scoped table and assert zero B rows; repeat with no context set and assert zero rows everywhere.
3. Write the schema audit test per database.md section 11 (pg_tables/pg_policies assertions + the `%_cents` integer rule).
**Accept:** both tests pass; deliberately dropping one policy in a scratch migration makes the audit fail (prove it, then remove the scratch).
**Tests:** `test_rls.py`, `test_schema_audit.py` - these run in CI forever.

---

### T-004 `[ ]` Supabase Auth + FastAPI tenant-context middleware (4h)
**Deps:** T-003. **Stories:** US-001.
**Read:** `design/database.md` sections 2-3 (roles, users, platform_admins).
**Files:** `backend/app/core/auth.py`, `backend/app/core/config.py`, `frontend/src/lib/supabase.ts`, `frontend/src/app/(tenant-admin)/login/page.tsx`, `.env.example` additions.
**Steps:**
1. Create the Supabase project (hosted, free tier); put URL + anon key + JWT secret in `.env.example` (names only) and local `.env`.
2. Frontend: Supabase email/password auth (signup + login pages using `Input`/`Button` from ui kit); session token attached to backend calls in `lib/api.ts`.
3. Backend `auth.py`: verify the Supabase JWT (HS256 with the JWT secret), extract `sub` (user id); dependency `require_tenant_admin` maps user id -> `users` row -> `tenant_id`, role `tenant_admin`; dependency `require_platform_admin` checks `platform_admins`. Signup endpoint `POST /api/tenants` creates tenants row + tenant_config defaults + users row (owner) in one transaction, service role context.
4. Every authed request runs inside `tenant_context(tenant_id, role)` (FastAPI dependency yields the connection).
**Accept:** signup from the frontend creates tenant + config + owner user; an authed request sees only its tenant's rows; a token for tenant A can never read tenant B (extend `test_rls.py` with an API-level case).
**Tests:** API-level auth tests with two signed-up tenants (httpx AsyncClient against the app, test Supabase JWTs minted with the secret).

---

### T-005 `[ ]` Tenant resolution by subdomain (4h)
**Deps:** T-004. **Stories:** US-002.
**Read:** `design/database.md` section 3 (`resolve_tenant_slug`); `design/frontend.md` section 7 (route groups).
**Files:** `frontend/src/middleware.ts`, `frontend/src/lib/tenant.ts`, `backend/app/api/public.py`.
**Steps:**
1. Next.js middleware: parse `host`; map `admin.*` -> `(platform)`, `app.*` -> `(tenant-admin)`, `{slug}.*` -> `(customer)` with the slug in a request header/rewrite param. Local dev: `{slug}.localhost:3000` plus an `X-Wren-Slug` header override for tests; production-ready for a Vercel wildcard domain. **Delete the phase-0 placeholder `src/app/page.tsx` when `(customer)/page.tsx` lands** - route groups do not segment URLs, so both would resolve to `/` and break the build.
2. Backend `GET /api/public/tenant/{slug}` -> `resolve_tenant_slug` (id, name, status, brand from tenant_config); 404 unknown, 200-with-status for suspended (frontend shows the suspended state, frontend.md 7.1).
3. Customer-surface API calls carry the slug; backend resolves and sets `tenant_context(tenant_id, 'customer')` per request. Resolution result cached in-process for 60s.
**Accept:** `bytefix.localhost:3000` renders Tenant 1's branded shell; unknown slug shows the calm 404; suspended shows the unavailable state; resolved requests are RLS-scoped (leakage case added to API tests).
**Tests:** middleware unit tests (host -> surface mapping), API tests for resolve (found/unknown/suspended).

---

### T-006 `[ ]` Conversational onboarding skeleton - Surface-2 Copilot (5h)
**Deps:** T-005. **Stories:** US-010, US-011.
**Read:** `design/frontend.md` sections 6-7.2 (chat components, Onboarding page); `design/database.md` sections 3, 5 (tenant_config, catalog_items, pricing_rules); frozen `Wren_P3_ArchitectureDoc.md` section 6 ONLY if the flow's intent is unclear.
**Files:** `backend/app/api/onboarding.py`, `backend/app/onboarding/flow.py`, `frontend/src/app/(tenant-admin)/onboarding/page.tsx`.
**Steps:**
1. `flow.py`: a guided state machine (explicit ordered stages: identity -> tone -> services/products -> pricing rules -> escalation threshold -> knowledge prompt -> confirm), NOT an open-ended interviewer. Each stage: one LLM call (via `app/llm/provider.py`) that extracts structured values from the admin's free-text answer into the stage's pydantic model; deterministic stage advance. Domain-agnostic prompts - generic wording only ("What do you offer? List services or products with rough prices if you have them").
2. Persist progress in `tenant_config.config['onboarding']` (stage, captured draft) so the flow resumes.
3. On confirm: write tenant_config fields, bulk-insert captured `catalog_items` and `pricing_rules` (amounts converted to integer cents server-side - the admin's "$120" becomes 12000 at parse time, never stored as text), mark tenant live.
4. Frontend page per frontend.md 7.2: chat pane + live captured-summary panel + confirm step.
**Accept:** a fresh tenant completes the interview and lands with populated tenant_config/catalog_items/pricing_rules; refresh mid-flow resumes; the same flow works for two structurally different fake businesses (manually try a service business and a goods business - wording must never assume either).
**Tests:** flow unit tests with canned LLM extractions (provider stubbed): stage advance, resume, cents conversion, confirm writes.

---

### T-007 `[ ]` Knowledge upload (3h)
**Deps:** T-006. **Stories:** US-011, US-020.
**Read:** `design/database.md` section 4 (documents); `design/frontend.md` section 6 (FileDropzone) + 7.2 (Knowledge page).
**Files:** `backend/app/api/knowledge.py`, `frontend/src/app/(tenant-admin)/knowledge/page.tsx`.
**Steps:** `POST /api/knowledge/upload` (multipart; .md .txt .pdf .csv .json; 10MB cap) -> store raw file (local `var/uploads/{tenant_id}/` at core scope; path from config) -> insert documents row status `pending`, `doc_type` from the user's selection. `GET /api/knowledge` lists documents. Frontend: Dropzone + documents Table with status badges, failed-row error + retry, real empty state.
**Accept:** uploads land as pending rows scoped to the tenant; wrong type/size rejected with a clear inline reason; the page matches frontend.md 7.2 states.
**Tests:** API tests for accept/reject paths and tenant scoping.

---

### T-008 `[ ]` Chunk + embed pipeline (4h)
**Deps:** T-007. **Stories:** US-020.
**Read:** `design/database.md` section 4 (knowledge_chunks); frozen Architecture Doc section 10 only if pipeline intent is unclear.
**Files:** `backend/app/ingestion/chunker.py`, `embedder.py`, `pipeline.py`, `backend/app/llm/provider.py` (+ `azure.py`).
**Steps:**
1. `provider.py`: thin abstraction - `chat(messages, tools?) -> ...`, `embed(texts) -> list[vector]`; model names from env config, never literals at call sites. `azure.py` implements it (Azure OpenAI; `text-embedding-3-small`, 1536 dims).
2. Chunker: prose (.md/.txt/.pdf via pypdf) -> heading-aware splits, target ~400 tokens, 15% overlap; structured (.csv/.json rows and catalog_items) -> one chunk per record with a rendered text form, `metadata.kind='catalog_item'` linking the item id.
3. Pipeline: pending document -> processing -> chunks inserted (batch embeds of 64) -> ready; failure -> failed + error text. Triggered on upload, re-runnable. Also ingests catalog_items as chunks when onboarding confirms (call it from T-006's confirm).
4. Add a `documents` "reprocess" endpoint for the retry button.
**Accept:** uploading Tenant 1's seed docs produces tenant-scoped chunks with embeddings + populated tsv; failed parse marks failed with a readable error; re-processing is idempotent (old chunks for the document replaced).
**Tests:** chunker unit tests (prose boundaries, structured records); pipeline test with a stub embedder.

---

### T-009 `[ ]` Hybrid retrieval: dense + sparse + RRF + rerank (5h)
**Deps:** T-008. **Stories:** US-021.
**Read:** `design/database.md` section 4 (query shapes, index notes).
**Files:** `backend/app/retrieval/dense.py`, `sparse.py`, `fuse.py`, `rerank.py`, `service.py`.
**Steps:**
1. Dense: embed query -> HNSW cosine top-20, `where tenant_id = :tid` explicit (plus RLS underneath).
2. Sparse: `websearch_to_tsquery` FTS top-20, same explicit scoping.
3. RRF fuse (k=60) -> candidates; cross-encoder rerank to top-k=5 (Cohere Rerank free tier via provider abstraction, or a local `cross-encoder/ms-marco-MiniLM-L-6-v2` fallback - pick via env; both behind `rerank.py`'s one interface).
4. `service.py`: `retrieve(tenant_id, query, k) -> [Chunk(content, metadata, score)]` - the single entry point everything (bare chat, agents, recommendation) uses.
**Accept:** for seeded Tenant 1, obvious queries return the right chunks; every stage independently swappable (interfaces, env-chosen impls); zero cross-tenant results with two tenants seeded (extend RLS API test).
**Tests:** retrieval integration test against seeded fixtures (a handful of hand-picked query -> expected-chunk cases as smoke; the real numbers come from T-010).

---

### T-010 `[ ]` [EDD] Golden retrieval set + eval script (5h)
**Deps:** T-008. **Stories:** US-030.
**Read:** `design/database.md` section 7 (eval_cases/eval_runs).
**Files:** `backend/evals/datasets/tenant1_retrieval.jsonl`, `backend/evals/retrieval_eval.py`.
**Steps:**
1. Author 40-60 retrieval cases against Tenant 1's seeded knowledge: query + relevant chunk identifiers (match on `metadata` source+chunk_index, stable across re-ingest). Cover: policy lookups, catalog facts, price-list facts, paraphrases, negatives (out-of-domain queries that should retrieve nothing relevant).
2. `retrieval_eval.py`: loads cases into `eval_cases` (idempotent), runs `service.retrieve` per case, computes recall@k (k=3,5), MRR, nDCG@5; writes an `eval_runs` row (run_type retrieval, git_sha) and prints a table. Exit non-zero below thresholds when `--gate` is passed (recall@5 >= 0.85).
**Accept:** the script runs end-to-end and reports real numbers; dataset committed; documented one-line "current numbers" note in the eval_runs row.
**Tests:** the eval script IS the test; add a tiny unit test for the metric functions (known-answer fixtures).
**Week-1 buffer rule:** if recall@5 << 0.85, fix retrieval (chunking, k, rerank) before starting T-011/phase 2 - that is the week's buffer purpose.

---

### T-011 `[ ]` Bare /chat: straight-line RAG with citations (3h)
**Deps:** T-009, T-010. **Stories:** US-021.
**Read:** `design/frontend.md` sections 6-7.1 (ChatBubble, StreamingText, CitationChip, customer surface states); `design/database.md` section 6 (conversations, messages).
**Files:** `backend/app/api/chat.py`, `frontend/src/app/(customer)/page.tsx` + chat components.
**Steps:**
1. `POST /api/chat` (slug-resolved tenant context): create/continue conversation, persist customer message, retrieve top-k, generate with a grounded prompt requiring inline citation markers keyed to retrieved chunks, stream via SSE, persist assistant message. No agents yet - one straight LLM call. Refuse-on-no-context: if retrieval returns nothing relevant, say so and suggest contacting the business (never invent).
2. Frontend: the Surface 3 screen per frontend.md 7.1 - branded header, bubbles, streaming, citations, empty-state greeting, error retry. This screen is reused as-is when agents replace the backend in phase 2.
**Accept:** end-to-end on `bytefix.localhost:3000`: ask a policy question, get a cited, streamed, grounded answer; conversation + messages persisted tenant-scoped; UI matches the spec's states (check each one manually).
**Tests:** API test with stubbed provider (citation markers present, refusal path); manual E2E pass through the real UI (per conventions section 5 spirit).

---

## Week 1 Definition of Done

- [ ] Signup -> subdomain resolution -> conversational onboarding writes config -> knowledge ingested -> hybrid retrieval returns grounded cited answers in the real UI.
- [ ] `test_rls.py` + `test_schema_audit.py` green; wrong-tenant returns zero rows through API paths too.
- [ ] Retrieval eval reports real numbers; recall@5 >= 0.85 or the gap is understood and being fixed before phase 2.
- [ ] No lint errors, no failing or flaky tests anywhere in the repo (conventions section 7).
- [ ] Durable discoveries recorded in `.agents/memory.md`.
