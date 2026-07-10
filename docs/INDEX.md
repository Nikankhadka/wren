# WREN - Documentation Index & Phase Router

> **This is the only file every session must read.** It tells you which documents to load for the phase you are working on, and nothing else. Do not load the full PRD, Architecture Doc, or Research doc into context unless this router says to - they are frozen source documents, already distilled into the working docs below.

---

## 1. How to use this index

1. Find your phase in the router table (section 3).
2. Read **exactly** the files in that phase's read-set, plus `AGENTS.md` at the repo root (tiny, always applies).
3. Inside a phase file, each ticket carries its own narrower read-list (specific sections of the design docs). Prefer the ticket's read-list over loading a whole design doc.
4. Update the ticket status markers in the phase file as you work: `[ ]` not started, `[~]` in progress, `[x]` done, `[!]` blocked (note why), `[-]` deferred (note why).
5. Record durable discoveries (decisions, gotchas) in `.agents/memory.md`, not in the phase files.

## 2. Document precedence

When documents seem to disagree:

1. `docs/Wren_AGENTS.md` (conventions v2.0) always wins on **how work is done** - style, git, hard rules (deterministic pricing, domain-agnostic), hygiene.
2. The **frozen source docs** (`Wren_P0P1_CharterAndPRD.md`, `Wren_P3_ArchitectureDoc.md`, `Wren_P3_SprintPlanAndBacklog.md`, `Wren_Research_CloningAndLearningPlan.md`) win on **what is in scope** - the 30-day clock, MoSCoW cuts, release criteria.
3. The **working docs** (`design/*`, `phases/*`) win on **implementation detail** - schema shape, tokens, ticket steps. They were derived from the source docs in the planning phase; if you find a genuine contradiction on scope, stop and flag it rather than picking one silently.

## 3. Phase router

| Phase | What it delivers | Read-set (complete) | Status |
|---|---|---|---|
| **0. Planning & scaffolding** (this phase) | Design docs, phase files, monorepo scaffold, /health green | done by the planning session; see git history | `[x]` |
| **1. Foundations** (Week 1) | Tenancy, RLS, subdomain resolution, onboarding skeleton, ingestion, hybrid RAG, retrieval eval | `INDEX.md` + `phases/phase-1-foundations.md` + per-ticket sections of `design/database.md` and `design/frontend.md` | `[ ]` |
| **2. Agents & pricing** (Week 2) | LangGraph supervisor + specialists, deterministic pricing engine, validation gate, inspection layer, leakage test | `INDEX.md` + `phases/phase-2-agents-pricing.md` + per-ticket sections of `design/database.md` | `[ ]` |
| **3. Eval, CI & console** (Week 3) | Three-layer eval, judge calibration, injection defense, CI gate, tracing/cost, tenant admin console | `INDEX.md` + `phases/phase-3-eval-console.md` + per-ticket sections of both design docs | `[ ]` |
| **4. Ship** (Week 4) | Customer + platform surfaces, dashboards, Terraform/AWS + Vercel deploy, Tenant 2 generalization proof, artifacts | `INDEX.md` + `phases/phase-4-ship.md` + per-ticket sections of both design docs | `[ ]` |

A phase is done when its file's Definition of Done block passes. Phases run in order; do not start a phase while the previous one's DoD is failing.

## 4. Document map

```
docs/
  INDEX.md                          <- you are here (always read)
  design/
    database.md                     <- schema DDL, RLS policies, indexes, migrations, seeds
    frontend.md                     <- design system (tokens), theming, components, surface specs
  phases/
    phase-1-foundations.md          <- tickets T-001..T-011 + Week 1 DoD
    phase-2-agents-pricing.md       <- tickets T-012..T-022 + Week 2 DoD
    phase-3-eval-console.md         <- tickets T-023..T-031 + Week 3 DoD
    phase-4-ship.md                 <- tickets T-032..T-040 + Week 4 DoD
  Wren_AGENTS.md                    <- binding conventions (always applies; read once per session)
  Wren_P0P1_CharterAndPRD.md        <- frozen source: scope, personas, user stories (E0-E14)
  Wren_P3_ArchitectureDoc.md        <- frozen source: system design the working docs derive from
  Wren_P3_SprintPlanAndBacklog.md   <- frozen source: original ticket list (superseded by phases/)
  Wren_Research_CloningAndLearningPlan.md <- frozen source: market grounding (background only)
```

Repo root: `AGENTS.md` (stack + verified commands + conventions pointers), `.agents/map.md` (file map), `.agents/memory.md` (session-learned facts).

## 5. The two hard rules (never load a doc to rediscover these)

- **Deterministic pricing:** no language model ever produces, computes, or emits a monetary amount. Agents select rule codes / item ids / quantities; the pricing engine computes everything in integer cents; the validation gate and the API both reject model-authored figures. Full text: `Wren_AGENTS.md` section 8.
- **Domain-agnostic:** no code anywhere branches on a business vertical. All vertical behavior lives in `tenant_config`, `catalog_items`, `pricing_rules`, and uploaded knowledge. Full text: `Wren_AGENTS.md` section 9.

*End of INDEX. Load your phase file and start.*
