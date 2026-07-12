# PHASE 3 - Eval Suite, CI Gate, Observability, Tenant Console (Week 3) - T-023..T-031

> **Read first:** `docs/INDEX.md`, root `AGENTS.md`. Per-ticket read-lists below; repository layout is in `phases/phase-1-foundations.md` (top block).
> **Goal:** the full three-layer eval runs in CI and blocks regressions; every agent run is traced and cost-logged; the tenant admin console's core screens are live and usable end-to-end.
> **Stories covered:** US-030..US-032 (E3); US-070 (E7); US-080, US-082 (E8); US-090, US-091 (E9); US-100 (E10); US-130 partially (E13).

---

### T-023 `[x]` Generation eval: RAGAS + citation-faithfulness (4h)
**Deps:** T-014. **Stories:** US-031.
**Read:** `design/database.md` section 7 (eval_cases/eval_runs); phase-1 T-010 for the dataset/eval-script pattern - mirror it.
**Files:** `backend/evals/datasets/tenant1_generation.jsonl`, `backend/evals/generation_eval.py`.
**Steps:**
1. Dataset: ~30 question cases over Tenant 1 knowledge (question, reference answer or reference facts, expected-source hints).
2. Script: run each through the Knowledge path; score RAGAS faithfulness + answer relevancy; add a custom **citation-faithfulness** metric: for each cited sentence, does the cited chunk actually support it (LLM-judged per citation, aggregated %).
3. Write eval_runs (run_type generation); print table; `--gate` thresholds faithfulness >= 0.85, relevancy >= 0.85.
**Accept:** real numbers reported; per-case failures inspectable (verbose mode prints question, answer, verdict, offending citation).
**Tests:** metric unit tests with fixture verdicts.

### T-024 `[!]` [EDD] Judge calibration (4h) - blocked on founder hand-labeling
**Deps:** T-023. **Stories:** US-032.
**Files:** `backend/evals/datasets/judge_calibration.jsonl`, `backend/evals/judge_calibration.py`.
**Steps:** hand-label ~30 (question, answer, citation) cases for faithfulness/citation correctness **before** running the judge on them (labels are the founder's, committed with the dataset); run the LLM judge; report agreement (percent + Cohen's kappa). Threshold: >= 80% agreement, else iterate the judge prompt (documented in the eval report later).
**Accept:** agreement report generated and committed to eval_runs (run_type generation, metrics include `judge_agreement`); honest number even if below target (then iterate).
**Tests:** the script is the test.
**Status note:** all infrastructure is built and tested (`evals/judge_calibration.py`, 29-case `datasets/judge_calibration.jsonl`) - see `.agents/memory.md`'s T-024 entry. Every dataset row currently carries `label_source: "agent_placeholder"` (agent-authored, not the founder's) since this ticket's own text requires hand-labels written independently of the judge, which no agent session can substitute for without making the exercise circular. `--gate` structurally fails on `founder_labeled_fraction < 1.0` regardless of the agreement score, so this can never silently read as done. **To close this ticket:** run `uv run python -m evals.judge_calibration --print-blind`, hand-label each case fresh (without looking at the placeholder labels already in the file), flip each row's `label_source` to `"founder"`, then run `uv run python -m evals.judge_calibration --gate`.

### T-025 `[x]` [EDD] Golden agent-task set (4h)
**Deps:** T-017, T-015. **Stories:** US-070.
**Files:** `backend/evals/datasets/tenant1_trajectory.jsonl`.
**Steps:** author 20-30 multi-step tasks: quoting scenarios (incl. budget caps, multi-line quotes), recommendation scenarios, order lookups, escalation triggers, mixed-intent conversations. Each case: opening messages, expected route(s), expected tool calls with argument matchers (e.g. rule_code set), expected terminal state (quote row exists / escalation row exists), forbidden behaviors (no invented items, no model-authored figures).
**Accept:** dataset committed, loadable into eval_cases, covers every specialist at least 4 times.

