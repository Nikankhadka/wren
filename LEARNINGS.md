# LEARNINGS

What building Wren actually taught, per subsystem: what was learned, what
surprised, and what I would change. Written for a reader deciding whether the
engineering judgement here is sound - so it favors the honest wrinkle over the
tidy retrospective. The numbers referenced live in
[`docs/artifacts/eval-report.md`](docs/artifacts/eval-report.md); the security
claims in [`docs/artifacts/security.md`](docs/artifacts/security.md).

---

## Tenancy & RLS

**Learned.** Row-level security is only as strong as the role that connects.
The whole isolation guarantee rests on the app connecting as a *non-owner*
role (`wren_app`) with `FORCE ROW LEVEL SECURITY` on every table - because the
table-owning `postgres` role bypasses RLS silently. Getting that boundary
right up front (migrations `0002`-`0003`) meant every later feature inherited
isolation for free instead of re-litigating it.

**Surprised.** The pre-auth surface is the subtle part. Resolving a subdomain
to a tenant, or a JWT to a user, happens *before* any tenant context exists -
so it needs a sanctioned RLS bypass. The instinct is a broad service role; the
right answer was `SECURITY DEFINER` resolvers owned by a dedicated
`wren_resolver` with *column-level* grants, so the bypass can read exactly four
columns and cannot widen without a migration. Narrowing that surface felt
paranoid until you realize it is the one door RLS does not guard.

**Would change.** Nothing structural. If anything, I would write the
`test_schema_audit.py` sweep (which asserts every tenant table has FORCE RLS +
a policy) on day one rather than mid-phase - it is the cheapest possible guard
against forgetting the pattern on a new table, and it caught real gaps.

## RAG / retrieval

**Learned.** Hybrid retrieval (dense + sparse + RRF + rerank) is worth the
moving parts: on the golden set the cross-encoder reranker dominates final
ordering, and sparse FTS carried the whole thing even when dense embeddings
were still stubbed. Recall@5 = 1.000 is real, but it is a 50-case set - the
right way to read it is "the pipeline shape is sound", not "retrieval is
solved".

