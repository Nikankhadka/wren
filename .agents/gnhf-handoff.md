# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Last completed
- T-006 (Conversational onboarding skeleton - Surface-2 Copilot). T-001..T-005
  landed before it - all six are marked [x] in docs/phases/phase-1-foundations.md.
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (61 passed);
  frontend lint/typecheck/vitest/check:tokens/build. Live-verified in a
  browser: signup + GET /api/onboarding/state work over real HTTP (JWT minted
  locally against backend/.env's actual secret); AzureOpenAIProvider
  construction fails cleanly (500, no crash) with empty AZURE_OPENAI_* -
  expected, not a bug. The onboarding page itself renders correctly and shows
  a graceful error state without a real Supabase session (same as login/signup
  - Supabase project still doesn't exist). Working tree is clean, scratch
  tenants cleaned up.
- New: app/llm/provider.py + app/llm/azure.py (the LLM provider abstraction,
  Azure OpenAI structured-output implementation), app/onboarding/flow.py (the
  7-stage state machine), app/api/onboarding.py (state/message/confirm
  endpoints), frontend (tenant-admin)/onboarding/page.tsx + a new shared
  ChatBubble component. Added the `openai` Python package.
- Three judgment calls made and documented in .agents/memory.md: (1) onboarding
  prices are extracted by the model as a float and converted to cents in
  plain Python, never inside the model call; (2) "mark tenant live" is a
  tenant_config.config.onboarding.completed flag, NOT a tenants.status
  transition - no RLS policy lets tenant_admin/service update tenants.status,
  only platform_admin; (3) full browser E2E of Supabase-gated pages stays
  blocked pending real credentials, same as T-004.

## Next intended ticket
- T-007 (Knowledge upload) - deps: T-006 (satisfied). Files:
  backend/app/api/knowledge.py, frontend/src/app/(tenant-admin)/knowledge/page.tsx.
  Read design/database.md section 4 (documents) and design/frontend.md
  section 6 (FileDropzone) + 7.2 (Knowledge page) before starting. Needs a
  new shared FileDropzone + Table component (neither exists yet) and local
  file storage under var/uploads/{tenant_id}/ (10MB cap, .md/.txt/.pdf/.csv/.json).

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- Hosted Supabase project still doesn't exist - blocks real browser E2E of
  any Supabase-gated page (login, signup, onboarding), not blocking for
  T-007 (knowledge upload doesn't need a new auth flow, just the existing
  require_tenant_admin dependency).
- AZURE_OPENAI_* env vars are still empty - blocks live LLM extraction in
  onboarding (stub-tested only). T-008 (chunk + embed pipeline) will hit this
  same gap for embeddings; flag to the founder if real testing is needed
  before then.

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-1-foundations.md -> T-007's
  read-list.
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass).
- Phase 1 must reach its Definition of Done green before starting phase 2.
