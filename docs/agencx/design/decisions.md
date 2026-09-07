# Agencx - Design Decisions, ADRs

The decision ledger: every consequential choice, old and new, with the reason it
was made. Nothing changes silently. The 11 decisions below were carried from
the planning phase (reasons condensed); D12 onward are the decisions that shape
the Agencx build.

## The carried decisions (1-11)

| # | Old | New | Reason |
|---|---|---|---|
| 1 | Cleaning wedge first | Domain-agnostic product; reference tenant 1 is the restaurant/catering anchor | Wren proved the agent, not the vertical; a vertical wedge contradicts the product thesis |
| 2 | TypeScript-e2e, Cloudflare Workers | Python/FastAPI + Next.js | Wren's proven modules (retrieval, graph, evals) are Python |
| 3 | No vectors / RAG | pgvector + hybrid retrieval from Stage 1 | Wren built and measured retrieval (recall@5 = 1.000); the old reconsider condition is met |
| 4 | No agent framework at all | LangGraph for the assistant graph only | Wren's ported layer is already a graph; onboarding stays a plain tool loop |
| 5 | Boundary unenforced | import-linter/AST test + ESLint no-restricted-imports, in CI from the first commit | The violation that matters is the one added later under time pressure |
| 6 | Phone-OTP only | Email + 6-digit code in-chat; phone is a profile field | No paid SMS in Stage 1 |
| 7 | "No settings screen, ever" | Second tab is **Business** - shown-back profile and knowledge | The owner must be able to trust and correct what the agent knows; it is not a settings tree |
| 8 | `AGENCX` mode value | `PLATFORM` in `payment_processing_mode` | Brand names in schema become rename migrations; settle before any row exists |
| 9 | `discovery_mode_teach_me` fork | Removed | "We don't serve your trade" contradicts I8; the geographic fork survives |
| 10 | Hosting "chosen" (Cloudflare) | **Closed by B-4:** both services are containers in one Vercel project behind one origin. The ECS Terraform stays dormant, still CI-validated, deployed by nothing | The frontend host stayed open until its own phase could decide it; B-4 is that phase, and it closed the backend target too - one provider, one origin, no CORS surface |
| 11 | Wren copy ported verbatim | Copy rewritten inside the porting ticket, never "later" | Wren surfaces said "AI"/"agent"; user-facing copy never does |

## New decisions (D12-D17)

### D12: Lean-first flow - whole-corpus fast path, hybrid RAG deferred

**Decision:** Phase 1 (small business, e.g. Sababa, <~7-8k total context) runs
the lean flow: the tenant's whole corpus goes into the prompt, no retrieval
scoring. Hybrid RAG + the tool loop defer to Phase 2 (mid-large businesses,
>50k corpus + structured commerce).

**Why:** The measured Wren turn was 37s with 3-5 serial LLM calls and a
retrieval round-trip before drafting. For a small corpus the retrieval scoring
adds latency without adding information - the model can read the material
directly. The product promise is a fast grounded answer; the lean flow is how
that is achievable at free-tier cost.

**Boundary:** the corpus-size threshold is **data-driven** (measured token
count, config value), never a business-size branch (I8). The seam
`get_business_context(tenant_id, query)` owns the choice; both paths return the
same shape.

### D13: Supervisor-with-tools from day one (Phase 1 shape)

**Decision:** The customer assistant is a supervisor with tools - one model call
per turn in the common case. Phase 1 ships it with exactly one tool beyond
answering: `escalate`. Phase 2 adds search/recommend/quote/order-status as
tools on the same supervisor.

**Why:** The shape that ships must be the shape that scales. Wren's fixed
five-specialist topology needed a route call before every turn; a supervisor
that can decide and act in one call halves the serial calls from the start.
Tool-driven supervision was already Wren's planned T-044; Agencx makes it the
Phase 1 topology instead of a Phase 5 afterthought. Escalation stays the only
tool until per-tenant gating (D-1/D-2) proves the demand.

### D14: Agent-ready pre-load - context package + knowledge_version invalidation

**Decision:** When a chat opens (any surface), the backend assembles a context
package (system prompt + profile + corpus) and caches it in-process keyed by
`(tenant_id, knowledge_version)`. `knowledge_version` is derived (max document
update timestamp) - no new table. Every customer turn then makes one LLM call
against the package. Re-ingest or profile change bumps the version and
invalidates the cache.

