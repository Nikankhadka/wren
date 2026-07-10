<!-- GENERATED 2026-07-11 by /init-project - do not hand-edit -->

# Wren - File Map

Phase 1 in progress: T-001 (scaffold), T-002 (schema migrations), T-003 (RLS enforcement + schema audit), and T-004 (Supabase auth + tenant provisioning) are done. Remaining phase-1 tickets (onboarding, RAG, etc.) tracked in `docs/phases/phase-1-foundations.md`.

```
wren/
├── AGENTS.md                     - project instructions: stack, verified commands, conventions pointers
├── CLAUDE.md                     - symlink to AGENTS.md (Claude Code entry point)
├── README.md                     - what Wren is, layout, quickstart
├── docker-compose.yml            - local Postgres + pgvector (service: db)
├── .env.example                  - env template (DB, Supabase, Azure OpenAI, Langfuse)
├── .agents/
│   ├── map.md                    - this file (regenerate via /init-project --refresh)
│   ├── memory.md                 - session-learned decisions, gotchas, conventions
│   ├── gnhf-objective.md         - overnight-run objective for the gnhf autonomous loop (phases 1-4)
│   └── gnhf-handoff.md           - state carried between gnhf loop iterations
├── docs/
│   ├── INDEX.md                  - ALWAYS READ FIRST: phase router + doc precedence + hard rules
│   ├── design/
│   │   ├── database.md           - full schema DDL, RLS policies, indexes, migrations, seeds
│   │   └── frontend.md           - design tokens, theming, component library, surface specs
│   ├── phases/
│   │   ├── phase-1-foundations.md      - T-001..T-011 (tenancy, RLS, onboarding, RAG) + repo layout contract
│   │   ├── phase-2-agents-pricing.md   - T-012..T-022 (agent graph, pricing engine, inspection, leakage)
│   │   ├── phase-3-eval-console.md     - T-023..T-031 (eval suite, CI gate, observability, console)
│   │   └── phase-4-ship.md             - T-032..T-040 (surfaces, deploy, generalization proof, artifacts)
│   ├── Wren_AGENTS.md            - binding conventions v2.0 (hard rules: deterministic pricing, domain-agnostic)
│   ├── Wren_P0P1_CharterAndPRD.md      - frozen source: scope, personas, user stories
│   ├── Wren_P3_ArchitectureDoc.md      - frozen source: system design
│   ├── Wren_P3_SprintPlanAndBacklog.md - frozen source: original backlog (superseded by phases/)
│   └── Wren_Research_CloningAndLearningPlan.md - frozen source: market grounding (background)
├── frontend/                     - Next.js 16 + TS + Tailwind v4 (npm)
│   ├── AGENTS.md                 - Next.js-specific agent rules (bootstrapped by create-next-app)
│   ├── README.md                 - create-next-app boilerplate readme
│   ├── src/app/                  - App Router: layout.tsx, page.tsx, globals.css (token->Tailwind mapping)
│   │   └── (tenant-admin)/       - tenant-admin route group (T-004 auth screens)
│   │       ├── login/page.tsx    - tenant-admin login screen (Supabase sign-in + redirect)
│   │       └── signup/page.tsx   - tenant self-onboarding signup screen (calls POST /api/tenants)
│   ├── src/components/ui/        - shared presentational primitives
│   │   ├── Button.tsx            - variant/size button primitive (primary/secondary/ghost/destructive)
│   │   └── Input.tsx              - labeled input primitive (useId for label/input association)
│   ├── src/lib/
│   │   ├── api.ts                 - typed fetch wrapper for the FastAPI backend (attaches Supabase access token)
│   │   └── supabase.ts            - lazy-singleton browser Supabase client
│   ├── src/styles/theme.css      - THE design-token source; only file allowed raw color values
│   └── scripts/check-tokens.mjs  - CI guard: fails on color literals outside theme.css
├── backend/                      - FastAPI, Python 3.12, uv
│   ├── app/main.py               - FastAPI entry: /health + mounts the tenants/platform routers
│   ├── app/core/
│   │   ├── config.py             - Settings (env-sourced runtime config, pydantic-settings)
│   │   ├── db.py                 - wren_app pool + tenant_context (sets app.tenant_id/app.role for RLS)
│   │   ├── auth.py               - T-004: Supabase JWT verification, AuthedTenantAdmin/AuthedPlatformAdmin deps
│   │   └── migrate.py            - forward-only migration runner (applies migrations/*.sql, tracks schema_migrations)
│   ├── app/api/
│   │   ├── tenants.py            - T-004: POST /api/tenants signup (service-role provisioning) + tenant-admin "me" probe
│   │   └── platform.py           - T-004: platform-admin probe endpoint (GET /api/platform/ping)
│   ├── migrations/               - forward-only SQL, applied in filename order by app/core/migrate.py
│   │   ├── 0001_extensions.sql   - pgvector extension + tenant-context helper functions
│   │   ├── 0002_roles.sql        - wren_app / service DB roles (password substituted from env)
│   │   ├── 0003_tenancy.sql      - tenants, tenant_config, users, platform_admins (+ RLS, slug resolver)
│   │   ├── 0004_knowledge.sql    - documents, knowledge_chunks (+ RLS, HNSW/GIN indexes)
│   │   ├── 0005_conversations.sql - conversations, messages, tool_calls (+ RLS)
│   │   ├── 0006_commerce.sql     - catalog_items, pricing_rules, quotes (+ RLS, integer-cents pricing)
│   │   ├── 0007_operations.sql   - orders, escalations (+ RLS, domain-agnostic shapes)
│   │   ├── 0008_eval_cost.sql    - eval_cases, eval_runs, cost_logs (+ RLS)
│   │   └── 0009_auth_lookup.sql  - T-004: pre-context user/platform-admin lookup resolvers for auth.py
│   ├── tests/
│   │   ├── __init__.py           - package marker
│   │   ├── conftest.py           - shared fixtures (wren_test DB session setup, wren_app-role DSN helper)
│   │   ├── test_health.py        - health endpoint test
│   │   ├── test_migrate_render.py - unit tests for the migration runner's placeholder substitution
│   │   ├── test_migrations.py    - T-002: runner applies 0001-0009 to a fresh DB, idempotently
│   │   ├── test_schema_audit.py  - T-003: every tenant-scoped table has RLS enabled+forced with a policy
│   │   ├── test_rls.py           - T-003: two-tenant leakage test, proves isolation as unprivileged wren_app
│   │   └── test_auth_api.py      - T-004: Supabase auth + tenant-context middleware, exercised via ASGITransport
│   └── pyproject.toml            - deps + ruff + mypy + pytest config
└── infra/main.tf                 - Terraform stub (populated by T-035)
```
