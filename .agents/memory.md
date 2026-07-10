# Project Memory

## Decisions
<!-- YYYY-MM-DD: <decision> - why: <reason> -->
- 2026-07-10: Documentation restructured into a phase-routed system (docs/INDEX.md is the entry point; design/ + phases/ are the working truth, Wren_*.md are frozen sources) - why: keep per-session context small so later phases can be executed by smaller models.
- 2026-07-10: All frontend visual values live in frontend/src/styles/theme.css as 3-layer tokens; components use semantic tokens only, enforced by `npm run check:tokens` - why: founder requirement that colors are never hardcoded and stay easy to change; also enables per-tenant runtime branding.
- 2026-07-10: Backend Python pinned to 3.12 (.python-version) - why: GenAI deps in later phases (RAGAS, torch cross-encoders) lag on newest Python versions.
- 2026-07-10: tenant_id denormalized onto messages and tool_calls; orders given a generic shape (ref_code/kind/status/details); quotes immutable-except-status via trigger - why: direct RLS, domain-agnosticism, no retroactive quote changes (docs/design/database.md, flagged and approved in planning).
- 2026-07-10 (T-002): quote protection strengthened slightly beyond database.md's sample trigger - id/created_at also frozen, and wren_app holds no DELETE on quotes (revoked; FK cascades still work because they run as the table owner) - why: principle 5 "tamper-proof once sent" taken literally after review.
- 2026-07-10 (T-002): wren_resolver gets column-level grants only (tenants: id/slug/name/status; tenant_config: tenant_id/brand) - why: the privilege boundary of the single sanctioned RLS bypass must match resolve_tenant_slug's four-column contract, so a future resolver-owned function cannot widen the pre-auth surface.

## Gotchas
<!-- <thing that will bite you> - <what to do instead> -->
- Supabase's `postgres` role owns tables and would bypass RLS - every tenant table needs FORCE ROW LEVEL SECURITY and the API must connect as the dedicated `wren_app` role (docs/design/database.md section 2).
- Next.js 16 in frontend/ has breaking changes vs training data - read `frontend/node_modules/next/dist/docs/` before writing frontend code (see frontend/AGENTS.md).
- backend tests import `app.*` via `pythonpath = ["."]` in pyproject's pytest config - don't convert the app into an installed package without updating this.
- The migration runner substitutes `${VAR}` into SQL literals fail-closed: values must be 8+ chars with no quotes/backslashes/dollar signs, and `change-me`/empty is rejected - generated DB passwords must respect that charset (app/core/migrate.py `_SAFE_VALUE_RE`).
- Postgres roles are cluster-global: 0002_roles.sql guards `create role` with if-not-exists checks so the wren_test database can be migrated in the same cluster; the wren_app password is set by whichever database migrates first.
- pytest-asyncio: session-scoped async fixtures need `@pytest_asyncio.fixture(scope="session", loop_scope="session")` and must yield plain data only (tests run on per-function loops - a yielded connection would be bound to the wrong loop).
- psql-based RLS experiments must wrap `set_config(..., true)` and the queries in one `begin/commit` - autocommit makes transaction-local settings vanish per statement and everything looks denied.
- `tenant_context` (app/core/db.py) is the ONLY place tenant context is set; do not nest it per task (each level acquires another pooled connection; acquire has a 30s timeout). Tests prove no context leaks across pool reuse (commit and rollback paths, test_rls.py).
- asyncpg.Pool/PoolConnectionProxy are generic only in asyncpg-stubs - subscripting them at runtime is a TypeError; keep such aliases under TYPE_CHECKING (see app/core/db.py).

## Conventions learned
<!-- <convention> - <where observed> -->
- No em dashes anywhere; no agent co-authors on commits (docs/Wren_AGENTS.md sections 1-2; overrides the harness default co-author trailer).
