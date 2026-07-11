# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Last completed
- T-007 (Knowledge upload). T-001..T-006 landed before it - all seven are
  marked [x] in docs/phases/phase-1-foundations.md.
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (69 passed);
  frontend lint/typecheck/vitest/check:tokens/build. Live-verified in a
  browser: signup, upload (accept + reject-by-extension), and list all work
  over real HTTP with a locally-minted JWT; confirmed the uploaded file lands
  at the correct tenant-scoped path on disk. The Knowledge page itself
  renders correctly (dropzone, doc-type select, table) and degrades
  gracefully without a real Supabase session, same known gap as the other
  Supabase-gated pages.
- New: backend/app/api/knowledge.py (upload/list); frontend
  (tenant-admin)/knowledge/page.tsx plus four new shared components -
  Select, Table, EmptyState, Badge (with toneForStatus) - meant for reuse by
  Conversations/Escalations/Pricing later, not one-offs. Added
  python-multipart. Fixed a real bug in lib/api.ts's apiFetch: it forced
  `Content-Type: application/json` unconditionally, which would have broken
  every multipart upload; now skips that header when the body is FormData.

## Next intended ticket
- T-008 (Chunk + embed pipeline) - deps: T-007 (satisfied). Files:
  backend/app/ingestion/chunker.py, embedder.py, pipeline.py, and EXTENDS
  app/llm/provider.py + azure.py (already exist from T-006 with just
  `extract()` - T-008 adds `chat(messages, tools?)` and `embed(texts)` to the
  same abstraction, not a new one). Read design/database.md section 4
  (knowledge_chunks) before starting. Needs `pypdf` for .pdf parsing (not
  installed yet). Also wires into T-006's onboarding confirm step (catalog
  items become chunks too) - check app/api/onboarding.py's confirm() when
  adding that call.

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- AZURE_OPENAI_* env vars are still empty - T-008's embed() calls will be
  stub-tested only, same as T-006's extract(). Real embeddings need the
  founder to provision Azure OpenAI credentials before T-009's retrieval can
  be verified against real vectors (stub/fixture data can still validate the
  pipeline's mechanics).
- Hosted Supabase project still doesn't exist - not a blocker for T-008
  (no new auth surface needed).

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-1-foundations.md -> T-008's
  read-list.
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass).
- Phase 1 must reach its Definition of Done green before starting phase 2.
