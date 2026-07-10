# Project Memory

## Decisions
<!-- YYYY-MM-DD: <decision> - why: <reason> -->
- 2026-07-10: Documentation restructured into a phase-routed system (docs/INDEX.md is the entry point; design/ + phases/ are the working truth, Wren_*.md are frozen sources) - why: keep per-session context small so later phases can be executed by smaller models.
- 2026-07-10: All frontend visual values live in frontend/src/styles/theme.css as 3-layer tokens; components use semantic tokens only, enforced by `npm run check:tokens` - why: founder requirement that colors are never hardcoded and stay easy to change; also enables per-tenant runtime branding.
- 2026-07-10: Backend Python pinned to 3.12 (.python-version) - why: GenAI deps in later phases (RAGAS, torch cross-encoders) lag on newest Python versions.
- 2026-07-10: tenant_id denormalized onto messages and tool_calls; orders given a generic shape (ref_code/kind/status/details); quotes immutable-except-status via trigger - why: direct RLS, domain-agnosticism, no retroactive quote changes (docs/design/database.md, flagged and approved in planning).

## Gotchas
<!-- <thing that will bite you> - <what to do instead> -->
- Supabase's `postgres` role owns tables and would bypass RLS - every tenant table needs FORCE ROW LEVEL SECURITY and the API must connect as the dedicated `wren_app` role (docs/design/database.md section 2).
- Next.js 16 in frontend/ has breaking changes vs training data - read `frontend/node_modules/next/dist/docs/` before writing frontend code (see frontend/AGENTS.md).
- backend tests import `app.*` via `pythonpath = ["."]` in pyproject's pytest config - don't convert the app into an installed package without updating this.

## Conventions learned
<!-- <convention> - <where observed> -->
- No em dashes anywhere; no agent co-authors on commits (docs/Wren_AGENTS.md sections 1-2; overrides the harness default co-author trailer).
