# Project Memory

## Decisions
<!-- YYYY-MM-DD: <decision> - why: <reason> -->
- 2026-07-10: Documentation restructured into a phase-routed system (docs/INDEX.md is the entry point; design/ + phases/ are the working truth, Wren_*.md are frozen sources) - why: keep per-session context small so later phases can be executed by smaller models.
- 2026-07-10: All frontend visual values live in frontend/src/styles/theme.css as 3-layer tokens; components use semantic tokens only, enforced by `npm run check:tokens` - why: founder requirement that colors are never hardcoded and stay easy to change; also enables per-tenant runtime branding.
- 2026-07-10: Backend Python pinned to 3.12 (.python-version) - why: GenAI deps in later phases (RAGAS, torch cross-encoders) lag on newest Python versions.
- 2026-07-10: tenant_id denormalized onto messages and tool_calls; orders given a generic shape (ref_code/kind/status/details); quotes immutable-except-status via trigger - why: direct RLS, domain-agnosticism, no retroactive quote changes (docs/design/database.md, flagged and approved in planning).
- 2026-07-10 (T-002): quote protection strengthened slightly beyond database.md's sample trigger - id/created_at also frozen, and wren_app holds no DELETE on quotes (revoked; FK cascades still work because they run as the table owner) - why: principle 5 "tamper-proof once sent" taken literally after review.
- 2026-07-10 (T-002): wren_resolver gets column-level grants only (tenants: id/slug/name/status; tenant_config: tenant_id/brand) - why: the privilege boundary of the single sanctioned RLS bypass must match resolve_tenant_slug's four-column contract, so a future resolver-owned function cannot widen the pre-auth surface.

- 2026-07-11 (T-004): auth dependencies return the authed principal and each route opens `tenant_context(tenant_id, role)` itself, instead of the ticket's "dependency yields the connection" - why: avoids holding a transaction/pooled connection for the whole request; acceptance (API-level cross-tenant isolation) proven in test_auth_api.py. Flagged for founder confirmation.
- 2026-07-11 (T-004): pre-context user/platform-admin lookups go through SECURITY DEFINER resolvers `resolve_user_tenant` / `resolve_platform_admin` (migration 0009, wren_resolver-owned, column-level grants) mirroring resolve_tenant_slug - why: keeps the sanctioned RLS bypass surface narrow and auditable.
- 2026-07-11 (T-004): frontend ui kit is hand-built per frontend.md section 6 (no shadcn - its own color-variable layer conflicts with the theme.css token system + check-tokens CI guard); no client state lib yet (supabase-js session + React state suffice; revisit at T-006 if the onboarding panel needs shared state).
- 2026-07-11 (T-005): Next.js 16 renamed the `middleware.ts` convention to `proxy.ts` (function renamed `middleware` -> `proxy`); `middleware.ts` still works but is deprecated. Wrote `frontend/src/proxy.ts` instead of the ticket's literal `middleware.ts` filename - same host-routing behavior, current convention. Deviation from ticket text, not from intent.
- 2026-07-11 (T-005): route groups don't segment URLs, so `(customer)/page.tsx` and any future `(platform)`/`(tenant-admin)` root page would collide at `/`. proxy.ts 404s `/` for the platform/tenant-admin surfaces until those surfaces get real root pages - replace that guard with real routing then, don't just delete it (see proxy.ts comment).
- 2026-07-11 (T-005): added vitest (frontend had no unit-test runner at all) to cover `lib/tenant.ts`'s `resolveHost` - `npm run test` is now a verified frontend command alongside lint/typecheck/check:tokens/build.
- 2026-07-11 (T-005): asyncpg returns `jsonb` columns as raw text, not decoded JSON - no codec was registered anywhere yet, so `app/api/public.py` does `json.loads()` on `tenant_config.brand` by hand. If a jsonb codec gets registered on the pool later, remove this ad hoc decode.

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
- Supabase JWT verification MUST pass `options={"require": ["exp"]}` to jwt.decode - PyJWT validates exp only if present, so a token minted without exp would otherwise never expire (app/core/auth.py; regression test in test_auth_api.py).
- INSERT ... RETURNING enforces the table's SELECT policies even for pure inserts - the service role (Shape C, INSERT-only) cannot use RETURNING; generate ids client-side instead (app/api/tenants.py signup).
- SECURITY DEFINER functions here use `set search_path = public` without trailing `pg_temp` (0003 and 0009, deliberately matching); harden both together in a future migration rather than diverging.
- Local dev needs a non-empty SUPABASE_JWT_SECRET in backend/.env (any 64-hex string); the hosted Supabase project is NOT created yet - real email/password login from the frontend is blocked on founder creating it and filling SUPABASE_*/NEXT_PUBLIC_SUPABASE_* values. Backend auth is fully testable with locally minted HS256 tokens.

## Conventions learned
<!-- <convention> - <where observed> -->
- No em dashes anywhere; no agent co-authors on commits (docs/Wren_AGENTS.md sections 1-2; overrides the harness default co-author trailer).
