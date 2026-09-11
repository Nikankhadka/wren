# Agencx - Frontend Design System and Surface Specs

The implementation truth for UI. The pixel standard of
`docs/agencx/design/conventions.md`
section 6 applies to everything here. Design language: **Airbnb colour
discipline** - white surfaces and cool greys, a **Rausch red action colour**
(the CTA gradient for text-bearing primary buttons, the deep red stop for text
actions) with amber, green, teal and red functional statuses, generous
whitespace, Plus Jakarta Sans throughout (D17 name and font, D26).

The system below is the shipped Wren frontend carried forward; the Agencx
changes are the three-screen manifest (S1/S2/S3), the font swap, the Airbnb
color system (D26, superseding D25), the failover typing indicator (P-5), and
the mobile-first app chrome (D18). The pre-Agencx prototype's teal accent,
cleaning copy, and Hivee emblem stay retired and archived (D17); its
mobile-first structure returns as the tenant app's bottom tab bar (D18).
D26's teal is the info status role, not a return of that identity accent.

## 1. The one hard rule: nothing is hardcoded

**No raw color, font, radius, shadow, or duration value ever appears in a
component, page, or Tailwind class.** Every visual decision routes through CSS
custom properties in exactly one file: `frontend/src/styles/theme.css`.
Changing the whole look means editing only that file. Per-tenant color
overrides are no longer a runtime path (D25).

Three token layers:

```
Layer 1 PRIMITIVES   --primary-20..--primary-95, --neutral-6..--neutral-100...   raw palette, defined once,
                                                                                  referenced ONLY by layer 2
Layer 2 SEMANTIC     --color-bg, --color-text, --color-accent...                 what components are allowed to use
Layer 3 COMPONENT    --button-primary-bg, --chat-bubble-user-bg...               optional; only when a component deviates
```

Rules:

1. Components and pages reference **semantic or component tokens only** - never
   primitives, never raw values.
2. Hex/rgb/hsl literals are allowed **only** in `theme.css`. A CI check
   (`frontend/scripts/check-tokens.mjs`, `npm run check:tokens`) fails the build
   if a color literal appears anywhere else under `src/`. It machine-enforces
   colors; the rest of rule 1 is enforced in review.
3. Dark mode (currently disabled) and any future theme are **variable
   overrides**, never component changes; tenant branding is name and logo only,
   not a color override (D25).

## 2. Theme file (`frontend/src/styles/theme.css`)

Layer 1 is a Material 3 tonal ramp set: each role (primary Airbnb red,
secondary teal, tertiary green, error red, amber, neutral) is a ramp of tone
steps (higher number = lighter); Layer 2 picks a tone per role. Dark-mode
overrides are disabled; any future theme is a variable override, never a
parallel component palette.

The primary ramp is rebuilt around the Airbnb identity (D26):
`--primary-40:#FF385C` is the action red, `--primary-35:#E31C5F` hover,
`--primary-30:#B4004E` pressed, and `--primary-90:#FFD1DA` the soft brand
fill. The D17 font change stands:

```
--font-sans: var(--font-plus-jakarta, ...sans-serif);
```

wired via `next/font/google` Plus Jakarta Sans in `layout.tsx` (replacing Inter;
`display: "swap"`). Component code is untouched - the color swap is a re-point
of tokens, the same load-bearing pattern the Wren rebrand proved.

**Colour convention (action accent + semantic status colours).** Deep red
(`text-accent-active`, `#B4004E`) is the **brand action** colour and carries
interactive text: links, text actions, chips, focus rings, and the sender
label on a human-agent bubble. Flat Rausch (`--color-accent`, `#FF385C`) never
carries text (3.52:1 on white) - it fills icon-only controls (send circles,
the storefront FAB, the thinking dots) and its gradient (`bg-brand`, all stops
clear 4.5:1 with white) fills text-bearing primary buttons and the BrandMark
monogram. The soft red wash (`#FFD1DA`, and the accent-a06/a07/a09 alpha
washes) is the brand surface: chips, selected filters, human-agent bubbles,
the Business page cards, and accent containers. None of these is used for a
*status* meaning. Status is expressed with the standard semantic ramp, routed
through the semantic tokens (Layer 2) and the `Badge` `STATUS_TONE` map:

- **Green** (`--color-success`, `#007A04` on `#E6F5E7`): approved, success,
  complete, paid, ready, resolved, active, delivered, confirmed.
- **Red** (`--color-danger`, `#C13515` on `#FDEDEA`): cancelled, declined,
  failed, suspended, rejected, refunded, error.
- **Amber** (`--color-warning`, `#8A5A00` on `#FFF3D6`): pending, warning,
  overdue, in-progress, provisioning, processing, claimed, escalated,
  outstanding. `--color-highlight` (`#FFB400` with dark ink) is the count and
  notification fill, never a warning text colour.
- **Neutral / info** (grey, or `--color-info` - `#007A7F` on `#E6F4F5` -
  where a distinct info colour is wanted): open, sent, draft, neutral - any
  status without a clear good/bad/pending charge. Teal is the info status
  role only, never a link colour.

