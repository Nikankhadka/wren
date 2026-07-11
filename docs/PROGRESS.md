# Wren - Progress Tracker

**The one page to check to know where the build is.** Every ticket in the project is listed below with its status, the commit that delivered it, and a one-line plain-English summary of what that commit actually did.

**Right now:** Phase 1 is fully done. Phase 2 is in progress - the next ticket is **T-016 (deterministic pricing engine)**, and its code is already sitting uncommitted in `backend/app/pricing/`.

## How to read this file

- The whole build is 40 tickets (T-001 to T-040), grouped into 4 phases of roughly one week each. One ticket = one commit, and the commit message always starts with the ticket number (e.g. `T-015: Recommendation Agent`), so `git log --oneline` lines up 1:1 with this table.
- For the full technical detail of any ticket, open its entry in the matching `docs/phases/` file. For the full story of any commit, run `git show <hash>` - commit bodies are written in plain language.
- **Statuses:** `done` | `in progress` | `not started` | `blocked (why)` | `deferred (why)`.
- **Keeping it updated:** whoever commits a ticket (human or agent) fills in that ticket's row - status, commit hash, one-line summary. This is written into the build loop (`.agents/gnhf-objective.md`, step 6).

## Phase 0 - Planning & scaffolding (done)

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| Planning docs + scaffold | done | `b910a50` | Wrote the whole documentation system (planning docs, design docs, phase ticket files) and created the empty frontend/backend/infra project skeletons with a working `/health` endpoint. |
| Review fixes | done | `c2101e2` | Fixed the issues found when reviewing the phase-0 work. |

## Phase 1 - Foundations (done)

Goal: a business can sign up, get its own subdomain, describe itself through a conversation, upload documents, and ask questions that get answered from those documents with citations.

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| T-001 Monorepo scaffold | done | `b910a50` | Project skeleton (delivered with the phase-0 commit). |
| T-002 Full schema + migrations | done | `3d070d5` | Created every database table (tenants, config, documents, chunks, conversations, quotes, orders...) as SQL migrations, plus a test suite for them. |
| T-003 RLS enforcement + schema audit | done | `c0b798b` | Locked every table down with row-level security so one business can never read another business's data, and added tests that prove it. |
| T-004 Auth + tenant provisioning | done | `d1826e4` | Supabase login/signup, and a signup flow that creates a new tenant with its own admin user. |
| T-005 Tenant resolution by subdomain | done | `075e17a` | Visiting `bytefix.wren.app` now resolves to the right tenant and loads its branding (colors, name). |
| T-006 Conversational onboarding | done | `d92ca24` | New businesses describe themselves in a chat; an LLM extracts the structured config (services, prices, policies) which the admin confirms. |
| T-007 Knowledge upload | done | `8a7b472` | Admins can upload documents (PDFs, text) that become the business's knowledge base. |
| T-008 Chunk + embed pipeline | done | `d8b0a43` | Uploaded documents get split into ~400-word chunks and turned into vector embeddings so they can be searched by meaning. |
| T-009 Hybrid retrieval | done | `9c27859` | Search that combines meaning-based (vector) and keyword-based (full-text) results, then reranks them so the best chunks come out on top. |
| T-010 Golden retrieval set + eval | done | `182985a` | 50 hand-written test questions with known right answers, plus a script that scores how well retrieval finds them (it scored very well). |
| T-011 Bare /chat with citations | done | `300699a` | The first real customer chat: ask a question, get a streamed answer built only from the business's own documents, with citations - or a polite refusal if nothing relevant exists. Also fixed a latent CORS bug that silently blocked all browser-to-backend calls. |

## Phase 2 - Agents & pricing (in progress)

Goal: replace the single straight-line chat with a team of specialist agents (a supervisor routes each message to the right one), and add the deterministic pricing engine - the "no LLM ever makes up a price" centerpiece.

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| T-012 LangGraph state schema + graph skeleton | done | `82322b9` | Set up the agent graph: a supervisor node, five specialist slots, and shared state flowing between them. The T-011 chat logic became the first real specialist (Knowledge). |
| T-013 Supervisor routing | done | `731b622` | The supervisor now actually classifies each customer message (price question? policy question? order status?) and routes to the right specialist. Low confidence always escalates to a human - enforced in code, not the prompt. (Live-model accuracy check still pending real Azure credentials.) |
| T-014 Knowledge Agent | done | `0b99a71` | Already delivered by T-012's design; this commit added the missing dedicated test for it. |
| T-015 Recommendation Agent | done | `c023918` | "What should I buy?" questions now get product recommendations pulled only from the business's real catalog - names, descriptions, and prices come straight from the database, never from the model. |
| T-016 Deterministic pricing engine | in progress | - | Pure-math quote calculator (integer cents, no LLM imports allowed in the module). Code exists uncommitted in `backend/app/pricing/`. |
| T-017 Quoting Agent | not started | - | |
| T-018 Validation gate: price provenance | not started | - | |
| T-019 Mock orders seed + lookup tool | not started | - | |
| T-020 Escalation Agent + state | not started | - | |
| T-021 Reasoning-inspection layer | not started | - | |
| T-022 Cross-tenant leakage test | not started | - | |

## Phase 3 - Eval, CI & console (not started)

Goal: measure answer quality automatically (and gate CI on it), defend against prompt injection, track per-tenant cost, and build the tenant admin console.

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| T-023 Generation eval (RAGAS + citation-faithfulness) | not started | - | |
| T-024 Judge calibration | not started | - | |
| T-025 Golden agent-task set | not started | - | |
| T-026 Trajectory scorer | not started | - | |
| T-027 Prompt-injection defense + adversarial set | not started | - | |
| T-028 Per-tenant cost/step caps + timeouts | not started | - | |
| T-029 CI regression gate | not started | - | |
| T-030 Tracing + cost accounting | not started | - | |
| T-031 Tenant admin console core | not started | - | |

## Phase 4 - Ship (not started)

Goal: polish all three surfaces, deploy to real infrastructure, and prove the whole system is domain-agnostic by onboarding a second, totally different business with zero code changes.

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| T-032 Customer chat surface - final polish | not started | - | |
| T-033 Platform-owner surface | not started | - | |
| T-034 Tenant dashboards: cost + eval | not started | - | |
| T-035 Terraform AWS backend | not started | - | |
| T-036 Deploy end-to-end (CI image push + Vercel wildcard) | not started | - | |
| T-037 Generalization proof: Tenant 2 by config alone | not started | - | |
| T-038 Eval report | not started | - | |
| T-039 Security write-up | not started | - | |
| T-040 README + LEARNINGS + demo video | not started | - | |

## Known gaps (not ticket failures - waiting on external setup)

- **No Azure OpenAI credentials yet** (`AZURE_OPENAI_*` empty since T-006): everything LLM-touching is proven with stubbed providers and clean-failure paths; real live generation/routing/embedding quality is unverified until the founder provisions credentials.
- **No hosted Supabase project yet**: real email/password login from the browser is blocked until it exists; backend auth is fully tested with locally minted tokens.
