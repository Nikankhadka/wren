> **NAVIGATION:** Frozen source document (v2.0). For implementation work start at `docs/INDEX.md` - schema detail now lives in `docs/design/database.md`, UI detail in `docs/design/frontend.md`, tickets in `docs/phases/`. Load this file only when a ticket's read-list points here (e.g. sections 4.1, 6, 9) or for scope questions.

# WREN - Technical Architecture Document
> **Version:** 2.0 (domain-agnostic multi-tenant SaaS) | **Companion to:** the Charter/PRD, Sprint, AGENTS, and Research docs.
> Read before writing code. `docs/conventions.md` governs how decisions get made where this doc doesn't pin one down.

---

## 1. STACK SELECTION

| Layer | Choice | Notes |
|---|---|---|
| Frontend (all 3 surfaces) | Next.js / React / TypeScript, Tailwind | Matches base skillset. One Next.js app serves platform-owner, tenant-admin, and customer surfaces via routing + subdomain. |
| Backend (agents, RAG, pricing, eval) | Python / FastAPI | GenAI toolchain (LangGraph, RAGAS) is Python-native; already known from OpsAssist, so zero net learning cost. |
| Auth | Supabase Auth | Integrates with Postgres RLS. |
| Database | Supabase Postgres + pgvector | Dense retrieval + relational data + RLS in one service. |
| LLM | Azure OpenAI (GPT-4o-mini agents; text-embedding-3-small) behind a thin provider abstraction | Model is a config value, not hardcoded (the "constellation of models" principle at small scale - see Research doc section 2.2). |
| Orchestration | LangGraph | Explicit, inspectable supervisor/specialist graph. |
| Retrieval | pgvector (dense) + Postgres FTS (sparse) + RRF + cross-encoder rerank | No separate search engine needed at this scale. |
| Eval | RAGAS + a custom trajectory scorer (DeepEval if time allows) | Documented substitution if the clock forces it. |
| Observability | Langfuse (self-host or free tier), OTel-based | Vendor-neutral. |
| Deployment | AWS ECS Fargate + Terraform (backend), Vercel (frontend) | AWS is a named target skill; see section 9. |
| CI/CD | GitHub Actions | Free tier sufficient. |

---

## 2. THE THREE-SURFACE / MULTI-TENANT ARCHITECTURE

### 2.1 One deployment, three surfaces, tenant isolation by data

```
  PLATFORM OWNER            TENANT ADMIN (per business)      CUSTOMER (per business)
  admin.wren.app            app.wren.app (authed, scoped)    {slug}.wren.app (public, scoped)
        |                            |                                |
        +------------- Next.js app (one deployment, Vercel) ----------+
                                     |  HTTPS/REST + SSE
                                     v
                        FastAPI backend (one service, ECS Fargate)
                        auth + tenant-context, onboarding, ingestion,
                        agent graph, pricing engine, eval, metrics
                                     |
             +-----------------------+------------------------+
             v                       v                        v
        Supabase                Azure OpenAI             Langfuse
        Postgres+pgvector       (chat + embed)           (tracing, cost)
        Auth + RLS
```

There is exactly one backend deployment and one database. Tenants are isolated by `tenant_id` + RLS, never by separate deployments.

### 2.2 Tenant resolution (how a "private website" works)

- Customer surface: a request to `{slug}.wren.app` is resolved to a `tenant_id` by looking up `slug` in `tenants`. The resolved `tenant_id` is set as the request's tenant context (the Postgres session variable the RLS policies key on) before any query runs. Everything the customer sees is that tenant's data only.
- Tenant-admin surface: `tenant_id` comes from the authenticated user's membership, not the subdomain.
- Platform-owner surface: a distinct privileged role that can read across tenants through explicit, audited admin queries (not through the tenant-scoped path).
- Local/dev: subdomains via `*.localhost` or a header override; production via a Vercel wildcard domain.

### 2.3 Domain-agnostic enforcement

All vertical behavior is `tenant_config` + uploaded knowledge. There is no vertical branch in agent, retrieval, pricing, or tool code. A test asserts the agent codebase contains no vertical-name conditionals (a simple guard, but it makes the principle enforceable).

