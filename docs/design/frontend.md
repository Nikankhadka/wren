# WREN - Frontend Design System & Surface Specs

> **Derived from:** PRD section 2 (three surfaces), MUSTs M16/M17/M18; Architecture Doc section 2. **Precedence:** this file is the implementation truth for UI. The pixel standard of `docs/conventions.md` section 6 applies to everything here.
> Design language: **Material 3 tonal clarity** (the "LuxeStay" rebrand) - warm-leaning neutrals, a confident crimson primary with teal and green as functional accents, generous whitespace, Inter throughout, M3 surface layering, restrained depth, no decoration that doesn't earn its place.

---

## 1. The one hard rule of this document: nothing is hardcoded

**No raw color, font, radius, shadow, or duration value ever appears in a component, page, or Tailwind class argument.** Every visual decision routes through CSS custom properties defined in exactly one file: `frontend/src/styles/theme.css`. Changing the entire look of Wren - palette, dark mode, a tenant's branding, a future redesign - must require editing **only that file** (or, at runtime, overriding its variables). 

Three token layers:

```
Layer 1 PRIMITIVES   --primary-20..--primary-95, --neutral-6..--neutral-100, ...   raw palette, defined once,
                                                                          referenced ONLY by layer 2
Layer 2 SEMANTIC     --color-bg, --color-text, --color-accent, ...        what components are allowed to use
Layer 3 COMPONENT    --button-primary-bg, --chat-bubble-user-bg, ...      optional, only when a component
                                                                          needs to deviate; references layer 2
```

Rules:

1. Components and pages reference **semantic or component tokens only** - never primitives, never raw values. This covers colors, font sizes/leading (use the `text-*` utilities from the type-scale tokens), radii, shadows, and durations alike.
2. Hex/rgb/hsl literals are allowed **only** in `theme.css`. A CI check (`frontend/scripts/check-tokens.mjs`, wired as `npm run check:tokens`) fails the build if a color literal appears in any other file under `src/`. The check machine-enforces colors only; the rest of rule 1 is enforced in review.
3. Dark mode, tenant branding, and any future theme are **variable overrides**, never component changes.

## 2. Theme file skeleton (`frontend/src/styles/theme.css`)

Layer 1 is a **Material 3 style tonal role ramp** set: each role (primary crimson, secondary teal, tertiary green, error, neutral, neutral-variant) is a ramp of tone steps (higher number = lighter), and Layer 2 selects a tone per role and per theme rather than owning any raw value. This is what makes dark mode a systematic derivation (pick a lighter tone of the same ramp) instead of a hand-picked parallel palette.