**Why:** Perceived latency is the measured killer (37s knowledge turns). With
the package assembled before the customer ever types, time to first token is
one call away, and provider prompt caching (Groq, Google) discounts the
repeated prefix. The package makes the "agent ready when the chat opens"
pattern literal instead of aspirational.

**Cost:** a slightly stale package between invalidation and the next open -
acceptable because the package is assembled fresh on every open and the
invalidation trigger (re-ingest) is exactly the moment the tenant is actively
editing, where a few seconds of staleness is invisible.

### D15: Provider strategy - Google primary, Groq/Cerebras fallback, OpenRouter failover

**Decision:** Three tiers, all OpenAI-compatible env config:

| Tier | Provider | Model |
|---|---|---|
| Primary | Google AI Studio (free) | `gemini-3.5-flash-lite` (OpenAI-compat endpoint) |
| Fallback | Groq (free) | `openai/gpt-oss-120b` (or `gpt-oss-20b` on tighter budget) |
| Failover | OpenRouter (free) | `google/gemma-4-26b-a4b-it:free` (CI pin) |

Cerebras (llama-3.3-70b, $5+$5 credits) where Groq is unavailable; GitHub
Models excluded (8k input/request cap); the Gemini 3.x reasoning-mandatory
flash family excluded (reasoning tokens break the latency budget and the
structured extract budget). Local dev may run Z.ai GLM; CI pins gemma so gates
run deterministically.

**Why:** Verified on 2026-08-20 across provider docs and the live model list:
Google's free tier is the most generous (1M TPM, 1,500 requests/day, 15-30
RPM) with the fastest small model; Groq's LPU gives the sub-200ms fallback and
cached-prefix tokens free of the TPM count; OpenRouter's free tier is the most
independent third leg and the CI-proven structured-output default. The budget
ceiling for live testing is $10/month.

### D16: Latency budget and first-wins failover

**Decision:** The product promise is time-to-first-token <= 4s primary, 10s
hard cap to a complete answer. On timeout or hard 429 the fallback tier races
the primary; **first-wins** - the losing stream is discarded. A hard 429 skips
that provider for the session. The client shows a typing indicator through the
failover window; the customer never sees a spinner or a provider-switch notice.

**Why:** Free tiers are unreliable by nature (measured: 6x timeouts between two
runs 15 minutes apart). A timeout-based failover converts that variance into a
first-wins race the customer cannot see, and keeps the product promise honest
under free-tier conditions. The 4s/10s numbers come from the PRD speed
contract, not from any single provider's SLA.

### D17: Rebrand - Agencx name, crimson primary, Plus Jakarta Sans

**Decision:** The product is **Agencx** on every user-facing surface (B-1, B-2).
The visual identity is the existing Wren Material 3 system with its **crimson
primary** (already the shipped M3 tonal ramps in `frontend/src/styles/theme.css`,
CI-enforced by `check:tokens`) and **Plus Jakarta Sans** via `next/font` (a
token-level swap: `--font-sans` re-point, no component changes). The teal accent
from the Agencx planning design is retired, not carried forward. Copy never says
"AI", "agent", "automated" or "virtual" (PRD copy rules; W-9's copy-rule
amendment of 2026-09-06 took "assistant" off that list and put "virtual" on it,
because both mandated openings name the assistant as what the surface is).

**Why:** The merge decision locked "AgenCX PRD/design, Wren's Supabase auth +
crimson primary". The Wren rebrand proved the tokens-only path (a full visual
rebrand with zero component code changes); reusing it keeps the Agencx look
consistent with the platform the code already ships. The repo, roles, and env
names stay `wren` (renaming is churn with no user value - see the set README).
The mobile-first structure does return - see D18.

### D18: Mobile-first revival - the bottom tab bar returns from the planning prototype

**Decision:** The tenant app is mobile-first. On phones (below `lg`) the two-tab
manifest - Chat and Business - renders as an app-style surface with a persistent
**bottom tab bar**; at `lg+` the left sidebar stays. One codebase, responsive; no
native app, no PWA shell in Stage 1. The bottom tab bar pattern from the Agencx
planning prototype is carried forward; the rest of the prototype stays retired
(D17 - teal accent, cleaning copy, Hivee emblem). E-1 owns the implementation.

