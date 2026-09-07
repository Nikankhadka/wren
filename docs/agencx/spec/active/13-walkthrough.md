> This file was amended twice: 2026-09-05 folded a second walkthrough round
> and its planning into the phase (record starts at
> [Amendment 2](#amendment-2-onboarding-completion-and-refinement-2026-09-05));
> 2026-09-06 rewrote W-9 into the single authoritative onboarding and
> customer-assistant contract ticket and corrected stale delivery-status
> language left over from the first amendment (record starts at
> [Amendment 3](#amendment-3-the-agent-contract-2026-09-06)). W-1 through W-8
> are shipped and their records, checked criteria, and commit evidence are
> preserved below unchanged; W-9 is the phase's sole open ticket.

# Phase 13: walkthrough fixes (W)

A founder walkthrough of the deployed build surfaced defects across three
surfaces: the owner's home escalation queue, the onboarding interview, and
customer chat grounding. A second walkthrough round, its repository scans, and
the subsequent planning extend this phase to nine tickets (W-1 through W-9)
and refine what W-3 through W-6 must deliver; W-8 and W-9 are new. W-1, W-2,
and W-7 shipped and their records are preserved below; the refinement amends
their behavior where noted under each ticket and in the amendment record.

Some of what the walkthrough asked for already shipped on this branch and
needs refinement, not rebuilding:

| Commit | What it already delivers |
|---|---|
| `8496f25` | Rounded escalation card, count pill on top, per-customer rows with name, age, and an assistant-written summary, oldest first, direct `/chats/:id` link, amber count badge on the Chats tab |
| `497bbf3` | Onboarding knowledge review sheet, document offering candidates |
| `0ebd1fc` | Confirmed offerings injected into the customer system prompt |
| `48c7acb` | W-1: escalation queue fitted to the screen, interval refresh (shipped) |
| `f2db993` | W-2: interview never re-asks a filled slot, every beat capped at two asks (shipped) |
| `cd10f6e` | W-7: answers made usable and resumable, single priced review card (shipped) |

So the escalation ask is largely built; W-1 covers what remains. The
onboarding and retrieval defects (W-3 through W-6) are unaddressed, and W-8
and W-9 extend the phase into review usability and conversational correction.

Ticket id prefix `W-` (Walkthrough), unused elsewhere in the ticket set. Nine
tickets, in build order: W-1 and W-2 shipped, W-5 precedes W-6 so the reported
chat bug closes before the document-extraction feature builds on top of it,
W-7 shipped after W-6, and W-8 and W-9 extend the review sheet and the
interview that the earlier tickets touched. **W-1 through W-8 are all
delivered; W-9 is the only open ticket in this phase** (corrected 2026-09-06 -
`progress.md` had drifted to claim W-3 through W-6 were still open after they
shipped).

Dependencies between the refined and new tickets (requested later work links
to the behavior it refines instead of duplicating its acceptance criteria):

- W-4 depends on W-7's shipped address-only confirmation behavior, which it preserves.
- W-6 produces the richer offering candidates that W-8 reviews; W-8's save feeds W-5's grounded answers.
- W-9's offering corrections reuse the update boundaries W-6 and W-8 extend.
- W-5 and W-6 both depend on the source-backed offering data W-8's review decisions finalize.

---

## Amendment 2: onboarding completion and refinement (2026-09-05)

A second founder walkthrough of the running onboarding and document-review
flow, supported by repository scans and planning, refined the phase. This
section records the walkthrough's observations, the founder's clarified
preferences, the current implementation evidence, and the boundary between
reported symptoms, confirmed code behavior, suspected causes, and
outstanding browser verification. It is the single evidence home for the
refinements; the tickets below reference this section rather than restating
it. The original PDF behind the 40-row review output is unavailable, so the
pasted review output is preserved here as reported but cannot establish which
prices, descriptions, or offerings correctly reflect the source - an
explicit verification boundary, not a gap in this record.

### The founder's clarified preferences

The agreed product decisions preserved in the refined tickets:

- Keep the existing business-information, hours, location, policies, and
  other-information sections; improve their readability and editing without
  discarding factual detail.
- Show five offerings initially. "Review all" opens the editor with five
  offerings per page.
- Suggest possible duplicates and let the owner combine them or keep both.
- Preserve complex pricing context and flag ambiguity instead of inventing a
  flat price.
- Let uploads process responsively while the owner remains on the page.
- Correct clear spelling mistakes in ordinary descriptions and offerings using
  the existing model call; preserve personal names and brand names unless
  explicitly corrected.
- Quotation functionality and a full pricing-rule editor remain future work.

### Reported observations (from the pasted review output and walkthrough)

The pasted review output proves what the owner reported seeing. The concrete
defects and phrasing flags in it:

- Offering names rendered as sentence fragments or prose joins
  (`"Bowl is,"`, `"the,"`, `"Plate and Pita Pocket both run"`), none of which
  is a sellable item.
- A possible duplicate pair reported for review (`"coffe"` alongside
  `"coffee drinks"`), where the owner's preferred outcome - keep both, or
  merge only on explicit choice - is not yet reflected in how the sheet
  behaves.
- Displayed amounts in the output. Because the original PDF is unavailable,
  which amount (if any) is correct is not established; the amounts are
  recorded as reported and flagged for re-extraction from source when the
  PDF regression fixture becomes available.

The full 40-row pasted output is greater than the examples above; only the
observations the notes name are transcribed here because the paste itself is
not preserved verbatim. Where a later step reproduces the source, the
regression fixture replaces this table as the authority.

| # | Reported (pasted review) | Ticket | Classification |
|---|---|---|---|
| 1 | Offering name fragments: "Bowl is", "the" | W-6 | Symptom |
| 2 | Prose-joined offering names: "Plate and Pita Pocket both run" | W-6 | Symptom |
| 3 | Possible duplicate pair: "coffe" / "coffee drinks" | W-6, W-8 | Symptom |
| 4 | Displayed amounts (source-correctness not established) | W-6 | Symptom |
| 5 | Whole catalogue or raw sections in the review sheet | W-8 | Symptom |
| 6 | Complex price context (ranges, "from", units) flattened or dropped | W-6 | Symptom |
| 7 | Descriptions missing or invented | W-6 | Symptom |
| 8 | Review sheet hard to scan when many candidates | W-8 | Symptom |
| 9 | Same text twice within a single reply (duplicated names) | W-9 | Symptom |

### Confirmed code behavior, suspected causes, and outstanding verification

A repository scan separated what is real in the code from what remains a
runtime hypothesis. This is read-only evidence; none of it is a shipped fix.

| Area | Status | Evidence |
|---|---|---|
| Reply context includes the current owner message twice | Confirmed code | [agent.py:688-713](../../../../backend/app/onboarding/agent.py#L688-L713): `record.history.append({...admin_message})` (line 691) runs before `reply_msgs` is built, whose `record.history[-3:]` loop (lines 711-712) includes that just-appended message, then `admin_message` is appended again (line 713). Its relationship to the reported duplicated names is a **suspected cause** pending browser reproduction |
| Review-return paths skip slug prefill | Confirmed code | `saveKnowledge`/`discardKnowledge` set confirm state without running `applyStateFields`' slug prefill (see [page.tsx:458-499](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L458-L499) and [page.tsx:141-157](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L141-L157)). Requires browser reproduction against the go-live screen to call the runtime cause established |
| Upload stamp is client-side only, non-streamed | Confirmed code | [page.tsx:398-417](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L398-L417) - a static `"adding…"` stamp over a single non-streamed `POST /api/knowledge/drafts/upload`; no progress events, so any progress shown is client-side animation, never fabricated percentages |
| Review sheet renders every candidate in one scroll | Confirmed code | [ReviewSheet.tsx:134-212](../../../../frontend/src/components/knowledge/ReviewSheet.tsx#L134-L212) - a single `offerings.map`, no pagination; duplicates are a hard save block (`hasDuplicateNames`, [ReviewSheet.tsx:257-264](../../../../frontend/src/components/knowledge/ReviewSheet.tsx#L257-L264)), not combine/keep-both choices; price conflicts surface as a "choose one" option row |
| Candidate price/description/provenance fields | Confirmed code | [flow.py:56-76](../../../../backend/app/onboarding/flow.py#L56-L76) - `PendingOffering` carries `name, description, price_cents, sources`; no identity, provenance, source-reference, complex-price-context, review-issue, or possible-match fields yet (proposed in W-6/W-8 contract extensions) |
| Merge rule for overlapping candidate | Confirmed code | [flow.py:78-99](../../../../backend/app/onboarding/flow.py#L78-L99) - document values win an overlap; [agent.py:228-246](../../../../backend/app/onboarding/agent.py#L228-L246) re-merges by `normalize_name` |
| Extraction is heading-limited / prose-splitting | Confirmed code | `offering_candidates.py` derives candidates deterministically from `"What we offer"`/`"Prices"`; no whole-source, section-spanning item extraction or reference-resolution price pass yet (scope of W-6) |
| SSE vs ordinary request split | Confirmed code | typed answers stream over SSE; chip, resume, and upload use ordinary requests (see [page.tsx:398-425](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L398-L425) for the non-streamed upload). A `fetch` entry in DevTools is not evidence of polling |
| "Answering…" duplicate pending indicator | Outstanding browser verification | The status line's "Answering…" and the thread's thinking dots are candidate duplicates (W-3); reproduce in the browser before runtime claim |

Outstanding browser verification is required before any of the above is
declared the established runtime cause. Bug fixes begin with an E2E
reproduction through the owner-facing surface; none of the W-3 through W-9
specs claim a runtime fix from these scans.

### Requirement ownership

One owning ticket per requirement, with dependency links instead of duplicated
acceptance criteria:

| Concern | Owning ticket |
|---|---|
| SSE versus polling; pending indicators; repeated input placeholder | [W-3](#w-3-keep-the-onboarding-thread-clear-and-responsive) |
| Slug prefill, review-return paths, and actionable go-live errors | [W-4](#w-4-complete-go-live-address-handling) |
| Customer answers combining confirmed offerings and knowledge | [W-5](#w-5-answer-from-confirmed-offerings-and-knowledge-together) |
| Offering names, descriptions, source-backed prices, duplicate proposals | [W-6](#w-6-extract-accurate-offerings-from-the-complete-source) |
| Five-item preview, pagination, editing, duplicate decisions | [W-8](#w-8-review-a-large-import-without-losing-information) |
| Readable, editable knowledge sections | [W-8](#w-8-review-a-large-import-without-losing-information) |
| Repeated names, conservative wording cleanup, conversational corrections, the customer-assistant contract and voice | [W-9](#w-9-definitive-onboarding-and-customer-assistant-contract) |

---

## Amendment 3: the agent contract (2026-09-06)

A founder request expanded the open W-9 ticket from a narrow correction fix
into the phase's closing ticket: a definitive contract for both the onboarding
assistant and the public customer assistant, replacing per-tenant prompt prose
with a code-owned contract, adding structured customer voice, and correcting
onboarding's name-capture behavior end to end. This amendment is the evidence
and definitions record for that ticket; W-9 itself references it rather than
restating it, the same relationship Amendment 2's tickets have to Amendment 2.

### Why this became one ticket instead of several

W-1 through W-8 are all shipped (corrected above); W-9 was the phase's only
open ticket, so there was no other open plan to merge it with. But the
expansion touches behavior five shipped tickets delivered - W-2's beat
resolution, W-5's dual-source grounding, W-6's provenance and frozen-price
extraction, W-7's junk-input challenge and reply discipline, W-8's review
boundaries - so the risk was never "which plan to merge," it was landing a
large prompt-and-schema change without silently regressing five already-closed
tickets. The amendment records, once, exactly what is preserved and what
changes, so the ticket itself can point at one table instead of five
scattered warnings.

| Shipped ticket | Preserved | Changed by W-9 |
|---|---|---|
| W-2 (`f2db993`) two-ask cap, server-owned question, deferral/pause | the cap, the second pass, pause-and-retry, the verbatim server question | extraction schema gains corrections, offering operations, and evidence fields; the `name` beat becomes `owner_display_name` |
| W-7 (`cd10f6e`) junk challenge, one-sentence replies, address-only go-live | both judges (server `valid` + model `answered_asked`), the veto, the no-extra-model-call latency decision, the go-live shape | the services-beat retry example becomes domain-neutral; `_COPILOT` and `Directive.as_prompt()` gain explicit Role/Goal/Constraints/Output/Stop structure |
| W-5 (`fix/w-5-combined-grounding`) dual-source grounding | `offerings_text` set on both agent-node return paths; the grounding judge's provenance text still includes offerings | tenant prose is replaced by the code-owned contract; the biggest regression risk in the ticket, called out explicitly in its Guardrails |
| W-6 (`feat/w-6-offering-extraction`) provenance, frozen money index | every provenance/source field on `PendingOffering`; `merge_offerings` stays the single precedence statement; no extraction schema ever gains a numeric field | explicit add/rename/remove/replace operations added on top, reusing the same update boundary |
| W-8 (`fc11883`) review sheet, paging, duplicate decisions | the review sheet, paging, and duplicate-decision UI, untouched | its one open Definition-of-done box (keyboard and mobile verification) is closed by this ticket's own editor testing, not reopened |
| W-3 SSE vs ordinary-request split | the transport split itself | asserted, not changed: one persisted assistant response on both paths |
| W-4 go-live address | the address-only confirm screen | the owner/business name conflation at `agent.py:269` (the go-live line falls back to the owner's name as a business name) is fixed as part of the `owner_display_name` rename |

### Agent contract and persona definitions

An agent contract is: identity and role, goal and success criteria, authority
and available tools, business knowledge, hard constraints, conversation
behavior, and escalation/stop rules. Persona is expression only - warmth,
formality, pacing, vocabulary, terminology, limited emoji - and cannot change
facts, policy, tools, identity, pricing, safety, or escalation behavior. This
follows the same behavior/persona split as
[OpenAI's prompting guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.5),
[Decagon's layered guardrail model](https://decagon.ai/blog/designing-layered-guardrails-for-reliable-ai-agents),
and [Sierra's voice-persona separation](https://sierra.ai/de/blog/introducing-voice-personas):
behavioral policy is code-owned and structurally enforced where the stakes are
highest (money, identity, escalation); expressive persona is tenant-configured
data that rides in afterward at lower authority.

Two names, kept distinct throughout this ticket because the code today
conflates them (`agent.py:269`):

- **`owner_display_name`** - private, tenant-level, used only in onboarding and
  owner-facing pages. Never customer-visible.
- **`business_name`** - the public business identity, used everywhere the
  customer assistant and the storefront speak.

### Copy-rule amendment

[`prd.md` section 13](../../prd.md#13-copy-rules) reads "Never say 'AI',
'agent', 'automated' or 'assistant' in user-facing copy." That rule predates
both mandated opening lines below, which name "assistant" as the surface's own
identity, and is amended for both surfaces as of this ticket:

- "assistant" may name the surface, on owner onboarding copy and customer chat
  copy alike.
- "AI", "agent", "automated", and "virtual" stay out of routine copy on both
  surfaces.
- A direct question about whether the surface is human or AI is answered
  honestly - the exemption above is about the noun used in routine copy, not a
  license to mislead when asked outright.

### Deterministic openings (flow-change, flagged per conventions.md 5.1)

| Surface | Before | After |
|---|---|---|
| Onboarding | "Hi! I'm your Agencx setup assistant. I'll help you get your business ..." ([controller.py:164](../../../../backend/app/features/onboarding/controller.py#L164)), then the `name` beat's own ask | "Hi, I'm the Agencx setup assistant. I'll help set up your business. Before we start, what should I call you?" |
| Customer chat | `greeting ?? "Hi! How can I help you with {name} today?"` ([CustomerChat.tsx:76](../../../../frontend/src/app/[slug]/CustomerChat.tsx#L76)) | "Hi, I'm [Business]'s assistant. How can I help today?" - fixed, composed first; any configured welcome message is optional following content, normalized so it never doubles the greeting |

### Regression inputs

Carried forward as the ticket's fixture set, taken from the founder's own
reports: `211e2esdsdfasdf`, `bkksbf88`, `21 ej2nek2ne2ken1e`, `sababa`,
`middle eastern cafe`. The concrete failure each must not reproduce: `sababa`
must never become `Sababasababa`; no assistant defers "my name" to later; no
subjective praise for "middle eastern cafe"; a cafe onboarding never sees
salon terminology (the services-beat retry example this ticket makes
domain-neutral).

---

## W-1: The escalation queue fits the screen and does not go stale

### Summary

Replace the fixed three-row cap on the home screen's waiting-customer panel
with a screen-fitted scroll cap, keep the Chats tab badge and the panel in
sync with the server without a manual refresh, and correct a token
discrepancy between the panel's own comment and the token it uses.

### Why

[WaitingPanel.tsx:34](../../../../frontend/src/app/(tenant-admin)/(console)/home/components/WaitingPanel.tsx#L34)
hard-codes `COLLAPSED_ROWS = 3` regardless of viewport, so a desktop window
with room for eight rows still shows three behind a "Show all" tap.
Separately, [QueryProvider.tsx:22-25](../../../../frontend/src/components/QueryProvider.tsx#L22-L25)
sets `staleTime: 30_000` with no `refetchInterval`, so the panel and the
Chats tab badge (both driven by `/api/conversations`, per
[layout.tsx:85-91](../../../../frontend/src/app/(tenant-admin)/(console)/layout.tsx#L85-L91))
keep showing a resolved escalation as waiting until the owner navigates away
and back. The panel's own comment at
[WaitingPanel.tsx:20](../../../../frontend/src/app/(tenant-admin)/(console)/home/components/WaitingPanel.tsx#L20)
claims the count pill uses "the prototype's actual amber, `--amber-400`", but
[theme.css:270](../../../../frontend/src/styles/theme.css#L270) points
`--color-highlight` at `--amber-300`.

### User stories

#### US-1 An owner on a small screen sees a manageable list

As a tenant owner on a phone, I see roughly the number of waiting customers
that fit below the greeting without the home screen feeling congested, and I
can scroll or expand to see the rest.

- The collapsed list height is unchanged from today's three-row feel on a
  phone-width viewport.
- Expanding still reveals every waiting customer, oldest first, matching
  today's ordering.

#### US-2 An owner on a desktop sees more at once

As a tenant owner on a wide screen, I see more waiting customers before I
need to scroll, because the screen has the room.

- At the `lg` breakpoint (1024px), the collapsed panel shows roughly five
  rows before scrolling, not three.
- No layout shift or content jump when the window crosses the breakpoint.

#### US-3 The count reflects reality without a manual refresh

As a tenant owner, once I resolve a customer's escalation, the panel and the
Chats tab badge stop showing them within a few seconds, without me needing to
reload the page.

- The `/api/conversations` query underlying both surfaces refetches on an
  interval while the console is open, matching the cadence the conversation
  thread page already polls at
  ([chats/[id]/page.tsx:28](../../../../frontend/src/app/(tenant-admin)/(console)/chats/[id]/page.tsx#L28),
  4 seconds).

### Design reference

The prototype (`agencx-prototype-v6.html`) has no per-customer escalation
card and no count pill; its only notification affordance is a bare dot,
`#ndot` (line 32), with no number. `8496f25` already established the row
idiom by porting the chats screen's `.chat-row` (line 138: name, time,
truncated preview). This ticket does not introduce new visual vocabulary; it
changes how much of that existing list is visible before scrolling, and how
current the data behind it is.

### Technical spec

- In `WaitingPanel.tsx`, remove the `rows.slice(0, COLLAPSED_ROWS)` split.
  Render every row inside one `overflow-y-auto` container whose collapsed
  `max-height` is sized for roughly three rows by default and roughly five
  at `lg:` (the console's one mobile/desktop switch, per
  [layout.tsx:109](../../../../frontend/src/app/(tenant-admin)/(console)/layout.tsx#L109)
  and [TabBar.tsx:57](../../../../frontend/src/components/ui/TabBar.tsx#L57)).
  The existing expanded caps (`max-h-[288px] lg:max-h-[432px]`, one row taller
  each) are the reference for computing a per-row height; the collapsed cap
  is the same formula at the lower row count.
  Do not add `matchMedia`, a resize listener, or client-only state to measure
  the viewport - the repo has no such hook today, and a CSS breakpoint is the
  established pattern.
- Keep the toggle. Its visibility condition becomes "does the list overflow
  its collapsed cap", which for a short list is equivalent to today's
  `rows.length > COLLAPSED_ROWS` check; for a list that fits within the
  collapsed cap but was previously hidden behind the row-count cap (four rows
  on desktop, say), the toggle no longer appears, because there is nothing to
  reveal.
- Add `refetchInterval: 4000` to the `useApiQuery<ConversationSummary[]>("/api/conversations")` call.
  Both call sites share the query key, so one option change covers
  [home/page.tsx:49](../../../../frontend/src/app/(tenant-admin)/(console)/home/page.tsx#L49)
  and [layout.tsx:85](../../../../frontend/src/app/(tenant-admin)/(console)/layout.tsx#L85).
  Confirm `useApiQuery` (wherever it wraps `useQuery`) passes an
  options-object override through; if it does not yet, add the pass-through
  rather than hard-coding the interval inside the hook.
- Resolve the token discrepancy: either repoint `--color-highlight` at
  `--amber-400` in [theme.css:270](../../../../frontend/src/styles/theme.css#L270),
  or correct the WaitingPanel comment to name `--amber-300`. Pick whichever
  matches the prototype's literal `--c-amber:#F5A623` (prototype line 13);
  `--amber-400` is `#F5A623` and `--amber-300` is not, so the fix is to
  repoint the token, not the comment.

### Tests

- Frontend: a viewport-width test (or a `lg:` class assertion) confirming the
  collapsed container's class differs between the default and `lg:` cases.
- Frontend: existing `WaitingPanel` tests updated for the new collapse
  mechanism (no more slicing to exactly three items).
- Frontend: `home-brief.spec.ts` (E2E) still passes the direct-open assertion
  unchanged.
- Manual: resolve an escalation in one tab, confirm the badge in a second
  open tab clears within one polling interval.

### Definition of done

- [x] Collapsed row count is CSS-breakpoint-driven, not a fixed JS constant.
- [x] `/api/conversations` refetches on an interval; badge and panel self-heal
      without a manual reload.
- [x] `--color-highlight` and its documenting comment agree on one amber
      value, matching the prototype's `--c-amber`.
- [x] `make check` green.

Shipped `48c7acb`. Unchanged by the 2026-09-05 amendment; no refined behaviour
targets the escalation queue.

---

## W-2: The interview never re-asks a question it already has an answer to

### Summary

Stop the onboarding assistant from re-asking a filled slot. Make the
question the owner sees a server-owned, verbatim string instead of an
LLM paraphrase; keep the extractor free to capture any field from any
answer (so an off-beat reply like an offer list given while hours are being
asked still gets filed correctly and acknowledged); add a repeat guard for a
slot that genuinely will not fill; and reword the hours question so it
answers both hours and days in one turn.

### Why

The founder's transcript shows the business-name question asked three times
after `business_name` had already been captured, and the assistant
apologizing without correcting course:

> Hi! I'm your Agencx setup assistant... What's your name?
> ... Nice to meet you, Nikan! What does your business go by?
> sababa
> ... What kind of business is it?
> ...
> Got it, 7 to 8. What would you like customers to know you offer?
> pita coffee wraps and more
> Great, "pita coffee wraps and more" sounds delicious! ... **What's the name
> of your business?**
> i already told u
> Got it - pita, coffee, wraps, and more. Thanks for sharing! ... **What's
> the name of your business?**

Root cause: [beats.py:182-187](../../../../backend/app/onboarding/beats.py#L182-L187)
(`next_beat`) picks the next unanswered slot deterministically and
correctly, but [agent.py:420-432](../../../../backend/app/onboarding/agent.py#L420-L432)
hands that choice to a second LLM call as advisory prose (a directive string
built by `as_prompt()` at [agent.py:50-57](../../../../backend/app/onboarding/agent.py#L50-L57),
`"Ask for: {ask_for}"`) which composes the visible question freely, with only
a three-message history window
([agent.py:428](../../../../backend/app/onboarding/agent.py#L428)) and a
system prompt that lists every field by name
([agent.py:60-67](../../../../backend/app/onboarding/agent.py#L60-L67)).
Nothing checks that the emitted text actually asks for `ask_for`. This design
has been in place since the first onboarding commit (`e919435`) and has never
been changed; the one place that already emits the beat's question verbatim
is the chip-selection path
([agent.py:241-244](../../../../backend/app/onboarding/agent.py#L241-L244)),
which free text does not go through.

Two supporting defects feed the same symptom:

- **Conditional persistence can rewind the pointer.**
  [agent.py:402](../../../../backend/app/onboarding/agent.py#L402) only
  persists a turn when `acknowledged` is non-empty or the turn was not flagged
  off-topic. `offering_names` is not counted toward `acknowledged`
  ([agent.py:397-398](../../../../backend/app/onboarding/agent.py#L397-L398)),
  so a turn that yields only offering names and is flagged off-topic is
  computed, shown to the owner, and never saved. Because `next_beat` rescans
  `BEAT_ORDER` from index 0 every call with no forward cursor, the next turn
  reloads the older database row and can land back on an earlier beat.
- **The extractor cannot route an offer answer into `services`.** The
  extraction prompt ([agent.py:77-84](../../../../backend/app/onboarding/agent.py#L77-L84))
  tells the model to list named offerings under `offering_names`, separate
  from `profile.services`, and never instructs it to also fill `services`
  when the reply is answering the offer question. An answer can leave
  `services` empty while still being a complete answer to that beat, which
  research also confirmed can produce a single merged offering
  (`"pita coffee wraps and more"`) instead of three, because splitting is
  delegated entirely to the model with no example covering an unpunctuated,
  conjunction-joined list.

### User stories

#### US-1 A filled slot is never asked for again

As a business owner, once I have told the assistant my business name, it
never asks for it again for the rest of the interview, no matter what I say
in between.

- Given `business_name` is set in the draft, the beat the assistant asks for
  next is never `business_name`, verified against the emitted reply text, not
  only against internal state.
- The visible question text matches the target beat's `ask` string exactly
  (server-emitted), for every beat.

#### US-2 An off-beat answer is captured, not discarded, and the flow continues on-topic

As a business owner, if I answer a different question than the one asked
(for example, naming what I offer while being asked about hours), the
assistant notes what I gave it, applies it to the right field, and still asks
me the question that is actually pending.

- Given the current beat is `hours` and the owner's reply names offerings,
  `services` (or `offering_names`) is filled from that reply.
- The next visible question is still the `hours` beat's `ask` (unless the
  reply also happens to answer `hours`), phrased as an acknowledgment of the
  off-beat information followed by the pending question, for example: "Great,
  you offer pita, coffee, and wraps - I have noted those. What are your
  opening hours, and which days are you open?"

#### US-3 An unpunctuated list of offerings becomes separate candidates

As a business owner, if I say "we offer pita coffee and wraps" with no
commas, the interview treats that as three offering candidates, not one.

- The extraction prompt gains an explicit example of a conjunction-joined,
  comma-less list yielding multiple `offering_names` entries.
- The review sheet (existing safety net from `497bbf3`) still lets the owner
  split, rename, or merge candidates before publish.

#### US-4 A slot that will not fill degrades gracefully instead of looping

As a business owner, if I cannot or do not want to answer a question after
two tries, the assistant stops repeating the identical sentence and offers a
way forward.

- A per-beat consecutive-ask counter is tracked in the onboarding record.
- The second consecutive ask of the same beat rephrases the acknowledgment
  and adds a concrete example.
- The third consecutive ask offers to move on and revisit the field later
  from Settings, and treats a "skip"-shaped reply as satisfying the beat with
  an explicit empty/placeholder value where the beat's semantics allow it.

#### US-5 The opening-hours question also asks about days

As a business owner, answering the hours question tells the assistant both
when I am open in a day and which days of the week I am active, in one turn.

- [beats.py:127](../../../../backend/app/onboarding/beats.py#L127)'s `ask`
  changes from "When are you open?" to a question that names both hours and
  days, for example: "What are your opening hours, and which days of the
  week are you open?"
- The extraction schema and prompt are updated so a reply covering only one
  half (hours or days) still fills what it answers and the repeat guard (US-4)
  handles the other half if it remains missing.

### Design reference

No visual change. The onboarding thread's structure, spacing, and composer
widgets are unchanged (`agencx-prototype-v6.html`, ONBOARDING section); this
ticket is entirely about which text the assistant emits and when.

### Technical spec

- **Beat-aware, still-open extraction.** Add the current beat's key and `ask`
  text to `_extraction_input` ([agent.py:262-270](../../../../backend/app/onboarding/agent.py#L262-L270))
  as context, not a filter: "The question asked this turn was: {ask}." Instruct
  the model to fill that field when the reply answers it, and separately to
  fill whatever other field(s) the reply actually answers when it answers
  something else instead. The extractor keeps its full nine-field schema; the
  beat hint only helps it disambiguate an ambiguous reply, it never narrows
  what can be captured.
- **Server-owned question text.** Change the reply-composition prompt at
  [agent.py:420-432](../../../../backend/app/onboarding/agent.py#L420-L432)
  so the model is asked to write only a short acknowledgment sentence of what
  was captured this turn (or of any off-beat information captured this turn), and
  explicitly told not to ask a question. The server appends `nxt.ask`
  verbatim after the model's acknowledgment:
  `reply = f"{ack} {nxt.ask}".strip()`. This is the same shape as the
  existing chip path ([agent.py:241-244](../../../../backend/app/onboarding/agent.py#L241-L244)),
  applied to free text. Update `_COPILOT`
  ([agent.py:60-67](../../../../backend/app/onboarding/agent.py#L60-L67)) so
  it no longer implies the model chooses or phrases the question.
- **Fill `services` from `offering_names` deterministically.** In the merge
  step ([agent.py:393](../../../../backend/app/onboarding/agent.py#L393) /
  `_merge_owner_offerings`), when `update.offering_names` is non-empty and
  `draft.get("services")` is empty, set `draft["services"]` to the
  comma-joined names. No extra model call; this is a plain server-side join.
- **Extraction prompt examples for unpunctuated lists.** Add one example pair
  to the prompt at [agent.py:77-84](../../../../backend/app/onboarding/agent.py#L77-L84)
  showing an input like "we offer pita coffee and wraps" mapped to
  `offering_names: ["pita", "coffee", "wraps"]`.
- **Repeat guard.** Add an `ask_count: dict[str, int]` (or a single
  `{beat, count}` pair, since only the current beat needs tracking) to the
  onboarding record's jsonb shape, bumped in `prepare_turn` when `next_beat`
  returns the same key as the previous turn's, reset to zero when it changes.
  At count 2, the reply-composition directive includes an instruction to
  rephrase and give a concrete example. At count 3, the directive offers to
  move on; a reply recognized as declining (already-handled "skip" vocabulary
  from the knowledge-offer path, [agent.py:218-223](../../../../backend/app/onboarding/agent.py#L218-L223),
  is the precedent) sets the field to an explicit placeholder that satisfies
  `beat.complete` (for text-shaped beats, the literal string the owner used,
  or a sentinel the Business tab already knows to render as "not set").
  `OnboardingRecord.from_jsonb`'s version gate
  ([agent.py:105-132](../../../../backend/app/onboarding/agent.py#L105-L132))
  needs its `version` literal bumped so old records reset cleanly rather than
  crashing on the new field's absence - this is the existing migration
  pattern, not a new one.
- **Persist every turn.** Remove the conditional at
  [agent.py:402](../../../../backend/app/onboarding/agent.py#L402); always
  call `service.save_record` after a turn (streaming and non-streaming paths
  both, per [controller.py:331-333](../../../../backend/app/features/onboarding/controller.py#L331-L333)
  and [controller.py:227-233](../../../../backend/app/features/onboarding/controller.py#L227-L233)).
  This guarantees the emitted `state` event and the stored record never
  disagree, closing the rewind path described above.
- **Hours beat rewording.** Update `beats.py:127`'s `ask` per US-5, and widen
  the beat's extraction guidance to expect a compound answer.

### Convention to add

The founder asked, in the walkthrough, for a standing rule that a working
conversational flow is not changed without a flagged confirmation. Add a new
subsection to [conventions.md](../../design/conventions.md), placed after
section 5 (bug-fix protocol), which it extends:

> ### 5.1 Flow-change confirmation
>
> A change to a working user-facing flow - the onboarding interview script or
> beat order, the chat routing between fast and hybrid paths, the publish/
> confirm sequence, or any other multi-turn behavior a user has already
> exercised successfully - is flagged to the founder before it is made, with
> the current behavior and the proposed behavior both stated. This applies
> even when the change is a refactor that is not intended to alter behavior:
> intent and actual behavior have diverged before in this codebase (the
> onboarding beat-versus-paraphrase seam this phase's W-2 closes is the
> concrete example), and the flag is what catches that divergence before a
> user does.

### Tests

Backend, in `backend/tests/test_onboarding_agent.py` or the equivalent
`agent.py` test module:

- A filled slot is never re-asked: seed a record with `business_name` set,
  run a turn whose reply is off-topic or answers a later beat, assert the
  emitted reply's `ask` portion equals the next unfilled beat's exact `ask`
  string and does not contain the business-name question text.
- An off-beat answer captures its own field and the pending beat is still
  asked: seed the current beat as `hours`, send a reply naming offerings,
  assert `services` or `offering_names` is populated and the emitted question
  is still the `hours` beat's `ask`.
- An unpunctuated, conjunction-joined answer yields more than one
  `PendingOffering` (via the new prompt example - this test may need a fixed
  provider response in the harness's `RecordingProvider` style, matching the
  pattern in `test_context_package.py`).
- A turn persists even when the extractor returns an empty `DraftUpdate`
  (regression test for the conditional-persistence fix).
- The repeat guard: three consecutive turns that fail to fill the same beat
  produce three distinct reply shapes (initial ask, rephrase-with-example,
  offer-to-skip), and a "skip"-shaped fourth reply advances past the beat.

### Definition of done

- [x] The onboarding reply's question text is server-appended, not
      model-composed, for every beat (chip and free-text paths agree).
- [x] A filled slot cannot be re-asked, proven by a regression test.
- [x] An off-beat answer is captured without derailing the pending question.
- [x] An unpunctuated offer list yields multiple candidates.
- [x] A two-times-unanswered beat resolves or defers instead of repeating.
- [x] The hours beat asks for both hours and days.
- [x] Every turn persists regardless of extraction outcome.
- [x] [conventions.md](../../design/conventions.md) carries the new
      flow-change confirmation subsection.
- [x] `make check` green.

Amended during the build, with the founder's confirmation (per the 5.1
convention this ticket adds):

- **Two asks per beat, not three.** Three adjacent asks was the symptom, so a
  third was never the fix. What made the founder's transcript read as a loop
  was the *adjacency*, not the count.
- **Required and skippable beats are now defined**, closing US-4's undefined
  "where the beat's semantics allow it". Skippable = nothing downstream reads
  it, or the owner can still edit it after go-live: `name`, `headcount`,
  `services`, `abn`, `gst`. Required: `business_name`, `business_type`,
  `hours`, `contact`.
- **A skippable beat resolves; a required one defers.** `headcount` takes
  "just me", `abn` takes `NO_ABN`; `name` and `services` carry a "Skip for
  now" chip. A required beat is held back to a second pass so the interview
  keeps moving, and returns once every other beat is done.
- **Terminal rule:** on the final pass the owner's own words are taken
  verbatim, so the interview always ends. The go-live screen reads
  `business_name` and `business_type` back as editable fields, since neither
  has an editor after publish.
- **A skip writes no sentinel into the profile** - `profile_tagline` renders
  `services` and `hours` into the public storefront subtitle, so the skipped
  keys are tracked beside the draft instead.
- **No `version` bump** on the record: the new fields read through a default,
  and a bump would have restarted every interview in flight at deploy.

Shipped `f2db993`. Forward reference: W-9 refines the interview's correction
behaviour - accepting explicit corrections to already-captured fields during
any beat and never counting a correction as a failed attempt - building on the
two-ask and deferral machinery this ticket fixed rather than replacing it.

---

## W-3: Keep the onboarding thread clear and responsive

### Summary

Extend the shipped composer and pending-state work: leave text input
placeholders empty, stabilize the composer's baseline height, show exactly one
pending indicator for the active operation, and give a processing upload an
animated state with an explicit outcome while the owner keeps reading and
scrolling. Document the transport split (SSE for typed answers, ordinary
requests for chips, resume, and uploads) and prove it with a browser network
trace.

### Why

A second walkthrough round restated and sharpened W-3's original concerns, and
a repository scan confirmed the current shape:

- The status line below the composer renders `"Answering…"`
  ([page.tsx:595-607](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L595-L607))
  while `TypingLine` already renders thinking dots for the same turn
  ([Thread.tsx:129-135](../../../../frontend/src/components/ui/Thread.tsx#L129-L135)).
  Two indicators, one operation.
- The composer swaps widget per beat
  ([BeatComposer.tsx:129-179](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/components/BeatComposer.tsx#L129-L179)),
  and the plain textarea auto-grows with content
  ([CommandPill.tsx:28](../../../../frontend/src/components/ui/CommandPill.tsx#L28),
  [CommandPill.tsx:56-63](../../../../frontend/src/components/ui/CommandPill.tsx#L56-L63)),
  so the composer reads as randomly resizing between turns.
- An attached file gets one static stamp, `"${file.name} · adding…"`
  ([page.tsx:398-417](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L398-L417)),
  over a single non-streamed `POST /api/knowledge/drafts/upload`, with no
  animated processing state and no explicit failure recovery prose while the
  document is read and structured.
- Text input placeholders repeat what the assistant's question already says;
  the field label and the in-thread question are the accessible carriers.

### User stories

#### US-1 Empty input placeholders by default

As a business owner, the text input I am about to type into shows no text
until I type; I still get the field's accessible label and the assistant's
question in the conversation.

- Text inputs and textareas leave their placeholder empty by default.
- The field keeps an accessible label, and the assistant's question remains
  the visible in-thread context for what to enter.
- Chip, phone, numeric, and multiline input behavior is unchanged.

#### US-2 One pending indicator per operation

As a business owner, while a turn is in flight I see one clear pending signal,
not the same state in two places.

- The thinking-dots row in the thread is the only pending-turn indicator.
- The status line below the composer holds nothing while a turn is in flight
  and reads as the error slot only (see W-4) when there is an error.

#### US-3 The composer holds a steady size between questions

As a business owner, the input area does not visibly grow or shrink when the
assistant asks its next question; it grows only as I type a longer answer and
shrinks back when I clear it.

- Switching from one beat's widget to another's does not change the
  composer's baseline height.
- Typing still grows the textarea up to its existing cap; clearing still
  shrinks it back.

#### US-4 A processing upload keeps the page usable and lands on an outcome

As a business owner, after I attach a file I keep reading and scrolling while
it processes, see an animated signal that work is happening, and get an
explicit success or failure with a usable recovery path.

- The upload stamp shows an animated processing state using the existing
  visual vocabulary while extraction runs.
- Reading and scrolling are available during extraction; the thread is not
  blocked.
- Submission stays serialized so the owner cannot submit conflicting
  operations at once.
- The operation ends in an explicit success or failure state, and a failure
  offers a usable recovery path.
- No fabricated percentage progress; no queues, workers, background-job
  polling, or resumable processing are added.

### Design reference

`ThinkingDots` ([ThinkingDots.tsx:21-33](../../../../frontend/src/components/ui/ThinkingDots.tsx#L21-L33))
and `ProcessingLine` ([Thread.tsx:144-150](../../../../frontend/src/components/ui/Thread.tsx#L144-L150))
are the existing motion primitives this ticket reuses; no new component or
dependency. The composer's visual shell is unchanged - only its height
stability and placeholder behavior.

### Technical spec

- Make text-input placeholders empty by default while keeping accessible
  labels and the in-thread question as the context carriers. Preserve chip,
  phone, numeric, and multiline behaviors.
- Delete the `"Answering…"` branch from the status line at
  [page.tsx:595-607](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L595-L607),
  leaving `{error ?? ""}`. Keep the element mounted as the `role="status"`
  live region and the error slot (danger styling per W-4).
- Give the `BeatComposer` root or widget wrapper a fixed minimum height
  matching the tallest common single-line state so a widget swap does not
  change the outer height. `CommandPill`'s own auto-grow is unchanged; this
  stabilizes the shell around it.
- Replace the static `"${file.name} · adding…"` stamp with the existing
  animated line component while that stamp's operation is in flight, falling
  back to explicit "added" or failure text once resolved. A failure state
  carries a usable recovery path (retry the upload). Do not add percentage
  progress, queues, workers, background-job polling, or resumable processing.
  Keep submission serialization: the busy guard in the upload path
  ([page.tsx:398-417](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L398-L417))
  blocks conflicting submissions until the current one settles.

### Transport verification

Document the current split and prove it with a browser network trace. Typed
answers stream over SSE; chip answers, resume actions, and uploads use
ordinary requests (see the non-streamed upload at
[page.tsx:401-406](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L401-L406)).
A `fetch` entry in DevTools is not evidence of polling.

Acceptance requires a browser network trace showing:

- The typed-answer request consumes incremental SSE events.
- Final reply reconciliation produces exactly one assistant message.
- State refreshes are bounded to their triggering actions.
- Idle onboarding does not request conversation state.
- Errors end the pending state and leave the conversation usable.

### Tests

- Frontend: a snapshot or class assertion that the status line renders empty
  (not "Answering…") while `busy` is true.
- Frontend: a test that the composer wrapper's height class is stable across a
  beat change.
- Frontend: the upload stamp renders the animated state while processing and
  the explicit success/failure state once resolved.
- E2E / manual: the browser network trace acceptance list above, applied
  through the owner-facing onboarding surface.

### Definition of done

- [x] Text-input placeholders are empty by default; labels and the in-thread
      question remain.
- [x] No duplicate "Answering…" text; thinking dots are the sole pending
      indicator.
- [x] Composer height is stable across beat changes; still grows with typed
      content.
- [x] Upload processing animates, keeps reading/scroll available, serializes
      submission, and ends in an explicit success or failure with recovery.
- [x] No fabricated percentage progress or background-job machinery.
- [x] The transport split is documented and proven by a browser network trace
      per the acceptance list.
- [x] `make check` green.

Shipped `cadbbd7`. The browser proof landed as `frontend/e2e/onboarding-transport.spec.ts`
rather than a hand-driven DevTools trace, on the founder's call. Three adjacent
defects were fixed in the same pass: `ProcessingLine`'s nested `role="status"`,
`ThinkingDots` rendering as a block-level box, and `sendText` leaving a failed
turn's bubble streaming forever - the last of which contradicted this ticket's
own error-recovery criterion.

---

## W-4: Complete go-live address handling

### Summary

Narrow W-4 to the remaining go-live address paths and their error handling,
on top of W-7's shipped address-only confirmation behavior. Every path that
reaches confirmation - initial load, ordinary answers, optional-knowledge
skip, review save, review discard, and reload - must provide the suggested
address. Failures (invalid, reserved, or taken slugs; network errors) produce
actionable field-level errors, and a retry succeeds without restarting
onboarding. Backend validation remains authoritative.

### Why

W-7 already shipped the address-only confirmation step: go-live confirms the
address only, prefilled to the real slug, with a "Going live as X" read-back.
What remains is that the prefill and its failures are not handled on every
path that can flip the confirm step open:

- `applyStateFields` ([page.tsx:135-143](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L135-L143))
  is the only place that prefills `publicSlug` from `suggested_slug`, and it
  runs only from the initial load and the turn handlers. `saveKnowledge`
  ([page.tsx:437-448](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L437-L448))
  and `discardKnowledge`
  ([page.tsx:456-465](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L456-L465))
  set confirm state directly, bypassing it, so the review-save and
  review-discard paths reach confirmation without the slug synchronization the
  initial-load path gets.
- A confirm failure lands in the shared status line
  ([page.tsx:472-503](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L472-L503)),
  grey and low-visibility, rather than the slug `Input`'s own danger state
  ([Input.tsx:34-46](../../../../frontend/src/components/ui/Input.tsx#L34-L46)).
- Client-side shape/length validation is absent, so an owner sees only the
  generic 422
  ([errors.py:77](../../../../backend/app/shared/errors.py#L77)) the frontend
  never reads the `errors[]` detail from
  ([api.ts:44-62](../../../../frontend/src/lib/api.ts#L44-L62)).

The scan confirmed the review save/discard paths update confirmation state
without the same slug synchronization as initial loading. This is recorded as
implementation evidence; the runtime cause is declared established only after
a browser reproduction on the go-live screen.

### User stories

#### US-1 Every path that reaches confirmation provides the address

As a business owner, whenever I get to the "confirm and go live" step - after
initial load, after ordinary answers, after skipping the optional knowledge
step, after saving or discarding a review, or after reload - the address field
shows a suggested slug based on my business name.

- Each of those paths runs the same prefill logic and provides the suggested
  address.
- Typing over the prefilled value is unaffected.

#### US-2 Corrections refresh the suggestion only until the owner edits the address

As a business owner, if I correct my business name then the address suggestion
follows it, but once I have typed my own address, unrelated state updates do
not overwrite it.

- A business-name correction refreshes the suggestion only while the owner has
  not edited the address.
- Owner-entered addresses survive unrelated state updates.

#### US-3 Slug problems are actionable at the field

As a business owner, if my chosen address is invalid, reserved, or taken, the
field itself shows why, and a retry can succeed without restarting onboarding.

- Invalid, reserved, or taken addresses produce actionable field errors.
- The failure preserves the draft and the entered address; retrying can
  succeed without restarting onboarding.
- Backend validation remains authoritative; client-side checks only add
  earlier, clearer feedback.
- A network failure leaves the interview usable and the entered address
  intact.

### Design reference

No new screen. The slug `Input` and `Button` are the existing go-live
components ([page.tsx:561-581](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L561-L581));
this ticket wires up states they already support (`Input`'s `error` prop, the
app-wide `Toaster` ([Toaster.tsx](../../../../frontend/src/components/Toaster.tsx)))
rather than building new ones.

### Technical spec

- Route the slug prefill through one function on every path that can open the
  confirm step, including `saveKnowledge` and `discardKnowledge`, so initial
  load, ordinary answers, optional-knowledge skip, review save, review
  discard, and reload all use the same suggestion logic.
- Refresh the suggested slug when the business name changes, but only while
  the owner has not edited the address. Preserve an owner-entered address
  across unrelated state updates.
- Add slug field error state to `Input`'s `error` prop and fire a
  `toast.error(...)` in the confirm failure path
  ([page.tsx:472-503](../../../../frontend/src/app/(tenant-admin)/(console)/onboarding/page.tsx#L472-L503)),
  covering invalid, reserved, and taken slugs as actionable field errors.
- Add client-side shape/length validation before `POST /api/onboarding/confirm`
  mirroring [slug.py:16](../../../../backend/app/features/tenants/slug.py#L16)
  and [slug.py:62](../../../../backend/app/features/tenants/slug.py#L62). Do
  not duplicate the reserved list client-side; the server's specific message
  for it stays authoritative. Keep the existing 409 taken-error text
  ([controller.py:495](../../../../backend/app/features/onboarding/controller.py#L495))
  as an actionable field error too.
- On a network failure, keep the draft and the entered address in place so a
  retry can succeed without restarting onboarding. Backend validation remains
  authoritative.

### Tests

- Frontend: after each confirm-opening path (initial load, ordinary answer,
  optional-knowledge skip, review save, review discard, reload), assert
  `publicSlug` is pre-filled.
- Frontend: correcting the business name refreshes the suggestion only while
  the owner has not edited the address; an owner-entered address survives an
  unrelated state update.
- Frontend: a 409 confirm failure sets the `Input` error prop and fires a
  toast; a client-side shape violation blocks submission with the same
  treatment and no network call.
- Frontend: a network failure preserves the draft and entered address, and a
  retry succeeds without restarting onboarding.
- E2E: reproduce the review-save/discard-then-confirm path on the go-live
  screen (the recorded implementation evidence above) before declaring the
  runtime cause established, then assert the address field is non-empty and
  correct through both paths.

### Definition of done

- [x] Every confirm-opening path provides the suggested address.
- [x] A business-name correction refreshes the suggestion only until the
      owner edits the address; owner-entered addresses survive unrelated
      updates.
- [x] Invalid, reserved, and taken slugs are actionable field errors.
- [x] Network failures preserve the draft and entered address; a retry
      succeeds without restarting onboarding.
- [x] Backend validation remains authoritative.
- [x] The review save/discard path is reproduced in the browser and its
      runtime cause recorded.
- [x] `make check` green.

Shipped `d56588c`. The address is now derived (`slugDraft ?? suggestedSlug`) rather than
pushed down six paths: `applyStateFields` sets the suggestion unconditionally
on every state read, so US-1 holds by construction and `saveKnowledge` /
`discardKnowledge` have nothing left to bypass. That also removed the need for
a client-side mirror of `suggested_slug()` - only the shape check
(`frontend/src/lib/slug.ts`) is mirrored.

Runtime cause recorded: the prefill was a one-shot latch
(`setPublicSlug(current => current || ...)`) whose client fallback was the
literal `"business"` - a name in `RESERVED_SLUGS`, so that fallback could only
ever produce a 422. The generic "One or more fields are invalid." the owner saw
was `ApiError.errors[0].detail` going unread; nothing in the repo read that
field before this ticket.

---

## W-5: Answer from confirmed offerings and knowledge together

### Summary

Retain the customer-grounding ticket that fixes the gap introduced by
`0ebd1fc`: one customer chat answer draws on the confirmed offerings catalog
and the uploaded knowledge together. A question like "what do you offer?"
must be answerable from the catalog and the knowledge base in the same reply,
not the catalog alone with the knowledge base surfacing only after a second,
more insistent question. Refined by the 2026-09-05 amendment to require the
relevant confirmed catalog facts and uploaded knowledge together on both the
fast and the hybrid paths, reusing the existing context package rather than
adding another catalog query or retrieval subsystem.

### Why

`0ebd1fc` added the confirmed-offerings block to the customer system prompt
correctly, but two mechanisms still stop a single reply from combining it
with uploaded knowledge:

- **The prompt instructs the model to lead with the catalog and stop there.**
  [agent_node.py:325-333](../../../../backend/app/agents/agent_node.py#L325-L333)
  says the catalog is "authoritative for what the business currently offers"
  and to "enumerate the complete catalog before offering to share more
  detail." [agent_node.py:78-80](../../../../backend/app/agents/agent_node.py#L78-L80)
  reinforces this by telling the model not to reach for a tool for exactly
  this question. On the fast path, the document's chunks are in the very same
  prompt as the offerings block, yet the model does what it is told and
  answers from the catalog first, matching the founder's observed two-step
  behavior exactly.
- **On the hybrid path, the two sources can never reach one generation.**
  `search_knowledge` returns only a chunk count to the model
  ([agent_node.py:507](../../../../backend/app/agents/agent_node.py#L507));
  the retrieved chunks are drafted separately by
  `_build_knowledge_prompt` ([draft_node.py:67-89](../../../../backend/app/agents/draft_node.py#L67-L89)),
  which reads `retrieved_chunks` only, never
  `ContextPackage.offerings`, and is instructed to answer "using ONLY the
  numbered context below." `get_business_context`
  ([retrieval.py:151-159](../../../../backend/app/services/retrieval.py#L151-L159))
  also excludes catalog-kind chunks from that retrieval, per the fix M-1
  made for a different reason (keeping catalog text out of the fast-path
  whole-corpus block).
- `_FAST_PATH_GUIDANCE` ([agent_node.py:102-103](../../../../backend/app/agents/agent_node.py#L102-L103))
  additionally overclaims that the corpus block "is everything the business
  has published" - it is not, since `whole_corpus` strips catalog chunks by
  design; the offerings block is the (currently insufficient) compensation
  for that gap.

### User stories

#### US-1 One concise answer combines an offering with a relevant policy or detail

As a customer, when I ask what a business offers, I get one concise answer
that combines a relevant offering with a relevant policy or business detail,
without needing to ask a follow-up for "all" of it.

- On the fast path (small corpus, whole document in one prompt), the reply
  synthesizes both blocks instead of listing the catalog and stopping.
- On the hybrid path (corpus over the fast-path token budget), a
  `search_knowledge` call's resulting `draft_node` answer also includes the
  relevant confirmed catalog, not knowledge-chunk text alone.

#### US-2 Relevant offerings, not an unnecessary catalog dump

As a customer, I get the offerings relevant to my question, not a complete
catalog enumerations on every answer.

- The answer selects the relevant confirmed catalog facts; it does not dump
  the whole catalog when the question does not call for it.

#### US-3 The catalog keeps its authority over price and availability

As a customer, if the catalog and an uploaded document ever disagree on a
price or whether something is still offered, the catalog wins, because it is
the row the owner actively maintains.

- The rewritten prompt instruction keeps "authoritative for prices and
  availability" for the catalog; it only removes the "before offering to
  share more detail" sequencing that causes the two-step answer.
- Confirmed structured prices retain their existing authority.
- The deterministic-pricing invariant
  ([conventions.md section 8](../../design/conventions.md)) is unaffected:
  no new path lets a model author a price. `owner_material()` remains the
  provenance source for the money gate
  ([agent_node.py:730](../../../../backend/app/agents/agent_node.py#L730)),
  and the pricing and inspection rules continue to be enforced.

#### US-4 Unconfirmed imports stay out of customer answers

As a customer, I am never answered from an import the owner has not reviewed:
unconfirmed imports remain unavailable to customer answers.

- Draft/reviewed-but-unsaved document content does not reach the customer
  answer path.
- Ambiguous source pricing is not silently resolved into an invented exact
  amount.

### Design reference

No UI change; this is a backend prompt-assembly and grounding fix.

### Technical spec

- Rewrite the offerings-block instruction at
  [agent_node.py:325-333](../../../../backend/app/agents/agent_node.py#L325-L333):
  keep "authoritative for names, availability, and prices"; keep "use
  reviewed knowledge for additional descriptions and supporting details";
  remove "enumerate the complete catalog before offering to share more
  detail" and replace it with an instruction to answer from both sources
  together in one reply when both are relevant, naming the relevant
  offerings rather than enumerating the complete catalog.
- Soften [agent_node.py:78-80](../../../../backend/app/agents/agent_node.py#L78-L80)
  so it still discourages an unnecessary tool call but no longer implies the
  catalog alone is a complete answer to "what do you offer."
- Correct `_FAST_PATH_GUIDANCE`'s claim
  ([agent_node.py:102-103](../../../../backend/app/agents/agent_node.py#L102-L103))
  that the corpus block is everything published - state instead that it is
  everything published except the confirmed catalog, which is provided
  separately above.
- Pass `package.offerings_text()` into `_build_knowledge_prompt`
  ([draft_node.py:67-89](../../../../backend/app/agents/draft_node.py#L67-L89))
  as a second grounded block alongside the numbered chunks, and change its
  "using ONLY the numbered context below" instruction to also admit the
  offerings block, naming both explicitly (for example: "using ONLY the
  confirmed offerings and numbered context below"). `draft_node` will need
  access to the `ContextPackage` (or only its `offerings` list) at the call
  site in the graph - trace how `retrieved_chunks` currently reaches it and
  thread `package.offerings` the same way rather than re-fetching from the
  database.
- Reuse the existing context package; do not extend
  [fuse.py](../../../../backend/app/retrieval/fuse.py) to rank catalog rows
  against knowledge chunks, and do not add a third retrieval source or a new
  catalog query. The catalog is small and already loaded whole by
  `build_package` ([context_package.py:128-141](../../../../backend/app/services/context_package.py#L128-L141));
  it belongs in the prompt directly, the same way it already does on the
  fast path, not through the scored-retrieval pipeline.
- Unconfirmed imports remain outside `offerings` until publish; the customer
  answer path reads only confirmed rows, and ambiguous source pricing stays
  flagged rather than becoming an invented exact amount.

### Tests

- Backend: extend or add to `test_context_package.py` a test that the
  **hybrid** knowledge-route prompt (the input to `_build_knowledge_prompt`
  or its resulting draft call) carries the offerings block - today nothing
  asserts this, and it is currently false.
- Backend: a test that a fast-path answer to "what do you offer" - using a
  `RecordingProvider` fixture whose canned reply references both an offering
  name and a knowledge-chunk-only detail - is accepted by whatever downstream
  check exists for provenance (inspection/price gate), confirming the
  combined answer does not trip the money-gate or provenance checks.
- Backend: `test_fast_path_prompt_lists_the_complete_confirmed_catalog`
  ([test_context_package.py:391](../../../../backend/tests/test_context_package.py#L391))
  stays green; extend its assertion or add a sibling asserting the
  instruction text no longer contains "before offering to share more detail".
- Backend: an unconfirmed (draft or unsaved) import is not available to the
  customer answer path; an ambiguous source price does not surface as an
  invented exact amount.
- Integration: publish a W-6/W-8 import, then ask a question that requires
  both its offering information and the retained knowledge - for example,
  "how much is X and what are your opening hours?" - and assert a single
  reply carries both the confirmed offering fact and the knowledge-derived
  detail.
- E2E or manual: reproduce the founder's exact scenario end to end - onboard
  a tenant with three chip-typed offerings and upload a document with
  additional menu detail, then ask the storefront chat "what services do you
  offer?" once, and confirm the single reply lists items from both sources.
  Per the bug-fix protocol
  ([conventions.md section 5](../../design/conventions.md)), reproduce this
  through the actual customer chat surface before considering the fix
  verified, not only via a unit test.

### Definition of done

- [x] A single customer-facing reply combines a relevant offering with a
      relevant policy or business detail on both the fast and hybrid paths.
- [x] Relevant offerings are used; the complete catalog is not dumped
      unnecessarily.
- [x] Confirmed structured prices retain their existing authority.
- [x] Pricing and inspection rules remain enforced; unconfirmed imports stay
      unavailable; ambiguous source pricing is not invented into an exact
      amount.
- [x] The integration scenario above passes.
- [x] `_FAST_PATH_GUIDANCE`'s claim about corpus completeness is accurate.
- [x] The scenario is reproduced and confirmed fixed through the actual
      customer chat surface, per the bug-fix protocol.
- [x] `make check` green.

Shipped. Verified through the real customer chat surface against a live model
(the `bytefix` tenant, 19 confirmed offerings and 4 ready documents), twice
each way. Before: "What do you offer?" enumerated the catalog price by price
("the iPhone 11 refurbished 64GB for 249 dollars, the iPhone 12 refurbished
128GB for 349 dollars ...") - the founder's reported symptom. After: one
concise reply naming the relevant offerings across devices, accessories, and
repairs together with the cited knowledge, no price-by-price dump.

One addition beyond the ticket text was required to make the fix hold.
`inspection._provenance_text` built the grounding judge's only evidence from
`retrieved_chunks` alone, and catalog rows are excluded from retrieval on both
paths by design, so a reply naming a confirmed offering had no supporting text
in front of the judge - this ticket's own goal would have failed grounding and
escalated. The offerings block is now appended to that provenance text. The
price gate needed no change: `price_gate.owner_material` already concatenated
the offerings string.

---

## W-6: Extract accurate offerings from the complete source

### Summary

Rewrite the document-offering extraction around source fidelity rather than
heading-specific line splitting. An owner who uploads one document describing
the whole business - facts, policies, hours, and what they sell with prices -
gets each distinct sellable item extracted into a reviewable candidate with a
name, a description, and a price bound to the correct item, landing in the
`offerings` table at confirm the same way chip-typed offerings do today. The
model never authors a price; it identifies items and references the source
evidence, and the server resolves those references and derives integer cents
deterministically. Complex and conflicting pricing is preserved and flagged,
never flattened or invented.

Sequenced after W-5 so the retrieval fix (one answer draws from both sources)
is already in place before this ticket makes the catalog larger and more
complete. The review usability that this richer candidate data feeds is W-8.

### Why

Today, document-derived offering candidates come only from two hard-coded
section headings ("What we offer", "Prices") and are split at the first
monetary figure in each line
([offering_candidates.py:76-159](../../../../backend/app/features/business/offering_candidates.py#L76-L159)).
`description` is never populated from a document - `PendingOffering.description`
defaults to empty and is only ever filled by hand in the review sheet. A
business document that describes its menu in prose, under a business-specific
heading, or with an item's description on a separate line from its price
produces no offering candidates at all, or candidates with no description. The
40-row pasted review output the founder reported shows the downstream result:
offering names rendered as sentence fragments (`"Bowl is,"`, `"the,"`) and
prose joins (`"Plate and Pita Pocket both run"`), which no slot on the review
sheet can map back to a real item. The founder's ask is to treat the whole
document as the source of offerings-with-detail, with an explicit boundary
that a numeric amount anywhere in the document does not by itself prove it
belongs to a particular offering.

### User stories

#### US-1 Offerings described anywhere in the complete source become candidates

As a business owner, if my uploaded document describes an item I sell - its
name, what it is, and its price - anywhere in the document, in any formatting,
it shows up as an offering candidate for me to review.

- The extraction reads the supported text-bearing document in full: lists,
  table-derived text, prose, and mixed formatting.
- Offerings are found even when their names, descriptions, and prices appear
  in different sections of the document.
- Repeated evidence about the same item is joined, not duplicated.
- Offerings are distinguished from categories, descriptive sentences, and
  unrelated facts.
- No candidate is created whose name is a sentence fragment or prose join such
  as "Bowl is", "the", or "Plate and Pita Pocket both run".
- Meaningful distinctions between separately sold items are preserved - a
  category is not collapsed into its individual products, and two separately
  sold items stay separate.

#### US-2 Incomplete or degraded processing is visible, not silent

As a business owner, when a document is too messy to extract fully, I can see
that extraction was incomplete and review the source, instead of being handed
a truncated result that looks complete.

- The review state distinguishes "fully extracted" from "partially or not
  extracted", and keeps the source context available for manual review.

#### US-3 A candidate carries a source-supported description

As a business owner, an offering candidate extracted from my document shows a
concise, readable description supported by the source, so I am not starting
from a blank or invented description in review.

- The description preserves distinguishing inclusions, options, restrictions,
  and units.
- The description stays absent when the source provides none.
- No ingredients, services, or marketing claims are invented.

#### US-4 Money is bound to the item it belongs to, never authored

As the platform, a price shown to a customer is always a number the server
computed from the document's own text for that item, never a figure the
language model wrote, and never an amount merely because it appears somewhere
in the document.

- The extraction schema has no numeric price field at all - there is no field
  for a model to fill with an invented number.
- The server resolves the source references and derives integer cents
  deterministically, accepting a price only when its relationship to the item
  is supported and unambiguous.
- Missing, invalid, or mismatched references are rejected.

#### US-5 Complex prices stay intact and flagged

As a business owner, a price that is not a single flat number - a range, a
"from" price, a unit, a variant, a bundle, a surcharge, or a currency note -
is preserved with its context and marked for review rather than flattened or
dropped.

- The numeric field is populated only when the existing offering
  representation can preserve the meaning; otherwise it is left unset, the
  source wording is retained, and the candidate is marked for review.
- A genuinely absent price is distinguished from an ambiguous or conflicting
  one.
- No full variant, quotation, or pricing-rule editor is introduced.

### Design reference

The onboarding thread and its knowledge-review sheet are unchanged in
structure - `ReviewSheet.tsx` already has a description field in its data
model; this ticket makes document-derived candidates populate it, and adds no
new screen. Images remain explicitly out of scope, per the founder's own
framing: onboarding stays text/price/description only, and an owner adds
images afterward from the Business tab, which `M-2` already supports. The
paginated review editor and duplicate decisions this feeding data supports are
W-8.

### Technical spec

- **Stage one, unchanged.** `structure_document`
  ([structuring.py:139-174](../../../../backend/app/features/knowledge/structuring.py#L139-L174))
  already reorganizes the raw document into the fixed headings under the
  `figures_preserved` money guard
  ([structuring.py:120-128](../../../../backend/app/features/knowledge/structuring.py#L120-L128)),
  which discards the model's structured output entirely (falling back to
  `AS_WRITTEN`) if it invents a figure. Keep this stage and this guard exactly
  as they are - they are the existing enforcement of the
  deterministic-pricing invariant at the structuring layer. This ticket adds a
  second enforcement point rather than relaxing this one.
- **Money-reference boundary.** Enforce the five-step contract:
  1. The server identifies the original source blocks and their monetary
     occurrences.
  2. The extraction result identifies offerings and references their
     supporting evidence (source blocks, not heading-specific lines).
  3. The model does not populate monetary amounts or `price_cents` anywhere.
  4. The server resolves the references and derives integer cents
     deterministically.
  5. A price is accepted only when its relationship to the item is supported
     and unambiguous.
  Reject missing, invalid, and mismatched references. A shared explicit price
  may apply to two separately named items when the source establishes that
  relationship (for example a listed price that names both items); it must
  not be used to create a composite sentence-fragment offering.
- **New stage two: whole-source item extraction without price.** Add an
  extraction pass (new Pydantic schema, e.g. `ExtractedOffering` carrying a
  name, a description or an empty description, and the source references for
  both, with a separate model-free price relationship) that runs over the
  full supported text of the document, not only the `offerings` and `prices`
  structured sections. Prompt instruction: identify each distinct sellable
  item wherever its name, description, and price-information appear - across
  lists, table-derived text, prose, and mixed formatting - join repeated
  evidence about the same item, distinguish offerings from categories and
  descriptive sentences, and never write a number.
- **Deterministic price resolution and provenance check.** For each extracted
  offering, resolve its price references against the server-identified source
  blocks and the monetary occurrences within them (exact substring match);
  reject the candidate's price when the reference is not found or does not
  match (the model paraphrased instead of quoting, which also means it is not
  safe to trust for price extraction). For an accepted reference, run
  `extract_monetary_figures` on the source block to get `price_cents` the same
  way `derive()` does today
  ([knowledge/service.py:223-234](../../../../backend/app/features/knowledge/service.py#L223-L234)).
- **Complex prices conservatively.** Preserve the context for ranges, "from"
  prices, units, variants, bundles, surcharges, and currency. Populate
  `price_cents` only when the existing offering representation can preserve
  the meaning; otherwise leave it unset, retain the source wording, and mark
  the candidate for review. Distinguish genuinely absent prices from
  ambiguous or conflicting ones. Do not introduce a full variant, quotation,
  or pricing-rule editor.
- **Reconcile repeated evidence with one shared precedence policy.** Consolidate
  exact, compatible repetitions while retaining provenance. Do not silently
  resolve conflicting prices. Preserve owner edits when incorporating document
  information. Generate possible-match suggestions for similar names (for
  example `"coffe"` and `"coffee drinks"`) rather than merging them, and never
  collapse a broad category into its individual products. Apply one shared
  precedence policy across backend and frontend behavior - the same rule the
  client uses to resolve a merge must be the one the server documents.
- **Fold into `PendingOffering`.** Produce `PendingOffering(name, description,
  price_cents, sources=["document"])` from the accepted candidates, merging by
  `normalize_name` the same way `_merge_owner_offerings`
  ([agent.py:162-185](../../../../backend/app/onboarding/agent.py#L162-L185))
  already merges owner-typed names, so a document candidate and an
  owner-typed chip candidate with the same normalized name combine into one
  reviewable row rather than duplicating - subject to the precedence policy
  above.
- **Run extraction during ingestion, not on every read.** The shared
  extraction mechanism runs during ingestion, not whenever a draft is read.
  Cover every caller of that mechanism, including onboarding and later
  knowledge imports.
- **Handle failure safely.** When extraction fails, preserve usable knowledge
  and safe candidate information; keep the source context available for manual
  review. Do not fall back to the same unsafe first-number parsing behavior.
- **Review sheet.** Update `ReviewSheet.tsx` to render `description` for every
  candidate regardless of source, to surface flagged complex/conflicting
  prices, and to render possible-match proposals. Confirm the existing
  save/discard handlers (`saveKnowledge`, `discardKnowledge` in `page.tsx`)
  pass the description through to
  `PUT /api/onboarding/knowledge/{document_id}` - check whether
  `OnboardingKnowledgeRequest`'s `offerings` field already round-trips
  `description`; if not, that is the one wire-shape gap to close.
- **Retrieval consumer.** No change needed beyond W-5: once these
  document-sourced rows are confirmed into `offerings` at publish
  (`reconcile_offerings_batch`, [business/service.py:187-244](../../../../backend/app/features/business/service.py#L187-L244)),
  they are projected into the vector store by the existing
  `ingest_offerings` pipeline and answered from by the same catalog block
  W-5 already wired into both the fast and hybrid prompts. This ticket's job is
  only getting a complete, priced, described, correctly-bound catalog into that
  table; W-5 is what makes the chat answer from it correctly.

### Tests

- Backend: a fixture document with an item's name, description, and price on
  separate lines or in different sections yields one candidate with all three
  populated and the price bound to the right item.
- Backend: prose and table-derived documents (not only list-shaped lines
  under the two fixed headings) yield distinct, correctly-named candidates;
  a category and its individual products stay distinct.
- Backend: a candidate whose model-returned source reference does not appear
  verbatim in the source document is dropped, not trusted.
- Backend: no test path allows a `price_cents` value that does not trace back
  to `extract_monetary_figures` output on real document text - the regression
  test for the deterministic-pricing invariant on this new path, analogous to
  the existing figure-provenance tests in `test_agent_graph.py`.
- Backend: a two-priced or range document keeps its context, leaves the
  numeric field unset, retains the source wording, and is marked for review.
- Backend: `"coffe"` and `"coffee drinks"` produce a possible-match suggestion,
  not an automatic merge; a shared explicit price for two named items is
  honored only when the source establishes the relationship.
- Backend: extraction does not re-run on every draft read, and every caller of
  the shared mechanism (onboarding and later knowledge imports) is covered.
- Backend: a document-sourced candidate and a chip-typed candidate with the
  same normalized name merge into one `PendingOffering` rather than
  duplicating, under the shared precedence policy.
- Frontend: `ReviewSheet` renders a non-empty description for a
  document-sourced candidate.

### Definition of done

- [x] Offerings described anywhere in a whole-business document - lists,
      table-derived text, prose, and mixed formatting - are extracted as
      reviewable candidates with correct names.
- [x] Each candidate carries a source-supported description (or none when the
      source provides none).
- [x] Every price is derived deterministically from quoted, source-resolved
      references bound to the correct item; no extraction schema has a
      model-fillable numeric price field; an amount's mere presence in the
      document never binds it to an item.
- [x] Complex and conflicting prices are preserved with context and marked for
      review, never flattened or invented.
- [x] Repeated evidence is reconciled under one shared precedence policy
      without silent merges or conflicts.
- [x] Extraction runs during ingestion for every caller; failures preserve
      usable knowledge and source context instead of unsafe first-number
      parsing.
- [x] The review sheet shows name, description, and price together for
      document-sourced candidates.
- [x] The confirm-time write path and the retrieval path from W-5 need no
      further change to serve these rows.
- [x] `make check` green.

Shipped `feat/w-6-offering-extraction` (2026-09-06). Full record in
`progress.md`'s "W-6 shipped" entry: Stage 0 indexes every monetary figure
before the model sees a token, so the extraction schema has no numeric field
at all and money can only reference that frozen index; extraction moved to
ingest (`documents.offerings`, migration 0026) so it runs once per document
instead of on every read; `derive()` and its regex-based helpers are deleted,
leaving one extraction path. Verified against the founder's own PDF, recovered
as `backend/tests/fixtures/`. Still owed at the time of shipping: a browser
pass with a live model configured locally (everything either side of the model
call is verified end to end against the real fixture text).

**Checkboxes above corrected 2026-09-06** - this section had shipped without
its own Definition of done being ticked, which is what left `progress.md` and
this file's own header disagreeing about W-6's status.

---

## W-7: The interview reads like a person, not a form

### Summary

W-2 stopped the re-asking, but it did so by taking all phrasing from the model
and bolting on machinery (a two-pass deferral surfaced through a "Skip for now"
chip, a reassuring nudge) to cover the cases a fluent model used to handle on
its own. On the next walkthrough that machinery read as robotic: a warm "no
worries" plus several questions at once, a skip chip on the first ask, a chip
that lingered after tapping, and a go-live screen re-asking for the business
name and type it already had. W-7 gives the conversational work back to the
model while keeping W-2's guarantee, and adds the one thing neither version had:
a server-plus-model check that a reply is actually a usable answer.

### Why

Every symptom traced to a specific W-2 addition (before/after stated to the
founder per 5.1 before the change):

| | After W-2 | After W-7 |
|---|---|---|
| Junk answer ("34234234" as a name) | saved - `Beat.complete` only checks non-empty | challenged in the beat's voice and re-asked; never saved |
| "No worries" + several questions | `_nudge()` told the model to reassure and give an example; the hours ask was two questions joined by "and" | one short sentence; `_ack` strips any stray question; hours is one question |
| "Skip for now" chip | on `name`/`services` from the first ask | removed entirely; a beat resolves on the ask cap |
| A tapped chip lingered | `disabled` only | the chip row unmounts for the in-flight turn |
| Go-live re-asked name/type | two editable fields | address only, prefilled, with a "Going live as X" read-back |
| Empty go-live address | `suggested_slug("")` is the truthy reserved fallback `business-page`, locked in on first load | null until a name exists, so the address prefills to the real slug |

### What W-7 keeps from W-2

The two-ask cap and the second-pass deferral are unchanged - they were right;
what was wrong is that the hand-off was silent, so a deferred beat resurfacing
later read as the assistant losing its place. It now says "No problem - I'll
come back to this." out loud. The question is still server-owned (appended
verbatim), which is the guarantee that a filled slot can never be re-asked.
If a required beat remains unusable after its second pass, the interview pauses
with the field unset and a retry action. It never falls back to storing the
owner's raw words or exposes the go-live action until the field is valid.

### The usability check (two judges, either vetoes)

Each text beat gains `valid` (a deterministic plausibility check - a name needs
letters, hours need a time or a day, a contact needs an `@` or six digits) and
`reject`/`example` copy. The extractor gains `answered_asked`, its verdict on
whether the reply genuinely answered the asked field. A captured value is
usable only if it has a value **and** the model did not flag it **and** `valid`
passes. The server floor catches structural junk (`34234234`); the model catches
word-shaped nonsense (`asdfgh` as a business type). A value the model mislabels
off-topic is still challenged when it cannot be the beat's answer. On a veto the
value is dropped back out and the model is told to re-ask that one field.

### User stories

- **US-1** Junk input is challenged by name, not absorbed: "34234234" for a
  name gets "that doesn't look like a name" and the same question, never saved.
- **US-2** Replies are one short sentence plus one question - no "no worries",
  no list of what is still missing, no double question.
- **US-3** A beat unanswered after two asks hands off out loud and the interview
  moves on, the deferred beat returning once.
- **US-4** Only the skip chip is removed; every functional chip (headcount,
  contact email/phone, ABN, GST) stays, and a tapped chip disappears while the
  turn is in flight.
- **US-5** Go-live confirms the address only, prefilled to the real slug, with a
  "Going live as X" line; name and type are not re-asked.
- **US-6** The knowledge review shows one card per offering (name and price on a
  row, description beneath); the document's own offering/price sections are not
  also shown as raw text, and a document overlaps an owner-typed name by taking
  the document's price and description.
- **US-7** A required field that still has no usable answer after both passes
  pauses the interview. The owner can retry it later, and cannot publish until
  it is valid.

### Decision on latency

No extra model calls: `answered_asked` rides inside the existing extraction
call, `valid` is regex, and the reply still streams live (sentence-buffered, so
a trailing question can be dropped). Same two calls per turn as before W-2.

### Amends W-2

The skip chip and the go-live name/type read-back fields introduced in W-2 are
removed here; the two-ask cap and the second-pass deferral are kept (only their
silence is fixed). No `version` bump - the removed `OnboardingRecord` fields
that remain (`deferred`, `ask_beat`, `ask_count`) read through defaults.

### Definition of done

- [x] Junk input is challenged and never saved (server + model, either vetoes).
- [x] Replies are one short sentence and one question; hours asks once.
- [x] The skip chip is gone; every functional chip stays; a tapped chip vanishes.
- [x] A two-times-unanswered beat hands off out loud, then moves on.
- [x] Go-live shows the address only, prefilled to the real slug.
- [x] The review sheet shows one priced card per offering; the document wins an
      overlap.
- [x] A final unresolved required beat pauses and can be retried without storing
      an invalid fallback or allowing publication.
- [x] `make check` green.

Shipped `cd10f6e`. Forward references: W-4 preserves this ticket's shipped
address-only confirmation behavior and narrows itself to the remaining paths;
W-9 refines the conversation's response to name corrections. This ticket's
checked criteria are unchanged by the 2026-09-05 amendment.

---

## W-8: Review a large import without losing information

### Summary

Add a ticket for the existing review sheet's usability with a large import.
Show up to five offering cards initially, open a five-per-page editor when
there are more, add possible-duplicate combine/keep-both decisions, and make
the knowledge sections editable without losing factual detail. The current
`ReviewSheet` renders every candidate in one scrollable list under the
knowledge sections; this ticket pages that list, adds duplicate resolution,
and keeps the existing save, discard, and go-live boundaries.

Refined by the 2026-09-05 amendment to make the five-item preview and the
five-per-page editor concrete, to add duplicate decision behavior, and to
require that formatting and editing preserve factual distinctions.

### Why

The 40-row pasted review output showed an import that a single-page review
cannot manage: every candidate renders inline
([ReviewSheet.tsx:134-212](../../../../frontend/src/components/knowledge/ReviewSheet.tsx#L134-L212)),
duplicate names are a hard save block rather than a decision
(`hasDuplicateNames`, [ReviewSheet.tsx:257-264](../../../../frontend/src/components/knowledge/ReviewSheet.tsx#L257-L264)),
and the knowledge sections are single textareas that drift from their source.
The founder asked for a review that scales to a real business document without
losing information: a bounded preview, a paginated editor, explicit duplicate
choices, and readable, editable sections that preserve exceptions, conditions,
locations, units, and other factual distinctions.

### User stories

#### US-1 A large import opens with a bounded preview

As a business owner, when my upload produces many offering candidates, I see a
bounded preview first, showing up to five offering cards and the total retained
count.

- Up to five offering cards are shown initially, with the total count stated.
- For more than five, a "Review all" control opens the editor.
- Pagination controls are absent when there are five or fewer offerings.

#### US-2 The expanded editor pages the offerings

As a business owner, when I open the editor I get five offerings per page with
position and previous/next controls, and my edits survive paging.

- The expanded editor displays five offerings per page with position and
  previous/next controls.
- Edits, removals, additions, and review decisions are preserved across page
  changes.
- Newly added offerings are revealed for editing.
- Removing the final item on a page moves to a valid adjacent page.
- Stable candidate identities keep edits attached to their item after
  deletion or reordering.

#### US-3 Saving includes everything retained, and nothing publishes early

As a business owner, I can save knowing every retained offering is included,
even ones I am not currently looking at, and paging or previewing never
publishes anything.

- Saving includes all retained offerings, including those outside the visible
  page; the owner does not need to open every page to save correctly.
- Paging and previewing do not publish data.
- The existing save, discard, and go-live boundaries are preserved.
- Off-page validation errors are discoverable, with a direct route to the
  affected item.

#### US-4 Possible duplicates are decisions, not blocks

As a business owner, when the import finds names that might be the same item,
I can combine them or keep both, and I always know which values a combine
would keep.

- Possible duplicates are shown with a subtle highlight, a textual
  explanation, and source labels.
- "Combine" and "Keep both" are offered. Before combining, the sheet shows
  which name, description, and price will be retained.
- Owner values are preserved unless the owner chooses a replacement; an
  explicit price choice is required when combining conflicting values.
- Suggestions left unresolved remain separate; saving never implies an
  unconfirmed merge occurred.
- The count of remaining possible matches is shown without forcing inspection
  of every unrelated offering.

#### US-5 Knowledge sections stay readable and edit without losing detail

As a business owner, the sections I review are readable and editable, and
formatting preserves the facts, not a lossy summary.

- The existing sections (business information, hours, location, policies,
  other information) and their order are kept.
- Short paragraphs, plain bullets, and preserved line breaks are supported.
- Multiline editing is supported for descriptions and longer knowledge text.
- Formatting preserves exceptions, conditions, locations, units, and other
  factual distinctions.
- The review is not replaced by a lossy summary; unrepresented offering and
  pricing details stay accessible through a collapsed source-detail view.

### Design reference

The current `ReviewSheet`
([ReviewSheet.tsx](../../../../frontend/src/components/knowledge/ReviewSheet.tsx))
is the base; the prototype and design tokens in `theme.css` set the layout,
spacing, controls, and states. Keyboard access and mobile behavior are
verified alongside desktop presentation. No new rich-text editor dependency
and no replacement wizard; a collapsed source-detail view reuses the existing
sheet/collapse vocabulary.

### Technical spec

- **Preview.** Above the editor, show up to five offering cards (name and
  price on a row, description beneath - the W-7 card shape) plus the total
  retained count. When the count exceeds five, a "Review all" control opens
  the expanded editor; otherwise the preview is the editor.
- **Pagination.** The expanded editor pages at five offerings per page with
  position and previous/next controls. Render no pagination controls at five
  or fewer. Preserve edits, removals, additions, and review decisions across
  page changes; reveal newly added offerings for editing; move to a valid page
  when removing a page's final item. Give each candidate a stable identity
  (see the contract extensions) so edits cannot migrate to another item after
  deletion, reordering, or a duplicate decision.
- **Save.** Saving includes every retained offering regardless of the visible
  page; no per-page save. Paging and previewing are read-only with respect to
  publish. Keep the existing save, discard, and go-live boundaries. Make
  off-page validation errors discoverable and link them directly to the
  affected item.
- **Possible duplicates and conflicts.** Compute possible matches (see W-6's
  precedence policy) and render them with a subtle highlight, a textual
  explanation, and source labels. Offer "Combine" and "Keep both". Before a
  combine, show which name, description, and price win; keep owner values
  unless the owner chooses a replacement; require an explicit price choice
  when the combining values conflict. Unresolved suggestions remain separate,
  and saving must never imply an unconfirmed merge. Show the count of
  remaining possible matches without forcing full inspection.
- **Knowledge formatting.** Keep the sections and their order; render short
  paragraphs and plain bullets with preserved line breaks; support multiline
  editing for descriptions and longer text; preserve exceptions, conditions,
  locations, units, and other factual distinctions; keep a collapsed
  source-detail view for unrepresented offering and pricing details. No
  rich-text editor dependency, no lossy summary, no replacement wizard.

### Tests

- Frontend: zero, five, six, 40, and at least 50 candidates render the
  preview/per-page behavior correctly (no pagination at five or fewer;
  position and controls at six; correct page counts at 40 and 50+).
- Frontend: editing, adding, and removing offerings across pages preserves
  those changes; adding reveals the new item for editing; removing a page's
  final item lands on a valid page; deleting or reordering an item does not
  move another item's edits to it.
- Frontend: a save with items on an unvisited page persists all retained
  offerings; paging and previewing make no publish calls; off-page validation
  errors are discoverable and route to the affected item.
- Frontend: a possible-duplicate pair shows highlight, explanation, and source
  labels; "Combine" and "Keep both" behave per the rules; conflicting combine
  requires an explicit price choice; unresolved suggestions stay separate and
  saving does not imply a merge.
- Frontend: complete knowledge details survive formatting and save (exceptions,
  conditions, locations, units; long paragraphs), keyboard and mobile
  verification alongside desktop.
- Fixture-driven: use controlled fixtures with explicit expected results for
  the above, as deterministic regression tests.

### Definition of done

- [x] Up to five offering cards preview with the total count; "Review all"
      opens the five-per-page editor.
- [x] Edits, removals, additions, and review decisions survive paging; newly
      added items are revealed; removing the final item pages validly; stable
      identities prevent cross-item edit drift.
- [x] Saving includes all retained offerings; paging and previewing never
      publish; existing save/discard/go-live boundaries hold; off-page errors
      are discoverable with a direct route.
- [x] Possible duplicates render as decisions (combine or keep both) with the
      retained values shown, explicit conflict price choice, and no implied
      unconfirmed merge.
- [x] Knowledge sections stay readable and editable, preserving factual
      distinctions; a collapsed source-detail view keeps unrepresented details
      accessible.
- [x] Keyboard and mobile behavior verified alongside desktop. Closed by W-9,
      which built the sheet vocabulary this review UI shares: the keyboard pass
      is `frontend/e2e/settings-voice.spec.ts:120` (tab order reaches the row,
      Enter opens the sheet, focus is trapped both ways, Space and Enter work
      the chips, Escape closes and restores focus), and the touch pass is
      `frontend/e2e/mobile-voice-sheet.spec.ts:16` under the `mobile-chrome`
      project at iPhone 13 width (no horizontal overflow, the panel rests
      inside the viewport, every control is a 44px tap target, and the whole
      save round trip works with taps alone). That pass is also what found the
      36px `ScreenTopbar` back button, fixed in commit `9109d17` on every
      console screen that carries a topbar.
- [x] `make check` green.

---
## W-9: Definitive onboarding and customer-assistant contract

### Summary

The single authoritative ticket for the phase's closing work: correct
onboarding's name-capture and correction behavior end to end, restructure both
onboarding and customer prompts into code-owned contracts with tenant data
riding in at lower authority, add structured customer voice configuration,
and retire the free-text `tenant_config.system_prompt`/`tone` columns from
every read path (their drop is a follow-up ticket - see Migration below).
Evidence, the agent-contract and persona definitions, the copy-rule amendment,
and the table of exactly what this ticket preserves versus changes in W-2,
W-5, W-6, W-7, and W-8 all live in
[Amendment 3](#amendment-3-the-agent-contract-2026-09-06); this ticket
references that record rather than restating it.

### Why

The repository scan behind Amendment 2 confirmed the reply-context duplication
(`agent.py:690` appends the owner's message to history, then the `[-3:]` slice
at 710-711 always includes it, then line 712 appends it a second time - every
turn, both paths) but stopped short of a fix. Separately, the founder's own
walkthrough transcripts show a name-confusion pattern this ticket exists to
close: the owner's typed name silently becoming a business-name fallback
(`agent.py:269`), spelling variants persisting uncorrected across turns, and no
way to correct a captured field without re-triggering the beat that captured
it. On the customer side, three of six prose routes never saw the tenant's
configured prompt at all
([draft_node.py](../../../../backend/app/agents/draft_node.py) - conversation,
recommendation, and quoting are code-only today), the same
`system_prompt`/`tone` pair is read by three independent, only-partly-cached
call sites, and the prompt-leakage eval's canary is planted directly in the
column this ticket retires from every read path.

### User stories

#### US-1 The name I give is confirmed before it's kept

As a business owner, when I type my name or my business's name, I see the
model's proposed spelling/spacing/capitalization and a Yes action before
either is persisted; a typed reply is a new correction, not a rejection of the
proposal, and an unusual but explicitly confirmed name is accepted unless it
violates a storage or safety limit.

- The raw input is preserved as evidence alongside the visible proposal.
- Explicit confirmation is required before either `owner_display_name` or
  `business_name` is persisted.
- `sababa` confirmed stays `sababa` - never a concatenation onto the raw value
  (`Sababasababa`).
- Reloading mid-confirmation resumes the same pending proposal.

#### US-2 My name and my business's name are never confused

As a business owner, the assistant never uses my own name as a stand-in for my
business's name, and asks me which one I mean when a correction is ambiguous.

- `_activation_summary`'s fallback (`agent.py:269`,
  `business_name or name`) is removed; a missing `business_name` is a
  deferred required beat, never a silent substitution.
- "Change the name" with both names on file asks a focused clarification
  before applying anything.
- `owner_display_name` never reaches the customer-facing prompt
  (`_PROFILE_LABELS`, [context_package.py:57-64](../../../../backend/app/services/context_package.py#L57-L64),
  stays exclusive of it).

#### US-3 A correction works from any beat, without losing my place

As a business owner, correcting something I already answered - regardless of
which question is currently on screen - is applied, validated, and persisted,
and does not cost me an attempt at the question I'm actually being asked.

- A correction to a previously captured field is recognized as a correction,
  not an answer to the pending question, and does not touch `ask_count`
  bookkeeping ([agent.py:640-652](../../../../backend/app/onboarding/agent.py#L640-L652)).
  This applies during every beat, not only the beat that first captured the
  field.
- An invalid correction keeps the previous valid value; unrelated fields and
  interview progress are untouched.
- Accepted corrections survive reload and land in the confirmed profile.
- A genuinely off-beat fact volunteered mid-question is still captured without
  derailing the current beat - the capability W-2 built stays intact.

#### US-4 Offering edits are operations, not a rewrite

As a business owner, adding, renaming, removing, and explicitly replacing an
offering are distinct actions; renaming one leaves its siblings, description,
price, and provenance untouched.

- Reuses `merge_offerings` ([flow.py:78-99](../../../../backend/app/onboarding/flow.py#L78-L99))
  as the single precedence statement W-6 established - no second rule is
  added anywhere.
- Every W-6 provenance/source field survives a rename.
- The walkthrough's description of an update as a "tool call" does not bring
  back an obsolete tool loop.

#### US-5 One acknowledgement, one question, one message

As a business owner, giving or correcting a name produces one acknowledgement
with consistent spelling, one assistant response, and my own message appears
exactly once in what the model sees.

- `reply_msgs` carries the current owner message once, on both the streamed
  and non-streamed paths.
- No subjective praise, fabricated enthusiasm, "no worries", or ambiguous "my
  name" phrasing - `_COPILOT` and `Directive.as_prompt()` are restructured
  into Role/Goal/Success Criteria/Constraints/Conversation Rules/Output/Stop
  Rules to make these prohibitions structural, not incidental phrasing.
- No generic text deduplicator is added - the fix is the message-assembly bug,
  not a string-similarity patch that could eat legitimate repeated words.

#### US-6 Conservative wording cleanup

As a business owner, clear spelling mistakes in ordinary words are fixed
through the existing extraction call, while my name, brand names,
capitalization, identifiers, contact details, and money are left alone unless
I explicitly correct them.

- No second "cleanup" model call - routed through the existing `DraftUpdate`
  extraction.
- Ambiguous input is preserved, never guessed.
- Every cleaned value is read back once so it can be corrected.

#### US-7 The customer assistant speaks with one contract, in my chosen voice

As a business owner, I pick how the public assistant sounds (warm and casual,
clear and professional, direct and concise, or my own description up to 300
characters), and that choice changes tone only - never facts, pricing,
escalation, tool behavior, or identity.

- All six customer prose routes (direct conversation, knowledge,
  recommendation, quote explanation, redraft, refusal/handoff) run the same
  code-owned contract with tenant data appended after it as lower-authority
  input - three of six ([draft_node.py](../../../../backend/app/agents/draft_node.py)'s
  conversation/recommendation/quoting) currently skip the tenant prompt
  entirely, which this ticket ends by making all six consistent.
- A hostile custom-voice string cannot override the money guardrail,
  grounding, identity, or escalation rules - verified with an adversarial
  fixture in the ticket's tests, not asserted by inspection alone.
- Saving voice configuration bumps `tenant_config.updated_at`, which the
  existing `knowledge_version` mechanism already turns into a cache
  invalidation for the agent prompt - no new invalidation path needed there.
  The greeting is a separate case; see Technical spec.

#### US-8 The customer assistant identifies itself honestly, without over-claiming

As a customer, the assistant introduces itself as the business's assistant,
never impersonates an employee or says "we" for something only a person could
do, and tells me the truth if I ask whether it's human or AI.

- Deterministic opening: "Hi, I'm [Business]'s assistant. How can I help
  today?" - "I" only for the assistant's own capabilities; the business is
  named or called "the team" for anything a person did.
- Answers first, then one relevant next step when useful - no manufactured
  urgency, no unrelated upsell.
- Genuine frustration is acknowledged once, then the assistant moves to
  solving the problem.
- A missing answer states the gap and offers follow-up; a human handoff is
  created only when requested or accepted, never assumed.

### Design reference

No new customer-facing screen beyond the voice editor, which follows the ABN
sheet's own visual pattern
([`AbnSheet.tsx`](../../../../frontend/src/app/(tenant-admin)/(console)/business/details/components/AbnSheet.tsx))
rather than a new prototype screen - a `Chip` group for the four presets, the
fourth opening a bounded text field, `role="alert"` for validation, keyed on
current values so an abandoned edit discards on close. The onboarding thread
itself gains no new screen; the name-confirmation Yes action is a chip on the
existing thread, following the vocabulary the existing chip beats already use
(`apply_selection`, [beats.py:355-377](../../../../backend/app/onboarding/beats.py#L355-L377)).

### Technical spec

**Onboarding record.** Bump `OnboardingRecord.version` from the literal `3` to
`4` ([agent.py:140,172,201](../../../../backend/app/onboarding/agent.py#L140)).
The existing `from_jsonb` branch drops any record that isn't exactly v3
([agent.py:162-197](../../../../backend/app/onboarding/agent.py#L162-L197)) -
add a v3-to-v4 upgrade that renames `draft["name"]` to
`draft["owner_display_name"]` and carries every other field forward untouched
(`history`, `offering_candidates`, `skipped`, `deferred`, `ask_beat`,
`ask_count`, `paused_beat`). This is a genuine version bump, unlike W-2's
fields which were deliberately added without one because their absence already
read as "fresh" (`agent.py:181-183`) - a rename cannot rely on that trick.
Rename propagates to `flow.py:23` (`ProfileDraft`), `beats.py:182-197` (the
beat key and its ask text), and the confirm write
(`controller.py:513-523` → `service.py:78-85`).

Add pending-name-confirmation state: raw input, the visible proposal, and
which name it targets. The rejection path already pops a bad value back out of
the draft with no memory of what it replaced
([agent.py:608](../../../../backend/app/onboarding/agent.py#L608)) - that seam
is where "keep the previous valid value on an invalid correction" attaches.

**Extraction schema.** `DraftUpdate`
([flow.py:54-72](../../../../backend/app/onboarding/flow.py#L54-L72)) gains
correction targets, offering `add | rename | remove | replace` operations, raw
evidence, and normalization type, alongside the existing `answered_asked`
(W-7). No schema anywhere gains a numeric field - W-6's frozen-money-index
discipline is unconditional.

**Prompt restructuring.** `_COPILOT`
([agent.py:100-106](../../../../backend/app/onboarding/agent.py#L100-L106))
and `Directive.as_prompt()` (83-97) become Role/Goal/Success
Criteria/Constraints/Conversation Rules/Output/Stop Rules. Fix the message
duplication at [agent.py:690,710-712](../../../../backend/app/onboarding/agent.py#L690)
so the owner's current message appears exactly once in `reply_msgs`, on both
`stream_reply` and `run_turn`. Wire up `Beat.reject`
([beats.py:116](../../../../backend/app/onboarding/beats.py#L116), populated
on six beats, read by nothing today) as the deterministic reply-validation
fallback text, and fix the stale module docstring
([beats.py:22-25](../../../../backend/app/onboarding/beats.py#L22-L25)) that
already claims this exists. Replace the salon-flavored services-beat example
([beats.py:257](../../../../backend/app/onboarding/beats.py#L257)) with
domain-neutral guidance. Add the voice beat as a chip beat after `services` in
`BEAT_ORDER`, validated server-side through `apply_selection` with no model
call, matching every other chip beat.

**Deterministic reply validation.** A post-generation check for identity
statements, single-question output, captured-value inclusion, monetary
claims, and pronoun inversion, reusing `_ack` (389-400, non-streamed only) and
`_flush_sentences` (407-429, streamed) rather than adding a parallel
mechanism. On failure: a deterministic acknowledgement plus the server-owned
question - no additional live model call, preserving W-7's latency decision.

**Customer contract.** Retire three independent, inconsistent readers of
`system_prompt`/`tone` - `context_package.py:121` (cached),
`draft_node.py:206-213` (per-turn DB read), `inspection.py:209-215` (per-turn
DB read) - behind one code-owned contract module applied to all six prose
routes (`agent_node.py`'s one-call turn, and `draft_node.py`'s conversation,
knowledge, recommendation, quoting, redraft). Tenant profile, offerings,
knowledge, and the new structured voice ride in after the contract as
lower-authority data; tool-specific instructions stay in the `ToolSpec`
descriptions ([agent_node.py:364-408](../../../../backend/app/agents/agent_node.py#L364-L408)),
not in prompt prose (`_TOOL_GUIDANCE`'s own comment at 64-73 already explains
why a per-tool bullet list was removed - it is not reintroduced here).
Deterministic strings (`REFUSAL_MESSAGE`, the order-status templates,
`HANDOFF_MESSAGE`, `GATE_ESCALATION_MESSAGE`, `ESCALATION_MESSAGE`,
`MONEY_GUIDANCE`) are unchanged.

**Structured voice config.**

```json
{
  "customer_voice": {
    "preset": "warm_casual | clear_professional | direct_concise | custom",
    "custom_style": "string or null"
  }
}
```

Lands in `config->customer_voice`. Migration backfills from the existing
`tone` column: `friendly` → `warm_casual`, `professional` →
`clear_professional`, a direct/concise equivalent → `direct_concise`, any
other non-empty value → bounded `custom_style`, missing → `warm_casual`. The
migration only backfills and stops application code reading the old columns -
it does not drop them (see Migration below).

**Greeting.** The fixed identity greeting composes first; any configured
`config->customer.greeting` becomes optional following content, normalized so
the two never double up. This is a frontend change
([CustomerChat.tsx:74-77](../../../../frontend/src/app/[slug]/CustomerChat.tsx#L74-L77))
plus a second invalidation path: the greeting travels through
`/api/tenants/resolve`'s own 60-second slug cache
([tenants/service.py:145-165](../../../../backend/app/features/tenants/service.py#L145-L165)),
which is separate from `knowledge_version` - a voice or greeting write must
call `invalidate_slug_cache` directly, not rely on the version bump alone.

**Voice editor.** Follows the ABN pattern end to end:
`PROFILE_FIELDS`/`write_profile`
([business/service.py:721,741-764](../../../../backend/app/features/business/service.py#L721))
extended with the voice fields, a `ProfileUpdate` extension with
`extra="forbid"` ([business/api.py:276-342](../../../../backend/app/features/business/api.py#L276-L342)),
generated types via `npm run gen:types`, aliased in `api-schemas.ts` (the R-3
direction) rather than hand-declared, and a sheet modeled on `AbnSheet.tsx`.

**Prompt-leak canary.** `check_prompt_leak`
([inspection.py:98-106](../../../../backend/app/agents/inspection.py#L98-L106))
currently substring-matches against `tenant_config.system_prompt` lines; it is
re-pointed at the code-owned contract text, which is a stable, testable set of
lines rather than free tenant prose. `LEAK_MARKER =
"SYSPROMPT-LEAK-MARKER"` ([seed_injection_probe.py:41-47](../../../../backend/seeds/seed_injection_probe.py#L41-L47)),
scored by eight cases in `injection_set.jsonl`, moves into the contract render
path so those cases keep their teeth. The judge prompt's "matches the stated
tone" clause ([inspection.py:236,245](../../../../backend/app/agents/inspection.py#L236))
is dropped - tone-as-prose no longer reaches the judge; tone/praise/concision
quality checks live only in transcript evaluations (below), never in a
production turn.

### Migration

`tenant_config.system_prompt` and `.tone` are **not dropped by this ticket.**
This ships as: backfill `customer_voice`, stop every application code path
from reading the two columns, keep the columns and their seed writes in place.
A separate, small follow-up ticket drops them after production verification -
the same shape as
[`0025_schema_cleanup.sql:33`](../../../../backend/migrations/0025_schema_cleanup.sql#L33)
dropping `escalation_threshold`. This resolves a genuine conflict in the
original request between "deliver as one commit" and "deploy
forward-compatible code before the destructive migration" - a single
squash-merge cannot do both, so the destructive half moves to its own ticket.

### Tests

- **Reproduce first** (conventions.md 5): the supplied transcript, driven
  through the real onboarding UI via `make demo`, screenshots kept as
  regression evidence, before any fix lands.
- Regression fixtures: `211e2esdsdfasdf`, `bkksbf88`, `21 ej2nek2ne2ken1e`,
  `sababa`, `middle eastern cafe` - `sababa` confirmed never becomes
  `Sababasababa`; no "my name" deferral language; no subjective praise for
  "middle eastern cafe"; no salon terminology in a cafe onboarding.
- Corrections during every beat; invalid corrections keep the prior value;
  off-beat facts still capture without derailing the current beat; all four
  offering operations; owner/business-name disambiguation on an ambiguous
  correction target.
- `reply_msgs` contains the current owner message exactly once, asserted
  directly (no test does this today -
  [test_onboarding_agent.py:483](../../../../backend/tests/test_onboarding_agent.py#L483)
  only checks it's `None`) - on both SSE and non-streamed paths, both
  persisting exactly one assistant response.
- Every customer prose route against the same identity/behavior contract;
  voice presets change expression only; an adversarial custom-voice fixture
  cannot override grounding, pricing, identity, escalation, or tool rules.
- Customer disclosure (honest answer to a direct human/AI question), sales
  restraint, frustration handling, missing-information follow-up, handoff
  consent, citations, plain-text output, prompt injection, deterministic
  pricing.
- Migration: existing v3 onboarding records and legacy `tone` values migrate
  without losing history, progress, or confirmed data; `customer_voice` is
  populated per the backfill rule.
- Update tests pinned to the old signatures:
  [`test_money_prompt.py:60-71`](../../../../backend/tests/test_money_prompt.py#L60-L71)
  (positional `tenant_prompt`/`tone` args),
  [`test_onboarding_api.py:586-594`](../../../../backend/tests/test_onboarding_api.py#L586-L594)
  (asserts `tone == "friendly"` post-confirm), `test_context_package.py`'s
  `package.system_prompt`/`tone` assertions, and confirm `test_schema_audit.py`
  / `test_migrations.py:44,57` stay green through the backfill migration.
- Single-turn and multi-turn transcript simulations in
  `tenant1_trajectory.jsonl` / `trajectory_eval.py`, deterministic terminal
  state plus provider-backed persona checks behind the existing `--skip-llm`
  split.
- Voice editor: persistence, validation, keyboard access, responsive layout,
  and next-turn activation (both the agent-prompt path via
  `knowledge_version` and the greeting path via `invalidate_slug_cache`).
- Keyboard and mobile verification for the voice editor closes W-8's one
  remaining open Definition-of-done box.
- No generic text deduplicator is added as part of the message-duplication
  fix.

### Record

Built on `feat/w-9-agent-contract` in seven commits: `3e9f349` (reproduction
evidence), `8a216ed` (phase 1a: rename, deduplication, prompt structure),
`aa663ca` (phase 1b: name confirmation, corrections, offering operations, the
voice beat, reply validation), `0759859` (phase 2: the code-owned contract,
structured voice, migration 0027), `37669c1` (phase 3: the voice editor API and
sheet, the composed opening), `1e66910` (phase 4a: tests and E2E), and
`9109d17` (the touch-target fix phase 4a's mobile pass found).

#### Behavior changes and decisions recorded rather than reopened

**The fast-path ceiling moved.** The contract plus its voice block measures
3,682 characters at its longest (a 300-character custom voice), against the
202-character prompt `system_prompt_for` used to produce, and
`_CONTRACT_OVERHEAD_CHARS`
([context_package.py:78](../../../../backend/app/services/context_package.py#L78))
carries that cost into the fast-path budget alongside the profile and the
offerings text. A tenant whose corpus sat within about 3,500 characters of that
budget therefore takes the hybrid path where it used to take the fast path.
That is the budget measuring the prompt honestly rather than a regression, but
it is a real behavior change on live tenants and belongs here rather than only
in a commit message.

**`_CONTRACT_OVERHEAD_CHARS` is a pin, not a measurement.** It reads 3,800
against a longest render of 3,682. The import contract
in [`backend/pyproject.toml`](../../../../backend/pyproject.toml) forbids
`app.services` from importing `app.agents`, so `context_package.py` cannot ask
the contract how long it is. The pin is held honest by
`test_the_pinned_prompt_overhead_covers_the_longest_render`
([test_agent_contract.py:206](../../../../backend/tests/test_agent_contract.py#L206)),
which imports both and fails the moment the contract outgrows the number.
Parking agent policy in `app.shared` to route around the contract would honor
its letter and break its intent, so it was not done.

**`MONEY_GUIDANCE` stays off the quoting route, deliberately.** Quoting already
forbids the model stating any figure at all, and `MONEY_GUIDANCE`
([drafting.py:28](../../../../backend/app/agents/drafting.py#L28)) permits
repeating a figure that is published in the material. Adding the general rule to
the stricter route would have licensed exactly the figures that route forbids.
The contract's own money clause covers quoting alongside the stricter rule, and
`test_every_prose_route_carries_a_money_rule`
([test_money_prompt.py:71](../../../../backend/tests/test_money_prompt.py#L71))
pins the whole arrangement, quoting's stricter wording included.

**A scraped business name still persists without a Yes chip.** US-1 is written
about a name the owner types; a `business_name` recovered from a website scrape
rides the O-3 read-back instead of the confirmation chip. Accepted as scope,
not fixed here.

#### The live eval gate is unmeasured, and what that leaves open

`make eval` was attempted twice, after phase 2 and again against the final
branch state. Both runs failed the same way and for the same reason, which is
quota rather than code: Groq answered `429 ... tokens per day (TPD): Limit
200000, Used 197445` for `openai/gpt-oss-120b` while the Google primary leg sat
in its own rate-limit retry ladder, so `generation_eval`, `injection_eval`, and
on the second run `trajectory_eval` errored instead of scoring. The day's
free-tier budget went on the phase 0 reproduction drives and the first attempt.

What that leaves proven and unproven:

- Proven, on both runs: `money_guardrail_eval`, `leakage_eval`, and
  `retrieval_eval` PASS. Those are the three deterministic absolute gates, and
  they include the money guardrail.
- Not proven: the three provider-backed regression gates. The
  `tool_correctness: 0.611` the first run recorded is not a measurement of
  anything - it was scored while provider calls were failing, and it carries no
  baseline, because `run_gate` reads the two most recent `eval_runs` rows and
  the re-seed left one.
- Re-run `make eval` once the daily window resets. Until it measures, the
  gate box stays unticked and this ticket stays in `spec/active/`.

**One eval failure was diagnosed and is not a regression.** The second run shows
`SelectionError: malformed catalog item id: 'tempered-glass-screen-protector'`
from [`pricing/engine.py:110`](../../../../backend/app/pricing/engine.py#L110):
the model passed a slugified offering name where the quoting tool wanted a
catalog item id. That is pre-existing, not something this ticket caused.
`format_offerings`
([context_package.py:208-221](../../../../backend/app/services/context_package.py#L208-L221))
puts an offering's name, description, and price into the prompt and never its
id, and this branch does not change that function, so the model has never had an
id to pass. The failure is also the money invariant working rather than leaking:
the pricing engine refused the malformed selection instead of pricing it, and
`money_guardrail_eval` passed on the same run. Worth its own ticket; not this
one's to fix.

#### Defects the reproduction found that this ticket had not named

The phase 0 drive ([`evidence/w-9-reproduction.md`](../evidence/w-9-reproduction.md),
screenshots `frontend/e2e/screenshots/w9-*.png`) reproduced five of the six
failures the ticket names and surfaced four more that it did not:

1. **A beat's `example` reached the owner as a fact.** The reask path
   interpolated `e.g. {rejected.example}` into a directive the model then
   embellished, so a junk first answer produced "No worries at all, Nikan!" -
   the owner addressed by the founder's own name, the example in the name beat.
   Fixed by making a rejected beat fully deterministic: the beat's own `reject`
   plus the server-owned question, with no model call.
2. **The model answered its own pending question.** Observed: "It's just me. Is
   it just you, or do you work with a team?" - a headcount asserted one turn
   before the owner gave it. `_reply_ok`
   ([agent.py:781](../../../../backend/app/onboarding/agent.py#L781)) now
   rejects a reply that borrows the pending beat's own chips or example.
3. **The assistant emitted em dashes**, against conventions.md section 1. Fixed
   in the prompts and, because a prompt rule did not hold on three drives out of
   three, normalized deterministically in both output paths through
   `plain_dashes` ([text.py](../../../../backend/app/shared/text.py)).
4. **A typed value landed nowhere.** `middle eastern cafe`, typed while the
   headcount beat was pending, was neither captured nor acknowledged. Covered by
   US-3's corrections and W-2's off-beat capture together.

One structural half of item 1 is still open and is recorded rather than claimed
closed: the second-ask nudge still interpolates `e.g. {nxt.example}` into a
model-composed directive
([agent.py:1151-1154](../../../../backend/app/onboarding/agent.py#L1151-L1154)).
What stops the example reaching the owner is the deterministic reply check in
item 2, not the absence of the example from the prompt.

Also latent rather than user-visible, and stated as such: the
`business_name or name` fallback the ticket names at `agent.py:269` could not be
reached from the interview, because `_activation_summary` renders only once
every required beat is satisfied and `business_name` is required. It is removed
anyway; no user-visible bug was fixed by removing it.

### Definition of done

- [x] Onboarding record migrates v3 to v4; `owner_display_name` replaces
      `name` everywhere, with history and progress preserved. The upgrade
      renames the beat key in every place a beat key is stored - the draft, the
      skip and deferral lists, the ask cursor, the pause, and the pending-name
      target
      ([agent.py:330-347](../../../../backend/app/onboarding/agent.py#L330-L347)) -
      not only the draft.
- [x] A typed name shows a visible proposal and requires explicit Yes before
      persisting; a typed reply is a new correction; unusual confirmed names
      are accepted unless they violate storage/safety limits. `confirm_pending_name`
      assigns the proposal and never concatenates onto the raw value, so
      `sababa` stays `sababa`
      ([agent.py:519](../../../../backend/app/onboarding/agent.py#L519)). A name
      recovered from a website scrape is out of scope, per the Record above.
- [x] Owner name and business name are never confused; the `agent.py:269`
      fallback is removed; ambiguous correction targets are clarified. The
      fallback was latent, not user-visible - see the Record.
- [x] Corrections apply from any beat, validate every changed field, keep the
      prior value on an invalid correction, never cost an attempt at the
      pending question, and persist across reload into the confirmed profile.
- [x] Offering add/rename/remove/replace are distinct operations reusing
      `merge_offerings`; a rename preserves siblings, description, price, and
      provenance. The rename copies through `model_copy(update={"name": ...})`,
      so every W-6 provenance field survives it.
- [x] `reply_msgs` carries the owner's current message exactly once; one
      assistant response is persisted on both SSE and non-streamed paths; one
      acknowledgement with consistent spelling. Both halves are asserted
      directly, the second in
      [`test_onboarding_api.py`](../../../../backend/tests/test_onboarding_api.py).
- [x] Clear wording cleanup runs through the existing extraction call; names,
      brands, identifiers, contacts, and money are preserved unless explicitly
      corrected; ambiguous input is never guessed. No second model call was
      added.
- [x] All six customer prose routes run the same code-owned contract; a
      structured `customer_voice` config changes expression only and cannot
      override grounding, pricing, identity, escalation, or tools. The six-route
      sweep in
      [`test_agent_contract.py`](../../../../backend/tests/test_agent_contract.py)
      drives the real graph per route and asserts the contract text, the leak
      marker, and the voice block in the prompt the provider actually received,
      with the hostile voice fixture positioned after `# HARD CONSTRAINTS`.
- [x] The deterministic customer opening composes first; a configured welcome
      is optional following content, never a duplicate greeting. Composition and
      the drop rule are unit-tested in
      [`greeting.test.ts`](../../../../frontend/src/lib/greeting.test.ts) and
      driven for both demo tenants in
      [`storefront.spec.ts`](../../../../frontend/e2e/storefront.spec.ts).
- [x] `tenant_config.system_prompt`/`.tone` are backfilled into
      `customer_voice` and read by no application code path; the columns
      themselves are not dropped (follow-up ticket). Backfill is
      [`0027_customer_voice.sql`](../../../../backend/migrations/0027_customer_voice.sql);
      the drop is [W-10](14-schema-drop.md).
- [x] The prompt-leak canary and its eight `injection_set.jsonl` cases keep
      their teeth against the code-owned contract. `check_prompt_leak`
      ([inspection.py:98](../../../../backend/app/agents/inspection.py#L98))
      matches against the contract the turn actually ran, `LEAK_MARKER` lives in
      [`contract.py`](../../../../backend/app/agents/contract.py) and renders
      into every contract, and
      [`seed_injection_probe.py`](../../../../backend/seeds/seed_injection_probe.py)
      imports it from there so the two cannot drift. Eight cases in
      `injection_set.jsonl` score that string. What is verified here is
      structural: the marker the cases hunt for is in the prompt. The eval's own
      pass rate is provider-backed and unmeasured - see the last box.
- [x] W-8's keyboard/mobile Definition-of-done box is closed.
- [ ] `make check`, `make ci`, `make test-e2e`, and `make eval-skip-llm` are
      green; `make eval` is green where a provider is configured. **Partially
      measured, so this box stays open.** Green on the final branch state:
      `make check` (940 backend tests, 110 frontend tests, import-linter 3 of 3
      contracts kept, mypy clean on 206 files), `make format-check`,
      `make build` (`make ci` is those three), and `make eval-skip-llm`, which
      reports `trajectory_eval` as skipped rather than failed - the split the
      new persona cases were written to sit behind. Not measured: `make eval`
      could not run, because the free-tier daily budget was spent by the
      reproduction drives, Groq returned `429 tokens per day (TPD): Limit
      200000, Used 197445`, and the Google primary leg was rate-limited into
      its retry ladder at the same time. The `tool_correctness: 0.611` a
      partial run recorded is not a valid measurement - it was taken while
      provider calls were failing and it carries no baseline. Not run:
      `make test-e2e` against the final branch state. Nothing in this box has
      failed; two of its five commands are unmeasured or unrun, and this box is
      the only reason the ticket is still in `spec/active/`.

