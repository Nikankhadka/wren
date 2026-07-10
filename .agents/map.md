<!-- GENERATED 2026-07-10 by /init-project - do not hand-edit -->

# Wren - File Map

Phase 0 complete: documentation system + monorepo scaffold. Feature code arrives with the phase 1 tickets (`docs/phases/phase-1-foundations.md`).

```
wren/
├── AGENTS.md                     - project instructions: stack, verified commands, conventions pointers
├── CLAUDE.md                     - symlink to AGENTS.md (Claude Code entry point)
├── README.md                     - what Wren is, layout, quickstart
├── docker-compose.yml            - local Postgres + pgvector (service: db)
├── .env.example                  - env template (DB, Supabase, Azure OpenAI, Langfuse)
├── .agents/
│   ├── map.md                    - this file (regenerate via /init-project --refresh)
│   └── memory.md                 - session-learned decisions, gotchas, conventions
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
│   ├── src/app/                  - App Router: layout.tsx, page.tsx, globals.css (token->Tailwind mapping)
│   ├── src/styles/theme.css      - THE design-token source; only file allowed raw color values
│   └── scripts/check-tokens.mjs  - CI guard: fails on color literals outside theme.css
├── backend/                      - FastAPI, Python 3.12, uv
│   ├── app/main.py               - FastAPI entry, /health
│   ├── tests/test_health.py      - health endpoint test
│   └── pyproject.toml            - deps + ruff + pytest config
└── infra/main.tf                 - Terraform stub (populated by T-035)
```