When a screen needs a status the component maps the status string to a tone via
`toneForStatus` (Badge.tsx) - never a hardcoded hex. Unknown/tenant-defined
statuses fall back to neutral, which is the honest answer for a word the map has
never seen. `toneForStatus` normalises case and separators, so one entry
(`in_progress`) answers the schema's spelling, this doc's hyphenated one, and a
tenant's "In Progress" - three keys for one concept is how one of them silently
goes grey. **Shipped is amber, not green**: on its way is not arrived, and the
customer waiting is the one who would notice. **Landed in B-3.**

**The one red-dot exception, and why it is not a status (B-3).** The Chats list
marks a conversation being handled with a red dot and one that wants the
owner with amber (`.bdot-t` / `.bdot-a` in the prototype, where `--c-teal` is a
legacy name holding the brand value). That looks like it contradicts the rule
above, and does not: "we have this one" carries no good/bad/pending charge - it
is the brand saying it is present, the same role red plays in the send circle.
Green would be wrong for a live conversation, since green means resolved.
Nothing else may borrow the action red for a status.

**Airbnb palette - SHIPPED (D26, supersedes Soft Sakura D25).** The brand
action is `#FF385C` (Rausch), with hover `#E31C5F` and active/pressed
`#B4004E`; subtle and accent-container are the soft red `#FFD1DA`, which pairs
with `text-accent-active` (deep red on soft red), not `text-inverse`. The text
stack is Airbnb's cool grey `#222222` / `#717171` / `#767676`. Flat `#FF385C`
is a fill-only colour: text-bearing CTAs ride `--gradient-brand`
(`#E61E4D -> #E31C5F -> #D70466`) and text actions use `text-accent-active`.
D26 also retires the per-tenant accent override (section 5).

**The alpha ladder (O-5; re-pointed by D26).** The prototype expresses every
soft surface as one hue at an alpha step, so `theme.css` carries two channel
triples - `--primary-40-rgb` (now `255 56 92`, Rausch) and `--neutral-10-rgb`
(now `34 34 34`) - and derives a ladder from them:
`--color-accent-a07/09/12/16/20/28/45/50` and
`--color-ink-a05/07/12/35/40`. These are named by alpha step rather than by role
because the prototype reuses each step in several places; a numeric name stays
honest where an invented role vocabulary would not. Only steps a shipped screen
uses are defined - add one when a screen needs it, never speculatively.
`--color-accent-a09` is the tab/action pill wash, no longer the opening veil
(the veil is `--gradient-veil`, the soft blush wash with its top stop at zero
alpha so the 56%-height overlay has no hard seam, D26). Note that
`--color-ink-a40` (the prototype's `--c-muted`) is what thread surfaces use for
muted text, NOT the grey `--color-text-tertiary`.

**Thread tokens (O-5).** The onboarding thread's type (`--text-lede`,
`--text-lede-q`, `--text-bubble`), geometry (`--radius-bubble-lg`,
`--space-thread-*`, `--size-send*`, `--size-code-cell-*`, `--width-thread`) and
motion (`--duration-rise-fast`, `--duration-veil`) are all prototype values. Some
gaps are deliberately off the 4px grid (14px, 18px) - where the prototype and
the grid guidance in section 4 disagree, the prototype wins.

**Tailwind v4 has no `--duration` namespace.** `duration-fast` is not a real
utility and silently does nothing; the form that reads a token is
`duration-(--duration-fast)`. `--animate-*` IS a namespace, so named animations
(`animate-rise`, `animate-beat-in`) are declared in `globals.css` and used
directly.

**Dark mode is disabled.** No `:root[data-theme="dark"]` block and no
`prefers-color-scheme` media block ship; `theme.css` points at git history for
the old palette and says light mode only (D25). Re-enabling is a deliberate
change, not a derivation.

## 3. Tailwind wiring (Tailwind v4)

`frontend/src/app/globals.css` imports `theme.css` and maps semantic tokens into
Tailwind utilities via `@theme inline` - self-referential mappings
(`--color-x: var(--color-x)`), the `theme.css` import stays **unlayered**. Both
are load-bearing. Components use `bg-surface`, `text-text-secondary`,
`border-border`, `bg-accent-container`, `rounded-md`, etc. Arbitrary values like
`bg-[#FF385C]` are what the CI grep forbids.

## 4. Typography, spacing, motion

- **Type scale** (M3-derived, exposed as `text-caption` ... `text-display`
  utilities): 12/16 caption, 13/18 footnote, 14/20 body-sm, **16/24 body
  (default)**, 18/28 body-lg, 18/26 title-3, 22/28 title-2, 32/40 title-1,
  48/56 display. Components reference the semantic `text-*` names; re-pointing
  these tokens is the single largest visual lever. Everything uses
  `--font-sans`; traces/ids/code use `--font-mono` at 13/18.
- **Radii:** 8 / 12 / 16 / full.
- **Weight discipline:** regular for prose, medium for labels/buttons, semibold
  for titles. Weight 700+ is reserved for hero/marketing display only.
