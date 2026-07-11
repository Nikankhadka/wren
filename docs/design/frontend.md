# WREN - Frontend Design System & Surface Specs

> **Derived from:** PRD section 2 (three surfaces), MUSTs M16/M17/M18; Architecture Doc section 2. **Precedence:** this file is the implementation truth for UI. The pixel standard of `docs/conventions.md` section 6 applies to everything here.
> Design language: **Anthropic warmth x Apple clarity** - warm paper-like neutrals, one confident terracotta accent, generous whitespace, system typography, restrained depth, no decoration that doesn't earn its place.

---

## 1. The one hard rule of this document: nothing is hardcoded

**No raw color, font, radius, shadow, or duration value ever appears in a component, page, or Tailwind class argument.** Every visual decision routes through CSS custom properties defined in exactly one file: `frontend/src/styles/theme.css`. Changing the entire look of Wren - palette, dark mode, a tenant's branding, a future redesign - must require editing **only that file** (or, at runtime, overriding its variables). 

Three token layers:

```
Layer 1 PRIMITIVES   --sand-50..--sand-900, --clay-300..--clay-700, ...   raw palette, defined once,
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

```css
/* ============ LAYER 1: PRIMITIVES (the only place raw values may live) ============ */
:root {
  /* sand - warm paper neutrals (Anthropic-style ivory ramp) */
  --sand-50:  #FAF9F5;  --sand-100: #F5F3EC;  --sand-200: #EBE8DE;
  --sand-300: #DDD9CB;  --sand-400: #B8B5AA;  --sand-500: #8E8B80;
  --sand-600: #5E5D55;  --sand-700: #3A3935;  --sand-800: #2B2A27;  --sand-900: #1F1E1B;
  /* clay - the terracotta accent ramp */
  --clay-100: #FAEDE6;  --clay-300: #EBA285;  --clay-500: #D97757;
  --clay-600: #C05F3C;  --clay-700: #9D4A2D;
  /* functional ramps (muted, warm-leaning) */
  --green-500: #4E7E5B; --green-100: #E8F0E9;
  --amber-500: #B07C24; --amber-100: #F7EEDC;
  --red-500:   #BC4B3C; --red-100:   #F8E8E5;
  --blue-500:  #5A7D9A; --blue-100:  #E8EEF3;

  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, ui-sans-serif, sans-serif;
  --font-display: "New York", ui-serif, Georgia, serif;   /* headings/hero only, used sparingly */
  --font-mono: ui-monospace, "SF Mono", "Cascadia Code", Menlo, monospace;
}

/* ============ LAYER 2: SEMANTIC (what components use) - LIGHT ============ */
:root {
  --color-bg:             var(--sand-50);
  --color-surface:        #FFFFFF;
  --color-surface-sunken: var(--sand-100);
  --color-surface-raised: #FFFFFF;
  --color-border:         var(--sand-200);
  --color-border-strong:  var(--sand-300);
  --color-text:           var(--sand-900);
  --color-text-secondary: var(--sand-600);
  --color-text-tertiary:  var(--sand-500);
  --color-text-inverse:   var(--sand-50);

  --color-accent:         var(--clay-500);
  --color-accent-hover:   var(--clay-600);
  --color-accent-active:  var(--clay-700);
  --color-accent-subtle:  var(--clay-100);
  --color-focus-ring:     var(--clay-500);

  --color-success: var(--green-500);  --color-success-subtle: var(--green-100);
  --color-warning: var(--amber-500);  --color-warning-subtle: var(--amber-100);
  --color-danger:  var(--red-500);    --color-danger-subtle:  var(--red-100);
  --color-info:    var(--blue-500);   --color-info-subtle:    var(--blue-100);

  --radius-sm: 6px;  --radius-md: 10px;  --radius-lg: 14px;  --radius-full: 9999px;
  --shadow-1: 0 1px 2px rgb(0 0 0 / 0.05);
  --shadow-2: 0 2px 8px rgb(0 0 0 / 0.07);
  --shadow-3: 0 8px 24px rgb(0 0 0 / 0.10);
  --duration-fast: 150ms;  --duration-base: 250ms;
  --ease-out: cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

/* ============ LAYER 2 OVERRIDES - DARK ============ */
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { /* same block as below */ } }
:root[data-theme="dark"] {
  --color-bg:             #262624;
  --color-surface:        #30302E;
  --color-surface-sunken: #1F1E1B;
  --color-surface-raised: #3A3937;
  --color-border:         #45443F;
  --color-border-strong:  #55534C;
  --color-text:           var(--sand-50);
  --color-text-secondary: var(--sand-400);
  --color-text-tertiary:  var(--sand-500);
  --color-text-inverse:   var(--sand-900);
  --color-accent:         var(--clay-300);
  --color-accent-hover:   var(--clay-500);
  --color-accent-subtle:  #4A3327;
  /* functional colors get one lighter step each; shadows drop to borders */
}
```

Exact dark values may be tuned during build - **in this file only**. The light/dark switch is `data-theme` on `<html>` (persisted preference) with `prefers-color-scheme` as the default; components never know which theme is active.

## 3. Tailwind wiring (Tailwind v4)

`frontend/src/app/globals.css` imports `theme.css` and maps semantic tokens into Tailwind utilities via `@theme inline`:

```css
@import "tailwindcss";
@import "../styles/theme.css";

