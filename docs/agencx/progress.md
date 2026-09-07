# Agencx build dashboard

## Current status

The Stage 1 product is deployed on Vercel and the production smoke test is
green. Feature delivery is complete. Phase 1 refinement remains open for
schema/type safety, judge calibration, production evidence, and operational
hardening.

| Environment | Value |
|---|---|
| Production branch | `staging` |
| Live origin | `https://agencx-iota.vercel.app` |
| Preview branch | `development` |
Production database: hosted Supabase, migrated and seeded with `bytefix`

## What's done

| Area | Tickets and evidence |
|---|---|
| Foundation and tenancy | A-1, A-2; schema, RLS, auth, tenant resolution |
| Onboarding and login | O-1, O-2, O-5, O-6, O-7, O-8, O-9, O-10, O-11, O-12 |
| Chat spine and providers | P-1, P-2, P-3, P-4, P-5; Google primary, fallback tiers, latency race, preload, invalidation, typing indicator |
| Grounded chat | O-3, O-4; hybrid retrieval, URL/document ingest, context package |
| Money and escalation safety | C-1, C-2, C-3, C-4, C-5, C-6; deterministic pricing, figure gate, non-terminal handoff, staff takeover |
| Tenant console | E-1, E-2, E-4, E-5, E-6; Home, Chats, Business, Booking, responsive navigation |
| Storefront and media | M-1, M-2, M-3, M-4, M-5, M-6; owner offerings, prices, Cloudinary media, reviewed imports |
| Product polish and hygiene | B-1, B-3, D-2, E-3, F-1, F-2, F-3, G-1 |
| Developer experience and deployment | K-1, B-4; containerized development, two Vercel services, same-origin routing, hosted embedding and reranking |
| Security and API reliability | R-1, R-2, R-4 US-1, R-5 US-1; Problem Details, safe SSE errors, request correlation, SSRF protection, Google tool-history fix |

Detailed records live in [`spec/completed/`](spec/completed/).

## What's next

- [ ] R-3: audit success schemas and explicit unknown-field policies.
- [ ] R-4: complete founder judge calibration and record additional production-smoke evidence.
- [ ] R-5: decide and validate backups/restore, error tracking, E2E-in-CI, and dependency scanning.
- [ ] Add the GitHub `VERCEL_TOKEN` secret so registry cleanup can run. The local Vercel token is not a repository secret.
- [ ] Record the QA pass, root-cause fixes, regression tests, and measured optimization results.
- [x] W-1: cap the home escalation queue by screen size, not a fixed row count, and keep it fresh without a manual reload.
- [x] W-2: stop the onboarding interview from re-asking a filled slot.
- [x] W-3: keep the onboarding thread clear and responsive - empty placeholders, stable composer geometry, one pending indicator, animated upload processing, and a proven SSE/ordinary-request transport split.
- [x] W-4: complete go-live address handling - the suggested slug on every confirm-opening path, actionable field errors, owner-typed addresses preserved, and recoverable network failures.
- [x] W-5: ground one customer chat answer in both the confirmed offerings catalog and uploaded knowledge together, using the existing context package.
- [x] W-6: extract accurate offerings from the complete source - distinct items, source-backed descriptions, deterministic item-bound prices, complex-price preservation, and possible-match proposals.
- [x] W-7: make the interview read like a person - challenge junk input, drop the
  skip chip, keep replies short, address-only go-live, priced offering cards.
- [x] W-8: review a large import without losing information - shared structured document review, five-item preview and editor pages, explicit duplicate decisions, owner-only source evidence, and catalog-only offering publication.
- [ ] W-9: the definitive onboarding and customer-assistant contract - name
  confirmation, corrections from any beat, offering operations, a code-owned
  customer-agent contract applied to every prose route, and structured customer
  voice. Built on `feat/w-9-agent-contract`; 12 of 13 Definition-of-done boxes
  ticked. Open only on the gate box, and only on one gate in it: `make ci` (940
  backend tests, 110 frontend, 3 of 3 import contracts, a clean production
  build), `make test-e2e` (105 passing across both Playwright projects), and
  `make eval-skip-llm` are all green against the final branch state. `make eval`
  is unmeasured, twice, because the free-tier provider quota is exhausted rather
  than because anything failed - see the ticket's Record for what that run does
  and does not prove.
