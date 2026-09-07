# Phase 1 - Polish (B-1/B-3/E-3/D-2/F-2/G-1)

**Status: complete.**

The final build group: rebrand copy, semantic colour convention, minimal
platform surface, lean default, CI import boundary, and the re-cut eval cases.

Tickets in this file (in build order):

- B-1: Copy rename to Agencx
- B-3: Semantic colour convention + lighter primary
- E-3: Platform admin stays minimal
- D-2: Lean default for new + legacy tenants
- F-2: Import boundary in CI
- G-1: Eval cases for the lean toolset

---

## B-1: Copy rename to Agencx

### Summary

Rename every user-facing surface from Wren to Agencx: brand mark, page
titles, login/greeting copy, console chrome, marketing pages, and the demo
world's seeded copy. The repo, roles, and env names stay `wren` (standing
names note in the set README) - this ticket touches user-visible strings only.

### Why

The product is Agencx (merge decision: "Name = Agencx (surface only)"). Copy
is the surface. Delaying copy to "later" is what produced the Wren surfaces
that said "AI"/"agent" and needed a rewrite pass (decision 11).

### User stories

#### US-1 Every surface says Agencx

**As** the founder,
**I want** no user-visible "Wren" left anywhere,
**so that** the product reads as one thing.

- [ ] Greeting, login, onboarding intro, escalation messages: Agencx
- [ ] Page titles (`<title>`, metadata): Agencx
- [ ] Tenant console shell + platform console header: Agencx wordmark
- [ ] Marketing pages (/, /product, /pricing, /demo, /about): Agencx naming,
  no "Wren" stragglers

#### US-2 Copy rules hold

**As** the founder,
**I want** user-facing copy to never say "AI", "agent", "automated", or
"assistant" (PRD section 13),
**so that** the product leads with outcomes.

> Amended after this ticket shipped: W-9's copy-rule amendment (2026-09-06,
> `spec/active/13-walkthrough.md`) took "assistant" off the list and put
> "virtual" on it, so both mandated openings can name the assistant as what the
> surface is. The list `frontend/e2e/copy-rules.spec.ts` enforces today is
> "AI", "agent", "automated", "virtual". Recorded here rather than rewritten:
> what this ticket delivered is what it says.

- [ ] A grep over frontend user-facing strings for the banned words is clean
  (exceptions: internal/console tooltips are still copy - clean them too;
  code identifiers are out of scope)

#### US-3 E2E specs move with the copy

**As** the maintainer,
**I want** every copy change to update the pinned e2e assertions in the same
commit,
**so that** CI stays green (the landing/marketing e2e specs pin h1 copy and
hrefs verbatim - a copy change without the spec update goes red).

- [ ] Playwright specs updated alongside the copy changes
- [ ] `make test-e2e` passes on the seeded world

### Design reference

**`docs/agencx/design/prototypes/agencx-prototype-v6.html`** carries the
shipped Agencx identity (crimson, monogram mark) and is the reference for how
the name and mark appear in product chrome. Prototype
copy is demo copy for the Sababa reference tenant - never lift strings from it
into marketing or product surfaces.

### Technical spec

- String sweep across `frontend/src/`, `backend/app/` (seeds + greeting
  templates + escalation copy), `scripts/`
