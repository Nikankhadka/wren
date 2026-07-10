> **NAVIGATION:** Frozen source document (v2.0). For implementation work start at `docs/INDEX.md` - it routes each phase to the derived working docs (`design/`, `phases/`), so you do not need to load this file. This file wins on scope questions only.

# WREN - Charter & Product Requirements Document
> **Version:** 2.0 (supersedes 1.0 - domain-agnostic multi-tenant SaaS pivot) | **Type:** Solo portfolio venture - personal learning + capstone-grade artifact
> **Author:** Ronin Khadka | **Build clock:** 30-day polished core, with an explicit phase 2 for the rest of the vision
> **Status:** Draft for founder sign-off. Conventions in `Wren_AGENTS.md` govern how this gets built.

---

## 0. HOW TO READ THIS PACKAGE

Five linked documents, meant to be handed to a coding agent (Claude Code) as a work order:

1. `Wren_P0P1_CharterAndPRD.md` (this file) - what we build and why, the three-surface SaaS model, personas, scope, user stories.
2. `Wren_P3_ArchitectureDoc.md` - stack, tenancy/tenant-resolution, system design, data model, API, agent architecture, pricing engine, security, observability.
3. `Wren_P3_SprintPlanAndBacklog.md` - the realistic 30-day core plan, epics to tickets, and the explicit phase-2 line.
4. `Wren_AGENTS.md` - how work gets done: style, git, the quality-over-dev-cost rule, bug-fix protocol, UI and engineering-hygiene standards, and the domain-agnostic discipline.
5. `Wren_Research_CloningAndLearningPlan.md` - market grounding (Sierra/Decagon reference architecture), the cloning strategy, and the expert learning roadmap.

---

## 1. CHARTER

```
IDEA (one sentence)
  A domain-agnostic, multi-tenant SaaS where any business - dentist, deli, butcher,
  pastry shop, phone/repair shop, online store - signs up, describes itself in a
  conversation, and gets its own private, branded AI support-and-sales agent that
  recommends, quotes, answers, and escalates to a human when it should.

PROBLEM HYPOTHESIS
  Small businesses across every vertical share the same unmet need: 24/7, accurate,
  action-capable customer conversations grounded in *their* data, without hiring a
  support team and without a developer to set it up. The traditional path - a website
  with browse/search/filter/FAQ - pushes work onto the customer. A single conversational
  agent that says "phone screen repair, under $120, here's the quote" replaces all of it.

WHY DOMAIN-AGNOSTIC (the load-bearing decision)
  The product is not "an e-commerce support tool." It is a platform whose code knows
  nothing about any vertical. Everything domain-specific lives in per-tenant config and
  per-tenant uploaded knowledge. "Works for any business" is therefore not a feature we
  build - it is what we get by *refusing to hardcode any vertical anywhere in agent logic*.
  This is exactly the Sierra/Decagon "goals and guardrails, not scripted steps" pattern
  (see Research doc). The discipline IS the product.

WHY THIS SHAPE (portfolio-first framing)
  The primary buyer of this artifact is a hiring panel for a mid-level Full Stack / GenAI
  Engineer role, with a Forward Deployed Engineer trajectory. Every scope call is filtered
  through "does this prove AI-engineering depth and production judgment?" The research doc
  shows this exact stack - RAG, agent orchestration, evaluation, observability, security,
  multi-tenancy - is what those roles hire for.

CONSTRAINTS
  Timeline: 30 days for a polished end-to-end core; the rest is documented phase 2.
  Budget:   Bootstrapped. Free/low-cost tiers. AWS backend (a named target skill) is the
            one deliberate paid exception.
  Team:     Solo (Ronin) + Claude Code as pair-programmer.
  Stack:    Next.js/TS frontend (all three surfaces) + Python/FastAPI backend (agents,
            RAG, pricing, eval) + Supabase (Postgres + pgvector + Auth + RLS). AWS ECS
            Fargate + Terraform for the backend, Vercel for the frontend.

DEFINITION OF A WIN
  A working, deployed, demoable multi-tenant SaaS where:
    - a new business self-onboards via a conversation and gets a private agent at its own
      subdomain, with zero code written for that business;
    - the agent recommends, answers from the business's own knowledge, and produces
      deterministic quotes (model selects inputs, code computes the price);
    - a second business in a completely different vertical is onboarded by config alone,
      proving domain-agnosticism;
    - there is a numbers-backed evaluation report (retrieval + generation + trajectory);
    - there is a proven cross-tenant isolation guarantee (RLS + passing leakage test) and
      a documented prompt-injection defense;
    - every deferred item is written up as "considered, out of scope, and why."

OUT OF SCOPE FOR THE 30-DAY CORE (full reasoning in section 6)
  Billing/subscriptions automation, multi-channel (SMS/voice/email), custom domains
  (subdomains only at core), rich per-vertical UI, fine-tuning, SSO/compliance certs,
  multi-language. These are phase 2, not permanent cuts (except fine-tuning and certs).
```