---

## 3. DATA MODEL (core entities)

```
tenants(id, slug UNIQUE, name, status, created_at)
tenant_config(tenant_id UNIQUE, system_prompt, tone, enabled_tools jsonb,
              escalation_threshold, brand jsonb, config jsonb)
users(id, tenant_id, role)                        -- role: 'owner' | 'staff'
platform_admins(user_id)                            -- surface-1 privileged users

documents(id, tenant_id, filename, doc_type, status, uploaded_at)
knowledge_chunks(id, tenant_id, document_id, content, embedding vector, metadata jsonb,
                 tsv tsvector)                       -- RLS + always tenant-filtered

catalog_items(id, tenant_id, name, description, attributes jsonb, active)  -- for recommendation
pricing_rules(id, tenant_id, code, label, unit_amount_cents, unit, conditions jsonb, active)
quotes(id, tenant_id, conversation_id, line_items jsonb, subtotal_cents, tax_cents,
       total_cents, status, created_at)             -- totals ALWAYS from the pricing engine

conversations(id, tenant_id, customer_ref, channel, status, created_at)
messages(id, conversation_id, role, content, agent_node, created_at)
tool_calls(id, message_id, tool_name, arguments jsonb, result jsonb, success, latency_ms)
orders(id, tenant_id, ...)                           -- mock order/ticket data, seeded
escalations(id, tenant_id, conversation_id, reason, status, created_at)

eval_runs(id, tenant_id, run_type, metrics jsonb, git_sha, created_at)
eval_cases(id, tenant_id, case_type, input jsonb, expected jsonb)
cost_logs(id, tenant_id, conversation_id, model, input_tokens, output_tokens, cost_usd, created_at)
```

RLS on every table carrying `tenant_id`.

---

## 4. AGENT ARCHITECTURE

### 4.1 The graph (LangGraph)

```
 customer msg -> Supervisor (classify + route)
                    |-> Knowledge Agent    (RAG, cited answers)
                    |-> Recommendation Agent(preference-aware catalog retrieval)
                    |-> Quoting Agent       (selects pricing rules/items + quantities)
                    |-> Order/Status Agent  (lookup_order_or_ticket tool)
                    |-> Escalation Agent    (human handoff, terminal)
                    v
                 Supervisor / Reasoning-Inspection layer
                    (grounding, policy, price-provenance, injection, prompt-leak)
                    v
                 streamed to customer + logged + cost-tracked
```

- Supervisor routes on intent; low confidence routes to Escalation rather than guessing.
- Quoting Agent NEVER emits a price. It emits selected `pricing_rules.code` values + quantities + any `catalog_items` refs; the pricing engine (section 5) computes money.
- Supervisor/Reasoning-Inspection is the upgraded validator (Research doc section 2.3): a second pass that inspects the primary output for grounding, on-policy behavior, price provenance (every figure traces to the pricing engine), injection compliance, and system-prompt leakage. This is the single most important reliability pattern; the 90% x 90% -> 99% intuition is why it exists.

### 4.2 Model choice & cost
GPT-4o-mini for agents (native tool-calling, cheap); text-embedding-3-small for embeddings; Cohere Rerank (free tier) or a small cross-encoder. All behind the provider abstraction so the model is not load-bearing on a version. Cost-per-conversation and cost-per-quote are logged (section 8) and reported with real numbers, not estimates.

---

## 5. DETERMINISTIC PRICING / QUOTING ENGINE (confirmed in scope)

This is the safety centerpiece and the pattern both Sierra and Decagon enforce (Research doc section 2.4).

- Input: the Quoting Agent passes structured selections - `[{rule_code, quantity}, {catalog_item_id, quantity}, ...]` plus any tenant tax flags.
- Computation: a pure, non-LLM function reads the tenant's `pricing_rules`/`catalog_items`, computes each line in integer cents, applies tax per tenant config, and returns line items + subtotal + tax + total.
- Validation gate: sits between agent output and the customer. It asserts (a) every monetary figure in the response derives from the engine's output, (b) no number was authored by the model, (c) totals reconcile. Failure re-prompts the agent up to a strict limit, then escalates. A model-authored price is a contract violation, caught here, and covered by a provenance test (a release criterion).
- Rules editing: tenant admins edit `pricing_rules` in the console; changes apply to new quotes only, never retroactively to sent quotes.