```css
/* ============ LAYER 1: PRIMITIVES (the only place raw values may live) ============ */
:root {
  /* primary - crimson, the brand accent ramp */
  --primary-20: #67001B;  --primary-30: #870027;  --primary-35: #A1002F;
  --primary-40: #BA0036;  --primary-45: #E21E4A;  --primary-60: #E14A69;
  --primary-70: #F76F86;  --primary-80: #FFB2BC;  --primary-90: #FFD9DC;  --primary-95: #FFECEE;
  /* secondary - teal (info role) */
  --secondary-30: #004F53;  --secondary-40: #00696D;  --secondary-80: #4DD9E2;  --secondary-90: #8EEFF4;
  /* tertiary - green (success role) */
  --tertiary-30: #00522F;  --tertiary-40: #006A45;  --tertiary-45: #008558;
  --tertiary-80: #57DFA2;  --tertiary-90: #C2F2DA;
  /* error - red (danger role) */
  --error-30: #93000A;  --error-40: #BA1A1A;  --error-80: #FFB4AB;  --error-90: #FFDAD6;
  /* amber - warm warning ramp (kept from the prior system) */
  --amber-100: #F7EEDC;  --amber-300: #D9B36A;  --amber-500: #B07C24;
  /* neutral - surface + text stack (warm-leaning greys), light + dark steps */
  --neutral-100: #FFFFFF;  --neutral-98: #FCF9F8;  --neutral-96: #F6F3F2;  --neutral-94: #F0EDED;
  --neutral-92: #EAE7E7;   --neutral-90: #E5E2E1;  --neutral-10: #1B1C1C;
  --neutral-6: #141313;   --neutral-8: #1B1919;   --neutral-12: #211F20;  --neutral-17: #2B2929;
  --neutral-22: #363334;  --neutral-30: #4A4646;  --neutral-80: #C9C6C5;
  /* neutral-variant - secondary/tertiary text + strong borders */
  --neutral-variant-30: #5C3F41;  --neutral-variant-50: #906F70;  --neutral-variant-80: #D8C2C3;

  --white: #FFFFFF;
  --scrim: rgb(0 0 0 / 0.4);

  --font-sans:    var(--font-inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ui-sans-serif, sans-serif);
  --font-display: var(--font-inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ui-sans-serif, sans-serif);
  --font-mono:    ui-monospace, "SF Mono", "Cascadia Code", Menlo, monospace;
}

/* ============ LAYER 2: SEMANTIC (what components use) - LIGHT ============ */
:root {
  --color-bg:                     var(--neutral-98);
  --color-surface:                var(--neutral-100);
  --color-surface-sunken:         var(--neutral-96);
  --color-surface-raised:         var(--neutral-100);
  --color-surface-container:      var(--neutral-94);   /* NEW - bento/sidebar fill */
  --color-surface-container-high: var(--neutral-92);   /* NEW - icon chip / raised fill */
  --color-border:                 var(--neutral-90);
  --color-border-strong:          var(--neutral-variant-50);
  --color-text:                   var(--neutral-10);
  --color-text-secondary:         var(--neutral-variant-30);
  --color-text-tertiary:          var(--neutral-variant-50);
  --color-text-inverse:           var(--neutral-100);

  --color-accent:                 var(--primary-40);
  --color-accent-hover:           var(--primary-35);
  --color-accent-active:          var(--primary-30);
  --color-accent-subtle:          var(--primary-90);
  --color-accent-container:       var(--primary-45);   /* NEW - filled nav pill; pairs with text-inverse */
  --color-focus-ring:             var(--primary-40);

  --color-success: var(--tertiary-40);  --color-success-subtle: var(--tertiary-90);
  --color-warning: var(--amber-500);    --color-warning-subtle: var(--amber-100);
  --color-danger:  var(--error-40);     --color-danger-subtle:  var(--error-90);
  --color-info:    var(--secondary-40); --color-info-subtle:    var(--secondary-90);

  --radius-sm: 8px;  --radius-md: 12px;  --radius-lg: 16px;  --radius-full: 9999px;
  --shadow-1: 0 1px 2px rgb(0 0 0 / 0.05);
  --shadow-2: 0 2px 8px rgb(0 0 0 / 0.07);
  --shadow-3: 0 8px 24px rgb(0 0 0 / 0.10);
  --duration-fast: 150ms;  --duration-base: 250ms;
  --ease-out: cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

/* ============ LAYER 2 OVERRIDES - DARK (two blocks, kept literally identical) ============ */
:root[data-theme="dark"] {
  --color-bg:                     var(--neutral-6);
  --color-surface:                var(--neutral-12);
  --color-surface-container:      var(--neutral-17);
  --color-surface-container-high: var(--neutral-22);
  --color-text:                   var(--neutral-90);
  --color-accent:                 var(--primary-80);
  --color-accent-container:       var(--primary-70);   /* near-black on #F76F86 ~6.16:1 AA */
  /* ...every other Layer 2 token re-pointed one lighter tone; functional subtles
     become color-mix(<tone-40> 22%, var(--neutral-12)); shadows drop to borders... */
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]):not([data-theme="dark"]) {
    /* the SAME body as the [data-theme="dark"] block above, verbatim */
  }
}
```

The three new tokens - `--color-surface-container`, `--color-surface-container-high`, and `--color-accent-container` - carry the M3 surface layering and the filled nav pill; each is added in **both** theme.css and the `@theme inline` map (section 3).

