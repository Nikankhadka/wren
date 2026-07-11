# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Last completed
- T-008 (Chunk + embed pipeline). T-001..T-007 landed before it - all eight
  are marked [x] in docs/phases/phase-1-foundations.md.
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (84 passed,
  +15 for T-008: chunker unit tests, upload->chunks->embedding assertions,
  a real-parse-failure path, reprocess endpoint). No frontend changes this
  ticket (the Knowledge page's existing Badge/status rendering already
  handles the new synchronous ready/failed outcomes). Live-verified in a
  browser: a real AzureOpenAIProvider still fails cleanly (500, no crash)
  with empty AZURE_OPENAI_* - same known gap, not a new bug.
- New: app/ingestion/{chunker,embedder,pipeline}.py; app/llm/dependency.py
  (extracted get_llm_provider so knowledge.py and onboarding.py share one
  override point); tests/fakes.py (BaseFakeProvider). LLMProvider grew
  chat() and embed(). db.py's create_pool now registers pgvector's vector
  codec on every connection (also added to tests/conftest.py's
  superuser_conn fixture). Knowledge upload now runs chunk+embed
  synchronously in the request (no queue system exists; 10MB cap makes this
  an acceptable scope call, not a shortcut). Added a POST
  /api/knowledge/{id}/reprocess endpoint for the retry button. Onboarding's
  confirm() now also calls ingest_catalog_items, writing catalog_items into
  a synthetic 'catalog'-doc_type document so they're retrievable too.

## Next intended ticket
- T-009 (Hybrid retrieval: dense + sparse + RRF + rerank) - deps: T-008
  (satisfied). Files: backend/app/retrieval/{dense,sparse,fuse,rerank,service}.py.
  Read design/database.md section 4 (query shapes) before starting. Needs a
  reranker: Cohere Rerank (COHERE_API_KEY, also empty right now) or a local
  cross-encoder/ms-marco-MiniLM-L-6-v2 fallback, chosen via the RERANKER env
  var (already defaults to 'local' in settings) - the local path is
  probably the only one testable without more founder-provisioned
  credentials. service.py's retrieve(tenant_id, query, k) is the single
  entry point later callers (bare chat T-011, agents in phase 2) use -
  don't let them call dense/sparse/fuse/rerank directly.

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- AZURE_OPENAI_* and COHERE_API_KEY are still empty - T-009's dense
  retrieval (needs query embeddings) and Cohere reranking are both
  live-untestable; the local cross-encoder fallback and sparse (FTS-only)
  retrieval can still be verified for real. Flag to the founder if T-009
  needs to prove dense retrieval works before Azure credentials exist -
  might be worth seeding fixture embeddings directly for a smoke test
  instead of waiting.
- Hosted Supabase project still doesn't exist - not a blocker for T-009 (no
  new auth surface).

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-1-foundations.md -> T-009's
  read-list.
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass).
- Phase 1 must reach its Definition of Done green before starting phase 2.
