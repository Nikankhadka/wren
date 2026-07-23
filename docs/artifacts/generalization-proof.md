# Generalization proof: Tenant 2 by config alone (T-037)

**Claim under test.** Wren's domain-agnostic hard rule says no code branches
on a business vertical, anywhere - all vertical behavior lives in
`tenant_config` and uploaded knowledge. The test of that claim is whether a
business with nothing in common with the anchor tenant can be brought live
through the same doors, with no code written for it.

**Result.** A dental clinic (`northgate`, "Northgate Family Dental") is live
on identical code, provisioned entirely through the public API: signup, a
six-question onboarding conversation, and three uploaded documents. No
direct database writes, no schema change, and no vertical branch anywhere in
the codebase.

The run was not clean on the first attempt. It surfaced two real platform
defects, both of which were fixed domain-agnostically before the proof was
re-run. That is recorded in full below rather than smoothed over - a proof
that only reports its successful final pass is not evidence of anything.

## How it was provisioned

`backend/seeds/seed_tenant2_dental.py` is deliberately not a seed in the
sense the other files in `backend/seeds/` are. `seed_tenant1_phoneshop.py`
and `seed_demo.py` write rows directly; this one never touches the database
on the provisioning path. It drives exactly the calls a business owner's
browser makes:

| Step | Call | Result |
|---|---|---|
| Sign up the owner | GoTrue `POST /auth/v1/signup` | auth user `owner@northgate.test` |
| Create the tenant | `POST /api/tenants` | slug `northgate` |
| The conversation | `POST /api/onboarding/message` x7 | six stages, one re-ask (below) |
| Go live | `POST /api/onboarding/confirm` | 29 catalog items, 5 pricing rules |
| Upload knowledge | `POST /api/knowledge/upload` x3 | 3 documents, 35 chunks total |

The words posted at each stage are in
`backend/seeds/tenant2_inputs/interview-script.md` - the script is the
single source of truth, parsed from its fenced blocks, so what a reader sees
is exactly what was sent. The three knowledge documents (clinic policies,
services and fees, FAQ) are in the same directory and are what a real
practice would already own.

Re-runnable: `--teardown` removes a previous run. That flag is the one path
in the file that touches the database directly, and it is not part of the
proof - it only undoes one.

Final state: `catalog_items=29 pricing_rules=5 documents=4 (3 uploaded + the
generated catalog document) chunks=35 escalation_threshold=0.75`.

## The two defects it found

Both are the same failure shape, and neither is dental-specific - they were
simply invisible until a business described itself in words the anchor
tenant's seed script never had to. A required numeric field on an extraction
schema gives the model no way to say "they described this but never gave a
number", so it fabricates one, and the fabricated value is silently
authoritative.

### 1. Pricing rules persisted at $0.00

The owner named two rules in the pricing stage - deep cleaning charged per
quadrant, wisdom teeth per tooth - without repeating the amounts they had
already given a question earlier. `PricingRuleDraft.unit_amount_dollars` was
a required `float`, so the model filled in `0.0`, and both rules were
written to `pricing_rules` at `unit_amount_cents = 0`.

This directly attacks the project's centerpiece guarantee. The pricing
engine is deterministic and trusts its inputs: a rule stored at zero makes
it correctly compute a real service as free. No LLM authored a price - the
hard rule held - but the number the engine read was still wrong.

**Fix** (`app/onboarding/flow.py`, `app/api/onboarding.py`): the amount is
now `float | None`, so absence is expressible. A stage whose answer is
understood but incomplete no longer advances - the flow stays put and asks
for the missing amounts by name, carrying the rules captured so far into the
follow-up extraction so the reply can return the complete corrected set.
Re-asks are bounded (`_MAX_PRICING_FOLLOWUPS`); if an amount still never
arrives, the unpriced rule is dropped rather than stored at zero, and is
addable with a real price in the Pricing tab. `POST /api/onboarding/confirm`
rejects any non-positive rule outright as defence in depth.

One detail worth recording, because it defeated the first fix: merging the
follow-up's rules into the prior ones by `code` does not work. The model
renames codes between turns (`wisdom_teeth` one turn,
`wisdom_tooth_removal` the next), so the unpriced original survives every
merge and the stage never converges. Feeding the running set back into the
extraction and asking for the complete list is what actually terminates.

### 2. Escalation threshold fabricated from a prose answer

`EscalationDraft.threshold` was a required `float`. Asked when to hand off
to a human, the owner answered in words - "be cautious, anything clinical
goes to a human, if you're not sure hand it over" - and named no number. The
model invented one. Across two runs it produced `0.0` and then `1.0`.

`0.0` is the dangerous one: the supervisor escalates when
`confidence < threshold`, so zero means *never escalate on low confidence* -
precisely inverting a request for caution, in the safety-relevant direction,
silently. `1.0` inverts it the other way and escalates everything.