- **Spacing:** 4px base grid - allowed steps 4, 8, 12, 16, 24, 32, 48, 64, 96.
  Card padding 24, page gutters 32 (16 mobile), stack gaps 16.
- **Depth:** flat by default; `--shadow-1` for cards, `--shadow-2` for
  popovers, `--shadow-3` for modals. Dark mode uses surface steps, not shadows.
- **Motion:** `--duration-fast` hover/press, `--duration-base` enter/exit;
  `--ease-out` everywhere; honors `prefers-reduced-motion`.

## 5. Per-tenant branding (name and logo only, D25)

`tenant_config.brand` still carries at most `{"accent": "#RRGGBB",
"display_name": "...", "logo_url": "..."}`. `accent` stays accepted, stored and
returned for compatibility, but it renders nothing: the color override is
retired and `src/lib/brand.ts` no longer exists. The backend never validated
the hex - the field was always free-form data, and the frontend was the only
thing that read it.

- Display name and logo render in the chat header. That is the entire branding
  surface - no per-tenant CSS, no per-tenant components, no per-tenant color.
- Console, platform and customer surfaces all use the same locked palette.

## 6. Component library (`frontend/src/components/ui/`)

Every component takes only semantic tokens. Each lists its required states.

| Component | Notes | Required states |
|---|---|---|
| `Button` | primary (rides the CTA gradient `bg-brand`, brightness hover) / secondary / ghost / destructive; sm/md | default, hover, active, focus ring, disabled, loading |
| `Input`, `Textarea`, `Select` | label above, help/error below; white field with a visible border, focus darkens the border to ink (D26); the inactive send state is the only validation signal - no red error text | default, focus, error, disabled |
| `CommandPill` | `command` (send circle appears with text) and `field` (circle always present, dimmed until valid) variants; the pill carries the focus ring, never a rectangle inside it; `.pill-plus` opens the file picker where attaching is offered (O-3) | empty, typing, armed, busy/stop, disabled, attach |
| `Card` | surface + border + radius-lg + shadow-1 | default, interactive |
| `Table` | sticky header, row hover | loading, empty, error |
| `Badge` | status pill; maps every status vocabulary to a tone (info=open/sent, warning=escalated/claimed/processing/provisioning, success=resolved/closed/active/ready, danger=failed/suspended, neutral=pending/draft/expired) | n/a |
| `Icon` | vendored Material Symbols Outlined SVG, `fill="currentColor"`, `name` -> path registry | n/a |
| `Tabs` | underline style, accent indicator | active, hover, focus |
| `Modal` / `Sheet` | shadow-3, scrim; Sheet for mobile | open/close, focus trap |
| `ConfirmDialog` | the app's one confirmation dialog, built on `Modal` (`useConfirm` for promise-style use); destructive removes, hand-back, and sign-out ask through it - `window.confirm` is banned | default, danger, working |
| `Toast` | top-center, auto-dismiss, functional-token edge; text only, no celebration | success/error/info |
| `EmptyState` | icon + one-line explanation + primary action; never bare "no data" | n/a |
| `Skeleton` | shimmer off in reduced-motion | n/a |
| `MetricCard` | bento stat card: big number + label + optional icon/trend/footer | loading, empty, error |
| `Sparkline` | dependency-free inline-SVG polyline, strokes `currentColor` | n/a |
| `ScreenTopbar` (O-3) | `.dst-topbar`: 58px, back control, title, optional trailing action, hairline rule | default |
| `RowLink` (O-3) | `.bh-row`: icon, label, chevron, hairline - a hub screen's list of destinations | default, pressed |
| `FileDropzone` | drag target; accepted PDF, DOCX, MD/TXT/CSV/JSON. **Images are refused** - nothing in the stack reads one (no OCR, no vision call), founder ruling 2026-08-22; a vision call on the provider seam is the upgrade path | idle, drag-over, uploading, done, rejected |
| `ChatBubble` | the OPERATOR thread idiom, all roles on bubble tokens: customer (brand red `bubble-out`, right), assistant (neutral `bubble-in`, left), human_agent (soft red `bubble-agent-in`), system (centered caption); 18px radius, tip at the top | static, streaming |
| `Thread` (O-5) | the ONBOARDING thread idiom, a separate design: `Thread`, `LedeMessage`, `AgentLine` (bare prose), `OwnerBubble` (20px, tip bottom-right), `TypingLine`, `ThreadPill`, `ThreadVeil`. Never merge with `ChatBubble` | static, streaming, pending |
| `StreamingText` | renders SSE tokens, `aria-live="polite"` | streaming, done, interrupted |
| `TypingIndicator` | **NEW (P-5):** three pulsing dots (600-800ms) shown while a turn is in flight, sustained through the failover window - never a spinner, never a blank | active |
| `CitationChip` | inline `[1]` chip; popover shows source + snippet | default, hover |
| `QuoteCard` | renders **pricing-engine output verbatim**; money formatted from integer cents in `src/lib/money.ts` - no arithmetic in components | default, sent |
| `TraceTree` | collapsible run tree (console only), mono font | loading, error, empty |
| `EscalationBanner` | in-chat handoff state | active |

