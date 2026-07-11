# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Last completed
- T-010 ([EDD] Golden retrieval set + eval script). T-001..T-009 landed
  before it - all ten are marked [x] in docs/phases/phase-1-foundations.md.
  This is the last ticket before Week 1's Definition of Done.
- Filled the seed-script gap flagged in T-009's handoff: created
  backend/seeds/seed_tenant1_phoneshop.py (tenant 'bytefix' - 15
  catalog_items, 12 pricing_rules, 20 mock orders, 3 knowledge docs
  policy/faq/price_list ingested through the real pipeline). Authored 50
  golden retrieval cases (45 positive + 5 negative) in
  backend/evals/datasets/tenant1_retrieval.jsonl, and
  backend/evals/retrieval_eval.py (recall@3/@5, MRR, nDCG@5, negative
  top-score tracking, --gate flag, writes an eval_runs row).
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (105
  passed, +12 for T-010: seed-script idempotence/counts, metric-function
  known-answer fixtures). Added seeds/ and evals/ to mypy's files list.
  Actually RAN the eval script against the seeded dev DB (not just unit
  tests): with a stub (all-zero) embedder standing in for the still-missing
  Azure credentials, got recall@3/@5 = 1.000, MRR = 0.911, nDCG@5 = 0.934,
  clearing the Week-1 DoD's recall@5 >= 0.85 bar. This is a genuine
  sparse+rerank-only result (dense degrades to noise with a constant
  embedding, but sparse FTS and the real local cross-encoder reranker don't
  need real embeddings at all) - re-run once Azure credentials exist for the
  true hybrid number, expected to be equal or better. eval_cases (50 rows)
  and the eval_runs row are already persisted in the dev DB from this run.
- The dev DB now has tenant 'bytefix' seeded persistently and intentionally
  (not scratch data to clean up) - it's Tenant 1, the anchor demo tenant
  every later ticket (T-011, phase 2 agents, phase 4 dashboards) can rely on
  existing. Re-run `uv run python -m seeds.seed_tenant1_phoneshop` any time
  to reset it (it wipes and recreates).

## Next intended ticket
- T-011 (Bare /chat: straight-line RAG with citations) - deps: T-009, T-010
  (both satisfied). This is the LAST phase-1 ticket - once it's done, run
  the full Week-1 Definition of Done checklist (docs/phases/phase-1-foundations.md,
  bottom of the file) before considering starting phase 2. Files:
  backend/app/api/chat.py, frontend/src/app/(customer)/page.tsx + chat
  components. Read design/frontend.md sections 6-7.1 (ChatBubble already
  exists from T-006 - StreamingText and CitationChip don't yet) and
  design/database.md section 6 (conversations, messages) before starting.
  This ticket REPLACES the placeholder "(customer)/page.tsx" content from
  T-005 (currently just a branded shell with "chat coming soon") with the
  real chat UI - expect to rewrite that file, not just add to it.
  Real end-to-end browser testing (bytefix.localhost:3000) is possible for
  the retrieval/citation parts, but the actual LLM generation call will hit
  the same missing-Azure-credentials wall as everything else - plan to
  verify with a stubbed provider and note the live-generation gap the same
  way prior tickets did.

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- AZURE_OPENAI_* still empty - blocks real chat generation in T-011 (same
  gap as embeddings/extraction throughout phase 1). The retrieval and
  citation-marker logic itself is fully testable with a stub provider.
- Hosted Supabase project still doesn't exist - not relevant to T-011 (the
  customer surface has no auth).

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-1-foundations.md -> T-011's
  read-list.
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass).
- After T-011, phase 1 is content-complete - walk the Week 1 Definition of
  Done checklist explicitly before moving to phase 2's T-012.