**Why:** Small-business owners live on phones; the tenant app's two destinations
map exactly onto two bottom tabs. The planning prototype validated the app-style
mobile interaction vocabulary (chat-first, thread as progress, no celebration),
and its screen inventory and states already match the S1/S2 specs. The pattern
also replaces the hamburger drawer and fixes the known narrow-mobile sidebar
squeeze (progress.md) - mobile stops being an afterthought of the desktop shell.

**Boundary:** The customer public page (S3) is untouched - it is a shared web
link, already chat-first and mobile. D17 stands for the prototype's identity
elements (teal, cleaning copy, Hivee emblem). This decision sets the
direction; E-1 delivers the chrome.

**Amended by D21 (2026-08-22):** the manifest is three tabs, not two - Home
joins Chat and Business. Everything else here stands unchanged.

### D19: Knowledge is one readable text the owner corrects, held until they save

**Decision:** A knowledge source - a pasted link or an uploaded file - is
extracted, then **processed into a fixed set of readable sections** (About, What
we offer, Prices, Hours, Location and contact, Policies, Other details) and
parked as a **draft**: stored, shown back, and answering nothing. It becomes
answerable only when the owner has read it and saved it, and what they saved -
their edits included - is what gets chunked, embedded and answered from. The
surface is **Settings > Knowledge** (`/settings/knowledge`), reached from a
Settings hub, and it renders the same sections it showed at review time.

**Why:** A list of files with statuses is a document manager, and it does not
scale for a real business: an owner with a dozen sources cannot tell what their
assistant actually believes by reading filenames. One structured text answers the
question they came with - "what does it think my business is?" - and makes
correction a matter of editing a sentence rather than re-uploading a file. The
draft gate exists because the first time an owner sees this text must not be
after it has already answered a customer.

**The money guard:** the processing step is a model rewriting the owner's own
material, and a price list is exactly the material it will handle. Every
monetary figure in the processed text must appear in the source, checked
deterministically with `extract_monetary_figures()` (the pricing gate's own
extractor); on any mismatch the processed version is discarded and the source
text is kept verbatim. This keeps I7 intact - a model still never authors a
monetary amount - and C-1 should adopt the same helper when it lands.

**Boundary:** the headings are the same for every business (I8 - the skeleton
does not branch on a vertical). Long sources keep their tail unstructured rather
than being cut. This decision amends the "no settings screen" ADR below: the
address changed, the substance did not - Knowledge is show-back-and-correct, not
a toggle tree.

## ADRs

### ADR: Import-boundary enforcement in CI

The codebase enforces the deterministic boundary (I1) with machine checks in
CI, because the violation that matters is the one added later under time
pressure. Determinism is a property of the module graph, not of willpower.

**Corrected 2026-08-22 (F-2), on two counts.** This ADR said the rule had been
in CI "from the very first commit". It had not: there was no import-linter
config, no ESLint rule and no AST test anywhere in the repo until F-2 wired
them. The ADR described an intention in the present tense for the length of the
build, which is worse than an admitted gap - nobody goes looking for a check
they have been told exists.

It also described the wrong contract. "Forbid importing `llm/provider.py`
outside `agents/` and `llm/`" fails on a dozen files today, and correctly so:
`features/chat`, `features/knowledge` and `features/onboarding` import
`LLMProvider` as a FastAPI dependency-injection annotation, which is how a
route receives a provider at all. Banning that would not protect determinism,
only wiring.

**What is enforced** (contracts in `backend/pyproject.toml`, run by
`make lint-backend` and CI):

1. **Pricing never reaches a model** - `app.pricing` may not import
   `app.llm`, `app.agents`, `app.onboarding` or `app.retrieval`. This is the
   hard rule itself; `engine.py` has always declared it in a docstring, and now
   a build fails on it.
2. **The deterministic services layer never asks a model for words** -
   `app.services` may not import `app.llm.provider` or `app.agents`.
   `app.llm.embedder` is deliberately allowed: an embedder turns text into a
   vector, and O-4's retrieval seam cannot work without one. The rule is about
   authorship, not arithmetic.
3. **The provider seam is a leaf** - `app.llm` may not import `app.features`,
   `app.agents`, `app.onboarding` or `app.pricing`, so swapping a provider by
   config cannot move anything above it.

The frontend carries the equivalent: `components/ui/**` may not import
`@/lib/api` or `@/lib/useApiQuery` (ESLint `no-restricted-imports`). The shared
library is presentational - a component that fetched its own data would decide
when a request happens from inside a render tree.

All four held on the day they were written, so they lock a property rather than
announce a migration. Each was proven to fail on a deliberately planted
violation before being trusted.

