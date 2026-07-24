# Wren - Progress Tracker

**The one page to check to know where the build is.** Every ticket in the project is listed below with its status, the commit that delivered it, and a one-line plain-English summary of what that commit actually did.

**Right now:** Phases 1 and 2 are fully done. Phase 3 (Eval, CI & console) is done except T-024, which is committed but blocked pending founder hand-labeling (see its phase-file status note). Phase 4 (Ship) is nearly complete: T-032 done, T-033 done (backend + frontend), T-034 done (backend + frontend dashboards), T-035 Terraform + lean image landed (live apply pending founder AWS secrets), CI/CD split into a development gate (`ci.yml`) and a production pipeline (`deploy.yml`, T-036 skeleton, dormant until T-035's secrets exist), T-037 generalization proof done. The portfolio artifacts are written: T-038 eval report and T-039 security write-up are done; T-040 README + LEARNINGS are done with only the demo-video recording (a founder step) outstanding. The two remaining gates on shipping are both external: T-036 live deploy (needs AWS/Vercel/Supabase secrets) and clean HEAD-fresh LLM-judged eval numbers (needs a paid/Azure key - the free tier throttles the re-runs).

## How to read this file

- The whole build is 40 tickets (T-001 to T-040), grouped into 4 phases. One ticket = one commit, and the commit message always starts with the ticket number (e.g. `T-015: Recommendation Agent`), so `git log --oneline` lines up 1:1 with this table.
- For the full technical detail of any ticket, open its entry in the matching `docs/phases/` file. For the full story of any commit, run `git show <hash>` - commit bodies are written in plain language.
- **Statuses:** `done` | `in progress` | `not started` | `blocked (why)` | `deferred (why)`.
- **Keeping it updated:** whoever commits a ticket (human or agent) fills in that ticket's row - status, commit hash, one-line summary.

## Phase 0 - Planning & scaffolding (done)

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| Planning docs + scaffold | done | `b910a50` | Wrote the full documentation system (planning, design, phase ticket files) and created empty frontend/backend/infra project skeletons with a working `/health` endpoint. |
| Review fixes | done | `c2101e2` | Fixed the issues found when reviewing the phase-0 work. |

## Phase 1 - Foundations (done)

Goal: a business can sign up, get its own subdomain, describe itself through a conversation, upload documents, and ask questions that get answered from those documents with citations.

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| T-001 Monorepo scaffold | done | `b910a50` | Project skeleton (delivered with the phase-0 commit). |
| T-002 Full schema + migrations | done | `3d070d5` | Created every database table as forward-only SQL migrations, plus a test suite. |
| T-003 RLS enforcement + schema audit | done | `c0b798b` | Locked every tenant table with row-level security so one business can never read another's data. |
| T-004 Auth + tenant provisioning | done | `d1826e4` | Supabase login/signup, plus a signup flow that creates a new tenant with its own admin user. |
| T-005 Tenant resolution by subdomain | done | `075e17a` | Visiting `bytefix.wren.app` resolves to the right tenant and loads its branding. |
| T-006 Conversational onboarding | done | `d92ca24` | New businesses describe themselves in a chat; an LLM extracts structured config the admin confirms. |
| T-007 Knowledge upload | done | `8a7b472` | Admins upload documents (PDFs, text) that become the business's searchable knowledge base. |
| T-008 Chunk + embed pipeline | done | `d8b0a43` | Uploaded documents get split into ~400-word chunks and embedded as vectors. |
| T-009 Hybrid retrieval | done | `9c27859` | Search combining dense (vector) and sparse (full-text) retrieval, then cross-encoder reranking. |
| T-010 Golden retrieval set + eval | done | `182985a` | 50 hand-written test questions with known answers, plus an eval script scoring retrieval quality. |
| T-011 Bare /chat with citations | done | `300699a` | First real customer chat: streamed answers from the business's own documents with citations, plus fixed a latent CORS bug. |

## Phase 2 - Agents & pricing (done)

Goal: replace straight-line chat with a team of specialist agents (a supervisor routes each message), plus the deterministic pricing engine where no LLM ever makes up a price.

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| T-012 LangGraph state schema + graph skeleton | done | `82322b9` | Set up the agent graph with a supervisor node and five specialist slots; T-011 chat became the Knowledge specialist. |
| T-013 Supervisor routing | done | `731b622` | Supervisor classifies each customer message and routes to the right specialist; low confidence always escalates in code. |
| T-014 Knowledge Agent | done | `0b99a71` | Dedicated test for the Knowledge agent node (logic already delivered by T-012). |
| T-015 Recommendation Agent | done | `c023918` | "What should I buy?" now gets catalog-sourced product recommendations; prices come from the DB, never the model. |
| T-016 Deterministic pricing engine | done | `eda876f` | Pure-math quote calculator: agents pick rules/items, the engine computes every total in integer cents. |
| T-017 Quoting Agent | done | `8e6b9e5` | Customers get real quotes: the model selects services/items (never sees prices), the engine computes totals, quotes render as QuoteCards. |
| T-018 Validation gate: price provenance | done | `7247a1c` | Every dollar figure in a reply is checked against what the pricing engine actually computed; unexplained figures trigger rewrite-then-escalate. |
| T-019 Mock orders seed + lookup tool | done | `ecd2b31` | "Where's my order R-1042?" gets a real answer via a deterministic DB lookup, never guessed by the model. |
| T-020 Escalation Agent + state | done | `c10b742` | Escalation is now a terminal dead-end: creates an escalations row, flips the conversation to escalated, permanently replaces the chat box with a handoff banner. |
| T-021 Reasoning-inspection layer | done | `e4db924` | Every AI reply passes a final review (grounding, policy, injection, prompt-leak, price-provenance re-check) before streaming to the customer. |
| T-022 Cross-tenant leakage test | done | `e7be3d2` | Proved with real tests (demanding 100%, never skipped) that two tenants can never see each other's data - including a deliberate break-then-restore proof the suite has teeth. |

## Phase 3 - Eval, CI & console (done except T-024)

Goal: measure answer quality automatically (and gate CI on it), defend against prompt injection, track per-tenant cost, and build the tenant admin console.

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| T-023 Generation eval (RAGAS + citation-faithfulness) | done | `aed2086` | Automated grader checking faithfulness (every claim traces to retrieved context), answer relevancy, and per-citation support. |
| T-024 Judge calibration | blocked (founder hand-labeling) | `19d68e0` | Pipeline and 29-case dataset built; blocked on founder hand-labeling (the calibration measures LLM-judge agreement against real human judgment - agent-generated labels would be circular). |
| T-025 Golden agent-task set | done | `22f9cae` | 30 annotated customer conversations (every specialist exercised 4+ times) with expected routes, selections, and must-not-do rules. |
| T-026 Trajectory scorer | done | `cd868c4` | Runs T-025's 30 cases through the real agent and grades routing, tool-call correctness, step efficiency, and cost per conversation. |
| T-027 Prompt-injection defense + adversarial set | done | `598f3a7` | Spotlight delimiters fence untrusted tenant data before reaching the LLM; 29-case attack set scored 96.7% blocked. |
| T-028 Per-tenant cost/step caps + timeouts | done | `ad07483` | Daily cost/token ceilings + loop-protection step cap + per-call timeouts, all degrading gracefully to a human-handoff message. |
| T-029 CI regression gate | done | `46c3be4` | CI workflow lints, typechecks, tests both stacks against a throwaway DB, then runs the eval suite (absolute gates for security, regression gates for LLM-judged quality). |
| T-030 Tracing + cost accounting | done | `e2f5034` | Every LLM call is cost-tracked (contextvar-based, per-turn); spans cover every graph node (scalar-only attributes, no cross-tenant content). |
| T-031 Tenant admin console core | done | `daea6d3`, `b9b561f` | Conversations tab (list + per-message drill-down with traces), Escalations tab (claim + resolve with customer-visible reply), Pricing tab (inline edit, dollars->cents on server). |

## Phase 4 - Ship (8/9 done; T-036 + demo video pending, founder-blocked)

Goal: polish all three surfaces, deploy to real infrastructure, and prove domain-agnosticism by onboarding a second, totally different business with zero code changes.

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| T-032 Customer chat surface - final polish | done | `c0adc77` | Every state from the frontend spec's 7.1 checklist works against the seeded tenant: greeting, starter chips, streaming with stop, QuoteCard, citations, refusal, escalation, runtime brand-accent with AA contrast gate, mobile pass at 375px. |
| T-033 Platform-owner surface | done | `b8a2f5b`, `07b8b13` | Admin console at `admin.*`: all-tenants list with metrics, provision-tenant modal, suspend/reactivate. Backend then frontend landed separately. |
| T-034 Tenant dashboards: cost + eval | done | `1aab440`, `cb9905c` | Dashboard tab in tenant console: cost MetricCards with 30-day sparkline, eval pass/fail checks against gate thresholds. Backend then frontend landed separately. |
| T-035 Terraform AWS backend | done | `d368b03` | Full 7-file Terraform stack (VPC, ALB, ECR, ECS Fargate, IAM, Secrets Manager, billing alarm) plus a lean production Docker image. Live `terraform apply` is a founder step (needs AWS secrets). |
| T-036 Deploy end-to-end (CI image push + Vercel wildcard) | not started | - | Blocked on founder AWS/Vercel/Supabase credentials. Deploy skeleton (`deploy.yml`) exists and no-ops gracefully without secrets. |
| T-037 Generalization proof: Tenant 2 by config alone | done | `2b8437d` | Dental clinic live on identical code through the public API alone - zero code changes. Full evidence: `docs/artifacts/generalization-proof.md`. |
| T-038 Eval report | done | _pending commit_ | Every quality number traced to its `eval_runs` row with methodology, gate thresholds, and honest analysis of free-tier misses. See `docs/artifacts/eval-report.md`. |
| T-039 Security write-up | done | _pending commit_ | OWASP LLM Top 10 mapping with exact code + test pointers per control, plus deliberate deferrals stated as decisions. See `docs/artifacts/security.md`. |
| T-040 README + LEARNINGS + demo video | in progress | _pending commit_ | `README.md` gained architecture diagram + artifacts table + deferral rationale; `LEARNINGS.md` written per subsystem. Only the 5-10 min demo-video recording remains (founder step). |

## Unticketed founder additions

| Work | Status | Commit | What was done |
|---|---|---|---|
| Marketing landing page | done | `b2c46e9` | Bare `wren.app`/`www.` serves a marketing landing page routing visitors to their front door: business owners to signup, customers to the demo chat, platform operator to admin login. |
| Full visual rebrand (LuxeStay M3 system) | done | `cc30fc5`, `86b03d9`, `5d2bb7d` | Material 3 tonal role ramp system (crimson primary, teal secondary, green tertiary) with Inter font, bento MetricCards, pill Badges, vendored Material Symbols icons. Component code was untouched by design (tokens-only change). |
| Marketing pages (/product /pricing /demo /about) | done | `27537d7` | Four public content pages behind the marketing nav: product walkthrough, honest beta-free pricing, demo credentials mirroring `docs/DEMO.md`, trust mechanics. |
| Reranker score normalization (retrieval-refusal bugfix) | done | `0dd266e` | Fixed a bug where the knowledge agent refused in-domain questions because the two reranker backends returned scores on different scales. Normalized both to [0,1] relevance probability with a regression test. |

## Known gaps (not ticket failures - waiting on external setup)

- **Live LLM calls run against a free OpenRouter model** (`qwen/qwen3-next-80b-a3b-instruct:free`, configured via the provider-seams refactor) and are prone to upstream 429 rate-limiting under real traffic; all LLM-touching code paths are proven with stubbed providers in CI, and live verification (confirmed working end-to-end during T-020) should expect occasional retries until a paid key or Azure OpenAI credentials are provisioned.
- **No hosted Supabase project yet**: real email/password login from the browser is blocked until it exists; backend auth is fully tested with locally minted tokens.
- **Console sidebar does not collapse on narrow mobile** (pre-existing, surfaced by the rebrand's 375px e2e check): the shared console shell (tenant-admin + platform, T-031/T-033) squeezes/clips instead of collapsing into a drawer below ~375px. Not a rebrand regression and not fixed here; flagged for a future responsive console-shell ticket (hamburger/drawer pattern) per the flag-not-decide convention.