- Brand mark: the Wren wordmark component -> Agencx wordmark (same token
  system; no design change - B-1 is copy only, D-17's font swap is separate)
- Seeded tenants: greeting/tone copy re-seeded to Agencx voice

### Tests

- `make lint-frontend`, `make typecheck-frontend`, `make test-frontend`
- `make test-e2e` green (updated specs)
- Copy grep: `rg -i "wren" frontend/src` returns only code-identifier hits
  (reviewed, not banned)

### Files touched

- `frontend/src/**` (copy-bearing components, layouts, marketing pages)
- `frontend/e2e/**` (specs pinned to copy)
- `backend/app/**` (greeting/escalation templates), `backend/seeds/**`

### Definition of done

- [ ] No user-visible "Wren" string remains
- [ ] No banned word in user-facing copy
- [ ] E2E green with updated specs

---

## B-3: Semantic colour convention + lighter primary

### Summary

Land the semantic status-colour convention in shipped code and lighten the brand
primary. Crimson stays the brand accent (buttons, active tab, links, monogram,
brand surfaces) but moves a touch lighter. Status is expressed with the standard
semantic ramp routed through tokens and the `Badge` `STATUS_TONE` map - never a
hardcoded hex: green = approved/success, red = cancelled/declined/error, amber =
pending/warning.

### Why

Today several statuses render neutral grey and some positive states lean on the
brand accent (crimson), which blurs brand vs status meaning. A single
status-to-tone map gives every status an unambiguous, accessible colour and keeps
brand colour out of status semantics. Lighter primary is the founder's brand
call. The reference prototypes already carry this convention; this ticket brings
the shipped app in line.

### User stories

#### US-1 Lighter brand primary - DONE, landed early with O-5

Pulled forward: O-5 ports the onboarding thread from the prototype, and the
prototype's crimson IS `#C1123F`, so the port could not be colour-accurate
without it. The ramp below is shipped; US-2 (the `STATUS_TONE` map) is what
remains of B-3.

**As** the founder,
**I want** the primary accent a touch lighter,
**so that** the crimson reads brighter while keeping white-text AA contrast.

- [x] `--primary-40` `#BA0036` -> `#C1123F`
- [x] Derived ramp: hover `#A1002F`->`#A80033`, active `#870027`->`#8F0029`,
      accent-container `#E21E4A`->`#E8385E`; subtle `#FFD9DC`/`#FFECEE` unchanged
- [x] Dark-mode blocks updated identically (edit both or neither) - vacuous
      today: the dark blocks are currently disabled in `theme.css`

#### US-2 Statuses use semantic colours

**As** a user,
**I want** each status to read green/red/amber by its meaning,
**so that** I can scan state at a glance.

- [ ] `STATUS_TONE` in `frontend/src/components/ui/Badge.tsx` re-mapped:
      green (approved/success/complete/paid/ready/resolved/active/delivered/
      confirmed), red (cancelled/declined/failed/suspended/rejected/refunded),
      amber (pending/warning/overdue/in-progress/processing/claimed/escalated/
      outstanding), neutral/info (open/sent/draft)
- [ ] Tenant-defined order/repair statuses (`in_progress`, `ready_for_pickup`,
      `completed`, `cancelled`, `shipped`, `delivered`) added to the map
- [ ] No status colour is a hardcoded hex; all route through the semantic tokens
      or `toneForStatus`

### Design reference

**`docs/agencx/design/prototypes/agencx-prototype-v6.html`** is the colour
source of record for this ticket: it already applies the convention (crimson
reserved for identity and the single primary action per view; state colour
carried by the semantic tokens, never by the brand hue).
Read its `:root` custom properties and the usage around `.pcta-main`, `.ccfm` /
`.ccnc`, and the status pills (`.spaid`, `.sover`, `.spend`) before touching
`theme.css`.

### Technical spec

- `frontend/src/styles/theme.css`: update the primary ramp tones (Layer 1) and any
  Layer 2 semantic token that references them; both dark blocks identically
- `frontend/src/components/ui/Badge.tsx`: extend `STATUS_TONE` + `BadgeTone` with
  the status values above
- `frontend/src/**`: remove any `bg-[#BA0036]`-style arbitrary-value hex for
  statuses (the CI grep already forbids these); brand surfaces may keep the accent
  token
- Domain-agnostic constraint: order status is tenant-defined free text - unknown
  statuses fall back to neutral (no per-vertical colouring)

### Tests

- `make lint-frontend`, `make typecheck-frontend`, `make test-frontend`
- `make check-tokens` (no raw status hex outside `theme.css`)
- Visual pass: money/quote/tenant/conversation badges show green/red/amber by
  status; primary buttons read lighter crimson

### Files touched

- `frontend/src/styles/theme.css`
- `frontend/src/components/ui/Badge.tsx`
- `frontend/src/components/ui/QuoteCard.tsx` (if it hardcodes a tone)
- Other status-bearing components as the map change requires

### Definition of done

- [x] Primary ramp lighter, dark-mode blocks identical (O-5)
- [ ] Every status maps to green/red/amber/neutral via `STATUS_TONE`
- [ ] No hardcoded status hex in components
- [ ] Lint, typecheck, tokens, tests green

---

## E-3: Platform admin stays minimal

### Summary

Confirm and preserve the minimal platform-owner surface: one Tenants page
(list with status/cost/conversation counts, provision, suspend/reactivate)
plus aggregate metrics. No new platform features land in the Stage 1 build.

**Later note:** platform pre-provisioning (the "provision a tenant shell"
control this ticket verified) was itself removed afterward - self-onboarding
was already the only claim path that worked, and a pre-provisioned tenant
could get permanently stuck (see progress.md's Platform-owner surface row).
The rest of this ticket's acceptance evidence is unaffected.

### Why

The platform owner persona (PRD section 3) needs provision/suspend and the
place where the generalization proof is watched - nothing else. Wren's
platform surface already matches; this ticket is a confirmation pass, not a
build.

### User stories

#### US-1 The surface is complete for its job

**As** the platform owner,
**I want** to list tenants, provision one, suspend/reactivate, and see the
watch metrics,
**so that** Stage 1 operations work end to end.

- [ ] Tenants table: slug, name, status, created, conversations, cost
- [ ] Provision-tenant modal (slug + name + admin user)
- [ ] Suspend/reactivate with the customer-visible consequences (public page
  shows "unavailable"; reactivation restores)
- [ ] Aggregate MetricCards on top

#### US-2 Nothing grows here in Stage 1

**As** the founder,
**I want** no new platform features in this phase,
**so that** the build stays on the spine.

- [ ] Ticket scoped to verification + fixes only; feature ideas are flagged,
  not built

#### US-3 Eval watch stays visible

**As** the founder,
**I want** the eval pass/fail surface reachable,
**so that** the keep/pivot/stop signals have a home.

- [ ] Existing dashboards (cost + eval) remain reachable from the platform
  side (they were tenant-side; the platform keeps its own aggregate view
  where present - no new build, just non-regression)

### Design reference

**None - and that is deliberate.** Neither prototype has a platform-owner
screen; the platform surface stays the existing plain admin UI. Do not invent a
prototype-flavoured design for it, and do not port tenant-app chrome (bottom tab
bar, command pill) onto it.

### Technical spec

- Verification pass over `frontend/src/app/(platform)/` and the platform API
  routes; fix anything broken found along the way (conventions section 6)

### Tests

- E2E: provision -> suspend -> public page unavailable -> reactivate
- Platform API regression tests

### Files touched

- `frontend/src/app/(platform)/**`, `backend/app/api/**` (fixes only)

### Definition of done

- [ ] Provision/suspend/reactivate verified end to end
- [ ] No scope growth
- [ ] Platform regression suite green

---

## D-2: Lean default for new + legacy tenants

### Summary

A forward-only migration that (a) changes the `tenant_config.enabled_tools`
column default to the lean set and (b) backfills existing rows. New tenants
are lean by default; the seeded Wren tenants move to lean unless their demo
role requires otherwise (documented in the seed).

### Why

D-1 ships the machinery; D-2 sets the default world state so the lean flow
is what everyone actually runs. The current column default is the full
advanced set - leaving it would make every new tenant quote-capable by
accident.

### User stories

#### US-1 New tenants are lean

**As** a tenant who just onboarded,
**I want** my enabled set to be answering + escalate,
**so that** nothing is on without my choosing it.

- [ ] Column default becomes `["answer_from_knowledge","create_escalation"]`
- [ ] Signup-created rows observe the new default (no code path hardcodes the
  old list)

#### US-2 Legacy rows are backfilled deliberately

**As** the maintainer,
**I want** existing rows migrated with intent per row,
**so that** the demo world keeps working and real rows are honest.

- [ ] Migration backfills legacy rows to the lean set
- [ ] Seeds re-assert per-tenant sets explicitly (tenant 1 demo may keep
  advanced tools to demo them; tenant 2 dental stays lean as the I8 proof)

#### US-3 The migration is forward-only and auditable

**As** the maintainer,
**I want** the change as migration `0016` (next number) with the schema
audit still green,
**so that** the change is reproducible everywhere.

- [ ] No editing of prior migration files
- [ ] `make migrate` applies cleanly on the dev DB

### Technical spec

- `backend/migrations/0016_enabled_tools_lean_default.sql`:
  `alter table tenant_config alter column enabled_tools set default ...;`
  + `update tenant_config set enabled_tools = ... where enabled_tools =
  '<old default>';` (targeted: only rows still carrying the old default list,
  never custom sets)
- Seed updates in `backend/seeds/**`

### Tests

- Migration test: fresh DB has lean default; simulated legacy row backfills
- Seed test: seeded tenants carry their documented sets

### Files touched

- `backend/migrations/0016_enabled_tools_lean_default.sql`
- `backend/seeds/**`, `backend/tests/test_migrations*.py`

### Definition of done

- [ ] New tenants lean by default
- [ ] Legacy rows backfilled deliberately
- [ ] Migration clean on the dev DB, forward-only

---

## F-2: Import boundary in CI

### Summary

Wire the deterministic-boundary enforcement into CI: backend import-linter
forbids importing `llm/provider.py` outside `agents/` and `llm/`; the
frontend ESLint `no-restricted-imports` rule forbids components importing a
model or backend client. Both fail the CI job on violation.

### Why

The boundary exists in prose (architecture section 4, decision 5). The
violation that matters is the one added later under time pressure - the
check must predate the pressure. Determinism is a property of the module
graph, not of willpower.

### User stories

#### US-1 Backend boundary is machine-enforced

**As** the maintainer,
**I want** CI to fail when a `services/` or `api/` module imports the model
layer,
**so that** I1 cannot be smuggled away later.

- [ ] import-linter contract: `llm/provider.py` importable only by `llm/*`
  and `agents/*` (and the onboarding loop, per the boundary doc)
- [ ] Wired into `ci.yml` (or the lint job `make lint-backend`)

#### US-2 Frontend boundary is machine-enforced

**As** the maintainer,
**I want** ESLint to fail when a component imports a model/backend client,
**so that** the frontend cannot bypass the API layer.

- [ ] `no-restricted-imports` rule over any client-side model SDK or direct
  backend client
- [ ] Wired into `npm run lint`

#### US-3 The check has teeth and is documented

**As** the maintainer,
**I want** a deliberate violation test proving the rules fire,
**so that** the check cannot silently rot.

- [ ] A test (or fixture) that asserts the linter config flags a violating
  import

### Technical spec

- Backend: import-linter as a dev dependency of `backend/` (or an AST-based
  test if the dependency is unwarranted - decision: use import-linter, it is
  the tool the ADR names)
- Frontend: ESLint config addition in `frontend/eslint.config.*`

### Tests

- CI runs `make lint`; violating-import fixture fails it

### Files touched

- `backend/pyproject.toml`, `backend/.importlinter`, `.github/workflows/ci.yml`
- `frontend/eslint.config.*`, `frontend/package.json`

### Definition of done

- [ ] Backend + frontend boundary rules wired into CI
- [ ] Teeth fixture proves they fire
- [ ] `make check` green with the rules active

---

## G-1: Eval cases for the lean toolset

### Summary

Re-cut the eval case sets for the Agencx shape: generation cases that expect
the lean flow (grounded answer, verbatim figures, refusal + escalation
instead of recommendations/quotes), trajectory cases that score the
supervisor-with-tools path (one call in the common case, correct escalate
usage), and the money-guardrail matrix from C-4 wired into the absolute
gate. Keep the recall, leakage, and injection gates untouched.

### Why

The eval sets were written against the five-specialist Wren topology; they
assert routes and tools that no longer exist in the lean shape. Un-updated,
the trajectory scorer measures the old build and the phase gate is red by
default. Eval cases grow with the build - a phase without eval cases is not
complete.

### User stories

#### US-1 Generation cases match the lean shape

**As** the maintainer,
**I want** held-out conversations that exercise the lean assistant (grounded
answers with citations, verbatim prices, honest refusals, escalations),
**so that** faithfulness/relevancy/citation metrics measure the real product.

- [ ] Sababa-flavored cases: menu/catering questions with verbatim figures
- [ ] Refusal cases: out-of-scope asks ("can I pay in crypto") -> refusal
  + unmet-ask, scored 0.0 positive / 1.0 negative
- [ ] Escalation cases: "talk to the owner" and guardrail-failure paths

#### US-2 Trajectory cases score the new topology

**As** the maintainer,
**I want** the 30-case agent-task set updated so expected routes are
tool-selections on one supervisor, not specialist nodes,
**so that** step efficiency measures one call in the common case.

- [ ] Expected tool calls per case re-annotated (answer vs escalate)
- [ ] "Must not" rules updated: lean tenant cases must not quote or
  recommend

#### US-3 The gates stay green and never skipped

**As** the maintainer,
**I want** recall/leakage/injection gates untouched and the money matrix
added to the absolute set,
**so that** the phase can only close with every absolute gate green.

- [ ] C-4 matrix included in `run_gate` absolute gates
- [ ] No CI flag skips any absolute gate

### Technical spec

- `backend/evals/**` case updates; re-run against the stubbed-provider
  harness in CI
- The generation/trajectory gates remain regression-gated (LLM-judged);
  the money matrix is deterministic-absolute

### Tests

- `make eval` green (with the matrix); `make eval-skip-llm` green locally

### Files touched

- `backend/evals/**`, eval seeds

### Definition of done

- [ ] Generation + trajectory cases re-cut for the lean shape
- [ ] Money matrix in the absolute gate
- [ ] Recall/leakage/injection gates untouched and green