**The two dark blocks must stay literally identical.** `src/lib/brand.ts` scopes a tenant's runtime accent override to light mode only, and it relies on the `[data-theme="dark"]` rule and the `prefers-color-scheme` media query carrying the exact same token body - drift between them would silently break dark mode for one entry path but not the other. A header comment in theme.css states this ("edit both or neither"); treat it as load-bearing, not documentation. Exact tone choices may still be tuned during build - **in this file only**. The light/dark switch is `data-theme` on `<html>` (persisted preference) with `prefers-color-scheme` as the default; components never know which theme is active.

## 3. Tailwind wiring (Tailwind v4)

`frontend/src/app/globals.css` imports `theme.css` and maps semantic tokens into Tailwind utilities via `@theme inline`:

```css
@import "tailwindcss";
@import "../styles/theme.css";

@theme inline {
  --color-bg: var(--color-bg);
  --color-surface: var(--color-surface);
  --color-surface-container: var(--color-surface-container);            /* NEW */
  --color-surface-container-high: var(--color-surface-container-high);  /* NEW */
  --color-accent: var(--color-accent);
  --color-accent-container: var(--color-accent-container);              /* NEW */
  /* ...one line per semantic token... */
  --font-sans: var(--font-sans);
  --text-body-lg: var(--text-body-lg-size);                            /* NEW step + its --line-height */
  --radius-md: var(--radius-md);
}
```

The rebrand added `--color-surface-container`, `--color-surface-container-high`, `--color-accent-container`, and the `body-lg` type step (plus the display/title-1/caption `--letter-spacing` suffixes) to this map, in lockstep with theme.css. The mappings remain **deliberately self-referential** (`--color-x: var(--color-x)`) and the `theme.css` import remains **unlayered** - both are load-bearing per the NOTE comment in globals.css, and neither the new tokens nor any future ones should move the import into a Tailwind `@layer`. Components then use `bg-surface`, `bg-surface-container`, `text-text-secondary`, `border-border`, `bg-accent-container`, `rounded-md`, `text-body-lg`, etc. Arbitrary values like `bg-[#BA0036]` are what the CI grep forbids.

## 4. Typography, spacing, motion

- **Type scale** (M3-derived, sizes in px with line-height, defined as tokens in theme.css and exposed as Tailwind `text-caption` ... `text-display` utilities): 12/16 caption (+0.05em tracking), 13/18 footnote, 14/20 body-sm, **16/24 body (default)**, 18/28 body-lg (NEW - hero ledes and marketing prose), 18/26 title-3, 22/28 title-2, 32/40 title-1 (-0.01em tracking), 48/56 display (-0.02em tracking). Since components only ever reference the semantic `text-*` utility names, re-pointing these token values was the single largest, lowest-risk lever of the whole rebrand - nothing in component code changed. Everything uses `--font-sans`; `--font-display` maps to the same Inter family (the old serif display face is retired). Traces, ids, code: `--font-mono` at 13/18.
- **Font loading:** Inter is loaded via `next/font/google` in `src/app/layout.tsx` (variable font exposed as `--font-inter`, `display: "swap"`, class on `<html>`), and both `--font-sans` and `--font-display` fall back to it. The first build needs network access once to cache the font files.
- **Radii:** `--radius-sm/md/lg` are 8px / 12px / 16px (up from 6/10/14); `--radius-full` unchanged. The bump reads as the softer M3 card language.
- **Weight discipline:** regular for prose, medium for labels/buttons, semibold for titles. Weight 700+ is reserved for hero/marketing **display** use only - never for console body, labels, or data. Never bold-everything.
- **Spacing:** 4px base grid - allowed steps 4, 8, 12, 16, 24, 32, 48, 64, 96. Section padding defaults: cards 24, page gutters 32 (16 on mobile), stack gaps 16.
- **Depth (Apple deference):** flat by default; `--shadow-1` for cards, `--shadow-2` for popovers, `--shadow-3` for modals only. In dark mode depth comes from surface steps, not shadows.
- **Motion:** `--duration-fast` for hover/press, `--duration-base` for enter/exit; `--ease-out` everywhere; everything honors `prefers-reduced-motion` (transitions collapse to instant). Streaming text does not animate per-token beyond the browser default reflow - no typewriter gimmicks.

