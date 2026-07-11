# PHASE 2 - Agent Graph, Pricing Engine, Inspection (Week 2) - T-012..T-022

> **Read first:** `docs/INDEX.md`, root `AGENTS.md`, and the two hard rules (INDEX section 5) - this phase is where both bite. Per-ticket read-lists below; the repository layout contract is in `phases/phase-1-foundations.md` (top block) if you need a path refresher.
> **Goal:** LangGraph supervisor + specialists live; recommendation and deterministic quoting work; the reasoning-inspection layer guards every send; cross-tenant leakage test passes 100%.
> **Stories covered:** US-040, US-041, US-042 (E4); US-050, US-051 (E5); US-060 (E6); US-081 (E8).
> **This is the plan's centerpiece week.** If it slips, cut SHOULD/COULD scope elsewhere - never the pricing provenance, leakage test, or inspection layer.

## Shared contracts for this phase

- **Agent state** (T-012 defines it in code): `conversation_id`, `tenant_id`, `messages`, `route`, `route_confidence`, `retrieved_chunks`, `selections` (quoting), `engine_quote` (pricing output), `draft_response`, `inspection` (verdict + reasons), `escalated`.
- **The Quoting Agent's output schema has no number fields.** It emits `[{rule_code | catalog_item_id, quantity}]` + free text. Quantities are counts of things, not money. Any schema change that adds a money field is a convention violation (root `AGENTS.md`, hard rule 1).
- **Every LLM call goes through `app/llm/provider.py`.** Model names come from env.

---