- [ ] W-10: drop `tenant_config.system_prompt` and `.tone` and their last
  writers, after W-9 is verified in production
  ([`spec/active/14-schema-drop.md`](spec/active/14-schema-drop.md)).

**Phase 13 specification amended twice.** 2026-09-05
(`docs/phase13-walkthrough-refinement`): a second walkthrough round and its
planning refined W-3 through W-6, added W-8 and W-9, and corrected the phase
introduction to nine tickets. 2026-09-06: W-9 was rewritten into the phase's
single authoritative closing ticket (Amendment 3 in `13-walkthrough.md`), and
this file's own status line is corrected here - **W-1 through W-8 are all
shipped; W-9 is the only ticket in Phase 13 still open.** The prior line above
this one claimed W-3 through W-6 were still open after they had already
shipped; that was this file drifting behind the spec, not a real regression -
see `13-walkthrough.md`'s corrected intro and W-6's now-ticked Definition of
done for the record.

## Known gaps and deliberate deferrals

- The owner Copilot route is deferred to Phase 2.
- Per-tenant tool gating and its toggle UI are deferred to Phase 2; advanced tools remain built but off by default in the lean configuration.
- `agencx.app` is deferred until the founder buys and binds the domain. The Vercel origin is the current stand-in.
- Judge calibration needs founder labels to avoid circular evaluation.
- The Hobby deployment has cold starts and Supabase can pause after inactivity; keep-warm mitigates this for the portfolio deployment.
- No real customer data should use the free-tier LLM and embedding providers until the provider decision changes.
- Custom SMTP (Brevo) is not yet configured on the hosted Supabase project. Its built-in mailer delivers only to project members at ~2/hour, so no real tenant owner can receive a login code until Brevo is set (`deploy.md` Step 1.5) - found 2026-09-04 while fixing the login OTP misconfiguration below.

## Spec status

**Two abandoned attempts sit behind `M-1`/`M-4`, and the record is the point.**
A Codex session built `M-1` on `feat/offerings-media-import` and renamed
`catalog_items` to `offerings`; a second, on `feat/business-storefront`, built
the storefront but kept `catalog_items`, reversed the rename in its own
migration, and dropped prices from offerings entirely. The founder ruled on
both open questions - the rename stands, and prices are owner-typed facts that
belong on the page (D24) - so the first branch merged to `development` as
`M-1` and the second was rebuilt on top of it as `M-4`. Nothing was thrown
away except the reversal migration. The dev database carried both experiments
plus a `0023_storefront_gallery.sql` that exists in no branch, so it was reset
from schema zero to prove `0001`-`0024` apply in order.

O-5 pulled **B-3 US-1** (the lighter crimson `#C1123F`) forward, because the
prototype the onboarding thread is ported from carries that ramp - B-3 stays
open for US-2, the `STATUS_TONE` map.

**Phase 1 refinement (`12-refinement.md`) has opened.** R-1 (documentation
truth), R-2 (the standard API contract), R-4 (reliability and provider, US-1),
and R-5 (operations and security, US-1) are closed: every JSON error is RFC
9457 Problem Details, SSE streams fail safely with a typed `error` event,
`api-contract.md` documents the shape, D-4 and other stale documentation is
reconciled against the code, Google's tool-history bug is fixed, and the
URL-ingest path is hardened against SSRF. **R-3 (schema and type safety) is
open as a backlog entry**, not yet scoped into a full ticket; R-4 and R-5 each
keep an open second half (judge calibration/production-smoke evidence;
backups, error tracking, E2E-in-CI, dependency scanning). No Phase 2 feature
work happens as a side effect of this phase - recommendation, quoting, and
order/ticket lookup stay exactly where D-2 left them: built, exposed to every
tenant today because D-1's per-tenant gating hasn't landed yet, not deleted or
deferred out of the codebase.

