# GNHF handoff state

This file carries state between gnhf iterations (fresh sessions) so a new
iteration knows where the previous one stopped. Read this before starting
work, and overwrite it at the end of your iteration per .agents/gnhf-objective.md.

## MILESTONE: Phase 1 (Foundations) is complete
- T-001 through T-011 are all [x] in docs/phases/phase-1-foundations.md, and
  the Week 1 Definition of Done checklist at the bottom of that file is
  fully checked (with an honest caveat on the one item that can't be 100%
  live-verified without real Azure credentials - see that file for the
  exact wording). Phase 2 (agents + pricing, docs/phases/phase-2-agents-pricing.md)
  starts at T-012.

## Last completed
- T-011 (Bare /chat: straight-line RAG with citations) - the final phase-1
  ticket.
- Verified green on 2026-07-11: backend ruff/format/mypy/pytest (118
  passed, +13 for T-011: chat API happy path, persistence, refusal,
  conversation resume, wrong-tenant 404, unknown/suspended slug 404, plus 7
  new CORS regression tests); frontend lint/typecheck/vitest/check:tokens/build.
  Live-verified in a browser end to end: bytefix.localhost:3000 renders the
  branded shell + greeting + composer, sending a message correctly shows the
  customer bubble, the request reaches the backend (proving the CORS fix
  below), and fails at the expected point (missing Azure credentials, clean
  500) with the frontend's error+Retry UI rendering exactly per spec - not a
  crash, not a blank screen.
- **Found and fixed a real bug while doing this**: `app/main.py` had NO CORS
  middleware at all. Every browser fetch from the frontend origin to the
  backend origin was silently broken - it just hadn't surfaced yet because
  onboarding/knowledge (T-006/T-007) fail earlier at `getSupabase()` (no
  Supabase project) before ever reaching their fetch call. T-011's
  unauthenticated bare chat was the first code path to actually execute a
  cross-origin fetch, and it hit `net::ERR_FAILED` immediately. Fixed with
  `CORSMiddleware` using an `allow_origin_regex` (every tenant gets its own
  subdomain, so a fixed origin list can't work) - regression-tested in
  test_health.py. If a custom-domains-per-tenant feature ever lands, that
  regex needs revisiting.
- New: app/api/chat.py (POST /api/chat, SSE streaming, citations, refusal
  path), frontend CustomerChat.tsx + StreamingText/CitationChip components,
  LLMProvider grew chat_stream() for real per-token streaming (distinct from
  the existing non-streaming chat() phase-2 agents will use).

## Next intended ticket
- T-012 (LangGraph state schema + graph skeleton) - deps: T-011 (satisfied).
  This starts PHASE 2 (docs/phases/phase-2-agents-pricing.md), not phase 1.
  Files: backend/app/agents/{state,graph,supervisor,knowledge,recommendation,
  quoting,order_status,escalation,inspection}.py. Read phase-2's shared
  contracts section and only consult the frozen Architecture Doc's 4.1
  diagram if graph topology is unclear. Step 3 explicitly says to swap
  /api/chat to invoke the graph with stub nodes behaving like T-011's
  straight RAG, so T-011's own tests must keep passing unmodified - budget
  time to verify that, not just write new graph tests. Needs the `langgraph`
  package (not installed yet).

## Branch
- gnhf/gnhf-objective-wren-6c20d4 (current branch); do not commit to main.

## Blocking issues
- AZURE_OPENAI_* still empty - real chat generation (and now real dense
  retrieval, since T-009/T-010) stays untestable live. This has been true
  since T-006 and doesn't block code correctness, only live end-to-end
  verification of generation text specifically.
- Hosted Supabase project still doesn't exist - blocks live E2E of
  login/signup/onboarding/knowledge pages specifically (customer chat has no
  auth, so it was unaffected and got fully live-verified this ticket).
- Neither of the above blocks starting phase 2 - agents/pricing work doesn't
  need either credential to build and test correctly (stub providers cover
  it, same pattern used throughout phase 1).

## Notes for the next iteration
- Read .agents/gnhf-objective.md in full first - it has the working loop and
  the binding rules.
- Then docs/INDEX.md -> docs/phases/phase-2-agents-pricing.md -> T-012's
  read-list. Do NOT reread phase-1-foundations.md's ticket details - phase 1
  is done, only its Week 1 DoD note at the bottom is worth a glance for
  context on what's still credential-blocked.
- .agents/map.md is stale (last regenerated after T-004, marked
  auto-generated - don't hand-edit it, regenerate via /init-project or leave
  for the maintainer pass). Worth doing a maintainer pass soon given how
  much has landed since it was last refreshed.
- Phase 2 must reach its own Definition of Done before starting phase 3.
