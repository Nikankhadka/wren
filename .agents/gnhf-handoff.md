# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Last completed
- T-009 (Hybrid retrieval: dense + sparse + RRF + rerank). T-001..T-008
  landed before it - all nine are marked [x] in docs/phases/phase-1-foundations.md.
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (93 passed,
  +9 for T-009: RRF fusion math, real-Postgres dense/sparse/retrieve
  integration tests with hand-picked basis-vector embeddings, tenant
  isolation). No frontend/API surface yet (retrieve() has no HTTP route
  until T-011's bare /chat) so no browser verification applies here -
  instead manually smoke-tested the real (non-stubbed) LocalCrossEncoderReranker
  once outside pytest: it downloaded the real HuggingFace model and scored a
  screen-repair chunk far above an unrelated chunk for a screen-repair query.
- New: backend/app/retrieval/{types,dense,sparse,fuse,rerank,service}.py.
  Added sentence-transformers (pulls in torch) for the local reranker
  fallback - the only non-credential-gated rerank path, so it had to be
  real, not stubbed only. CohereReranker exists but is untested (needs
  COHERE_API_KEY, empty like Azure's).

## IMPORTANT - a gap discovered for the next ticket
- T-010 (Golden retrieval set + eval script) assumes "Tenant 1's seeded
  knowledge" already exists, but NO ticket through T-009 creates it.
  database.md's seeds section (around line 421-423) fully specifies
  `backend/seeds/seed_tenant1_phoneshop.py` - slug 'bytefix', tenant_config,
  ~15 catalog_items, ~12 pricing_rules, ~20 mock orders, knowledge docs
  ingested through the real pipeline - but no ticket's "Files" list owns it.
  T-010 cannot be done as literally written without it. Plan: fold creating
  that seed script into T-010's own work (it's fully specified already, just
  not explicitly ticketed) rather than treating it as a separate blocker.
  Flagging here per Wren_AGENTS.md's "flag conflicts instead of silently
  resolving them" - this is a documentation/sequencing gap, not a founder
  decision, so proceeding to fill it rather than stalling.
- Mock orders need the `orders`/`conversations` schema (kind 'repair'/'order',
  varied statuses) - read database.md's orders section before writing the
  seed script.

## Next intended ticket
- T-010 (Golden retrieval set + eval script) - deps: T-008 (satisfied), plus
  the seed-script gap above. Files: backend/seeds/seed_tenant1_phoneshop.py
  (new, not in the ticket's own list but required), backend/evals/datasets/tenant1_retrieval.jsonl,
  backend/evals/retrieval_eval.py. Read design/database.md section 7
  (eval_cases/eval_runs) and the seeds section before starting. The eval
  script needs real embeddings to produce real recall/MRR/nDCG numbers -
  AZURE_OPENAI_* being empty means this can only be smoke-tested with a stub
  provider, not run with real numbers, until the founder provisions
  credentials. Note that gap explicitly in the eval_runs row / commit rather
  than reporting fake "real numbers."

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- AZURE_OPENAI_* still empty - blocks real embeddings for T-010's eval
  numbers (same gap flagged since T-006/T-008). COHERE_API_KEY also empty -
  CohereReranker stays untested against a real API.
- Hosted Supabase project still doesn't exist - not relevant to T-010 (no
  auth surface involved).

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-1-foundations.md -> T-010's
  read-list, plus database.md's seeds section (not in T-010's own read-list
  but necessary given the gap above).
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass).
- Phase 1 must reach its Definition of Done green before starting phase 2.
