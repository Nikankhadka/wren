<!-- GENERATED 2026-07-24 by /init-project --refresh - do not hand-edit -->

# Wren - File Map

Phase 4 nearly complete: 37 of 40 tickets done (see `docs/PROGRESS.md`). Only T-036 (live AWS/Vercel deploy) and the demo-video recording remain - both founder-blocked, not code-blocked.

```
wren/
├── AGENTS.md                        - project instructions: stack, verified commands (make targets + raw), conventions pointers
├── CLAUDE.md                        - symlink to AGENTS.md (Claude Code entry point)
├── Makefile                         - central task runner (make help for the full list)
├── README.md                        - what Wren is, architecture diagram, artifacts, quickstart
├── docker-compose.yml               - local Postgres + pgvector (db), GoTrue auth, nginx auth-proxy
├── docker/
│   └── auth-proxy.conf              - nginx config stripping /auth/v1 prefix for local GoTrue
├── .env.example                     - env template (DB, Supabase, LLM provider, embedder, reranker, Langfuse)
├── scripts/
│   └── demo.sh                      - one-command demo bootstrap (GoTrue, DB, migrate, seed, dev servers)
├── .agents/
│   ├── map.md                       - this file (regenerate via /init-project --refresh)
│   ├── memory.md                    - session-learned decisions, gotchas, conventions
│   ├── gnhf-objective.md            - overnight-run objective for the gnhf autonomous loop
│   └── gnhf-handoff.md              - state carried between gnhf loop iterations (reset post T-037)
├── .github/
│   └── workflows/
│       ├── ci.yml                   - development gate: frontend + backend + infra + eval-gate on every push/PR
│       └── deploy.yml               - production pipeline (T-036 skeleton, dormant until AWS secrets exist)
├── docs/
│   ├── INDEX.md                     - ALWAYS READ FIRST: phase router + doc precedence + hard rules
│   ├── PROGRESS.md                  - every ticket, its status, its commit, and what it did (one-line each)
│   ├── conventions.md               - binding conventions v2.0 (hard rules: deterministic pricing, domain-agnostic)
│   ├── DEMO.md                      - scripted walkthrough, credentials, troubleshooting
│   ├── LEARNING.md                  - guided tour + glossary for learning how the system works (first-time readers)
│   ├── design/
│   │   ├── database.md              - full schema DDL, RLS policies, indexes, migrations, seeds
│   │   └── frontend.md              - design tokens, theming, component library, surface specs
│   ├── phases/
│   │   ├── phase-1-foundations.md   - T-001..T-011 (tenancy, RLS, onboarding, RAG) + repo layout contract
│   │   ├── phase-2-agents-pricing.md - T-012..T-022 (agent graph, pricing engine, inspection, leakage)
│   │   ├── phase-3-eval-console.md  - T-023..T-031 (eval suite, CI gate, observability, console)
│   │   └── phase-4-ship.md          - T-032..T-040 (surfaces, deploy, generalization proof, artifacts)
│   ├── artifacts/
│   │   ├── eval-report.md           - T-038: every quality number traced to its eval_runs row
│   │   ├── security.md              - T-039: OWASP LLM Top 10 mapping with code + test pointers
│   │   └── generalization-proof.md  - T-037: dental clinic live on identical code via public API alone
│   └── source/                      - frozen planning docs (rarely loaded; scope truth)
│       ├── product-requirements.md  - what we build and why: personas, user stories (E0-E14)
│       ├── architecture.md          - system design the working docs derive from
│       ├── sprint-plan.md           - original ticket list (superseded by phases/)
│       └── research.md              - market grounding (background only)
├── frontend/                        - Next.js 16 + React 19 + TypeScript 5 + Tailwind v4 (npm)
│   ├── AGENTS.md                    - Next.js-specific agent rules (create-next-app bootstrap)
│   ├── README.md                    - Wren-specific pointer (surfaces, tokens, make targets)
│   ├── package.json                 - scripts: dev, build, lint, typecheck, check:tokens, test (vitest), test:e2e (Playwright)
│   ├── src/
│   │   ├── proxy.ts                 - host-based routing: resolves {slug}.localhost -> tenant, routes surfaces
│   │   ├── app/
│   │   │   ├── layout.tsx           - root layout (Inter via next/font, theme + branding scripts)
│   │   │   ├── (customer)/          - customer chat surface at {slug}.* (streaming Q&A, QuoteCard, citations, escalation)
│   │   │   ├── (tenant-admin)/      - tenant console: login, signup, onboarding, knowledge, conversations, escalations, pricing, dashboards
│   │   │   ├── (platform)/          - platform-owner surface at admin.* (all-tenants, provision, suspend/reactivate)
│   │   │   ├── admin-surface/       - proxy-rewritten platform surface (route groups can't segment URLs)
│   │   │   └── marketing-surface/   - proxy-rewritten marketing landing + /product, /pricing, /demo, /about
│   │   ├── components/ui/           - shared primitives: Button, Input, Select, Table, EmptyState, Badge, MetricCard, Modal, Icon, etc.
│   │   ├── lib/
│   │   │   ├── api.ts               - typed fetch wrapper for the FastAPI backend (attaches Supabase JWT)
│   │   │   ├── tenant.ts            - resolveHost, surfaceUrl, tenant context
│   │   │   ├── supabase.ts          - lazy-singleton browser Supabase client
│   │   │   └── brand.ts             - per-tenant runtime accent override with WCAG AA contrast gate
│   │   └── styles/
│   │       └── theme.css            - THE design-token source (3-layer: tonal ramps -> semantic -> utility); CI-enforced
│   ├── scripts/
│   │   └── check-tokens.mjs         - CI guard: fails on color literals outside theme.css
│   └── e2e/                         - Playwright specs: landing, marketing-pages, chat, dashboards, cross-tenant
├── backend/                         - FastAPI, Python 3.12, uv
│   ├── .python-version              - 3.12 (pinned)
│   ├── pyproject.toml               - deps + ruff + mypy + pytest config; local-ml group (sentence-transformers, excluded from Docker)
│   ├── Dockerfile                   - multi-stage uv build (production image, --no-group local-ml)
│   ├── .dockerignore                - prevents baking .env secrets + macOS .venv into the image
│   ├── app/
│   │   ├── main.py                  - FastAPI entry: /health, CORS, mounts routers
│   │   ├── core/
│   │   │   ├── config.py            - pydantic-settings env config
│   │   │   ├── db.py                - wren_app pool + tenant_context (contextvar, sets app.tenant_id/app.role for RLS)
│   │   │   ├── auth.py              - Supabase JWT verification, AuthedTenantAdmin/AuthedPlatformAdmin dependencies
│   │   │   ├── migrate.py           - forward-only migration runner (applies migrations/*.sql, fail-closed substitution)
│   │   │   └── limits.py            - per-tenant cost/step caps + timeouts (graceful degradation)
│   │   ├── api/
│   │   │   ├── chat.py              - POST /api/chat: graph runner, SSE streaming, escalation short-circuit
│   │   │   ├── tenants.py           - POST /api/tenants signup (service-role provisioning), tenant-admin "me" probe
│   │   │   ├── platform.py          - GET/POST platform endpoints: tenants list, metrics, provision, suspend
│   │   │   ├── onboarding.py        - conversational onboarding: POST /api/onboarding/message, confirm
│   │   │   ├── knowledge.py         - document upload/list/delete endpoints
│   │   │   ├── conversations.py     - tenant-admin: list/detail conversations with traces
│   │   │   ├── escalations.py       - list + resolve escalation endpoints
│   │   │   ├── pricing.py           - tenant-admin: edit pricing rules inline
│   │   │   ├── dashboards.py        - tenant cost + eval dashboard endpoints
│   │   │   └── public.py            - unauthenticated public endpoints (brand, etc.)
│   │   ├── agents/
│   │   │   ├── graph.py             - LangGraph build_graph(), _traced node wrapper, graph context
│   │   │   ├── supervisor.py        - route intent classification + low-confidence escalation override
│   │   │   ├── knowledge.py         - hybrid RAG node: retrieve (dense + sparse + rerank) + citation streaming
│   │   │   ├── recommendation.py    - catalog-scoped retrieval + DB-refetched product recommendations
│   │   │   ├── quoting.py           - pricing-rule selection + engine quote (model never sees prices)
│   │   │   ├── order_status.py      - deterministic tool lookup (ref_code filter, template response)
│   │   │   ├── escalation.py        - terminal handoff: writes escalations row, flips conversation status
│   │   │   ├── inspection.py        - final gate: grounding, policy, injection, prompt-leak checks
│   │   │   ├── price_gate.py        - provenance check: every displayed $ must trace to pricing engine
│   │   │   ├── spotlight.py         - per-request delimiters fencing untrusted tenant data before prompt insertion
│   │   │   └── tools.py             - lookup_order_or_ticket tool (order_status uses it)
│   │   ├── llm/
│   │   │   ├── provider.py          - LLMProvider ABC: extract(), chat(), chat_stream()
│   │   │   ├── openai_compat.py     - OpenAI-compatible backend (OpenRouter, Groq, Ollama) - proven default
│   │   │   ├── azure.py             - Azure OpenAI backend
│   │   │   ├── embedder.py          - Embedder ABC: local (bge-small, keyless) or azure
│   │   │   └── dependency.py        - FastAPI dependency: get_llm_provider, override point for tests
│   │   ├── retrieval/
│   │   │   ├── service.py           - retrieve(): orchestrates dense + sparse + rerank pipeline
│   │   │   ├── dense.py             - pgvector cosine similarity search
│   │   │   ├── sparse.py            - PostgreSQL full-text search (tsvector/tsquery)
│   │   │   └── rerank.py            - Reranker ABC: local (cross-encoder, sigmoid-normalized) or Cohere
│   │   ├── pricing/
│   │   │   ├── engine.py            - compute_quote(): pure-math engine, integer cents, typed errors
│   │   │   └── validation_gate.py   - quote validation: line items match selections, totals reconcile
│   │   └── observability/
│   │       ├── cost.py              - per-turn usage sink (contextvar-based), cost_logs persistence
│   │       └── tracing.py           - Tracer/Turn/Span protocol, NoOpTracer default (Langfuse-ready)
│   ├── migrations/                  - forward-only SQL, applied in filename order
│   │   ├── 0001_extensions.sql      - pgvector extension + tenant-context helper functions
│   │   ├── 0002_roles.sql           - wren_app / service / wren_resolver DB roles
│   │   ├── 0003_tenancy.sql         - tenants, tenant_config, users, platform_admins + RLS + slug resolver
│   │   ├── 0004_knowledge.sql       - documents, knowledge_chunks + RLS + HNSW/GIN indexes
│   │   ├── 0005_conversations.sql   - conversations, messages, tool_calls + RLS
│   │   ├── 0006_commerce.sql        - catalog_items, pricing_rules, quotes + RLS (integer-cents pricing)
│   │   ├── 0007_operations.sql      - orders, escalations + RLS (domain-agnostic shapes)
│   │   ├── 0008_eval_cost.sql       - eval_cases, eval_runs, cost_logs + RLS
│   │   ├── 0009_auth_lookup.sql     - pre-context user/platform-admin lookup resolvers (SECURITY DEFINER)
│   │   ├── 0010_embedding_dim.sql   - `knowledge_chunks.embedding` resized to vector(384)
│   │   ├── 0011_escalations_dedupe.sql - partial unique index preventing duplicate open escalations
│   │   └── 0012+                     - subsequent forward-only migration files
│   ├── tests/                       - 51+ test files (unit + db-marked integration)
│   │   ├── conftest.py              - shared fixtures: wren_test DB, tenant_context, fake providers
│   │   ├── fakes.py                 - FakeProvider, FakeEmbedder, FakeReranker test doubles
│   │   ├── test_*.py                - per-module test files matching `app/` structure
│   ├── seeds/                       - data seeding scripts
│   │   ├── seed_demo.py             - full demo world (bytefix + lumident tenants + auth users + conversations)
│   │   ├── seed_tenant1_phoneshop.py - Tenant 1 (Bytefix): catalog, pricing rules, orders, knowledge chunks
│   │   ├── seed_tenant2_dental.py   - Tenant 2 (dental): drives the public API (generalization proof driver)
│   │   ├── seed_leakage_pair.py     - leakage eval probe tenants (unique secrets per surface)
│   │   ├── seed_injection_probe.py  - injection eval probe tenant
│   │   └── supabase_keys.py         - mint anon/service_role keys from SUPABASE_JWT_SECRET
│   └── evals/                       - three-layer evaluation suite (T-023..T-027)
│       ├── run_gate.py              - gate orchestrator: absolute + regression gates, CI integration
│       ├── retrieval_eval.py        - T-010: recall@k, MRR, nDCG against golden case set
│       ├── generation_eval.py       - T-023: faithfulness, answer relevancy, citation faithfulness (RAGAS-equivalent)
│       ├── judge_calibration.py     - T-024: LLM judge vs human labels (blocked: founder hand-labeling)
│       ├── trajectory_dataset.py    - T-025: 30-case agent task set + schema
│       ├── trajectory_scorer.py     - T-026: tool-call correctness, step efficiency, cost tracking
│       ├── leakage_eval.py          - T-022: cross-tenant leakage probes (both directions)
│       ├── injection_eval.py        - T-027: 29-case prompt-injection attack set
│       └── datasets/                - JSONL case files for each eval type
├── infra/                           - Terraform AWS stack (T-035)
│   ├── main.tf                      - provider config + VPC (two public subnets, no NAT)
│   ├── ecr.tf                       - ECR repository
│   ├── ecs.tf                       - ECS Fargate task + service
│   ├── alb.tf                       - Application Load Balancer
│   ├── iam.tf                       - ECS execution + service roles
│   ├── secrets.tf                   - AWS Secrets Manager entries
│   ├── variables.tf                 - parameterized values
│   └── outputs.tf                   - ALB DNS, ECR URL, task role ARN
├── LEARNINGS.md                     - retrospective: what building Wren taught, per subsystem (for external reviewers)
└── CLAUDE.md                        - symlink to AGENTS.md

```

Note: `docs/phases/phase-1-foundations.md` contains a "repository layout contract" tree - that is a subset contract pinned at phase 1. It carries a one-line pointer confirming this file is the authoritative full tree.
