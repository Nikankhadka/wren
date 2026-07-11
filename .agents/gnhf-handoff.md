# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Phase 1 done; in Phase 2 (Agents & Pricing, docs/phases/phase-2-agents-pricing.md)

## Last completed
- T-013 (Supervisor routing). supervisor.py now does real routing via one
  `extract()` call -> `RouteDecision{route, confidence, reason}`; confidence
  below `tenant_config.escalation_threshold` is always overridden to
  `escalation` in code (not left to the prompt).
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (132
  passed, +8 for T-013's routing tests: all 5 routes pass through at high
  confidence, low-confidence override, exact-threshold boundary, per-tenant
  threshold). Fixed fallout in test_chat_api.py's FakeChatProvider (needed
  extract() now that the real supervisor runs for every chat request).
- **Gap, not silently skipped**: the ticket's "small live-model routing
  smoke set (~10 cases) run manually and noted" was NOT run -
  AZURE_OPENAI_* is still empty. The deterministic override logic (the part
  that's actually code, not prompt quality) is thoroughly unit-tested; the
  claim "obvious utterances route correctly across two fake verticals"
  stays unverified until real credentials exist. Don't report this as fully
  done without that caveat.
- Learned: `get_runtime()` (langgraph) only works inside an actual node
  execution inside a running graph - can't unit-test `supervisor.run(state)`
  or `knowledge.run(state)` by calling them directly; must drive through
  `build_graph().ainvoke(...)`/`.astream(...)`.

## Next intended ticket
- T-014 (Knowledge Agent) - deps: T-013 (satisfied). **Mostly already done**
  as a side effect of T-012: the ticket's own accept criteria is "parity
  with T-011 behavior through the graph; provenance lands in state," and
  app/agents/knowledge.py already IS T-011's logic as a real node, already
  returning `retrieved_chunks` (id/content/metadata) into state for
  Inspection to use later. What's actually missing for T-014 specifically:
  a dedicated node-level unit test ("node test with stubbed
  retrieval/provider" - the ticket's own Tests line) driving just the
  knowledge node in isolation (through the graph, per the get_runtime
  constraint above) rather than only indirectly via test_chat_api.py/
  test_agent_graph.py. Should be a fast ticket - write that test, confirm
  provenance shape, mark done.

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- AZURE_OPENAI_* still empty - blocks T-013's live-model smoke set (not
  re-attempted, see above) and will block similar "live-model" Tests asks
  in later phase-2 tickets the same way. COHERE_API_KEY also still empty.
- Hosted Supabase project still doesn't exist - irrelevant to phase 2.

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-2-agents-pricing.md (shared
  contracts section) -> T-014's own read-list.
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass). Worth doing soon given how much has landed.
- Phase 2 must reach its own Definition of Done before starting phase 3.