**Surprised - the bug I would put on a poster.** The single most instructive
defect in the whole build: two reranker backends returned scores on *different
scales* (Cohere a [0,1] probability, the local cross-encoder raw logits,
routinely negative for a genuinely relevant passage), and the knowledge agent
applied one absolute `score > 0.0` cutoff to both. The reranker was ranking the
correct chunk #1 and the gate then threw it away - so the *local* backend
refused almost everything while *Cohere* would have refused nothing, from
identical code. It presented as a model-quality problem ("the AI won't answer
in-domain questions") and was actually a scale-mismatch at an interface. The
lesson: when a contract crosses backends, the *units* are part of the contract.
Fixed by normalizing every reranker to a [0,1] probability (sigmoid over the
logit, monotonic so ranking is untouched) - see `test_rerank_normalization.py`.

**Would change.** Make the `Reranker` return type carry its units in the type
system from the start (a `RelevanceProbability` newtype), not a bare `float`. A
comment saying "[0,1]" did not exist until the bug forced it; a type would have.

## Agents (LangGraph orchestration)

**Learned.** A supervisor-plus-specialists graph earns its keep when the
routing decision is *auditable*. The high-value move was making the supervisor
return its own `route_reason` and forcing low-confidence to escalation **in
code** (`confidence < threshold`), not trusting the prompt to be cautious. Safety
rules belong in Python; the model advises, Python decides.

**Surprised.** LangGraph's streaming model. Token streaming out of a custom
(non-LangChain) provider needs `get_stream_writer()` + `stream_mode="custom"` -
the automatic `on_chat_model_stream` events only fire for LangChain-wrapped
chat models, which this codebase deliberately does not use. And `get_runtime()`
only works inside a running graph, so nodes cannot be unit-tested by calling
them directly - every node test drives the compiled graph. Both cost a session
to discover and are now in memory so they never do again.

**Would change.** I would introduce the "stub specialist becomes real logic
breaks the topology tests" trap earlier as an explicit rule. Three times, making
a placeholder node real broke order-assertions in `test_agent_graph.py` that had
been written against "stub == free pass-through". Re-run the *full* suite when a
stub grows teeth, never just the new node's test.

## Pricing (the deterministic engine)

**Learned.** The hard rule - no LLM ever authors a monetary amount - is only
credible if it is enforced in more than one place. It lives at three layers: the
model's selection schema has no money-shaped field, the validation gate rejects
any figure (including spelled-out ones like "twelve hundred") the engine did not
compute, and the API rejects non-positive rules. Defense in depth on the one
guarantee a business will never forgive being wrong.

**Surprised.** The threat was not the quoting agent - it was *onboarding*. The
generalization proof found pricing rules stored at $0.00 because a required
`float` field on an extraction schema gave the model no way to say "they never
gave a number", so it fabricated `0.0`, and the deterministic engine faithfully
quoted a real service as free. The model never "authored a price" in the sense
the rule polices, yet the number the engine read was still wrong. The fix -
`float | None` so absence is expressible, then re-ask or drop rather than zero -
generalized to a second case (a safety threshold fabricated from a prose
answer). **Lesson: a required numeric field on an LLM extraction schema is a
latent fabrication bug.** Make absence representable.

**Would change.** Audit every LLM-extraction schema in the codebase for
required scalars the user might not supply, proactively, rather than finding them
one production-shaped bug at a time.

## Eval

**Learned.** The three-layer split (retrieval / generation / trajectory) plus a
leakage layer is the right decomposition - each answers a different question and
fails for a different reason, so a single number never hides a regression in
another layer. The best decision was gating deterministic layers on an
*absolute* threshold and LLM-judged layers on a *regression* tolerance vs. the
previous run - because an LLM-judged absolute score depends on which model
answered, so a fixed pass-mark would either rubber-stamp regressions or perpetually
fail on the free dev model.

**Surprised.** How much the free-tier model bounds what you can *prove* live.
The machinery is sound and CI-green on stubs, but the LLM-judged numbers
(generation 0.48, trajectory 0.67) are free-tier numbers, and re-running them at
HEAD repeatedly aborted on upstream 429s. Also: an LLM judge that returns fewer
verdicts than claims silently shrinks the denominator toward a passing score -
you have to pad missing verdicts as fail-closed, or the judge's laziness reads as
your system's quality.

**Would change.** Provision a paid/Azure key before the eval phase, not after.
Half the eval learnings are really "free tier throttled the proof". Also, judge
calibration (T-024) genuinely cannot be closed by an agent - it needs a human to
label ground truth blind, or you are measuring two model calls agreeing with each
other. Build that human step into the schedule, not around it.

## Security

**Learned.** The signature result is the leakage test at 100% both directions,
and what makes it credible is not the pass - it is that its *teeth were proven*
by deliberately weakening a RLS policy and watching the tests go red. A green
test you have never seen fail is not evidence. Every positive control (attacker
queries its *own* secret) exists so a probe finding nothing cannot vacuously
pass.

**Surprised.** Prompt injection is a layered-probability game, not a solved
problem. Spotlighting (fencing untrusted tenant data in per-request random
delimiters) + an input scanner + the output inspection gate got 96.7% blocked on
the free model - and the residual miss is a poisoned chunk the free-tier *judge*
missed, i.e. the defense's weakest link was the cheap model grading it, not the
fencing. The most robust control was the least clever one: the order-status reply
is a deterministic template that never includes the free-text field, so a
poisoned order record is neutralized by construction, scoring 100%.

**Would change.** Nothing in the controls; I would add automated dependency
scanning to CI (deferred, honestly, in `security.md`) - it is a cheap CI
addition, not an architecture change, and it is the one classic-web gap left
open.

## Observability

**Learned.** Cost accounting wants to be stateless and task-local. A
contextvar-based per-turn usage sink lets the provider stay stateless while
concurrent turns never cross-contaminate their token counts. Tracing every graph
node via one wrapper (`_traced`) rather than editing eight node bodies kept the
instrumentation in one auditable place.

**Surprised.** The pathological turn was the invisible one. A turn that trips the
step cap makes *more* LLM calls than a normal turn, yet the original exception
handler returned without recording costs - so exactly the most expensive turns
were absent from the daily budget sum. The highest-usage path is the one most
likely to skip your accounting; instrument the error branches first.

**Would change.** Wire a real tracing backend (Langfuse) behind the existing
no-op Protocol earlier, even in dev, so the span-attribute whitelist decisions
(what content is safe to send one hop out from a leakage-sensitive system) get
exercised rather than reasoned about.

## Infra

**Learned.** Free-first is a real architecture stance, not a compromise. Every
paid seam (chat LLM, embeddings, reranker) swaps by config; the committed infra
(Postgres/RLS, LangGraph, FastAPI, Next.js) is deliberately *not* abstracted. The
production Docker image is lean by construction - the heavy `sentence-transformers`/`torch`
local-ML deps live in a `local-group` excluded from the image, so ECS binds to
hosted embedder/reranker providers.

**Surprised.** The cheapest cloud decision was *removing* a component: no NAT
gateway (public subnet + strict security groups instead) avoids ~$32/mo, which
on a solo portfolio budget is most of the bill. And the `.dockerignore` was
load-bearing security, not hygiene - without it a local build bakes real `.env`
secrets and the host `.venv` into the image. Caught by review, not by me the
first time.

**Would change.** Local state for Terraform is right at solo scope but is the
first thing to migrate (to S3 + DynamoDB lock) the moment a second person
touches infra. Flag it now so it is a decision, not a discovery.

---

## The one meta-lesson

Every subsystem's most instructive moment was the same shape: a control that
looked fine because it had never been made to fail. The reranker gate that
"worked" on one backend, the leakage tests that were green but toothless, the
cost accounting that skipped its worst case, the required-float that only broke
on a second vertical. The build's real discipline was not writing the controls -
it was deliberately breaking each one to confirm it bites. A green check you have
never watched go red is a hypothesis, not a guarantee.
