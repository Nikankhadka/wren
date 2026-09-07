# Agencx PRD

The product authority. Why, who, what, Stage 1 scope, and the signals that decide
what happens next. This replaces the pre-Agencx planning docs (archived under
`docs/archive/`); the technical ceiling that implements it lives in
`architecture.md`, the tickets in `spec/`.

## 1. What Agencx is

Agencx is a **domain-agnostic agentic business assistant**. Any small business
self-onboards through a single conversation and gets a private agent that talks
to its customers on its behalf: greeting requests, answering from the business's
own profile and materials, taking the load while the owner is busy, and never
standing in for the owner on anything that must be decided or paid.

One codebase, per-tenant config and knowledge. **No vertical branching anywhere
in code** (invariant I8): a shawarma restaurant, a cleaner and a dental clinic
all run the same software; the difference is the data they supply and the
configuration that shapes the interview that gathers it.

Agencx is the continuation of the shipped Wren build, re-scoped around three
screens and a lean-by-default toolset. Everything Wren proved - grounded
answers, cross-tenant isolation, the deterministic money boundary, the
generalization proof - carries over; the advanced machinery (quoting,
recommendations, order lookup, the pricing engine) becomes per-tenant opt-in
instead of the default experience.

## 2. The problem and the reference class

Small businesses run on their owner's attention. A menu, rates, hours, answers
to the same five questions every week - all of it lives in the owner's head.
Customers don't care about workflows; they ask "can you do catering for 15
people?" and want an honest, grounded answer now.

The human answer today is a **freelance admin helper**: $1,500+/month of someone
who knows the business. That generalises exactly to what an agentic assistant
does - with differences the product owns:

- It is always available, including the hours the business is closed.
- It answers only from materials the owner supplied - it cannot invent, and when
  the answer is not in the material it says so. The worst failure in the product
  is a made-up number.
- It learns the business once, in conversation, instead of being taught by the
  owner repeatedly.

The wrong reference class is job-management software ($69/month subscriptions
that make the owner redo the paperwork an assistant should absorb).

## 3. Personas

Three personas for Stage 1. Names are canonical and stable across all docs.

### Sam - the operator (the tenant)

A sole trader or small-team owner, generalised across any vertical. The worked
example: **reference tenant 1: Sababa, a shawarma restaurant in Bondi Junction** -
five staff, a lunch counter, and catering enquiries that arrive while the owner
is behind the grill.

**Job to be done:** get the chatty side of the business running with the
smallest possible share of attention: one conversation to set up, a few uploads,
and a link to hand out.

**Patterns:**

- Anxious about anything that feels like a company portal. One conversation is
  fine; a tree of forms is not.
- Trusts a customer-facing assistant only as much as it echoes what he said. The
  Business tab shows his profile and materials back, so a wrong fact is
  something he can see and correct.
- Is offline during most of the hours questions arrive. The public page is the
  "you're off" side.
- Tests the assistant: asks twice what it cannot do, and if it misleads rather
  than refusing, he stops recommending it.

### Alex - the customer

Anonymous. No account, no login, no identity - walks in from a link or QR scan,
often from an incognito window, mid-decision.

**Job to be done:** actually answer. "Can you cater for 15? What's in the box?
Are you open today?" A real answer, fast, grounded. No login wall; every
material fact cites its source; a refusal is a badge of honesty when phrased in
the business's voice.

### The platform owner

The operator of the service itself. Stage 1 surface is minimal: a tenants table
(slug, name, status), suspend/reactivate, and the place where the
generalization proof is watched.

## 4. Reference tenants

Verticals are configuration, never identity. Three reference tenants anchor the
build and prove I8:

| Tenant | What it is | Role |
|---|---|---|
| **Reference tenant 1** | Sababa, a shawarma restaurant in Bondi Junction - a catering business with a menu and catering rates | The **anchor**: Stage 1 must make this tenant's public page hold a real conversation |
| **Reference tenant 2** | A residential cleaning business | **Proof 1** of I8 - onboarded via the public path alone, no code change |
| **Reference tenant 3** | A dental clinic | **Proof 2** of I8 - structurally different, still no code change |