**Fix**: the model now reports a `posture` it can actually transcribe from
what was said (`rarely` / `balanced` / `cautious`), and `resolve_threshold()`
maps that to a number in Python. An explicit in-range number is still
honored if the admin genuinely gave one; otherwise the posture decides;
otherwise the column default (0.5) stands. The model no longer authors the
number - the same principle the pricing rule already applied to money, now
applied to the one other number onboarding stores.

After the fix the clinic's "be cautious" answer resolves to `0.75`, and no
pricing rule carries a non-positive amount.

## Verification against the live tenant

Run through `POST /api/chat` against the real graph, free-tier model
(`google/gemma-4-26b-a4b-it:free`).

| Check | Question | Outcome |
|---|---|---|
| Engine quote | "Price for wisdom tooth removal for two teeth?" | Quote, 2 x $420 = **$840**, engine-computed | 
| Engine quote | "How much would a deep clean of my whole mouth cost?" | Quote produced, but **quantity 1, not 4** - see misses |
| Out-of-domain | "Do you fix cracked phone screens?" | Declined cleanly |
| Cross-tenant | "How much does Bytefix charge for a battery replacement?" | Declined; no tenant-1 data surfaced |
| Clinical | "I have a swollen jaw, do I need a root canal?" | Escalated to a human, as configured |
| In-domain knowledge | "What is your cancellation policy?" | **Refused / escalated** - see misses |

## Honest misses

**A retrieval bug this surfaced - since fixed.** Several in-domain questions
to the clinic (cancellation policy, children) and to `bytefix` (warranty
policy) were refused with "I don't have information about that" despite the
answer being plainly in the uploaded documents. Diagnosing it turned up a
real, model-independent defect, not free-tier quality: the local cross-
encoder reranker returns raw logits (routinely negative for a genuinely
relevant passage), while the Cohere backend returns a [0, 1] probability, and
the knowledge agent applied one absolute `score > 0.0` cutoff to both. The
reranker was ranking the correct chunk **#1** - "warranty policy" -> the
policy.md Warranty passage at logit -0.11, "treat children" -> the right FAQ
chunk at -1.45 - and the gate then threw the #1 result away. On the local
backend it refused almost everything; on Cohere the same cutoff would have
refused nothing. Fixed by making the Reranker contract return a normalized
[0, 1] relevance probability on every backend (sigmoid over the cross-encoder
logit) and setting the refusal threshold to 0.05, which sits in the wide gap
between correctly-ranked matches (0.19-0.95) and noise (< 0.002). After the
fix the previously-refused chunks retrieve and reach the model; "where can I
park", whose best chunk scores 0.0004, still correctly refuses - a genuine
retrieval miss where the parking sentence was buried in a large chunk. See
`app/retrieval/rerank.py`, `app/agents/knowledge.py`,
`tests/test_rerank_normalization.py`.

**What remains is genuinely the free model.** With retrieval fixed, the
correct chunk now reaches generation, but some answers are still bounced by
the T-021 inspection/grounding gate on the weak free model (the refusal text
changes accordingly, from "I don't have information about that" - the
retrieval refusal - to "I wasn't able to put together a reliable answer" -
the post-inspection handoff), and the free endpoint drops streams under load.
This affects both tenants equally, so it is the known generation-quality gap,
not a generalization failure. End-to-end answer quality for either tenant
stays unproven until a stronger model is provisioned.

Worth noting which way it fails: every miss refused or escalated. None
invented an answer.

**Quote quantity.** "Deep clean of my whole mouth" produced a one-quadrant
quote ($130) where the clinic's own documents say a full mouth is four
quadrants ($520). The engine computed its input correctly and no price was
model-authored; the agent selected the wrong quantity. This is a trajectory
accuracy miss of the kind T-026 measures, on the free model.

## The domain-agnostic evidence

`grep -rniE "dental|dentist|tooth|teeth|clinic|quadrant|phone|repair" backend/app frontend/src`
returns only:

- docstrings and comments using them as examples (including the two written
  during this ticket, which name dental terms precisely because that is
  where the bug was found),
- marketing copy that deliberately names the demo tenants, and
- test fixture names.

Zero hits are conditionals. No function, route, prompt, or schema branches
on what kind of business a tenant is.

The code changed during this ticket is the honest caveat to "zero code
changes": two files were edited (`app/onboarding/flow.py`,
`app/api/onboarding.py`). Neither edit mentions dentistry or adds a vertical
branch - both remove a way for the model to fabricate a number, which was
always a bug and would have bitten a plumber or a caterer identically. The
claim the proof supports is the accurate one: **bringing up a second
vertical required no vertical-specific code**, and the platform defects it
exposed were general.

## Reproducing

```bash
scripts/demo.sh                                   # stack up
cd backend
uv run python -m seeds.seed_tenant2_dental --teardown
uv run python -m seeds.seed_tenant2_dental
```

The script fails loud on any step the public API cannot complete, on the
principle that a workaround in the driver would defeat the thing being
proved.
