> **NAVIGATION:** Frozen source document (v2.0). The tickets here are superseded for execution by the expanded per-phase files in `docs/phases/` (same T-numbers, full detail) - work from those via `docs/INDEX.md`. This file wins on scope, cut order, and the phase-2 line only.

# WREN - 30-Day Sprint Plan & Engineering Ticket Backlog
> **Version:** 2.0 (domain-agnostic multi-tenant SaaS) | **Companion to:** Charter/PRD, Architecture, AGENTS, Research docs.
> Sized for solo + Claude Code. The 30 days deliver ONE polished end-to-end path through the full vision (Tenant 1 across all three surfaces + quoting + eval + security + the Tenant 2 config-only proof). Everything else is the explicit phase-2 list at the end.

---

## 0. HOW TO USE THIS BACKLOG
- Epics match PRD IDs (E0-E14). Estimates are focused solo+AI hours, not calendar time.
- EDD discipline: write the golden dataset/eval before the capability it tests.
- Conventions in `docs/conventions.md` apply to every ticket (style, git, bug-fix protocol, UI/pixel standard, lint/test hygiene, domain-agnostic discipline) whether or not a ticket restates them.
- Each week ends with a soft checkpoint (self-review vs the week's Definition of Done).

```
CRITICAL PATH
  Tenancy + tenant resolution + RLS (E0) -> ingestion + hybrid RAG (E2) -> retrieval eval
  (E3) -> agent graph incl. quoting + recommendation (E4/E5) -> supervisor inspection (E6)
  -> trajectory eval (E7) -> security/isolation (E8) -> observability (E9) -> the 3 surfaces
  (E10/E11/E12) -> deploy (E13) -> generalization proof (E14).

  E4/E5 (the agent graph + pricing engine) is the centerpiece; it must be stable by end of
  Week 2 or the plan is at risk. If a week runs long, cut SHOULD/COULD and phase-2 items,
  never the eval, security, or pricing-provenance MUSTs.
```

---

## WEEK 1 - TENANCY, RESOLUTION, ONBOARDING SKELETON, RAG CORE

Goal: a business can sign up, be resolved by subdomain, be onboarded conversationally into a config, upload knowledge, and get grounded hybrid-RAG answers. RLS enforced from day one.

- T-001 Monorepo scaffold (/frontend Next.js, /backend FastAPI, /infra, README, .env.example); local Postgres+pgvector; /health green. 3h.
- T-002 Full schema + migrations (all entities incl. tenants.slug, tenant_config, catalog_items, pricing_rules, quotes, platform_admins). 4h. Deps T-001.
- T-003 RLS on every tenant-scoped table + a manual "wrong tenant returns zero rows" check. 3h. Deps T-002.
- T-004 Supabase Auth wired into Next.js + FastAPI JWT middleware that sets the tenant-context session variable before queries. 4h. Deps T-003.
- T-005 Tenant resolution: `{slug}.wren.app` -> tenant_id lookup -> tenant context; local `*.localhost`/header override; wildcard-domain-ready. 4h. Deps T-004. (E0)
- T-006 Conversational onboarding skeleton (Surface-2 Copilot): guided flow that captures identity/tone/services/pricing-rules/escalation-threshold and writes tenant_config + seeds catalog_items/pricing_rules. 5h. Deps T-005. (E1)
- T-007 Knowledge upload (.md/.txt/.pdf, .csv/.json) -> documents row (status pending). 3h. Deps T-006.
- T-008 Chunk + embed (Azure) -> knowledge_chunks (tenant-scoped, tsv populated); catalog ingest as structured chunks. 4h. Deps T-007.
- T-009 Dense + sparse retrieval + RRF + cross-encoder rerank, tenant-scoped. 5h. Deps T-008. (E2)
- T-010 [EDD] Golden retrieval set (~40-60 cases) for Tenant 1 + eval script (recall@k/MRR/nDCG -> eval_runs). 5h. Deps T-008.
- T-011 Bare /chat (straight-line RAG, cited answers) to validate the pipeline before orchestration. 3h. Deps T-009,T-010.
- Week 1 buffer: fix retrieval if recall@5 << 0.85 before adding agents.

DoD W1: signup -> subdomain resolution -> conversational onboarding writes config -> knowledge ingested -> hybrid retrieval returns grounded cited answers -> retrieval eval produces real numbers. RLS verified.

---

## WEEK 2 - AGENT GRAPH, RECOMMENDATION, PRICING ENGINE, SUPERVISOR

Goal: the LangGraph supervisor + specialists work; recommendation and deterministic quoting are live; the reasoning-inspection layer guards every send.

- T-012 LangGraph state schema + graph skeleton (Supervisor -> Knowledge/Recommendation/Quoting/Order-Status/Escalation -> Inspection). 4h. Deps T-011. (E4)
- T-013 Supervisor node: intent classification + routing; low-confidence -> Escalation. 4h. Deps T-012.
- T-014 Knowledge Agent wired to hybrid retrieval + citations. 3h. Deps T-013.
- T-015 Recommendation Agent: preference-aware retrieval over catalog_items -> grounded recommendations. 4h. Deps T-013. (E4)
- T-016 Deterministic pricing engine (pure function: selections -> line items -> subtotal/tax/total in cents). 4h. Deps T-002. (E5)
- T-017 Quoting Agent: emits selected rule_codes/item refs + quantities ONLY; never a price. Persists a quotes row from engine output. 4h. Deps T-016,T-013. (E5)
- T-018 Validation gate: asserts every figure derives from the engine, no model-authored numbers, totals reconcile; re-prompt-then-escalate on failure. 3h. Deps T-017. (E5)
- T-019 Mock orders/tickets seed + `lookup_order_or_ticket` tool (typed, validated, graceful not-found). 4h. Deps T-002. (E4)
- T-020 Escalation Agent: create_escalation, clear customer handoff, terminal state. 3h. Deps T-013.
- T-021 Supervisor/Reasoning-Inspection layer: grounding + policy + price-provenance + injection + prompt-leak checks before send. 4h. Deps T-018,T-014,T-020. (E6)
- T-022 [EDD] Cross-tenant leakage test: two tenants, disjoint secrets, assert zero leakage across retrieval/recommendation/quoting/output; must pass 100%; add to CI. 4h. Deps T-021. (E8)
- Week 2 buffer (most important in the plan): stabilize the graph + pricing before Week 3.

DoD W2: end-to-end - customer describes a need -> recommendation; asks "repair under $X" -> tenant-priced quote from the engine, provenance-validated; escalation works; leakage test 100%.

---

## WEEK 3 - EVAL SUITE, CI GATE, OBSERVABILITY, TENANT CONSOLE

Goal: full three-layer eval in CI, every run traced and cost-logged, tenant admin console core screens live.

- T-023 RAGAS faithfulness/relevancy + citation-faithfulness metric. 4h. Deps T-014.
- T-024 [EDD] Judge calibration: ~30 hand-labeled cases (labeled before judge run) + agreement report. 4h. Deps T-023. (E3)
- T-025 [EDD] Golden agent-task set (~20-30 multi-step incl. quoting + recommendation scenarios). 4h. Deps T-017,T-015.
- T-026 Trajectory scorer: tool/argument correctness, step efficiency, cost-per-task, reasoning quality. 4h. Deps T-025. (E7)
- T-027 Prompt-injection defense (spotlight/delimit) + scored adversarial set (>=80%, documented). 4h. Deps T-021. (E8)
- T-028 Per-tenant cost/step caps + timeouts. 3h. Deps T-021. (E8)
- T-029 GitHub Actions CI gate: retrieval + generation + trajectory + security subsets; block on regression; prove it catches a deliberate break. 4h. Deps T-010,T-023,T-026,T-022,T-027. (E13)
- T-030 Langfuse/OTel tracing over every agent run; cost_logs per LLM call + aggregation. 5h. Deps T-021. (E9)
- T-031 Tenant admin console core (Surface 2): onboarding entry, knowledge upload + status, conversation viewer + trace drill-down, escalation queue, pricing-rules editor. 6h. Deps T-006,T-030,T-020,T-016. (E10)
- Week 3 buffer.

DoD W3: three-layer eval producing real numbers; CI gate proven; every run traced + cost-logged; tenant console core usable end-to-end incl. editing pricing rules.

---

## WEEK 4 - CUSTOMER SURFACE, PLATFORM SURFACE, DASHBOARDS, DEPLOY, GENERALIZATION, ARTIFACTS

Goal: ship it. All three surfaces live, deployed to public subdomains, Tenant 2 proves generalization, portfolio artifacts written.

- T-032 Customer chat surface (Surface 3): subdomain-hosted, streaming, clear escalation handoff, competent clean UI. 5h. Deps T-021,T-005. (E11)
- T-033 Platform-owner surface (Surface 1, minimal): protected all-tenants view + provisioning/suspension. 3h. Deps T-004. (E12)
- T-034 Dashboards in tenant console: cost (from cost_logs) + latest CI eval results. 4h. Deps T-030,T-029. (E10)
- T-035 Terraform backend infra (ECR, ECS, ALB, SGs, IAM least-priv, Secrets Manager); apply brings up, destroy tears down; /health reachable via ALB. 6h. Deps T-029. (E13)
- T-036 Dockerize + push image via CI; deploy frontend to Vercel with wildcard domain; two tenants reachable at their subdomains end-to-end. 4h. Deps T-035,T-032,T-033,T-034.
- T-037 [Time-boxed 1 day] Generalization proof: onboard Tenant 2 (dental clinic) by conversational onboarding + knowledge only, zero code changes; answers in-domain, declines/escalates out-of-domain. 6h. Deps T-036. (E14)
- T-038 Eval report (real numbers: retrieval/generation/trajectory + judge calibration + injection pass rate + quote-provenance) with the WON'T/deferral table. 4h. Deps T-029.
- T-039 Security write-up (OWASP LLM mapping, leakage test as proof, injection defense + honest pass rate, deferrals). 3h. Deps T-022,T-027.
- T-040 README (what Wren is, the three-surface diagram, setup, links) + LEARNINGS.md populated per subsystem + 5-10 min demo walkthrough video. 5h. Deps T-038,T-039.
- Day-24 buffer: bug sweep; re-run the leakage + quote-provenance tests before any "done" claim.

DoD W4 / Final (mirrors PRD section 9): all MUST pass; eval report with real numbers; leakage test + quote-provenance passing in CI; no lint/test failures; >=2 tenants live at their own subdomains; README + LEARNINGS + demo video; Tenant 2 generalization proven.

---

## 1. CUT ORDER IF THE CLOCK RUNS SHORT (most to least expendable)
```
1. Tenant 3 / online-store (C1) and other COULD items - cut first, documented
2. Conversation-simulation eval (S3), query rewriting (S2), recommendation tuning (S1)
3. Console polish beyond clean-and-functional
4. Terraform (T-035) -> fall back to console-configured ECS, document IaC as descoped;
   keep the AWS deployment itself
5. NEVER cut: pricing-engine + provenance validation, cross-tenant leakage test, the
   three-layer eval harness, the reasoning-inspection layer, the honest write-ups, or the
   AWS deployment. Falling back to a simpler host is the last resort, not a first response.
```

## 2. EXPLICIT PHASE 2 (documented, not half-built)
Billing/subscriptions on the platform-owner surface; SMS/voice/email channels; custom domains; open-ended "magic" onboarding interviewer + existing-website ingestion; per-customer memory; multi-language; team-member roles beyond owner; Tenant 3+. Each is named here so the 30-day core reads as deliberate scope, not an unfinished product.

## 3. STATUS CONVENTION
`[ ] not started  [~] in progress  [x] done  [!] blocked (note why)  [-] deferred (note why)`

---

*End of Sprint Plan & Backlog v2.0.*