A code change required to onboard any tenant is a bug in I8, not a feature
request. (Proof 2 is delivered: the dental clinic went live on identical code in
the Wren build; evidence in `docs/archive/artifacts/generalization-proof.md`.)

## 5. The two stages

| Stage | What it is | Status |
|---|---|---|
| **Stage 1 - the assistant** | Owner self-onboards in a chat, lands in a three-tab app (Home, Chats, Business), uploads knowledge, and an anonymous customer can ask its public page questions grounded in that material. No leads, no quotes, no payments, no scheduling, no invoicing. | **Build now** |
| **Stage 2 - the back-office** | Lead qualification, deterministic quoting, approval gates, payments, scheduling, write-once invoicing, post-job care. The assistant gains the machinery to close and manage work. | After Stage 1 validates |

Stage 2 is the same product's promise, deferred - not a different product. It is
tracked as backlog (see `docs/archive/agencx-planning/stage-2-backlog.md`) but
is not planned or ticketed until Stage 1 reports back.

## 6. Stage 1 scope

### The spine - built end to end

1. **The first conversation.** The owner opens the chat page (no sign-up form).
   Types an email; a 6-digit code arrives by email; types it back. Authenticated
   inside the conversation.
2. **The interview.** The same agent gathers name, business name, business type,
   headcount, hours, what is sold - into a small profile. The business type
   selects what is asked (config, not branches).
3. **Going live.** The tenant reaches a ready state and lands in the three-tab
   app: Home, Chats and Business.
4. **Knowledge.** The owner adds material - menu, FAQs, catering rates, terms.
5. **Share.** The owner hands out the public link or QR.
6. **The anonymous visit.** Off-hours, an incognito visitor asks a plain-language
   question.
7. **The grounded answer.** The assistant answers from the profile and the
   uploaded material, with citations; when nothing relevant exists, it refuses
   and records the ask.
8. **The money guardrail.** A figure may be stated only when that exact figure
   appears in owner-supplied material or is the output of the deterministic
   pricing engine (which runs only for tenants with quoting enabled). Never
   computed by a model, never invented. The guardrail is the floor under the
   whole spine, not a step after it.

### Screen manifest

| # | Screen | Surface | Notes |
|---|---|---|---|
| S0 | **Home** | tenant app tab 1 | where the owner lands after go-live: the greeting and the brief - what needs them right now |
| S1 | **Chats** | tenant app tab 2 | the customers' conversations, and stepping into one; contains login-in-chat and the onboarding interview before go-live |
| S2 | **Business** | tenant app tab 3 | the show-back surface (profile + knowledge), editable - NOT a settings tree |
| S3 | **Public page** | anonymous | per-tenant slug, share link + QR; the only customer surface in Stage 1 |

The advanced Wren surfaces (conversations with traces, dashboards, escalations
queue, pricing editor) are hidden from the tenant app navigation, not deleted.
They stay reachable by code and by the platform owner until Stage 2 re-lands
them with a purpose.

The three-tab app is mobile-first: on phones the tabs render as an app-style
bottom tab bar (D18, D21), on desktop as a sidebar (E-1). D21 added Home
because the prototype's home thread had no tab of its own - "your thread with
the assistant" and "the customers' threads" are different places.

### What is explicitly out

- No lead records, quote objects, payments, scheduling, or invoicing as default
  flows (quoting machinery exists but is per-tenant opt-in and off by default)
- No signup form, no settings tree, no configuration toggles
- No welcome screen, no progress bars, no celebration, no dead surfaces
- No model-computed pricing - the assistant may repeat a figure from owner
  material, or one produced by the pricing engine for quote-enabled tenants, but
  never compute one

### Never build dead surfaces

Every screen and control maps to a step in the spine or to a keep/pivot/stop
signal. Anything that would exist only "to show progress" is not built.

## 7. The money guardrail