## 7. Surface specs

One Next.js app (App Router), one origin, surfaces separated by path (D22):
`(tenant-admin)/` serves the apex and the console routes (`/login`, `/home`,
`/chats`, ...), `admin/` is the platform at `/admin`, and `[slug]/` is the
customer page at `/{slug}` - the app's only dynamic top-level segment, which
catches everything the static routes do not. There is no host middleware; the
customer page reads `params`. Shared shell: `bg-bg`, max-width content column,
`text-text` body.

### S0 - Home (tenant app tab 1) - the greeting and the brief

Where the owner lands after go-live, and the first of three tabs (D21). Home is
the owner's own thread with the assistant, headed by a time-of-day greeting from
the O-1 profile, and carrying **the brief**: the small set of things that want
the owner right now, each a card with the one action that resolves it.

Ported from `#greeting` / `#greeting-h1` and `showMorningBrief()` /
`addCard(hl, chips, note)` in `agencx-prototype-v6.html`. `addJobRows()` is not
ported - jobs are Stage 2 and there is nothing behind them.

**Item kinds in Stage 1 (shipped, E-4)**, each rendered only when its state is
real: customers waiting on the owner (`/api/conversations`, `needs_attention`),
knowledge waiting to be saved (`/api/knowledge/records`, `status = draft` - a
draft answers nothing until saved, D19), and the share nudge. Stage 2's quote
and order approvals arrive as further kinds in the same list, never as new
screens.

**"Not shared yet" is derived, not tracked.** The nudge shows while the tenant
has no conversations at all - a customer having written is the only proof the
link reached anyone, and it needs no column to record it.

**The brief is composed on the client**, in `home/lib/brief.ts`, from the two
endpoints that already serve this state - two queries is not a reason to build a
route. `BriefItem` is the contract Stage 2 promotes to a single `/api/brief`
when the kind count grows; the change is then server-side only. Both queries
must have answered before composing, because an empty conversation list is the
share nudge's trigger and composing early flashes a card that is about to be
wrong.

**No composer, deliberately.** The prototype's home carries one, and Stage 1
does not: `POST /api/onboarding/message` 409s once onboarding is confirmed and
no everyday owner-Copilot route replaces it. An affordance that errors on every
send is worse than an absent one; the composer waits for the backend that
answers it.

| State | Spec |
|---|---|
| Nothing waiting | The greeting and the thread, nothing else. Never a "you're all caught up" card - absence is the message |
| Items waiting | Cards in the thread, most-urgent first: headline, action chip(s), one context note line |
| Loading | No skeleton for the brief - a card that appears a beat late is better than a grey box that promises one |

### S1 - Chats (tenant app tab 2) - login-in-chat, interview, the customers' threads

The product opens into a conversation, not a home screen. The first
conversation IS the product.

- **Login-in-chat (NEW, O-2):** the owner types an email in the command pill;
  send activates on valid email format (no error text). A 6-digit code is sent
  to that address; six digit cells replace the input footprint (auto-focus
  first cell, numeric keyboard on mobile), auto-submit on six valid digits. One
  line echoes the destination with a "Wrong email?" affordance; resend is
  inactive for 60 seconds with no visible countdown; wrong-code/expired/
  max-attempts each get one calm line. Duplicate email sends the code regardless
  (no account-existence leak); success silently continues. No toast, no
  celebration.
- **Interview:** the same conversation continues as the onboarding interview
  (name, business name, business type, headcount, hours, what they sell).
  Business type drives questions from config, never code (I8). Once those seven
  fields are captured the assistant offers a website/documents ask (paste a
  link, attach a file, or say "skip") - optional, one word to decline, and it
  never gates go-live; the confirm button appears after it is answered.
- **Everyday chat: NOT in Stage 1.** This spec used to say the Chat tab holds
  the Copilot conversation after go-live. It does not, and no route answers
  one: `POST /api/onboarding/message` returns 409 once onboarding is confirmed
  (`features/onboarding/controller.py`), and nothing replaces it. Home
  therefore ships without a composer (S0) rather than with one that errors on
  every send. Deferred by founder ruling (2026-08-22); revisit after Stage 1
  reports back, since a running conversation with the owner about their own
  business belongs with Stage 2's back-office story.

The thread is the progress indicator: no progress bars, no "% complete"
anywhere. After go-live the app has exactly three tabs: Home, Chats and
Business (D21), and `/onboarding` sends an already-live owner on to Home.

**Shipped shape (O-5).** Both halves of this conversation - `/login`
(login-in-chat) and `/onboarding` (the interview) - render on the shared
primitives in `frontend/src/components/ui/Thread.tsx`, ported from the
prototype's ONBOARDING screen. The thread IS the screen: `/onboarding` renders
chrome-free (no sidebar, no hamburger header), there is no title, and there is no
progress surface of any kind. Assistant turns are bare prose; only the owner's
turns get a bubble. A soft blush veil (`#s1-grad`) sits over the bottom 56%
and fades for good once the owner has answered once.