## 5. Per-tenant branding (runtime, data-driven - the domain-agnostic rule in UI form)

`tenant_config.brand` (see database.md section 3) carries at most: `{"accent": "#RRGGBB", "display_name": "...", "logo_url": "..."}`.

- Surface 3's server layout fetches the resolved tenant's brand and injects a scoped override: `<style>:root{--color-accent:{validated};--color-accent-hover:{derived};--color-accent-subtle:{derived};--color-focus-ring:{validated};}</style>`.
- The backend validates `accent` as a hex color at write time; the frontend derives hover/active/subtle steps from it (simple HSL lightness shifts in one utility, `src/lib/brand.ts`) and falls back to the default primary ramp if contrast against `--color-surface` fails WCAG AA (4.5:1 for text-on-accent).
- Mechanics are unchanged by the rebrand: the tenant accent override simply replaces the default crimson `--color-accent` (and its hover/active/subtle steps and focus ring) on the customer surface **only**, gated by the same WCAG AA contrast check - the console and platform surfaces always keep the crimson primary.
- Logo and display name render in the chat header. That is the entire branding surface at core scope - no per-tenant CSS, no per-tenant components, ever.

## 6. Component library (`frontend/src/components/ui/`)

Build these once, use everywhere; every component takes only semantic tokens. Each lists its required states - the pixel standard applies to all of them.

| Component | Variants / notes | Required states |
|---|---|---|
| `Button` | primary (accent bg), secondary (surface + border), ghost, destructive; sm/md | default, hover, active, focus-visible ring, disabled, loading (spinner replaces label, width stable) |
| `Input`, `Textarea`, `Select` | label above, help/error text below | default, focus, error (danger border + text), disabled |
| `Card` | surface + border + radius-lg + shadow-1; optional header/footer | default, interactive (hover raise) |
| `Table` | admin data tables; sticky header, row hover | loading (skeleton rows), empty (EmptyState inside), error |
| `Badge` | status pill; maps every status vocabulary in database.md -> functional tokens: info = open/sent; warning = escalated/claimed/processing/provisioning; success = resolved/closed/active/ready; danger = failed/suspended; neutral = pending/draft/expired. Renders as an uppercase `text-caption` (caption tracking) `rounded-full` pill - no arbitrary values; `toneForStatus` maps a raw status string to a tone | n/a |
| `Icon` | `frontend/src/components/ui/Icon.tsx`; vendored Material Symbols Outlined SVG paths (Apache 2.0, attribution in header), `viewBox="0 -960 960 960"`, `fill="currentColor"` (so no color literal ever reaches the token guard), `name` -> path registry, `size` prop, optional `filled` variant for the 7 nav icons, `aria-hidden` by default | n/a |
| `Tabs` | underline style, accent indicator | active, hover, focus |
| `Modal` / `Sheet` | shadow-3, scrim `rgb(0 0 0/0.4)`; Sheet for mobile | open/close transition, focus trap |
| `Toast` | bottom-right, auto-dismiss, functional-token left edge | success/error/info |
| `EmptyState` | icon + one-line explanation + primary action; never a bare "No data" | n/a |
| `Skeleton` | shimmer off in reduced-motion | n/a |
| `MetricCard` | bento stat card - big number + label, plus optional `icon` (top-right accent chip), `trend` ({direction: up/down/flat, label} with a matching trend glyph, display-only - never computes a delta), and a `footer` slot (e.g. a Sparkline on a wide card); `rounded-lg border bg-surface p-6 shadow-1 hover:shadow-2`. Backward compatible with the label/value/loading/error API | loading, empty ("no data yet" + why), error |
| `Sparkline` | `frontend/src/components/ui/Sparkline.tsx`; dependency-free inline-SVG polyline (optional low-opacity area fill) on a fixed 100x28 viewBox stretched via `preserveAspectRatio="none"`; strokes `currentColor` under a `text-accent` wrapper (no color literal), `role="img"` + computed `aria-label`, flat/empty series render a baseline (no divide-by-zero) | n/a |
| `FileDropzone` | drag target, accepted types from ticket | idle, drag-over, uploading (per-file progress), done, rejected (reason) |
| `ChatBubble` | roles: customer (accent-subtle bg, right), assistant (surface, left), human_agent (info-subtle, labeled), system (centered caption) | static, streaming (see below) |
| `StreamingText` | renders SSE tokens; caret pulse while open; `aria-live="polite"` | streaming, done, interrupted (retry affordance) |
| `CitationChip` | inline `[1]`-style chip after cited sentences; popover shows chunk source + snippet | default, hover/popover |
| `QuoteCard` | renders **pricing-engine output verbatim**: line items (label, qty, unit, line total), subtotal/tax/total rows; money formatted from integer cents in exactly one utility `src/lib/money.ts` - no arithmetic in components, ever (deterministic-pricing rule in UI form) | default, sent badge |
| `TraceTree` | collapsible run tree: supervisor -> node -> tool calls (name, args, latency, success); mono font | loading, error, empty |
| `EscalationBanner` | in-chat handoff state: "A human will take it from here" + position/status | active |

