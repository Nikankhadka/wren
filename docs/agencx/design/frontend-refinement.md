# Agencx Phase 1 Refinement - Frontend Design Spec (v7 prototype)

The design companion to
[HiveAgencyXRefinement.md](../HiveAgencyXRefinement.md). The refinement plan
owns the product decisions; this file owns the UI decisions those decisions
imply. Read it with `frontend.md` (the shipped system this refines) and the v7
prototype (the pixel authority for every screen below).

The UI standard of `design/conventions.md` section 6 applies unchanged: UI is
ported from the prototype, never designed from ticket text; take behaviour,
never strings; every visual value lands in `theme.css` as a token, never a hex
in a component.

## 1. How this document is used

The v7 prototype is
[`prototypes/agencx-prototype-v7.html`](prototypes/agencx-prototype-v7.html),
created beside the preserved v6. Every RF ticket names its screens and states
here and in the prototype; the implementing agent reads both, then builds from
`frontend/src/styles/theme.css` tokens and existing components.

Canonical vocabulary (from the refinement plan, binding in UI copy and code
identifiers): **Business page, offering, preferred name, conversation,
conversation reference, issue, handoff, takeover, handback, resolution, price
summary, and request**. A request awaits business acceptance - it must never
render as a confirmed order or booking, in any state, on either surface.

The four switchable businesses - cafe, retail/repair, dental clinic, and
general clinic - prove the domain-agnostic invariant visually: identical
screens and workflow code, with content, offerings, categories, and knowledge
driven by prototype session config only. The prototype carries a business
switcher so a walkthrough can move between them without reloading a different
build.

## 2. Shared presentation layer (RF-1)

The refinement keeps the shipped design language: Airbnb colour discipline,
white surfaces and cool greys, the Rausch action red (`#FF385C`) with the deep
red text stop and soft red washes, amber/green/teal/red functional statuses,
Plus Jakarta Sans, generous whitespace. D26 superseded D25's Soft Sakura
palette, so the color system follows D26; RF-1 refines structure and does not
rebrand it. Changes must preserve routes and flow order.

- **Typography.** The shipped scale (caption through display, `text-*`
  utilities) stays. Refinement covers hierarchy and rhythm only: consistent
  list-row type pairing (title + meta + preview), consistent sheet headers,
  consistent empty states. Any new type style is a token, not a utility
  invention.
- **Surfaces.** Flat, hairline-separated, `--shadow-1` cards. Refinement
  standardizes the row surface used by Chats, offerings, and business details:
  one row grammar (icon or identity slot, primary line, meta line, trailing
  action) reused across list screens so owner and customer surfaces read as one
  system.
- **Controls.** Existing Button, Input, Textarea, Select, Tabs, Badge, Sheet,
  Modal, Toast, EmptyState, Skeleton keep their required states. Refinement
  adds: the queue filter row (Needs you / All / Human handled), the search
  field, the pagination control, and the split-pane frame. Each is a component
  with the same required-states discipline as the shipped library.
- **Responsive navigation.** Sidebar at `lg+` and bottom tab bar below `lg`
  (Home, Chats, Business) stay exactly as shipped (D18/E-1). The refinement
  adds responsive behavior inside screens: Chats becomes a split pane at `lg+`
  and stays list-then-thread below it (RF-15); the customer chat is a side
  panel at `lg+` and a full-height sheet on mobile (RF-8).
- **Focus and keyboard.** `:focus-visible` ring on every interactive element,
  unlayered ring rules for composite controls (the shipped command pill
  pattern), focus restoration after sheets close, focus moves into the pane
  that opens, scroll position preserved on list return. The prototype
  demonstrates each of these states; the e2e checks them (RF-17).

## 3. Owner surface specifications

### 3.1 Chats - work queue (RF-14, RF-15, RF-16)

The Chats list opens on **Needs you**: unresolved issues and active
human-handled conversations. **All** shows the complete dataset and **Human
handled** the handled subset. All three views share one row component and one
pagination control; filtering, searching, and pagination apply to the complete
conversation dataset (verified with more than 200 conversations, including
older unresolved issues beyond the first page).

One row per conversation, carrying: identity or conversation reference,
attention reason (why it sits in this queue), current handler (assistant,
owner, or human), and waiting time. Attention counts sit beside the tabs so
the owner sees the queue size before entering. The row preview shows the
assistant's own summary of what the customer wants, as shipped.

Thread actions stay distinct and labeled: **takeover**, **reply**, **resolve
issue**, **handback**. Replying or handing back never silently resolves an
issue - resolution is an explicit control with its own confirmation. The
thread shows status stamps for each state, in the shipped stamp idiom
(`thr-pill`). Unanswered questions that the customer does not hand off remain
in All; only an operational failure moves them to Needs you.

Desktop (`lg+`): split pane - list left, thread right, thread opens without
navigation. Mobile: existing list-then-thread navigation, bar preserved.

### 3.2 Business hub and editors (RF-2, RF-3, RF-4, RF-5, RF-7)

The Business hub keeps its three rows - **Business page**, **What you offer**,
**Business details** - with the shipped show-back posture: the owner sees what
the assistant believes and corrects it.

- **Business details editing (RF-2).** Name, hours, description, and business
  contact information become editable after launch, in the same editor-sheet
  idiom as the shipped ABN editor. The public address is a separate field,
  visually distinct from the name, and stays stable when the name changes.
  Saved edits appear immediately on the Business page and in customer answers
  (same-tab, no reload in the prototype).