---

## 2. THE THREE-SURFACE SAAS MODEL (the heart of v2.0)

Wren is one application, deployed once, serving three distinct front-end surfaces. Understanding this separation is understanding how Wren is a SaaS. There is NEVER a separate deployment per business - one codebase, one deployment, tenant isolation by data.

### Surface 1 - Platform Owner (you)
A super-admin surface only the platform operator sees. Lists every tenant, provisions/suspends them, and (phase 2) handles subscriptions and billing. This is what makes you the SaaS vendor rather than the app being one business's internal tool. At core scope this is intentionally minimal - a protected internal view over all tenants plus provisioning - not a billing product.

### Surface 2 - Tenant Admin (each business)
When a business signs up, it lands in its own admin console, scoped entirely to its `tenant_id`. Here it onboards conversationally (Surface-2 Copilot interviews it and writes its own config), uploads knowledge, watches its conversations, handles escalations, sets its quoting rules, and sees its costs. The dentist and the butcher get the identical console populated with entirely different data; neither can see the other.

### Surface 3 - Customer (each business's customers)
Each tenant gets a private customer chat at `{tenant-slug}.wren.app` (subdomain per tenant). To the customer it looks like that business's own support. It is scoped to exactly one tenant - the agent only knows that business's knowledge and only ever touches that business's data. "Customers accessing it as a private website" = this surface, resolved by subdomain to a `tenant_id`.

> The mental shift that resolves the original confusion: "private website" does NOT mean a separate deployment. It means one app resolving which tenant a visitor belongs to (by subdomain) and showing only that tenant's world.

---

## 3. TENANCY & THE DOMAIN-AGNOSTIC PRINCIPLE

- A tenant is a row keyed by `tenant_id`. All tenant data (config, knowledge, conversations, quotes, orders) carries it. Postgres Row-Level Security enforces isolation at the database layer, not just the application layer.
- The dentist and the butcher run identical code on identical servers. They differ ONLY in (a) their uploaded knowledge and (b) their `tenant_config`.
- Hard rule (also in AGENTS.md): no `if vertical == "dentist"` anywhere in agent, retrieval, pricing, or tool logic. Any vertical-specific behavior is data, never code. A single such branch breaks the entire domain-agnostic claim and is treated as a bug.

---

## 4. PERSONAS

**Priya - Tenant Admin (primary buyer/operator).** Runs a small business, not technical. Wants to describe her business in a chat, upload her price list and policies, and get a working agent she trusts enough to leave running. Success: she self-serves setup with zero developer help.

**Alex - End Customer.** A customer of Priya's business with a question, a product need, or a repair to price. Wants a fast, correct answer or quote, and a real human when needed - no dead ends. Success: answered, quoted, or escalated in one exchange.

**You - Platform Owner.** Operate the SaaS: see all tenants, provision them, keep the platform healthy. Success: a new tenant can be live without you touching code.

**(Portfolio-only) The Hiring Panel.** Wants, in under 10 minutes, evidence of multi-agent orchestration, real tool use and quoting, rigorous evaluation, security-mindedness, and multi-tenant SaaS system design. Kept in mind when deciding what to make *visible* (dashboards, eval report, the generalization demo).

---

## 5. REFERENCE TENANTS (diverse on purpose)

To build, evaluate, and demo a domain-agnostic platform, we use deliberately different example tenants. These are swappable examples, not hardcoded verticals.

| | Anchor: Phone shop & repair (Tenant 1) | Generalization proof: Dental clinic (Tenant 2) | Stretch: Online store (Tenant 3) |
|---|---|---|---|
| Why | Exercises every capability at once: recommend (phones/accessories), quote (repairs, deterministic), status (repair tickets), FAQ/policy (RAG), escalation | Maximally different: a health service, no products, no repairs - proves "any domain" | Classic orders/returns/WISMO |
| Build depth | Full build + full eval | Config-only onboarding (the proof) | Only if clock allows |

Tenant 1 is the primary build-and-eval anchor because it naturally uses recommendation + deterministic quoting + status + RAG + escalation in one place. Tenant 2 is the config-only generalization proof, and being health-services-with-no-products makes the "domain-agnostic" claim vivid.

---

## 6. MVP SCOPE - MoSCoW