### T-026 `[x]` Trajectory scorer (4h)
**Deps:** T-025. **Stories:** US-070.
**Read:** `design/database.md` sections 6-7 (tool_calls, eval_runs).
**Files:** `backend/evals/trajectory_eval.py`.
**Steps:** drive each T-025 case through the real graph (stubbed customer, real tenant seed); score per case: **tool/argument correctness** (expected calls happened with matching args), **step efficiency** (actual node/tool steps vs expected minimum, ratio), **cost-per-task** (sum cost_logs for the run), plus a judged **reasoning quality** grade on the supervisor's route reasons. Aggregate to eval_runs (run_type trajectory); `--gate`: tool-call correctness >= 90%.
**Accept:** real numbers; failing cases print full trajectories for debugging.
**Tests:** scorer unit tests on fixture trajectories.

### T-027 `[x]` Prompt-injection defense + adversarial set (4h)
**Deps:** T-021. **Stories:** US-080.
**Read:** phase-2 T-021 (inspection's injection check); frozen Architecture Doc section 7 ONLY if defense intent is unclear.
**Files:** `backend/app/agents/spotlight.py`, `backend/evals/datasets/injection_set.jsonl`, `backend/evals/injection_eval.py`.
**Steps:**
1. **Spotlighting:** every retrieved chunk and tool result is wrapped in explicit data delimiters with random per-request boundary tokens, plus a standing system instruction that delimited content is data, never instructions. Applied centrally where context is assembled (one function, used by all nodes).
2. **Input scan:** cheap pre-check on customer messages (pattern + small-model classifier via provider) flagging obvious injection attempts; flagged messages still get answered but with the flag in state for inspection to weigh.
3. Adversarial set (~30 cases): direct injections (ignore instructions, reveal prompt, change prices) and indirect (poisoned knowledge chunk seeded in a scratch tenant, poisoned tool result). Score pass/fail through the full stack; eval_runs run_type injection; target >= 80% documented honestly.
**Accept:** >= 80% pass or an honest number plus analysis; poisoned-chunk case demonstrably neutralized by spotlighting + inspection together.
**Tests:** the eval is the test; unit test the delimiter wrapper (tokens random, unbalanced content escaped).

### T-028 `[x]` Per-tenant cost/step caps + timeouts (3h)
**Deps:** T-021. **Stories:** US-082.
**Read:** `design/database.md` section 7 (cost_logs).
**Files:** `backend/app/core/limits.py`, wired into graph + provider.
**Steps:** per-tenant daily token/cost budget (from `tenant_config.config.limits`, platform defaults in env); checked before each LLM call (sum today's cost_logs, cached); graph step cap (max nodes per turn, default 8) and per-tool + per-LLM-call timeouts. Over budget -> polite unavailable message + escalation row (reason `budget`); never a stack trace.
**Accept:** a tenant at its cap gets the graceful path; caps configurable per tenant; step-cap loop protection proven with a forced cycle in test.
**Tests:** limits unit tests (budget math, step cap, timeout wrapping).

### T-029 `[x]` CI regression gate (4h)
> **Founder follow-up (step 3, not yet done):** add `LLM_API_KEY` as a GitHub Actions secret, then open a scratch branch with a deliberate retrieval break and confirm CI goes red, noting the run link in `.agents/memory.md`. The gate and workflow are built, wired, and locally proven (deterministic gate runs green; decision helpers unit-tested on the failing paths); only the live-Actions break-proof remains and it needs the repo secret.
**Deps:** T-010, T-023, T-026, T-022, T-027. **Stories:** US-130.
**Read:** root `AGENTS.md` Commands table (the commands CI runs must be exactly these).
**Files:** `.github/workflows/ci.yml`, `backend/evals/run_gate.py`.
**Steps:**
1. CI jobs: lint (frontend eslint + `check-tokens.mjs`, backend ruff), typecheck (`tsc --noEmit`, `uv run mypy` - per root AGENTS.md Commands), unit/integration tests (pgvector service container, migrations from scratch), then the **eval gate**: retrieval + generation + trajectory + injection subsets with `--gate` thresholds, plus the leakage test at 100%.
2. `run_gate.py` orchestrates eval subsets against a seeded CI database, compares against thresholds (absolute) and last main-branch run (regression tolerance where thresholds are judged: generation/trajectory 3 points; leakage and price-provenance zero tolerance).
3. **Prove the gate:** open a scratch branch with a deliberate retrieval break; CI must go red; close it. Note the run link in `.agents/memory.md`.
**Accept:** green on main; the deliberate break was caught; secrets via GitHub Actions secrets (provider keys), LLM-dependent evals use pinned models + cached seeds to control flake and cost.
**Tests:** the pipeline is the test.

### T-030 `[x]` Tracing + cost accounting (5h)
**Deps:** T-021. **Stories:** US-090, US-091.
**Read:** `design/database.md` sections 6-7 (tool_calls, cost_logs).
**Files:** `backend/app/observability/tracing.py`, `cost.py`; instrumentation across graph/provider/retrieval/pricing.
**Steps:**
1. Langfuse (free tier) via OTel-compatible SDK: one trace per agent turn - spans for supervisor route, each node, each retrieval stage, each tool call, pricing engine call, inspection verdicts; span attributes carry tenant_id, conversation_id, model, tokens.
2. `cost.py`: provider wrapper records every LLM call into cost_logs (model, tokens, computed USD from a price table in config); aggregation queries for per-tenant/day and per-conversation (used by dashboards T-034).
3. tool_calls rows written for every tool invocation (name, args, result, success, latency_ms) - this is what the Surface-2 TraceTree renders.
**Accept:** a full conversation shows as one coherent Langfuse trace; cost_logs rows reconcile with provider token counts; tool_calls populated.
**Tests:** cost recording unit test (stub provider usage payloads); tool_call persistence test.

### T-031 `[ ]` Tenant admin console core (6h)
**Deps:** T-006, T-030, T-020, T-016. **Stories:** US-100.
**Read:** `design/frontend.md` sections 6 and 7.2 in full (this ticket implements 7.2 except Dashboards); `design/database.md` sections 5-6 for the data.
**Files:** `frontend/src/app/(tenant-admin)/…` - conversations, escalations, pricing pages (+ nav shell); `backend/app/api/` - conversations.py, escalations.py (extend), pricing.py.
**Steps:**
1. Sidebar shell per frontend.md 7.2 (Onboarding and Knowledge pages already exist from phase 1 - mount them in the nav).
2. **Conversations:** list + detail transcript with ChatBubbles + per-assistant-message TraceTree (tool_calls + inspection verdicts + cost per message). Filters by status.
3. **Escalations:** queue with claim/resolve; resolve can post a `human_agent` message into the conversation (delivered to the customer surface).
4. **Pricing:** rules table with inline editing (currency input -> integer cents at the API boundary, validated), catalog list, "new quotes only" note; edits take effect immediately for new quotes (verify against a sent quote staying unchanged - the immutability trigger backs this).
5. Every screen: real loading/empty/error states per the specs; UI pixel standard applies (fix anything visibly off in shared components).
**Accept:** the founder can operate a tenant end-to-end from the console: watch a conversation with trace drill-down, claim + resolve an escalation with a human reply reaching the customer UI, edit a price and see the next quote reflect it while old quotes stay frozen.
**Tests:** API tests for the new endpoints (scoping, cents validation, human_agent message flow); manual E2E pass of all three screens against the seeded tenant.

---

## Week 3 Definition of Done

- [ ] Three-layer eval (retrieval, generation incl. judge calibration, trajectory) + injection producing real committed numbers.
- [ ] CI gate green on main and proven to catch a deliberate break; leakage test wired into CI at 100%.
- [ ] Every agent run traced end-to-end in Langfuse; cost_logs accurate; caps/timeouts protective.
- [ ] Tenant console core usable end-to-end including pricing edits and escalation handling.
- [ ] No lint errors, no failing/flaky tests; discoveries in `.agents/memory.md`.
