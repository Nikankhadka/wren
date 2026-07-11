# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Last completed
- T-005 (Tenant resolution by subdomain). T-001..T-004 landed before it - all
  five are marked [x] in docs/phases/phase-1-foundations.md.
- Verified green on 2026-07-11: backend ruff check/format, mypy strict,
  pytest (51 passed, +4 for T-005's public resolve endpoint); frontend lint,
  typecheck, check:tokens, build, and a new `npm run test` (vitest, 5 passed -
  frontend had no unit-test runner before this ticket). Manually E2E'd in a
  real browser: bytefix.localhost:3000 (branded shell), a suspended tenant
  (unavailable state), an unknown slug (calm 404), and confirmed
  admin.localhost:3000/ and app.localhost:3000/login behave correctly (see
  .agents/memory.md for the root-path collision guard this required). Working
  tree is clean, nothing uncommitted, scratch dev-DB tenants cleaned up.
- Deviated from the ticket's literal filename: wrote `frontend/src/proxy.ts`,
  not `middleware.ts` - Next.js 16 renamed the convention (deprecated but
  still functional). See .agents/memory.md T-005 entries for this and two
  other durable discoveries (the root-collision guard, the jsonb decode
  workaround).

## Next intended ticket
- T-006 (Conversational onboarding skeleton - Surface-2 Copilot) - deps: T-005
  (satisfied). Files: backend/app/api/onboarding.py,
  backend/app/onboarding/flow.py, frontend/src/app/(tenant-admin)/onboarding/page.tsx.
  Read design/frontend.md sections 6-7.2 and design/database.md sections 3, 5
  before starting. This is the first ticket needing `app/llm/provider.py` (an
  LLM abstraction) - it doesn't exist yet, so T-006 likely needs to stand up a
  minimal provider abstraction (or at least a stub/interface) before the
  onboarding flow can call it. Check if a later ticket already owns that file
  before building it ad hoc.

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- None. The hosted Supabase project still does not exist (T-004) - real
  email/password login from the frontend stays blocked on the founder
  creating it and filling SUPABASE_*/NEXT_PUBLIC_SUPABASE_* values. Not a
  blocker for T-006, which doesn't need real Supabase auth to build the
  onboarding flow itself.
- The Azure OpenAI env vars (AZURE_OPENAI_*) are also still empty in .env -
  T-006's LLM calls for stage extraction will need either real credentials or
  a stubbed provider to be testable locally. Flag to the founder if T-006
  can't proceed without them.

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-1-foundations.md -> T-006's
  read-list.
- .agents/map.md is stale (last regenerated after T-004) - it's marked
  auto-generated, so don't hand-edit it; regenerate via /init-project when
  convenient, or leave for the maintainer pass.
- Phase 1 must reach its Definition of Done green before starting phase 2.