`Thread.tsx` is deliberately NOT `ChatBubble`: the operator thread's two-bubble
idiom (18px radius, tip at the top) and the onboarding thread's idiom (bare prose
plus a 20px owner bubble tipped bottom-right) are different designs in the
prototype. Do not unify them.

**Phase 13, W-3 (planned, `13-walkthrough.md`):** the onboarding composer and
pending states are refined without changing this idiom - text-input
placeholders become empty by default (label plus the in-thread question remain
the context carriers), the composer's baseline height is stabilized across
beat changes while typed growth is kept, the thinking-dots row becomes the sole
pending indicator (the "Answering…" status line is removed; the status line
becomes the error slot only), and a processing upload animates in the existing
motion vocabulary with an explicit success or failure and a recovery path. No
fabricated percentage progress and no queues/workers/background polling are
added. Typed answers use SSE; chip, resume, and upload use ordinary requests -
proven by a browser network trace.

**Email in a chat composer (O-5; extraction moved client-side 2026-08-28, D23).**
The client gate on the login pill is *liveness only* - it arms the send circle
when the text contains something address-shaped, so "it's sam@shop.com" is
sendable. The same regex plus a trailing-punctuation trim (`(tenant-admin)/
login/page.tsx::extractEmail`) is now also the extraction step: GoTrue is the
real validator, exactly like every other OTP flow - a bad address either never
looks address-shaped enough to submit, or gets GoTrue's own rejection, mapped
to one calm conversational line the thread renders verbatim. The typed text
stays put so it can be corrected. Deliverability is not checked - the code
itself is that test, and "Wrong email?" is already on screen. (The old
authority, `backend/app/services/email_address.py`, is deleted - GoTrue never
consulted it, so there was no reason to keep porting its stricter RFC checks
forward.)

| State | Spec |
|---|---|
| Resolving tenant | full-page skeleton; no flash of default branding while the tenant resolves |
| Login / no valid session | chat surface present with the agent's first message already rendered - no welcome screen |
| Opening message | held behind the typing indicator for 820ms, then revealed as the lede - static messages are paced like streamed ones (section 9). Never re-paced for restored history |
| Bad email typed | one calm line under the composer from the server; typed text kept |
| Streaming | StreamingText in assistant bubble; TypingIndicator up while the turn is in flight (through the failover window, P-5); composer disabled with "answering..." hint; stop button |
| Handed off (C-5) | A topic went to a human. Handoff bubble, **composer stays live**, next message gets a full turn. The human-reply poll starts here |
| Handled by a human (C-6) | Staff took the conversation over. The customer's messages are stored and reach the owner's thread; the assistant stays silent, the composer stays live |
| Escalated (limit only) | A tenant limit ended the conversation - EscalationBanner replaces the composer; conversation stays readable. Since C-5 no agent path reaches this state |
| Error / disconnect | inline retry in the failed bubble, never a blank screen |
| Drop-off / return | full history renders from server (last 20 turns), scrolled to the most recent message; input state matches the in-progress beat |

**The owner's side of the same surface (C-6).** `/chats` (list) and
`/chats/[id]` (thread) are where the business reads its customer conversations
and steps into them. Ported from the prototype's `chats` and `renderThreadScreen`
screens: the **All / Action needed / Unread** filter row, where "Action needed"
*is* the escalation queue; `chat-row` with name, relative time, a status dot
(amber = the assistant asked for you, red = it is handling this) and a
one-line preview that shows the assistant's own summary of what the customer
wants; and in the thread, the "Handling" / "You're replying" status with the
take-over and hand-back pills and their symmetrical `thr-pill` stamps. Built on
`ChatBubble` with `perspective="operator"`, which mirrors which side is
outbound - never on `Thread.tsx`. Chrome-free until E-1's tab bar re-homes both.

### S2 - Business (tenant app tab 3) - show-back of profile + knowledge

**Three rows since M-4** (`/business`): **Business page** (`/business/page` -
cover, name, the share link, platform tiles, the compact offering summary, and
a preview link out to the storefront), **What you offer**
(`/business/offerings` - the offerings editor), and **Business details**
(`/business/details` - knowledge, ABN and tax). `/business/booking` and
`/settings` are gone as paths rather than aliased: two routes rendering one
screen drift, and four E2E specs had already been written against the pair.

The Business tab displays the profile and knowledge the owner gave the agent -
what the assistant believes about the business, and the uploaded material it
answers from - so the owner can trust and correct it. Editable through the
Copilot ("change my rate to $160"), never through settings forms. No
configuration that exists only as a toggle.

The thin, product-required exceptions: the share link and the **enabled-tools
toggle (D-3)** - the per-tenant on/off for recommendations / quoting / order
lookup that implements tool gating (PRD section 8). These are scope, not
settings-tree creep (decision 7).

