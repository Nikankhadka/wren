# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Phase 1 done; in Phase 2 (Agents & Pricing, docs/phases/phase-2-agents-pricing.md)

## Last completed
- T-014 (Knowledge Agent) - mostly already satisfied by T-012's design (T-011's
  logic became a real node immediately, not a stub). The only actual gap was
  a dedicated node-level test with stubbed retrieval/provider, added in
  tests/test_knowledge_agent.py (2 new tests: provenance shape on success,
  empty provenance on refusal).
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (134
  passed). No frontend changes.

## Next intended ticket
- T-015 (Recommendation Agent) - deps: T-013 (satisfied). Files:
  backend/app/agents/recommendation.py. Read design/database.md section 5
  (catalog_items) and recall T-008's note that catalog items exist as
  knowledge_chunks with metadata.kind='catalog_item' (see
  app/ingestion/chunker.py's chunk_catalog_item + app/ingestion/pipeline.py's
  ingest_catalog_items). Steps: extract preferences via structured LLM call
  (generic needs/constraints keys, no vertical assumptions), retrieve scoped
  to metadata.kind='catalog_item' chunks specifically (retrieve() doesn't
  currently support filtering by metadata kind - check whether to add that
  as a parameter to app/retrieval/service.py or filter client-side after a
  normal retrieve() call, whichever is cleaner), draft recommendations
  naming only retrieved items with their DB price_cents formatted
  server-side (never model-authored - deterministic-pricing hard rule).
  Tests: node tests with a fixture catalog; assert recommended item ids are
  a subset of retrieved ids (never invented).

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- AZURE_OPENAI_* still empty - same pattern as every ticket since T-006;
  structured-extraction logic is stub-testable, live-model behavior isn't.
- Hosted Supabase project still doesn't exist - irrelevant to phase 2.

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-2-agents-pricing.md (shared
  contracts section) -> T-015's own read-list.
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass). Worth doing soon given how much has landed.
- Phase 2 must reach its own Definition of Done before starting phase 3.