## 7. Surface specs

All three surfaces are one Next.js app (App Router). Route groups: `(platform)` -> admin.wren.app, `(tenant-admin)` -> app.wren.app, `(customer)` -> `{slug}.wren.app`, resolved by host middleware (T-005). Shared shell: `bg-bg`, max-width content column, `text-text` body.

### 7.1 Surface 3 - Customer chat (`{slug}.wren.app`) - the showpiece

Single screen, centered column (max 720px), tenant logo + display name header, message list, composer pinned bottom.

| State | Spec |
|---|---|
| Resolving tenant | full-page centered skeleton; no flash of default branding before brand loads (brand is injected server-side) |
| Unknown slug | calm 404: "There's no business here." - no Wren upsell at core scope |
| Suspended tenant | "This assistant is currently unavailable." caption, composer hidden |
| Empty conversation | tenant-configured greeting from `tenant_config` as first assistant bubble; 2-3 suggested starter chips if configured (data-driven) |
| Streaming | StreamingText in assistant bubble; composer disabled with subtle "answering..." hint; stop button |
| Quote in reply | QuoteCard beneath the assistant text |
| Citations | CitationChips on grounded sentences |
| Escalated | EscalationBanner replaces composer state messaging; conversation stays readable |
| Error / disconnect | inline retry affordance in the failed bubble, never a blank screen |

### 7.2 Surface 2 - Tenant admin console (`app.wren.app`)

Left sidebar nav (icons + labels): **Onboarding, Knowledge, Conversations, Escalations, Pricing, Dashboards, Settings**. Content area with title-2 page headers. Auth required; tenant scope from membership.

- **Onboarding** (T-006, T-031): the Copilot chat (same chat components as Surface 3) that interviews the business and writes config; right-side live summary panel showing captured fields (identity, tone, services, rules, threshold) with a confirm step. States: fresh, in-progress (resume), confirmed/live.
- **Knowledge**: FileDropzone + documents Table (filename, doc_type badge, status badge, uploaded). Failed rows show the error and a retry action. Empty state explains what to upload.
- **Conversations**: list (customer_ref, started, status badge, message count) -> detail: full transcript with ChatBubbles + per-message TraceTree drill-down (tool calls, latency, cost). Filter by status.
- **Escalations**: queue Table (reason, conversation link, age, status) with claim/resolve actions; resolving posts a `human_agent` message option. Empty state: "Nothing needs you right now."
- **Pricing**: pricing_rules Table with inline editor (code, label, amount as currency input stored as cents, unit, active toggle) + catalog_items list. Banner note: "Changes apply to new quotes only." Validation errors inline.
- **Dashboards** (T-034, **built**): `(tenant-admin)/(console)/dashboards/page.tsx` - a bento grid of MetricCards (cost today with a trend vs yesterday, cost this month vs prev month, avg cost/conversation, conversations, escalation rate) plus a full-width 30-day card whose footer hosts a Sparkline; below it an eval section (one row per run_type: pass/fail Badge, per-check chips of value-vs-threshold, git_sha, timestamp). Two independent `apiFetch` loads (costs + evals) with per-section loading skeletons and error/retry; money is formatted in a local `formatUsd` for display only (never `money.ts`, which is the integer-cents quote path). Empty states are honest - a fresh tenant with no `eval_runs` sees an explanation, not a blank panel.
- **Settings**: brand editor (accent color input with live preview + contrast warning, display name, logo URL), escalation threshold slider, tone.