### MUST (the 30-day polished core)
- M1. Multi-tenant auth + workspace, RLS-enforced isolation on every tenant-scoped table.
- M2. Tenant resolution by subdomain: `{slug}.wren.app` resolves to a `tenant_id`; the customer surface is scoped to it.
- M3. Conversational onboarding (Surface-2 Copilot): interviews the business through a guided conversation and writes its `tenant_config` (identity, tone, services/products, pricing rules, escalation threshold) and triggers knowledge ingestion. Guided/structured-conversational at core scope, not an open-ended magic interviewer.
- M4. Knowledge ingestion pipeline: upload policies/FAQ/catalog/price list; chunk, embed, store in pgvector, tenant-scoped.
- M5. Hybrid retrieval: dense (pgvector) + sparse (Postgres FTS) + RRF + cross-encoder rerank.
- M6. Multi-agent orchestration (LangGraph): a Supervisor routes to specialists - Knowledge (RAG), Recommendation, Quoting, Order/Status, Escalation.
- M7. Tool calling: `search_knowledge`, `recommend_items`, `lookup_order_or_ticket`, `get_quote_inputs`, `create_escalation` - typed, validated, structured error handling.
- M8. Deterministic pricing/quoting engine: the agent selects priced items/rules and quantities from the tenant's data; a non-LLM engine computes the total in integer cents. A model producing a price directly is a contract violation caught by a validation gate. (Confirmed in scope.)
- M9. Supervisor / reasoning-inspection layer: a second-pass check over the primary agent's output for grounding, policy adherence, price-provenance, injection, and prompt-leak, before anything reaches the customer (the Sierra/Decagon supervisor pattern).
- M10. Human-in-the-loop escalation as a first-class state, surfaced in the tenant admin queue.
- M11. Evaluation harness: golden datasets for retrieval (recall@k, MRR), generation (faithfulness, relevancy, citation-faithfulness), and trajectory (tool/argument correctness, step efficiency, cost-per-task), plus judge calibration.
- M12. CI regression gate (GitHub Actions) blocking on regression beyond tolerance.
- M13. Prompt-injection defense (spotlighting + input scan) with a scored adversarial set.
- M14. Cross-tenant isolation proven: RLS + an automated leakage test that must pass at 100%.
- M15. Observability: OpenTelemetry tracing (Langfuse/Phoenix) + per-tenant, per-conversation token/cost accounting.
- M16. Tenant admin console (Surface 2): onboarding, knowledge, conversation viewer with trace drill-down, escalation queue, pricing-rules editor, cost + eval dashboards.
- M17. Customer chat surface (Surface 3): subdomain-hosted, streaming, clear escalation handoff.
- M18. Platform-owner surface (Surface 1), minimal: protected all-tenants view + provisioning.
- M19. Deployment: backend on AWS ECS Fargate via Terraform; frontend on Vercel; CI/CD via GitHub Actions.
- M20. Generalization proof: onboard Tenant 2 (dental clinic) by config + knowledge only, zero code changes.

### SHOULD
- S1. Recommendation quality tuning (preference-aware retrieval over the catalog).
- S2. Query rewriting for multi-turn.
- S3. Conversation-simulation eval (an LLM persona drives a full conversation; score the trajectory) - the Decagon simulation pattern.

### COULD
- C1. Tenant 3 (online store).
- C2. Contextual retrieval / semantic chunking with before/after numbers.
- C3. Semantic caching. C4. Load testing.

### WON'T (30-day core) - with reasoning
| Deferred | Why |
|---|---|
| Subscriptions/billing automation | Phase 2. The platform-owner surface proves the SaaS shape without a billing product eating the clock. |
| SMS/voice/email channels | Phase 2. The chat surface already proves the agent; extra channels are integration volume, low incremental AI signal. |
| Custom domains (vs subdomains) | Phase 2. Subdomains prove private-per-tenant access; custom domains are DNS/cert plumbing. |
| Open-ended "magic" onboarding interviewer | Guided-conversational onboarding proves the concept; a fully open interviewer that reliably configures any business is itself a hard agent-research problem, deferred. |
| Fine-tuning, SSO/SOC2 certs, multi-language | Poor time-to-signal for a solo 30-day portfolio core; documented as deliberate. |

---

## 7. TIMELINE REALITY (honest, per AGENTS.md quality-over-cost rule)

The v2.0 vision is a genuine multi-tenant SaaS and exceeds a naive 30-day build. Handling: the 30 days deliver ONE polished end-to-end path - Tenant 1 fully built across all three surfaces with quoting and eval and security, plus the Tenant 2 config-only proof. Anything not needed for that polished path (billing, extra channels, custom domains, tenant 3, the richer onboarding) is phase 2, documented, not half-built. Scope boundaries are fixed; quality within them is not compromised. If a core ticket threatens the clock, flag it rather than silently cutting quality or blowing the date.

---

