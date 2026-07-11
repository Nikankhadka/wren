# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## Phase 1 is done; now in Phase 2 (Agents & Pricing)
- Phase 1 (T-001..T-011) is fully complete, Week 1 DoD checked -
  docs/phases/phase-1-foundations.md. Phase 2 is
  docs/phases/phase-2-agents-pricing.md (T-012..T-022).

## Last completed
- T-012 (LangGraph state schema + graph skeleton).
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (124
  passed, +6 for T-012: forced-route topology tests, escalation flag
  propagation, node-reachability check). No frontend changes (pure backend
  refactor, transparent to the customer surface). Re-verified all 7 of
  T-011's existing chat API tests still pass unmodified - the accept
  criteria's explicit requirement. Also live-smoke-tested the compiled
  graph directly against the real seeded 'bytefix' tenant (retrieved 5 real
  chunks from policy/faq/price_list/catalog, streamed fake tokens through
  langgraph's custom stream writer correctly) before wiring it into chat.py.
- T-011's retrieval+prompt+streaming logic moved into app/agents/knowledge.py
  as a real graph node (supervisor -> knowledge -> inspection, since the
  supervisor stub always routes to knowledge for now). app/api/chat.py is
  now a thin wrapper: resolve tenant/conversation, invoke the graph via
  `astream(..., stream_mode="custom")`, translate custom events to SSE,
  persist the final message. New app/agents/{state,graph,supervisor,
  knowledge,recommendation,quoting,order_status,escalation,inspection}.py.
  All non-knowledge specialist nodes are pure stubs (recommendation/quoting/
  order_status pass through with `{}`; escalation sets `escalated: True`;
  inspection always passes). Added the `langgraph` package.

## Next intended ticket
- T-013 (Supervisor routing) - deps: T-012 (satisfied). Files:
  backend/app/agents/supervisor.py (replace the always-knowledge stub with
  real routing). Steps: one structured LLM call (conversation tail ->
  {route, confidence, reason}), routing prompt generic/capability-based
  (never vertical-named, domain-agnostic hard rule), confidence below
  tenant_config.escalation_threshold always routes to escalation regardless
  of what the model guessed. Tests: routing unit tests with a stubbed
  provider (this is straightforward - `supervisor.run` already has the
  `extract()`-style structured-output pattern to copy from onboarding's
  flow.py) - PLUS the ticket explicitly asks for "a small live-model routing
  smoke set (~10 cases) run manually and noted," which needs real Azure
  credentials (still absent) to actually execute. Note that gap in the
  commit/memory rather than skipping the requirement silently.
- Once T-013 lands, build_graph()'s default supervisor_node becomes the real
  router - re-verify T-012's forced-route tests and T-011's chat API tests
  both still pass (same "nothing regresses" discipline as this ticket).

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- AZURE_OPENAI_* still empty - blocks T-013's live-model routing smoke set
  and any other real-model verification throughout phase 2. Every ticket so
  far has worked around this with stubbed-provider tests; expect the same
  pattern to keep working for the remaining phase-2 tickets (recommendation,
  quoting, escalation are logic-heavy, not generation-heavy, so this
  shouldn't block much).
- Hosted Supabase project still doesn't exist - irrelevant to phase 2 (no
  auth surface involved in agents/pricing work).

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-2-agents-pricing.md (read the
  "Shared contracts for this phase" section at the top once) -> T-013's
  own read-list.
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass). Worth doing soon given how much has landed.
- Phase 2 must reach its own Definition of Done before starting phase 3.
