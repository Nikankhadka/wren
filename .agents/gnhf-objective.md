# GNHF objective - Wren full build (phases 1 through 4)

You are running as an unsupervised overnight coding agent on the Wren monorepo
at /Users/nikankhadka/projects/wren. Each gnhf iteration is a fresh session, so
read this file in full at the start of every iteration before doing anything
else. Do not rely on anything you think you remember from a previous iteration.

## What you are building

Wren is a domain-agnostic, multi-tenant SaaS. Start at docs/INDEX.md, follow
its phase router, and execute the ticket files in docs/phases/ in strict
order: phase-1-foundations (T-002..T-011), then phase-2-agents-pricing
(T-012..T-022), then phase-3-eval-console (T-023..T-031), then phase-4-ship
(T-032..T-040). T-001 is already done. Stop only when the phase-4 Definition of
Done block passes, or when gnhf's iteration/token limits are hit.

## The working loop - run it once per ticket, then move on

For each ticket, in this exact order:

1. PLAN - Read docs/INDEX.md, the current phase file, the ticket's own
   read-list (per-ticket sections of docs/design/database.md and/or
   docs/design/frontend.md), docs/Wren_AGENTS.md, .agents/memory.md, and this
   file. Decide the smallest correct change set. If a ticket is genuinely
   independent of the others (its inputs are already in place), you may start
   it on its own; otherwise sequence after the ticket that produces its inputs.

2. CODE - Implement the ticket. Work test-first per the testing skill where
   practical (Red-Green-Refactor). Keep changes scoped to the ticket.

3. REVIEW - Review your own diff before committing: lint, typecheck, and a
   self-critique against the two hard rules (sections 8 and 9 below) and the
   hygiene rule (section 7). Fixanything you find before committing.

4. NO-MISTAKES - Run the no-mistakes pipeline (the /no-mistakes skill) on the
   change set: automated review, tests, lint, docs, push, PR, CI. If the skill
   or its CLI is unavailable in this iteration, do the steps manually
   (lint -> typecheck -> test -> docs update) and note that no-mistakes was
   skipped in the commit body. Do not block the whole run on a missing skill.

5. TEST - Run the verified commands for whatever you touched, and they must be
   green before you commit:
   - frontend (in frontend/): npm run lint, npm run typecheck,
     npm run check:tokens, npm run build
   - backend (in backend/): uv run ruff check ., uv run ruff format --check .,
     uv run mypy, uv run pytest
   - Lint errors, failing tests, and flaky tests are BLOCKING wherever
     encountered, regardless of whether this ticket caused them. Fix them as
     part of the work (Wren_AGENTS.md section 7).

6. DOC-UPDATE - After the ticket passes its gates, update the ticket's status
   marker in the phase file: [ ] -> [x] (or [!] blocked with a note, or [-]
   deferred with a note). If a definition-of-done checklist item in the phase
   file is now satisfied, mark it too. Record any durable discovery
   (decision, gotcha, convention) in .agents/memory.md under the right section
   with a dated entry. Never edit CHANGELOG.md or anything marked
   auto-generated.

7. COMMIT - Make exactly ONE commit for this ticket (or a small, logically
   grouped commit set if the ticket has distinct phases). Commit message:
   "T-NNN <short ticket title>" on the first line, plain-language body after a
   blank line describing what changed and why. Do NOT add any agent name as
   co-author (Wren_AGENTS.md section 2). Do NOT use the em dash character
   anywhere (use a plain dash). Stage only the files this ticket touched plus
   the phase-file status update and any memory.md additions.

8. COMPACT - Before starting the next ticket, compact the session context so
   you don't accumulate noise: write a short handoff note to
   .agents/gnhf-handoff.md (last completed ticket, next intended ticket, any
   blocking issue), then rely on the gnhf iteration boundary to reset context.

Then move to the next ticket in the phase. When a phase's Definition of Done
block is fully green, advance to phase (N+1). Do NOT start phase N+1 while
phase N's DoD is failing - docs/INDEX.md forbids it.

## Branch and commit model (selective-merge friendly)

You are on a single gnhf branch (gnhf creates it for this run; do not commit to
main). Each ticket is its own commit, so the human can cherry-pick or
selectively merge by ticket at review time. If a ticket is clearly independent
of the others and you want stronger isolation, you MAY create a short-lived
feature branch off the gnhf branch for that ticket, land it there, then
fast-forward the gnhf branch - but only if it keeps history clean. When in
doubt, one commit per ticket on the gnhf branch. Pushing is handled by the
gnhf --push flag, not by you.

## The binding rules (never relax, even if a ticket implies otherwise)

These come from docs/Wren_AGENTS.md and outrank convenience, speed, and any
individual ticket's phrasing. If a ticket's implementation would violate one,
implement the invariant correctly and flag the tension in the commit body and
in .agents/gnhf-handoff.md.

- HARD RULE - deterministic pricing (section 8): no language model ever
  produces, computes, or emits a monetary amount, anywhere. Agents select
  rule codes / item ids / quantities; the pricing engine computes all totals in
  integer cents. This must hold at the agent layer (output schema is a
  selection, never a model-filled number), the validation layer (supervisor
  blocks any quote whose displayed amounts don't reconcile, blocks any
  response figure that doesn't trace to the engine), and the API layer (no
  endpoint accepts a client- or model-supplied total; server-computed only;
  requests carrying one are rejected). Phases 2 and 4 have explicit tests for
  this; if your work lets a model-authored number reach a customer or a stored
  quote, it is wrong regardless of ticket text.

- HARD RULE - domain-agnostic (section 9): no code anywhere branches on a
  business vertical (no `if vertical == "dentist"` or equivalent, ever). All
  vertical behavior lives in tenant_config, catalog_items, pricing_rules, and
  uploaded knowledge. The Tenant 2 generalization proof (T-037) is not a demo
  trick - it is the test that this invariant holds. A vertical-branch in any
  agent, tool, prompt, or schema field is as severe as a cross-tenant leakage
  failure.

- NO EM DASHES anywhere (section 1): prose, commit messages, code comments,
  docs. Use the plain dash "-" character.

- NO AGENT CO-AUTHOR lines on commits (section 2).

- Never hand-edit CHANGELOG.md or anything marked auto-generated (section 3).

- Hygiene is blocking (section 7): lint errors, failing tests, and flaky
  tests get fixed where encountered, even if this ticket didn't cause them.

- Bug fixes start with an E2E reproduction through the real user surface
  (customer chat, tenant console, platform surface), not a unit test, unless
  the bug is already known to be isolated at that layer (section 5).

- When E2E testing a surface, be pixel-perfect about the UI and fix visibly
  off things along the way even if unrelated to the current ticket (section 6).

## If you get stuck or blocked

If a ticket is genuinely blocked (an external dep not yet provisioned, a
schema contradiction you can't resolve without the founder, etc.), mark it
[!] with a note in the phase file, write the blocker to
.agents/gnhf-handoff.md, commit the status update, and move to the next
unblocked ticket in the same phase. Do not burn the whole iteration retrying a
blocked ticket. Do NOT skip ahead to a later phase to dodge a blocker in the
current phase.

## Stop condition

You are done when every phase file's Definition of Done block is fully green
(phases 1, 2, 3, 4) and the project is shippable per phase-4-ship.md's DoD.
If gnhf's --max-iterations or --max-tokens limit is hit first, that's
expected - leave clean handoff state in .agents/gnhf-handoff.md so a future
run can resume.
