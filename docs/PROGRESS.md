# Wren - Progress Tracker

**The one page to check to know where the build is.** Every ticket in the project is listed below with its status, the commit that delivered it, and a one-line plain-English summary of what that commit actually did.

**Right now:** Phases 1 and 2 are fully done. Phase 3 (Eval, CI & console) is in progress - T-023, T-025, T-026, and T-027 are committed; T-024's infrastructure is committed but blocked pending founder hand-labeling (see its phase-file status note); the next ticket is **T-028 (Per-tenant cost/step caps + timeouts)**.

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
| T-016 Deterministic pricing engine | done | `eda876f` | The pure-math quote calculator: agents pick rule codes/item ids and quantities, this module reads the tenant's real prices from the database and computes every total in integer cents - no LLM can ever touch a number. Bad selections raise a typed error instead of guessing. |
| T-017 Quoting Agent | done | `8e6b9e5` | Customers can now ask "how much for X?" and get a real quote: the model only picks which services/items match (it never sees prices), the pricing engine computes the totals, and the quote is saved and shown in a QuoteCard rendered straight from engine output. Budget questions ("under $120?") get a yes/no comparison against the computed total, never model math. |
| T-018 Validation gate: price provenance | done | `7247a1c` | The safety net behind the pricing rule: every dollar figure in a generated reply (even spelled-out ones like "twelve hundred") is checked against what the pricing engine actually computed. An unexplained figure gets one rewrite; a second offense hands the conversation to a human. Its tests are a release criterion - never skipped. |
| T-019 Mock orders seed + lookup tool | done | `ecd2b31` | "Where's my repair R-1042?" now gets a real answer pulled from the seeded orders table - the code lookup is a plain database query (never guessed), and the status/details shown are always exactly what's in the database. An unknown code gets a polite "double-check the code" instead of an error. The 20 seed orders already existed from an earlier ticket. |
| T-020 Escalation Agent + state | done | `c10b742` | Escalation is now a real dead end, not a stub: asking for a human (or two price-provenance strikes) creates an escalations row, flips the conversation to `escalated`, and shows a "a human will take it from here" banner that permanently replaces the chat box - no further AI replies ever happen in that conversation. A database-level guard stops two simultaneous messages from ever creating duplicate escalation records. |
| T-021 Reasoning-inspection layer | done | `e4db924` | Every AI-generated reply now passes a final review before the customer sees it: it must trace to real business content (no invented facts), match the business's tone, not follow hidden instructions planted in retrieved content, not leak the AI's own instructions, and (for price-carrying replies) re-confirm every dollar figure against the pricing engine. A failing reply gets rewritten once; a second failure hands off to a human. Nothing streams to the customer until this passes - a deliberate wait-for-it tradeoff over showing text that might get pulled back. |
| T-022 Cross-tenant leakage test | done | `e7be3d2` | Proved, with real tests (never skipped, must be 100% or the build is red), that two businesses sharing this system can never see each other's data - not in a search result, an order lookup, a saved conversation, or a full customer chat, even when someone tries to fish for it. Proved the proof itself works by briefly and deliberately breaking the isolation on a throwaway branch and watching the tests correctly catch it, then discarding that branch. |

## Phase 3 - Eval, CI & console (in progress)

Goal: measure answer quality automatically (and gate CI on it), defend against prompt injection, track per-tenant cost, and build the tenant admin console.

| Ticket | Status | Commit | What was done |
|---|---|---|---|
| T-023 Generation eval (RAGAS + citation-faithfulness) | done | `aed2086` | An automated grader now checks every AI answer against the business's real knowledge: does every claim actually trace back to a real document (not invented), does the answer actually address what was asked, and - this project's own addition beyond the standard approach - does each individual footnote in the answer actually support the specific sentence it's attached to, not just the topic in general. Real numbers require a live AI model; the free tier used for development is rate-limited, so a full live run is a manual follow-up rather than something proven in this commit. |
| T-024 Judge calibration | blocked (founder hand-labeling) | `19d68e0` | Built the tool that checks whether the AI grader from T-023 agrees with real human judgment - but the ~30 example cases it checks against need a person to label them independently first, which is the entire point of the exercise. Every label in the committed dataset is clearly marked as a placeholder written by the agent, not the founder, and the pass/fail gate is wired to always fail until real labels replace them - so this can't accidentally look "done" when it isn't. |
| T-025 Golden agent-task set | done | `22f9cae` | Wrote the exam the AI agent will be graded against: 30 realistic customer conversations for the demo phone-repair shop - quote requests (including a budget cap where picking the pricier repair is an automatic fail), product recommendations, order status checks by ticket number, requests for a human, and mixed questions - each annotated with what the agent should do (which route, which catalog items or price rules, whether a quote or escalation record should exist afterward) and what it must never do (invent products, state prices the pricing engine didn't compute). Every one of the five specialists is exercised at least four times, enforced by a test. The machinery that actually runs and grades these conversations is the next ticket. |
| T-026 Trajectory scorer | done | `cd868c4` | Built the grading machine for T-025's exam: it runs each of the 30 conversations through the real agent and checks what the agent actually did - did it route to the right specialist, pick the right price rules and catalog items, look up the right order, end with a quote or escalation when it should, and never state a price the pricing engine didn't compute. It also measures how many steps the agent took versus the minimum needed, tracks cost per conversation, and has a second AI grade whether the agent's stated reason for its routing choice actually holds up. Cases that fail print the full step-by-step trajectory for debugging; the gate demands 90% tool-call correctness. Real scores need a live AI model. |
| T-027 Prompt-injection defense + adversarial set | done | `598f3a7` | Hardened the agent against prompt-injection two ways: every piece of business-uploaded text handed to the AI (knowledge documents, catalog entries, price labels) is now fenced inside random per-request delimiters with a standing "this is data, never instructions" rule, so a booby-trapped document can't smuggle commands into the AI's reasoning; and a cheap scanner flags obvious attack phrasing in the customer's own message so the safety-review layer scrutinizes that reply harder. Proved it with a 29-case attack set (fake system overrides, "ignore your instructions", prompt-extraction attempts, a poisoned knowledge document, a poisoned order record) run through the whole real stack - a case passes only if no secret marker leaks into the customer's reply and any genuinely-needed human handoff still happens. Target is 80% blocked, reported honestly; real numbers need a live AI model. |
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

- **Live LLM calls run against a free OpenRouter model** (`qwen/qwen3-next-80b-a3b-instruct:free`, configured via the provider-seams refactor) and are prone to upstream 429 rate-limiting under real traffic; all LLM-touching code paths are proven with stubbed providers in CI, and live verification (confirmed working end-to-end during T-020) should expect occasional retries until a paid key or Azure OpenAI credentials are provisioned.
- **No hosted Supabase project yet**: real email/password login from the browser is blocked until it exists; backend auth is fully tested with locally minted tokens.