This gives "phone screen repair under $X" as a safe, provable capability: the agent picks the screen-repair rule + model tier; the engine computes; the validator guarantees the model never invented the figure.

---

## 6. CONVERSATIONAL ONBOARDING (Surface-2 Copilot)

- A guided conversational flow (not an open-ended interviewer at core scope) walks the business through: identity + tone, services/products, pricing rules, escalation threshold, and knowledge upload.
- It writes `tenant_config` and seeds `catalog_items`/`pricing_rules` from the conversation, then triggers ingestion of uploaded docs, and confirms captured state before the tenant goes live.
- It is domain-agnostic: the same flow configures a dentist or a butcher; only the captured data differs.
- Phase 2: a more open-ended interviewer that infers structure from freeform description and existing-website ingestion.

---

## 7. SECURITY & PRIVACY (OWASP LLM Top 10, right-sized)

- LLM01 Prompt injection: spotlight/delimit retrieved content and tool output as data; input-scan user messages; scored adversarial set (direct + indirect via poisoned chunk).
- LLM08 Vector/tenant isolation (signature story): `tenant_id` filter on every retrieval + Postgres RLS on all tenant tables; the cross-tenant leakage test (seed two tenants with disjoint secret facts, assert zero leakage through retrieval, recommendation, quoting, and agent output) must pass 100%.
- LLM10 Unbounded consumption: per-tenant per-day token/cost budgets, agent step caps, tool/LLM timeouts.
- LLM07 System-prompt leakage: the reasoning-inspection layer checks outgoing responses; secrets live in env/secret manager, never in prompts.
- Classic web security: Supabase auth, tenant-scoped route protection, input validation, no committed secrets. Platform-owner routes gated to `platform_admins`.
- Deliberately deferred (documented): full guardrails framework, formal red-team beyond the adversarial set, SSO/compliance certs.

---

## 8. OBSERVABILITY & COST
- OTel-based tracing via Langfuse/Phoenix over every agent run (supervisor routing, retrieval, tool calls, pricing calls, generation, inspection).
- Per-LLM-call cost logged to `cost_logs`; aggregated per tenant/day/conversation and per quote; surfaced in the tenant console and (aggregate) the platform-owner surface.

---

## 9. DEPLOYMENT ARCHITECTURE (AWS)

```
 Internet
   |-- Vercel (Next.js: all 3 surfaces; wildcard *.wren.app for tenant subdomains)
   |-- Application Load Balancer (public, TLS) --> ECS Fargate task (FastAPI backend,
   |         0.25 vCPU / 0.5GB, public subnet, no NAT) --> Secrets Manager, CloudWatch Logs
   |         image from ECR
 External: Supabase (Postgres+pgvector+Auth+RLS), Azure OpenAI, Langfuse.
```

- Terraform root module: ECR, ECS cluster/service/task-def, ALB + target group + listener, security groups (ALB -> task only), least-privilege IAM (task-execution role: ECR pull + logs; task role: scoped Secrets Manager ARNs), Secrets Manager resources. `terraform apply` brings it up, `terraform destroy` tears it down.
- No NAT Gateway (public subnet + SG lock-down) - documented cost-driven simplification (~$32/mo avoided).
- Vercel wildcard domain resolves tenant subdomains; the frontend passes the resolved slug to the backend, which sets tenant context for RLS.
- Cost note: a small always-on Fargate task is ~$10-20/mo; scale to 0 tasks between demo sessions and set a CloudWatch billing alarm.

---

## 10. RETRIEVAL PIPELINE DETAIL
Query (optionally rewritten vs history) -> dense (pgvector) top-N + sparse (FTS) top-N -> RRF fuse -> cross-encoder rerank to top-k -> generation with required citations -> citation-faithfulness validation. For recommendation, the same retrieval runs over `catalog_items` with preference-aware query construction. Every stage is independently swappable and every swap is run through retrieval eval with a before/after number.

---

*End of Architecture Document v2.0. Proceed to the Sprint Plan.*
