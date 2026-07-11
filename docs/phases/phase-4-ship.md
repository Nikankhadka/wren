# PHASE 4 - Surfaces, Deploy, Generalization Proof, Artifacts (Week 4) - T-032..T-040

> **Read first:** `docs/INDEX.md`, root `AGENTS.md`. Per-ticket read-lists below; repository layout is in `phases/phase-1-foundations.md` (top block).
> **Goal:** ship. All three surfaces live on public subdomains, Tenant 2 proves domain-agnosticism by config alone, and the portfolio artifacts (eval report, security write-up, README, LEARNINGS, demo video) exist with real numbers.
> **Stories covered:** US-110 (E11); US-120 (E12); US-100 dashboards (E10); US-130 (E13); US-140 (E14).
> **Cut order if the clock runs short** (from the frozen Sprint Plan - unchanged): COULD items first, then S-items, then console polish, then Terraform (fall back to console-configured ECS, keep AWS). **Never cut:** pricing provenance, leakage test, three-layer eval, inspection layer, honest write-ups, AWS deployment.

---

### T-032 `[ ]` Customer chat surface - final polish (5h)
**Deps:** T-021, T-005. **Stories:** US-110.
**Read:** `design/frontend.md` section 7.1 in full (every state row is the checklist), sections 4-5 (type/motion, branding).
**Files:** `frontend/src/app/(customer)/…` (exists since T-011 - this ticket completes it).
**Steps:** work through the 7.1 state table as a literal checklist against the seeded tenant: resolving skeleton without brand-flash, unknown-slug 404, suspended state, configured greeting + starter chips, streaming with stop, QuoteCard rendering, citations with popovers, EscalationBanner incl. a human_agent reply arriving live, disconnect/retry. Mobile pass at 375px. Tenant brand accent applied via the runtime override (frontend.md section 5) with the contrast fallback verified.
**Accept:** every state in 7.1 demonstrably correct on desktop + mobile; pixel standard sweep done (spacing, alignment, empty states) - fix shared components where issues are systemic.
**Tests:** middleware/API tests already cover logic; this ticket's proof is a recorded manual E2E pass, plus a Playwright smoke (load branded page, send message, receive streamed reply) if the harness exists by now - add it if cheap, note if deferred.

### T-033 `[ ]` Platform-owner surface (3h)
**Deps:** T-004. **Stories:** US-120.
**Read:** `design/frontend.md` section 7.3; `design/database.md` section 3 (tenants policies, platform_admins).
**Files:** `frontend/src/app/(platform)/page.tsx`, `backend/app/api/platform.py`.
**Steps:** protected by `require_platform_admin`; tenants Table (name, slug, status, created, conversation count, cost aggregate) via audited admin queries; Provision modal (name + slug availability check -> creates tenant + config + invite email note); suspend/reactivate with confirm modal (suspend flips tenants.status - customer surface immediately shows the unavailable state). Aggregate MetricCards (tenant count, total cost). Nothing more - minimal is the spec.
**Accept:** provisioning from this surface yields a tenant that can complete onboarding with zero founder code/DB touches; suspend takes effect on the live customer surface; non-admin users get a hard 403 on page and API.
**Tests:** API tests: admin-gated access, provision flow, suspend effect on resolve endpoint.

### T-034 `[ ]` Tenant dashboards: cost + eval (4h)
**Deps:** T-030, T-029. **Stories:** US-100.
**Read:** `design/frontend.md` sections 6 (MetricCard) and 7.2 (Dashboards); `design/database.md` section 7 (cost_logs, eval_runs).
**Files:** `frontend/src/app/(tenant-admin)/dashboards/page.tsx`, `backend/app/api/dashboards.py`.
**Steps:** cost cards (today, this month, per-conversation average) from cost_logs aggregation; conversation volume + escalation rate; latest eval_runs metrics rendered with pass/fail chips vs the gate thresholds; simple 30-day cost sparkline (no chart library heavier than a tiny sparkline - keep it light). Real empty states ("no conversations yet - share your chat link").
**Accept:** numbers reconcile with direct SQL against cost_logs/eval_runs; empty/loading/error states real.
**Tests:** aggregation endpoint tests against fixtures.