The "live / not live" indicator that used to head that list is **void**, ruled
2026-08-23 while closing E-5. There is no not-live state to show: `tenants.status`
defaults to `active`, self-signup inserts `active`, and onboarding confirm never
touches it - so the indicator would read "Live" through the whole interview.
What "live" means for a self-onboarded tenant is `config->onboarding.completed`,
which is already true by the time the owner can open the screen. `tenants.status`
is a platform-admin lifecycle (suspend / reactivate), not an owner-facing one.

**Shipped shape (E-5).** Business is a hub of `.bh-row`s
(`renderScreen('business')`) holding **Business page**, **What you offer**, and
**Business details**.
Schedule, Money and Plan are the prototype's Stage 2 rows and are absent, not
disabled. The Booking page (`renderScreen('booking')`) shows the business name,
a clamped one-line description built from the O-1 profile's services and hours,
and the public link with a copy control - the address derived from the current
host via `surfaceUrl()`, never hardcoded, and shown without its scheme or
trailing slash while the whole URL is what gets copied.

**E-6 completed the screen** (founder walkthrough, 2026-08-23). The three parts
E-5 left out now ship, because something stands behind each of them:

- **The cover photo.** O-3's refusal of images is about *knowledge* - nothing
  reads an image for text - and a brand asset is not knowledge, so the two
  rulings do not collide. New covers use the signed Cloudinary adapter and are
  delivered from their public CDN URL. Legacy `tenant_assets` bytes remain
  readable during rollout and are migrated by the count-verified one-off
  script. Resized client-side on a `<canvas>` before upload; the API cap is the
  backstop.
- **The platform tiles** are link slots, not integrations: the owner's own
  Website/Google/Facebook/Instagram addresses, stored in `tenant_config.brand
  ->links`. Tapping a tile opens a panel - it never navigates on the tap, which
  had left no way back to a link already saved. Schemes are allowlisted server
  side; these render as links a customer clicks.
- **Offerings** are the owner's structured `offerings` rows, created, edited
  and retired from **Business > What you offer** (`/business/offerings`).
  M-4 moved them off this screen entirely: the customer's storefront renders
  them and the owner reaches it through the "Preview your business page" link,
  so the owner's screen carries no second read-only copy to drift. Removing an
  offering clears `active` rather than deleting the row, so a past quote that
  refers to it still resolves. A price is the owner's own typed decimal,
  validated at the API boundary and stored as integer cents; the page formats
  cents to dollars and does no other arithmetic. Catalog chunks stay out of
  general-knowledge fast paths, and recommendations re-fetch the authoritative
  row before stating a price.
- **About** remains in `tenant_config.brand->storefront` for reversibility, but
  the owner editor and public storefront do not expose or render it. It is
  presentation, not knowledge, and the assistant never answers from it.

**The QR is gone** (E-6). It was never in the prototype's owner screen - it came
from the storefront's share sheet - and the founder does not use it. With it
went the `qrcode-generator` dependency and the `BarcodeDetector` e2e. Sharing is
the native `navigator.share()` with a clipboard fallback, which lists the apps
the owner actually has rather than a hardcoded four-icon row.

**The "Get a quote" CTA does not ship.** Quoting is a per-tenant opt-in that is
off by default (D-1/D-2).

**Current storefront shape:** the page a customer lands on
(`(customer)/page.tsx`) is the compact catalogue described below. It leads with
the business identity, optional cover, categorized offerings, links, and one
header chat action; the assistant opens in a sheet when requested.

The knowledge half now lives at **Settings > Knowledge** (`/settings/knowledge`,
O-3 / D19) and is not a document table: a source is processed into fixed readable
sections the owner corrects, held as a draft until they save it. E-1 re-homed
this screen inside the shell: it is reached from the Business hub's Settings
row, and the Business tab stays lit while the owner is inside it.

**Settings holds a second row from O-9: ABN & Tax.** The interview asks for an
ABN and a GST registration (O-6); this is where they are read back
(`51 824 753 556 · GST registered`) and corrected, in the prototype's
`openSettingsEdit('abn')` sheet. It is not the start of a settings tree - the
other seven profile fields are still written once, at confirm, and have no
editor. The digits are what is stored; grouping them is the screen's job, done
by `lib/abn.ts`, which is the same function the interview's masked pill uses.
GST is a chip pair rather than the prototype's toggle: the same question the
interview asks, with the control the interview asks it with.

| State | Spec |
|---|---|
| Empty | One line plus the two ways in (paste a link, add a document); no table, no type picker |
| Reading | The `.proc-txt` line naming the work ("Reading your site...") while a source is fetched and processed |
| Review (draft) | Bottom sheet: the sections as editable text, Save / Discard. Nothing answers a customer until Save |
| Active | Each source shown as its sections, with its own status line; edit reopens the sheet |
| Failed | The reason in place, plus retry (re-runs the ingest over the stored text) |
| Tool toggles | Enabled-tools section (D-3); toggling updates `tenant_config.enabled_tools` |