### ADR: No settings screen - Business tab as show-back only

The tenant app has no settings tree, no configuration screen, and no
toggle-only preferences. The second tab - **Business** - displays the profile
and knowledge the owner gave the agent, shown back so they can trust and
correct it. Every configuration change happens through conversation with the
Copilot, never through a form.

The product thesis is that the agent, not the owner, should absorb the
paperwork. If a setting can only exist as a toggle on a screen, it should not
exist. If the Business tab fails the trust test with a real cohort, the
decision is revisited - the signal is logged, not assumed away.

**Exception:** the Business tab carries the thin, product-required toggles the
PRD names: live/not-live state, the share link + QR, and the enabled-tools
toggle (D-1/D-3). These are scope, not settings-tree creep.

**Amended by D19 (2026-08-22):** a Settings destination does exist, and it holds
the Knowledge screen. It carries no toggles and no preferences - it is the
show-back surface this ADR asks for, at a different address. The rule the ADR
protects ("if a setting can only exist as a toggle on a screen, it should not
exist") is unchanged.

---

## D20: an escalation notifies; a takeover is what changes who is replying

**Date:** 2026-08-22 (C-5 / C-6). **Status:** accepted.

The schema had one terminal `escalated` status doing two jobs, and the result
was that any handoff ended the conversation. One unanswerable pricing question
could dead-end a support session that was working fine for everything else.

They are separate concerns and the code now says so:

- **An escalation is a notification** - "a human should look at this". It writes
  a queue row and says nothing about who is replying. The assistant keeps
  helping (C-5).
- **A takeover is a mode** - `conversations.status = 'human'`. A staff member is
  the voice; the assistant is silent until handed back (C-6). Reversible, and
  the interlude stays in the transcript so the assistant reads what the human
  said rather than contradicting it.
- **`'escalated'` means a limit stopped it.** Daily budget, step cap, turn
  budget. Written only by `record_limit_escalation`. This is the one hard stop,
  and it is the behaviour being paid for.

**A provider failure is not a limit.** It was originally routed through the
terminal path because it is another way a turn dies, but an upstream fault the
customer had no part in should not end their conversation - it hands off
non-terminally and invites them to try again. This was found by the C-6 E2E,
which the free-tier provider failed into on its first run.

**Consequence for the owner surface:** the escalations queue stops being a
separate destination - it is the "Action needed" filter on the Chats list, where
the owner already is. The Wren-era `/escalations` and `/conversations` screens
stay mounted for E-2 to hide.

---

## D21: three tabs, and Home is a place

**Date:** 2026-08-22 (pre-E-1, founder). **Status:** accepted. **Amends D18.**

The tenant app has **three** top-level destinations, not two:

- **Home** - the owner's own thread with the assistant, and the surface that
  greets them with what needs them today.
- **Chats** - the customers' threads with the assistant, and where the owner
  steps into one (C-6).
- **Business** - the hub: the show-back of what the assistant knows, the
  booking page and share link, Settings. Its rows are what grows in Stage 2.

Below `lg` these render as the bottom tab bar D18 established; at `lg+` they are
the left sidebar. One nav model, two renderings.

**Why:** two tabs could not name three places, and the prototype shows the
strain. In `agencx-prototype-v6.html` the home Copilot thread - greeting,
morning brief, command pill - is the base layer *underneath* the tab bar with no
tab of its own, and `navBack()` lights the **Chats** tab when you land back on
it. "Your thread with the assistant" and "customers' threads with the
assistant" are different destinations; collapsing them is exactly why that back
behaviour reads as muddled. Naming Home makes the third place addressable and
gives the brief somewhere to live.

**Why not a sidebar/drawer instead of the tab bar.** On a phone a sidebar is a
hamburger drawer: two taps to every destination, and no persistent answer to
"where am I". D18 retired it for that reason, and it is the cause of the
≤375px squeeze still open in `progress.md`. The founder's proposed row list -
Chats, Money, Business page, Settings - is the prototype's **Business hub**
(`renderScreen('business')`), not its top-level nav, and it stays there.

**Boundary:** this amends D18's tab count and nothing else. Mobile-first, the
tab-bar idiom, the retired drawer, and the untouched public page (S3) all stand.
**Money, Schedule and Plan remain Business-hub rows that Stage 2 adds** - they
are never top-level tabs, and until Stage 2 they are absent rather than
disabled (PRD, "never build dead surfaces"). Home's brief carries only item
kinds backed by real state; Stage 2's quote and order approvals arrive as new
kinds in the same list, not as new screens.

---

## D22: a tenant is a path, not a subdomain

**Date:** 2026-08-23 (founder). **Status:** accepted. **Supersedes decision 10's
"frontend host open"; rewrites B-2.**

**Decision:** A tenant is addressed at `agencx.app/{slug}`. The three surfaces
are paths on one origin, not three host patterns:

| Surface | Was | Is |
|---|---|---|
| Customer chat | `{slug}.agencx.app` | `agencx.app/{slug}` |
| Tenant console | `app.agencx.app` / apex | `agencx.app` (`/login`, `/home`, `/chats`, ...) |
| Platform | `admin.agencx.app` | `agencx.app/admin` |

Host resolution is gone, not made configurable: `resolveHost`, `surfaceUrl`,
`BASE_HOSTS`, the `x-wren-surface`/`x-wren-slug` request headers and
`frontend/src/proxy.ts` itself are all deleted. The customer page is a plain
dynamic segment (`app/[slug]/page.tsx`) that reads `params`.

**Why:** The subdomain scheme had stopped paying for itself.

It blocked the deploy outright. Vercel Hobby serves one `<project>.vercel.app`
with no wildcard subdomains, so the customer chat page - the product - could not
be reached at all on the deployed stack, and neither could the platform. Both
sat behind a wildcard DNS entry and a certificate nobody had bought. Paths make
the customer link work on the free tier the day it deploys, with no DNS step.

It also leaked downward. `GOTRUE_CORS_ALLOWED_ORIGINS` was a hand-maintained
list naming every dev tenant individually; the same wildcard origin regex was
written out three times (backend CORS, the auth-proxy shim, GoTrue); and the
platform surface needed an entire fake path segment (`admin-surface/`) plus a
proxy rewrite, because route groups do not segment URLs and two surfaces
collided at `/`. All of that is deleted rather than ported.

**Why not subdomains.** The case for them was private-per-tenant access. But
the isolation was never real - there is one backend, one database and one RLS
boundary behind all of it, and that boundary is `tenant_id`, not the host. The
subdomain bought an *appearance* of separation while charging for a wildcard
certificate, a hand-kept origin list and a middleware layer.

**Why not slug-scoped consoles** (`/{slug}/login`, `/{slug}/home`). It removes
the reserved-word problem, and it was rejected anyway. Slugs are generated at
first login as `{email-local}-{4 random}`, so an owner would have to know a
string they never chose in order to reach the page that would tell them what it
is. And the backend resolves the tenant from the JWT - a slug in the console URL
is a second source of tenant identity that can disagree with the first, which is
new authorization logic bought for nothing. The owner logs in at a global
`/login` and types their email, exactly as before.

**The cost, and the guard.** Every top-level route name is now a name no tenant
can have. `RESERVED_SLUGS` (`backend/app/features/tenants/slug.py`) refuses them
at owner self-onboarding, and
`frontend/src/lib/reserved-slugs.test.ts` fails the build if a route directory
is added without reserving its name - proven against a planted collision. Next
resolves static segments before the dynamic one, so a collision would not be
ambiguous, it would make a paying tenant silently unreachable.

**The other accepted cost:** one origin means the public customer page shares
`localStorage` with the authenticated console (`frontend/src/lib/auth-session.ts`,
key `agencx.login-session`). The separation the subdomain gave here was real,
if thin - both are our own first-party code, and the exposure only matters given
an XSS on the customer page, which would be serious regardless.

*(Resolved by D23: the session moved off `localStorage` onto a cookie, so this
specific cost no longer applies - see D23 for what replaced it and why.)*

**Boundary:** the resolver is untouched - `resolve_tenant_slug()` is still the
single audited RLS bypass, the slug DDL and its regex are unchanged, and no
migration ships with this. The API is unchanged too: the backend never read a
`Host` header, so slugs still arrive as a path param, a body field or a query
param exactly as before. **The TLD is not bound by this decision** - `.app`,
`.com` or anything else is a purchase and a find-and-replace, made when B-2
ships.

## D23: login-in-chat moves onto GoTrue OTP; sessions move onto @supabase/ssr cookies

**Date:** 2026-08-28 (founder). **Status:** accepted. Closes G2.1 and G2.2 in
`docs/archive/industry-standard-gap.md` (`FLAG: auth-model change`).

**Decision:** The backend stops issuing and verifying its own login codes.
GoTrue's own OTP flow (`signInWithOtp` / `verifyOtp`, type `email`) replaces
`auth_codes` + `services/{auth_codes,email,email_address,identity}.py` +
`/api/auth/*` - all deleted rather than kept alongside. GoTrue mints the
session (1h access token, rotating single-use refresh token) instead of the
backend signing its own HS256 claims. The frontend stores that session in a
cookie via `@supabase/ssr`'s `createBrowserClient`/`createServerClient`
instead of `localStorage`, and a new `frontend/src/proxy.ts` refreshes it and
redirects a signed-out request before a protected page renders.

`shared/auth.py::verify_token` gains ES256/RS256 verification via the
project's JWKS (`PyJWKClient`, cached), selected by reading the token's own
`alg` header; HS256 against the shared secret remains the path for local
GoTrue. This was already a known gap on its own (`progress.md`'s "known gaps"
noted the hosted `/admin` surface 401ing because the hosted project signs
ES256 and `verify_token` only checked HS256) - the OTP migration made fixing
it unavoidable anyway, since GoTrue-minted sessions are the same tokens
platform admin already gets, and now the tenant flow gets them too.

**Why.** `auth_codes` was ours: a bespoke 6-digit code table, our own SMTP
seam, and a backend-minted session with no refresh, no rotation, and no
revocation (G2.1) - stored in `localStorage` and guarded only by client-side
`useEffect` checks (G2.2). GoTrue was already running for platform admin.
Moving the tenant-owner flow onto the identity store already in the stack
costs nothing extra and closes both gaps in one ticket instead of two.

The interaction remains email in and a 6-digit code back. The resend control
now stays inactive for 60 seconds, matching GoTrue's production
`SMTP_MAX_FREQUENCY`, instead of the previous backend flow's 30 seconds.

**Why not httpOnly cookies.** The gap doc's own G2.2 write-up said "httpOnly
cookies" as the target shape, and that was wrong - checked against
`@supabase/ssr`'s source and docs while building this. The package's cookie is
deliberately JS-readable: the browser client has to read and write it itself
to run `signInWithOtp`/`verifyOtp`, to refresh in the background, and to clear
it on sign-out - an httpOnly cookie would break the client the package exists
to support. The security posture is rotation, not secrecy of the cookie: a 1h
access token, a single-use rotating refresh token, PKCE on the OTP exchange,
and `Secure`/`SameSite=Lax` on the cookie itself - with the backend's own
verification and RLS underneath as the real enforcement boundary, unmoved by
any of this. `industry-standard-gap.md`'s G2.2 entry is corrected to say this.

**`frontend/src/proxy.ts` is a new file, not a revival.** D22 deleted a
`proxy.ts` that did host-based tenant routing (`resolveHost`, `BASE_HOSTS`,
the `x-wren-surface` header) - gone for good, paths replaced it. This one does
something unrelated: refresh the session and redirect before render for a
signed-out request to a console or `/admin` path. It is UX, not the
enforcement boundary (CVE-2025-29927 is why that boundary stays the backend's
Bearer check plus RLS, never the proxy alone) - a positive route matcher, and
`/[slug]` and `/` are untouched by it, same as D22 left them.

**Cutover.** Self-minted sessions were 1h TTL and lived under the
`agencx.login-session` `localStorage` key; the new frontend never reads that
key again, so a session from before this ships expires within the
hour rather than needing a forced mass logout.

**Boundary:** the backend's Bearer-header contract is unchanged (a route still
takes `Authorization: Bearer <token>` and verifies it the same way regardless
of who issued it), and RLS is untouched. Only session issuance and storage
moved. `POST /api/tenants` absorbs first-login provisioning (empty body ->
create-or-return the caller's tenant) instead of a new endpoint, since it
already was "authed user -> provision tenant" with the audited service-role
write path the seed scripts depend on.

## D24: Offerings become owner-writable; reusable business media moves to Cloudinary

**Date:** 2026-08-28 (founder, designed in a Codex CLI session; recorded here
after that session ran out of usage before it could write anything down -
provenance below). **Status:** `M-1`, `M-2`, `M-3`, and `M-4` built; live
Cloudinary smoke testing remains credential-dependent - see
`docs/agencx/spec/completed/11-offerings-media.md`.
Closes G5.1 in `industry-standard-gap.md`, broadened past that ticket's
original scope. `FLAG: new external service` (Cloudinary). `FLAG: schema
change` (`tenant_assets` widens or is replaced).

**Amendment (2026-08-29):** The initial five-image gallery scope was narrowed
to one Cloudinary-backed cover and one optional visual per offering. Offering
media accepts files or URLs; YouTube and Vimeo remain controlled external
providers. The owner page removes About, and the public page is a categorized
catalogue with Share and contextual chat actions.

**Decision:** Four things, decided together because each one shapes the others.

1. **`Offering` is the one domain noun** for anything a business sells - a
   tradie service, a dental appointment, a menu item, a retail product, a
   package. Owner-facing heading is "What you offer"; customer-facing is
   "What we offer". The `offerings` table is the implementation underneath
   that noun, not a second concept next to it.
2. **The catalog and the knowledge base stay two systems, joined only at
   answer time.** The catalog (`offerings`) is the structured source of
   truth for name/price/availability; the knowledge base stays prose (policy,
   FAQs, general info). A generated search projection off the catalog lets the
   agent *find* candidate items during retrieval, but the agent always
   re-fetches the authoritative row before stating a price or availability -
   it never trusts the embedded chunk text. This is not new invention:
   `_recommend_items_impl` (`backend/app/agents/agent_node.py:195`) already
   does exactly this search-then-re-fetch pattern for the one live catalog
   reader that exists today; the decision is to build the writer path the
   same way, not to invent a different one.
3. **Cloudinary, not Supabase Storage, for offering and cover media.**
   Supabase Storage stays correct for knowledge *documents* (unchanged - it
   already backs `shared/storage.py`'s `SupabaseStorage`). Media is a
   different problem: reusable, transformable, CDN-delivered images attached
   to offerings and the business cover, not opaque private byte blobs. Google
   Photos-style client-side downscaling stays (it already exists,
   `CoverPhoto.tsx:22-48`), but delivery and storage move to a provider built
   for that job.
4. **One business cover and one optional visual per offering**, attachable
   after an offering is confirmed - not required at confirm time. The scope
   stays deliberately small: no separate photo-gallery editor, no multi-image
   carousels-of-carousels, no dropdown/variant picker UI, and no automatic
   PDF-image-to-item matching. The storefront highlights what the business
   offers without asking an owner to maintain a page-builder surface.

**Why the catalog/knowledge split, not one merged store.** The founder's own
instinct going in was to avoid the owner ever entering the same information
twice, which is right - but the fix is *one confirmation step*, not *one
storage system*. Sierra separates knowledge management from tools/dynamic
data/systems-of-record; Decagon separates knowledge-base retrieval from
APIs/integrations that hold live structured data; Airbnb runs listing search
(structured, embeddings + ranking) and support knowledge search (vector
knowledge base) as genuinely separate retrieval systems behind one API layer.
Tidio Lyro - the closest product analogue to Agencx's audience (small
businesses without an existing Shopify/WooCommerce catalog) - presents one
unified owner-facing "Knowledge" area while keeping products as an internally
distinct, separately-synced source. Agencx's gap next to Lyro: Lyro still
expects the owner to choose product sync as a separate step; nothing in its
public docs detects menu items inside an arbitrary uploaded PDF and proposes
them as structured products. That gap is the opportunity - see the
import-and-confirm decision below.

If catalog content were instead folded into ordinary knowledge chunks, a
price edit would require re-embedding prose, the fast-path retrieval
(`whole_corpus()`, `backend/app/services/retrieval.py:100`) would hand raw
catalog text straight to the model with no re-fetch, and a stale PDF price
could out-rank a corrected one - a direct collision with the standing money
rule (no model states a figure it didn't get from the owner's material or the
deterministic engine).

**Why Cloudinary over Supabase Storage.** Scoped narrowly (G5.1: replace the
`tenant_assets` bytea cover with something in object storage), Supabase
Storage wins outright - it's already integrated, already used for documents,
free tier covers a single cover image many times over. That was the first
answer given, and it was wrong for the actual ask: reusable media across a
storefront (the cover and offering visuals) benefits from Cloudinary's
server-signed uploads, CDN delivery and on-the-fly responsive transforms in a
way a plain object-storage bucket does not replicate without building the
transform layer separately. Cloudflare R2 + Images was the credible
cost-first alternative (10GB free storage, 5,000 free unique transforms/mo)
but needs two separate Cloudflare services stitched together; Cloudinary is
one provider for the whole job. The quota is a real constraint, not hidden:
Cloudinary's free plan is 25 credits/month shared across storage, bandwidth
*and* transformations - workable for a Stage-1 storefront's traffic, not a
production-scale promise. The trigger to reconsider is ordinary usage
growth, not a design flaw to fix now.

**Why import-and-confirm, not two separate onboarding steps.** The founder's
ask was explicit: an owner who already uploads a PDF/URL with hours, policy,
*and* a menu should not have to re-type the menu a second time into a
separate catalog screen, but the extraction must never become the source of
truth on its own. The resolved pattern: ingestion classifies sections as it
already does (O-3's headed sections), facts/policy save as knowledge exactly
as today, and any section under `"What we offer"`/`"Prices"` becomes a
*candidate* offering shown in one lightweight confirm step - reusing the
existing Settings > Knowledge `ReviewSheet` review pattern rather than a new
questionnaire. Only what the owner confirms becomes an `offerings` row.
Re-uploading the same or an updated document later proposes a diff against
what's already confirmed; it never silently overwrites an owner's own edit -
the owner's live catalog edit always outranks a stale document, matching the
same "confirmed value wins" rule the money guardrail already lives by.

**The naming decision.** `M-1` renamed `catalog_items` to `offerings` in
migration `0023`: the table's generic existing row shape already was an
Offering, and retaining a second physical name would keep two terms for one
concept. The migration preserves RLS policies and grants because they follow
the table OID. The ticket records the full reasoning.

**One name deliberately not renamed.** Chunk `metadata.kind = "catalog_item"`,
`metadata.catalog_item_id` and `documents.doc_type = 'catalog'` stay as they
are. Those name the *search projection* built off the table, not the table:
the catalog is the projection, offerings are the rows. They are also stored
data rather than vocabulary - renaming them would leave every existing chunk's
metadata stale until a full re-ingest, for no reader's benefit. Recorded here
so the remaining "catalog" spellings read as a boundary rather than a missed
find-and-replace.

**Prices are owner-typed facts, and they are shown.** Settled by the founder
during `M-4` (2026-08-28), after that branch had briefly built offerings
without prices at all on the reasoning that "the page describes, the agent
quotes". It does not hold: a menu item or a service the owner has priced is
one whose price a customer expects to read on the page, and hiding it makes
them ask a question they should not have to ask. So an offering carries an
optional `price_cents`, the owner types it, the storefront renders it, and
the assistant may state it.

None of that relaxes the money rule, and the mechanism is why: the value is a
decimal the owner typed, validated at the API boundary and stored as integer
cents; the storefront formats cents to dollars and performs no other
arithmetic; and the assistant reaches the figure the two ways it always could
- `agent_node.py`'s search-then-re-fetch of the authoritative row, or a
verbatim quote from owner material. What the founder ruled out is the model
inventing a figure when none was published, which is exactly what the
validation gate already refuses. A priced offering makes the honest answer
available; it does not make a dishonest one possible.

**Boundary:** the money rule is unchanged and unrelaxed by any of this - no
model produces, edits, or infers a price; a confirmed offering's price is
always a verbatim slice of the owner's own text (reusing
`extract_monetary_figures`, `backend/app/pricing/validation_gate.py:104`,
exactly as `business/offerings.py`'s read-time derivation already does today)
or an owner-typed value, never a computed or model-drafted one. This ADR does
not itself change any code - the concrete implementation gaps it depends on
closing (the now-built owner-facing `offerings` writer; `tenant_assets` is
schema-capped to one row per tenant; the fast-path retrieval now filters
catalog-kind chunks out of general knowledge answers; `knowledge_version` now
includes `offerings.updated_at`) are catalogued in
`11-offerings-media.md`'s tickets, not here.

**Provenance.** This design was reached over a long conversation between the
founder and a Codex CLI session (branch `feat/offerings-media-import`,
2026-08-28), starting from the G5.1 gap and widening once the founder pushed
back on the narrow framing. That session said it would record this exact
design in the canonical docs and then hit its usage limit mid-sentence,
before writing anything - the branch had zero commits and no doc mentioned
any of this when this entry was written. This ADR, and the tickets in
`11-offerings-media.md`, are that recovery: reconstructed from the session's
own transcript and independently re-verified against the current code before
being written down, not taken on faith from either party.