### T-035 `[ ]` Terraform AWS backend (6h)
**Deps:** T-029. **Stories:** US-130.
**Read:** frozen `docs/source/architecture.md` section 9 (this ticket's spec lives there - the one phase-4 ticket that reads the frozen doc).
**Files:** `infra/*.tf` (main, ecr, ecs, alb, iam, secrets, variables, outputs), `backend/Dockerfile`.
**Steps:** per Architecture section 9: ECR repo; ECS cluster + Fargate service (0.25 vCPU/0.5GB) + task def; public ALB + TLS + target group with `/health` checks; security groups ALB->task only; least-privilege IAM (execution: ECR pull + logs; task: scoped Secrets Manager ARNs); Secrets Manager entries for provider keys + DB URL; CloudWatch log group + billing alarm; no NAT (public subnet, SG lockdown - documented cost decision). `terraform apply` up, `destroy` down, state local at core scope (documented).
**Accept:** apply from clean -> `/health` 200 via the ALB DNS name; destroy leaves nothing billing except the ECR images; plan is clean immediately after apply.
**Tests:** `terraform validate` + fmt in CI; the apply/destroy cycle is the acceptance run (documented in memory, not CI).

### T-036 `[ ]` Deploy end-to-end: CI image push + Vercel wildcard (4h)
**Deps:** T-035, T-032, T-033, T-034.
**Read:** root `AGENTS.md` Commands; `.github/workflows/ci.yml` from T-029.
**Files:** `.github/workflows/deploy.yml`, Vercel project config, frontend env wiring.
**Steps:** on main after CI gate: build backend image -> push ECR -> update ECS service; frontend to Vercel with wildcard domain (`*.wren.app` or the actually-registered domain; document the real one), env vars pointing at the ALB backend; Supabase production config. Smoke script post-deploy: resolve two tenant subdomains, run one chat turn each.
**Accept:** two tenants reachable at their own public subdomains end-to-end (chat -> agents -> quote) on production infra; deploy is push-triggered, gate-protected.
**Tests:** the post-deploy smoke script.

### T-037 `[ ]` [Time-boxed: 1 day] Generalization proof - Tenant 2 by config alone (6h)
**Deps:** T-036. **Stories:** US-140.
**Read:** `design/database.md` section 10 (seed_tenant2_dental is inputs-only, on purpose); INDEX section 5 (domain-agnostic rule).
**Files:** `backend/seeds/tenant2_inputs/` (knowledge docs: clinic policies, services/fees sheet, FAQ), a written interview script, `docs/artifacts/generalization-proof.md` (the evidence).
**Steps:**
1. Provision the dental clinic tenant from Surface 1; complete conversational onboarding using only the interview script; upload the knowledge docs. **Zero code changes, zero direct DB writes** - if any step needs one, stop: that is a domain-agnostic bug to fix in the platform, then restart the proof (the AGENTS.md hard rule; the time-box guards the clock).
2. Verify: in-domain questions answered + cited; fee questions produce engine quotes from its own pricing rules; out-of-domain ("do you fix phone screens?") declines/escalates; leakage re-run against tenant pair.
3. Write the proof doc: what was configured, transcript excerpts, the "git diff is empty" evidence, eval numbers if the golden-set pattern is reused.
**Accept:** dental clinic live at its subdomain on identical code; the proof doc holds up to a skeptical reader.

### T-038 `[ ]` Eval report (4h)
**Deps:** T-029. **Files:** `docs/artifacts/eval-report.md`.
**Steps:** real numbers only, from eval_runs: retrieval (recall@k, MRR, nDCG), generation (faithfulness, relevancy, citation-faithfulness), judge calibration agreement, trajectory (tool correctness, efficiency, cost-per-task), injection pass rate, leakage 100%, quote-provenance status; methodology per layer (dataset sizes, judge models, thresholds); honest analysis of misses; the WON'T/deferral table copied forward from the PRD with any updates.
**Accept:** every figure traceable to an eval_runs row (include run ids); no rounded-up marketing numbers.

### T-039 `[ ]` Security write-up (3h)
**Deps:** T-022, T-027. **Files:** `docs/artifacts/security.md`.
**Steps:** OWASP LLM Top 10 mapping (addressed: LLM01 spotlighting + input scan + inspection, with the honest injection pass rate; LLM07 leak checks; LLM08 RLS + leakage test as the signature proof; LLM10 caps/timeouts; classic web controls), each with pointers to code + tests; deliberate deferrals (guardrails framework, formal red team, SSO/certs) stated as decisions.
**Accept:** a security-literate reviewer can verify every claim from the linked tests.

### T-040 `[ ]` README + LEARNINGS + demo video (5h)
**Deps:** T-038, T-039. **Files:** `README.md`, `LEARNINGS.md`, video link in README.
**Steps:** README: what Wren is, the three-surface diagram (redraw from the frozen PRD section 2), quickstart (verified against root AGENTS.md commands on a clean clone), architecture summary linking the design docs, deferral rationale table, links to artifacts. LEARNINGS.md: per subsystem (tenancy/RLS, RAG, agents, pricing, eval, security, observability, infra) - what was learned, what surprised, what would change (the Research doc's section 4.1 intent; open it only if the rubric is needed). Record the 5-10 minute walkthrough: three surfaces, a quote with trace drill-down, the generalization proof, the eval report.
**Accept:** clean-clone quickstart works as written; video linked; release criteria checklist below all green.

---

## Week 4 / FINAL Definition of Done (mirrors PRD section 9 - verify every line)

- [ ] All MUST items (M1-M20) pass their acceptance criteria (walk the list in the frozen PRD section 6 once, at the end).
- [ ] Numbers-backed eval report; leakage test + quote-provenance test passing in CI.
- [ ] Zero model-authored prices possible (gate + inspection + API rejection all tested).
- [ ] No known lint errors, no failing/flaky tests in CI.
- [ ] Two+ tenants live at their own public subdomains; Tenant 2 was config-only (proof doc).
- [ ] README + LEARNINGS.md + demo video done.
- [ ] Day-24 buffer honored: bug sweep + re-run leakage and provenance tests before calling it shipped.
