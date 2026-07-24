# Wren Frontend

Next.js 16 + React 19 + TypeScript 5 + Tailwind v4. One app, three surfaces via route groups:

- **Customer chat** at `{slug}.wren.app` - streaming Q&A with citations, quotes, escalation
- **Tenant admin** at `app.wren.app` - onboarding, knowledge, conversations, pricing, dashboards
- **Platform owner** at `admin.wren.app` - all-tenants view, provisioning, suspend/reactivate

All visual values live in `src/styles/theme.css` design tokens (3-layer, CI-enforced by `check:tokens`). Components reference semantic tokens only - never hardcode colors.

## Conventions

See [`frontend/AGENTS.md`](./AGENTS.md) for Next.js-specific agent rules, and [`../AGENTS.md`](../AGENTS.md) at the repo root for the stack, hard rules, and verified commands.

## Running

```bash
# From repo root:
make dev-frontend     # frontend dev server only (:3000)
make dev              # backend + frontend concurrently
make install-frontend # npm ci
make lint-frontend    # ESLint + token guard
make typecheck-frontend # tsc --noEmit
make test-frontend    # vitest
make test-e2e         # Playwright e2e tests
```

See `../docs/DEMO.md` for the full demo walkthrough and `../Makefile` for all targets.
