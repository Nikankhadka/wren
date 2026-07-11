# WREN - Documentation Index & Phase Router

> **This is the only file every session must read.** It tells you which documents to load for the phase you are working on, and nothing else. Do not load the frozen planning docs in `docs/source/` into context unless this router says to - they are the original planning documents, already distilled into the working docs below.

---

## 1. How to use this index

1. Find your phase in the router table (section 3).
2. Read **exactly** the files in that phase's read-set, plus `AGENTS.md` at the repo root (tiny, always applies).
3. Inside a phase file, each ticket carries its own narrower read-list (specific sections of the design docs). Prefer the ticket's read-list over loading a whole design doc.
4. Update the ticket status markers in the phase file as you work: `[ ]` not started, `[~]` in progress, `[x]` done, `[!]` blocked (note why), `[-]` deferred (note why).
5. When you commit a ticket, also update its row in `PROGRESS.md` (status, commit hash, one-line plain-English summary). That file is the human-readable progress view.
6. Record durable discoveries (decisions, gotchas) in `.agents/memory.md`, not in the phase files.

## 2. Document precedence

When documents seem to disagree:

1. `conventions.md` always wins on **how work is done** - style, git, hard rules (deterministic pricing, domain-agnostic), hygiene.
2. The **frozen planning docs** (`source/product-requirements.md`, `source/architecture.md`, `source/sprint-plan.md`, `source/research.md`) win on **what is in scope** - the 30-day clock, MoSCoW cuts, release criteria.
3. The **working docs** (`design/*`, `phases/*`) win on **implementation detail** - schema shape, tokens, ticket steps. They were derived from the planning docs in phase 0; if you find a genuine contradiction on scope, stop and flag it rather than picking one silently.

## 3. Phase router

| Phase | What it delivers | Read-set (complete) | Status |
|---|---|---|---|
| **0. Planning & scaffolding** | Design docs, phase files, monorepo scaffold, /health green | done by the planning session; see git history | `[x]` |
| **1. Foundations** (Week 1) | Tenancy, RLS, subdomain resolution, onboarding skeleton, ingestion, hybrid RAG, retrieval eval | `INDEX.md` + `phases/phase-1-foundations.md` + per-ticket sections of `design/database.md` and `design/frontend.md` | `[x]` |
| **2. Agents & pricing** (Week 2) | LangGraph supervisor + specialists, deterministic pricing engine, validation gate, inspection layer, leakage test | `INDEX.md` + `phases/phase-2-agents-pricing.md` + per-ticket sections of `design/database.md` and `design/frontend.md` (section 6: T-017, T-020) | `[~]` |
| **3. Eval, CI & console** (Week 3) | Three-layer eval, judge calibration, injection defense, CI gate, tracing/cost, tenant admin console | `INDEX.md` + `phases/phase-3-eval-console.md` + per-ticket sections of both design docs | `[ ]` |
| **4. Ship** (Week 4) | Customer + platform surfaces, dashboards, Terraform/AWS + Vercel deploy, Tenant 2 generalization proof, artifacts | `INDEX.md` + `phases/phase-4-ship.md` + per-ticket sections of both design docs | `[ ]` |

A phase is done when its file's Definition of Done block passes. Phases run in order; do not start a phase while the previous one's DoD is failing. Per-ticket status lives in `PROGRESS.md`.

## 4. Document map

```
docs/
  INDEX.md                 <- you are here (always read)
  PROGRESS.md              <- progress tracker: every ticket, its status, its commit,
                              and what that commit did in plain English
  conventions.md           <- binding conventions (always applies; read once per session)
  design/
    database.md            <- schema DDL, RLS policies, indexes, migrations, seeds
    frontend.md            <- design system (tokens), theming, components, surface specs
  phases/
    phase-1-foundations.md      <- tickets T-001..T-011 + Week 1 DoD
    phase-2-agents-pricing.md   <- tickets T-012..T-022 + Week 2 DoD
    phase-3-eval-console.md     <- tickets T-023..T-031 + Week 3 DoD
    phase-4-ship.md             <- tickets T-032..T-040 + Week 4 DoD
  source/                  <- frozen planning docs (rarely loaded; scope truth)
    product-requirements.md     <- what we build and why: personas, user stories (E0-E14)
    architecture.md             <- system design the working docs derive from
    sprint-plan.md              <- original ticket list (superseded by phases/)
    research.md                 <- market grounding (background only)
```

Repo root: `README.md` (human entry point), `AGENTS.md` (stack + verified commands + conventions pointers), `.agents/map.md` (file map), `.agents/memory.md` (session-learned facts).

## 5. The two hard rules (never load a doc to rediscover these)

- **Deterministic pricing:** no language model ever produces, computes, or emits a monetary amount. Agents select rule codes / item ids / quantities; the pricing engine computes everything in integer cents; the validation gate and the API both reject model-authored figures. Full text: `conventions.md` section 8.
- **Domain-agnostic:** no code anywhere branches on a business vertical. All vertical behavior lives in `tenant_config`, `catalog_items`, `pricing_rules`, and uploaded knowledge. Full text: `conventions.md` section 9.

*End of INDEX. Load your phase file and start.*