## 8. SUCCESS METRICS
- Retrieval recall@5 >= 0.85 (report actual).
- Generation faithfulness >= 0.85, relevancy >= 0.85.
- Trajectory tool-call correctness >= 90%.
- Quote correctness: 100% of quotes derive every figure from the pricing engine (zero model-authored prices) - non-negotiable.
- Cross-tenant leakage test: 100% pass - non-negotiable.
- Prompt-injection set: >= 80% pass, documented honestly.
- Judge calibration: >= 80% agreement with human labels.
- Generalization: Tenant 2 onboarded with zero code changes.

## 9. RELEASE CRITERIA
```
- All MUST items (M1-M20) pass their acceptance criteria
- Numbers-backed eval report against the golden datasets
- Cross-tenant leakage test passing in CI
- Zero model-authored prices (pricing-engine provenance test passing)
- No known lint errors, no failing/flaky tests in CI (AGENTS.md section 7)
- Live deployment: at least two tenants reachable at their own subdomains
- README with architecture diagram, setup, and the deferral rationale table
- LEARNINGS.md populated per subsystem (Research doc section 4.1)
- A recorded 5-10 minute walkthrough
```

---

## 10. USER STORIES (epic-level; ticket detail in the Sprint doc)

### E0 - Foundations, Multi-Tenancy & Tenant Resolution
- US-001 As a business, I sign up and get an isolated, RLS-enforced workspace.
- US-002 As a platform, `{slug}.wren.app` resolves a visitor to exactly one tenant; the customer surface only ever sees that tenant's data.
- US-003 As a developer, all tenant behavior is driven by `tenant_config` + uploaded knowledge - no vertical-specific code branches anywhere.

### E1 - Conversational Onboarding (Surface-2 Copilot)
- US-010 As a business admin, an onboarding conversation interviews me about my business, services/products, pricing rules, tone, and escalation preferences, and writes my `tenant_config` for me.
- US-011 As a business admin, the same flow ingests my uploaded knowledge and confirms what it captured before going live.

### E2 - Ingestion & Hybrid RAG
- US-020 Upload policies/FAQ/catalog/price list; chunk, embed, tenant-scoped store.
- US-021 Hybrid retrieval (dense + sparse + RRF) with cross-encoder rerank.

### E3 - Retrieval & Generation Eval
- US-030 Golden retrieval set -> recall@k/MRR/nDCG. US-031 RAGAS faithfulness/relevancy + citation-faithfulness. US-032 Judge calibration vs human labels.

### E4 - Agent Orchestration
- US-040 Supervisor routes to Knowledge / Recommendation / Quoting / Order-Status / Escalation.
- US-041 As a customer, I describe a need and get a grounded recommendation from the tenant's catalog.
- US-042 As a customer, I ask "screen repair under $X" and get an accurate, tenant-priced answer.

### E5 - Deterministic Pricing/Quoting Engine
- US-050 The agent emits selected rule/item IDs + quantities; the non-LLM engine computes totals in cents; a validation gate rejects any model-authored figure.
- US-051 As a business admin, I edit my pricing rules and quotes reflect them, with no retroactive change to already-sent quotes.

### E6 - Supervisor / Reasoning Inspection
- US-060 A second-pass supervisor checks grounding, policy, price-provenance, injection, and prompt-leak before any customer-facing send.

### E7 - Trajectory Eval
- US-070 Score agent trajectories on tool/argument correctness, step efficiency, and cost-per-task over a golden agent-task set.

### E8 - Security & Isolation
- US-080 Spotlight/delimit retrieved + tool content; scored adversarial injection set.
- US-081 RLS on every tenant table + a 100%-passing cross-tenant leakage test.
- US-082 Per-tenant cost/step caps and timeouts.

### E9 - Observability & Cost
- US-090 Trace every agent run (OTel/Langfuse). US-091 Per-tenant, per-conversation token/cost logged and dashboarded.

### E10 - Tenant Admin Console (Surface 2)
- US-100 One place: onboarding, knowledge, conversation viewer + trace, escalation queue, pricing-rules editor, cost + eval dashboards.

### E11 - Customer Chat Surface (Surface 3)
- US-110 Subdomain-hosted streaming chat with a clear human-handoff state.

### E12 - Platform-Owner Surface (Surface 1)
- US-120 Protected all-tenants view + tenant provisioning/suspension.

### E13 - Deploy & CI/CD
- US-130 Terraform-provisioned AWS backend + Vercel frontend; eval suite gates CI.

### E14 - Generalization Proof
- US-140 Onboard Tenant 2 (dental clinic) by config + knowledge only; it answers in-domain and declines/escalates out-of-domain, on identical code.

---

*End of Charter & PRD v2.0. Proceed to the Architecture Doc.*