**Phase 13, W-8 (`13-walkthrough.md`):** the shared review sheet presents a
read-first document. Offerings appear first, initially capped at five cards
with a total, and "Review all N" opens a five-per-page editor keyed by stable
candidate identity. Editing, additions, removals, and duplicate decisions stay
in one review state, so Save sends every retained offering rather than only the
visible page. A possible duplicate remains separate unless its owner selects
"Keep both" or confirms a previewed combine, with an explicit price choice for
a conflict. Business overview, hours, location, and named other-information
subsections render as document content and edit inline. Saved sources use the
same expandable renderer. Original extracted source is an owner-only,
on-demand region, never customer retrieval. No rich-text editor dependency or
replacement wizard is used.

### S3 - Public page (anonymous, per-tenant slug)

Centered column (max ~720px), tenant logo + display name header. No auth. The
share link is how a customer gets here (E-6 removed the QR).

**M-4 made this a storefront, not just a chat.** It had been a message list and
a composer, which meant a customer arriving from a shared link had to know what
to ask before the page told them anything. The page now leads with the business:
optional cover, name and tagline, **what we offer** (the owner's `offerings`,
with categories, optional media, and the owner's own price when they published
one), and the links. Legacy About data is preserved but not exposed or rendered.
The assistant is a tap away in the existing sheet from one header action, "Ask a
question"; the rest of the storefront remains informational.

The address is the owner's own: M-4 lets them choose it at go-live rather than
keeping the provisional `biz-…` slug (see `11-offerings-media.md` M-4 US-3).
**Phase 13, W-4 (planned):** every path that reaches confirmation - initial
load, ordinary answers, optional-knowledge skip, review save, review discard,
and reload - provides the suggested address; invalid, reserved, and taken
slugs are actionable field errors (including the backend's own validation
remaining authoritative); a business-name correction refreshes the suggestion
only until the owner edits the address; and network failures preserve the
entered address so a retry succeeds without restarting onboarding.

| State | Spec |
|---|---|
| Resolving tenant | Full-page centered skeleton; no flash of default branding |
| Unknown slug | Calm 404: "There's no business here." |
| Neither active nor suspended | `provisioning` has no storefront to read; falls back to the bare chat rather than an empty page |
| Suspended tenant | "This page is currently unavailable." caption, composer hidden. Says nothing about why - a customer is not owed the tenant's billing state (PRD 13; the wording also carried "assistant" until B-3's E-3 sweep) |
| Empty conversation | Tenant-configured greeting as the first assistant bubble; starter chips if configured |
| Streaming | StreamingText in assistant bubble; TypingIndicator through the failover window (P-5); composer disabled with "answering..." hint; stop button |
| Citations | CitationChips on grounded sentences |
| Escalated (limit only) | EscalationBanner replaces composer-state messaging; conversation stays readable |
| Error / disconnect | Inline retry in the failed bubble, never a blank screen |

### Tenant console shell (nav re-cut, E-1/E-2)