- **Offerings (RF-3, RF-4, RF-9).** Offerings are searchable and grouped by
  category. Equal prices never merge distinct offerings - each offering is its
  own card regardless of price equality. Two price fields, deliberately
  distinct: a **fixed price** (numeric, calculable) and **pricing wording**
  (owner-confirmed display text such as "from $12 a head"). Wording is
  display-only: no UI state, badge, or calculation ever treats it as a
  calculable amount, and the customer card renders it as display text only.
- **Images (RF-5).** Cover and offering images support upload, preview,
  replacement, and removal, in one workflow with the same states (empty,
  uploading, preview, done, remove). Preview shows the image before
  confirming; removal is explicit, never accidental.
- **Contextual editing (RF-7).** Contextual owner edit shortcuts on the
  Business page open the same editors as the Business hub - one editor per
  field kind, two entry points. Every editor has explicit Save and Cancel.
- **Document review (RF-6).** The workspace is clarified, its semantics
  unchanged: drafts, source evidence, explicit price decisions, replacement,
  retry, and independent publication all behave exactly as shipped.

### 3.3 Home

Unchanged in behavior (greeting plus the brief). Refinement only restyles it
through shared tokens (RF-1); the brief cards continue to surface what wants
the owner right now, now including the queue attention count when Needs you
is non-empty.

## 4. Customer surface specifications

### 4.1 Business page (RF-7, RF-9)

Browse-first composition: cover, business identity, category-grouped
offerings with optional media, price summaries, links - with chat access
clearly labeled, not visually competing with the browsing content. Offering
cards and price-summary cards are realigned to the refined card grammar:
offering card (image, name, category, price or wording, one line), price
summary (deterministic figures only, formatted from cents by `src/lib/money.ts`).

### 4.2 Chat panel and sheet (RF-8)

The customer chat opens into a **desktop side panel** (`lg+`, anchored beside
the page content) and a **full-height mobile sheet** below `lg`. Both show the
conversation header, transcript, and composer. The Business page stays
reachable while the chat is open; the conversation is preserved while
browsing and restored through same-tab refresh (RF-12).

### 4.3 Composer and question behavior

Composer text is never sent automatically. Contextual questions arrive
editable, and existing composed text survives navigation and refresh (RF-13).
Send failures recover in place with the draft preserved - no unsafe automatic
replay; the retry is explicit, in the failed bubble idiom.

### 4.4 Preferred name (RF-10, RF-11)

The assistant answers while asking for a preferred name, at most two name
requests in the opening phase. A first name or nickname is accepted without
verification; no phone number or email is ever collected. The name is shown,
correctable (correction affordance on the header or first message), and
persisted across refresh. After the limit, the prompt stops silently - no
repeat loop.

**Ask for a person** is a visible action in the chat header and composer area.
Customer-requested handoff requires the preferred name; without one the
action explains the one missing thing instead of sending. Refused or
unanswered handoffs leave the conversation in the owner's All view. Internal
operational alerts may still use the conversation reference without a name.

### 4.5 Handoff, takeover, handback, resolution (RF-16)

Customer-facing handoff copy matches the shipped handoff bubble; the
conversation stays live. Owner-side stamps distinguish takeover (the assistant
goes silent, the owner replies), handback (restores the assistant with the
interlude in history), and resolution (explicit, with confirmation). Transcript
consistency across all of these and refresh is an RF-17 check.

## 5. Per-ticket design references

| Ticket | Design reference |
|---|---|
| RF-1 | Section 2 - shared tokens, row grammar, focus rules |
| RF-2 | Section 3.2 - business details editor; Business page show-back |
| RF-3 | Section 3.2 - offering search, category grouping, distinct-offering cards |
| RF-4 | Section 3.2 and 4.1 - fixed price vs pricing wording, both surfaces |
| RF-5 | Section 3.2 - cover and offering image workflow |
| RF-6 | Document review workspace, shipped semantics, clarified only |
| RF-7 | Section 3.2 and 4.1 - Business page composition, contextual edit shortcuts |
| RF-8 | Section 4.2 - desktop side panel, mobile full-height sheet |
| RF-9 | Section 4.1 - offering and price-summary cards |
| RF-10 | Section 4.4 - name capture, correction, prompt limit |
| RF-11 | Section 4.4 - Ask for a person, name-gated handoff |
| RF-12 | Section 4.2 - conversation, cards, and state restored after same-tab refresh |
| RF-13 | Section 4.3 - failed-send recovery, draft preservation |
| RF-14 | Section 3.1 - queue tabs, attention counts, filtering, search, pagination |
| RF-15 | Section 3.1 - desktop split pane, mobile navigation preserved |
| RF-16 | Section 3.1 and 4.5 - explicit resolution in the conversation workspace |
| RF-17 | Every section - four-business walkthroughs, visual and behavioral evidence |

## 6. Prototype rules and verification

- v7 sits beside v6 in `prototypes/`; v6 is preserved unchanged apart from the
  D25 color-only recolor (no layout, copy, interaction, or state changes).
- The prototype owns shared simulated state: offering edits affect the
  Business page; customer handoffs appear in the owner queue; owner replies
  appear in the customer conversation; all of it survives same-tab refresh
  through isolated session state.
- The prototype demonstrates every state a ticket names, including recovery
  states (failed sends, failed uploads, partial processing failures), long
  offerings, missing images, and unpriced items.
- No production API calls: simulated processing and responses only.
- RF-17 records visual evidence (screenshots per state) and behavioral
  evidence (the e2e checks) for all four businesses, and the ledger of what
  was verified where.

## 7. Explicitly out of scope for the UI

Old payment, scheduling, and Copilot screens are excluded from the Phase 1
experience. Owner Copilot, image understanding, galleries, independent
page-pause controls, scheduling, payments, invoices, billing, external
reviews, and account-management additions remain deferred and get no
prototype states in v7. Future request submission and business acceptance are
documented separately and never implied by the request vocabulary above.