### T-012 `[x]` LangGraph state schema + graph skeleton (4h)
**Deps:** T-011. **Stories:** US-040.
**Read:** this file's shared contracts; frozen `Wren_P3_ArchitectureDoc.md` section 4.1 diagram ONLY if graph topology is unclear.
**Files:** `backend/app/agents/state.py`, `graph.py`, stub nodes `supervisor.py`, `knowledge.py`, `recommendation.py`, `quoting.py`, `order_status.py`, `escalation.py`, `inspection.py`.
**Steps:**
1. `state.py`: typed state (pydantic/TypedDict) per the contract above.
2. `graph.py`: Supervisor -> conditional edge on `route` -> one specialist -> Inspection -> END (or Inspection -> re-prompt loop, wired in T-021). All nodes stubbed to pass-through; graph compiles and streams.
3. Swap `/api/chat` to invoke the graph (stubs behave like T-011's straight RAG for now, so nothing regresses).
**Accept:** graph compiles, traces node order, `/api/chat` still passes its T-011 tests.
**Tests:** graph topology test (given a forced route, the right node sequence runs).

### T-013 `[x]` Supervisor routing (4h) - live-model smoke set deferred, AZURE_OPENAI_* still empty (see memory.md)
**Deps:** T-012. **Stories:** US-040.
**Files:** `backend/app/agents/supervisor.py`.
**Steps:** one structured LLM call: conversation tail -> `{route: knowledge|recommendation|quoting|order_status|escalation, confidence: 0..1, reason}`. Below `tenant_config.escalation_threshold` -> route escalation (low confidence never guesses). Routing prompt is generic - intents described by capability ("wants a price for something", "asking about a policy"), never by vertical.
**Accept:** obvious utterances route correctly across two different fake verticals; low-confidence gibberish routes to escalation.
**Tests:** routing unit tests with stubbed provider outputs; a small live-model routing smoke set (~10 cases) run manually and noted.

### T-014 `[ ]` Knowledge Agent (3h)
**Deps:** T-013. **Stories:** US-041 partially.
**Read:** phase-1 T-009's `service.retrieve` signature.
**Files:** `backend/app/agents/knowledge.py`.
**Steps:** node calls `retrieve`, generates grounded + cited draft into `draft_response` with chunk provenance kept in state (Inspection needs it); refusal path when nothing relevant (same rule as T-011).
**Accept:** parity with T-011 behavior through the graph; provenance lands in state.
**Tests:** node test with stubbed retrieval/provider.

### T-015 `[ ]` Recommendation Agent (4h)
**Deps:** T-013. **Stories:** US-041.
**Read:** `design/database.md` section 5 (catalog_items); phase-1 T-008 note that catalog items exist as chunks with `metadata.kind='catalog_item'`.
**Files:** `backend/app/agents/recommendation.py`.
**Steps:** extract preferences from the conversation (structured LLM call: needs, constraints - generic keys, no vertical assumptions); build a preference-aware query; retrieve over catalog chunks (filter `metadata.kind='catalog_item'`); draft grounded recommendations naming only retrieved items, each with its item provenance. If the item has `price_cents`, the displayed price comes from the DB value formatted server-side - included in provenance for Inspection, never model-authored.
**Accept:** "I need something for X" returns real catalog items with reasons; items never invented; works identically on a second seeded vertical.
**Tests:** node tests with fixture catalog; assert response item ids are a subset of retrieved ids.

### T-016 `[ ]` Deterministic pricing engine (4h)
**Deps:** T-002 (schema). **Stories:** US-050.
**Read:** `design/database.md` section 5 (pricing_rules, quotes, line_items shape).
**Files:** `backend/app/pricing/engine.py`, `backend/tests/test_pricing_engine.py`.
**Steps:**
1. Pure function, no LLM imports anywhere in the module: `compute_quote(tenant_id, selections: [{rule_code|catalog_item_id, quantity}]) -> EngineQuote(line_items, subtotal_cents, tax_cents, total_cents)`.
2. Reads the tenant's active pricing_rules/catalog_items; unknown code/id or inactive -> typed error (agent will re-select); quantity bounds (1..999); `conditions` honored for the generic keys defined in database.md (`min_qty`, `applies_to`).
3. Tax from `tenant_config.config.tax` (`rate_bps`, banker-free integer math: `tax = subtotal * rate_bps // 10000`).
**Accept:** exhaustive unit coverage - single/multi line, both selection kinds, tax on/off, rounding, unknown codes, zero-amount rules; property test: total always equals sum of parts.
**Tests:** `test_pricing_engine.py` is the deliverable's proof; add a hypothesis property test if quick.

### T-017 `[ ]` Quoting Agent (4h)
**Deps:** T-016, T-013. **Stories:** US-042, US-050.
**Read:** this file's shared contracts (no-number-fields schema); `design/database.md` section 5 (quotes).
**Files:** `backend/app/agents/quoting.py`.
**Steps:**
1. Structured LLM call over conversation + retrieved rule/item candidates (retrieve over pricing_rules labels + catalog): output = selections (codes/ids + quantities) + a free-text explanation. Schema has **no numeric money field** - enforce with the response model.
2. Call `engine.compute_quote`; on typed error, re-select once with the error in context; then persist the quotes row verbatim from engine output (the only code path that writes quotes, per database.md section 5).
3. Draft response references the QuoteCard payload (engine output verbatim); money formatting happens in the frontend's `money.ts` from integer cents.
4. Budget-cap questions ("under $X"): the agent may compare the customer's stated cap against engine totals only by including the engine result in a second structured call ("does this satisfy the constraint") - it still never authors a figure.
**Accept:** "screen repair for a mid-tier phone, under $120" -> correct tenant-priced quote, persisted, rendered via QuoteCard; every displayed figure traces to the engine row.
**Tests:** node tests with stubbed provider (selection -> engine -> persisted row); error re-selection path.

### T-018 `[ ]` Validation gate: price provenance (3h)
**Deps:** T-017. **Stories:** US-050.
**Files:** `backend/app/pricing/validation_gate.py`, `backend/tests/test_validation_gate.py`.
**Steps:**
1. `validate(draft_response, engine_quote|None, provenance) -> ok | violations`. Extract every monetary figure from the draft (regex over currency patterns + spelled-out amounts); each must reconcile to the engine output (line totals, subtotal, tax, total) or to DB-sourced provenance (catalog price_cents from T-015). Any unmatched figure = violation.
2. Wire into the graph after Quoting (and Recommendation): violation -> re-prompt the node once with violations listed -> still failing -> route to Escalation with reason `price_provenance`.
3. API layer half: quote endpoints accept no client/model totals anywhere (schema-level).
**Accept:** a deliberately planted model-authored "$99" is caught, re-prompted away or escalated - demonstrate in a test; zero false-positive on clean engine-derived responses in the existing suite.
**Tests:** `test_validation_gate.py` (extraction cases incl. "$1,299.00", "1299 dollars", "twelve hundred"), graph-level violation path test. **This test is a release criterion - it never gets deleted or skipped.**

### T-019 `[ ]` Mock orders seed + lookup tool (4h)
**Deps:** T-002. **Stories:** part of E4.
**Read:** `design/database.md` section 6 (orders).
**Files:** `backend/seeds/seed_tenant1_phoneshop.py` (orders part), `backend/app/agents/tools.py::lookup_order_or_ticket`.
**Steps:** seed ~20 varied orders for Tenant 1 (kinds 'repair'/'order', tenant-vocabulary statuses); tool takes `ref_code` (+ optional `customer_ref`), returns typed result or a graceful typed not-found (never an exception into the model); tenant-scoped by construction (tenant context, plus explicit predicate).
**Accept:** "where is R-1042" style lookups return the seeded state; unknown refs produce a helpful "can't find it - double-check the code" draft, not an error.
**Tests:** tool unit tests: found, not-found, wrong-tenant (returns not-found, never leaks).

### T-020 `[ ]` Escalation Agent + state (3h)
**Deps:** T-013. **Stories:** US-040, part of M10.
**Read:** `design/database.md` section 6 (escalations, conversations.status); `design/frontend.md` section 6 (EscalationBanner).
**Files:** `backend/app/agents/escalation.py`, `backend/app/api/escalations.py`.
**Steps:** node creates the escalations row (reason from state: low confidence, customer request, gate failure, inspection failure), sets conversation status `escalated`, drafts the handoff message ("a human will pick this up"), terminal - no further agent turns in an escalated conversation (chat endpoint refuses agent path, allows `human_agent` messages from Surface 2 later). Customer surface shows EscalationBanner.
**Accept:** "I want to talk to a human" escalates cleanly; escalated conversations stay escalated; banner renders.
**Tests:** node test + API test (post-escalation agent turn blocked).

### T-021 `[ ]` Supervisor / Reasoning-Inspection layer (4h)
**Deps:** T-018, T-014, T-020. **Stories:** US-060.
**Read:** INDEX section 5 hard rules; frozen Architecture Doc section 4.1 note on inspection ONLY if intent unclear.
**Files:** `backend/app/agents/inspection.py`.
**Steps:**
1. Second-pass node over every draft before send. Checks, each a structured verdict: **grounding** (claims trace to retrieved provenance - LLM check with chunk list), **policy** (matches tenant tone/system_prompt constraints), **price-provenance** (re-assert the T-018 gate result - deterministic), **injection compliance** (draft does not follow instructions found inside retrieved/tool content), **prompt-leak** (no system-prompt text in draft - deterministic substring/similarity check first, LLM fallback).
2. Fail -> one re-prompt of the producing node with the verdict; second fail -> Escalation (reason `inspection:<check>`). All verdicts persisted into state and logged onto the message row (`agent_node='inspection'` trace message or metadata) for the Surface-2 trace viewer.
3. Nothing streams to the customer until inspection passes: buffer node outputs; stream the approved draft. (Latency note: acceptable at core scope; recorded as a known tradeoff.)
**Accept:** planted failures for each check (ungrounded claim, leaked system prompt line, injected instruction, bad figure) are each caught in tests; clean paths pass without visible latency disaster.
**Tests:** per-check unit tests with stubbed provider; graph-level "second failure escalates" test.

### T-022 `[ ]` [EDD] Cross-tenant leakage test - 100% or red (4h)
**Deps:** T-021. **Stories:** US-081.
**Read:** `design/database.md` sections 2.3 and 10 (`seed_leakage_pair.py`).
**Files:** `backend/seeds/seed_leakage_pair.py`, `backend/tests/test_leakage.py` (or `backend/evals/leakage_eval.py` writing eval_runs - do both: pytest wraps the eval).
**Steps:**
1. Seed two tenants, each with unique nonsense secrets planted in knowledge chunks, catalog items, pricing rules, and orders (e.g. `ZX-ALPHA-...` strings).
2. As tenant A, drive the full stack - retrieval service, recommendation, quoting, order lookup, and complete `/api/chat` conversations designed to fish for tenant B's secrets (direct asks, injection-style asks). Assert zero occurrences of B's secrets in any response, any retrieved set, any persisted row visible to A. Repeat mirrored.
3. Record as an `eval_runs` row (run_type leakage) with a pass count; the pytest wrapper fails on anything below 100%.
**Accept:** 100% pass; deliberately weakening one RLS policy in a scratch branch makes it fail (prove once, discard). Added to CI in T-029 - **it is a release criterion and is never skipped or tolerance-ed.**

---

## Week 2 Definition of Done

- [ ] End-to-end in the real customer UI: describe a need -> grounded recommendation; "repair under $X" -> tenant-priced, engine-computed, provenance-validated quote; "get me a human" -> escalation state.
- [ ] Zero model-authored figures possible: T-018 + inspection price check green, planted-violation tests in the suite.
- [ ] Leakage test 100%.
- [ ] The graph is stable - this was the week's buffer priority; do not enter phase 3 with a flaky graph.
- [ ] No lint errors, no failing/flaky tests; discoveries in `.agents/memory.md`.