### 7.3 Surface 1 - Platform owner (`admin.wren.app`)

Deliberately minimal, protected by `platform_admins` membership: one Tenants page - Table (name, slug, status badge, created, conversations count, cost) + "Provision tenant" modal (name + slug with availability check) + suspend/reactivate row actions (confirm modal for suspend). Aggregate MetricCards on top (tenants, total cost). Nothing else at core scope.

### 7.4 Marketing surface (apex host `wren.app` / `localhost:3000`)

Public, login-free content served from `app/marketing-surface/` (route groups can't segment `/`, so `proxy.ts` rewrites marketing paths into this real segment, same pattern as `admin-surface/`). Server components using the `headers()` + `surfaceUrl()` idiom so every cross-surface link is derived from the request host; per-page `export const metadata`. Shared nav shell (wordmark, Product/Pricing/Demo/About, "Business sign in" + "Get started" pill). Copy rule: real mechanics only - no invented metrics, customers, or testimonials. The landing page (`page.tsx`) keeps its asserted h1 and deep links verbatim; four content pages sit behind the nav:

- **`/product`** ("One agent, three front doors."): walks the customer chat, tenant console, and platform console, then a bento of the four load-bearing properties (cited answers, deterministic quotes, human escalation, domain-agnostic by construction) and an honest "under the hood" band (traces, cost accounting, eval gates).
- **`/pricing`** ("Simple pricing, still in beta."): an explicit beta banner (free while in beta, tiers illustrative until launch), three tier cards differentiated on real mechanics, an "every plan includes" strip, and an FAQ (anchor ids kept non-hex-looking, e.g. `#faq-billing`, so the token guard never mistakes one for a color literal).
- **`/demo`** ("See it working in ten minutes."): always-on, mirrors the `docs/DEMO.md` persona walkthrough (customer / business owner / platform operator) with the public demo credentials and a "why two tenants" domain-agnostic band; degrades calmly if the demo world isn't seeded.
- **`/about`** ("Built to be trusted"): the real trust mechanics - RLS + dedicated app role and CI-gated leakage test, the three-layer deterministic-pricing explanation, the escalation model, and eval suites as CI gates - stated without puffery or invented numbers.

## 8. Accessibility & quality bar

- WCAG AA contrast on every token pair used together (checked once, in theme.css review, plus the runtime brand check in section 5).
- Full keyboard navigation; `:focus-visible` ring (`--color-focus-ring`, 2px offset 2px) on every interactive element; focus traps in modals.
- `aria-live` for streaming and toasts; labeled form fields; table semantics.
- Responsive: all admin tables collapse gracefully at 768px (horizontal scroll within the card, never the page); chat is mobile-first.
- **Known gap (flagged, not a rebrand regression):** the shared console shell's left sidebar (tenant-admin and platform surfaces, built in T-031/T-033 and structurally untouched by the rebrand) does not collapse into a mobile drawer below ~375px - the content column visually squeezes and clips at narrow viewports on every console page. It is pre-existing, not introduced here, and the 375px e2e overflow check passes because content clips rather than overflowing the page; it still looks wrong. Per the "architecturally consequential changes get flagged, not silently decided mid-build" convention, this is recorded rather than patched in-place: it wants a dedicated future ticket (a responsive console-shell chunk adding a hamburger/drawer pattern), not a local fix.
- The `docs/conventions.md` section 6 standard applies: if a screen looks off while you're in there - fix it in the shared component/token, not with a local patch.

*End of frontend design. Screens not specced here don't exist at core scope - if a ticket seems to need one, flag it.*
