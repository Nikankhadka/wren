# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Phase 1 done; in Phase 2 (Agents & Pricing, docs/phases/phase-2-agents-pricing.md)

## Last completed
- T-015 (Recommendation Agent). Extracts generic needs/constraints,
  retrieves scoped to metadata.kind='catalog_item' only (new optional
  metadata_kind filter added to app/retrieval/{dense,sparse,service}.py -
  backward compatible, default None), re-fetches price/name/description
  fresh from catalog_items by id (never trusts the chunk's embedded text or
  the model), refuses when nothing matches.
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (137
  passed, +3 for recommendation node tests: selections are a subset of the
  real catalog, price comes from the DB column, refusal on empty catalog).
  Live-verified against the real seeded 'bytefix' catalog: all 5 returned
  recommendations were genuine catalog items, zero prose leaked in.
- Fixed fallout: making recommendation.py a real node (not a stub) broke
  test_agent_graph.py's topology tests, which had assumed every non-knowledge
  specialist was a free no-op. Needed pytest.mark.db + a real pool fixture +
  a FakeProvider supporting both extract() shapes it might now see. Lesson
  recorded in memory: whenever a stub specialist gains real logic, re-run
  the FULL suite, not just its own new tests.

## Next intended ticket
- T-016 (Deterministic pricing engine) - deps: T-002 (satisfied, schema
  already exists). Files: backend/app/pricing/engine.py,
  backend/tests/test_pricing_engine.py. THIS IS THE HARD-RULE CENTERPIECE
  TICKET - no LLM imports anywhere in this module, full stop. Pure function
  compute_quote(tenant_id, selections: [{rule_code|catalog_item_id,
  quantity}]) -> EngineQuote(line_items, subtotal_cents, tax_cents,
  total_cents). Reads active pricing_rules/catalog_items fresh from DB;
  unknown code/id or inactive item -> typed error (the agent re-selects, it
  never fabricates); quantity bounded 1..999; conditions (min_qty,
  applies_to) honored per database.md's generic keys. Tax from
  tenant_config.config.tax.rate_bps, integer math only
  (subtotal * rate_bps // 10000 - no float rounding anywhere near money).
  Accept criteria demands EXHAUSTIVE unit coverage (single/multi line, both
  selection kinds, tax on/off, rounding, unknown codes, zero-amount rules)
  plus a property test that total always equals sum of parts (hypothesis,
  if quick) - this ticket's tests ARE the deliverable, budget real time for
  them, don't rush this one.

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- None specific to T-016 - it's pure DB + arithmetic, no LLM/embeddings
  needed at all, so the AZURE_OPENAI_*/COHERE_API_KEY gaps that have
  affected most tickets since T-006 don't apply here. This should be fully
  live-testable without any founder-provisioned credentials.
- Hosted Supabase project still doesn't exist - irrelevant to phase 2.

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-2-agents-pricing.md (shared
  contracts section, especially "The Quoting Agent's output schema has no
  number fields") -> T-016's own read-list (database.md section 5).
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass). Worth doing soon given how much has landed.
- Phase 2 must reach its own Definition of Done before starting phase 3.