The product promise: a figure may be stated only when that exact figure appears
in owner-supplied material, or is the output of the deterministic pricing
engine. Never computed by a model, never invented. The allowed sources, in
order:

1. **Owner-supplied material verbatim** - the figure appears exactly as written
   in a document, the profile, or the pricing rules/catalog the owner
   configured. "About $40" or "roughly $39" fails.
2. **Pricing-engine output** - a total the engine computed in integer cents,
   presented exactly. This source exists only for tenants with quoting enabled
   (see tool gating, below).

This is enforced by a deterministic money guardrail node that checks every
figure in every assistant reply against the allowed sources - rewrite-once, then
escalate. Inventing a number is the one failure that must be impossible.

## 8. Tool gating (how the lean default works)

Every tenant has an enabled-tool set. The assistant's tools are built from that
set - no fixed list, no hidden capabilities. The lean default is:

- **Answer from knowledge** (the grounded Q&A path)
- **Escalate to a human**

Optional per-tenant additions (off by default): recommendations, quoting,
order/ticket lookup. The pricing engine runs only when quoting is enabled. A
tenant that never asked for quotes gets a refusal path ("I can't quote that yet -
I'll have the owner call you"), never a guessed number. The Business tab shows
the toggle surface so the owner decides.

The lean default means the small-business Phase 1 flow - the Sababa slice - is
one grounded answer path, not a menu of sales machinery.

## 9. The speed contract

The customer-facing answer must arrive fast enough to feel like a person
answering. The product promise:

- Time to first token target: **under 2 seconds** in the normal case (pre-loaded
  context, one LLM call per turn).
- Hard cap: **10 seconds** to a complete answer. If the primary provider has not
  produced a first token within 4 seconds, the platform fails over to a
  secondary provider (first-wins - whichever completes first is used).
- The client shows a natural typing indicator while the answer is being
  assembled; the customer never sees a spinner or a blank.

Implementation detail lives in `architecture.md` (latency budget + failover) and
tickets P-2, P-3, P-5 in `spec/`.

## 10. Keep / pivot / stop signals

| Signal | Measure | Action |
|---|---|---|
| Activation | % of visitors who reach "live" in one conversation; drop-off recovery rate | keep - the thesis holds or the interview is trimmer |
| Trust | public page answers carry citations; refusal rate stays sane (unmet asks are visible) | keep when grounded; pivot the tone/rules if answers read as evasive |
| **The money guardrail** | adversarial "a price anyway" attempts can never produce a number | keep; a single invented figure is a **stop-and-fix-the-panel** run, not a bug ticket |
| **Latency** | % of turns under 10s; failover trigger rate | keep when the cap holds; a persistently slow answer is a stop-and-fix, not a tuning ticket |
| Generalization | a cleaner and a dental clinic onboard via the public path alone with zero code change | keep; a code change required = bug in I8 |
| **STOP gate** | if the tenant-1 page cannot hold a grounded conversation, stop - re-scope retrieval before any Stage 2 planning | |

## 11. Plans and packaging

| Plan | For | What it contains |
|---|---|---|
| Starter | Anyone trying the assistant | Stage 1 live tenant, one public page, usage credits - free while Stage 1 validates |
| Pro | The working sole trader ($249/mo anchor) | Stage 2: quoting, payments, scheduling, invoicing - the back-office contract |
| Scale | Bigger teams | Team members, multiple channels, platform polish - the deferred tail |

Stage 1 ships free with **zero paid dependencies** (decision 6), so the public
validation phase has no cost floor. The testing budget ceiling for the build is
$10/month (decision D16).

## 12. Glossary (Stage 1 subset)

### Tenancy and isolation

| Term | Meaning |
|---|---|
| **tenant** | One business on the platform; its own row space in the database (`tenant_id` everywhere, invariant I5). A tenant is configuration + knowledge, never a fork |
| **slug** | The tenant's public identifier, resolves via `resolve_tenant_slug()` |
| **business type** | A `business_types` row: a profile template and prompt fragments. Data, never a code branch (I8) |
| **reference tenant** | A labelled example vertical used in docs and seeds |
| **enabled tools** | The tenant's per-tenant tool set (`tenant_config.enabled_tools`); the assistant's tools are built from it |

### Roles and people

| Term | Meaning |
|---|---|
| **operator** | The business owner (persona Sam), the tenant's admin |
| **customer** | Anonymous visitor on the public page (persona Alex); no account, no portal |
| **actor_id** | Who did the row - operator, assistant node, or the platform |

### Conversations

| Term | Meaning |
|---|---|
| **auth code** | The 6-digit email-issued code that authenticates the owner inside the conversation - no sign-up form |
| **login-in-chat** | The pattern: typing an email / code in the chat thread itself |
| **conversation** | A thread; tenants have one in Chat; public page threads are per-visitor and anonymous |
| **message** | A row in a conversation (role, content, tenant_id denormalised) |
| **drop-off / resume** | Leaving an interview mid-flow and returning to the same state later |
| **unmet ask** | A recorded question the assistant could not answer (the roadmap instrument) |

### Grounding and knowledge

| Term | Meaning |
|---|---|
| **grounding** | Answering only from the tenant's profile + uploaded material; everything else is refused |
| **document** | An owner upload (menu, FAQ, rates, terms) |
| **knowledge_chunk** | A stored slice of a document with embedding + tsvector |
| **get_business_context(tenant_id, query)** | The single entry point for grounded context; whole-corpus fast path below the token threshold, hybrid retrieval above it |
| **context package** | The pre-loaded, cached bundle (system prompt + profile + corpus) assembled when the chat opens, keyed by `(tenant_id, knowledge_version)` |
| **knowledge_version** | A derived version of the tenant's knowledge (max document update); invalidates the context package on re-ingest |
| **citation** | A reference to the exact chunk a fact came from; rendered as an inline chip |

### Evaluation

| Term | Meaning |
|---|---|
| **golden set** | Hand-labelled query-to-chunk pairs with negatives, grown each phase |
| **recall@k, MRR, nDCG** | Retrieval metrics |
| **absolute vs regression gate** | Deterministic gates never skipped (leakage, money air-gap) vs regression-tolerated judged metrics |

### Money and the guardrail

| Term | Meaning |
|---|---|
| **integer cents** | All money columns are integers in cents (I1) |
| **money guardrail** | A deterministic node: every figure in an assistant reply must appear in owner-supplied material or pricing-engine output; otherwise rewrite-once-then-escalate |

### Surfaces

| Term | Meaning |
|---|---|
| **Chat** | Tenant app tab 1: login-in-chat, onboarding, then everyday conversation |
| **Business** | Tenant app tab 2: profile + knowledge shown back, editable (show-back, not settings) |
| **bottom tab bar** | The mobile navigation (D18): Chat + Business as persistent bottom tabs on phones, sidebar on desktop |
| **public page** | Anonymous per-tenant page at a slug; share link + QR |

### Stages and readiness

| Term | Meaning |
|---|---|
| **Stage 1** | The assistant slice (build now) |
| **Stage 2** | The back-office slice (after Stage 1 gates) |
| **ready / live** | Onboarding's complete state; only live tenants have a public page |

## 13. Copy rules

- "Assistant" may name the surface, on both owner-facing (onboarding) and
  customer-facing copy - the onboarding opening ("I'm the Agencx setup
  assistant") and the customer opening ("I'm [Business]'s assistant") both
  depend on this. "AI", "agent", "automated", and "virtual" stay out of
  routine copy on both surfaces regardless. A customer who asks directly
  whether they're talking to a human or an AI is answered honestly - the
  exemption above is about the noun used in routine copy, never a license to
  mislead when asked outright. (Amended 2026-09-06, W-9 - see
  `spec/active/13-walkthrough.md` Amendment 3; the original blanket rule
  predates both mandated openings.)
- Lead with outcomes, not features
- Plain dash, never the em dash (U+2014)
