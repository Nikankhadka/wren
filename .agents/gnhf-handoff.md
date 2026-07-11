# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Last completed
- T-004 (Supabase Auth + FastAPI tenant-context middleware), commit d1826e4.
  T-002 (schema + migrations, 3d070d5) and T-003 (RLS enforcement + schema
  audit, c0b798b) landed before it - all three are marked [x] in
  docs/phases/phase-1-foundations.md.
- Verified green on 2026-07-11: backend ruff check/format, mypy strict,
  pytest (47 passed); frontend lint, typecheck, check:tokens, build. Working
  tree is clean, nothing uncommitted.

## Next intended ticket
- T-005 (Tenant resolution by subdomain) - deps: T-004 (satisfied).
  Files: frontend/src/middleware.ts, frontend/src/lib/tenant.ts,
  backend/app/api/public.py. Read design/database.md section 3
  (resolve_tenant_slug) and design/frontend.md section 7 (route groups)
  before starting.
- Remember to delete the phase-0 placeholder frontend/src/app/page.tsx once
  (customer)/page.tsx lands (route groups do not segment URLs; both would
  resolve to / and break the build).

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- None. The hosted Supabase project still does not exist (T-004 notes this
  in .agents/memory.md) - real email/password login from the frontend stays
  blocked on the founder creating it and filling SUPABASE_*/NEXT_PUBLIC_
  SUPABASE_* values. Backend auth is fully testable locally without it, and
  T-005 does not depend on it either, so this is not a blocker for the next
  ticket.

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-1-foundations.md -> T-005's
  read-list.
- Phase 1 must reach its Definition of Done green before starting phase 2.