**Owner-home escalation queue is unticketed UI polish** (founder request,
2026-09-04, `feat/owner-escalation-panel`), not a spec ticket. Home's
`WaitingPanel` replaces the single collapsed "waiting" `BriefItem` with one
row per customer who needs the owner (name, relative time, the assistant's
one-line summary), sorted oldest escalation first and capped to 3 with a
"Show all N" expand; a row links straight to `/chats/:id` rather than the bare
list. The Chats tab badge (bottom bar and sidebar) now carries the count
instead of a bare dot. `escalations.summary` is only ever written today by the
`create_escalation` tool - the price_gate/inspection/limit paths leave it
NULL - so a new async summariser (`app/agents/escalation_summary.py`) fills it
from the last few messages after the customer's turn is already on the wire
(never inside it: T-028's 10s turn budget has no room for an extra LLM call at
the point an escalation fires). `ConversationSummary` gained `pending_since`
(the escalation's own timestamp) alongside the existing `pending_summary`.
Also fixed in passing: the Chats-list attention dot and the new count badges
disagreed on which amber to use (`--color-warning`'s amber-500, a "kept from
the prior system" holdover that reads brown at text weight and fails 4.5:1
against its own subtle background, versus `--color-highlight`'s amber-400,
the prototype's actual notification colour). W-1 points `--color-highlight`
at that prototype literal, with 8.6:1 dark-text-on-solid-fill contrast, and
every "wants the owner" indicator in the app uses it consistently.

**Hosted login OTP was misconfigured, not a code bug** (found 2026-09-04,
`fix/hosted-otp-sends-link`). Staging's login-in-chat mailed a magic LINK to
Supabase's default Site URL (`http://localhost:3000`) instead of the
six-digit code the UI asks for - `auth_logs` showed `POST /otp` 200 followed
by `GET /verify` **303** (a clicked link, not a typed code, which is a `POST
/verify` 200), and `auth.users.recovery_sent_at` was stamped instead of
`confirmation_sent_at`, confirming the Magic Link template's link-only
default had rendered. `signInWithOtp`/`verifyOtp` (`login/page.tsx`) were
already correct; the hosted project's Auth config (Site URL, URI allow list,
Magic Link and Confirm signup email templates) had simply never been set per
`deploy.md`'s own Step 1.5, which calls this "blocking, not optional." Fixed
by PATCHing the project's Management API config directly - `deploy.md` Step
1.5 now gives literal field values and `curl` commands instead of
dashboard-click prose, and `docker-compose.yml` gained
`GOTRUE_MAILER_TEMPLATES_CONFIRMATION` so local dev mirrors both templates
hosted needs. Custom SMTP (Brevo) is a separate, still-open gap (above): this
fix restores the founder's own login, but a real tenant owner receives
nothing until Brevo is configured.

**W-6 shipped** (2026-09-06, `feat/w-6-offering-extraction`). The founder's PDF
turned out to be recoverable, and it is now `backend/tests/fixtures/`. Running
the old `derive()` over it reproduces the report exactly: `"Pocket both run"`,
`"of wrapped in. For"`, `"Salads are sold individually too, mostly"`. Six pages
of prose about a Bondi Junction restaurant, ~20 sellable items, in a document
that is ~80% reviews, FAQ and platform trivia - nothing like the seeded catalogs,
which are rows the app itself produced.

The fix is a split of labour rather than a better regex: the model identifies
items, the server counts. That is structural, not instructed. **Stage 0 indexes
every monetary figure before the model sees a token**, so the set of amounts the
pipeline can emit is fixed in advance; the extraction schema then has no numeric
field at all, and for money the model can only return a block id pointing into
that frozen index. There is nowhere for an invented number to arrive.

Three things the ticket did not anticipate, all found by running the real
fixture:

- `is_hedged` (built for the chat price gate, used nowhere else) rejects
  `"around $18"` for free, and a reporting-verb check catches `"another said the
  $18 plate"`. Two customer reviews price the plate in this document; neither may
  price the menu.
- Quotation marks are **not** an attribution signal. The first pass treated them
  as one and silently suppressed two real menu prices, because this kind of
  document is full of scare quotes - a `"Pimped Up"` pocket, chips `"described as
  famous"`. A whole quoted sentence is caught structurally instead.
- A range whose second half drops the currency mark (`"mostly $10-14"`) is
  invisible to `extract_monetary_figures`, so a pairwise check between two
  detected figures reads it as one flat price and puts every salad on the menu at
  $10. The range check reads forwards from a figure's own text instead.

Blocks are sentence-sized, not paragraph-sized: a prose menu paragraph prices
several items in a row, and at paragraph granularity every figure looks like a
competing price for every item in the paragraph.

Because extraction needs a model call it moved to ingest (`documents.offerings`,
migration 0026); it used to run inside **every read** of every document.
`derive()` and its helpers are deleted rather than kept as a fallback, so there
is one extraction path - a failure yields fewer candidates and says so
(`extraction_status`), never a fall back to first-number parsing.

`merge_offerings` is now the single written statement of offering precedence.
The browser had reimplemented it with the opposite rule - owner wins, not
document - so an uploaded price list and a chip-typed name disagreed depending on
which surface you looked at. `withCombinedOfferings` could not simply be deleted
as planned: a file uploaded mid-interview posts to the shared knowledge route,
which does not fold candidates into the onboarding record the way the URL turn
does. It now applies the server's rule and names it.

Also fixed in passing: `vitest.config.ts` had no `@/` alias, so a unit test could
only import from modules that happened to use relative paths - which had quietly
decided which components were testable.

**Still owed: the browser pass.** No LLM key is configured locally, so the real
model call over the real PDF has not run. Everything either side of it is
verified end to end - the upload route, structuring, extraction, the jsonb
column, the API shape and the no-re-extraction-on-read property, in
`test_knowledge_api.py` - and the resolver is pinned against the real fixture
text in `test_offering_extraction.py`. What remains unproven is how well the
model itself identifies items in prose, which is the one part a fake provider
cannot stand in for.

**Phase 13 (walkthrough fixes) has opened** (`13-walkthrough.md`, 2026-09-04).
A founder walkthrough of the deployed build found defects across the home
escalation queue, the onboarding interview, and customer chat grounding. Two
of the six tickets, W-1 and W-5, refine work this same session already
shipped (the escalation queue above, and `fix/customer-offering-context`'s
offerings-grounding fix) rather than building it fresh. W-2 is the largest
ticket: the onboarding interview's next question has always been chosen
deterministically but composed by a second, unconstrained LLM call, which let
it re-ask a business name already on file - the fix makes the server emit the
question verbatim, the same way the chip-answer path already does, and adds a
flow-change confirmation rule to `conventions.md` so a working conversational
flow is not altered again without a flagged before/after. The phase was
extended to nine tickets by a second walkthrough round and its planning
(`docs/phase13-walkthrough-refinement`, 2026-09-05) - refined W-3 through
W-6, new W-8 and W-9 - as a specification update only; those tickets remain
open for implementation.

**W-2 shipped** (2026-09-05, `fix/w-2-onboarding-repeat`). Building it surfaced
that the ticket named a symptom the spec had mis-sized: there was no repeat cap
anywhere to raise or lower - `next_beat` was a stateless rescan and
`off_topic_count` was incremented but read by nothing - and every one of the
nine beats was a hard gate, so an unanswerable one looped forever and blocked
go-live. The diagnosis that shaped the fix is that *adjacency*, not count, is
what made the transcript infuriating: three business-name questions back to
back. So each beat now gets two asks, and then resolves rather than repeating -
a skippable beat takes a default or is dropped, a required one is deferred to a
second pass that returns only once every other beat is done. Which beats are
which follows one rule: skippable means nothing downstream reads it, or the
owner can still edit it after go-live. On the final pass the owner's own words
are never stored as a fallback: an unresolved required field pauses the
interview, survives reload, and offers a retry with a fresh two-ask allowance.
Go-live stays blocked until it has a valid value. A skipped beat deliberately
writes no sentinel into the profile - `profile_tagline` renders `services` and
`hours` straight into the public storefront subtitle, so a "skipped" string
there would have shown to customers.

Still open from this ticket's edges: `hours` and `contact` are required only
because no post-go-live editor exists for them. A profile editor at
Business > details would let them become skippable, and is the natural
follow-up.

**W-5 shipped** (2026-09-05, `fix/w-5-combined-grounding`). The customer chat
answered "what do you offer?" from the confirmed catalog and stopped there,
surfacing uploaded knowledge only on a second, more insistent question. Three
mechanisms caused it and all three were prompt-level: the offerings block told
the model to "enumerate the complete catalog before offering to share more
detail", the tool guidance said that answer "is in the material above", and on
the hybrid path the catalog could never reach the same generation as the
retrieved chunks because `_build_knowledge_prompt` only ever saw
`retrieved_chunks`. The catalog now rides in state as `offerings_text`, set
beside the existing `owner_material` on both of the agent node's return paths,
so the draft node can put both sources in front of one generation without a
second query.

The ticket missed one thing that would have made the fix backfire: the
grounding judge's only evidence is `_provenance_text`, which read
`retrieved_chunks` alone, and catalog rows are stripped from retrieval on both
paths on purpose (M-1). A reply naming a confirmed offering therefore had no
provenance in front of the judge, so doing exactly what W-5 asks for would have
failed grounding and escalated. The offerings block is appended there too. The
price gate needed nothing - `owner_material` already carried the catalog
string, which is why the money guardrail never showed the same gap.

Verified through the real customer chat with a live model rather than a mocked
turn: the repo's E2E convention deliberately scripts customer turns through
`page.route` (`e2e/typing-indicator.spec.ts` header) because a free-tier model
makes timing non-deterministic, and a mocked `/api/chat` would mock away the
server-side prompt assembly that is the whole change. Before and after were run
twice each against `bytefix`.

**W-9 is built; one Definition-of-done box is unmeasured** (2026-09-07,
`feat/w-9-agent-contract`, seven commits). Twelve of the ticket's thirteen boxes
are ticked with evidence. The thirteenth is the gate box, and it stays open
because `make eval` could not run: the free-tier daily budget was spent by the
conventions.md section 5 reproduction drives, Groq returned `429 tokens per day
(TPD): Limit 200000, Used 197445`, and the Google primary leg was rate-limited
into its retry ladder at the same time. A partial run recorded
`tool_correctness: 0.611`, which is not a measurement of anything - it was taken
while provider calls were failing and it carries no baseline. `make test-e2e`
has also not been run against the final branch state. `make check`,
`make format-check`, `make build`, and `make eval-skip-llm` are green. The
ticket therefore stays in `spec/active/`; moving it would claim a gate nobody
has seen pass.

What the reproduction changed about the ticket is worth keeping. Five of the six
failures the ticket names reproduced through the real onboarding UI, and the
drive surfaced four the ticket had not: a beat's own `example` reaching the
owner as a fact (the owner greeted as "Nikan", the founder's name in the name
beat), the model answering the question it was one turn away from asking, em
dashes in assistant output against a repo-wide rule, and a value typed during
another beat landing nowhere. The sixth named failure, the owner's name standing
in for the business name, turned out to be latent rather than user-visible: the
summary carrying that fallback renders only once every required beat is
satisfied, and `business_name` is required. It is removed anyway, and the ticket
record says plainly that no user-visible bug was fixed by removing it.

Two consequences worth carrying forward. The customer contract and its voice
block measure 3,682 characters at their longest, where the retired
`tenant_config.system_prompt` measured 202, so the fast-path budget now accounts
for a much larger prompt and a tenant sitting within about 3,500 characters of
that budget takes the hybrid path where it used to take the fast path - honest
accounting, but a real behavior change on live tenants. And the pin that carries
that cost into the budget, `_CONTRACT_OVERHEAD_CHARS`, is a number rather than a
measurement, because the import contract forbids `app.services` from importing
`app.agents`; a test that imports both fails the moment the contract outgrows
it.

`tenant_config.system_prompt` and `.tone` are read by no application code after
this ticket, but the columns and their seed writes are still in place. Dropping
them is W-10 (`spec/active/14-schema-drop.md`), deliberately its own ticket
because one squash-merge cannot both deploy forward-compatible code and run the
destructive migration after it is verified.

**Chats-list row identity is unticketed UI polish** (founder request,
2026-09-06, `fix/chats-row-identity`). Every row on the owner's Chats list read
"Customer", because the web chat surface never captures a name - `chat/service.py`
inserts a conversation with nothing but `tenant_id`, and only `seed_demo.py` ever
sets `customer_ref`. The seeded demo world hid this completely: all seven of its
conversations are named, so the list looked fine in every screenshot and every
E2E run, and the defect only appears against a conversation a real customer
started. An unnamed row now falls back to the conversation's own short reference
(`#06BD83`, the head of its uuid), which is a literal prefix of the id in
`/chats/<id>` - so a row, its thread topbar, and the URL all identify the same
conversation without a new column, a migration, or a generated id nothing else
would agree with. A named customer shows the name alone; the code is a fallback,
not a suffix.

The second half is the attention signal: "needs you" was a 7px amber dot sitting
right of the timestamp, unlabelled, beside an identically sized accent dot
meaning the opposite ("being handled, ignore this"). Two dots differing only in
hue, one demanding action and one suppressing it, and the amber one's
`aria-label` was on a bare `<span>` with no role, so it announced to nobody. It
is now a pill reading "Action needed" in the same words as the filter chip above
that selects for it, on `--color-highlight` per W-1. The accent dot stays a dot -
these two states are not peers, and only one of them is asking for something.

Two things worth recording. The three surfaces had drifted to three different
fallbacks (`"Customer"` twice, `"A customer"` once, `"Anonymous"` on the legacy
table); the label now lives once in `lib/format.ts` beside `relativeTime`, which
all three already shared. And `check-tokens.mjs` fails a six-hex-character
display code as a colour literal - the same "hex-looking, not a colour" class as
the `href="#abc"` limit its own header documents - so `format.ts` joins
`brand.ts` on the allowlist rather than the regex being loosened. `/chats` had no
E2E coverage at all, which is how this shipped; `e2e/chats-list.spec.ts` now
stubs the unnamed case the seed cannot produce.

| Location | Status | Contents |
|---|---|---|
| [`spec/active/08-deferred.md`](spec/active/08-deferred.md) | Deferred | B-2, D-1, D-3 |
| [`spec/active/12-refinement.md`](spec/active/12-refinement.md) | Open | R-3, R-4, R-5 |
| [`spec/active/13-walkthrough.md`](spec/active/13-walkthrough.md) | Open | W-1 through W-8 delivered; W-9 built, open on its gate box alone (amended 2026-09-06, Amendment 3) |
| [`spec/active/14-schema-drop.md`](spec/active/14-schema-drop.md) | Open | W-10, blocked on W-9 production verification |
| [`spec/completed/`](spec/completed/) | Complete | All delivered feature, deployment, and supporting phases |
| [`docs/archive/phase1-complete/`](../archive/phase1-complete/) | Historical | Completed R-1 and R-2 records |

Phase 1 is not called fully complete until the active refinement items are
validated or explicitly accepted as deferred. QA and optimization are separate
from the documentation closeout and must be evidence-driven.
