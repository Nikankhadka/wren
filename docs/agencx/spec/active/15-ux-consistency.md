# 15 - UX consistency: nav tone, button feel, confirmations, toasts

**Status:** built on `feat/ux-consistency` (U-1 through U-4), awaiting founder
review and merge.

Founder request: the mobile tab bar's accent active state and the desktop
sidebars' grey pill were visibly different products. All navs now wear the
mobile accent idiom, every button answers hover and press, destructive
actions ask through one in-app dialog, and mutations report through toasts.

## U-1: one nav idiom

- Shared `navTone()` helper in `components/ui/TabBar.tsx`; tenant sidebar,
  platform sidebar/drawer, and storefront category navs all use it.
- Active is accent text on a 9% accent wash with the filled glyph; inactive
  hover is the same wash. Inactive text is the only per-surface choice, and
  it is a contrast choice (`text-text-secondary` on the light sidebars,
  `text-ink-a40` on the mobile bar).
- `frontend.md` section 7 records the unified idiom (the old deliberate
  divergence is gone).

### Acceptance signal

- [ ] `tab-shell` computed-style test: active Home is `rgba(255, 56, 92, 0.09)`
  / `rgb(180, 0, 78)`; hovered Chats is `rgba(255, 56, 92, 0.07)`.
- [ ] `tab-shell-mobile` computed-style test: active tab is the accent wash.

## U-2: button feel

- One unlayered global rule in `globals.css` restores `cursor: pointer` on
  buttons (Tailwind v4 preflight leaves `default`); per-role hover/active
  idioms everywhere else, semantic tokens only.

### Acceptance signal

- [ ] `make lint` (includes `check:tokens`) and `make typecheck` pass.
- [ ] Keyboard pass: visible focus ring on every button, pointer cursor
  everywhere enabled.

## U-3: confirmations

- New `components/ui/ConfirmDialog.tsx` (`ConfirmDialog` + `useConfirm`),
  built on `Modal` with a `layer` prop for confirms opened over a sheet.
- Destructive removes (offering, media, link, knowledge row, review source,
  non-draft discard), hand-back, and all three sign-outs ask through it.
  Take-over, draft discard, and copy link never ask. `window.confirm` is
  gone (`grep` is empty).

### Acceptance signal

- [ ] `business-hub` Escape test: cancel closes the confirm, no DELETE fires.
- [ ] `auth-login` sign-out, `chats-takeover` hand-back, `settings-knowledge`
  remove all pass through `confirm-accept`.

## U-4: toasts

- `react-hot-toast` (already mounted top-center) for every mutation:
  offering added/saved/removed, link saved/removed, cover updated, knowledge
  saved/draft-ready/replaced/removed/discarded, tenant
  suspended/reactivated. Inline errors remain only for initial loads; field
  validation stays inline.

### Acceptance signal

- [ ] `business-hub`, `settings-knowledge` assert toast text, not roles.
- [ ] `copy-rules` passes on the new confirm and toast copy.
