> **NAVIGATION:** Evidence record for W-9. Read it with the ticket in
> [13-walkthrough.md](../active/13-walkthrough.md) and its
> [Amendment 3](../active/13-walkthrough.md#amendment-3-the-agent-contract-2026-09-06).

# W-9 reproduction record

This is the reproduction step [conventions.md section 5](../../design/conventions.md#5-bug-fix-protocol)
requires before any W-9 fix lands. Nothing under `backend/app/` or
`frontend/src/` was changed to produce it. Five of the six failures W-9 exists
to close reproduce through the real onboarding UI; the sixth reproduces through
a deterministic check, and one of the five does not reproduce for a structural
reason recorded below.

Quoted assistant text is verbatim, including its em dashes. Those em dashes are
the model's own output against a repo that bans them in copy, and they are
recorded as observation 4 rather than edited away.

## What you ran

The Docker stack was already up (`db`, `auth`, `auth-proxy`, `backend`,
`frontend`, `mailpit`) with a real provider configured (Google Gemini primary,
Groq fallback). The demo world was already seeded, so `make seed` was not
re-run.

1. Drive the interview. The spec is excluded from the default `chromium`
   project in [`frontend/playwright.config.ts`](../../../../frontend/playwright.config.ts)
   the same way `w7-screenshots.spec.ts` is, so `make test-e2e` never runs it.
   The Playwright CLI cannot override `testIgnore`, so the run used a
   throwaway config, deleted afterwards:

   ```
   cat > frontend/playwright.w9.config.ts <<'EOF'
   import { devices } from "@playwright/test";
   import base from "./playwright.config";

   export default {
     ...base,
     projects: [
       { name: "w9", use: { ...devices["Desktop Chrome"] }, testMatch: /w9-repro\.spec\.ts/ },
     ],
   };
   EOF

   docker compose --profile e2e run --rm e2e sh -c 'socat TCP-LISTEN:3000,fork,reuseaddr,bind=127.0.0.1 TCP:frontend:3000 & socat TCP-LISTEN:8000,fork,reuseaddr,bind=127.0.0.1 TCP:backend:8000 & socat TCP-LISTEN:54321,fork,reuseaddr,bind=127.0.0.1 TCP:auth-proxy:80 & socat TCP-LISTEN:8025,fork,reuseaddr,bind=127.0.0.1 TCP:mailpit:8025 & exec "$@"' -- npx playwright test --config=playwright.w9.config.ts --reporter=list
   ```

2. Count the owner's message in the reply context. The probe below ran inside
   the backend container and was deleted after its output was recorded here.

Both tests in [`frontend/e2e/w9-repro.spec.ts`](../../../../frontend/e2e/w9-repro.spec.ts)
sign up a fresh tenant admin through the login-in-chat OTP flow, so each drive
starts at the opening beat. The demo seed tenants are already onboarded and
cannot be used for this.

## Transcript A: the founder's regression inputs

Test `W-9 reproduction drive`, one interview, owner input followed by the
assistant's reply. Turns 6 to 12 are the walk to the go-live line and are not
part of the founder's fixture set.

| # | Owner | Assistant |
|---|---|---|
| 0 | (opening, nothing typed) | Hi! I'm your Agencx setup assistant. I'll help you get your business ready. First - what should I call you? I'll ask about the business next. |
| 1 | `211e2esdsdfasdf` | No worries at all, Nikan! First - what should I call you? I'll ask about the business next. |
| 2 | `bkksbf88` | Don't worry about my name for now—let's just sort it out as we go! What does the business go by? |
| 3 | `21 ej2nek2ne2ken1e` | Got it, thanks! In a few words, what kind of business is it? |
| 4 | `sababa` | Got it, thanks for sharing that! Is it just you, or do you work with a team? |
| 5 | `middle eastern cafe` | It's just me. Is it just you, or do you work with a team? |
| 6 | `just me` | Got it, just you running the show! What days and hours are you open? |
| 7 | `9 to 5, Monday to Friday` | Got it—open Monday through Friday from 9 to 5! What would you like customers to know you offer? |
| 8 | `211e2esdsdfasdf` | No worries if that was a test, but a short list of your main services is plenty—like haircuts, colours, and beard trims! What would you like customers to know you offer? |
| 9 | `pita, coffee, wraps` | Fresh pitas, hot coffee, and delicious wraps sound like the ultimate combination to keep everyone coming back! How should customers reach you? |
| 10 | `hello@sababa.dev` | Got it, I've saved hello@sababa.dev for your contact details! Do you have an ABN? |
| 11 | `no` | Your assistant for 21 ej2nek2ne2ken1e is ready to go live. Hit confirm to publish it. Do you have a website or any documents - a menu, price list, or FAQs? You can paste a link, attach a file, or say "skip". Anything you save becomes a reference I can use when answering your customers, and you can add more any time from Settings. |
| 12 | `skip` | Your assistant for 21 ej2nek2ne2ken1e is ready to go live. Hit confirm to publish it. |

At turn 3 the business-name beat accepted `21 ej2nek2ne2ken1e` (it contains a
word, so `_wordish` at [`beats.py:142-148`](../../../../backend/app/onboarding/beats.py#L142-L148)
passes it), which is why `sababa` landed on the business-type beat at turn 4
and why the go-live line reads back a junk business name. `middle eastern cafe`
at turn 5 was never captured at all.

## Transcript B: sababa on both name beats

Test `W-9 sababa name doubling`, a second interview, driven so that `sababa`
answers the owner-name beat and then the business-name beat.

| # | Owner | Assistant |
|---|---|---|
| 0 | (opening, nothing typed) | Hi! I'm your Agencx setup assistant. I'll help you get your business ready. First - what should I call you? I'll ask about the business next. |
| 1 | `sababa` | It's wonderful to meet you, sababasababa! What does the business go by? |
| 2 | `sababa` | It's wonderful to connect with you, Sababasababa! In a few words, what kind of business is it? |
| 3 | `middle eastern cafe` | That sounds delicious and cozy! Is it just you, or do you work with a team? |

## Deterministic check for the duplicated owner message

`prepare_turn` appends the owner's message to `record.history`
([`agent.py:690`](../../../../backend/app/onboarding/agent.py#L690)), the
`history[-3:]` slice at [710-711](../../../../backend/app/onboarding/agent.py#L710)
therefore includes it, and [712](../../../../backend/app/onboarding/agent.py#L712)
appends it a second time. A browser screenshot cannot show the context the
model receives, so this was measured directly with a fake provider modeled on
`_ExtractFake` in [`test_onboarding_agent.py`](../../../../backend/tests/test_onboarding_agent.py).

The probe (written to `backend/w9_dup_check.py`, run with
`docker compose run --rm --no-deps backend python w9_dup_check.py`, then
deleted):

```python
class _Fake(BaseFakeProvider):
    async def extract(self, *, system_prompt, user_input, schema):
        return schema.model_validate(
            {"business_type": "middle eastern cafe", "off_topic": False, "answered_asked": True}
        )

    async def chat(self, messages): return "Got it."

    async def chat_stream(self, messages): yield "Got it."


record = OnboardingRecord(
    draft={"name": "Nikan", "business_name": "sababa"},
    history=[
        {"role": "user", "content": "sababa"},
        {"role": "assistant", "content": "Sababasababa is such a fun name! ..."},
    ],
    ask_beat="business_type",
    ask_count=1,
)
plan = await prepare_turn(admin_message="middle eastern cafe", record=record, provider=_Fake())
count = sum(1 for m in plan.reply_msgs or [] if m.get("content") == "middle eastern cafe")
```

Output:

```
reply_msgs entries: 6
  system: "You are the owner's Agencx setup assistant, helping a small-business owner set u"
  system: 'Compose reply. They have not answered this yet. In one short line encourage them'
  user: 'sababa'
  assistant: 'Sababasababa is such a fun name! In a few words, what kind of business is it?'
  user: 'middle eastern cafe'
  user: 'middle eastern cafe'
OWNER MESSAGE 'middle eastern cafe' APPEARS 2 TIME(S) IN reply_msgs
```

## Findings

| # | Failure | Verdict | Evidence |
|---|---|---|---|
| 1 | `sababa` given as a name comes back concatenated as `Sababasababa` | REPRODUCED | Transcript B turn 1: "It's wonderful to meet you, sababasababa!" and turn 2: "It's wonderful to connect with you, Sababasababa!" - `w9-b1-owner-name-sababa.png`, `w9-b2-business-name-sababa.png` |
| 2 | The assistant defers "my name" to later, or uses ambiguous "my name" phrasing | REPRODUCED | Transcript A turn 2: "Don't worry about my name for now—let's just sort it out as we go!" - the assistant says "my name" about the owner's name, and defers it - `w9-03-fixture-2.png` |
| 3 | Subjective praise or fabricated enthusiasm for `middle eastern cafe` | REPRODUCED | Transcript B turn 3: "That sounds delicious and cozy!" - `w9-b3-middle-eastern-cafe.png`. Transcript A turn 9 carries the same fabrication for the offerings: "Fresh pitas, hot coffee, and delicious wraps sound like the ultimate combination to keep everyone coming back!" - `w9-08-go-live.png` |
| 4 | Salon-flavored example text leaks into a cafe onboarding | REPRODUCED | Transcript A turn 8: "a short list of your main services is plenty—like haircuts, colours, and beard trims!" - the services beat's own example at [`beats.py:257`](../../../../backend/app/onboarding/beats.py#L257) reaching the owner verbatim - `w9-07-services-reask.png` |
| 5 | The owner's own name is reused as the business name on the go-live line | NOT REPRODUCED | The go-live line read "Your assistant for 21 ej2nek2ne2ken1e is ready to go live" - the captured `business_name`, not the owner's name (`w9-08-go-live.png`). The fallback at [`agent.py:268-274`](../../../../backend/app/onboarding/agent.py#L268-L274) is unreachable from the UI today: `_activation_summary` runs only when `_advance` returns `None` ([`agent.py:714-719`](../../../../backend/app/onboarding/agent.py#L714)), and `business_name` is a required beat that `next_beat` keeps returning until it holds a value, so `business_name` is always set by the time the line renders. The conflation is real in the code and still has to be removed, but it is latent, not user-visible on this path |
| 6 | The owner's message appears twice in what the model sees | REPRODUCED | `OWNER MESSAGE 'middle eastern cafe' APPEARS 2 TIME(S) IN reply_msgs`, with `reply_msgs` ending in two identical `user` entries - see the deterministic check above |

## Other observations from the same drives

1. **The beat example is read back as the owner's name.** Transcript A turn 1
   answered junk with "No worries at all, Nikan!" - `Nikan` comes from the
   name beat's own example (`just a first name is plenty - "Nikan"`,
   [`beats.py:196`](../../../../backend/app/onboarding/beats.py#L196)), which
   the reask directive interpolates at
   [`agent.py:660-664`](../../../../backend/app/onboarding/agent.py#L660). The
   assistant addressed the owner by a name the owner never gave. This is the
   same defect as finding 4 on a different beat, so a fix that only makes the
   services example domain-neutral leaves this half open.
2. **The assistant answers its own pending question.** Transcript A turn 5
   replied "It's just me. Is it just you, or do you work with a team?" - the
   model invented the owner's answer, and the server-owned question was then
   appended after it.
3. **Junk reaches the public identity.** `21 ej2nek2ne2ken1e` passed the
   business-name beat and became the go-live name, the read-back line ("Going
   live as 21 ej2nek2ne2ken1e."), and the suggested address
   (`agencx.app/21-ej2nek2ne2ken1e`) - visible in `w9-08-go-live.png`. The
   confirmation step US-1 asks for is what closes this.
4. **The assistant emits em dashes.** "now—let's", "Got it—open", and
   "plenty—like" all appear in transcript A, against the repo's own copy rule.
5. **`middle eastern cafe` was dropped.** In transcript A the business type on
   file is `sababa`; the phrase the owner typed at turn 5 was captured nowhere.

The `Review your information` panel visible at the foot of every full-page
screenshot is a capture artifact: the review sheet is fixed-position, and a
`fullPage` shot renders it at the bottom of the expanded document. It is not
open during the interview.

## Run-to-run variation

The provider is live, so the interview differs between runs. Three drives of
transcript A ran in this session. Findings 2, 3, and 4 appeared in all three;
finding 1 appeared in the first drive ("Sababasababa is such a fun and
memorable name!") and in both turns of transcript B, and not in the third
drive of transcript A, where `sababa` landed on the business-type beat instead
of a name beat. Finding 3 was stronger in the earlier drives ("A Middle
Eastern cafe sounds wonderful and so inviting!", "It's wonderful to bring your
Middle Eastern cafe vision to life all on your own!"). Only the final drive is
screenshotted; the earlier quotes are recorded here without screenshots and
should be read as supporting, not as the primary record.

## Screenshot index

All under [`frontend/e2e/screenshots/`](../../../../frontend/e2e/screenshots),
beside the W-7 walkthrough set.

| File | Shows |
|---|---|
| `w9-01-opening.png` | The opening beat before anything is typed |
| `w9-02-fixture-1.png` | After `211e2esdsdfasdf` - the "Nikan" read-back |
| `w9-03-fixture-2.png` | After `bkksbf88` - finding 2 |
| `w9-04-fixture-3.png` | After `21 ej2nek2ne2ken1e` - junk accepted as the business name |
| `w9-05-fixture-4.png` | After `sababa` |
| `w9-06-fixture-5.png` | After `middle eastern cafe` - the assistant answering its own question |
| `w9-07-services-reask.png` | The services beat reask - finding 4 |
| `w9-08-go-live.png` | The go-live line, read-back, and address - finding 5, and finding 3's offerings copy |
| `w9-b1-owner-name-sababa.png` | `sababa` on the owner-name beat - finding 1 |
| `w9-b2-business-name-sababa.png` | `sababa` on the business-name beat - finding 1 |
| `w9-b3-middle-eastern-cafe.png` | Praise for `middle eastern cafe` - finding 3 |