Nav re-cut to **Home**, **Chats** and **Business** (E-1, D21) - the sidebar at
`lg+`, the bottom tab bar below it. The advanced Wren screens (Conversations
with traces, Dashboards, Escalations, Pricing) are removed from the tenant nav
but their routes and code remain (E-2), reachable by the platform owner until
Stage 2 re-lands them. Platform admin stays minimal (E-3): one Tenants page
(list, suspend/reactivate) plus aggregate metrics; tenant pre-provisioning was
removed (see progress.md's Platform-owner surface row) since self-onboarding
was already the only claim path that worked.

**Which tab owns which route.** A drill-down does not have to live under its
tab's URL, so a nav item can carry an `owns` list of extra prefixes.
Settings was the one user of it, hanging off the Business hub at `/settings`;
M-4 moved that screen to `/business/details` and the list is empty again. The
mechanism stays, because the next drill-down that lands outside its tab's
prefix needs it. `isTabActive()` in
`components/ui/TabBar.tsx` is exported and used by *both* renderings: if the
sidebar and the bar computed this separately they could disagree, and the wrong
one is whichever the owner is looking at.

**A tab destination has no back control.** `ScreenTopbar` takes `back={false}`
and renders the prototype's bare 36px spacer instead - both variants are in
`agencx-prototype-v6.html`. Drill-downs (`/chats/[id]`, `/settings`,
`/settings/knowledge`) keep theirs.

### Mobile-first app chrome (tenant app, D18)

The tenant app is mobile-first: below `lg` the three-tab manifest renders as an
app-style surface with a persistent **bottom tab bar** - Home, Chats and
Business as bottom tabs (D21); at `lg+` the left sidebar stays (E-1). One
codebase, responsive; no native app, no PWA shell in Stage 1.

- Tab bar: icon + label per tab, minimum 44px touch target, ~64px height plus
  `env(safe-area-inset-bottom)` padding for home-indicator devices. The bar is
  64px but the tab inside it is a 48px pill inset 8px vertically and 24px
  horizontally - that inset is what makes the active state read as a pill
  rather than a full-height block, and it is easy to lose
- Active tab: **accent text on a 9% accent wash** (`bg-accent-a09 text-accent-active`)
  with the filled Material Symbol; inactive: `text-ink-a40` with the outlined
  glyph. This is the prototype's `.tab.active`, and it is the one nav idiom
  everywhere: the tenant and platform sidebars and the storefront category nav
  wear the same wash through the shared `navTone()` helper
  (`components/ui/TabBar.tsx`), differing only in their inactive text - the
  light sidebars use `text-text-secondary`, which is the AA choice on their
  background, while the bar keeps the prototype's muted tone
- The bar is **persistent, including over drill-downs**: in the prototype
  `#screen-layer` is z-index 20 and stops 64px short of the bottom while
  `#tabbar` is 21, so a pushed screen never covers the bar
- Unread dot (`#ndot`): anchored to the tab's glyph, not to the bar, so it
  stays put at any tab count. Driven by the same `needs_attention` the Chats
  "Action needed" filter uses, so the two cannot disagree
- The hamburger Drawer is no longer the tenant app's mobile nav; it stays
  available to the platform surface (E-3)
- Brand header stays compact on mobile; sign-out is reachable, never hidden
- Structural reference: the reworked prototype
  (`docs/agencx/design/prototypes/agencx-prototype-v6.html`) is trusted for
  screen inventory, states, interaction vocabulary, and the bottom tab bar
  pattern, now carrying the shipped Airbnb identity, the monogram mark, and
  the Sababa reference tenant (D17, D18, D25). The companion storefront surface
  (`docs/archive/prototypes/agencx-storefront-customer-v3.html`) is a retired pre-D18 surface kept for
  storefront interaction vocabulary only

## 8. SSE event contract

| Event | When emitted | Subscribed surfaces update |
|---|---|---|
| `onboarding_beat_completed` | A capture beat promotes to confirmed | Business tab (show-back surface) |
| `escalation_triggered` | Agent escalates to tenant | Chat thread, EscalationBanner |
| `failover_engaged` | Primary timed out, fallback raced (never customer-visible text) | Tracing/cost attributes only; the indicator keeps animating |

**`turn_started` was specified and is not built (P-5).** The client raises the
indicator on send, which is strictly earlier than any server event could arrive
- a `turn_started` frame would only ever confirm something already on screen.
The row is removed rather than left as a promise.

**The indicator, and what may not interrupt it (P-5).** `ThinkingDots` is up
from send until the first inspected token: `CustomerChat` pushes
`{streaming: true, text: ""}` on send, and `StreamingText`'s `pending` renders
the dots whenever a streaming message has no text yet. Three consequences worth
stating, because each is a way the continuity could be lost by accident:

- **`progress` never touches the bubble.** A stage label belongs in the
  `aria-live` region under the composer; in the bubble it would read as a
  half-answer.
- **P-2's provider race is invisible by construction.** The losing leg is
  cancelled server-side and nothing about the switch is streamed, so a slow
  primary is indistinguishable from a slow answer. There is nothing to hide,
  which is why there is no code here - only a test that no provider,
  failover or switching vocabulary reaches the customer.
- **`redraft` returns to the dots deliberately.** The price gate rejected the
  streamed draft, so the rejected sentence is cleared and the assistant is
  visibly thinking again - a retracted half-answer left on screen would be
  worse than the wait.

## 9. Interaction rules (load-bearing)

- **No welcome screen, no progress bars, no celebration.** The thread is the
  progress indicator.
- **Typing indicator before static messages** - conversational pacing must feel
  consistent from the first beat; the indicator must never stop mid-turn to
  reveal a provider switch (P-5, pinned by `e2e/typing-indicator.spec.ts`).
- **Confirmation-card pattern** for every action that touches money or
  customer-facing records (Stage 2; Stage 1 has no autonomous writes).
- **No undo bar** - the confirmation card covers the same ground.
- **No raw structured data in user-facing output** - JSON, XML, markdown tables,
  or code blocks never render in chat. Parse and present through UI components,
  or show an honest fallback message.
- **Natural-language summaries only** - lists use conversational framing ("Here's
  what I know:"), never bullet points or markdown.
- **No impersonation** - every agent identifies as an assistant acting on behalf
  of Agencx, never as the business owner or as human.

## 10. Accessibility and quality bar

- WCAG AA contrast on every token pair, pinned by the theme contract test (`src/styles/theme.test.ts`)
- Full keyboard navigation; `:focus-visible` ring on every interactive element;
  focus traps in modals
- `aria-live` for streaming and toasts; labeled forms; table semantics
- Responsive: admin tables collapse gracefully at 768px (horizontal scroll
  within the card); the tenant app is mobile-first (bottom tab bar below `lg`,
  D18); chat is mobile-first; minimum touch target 44px
- Tab bar: `aria-current` on the active tab, visible labels on every tab,
  keyboard navigation, safe-area padding honored
- The `docs/agencx/design/conventions.md` section 6 standard applies: if a screen looks off
  while you're in there - fix it in the shared component/token, not with a local
  patch