@theme inline {
  --color-bg: var(--color-bg);
  --color-surface: var(--color-surface);
  --color-accent: var(--color-accent);
  /* ...one line per semantic token... */
  --font-sans: var(--font-sans);
  --radius-md: var(--radius-md);
}
```

Components then use `bg-surface`, `text-text-secondary`, `border-border`, `bg-accent`, `rounded-md`, etc. Arbitrary values like `bg-[#D97757]` are what the CI grep forbids.

## 4. Typography, spacing, motion

- **Type scale** (Apple-ish, sizes in px with line-height, defined as tokens in theme.css and exposed as Tailwind `text-caption` ... `text-display` utilities): 12/16 caption, 13/18 footnote, 15/22 body-sm, 17/26 **body (default)**, 20/28 title-3, 24/32 title-2, 28/36 title-1, 34/42 display. Display and title-1 may use `--font-display`; everything else `--font-sans`. Traces, ids, code: `--font-mono` at 13/18.
- **Weight discipline:** regular for prose, medium for labels/buttons, semibold for titles. Never bold-everything.
- **Spacing:** 4px base grid - allowed steps 4, 8, 12, 16, 24, 32, 48, 64, 96. Section padding defaults: cards 24, page gutters 32 (16 on mobile), stack gaps 16.
- **Depth (Apple deference):** flat by default; `--shadow-1` for cards, `--shadow-2` for popovers, `--shadow-3` for modals only. In dark mode depth comes from surface steps, not shadows.
- **Motion:** `--duration-fast` for hover/press, `--duration-base` for enter/exit; `--ease-out` everywhere; everything honors `prefers-reduced-motion` (transitions collapse to instant). Streaming text does not animate per-token beyond the browser default reflow - no typewriter gimmicks.

## 5. Per-tenant branding (runtime, data-driven - the domain-agnostic rule in UI form)

`tenant_config.brand` (see database.md section 3) carries at most: `{"accent": "#RRGGBB", "display_name": "...", "logo_url": "..."}`.

- Surface 3's server layout fetches the resolved tenant's brand and injects a scoped override: `<style>:root{--color-accent:{validated};--color-accent-hover:{derived};--color-accent-subtle:{derived};--color-focus-ring:{validated};}</style>`.
- The backend validates `accent` as a hex color at write time; the frontend derives hover/active/subtle steps from it (simple HSL lightness shifts in one utility, `src/lib/brand.ts`) and falls back to the default clay ramp if contrast against `--color-surface` fails WCAG AA (4.5:1 for text-on-accent).
- Logo and display name render in the chat header. That is the entire branding surface at core scope - no per-tenant CSS, no per-tenant components, ever.

## 6. Component library (`frontend/src/components/ui/`)

Build these once, use everywhere; every component takes only semantic tokens. Each lists its required states - the pixel standard applies to all of them.

| Component | Variants / notes | Required states |
|---|---|---|
| `Button` | primary (accent bg), secondary (surface + border), ghost, destructive; sm/md | default, hover, active, focus-visible ring, disabled, loading (spinner replaces label, width stable) |
| `Input`, `Textarea`, `Select` | label above, help/error text below | default, focus, error (danger border + text), disabled |
| `Card` | surface + border + radius-lg + shadow-1; optional header/footer | default, interactive (hover raise) |
| `Table` | admin data tables; sticky header, row hover | loading (skeleton rows), empty (EmptyState inside), error |
| `Badge` | status pill; maps every status vocabulary in database.md -> functional tokens: info = open/sent; warning = escalated/claimed/processing/provisioning; success = resolved/closed/active/ready; danger = failed/suspended; neutral = pending/draft/expired | n/a |
| `Tabs` | underline style, accent indicator | active, hover, focus |
| `Modal` / `Sheet` | shadow-3, scrim `rgb(0 0 0/0.4)`; Sheet for mobile | open/close transition, focus trap |
| `Toast` | bottom-right, auto-dismiss, functional-token left edge | success/error/info |
| `EmptyState` | icon + one-line explanation + primary action; never a bare "No data" | n/a |
| `Skeleton` | shimmer off in reduced-motion | n/a |
| `MetricCard` | big number + label + delta; dashboards | loading, empty ("no data yet" + why), error |
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
- **Dashboards** (T-034): MetricCards - cost today/this month (cost_logs), conversations, escalation rate; latest eval run metrics (from eval_runs) with pass/fail vs thresholds; each card has real empty/loading states.
- **Settings**: brand editor (accent color input with live preview + contrast warning, display name, logo URL), escalation threshold slider, tone.

### 7.3 Surface 1 - Platform owner (`admin.wren.app`)

Deliberately minimal, protected by `platform_admins` membership: one Tenants page - Table (name, slug, status badge, created, conversations count, cost) + "Provision tenant" modal (name + slug with availability check) + suspend/reactivate row actions (confirm modal for suspend). Aggregate MetricCards on top (tenants, total cost). Nothing else at core scope.

## 8. Accessibility & quality bar

- WCAG AA contrast on every token pair used together (checked once, in theme.css review, plus the runtime brand check in section 5).
- Full keyboard navigation; `:focus-visible` ring (`--color-focus-ring`, 2px offset 2px) on every interactive element; focus traps in modals.
- `aria-live` for streaming and toasts; labeled form fields; table semantics.
- Responsive: all admin tables collapse gracefully at 768px (horizontal scroll within the card, never the page); chat is mobile-first.
- The `docs/conventions.md` section 6 standard applies: if a screen looks off while you're in there - fix it in the shared component/token, not with a local patch.

*End of frontend design. Screens not specced here don't exist at core scope - if a ticket seems to need one, flag it.*
