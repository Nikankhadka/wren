import { test } from "@playwright/test";
import { loginInChat } from "./auth-helpers";

/**
 * Not a regression test - the W-9 reproduction driver (conventions.md 5), run
 * against the real backend and a real LLM with a fresh (never-onboarded) email
 * so the interview starts at its opening beat. It replays the founder's
 * regression inputs through the real onboarding UI and keeps a screenshot per
 * turn plus the full thread text on stdout, as the evidence recorded in
 * docs/agencx/spec/evidence/w-9-reproduction.md. Excluded from the chromium
 * project the same way w7-screenshots.spec.ts is, so `make test-e2e` never
 * runs it. Saved into e2e/screenshots/.
 */

const SHOTS = "e2e/screenshots";

// The founder's regression inputs, in the order Amendment 3 records them.
const FIXTURES = [
  "211e2esdsdfasdf",
  "bkksbf88",
  "21 ej2nek2ne2ken1e",
  "sababa",
  "middle eastern cafe",
];

async function waitIdle(page: import("@playwright/test").Page) {
  // The composer is re-enabled (busy=false) once a turn settles.
  await page
    .getByTestId("onboarding-composer")
    .waitFor({ state: "visible", timeout: 30_000 })
    .catch(() => {});
  await page.waitForTimeout(4500);
}

async function thread(page: import("@playwright/test").Page): Promise<string> {
  return (await page.getByTestId("onboarding-thread").innerText()).trim();
}

/**
 * Wait for the streamed reply to finish arriving: the thread must no longer end
 * with the owner's own message, and must then hold still. A fixed pause is not
 * enough here - the screenshots are the evidence, so a shot taken mid-stream
 * would record an empty assistant line instead of the sentence under test.
 */
async function settle(page: import("@playwright/test").Page, sent: string) {
  const deadline = Date.now() + 60_000;
  let previous = "";
  let stableSince = 0;
  while (Date.now() < deadline) {
    await page.waitForTimeout(500);
    const now = await thread(page);
    const answered = !now.endsWith(sent);
    if (answered && now === previous) {
      if (!stableSince) stableSince = Date.now();
      else if (Date.now() - stableSince > 2500) return;
    } else {
      stableSince = 0;
    }
    previous = now;
  }
}

/** Send one owner message, wait for the turn, then log the whole thread. */
async function say(page: import("@playwright/test").Page, text: string) {
  const pill = page.getByRole("textbox").first();
  await pill.click();
  await pill.fill(text);
  await pill.press("Enter");
  await waitIdle(page);
  await settle(page, text);
  console.log(`\n===== OWNER: ${text}\n----- THREAD:\n${await thread(page)}\n`);
}

test("W-9 reproduction drive", async ({ page, request }) => {
  test.setTimeout(900_000);
  const email = `w9-${Date.now()}@founder.dev`;
  await loginInChat(page, request, email);
  await page.waitForURL("**/onboarding");
  await waitIdle(page);

  // The opening beat, before anything is typed.
  console.log(`\n===== OPENING\n${await thread(page)}\n`);
  await page.screenshot({ path: `${SHOTS}/w9-01-opening.png`, fullPage: true });

  // Failures 1 to 3: the junk inputs, the name "sababa", and the business type
  // "middle eastern cafe" - each turn gets its own screenshot.
  for (const [i, input] of FIXTURES.entries()) {
    await say(page, input);
    const n = String(i + 2).padStart(2, "0");
    await page.screenshot({ path: `${SHOTS}/w9-${n}-fixture-${i + 1}.png`, fullPage: true });
  }

  // Walk to the services beat.
  await say(page, "just me");
  await say(page, "9 to 5, Monday to Friday");

  // Failure 4: an unusable answer at the services beat sends the beat's own
  // example into the reply directive, and that example is salon-flavored
  // (backend/app/onboarding/beats.py:257) in a cafe onboarding.
  await say(page, FIXTURES[0]);
  await page.screenshot({ path: `${SHOTS}/w9-07-services-reask.png`, fullPage: true });

  await say(page, "pita, coffee, wraps");
  await say(page, "hello@sababa.dev");
  await say(page, "no");

  // Keep saying "skip" until the go-live address field appears - the knowledge
  // offer and the ABN/GST asks can each need an extra turn.
  const slug = page.getByTestId("onboarding-public-slug");
  for (let i = 0; i < 6; i++) {
    if (await slug.isVisible().catch(() => false)) break;
    await say(page, "skip");
  }
  await slug.waitFor({ timeout: 30_000 }).catch(() => {});

  // Failure 5: which name the go-live line uses.
  console.log(`\n===== FINAL THREAD\n${await thread(page)}\n`);
  await page.screenshot({ path: `${SHOTS}/w9-08-go-live.png`, fullPage: true });
});

test("W-9 sababa name doubling", async ({ page, request }) => {
  test.setTimeout(900_000);
  // A tighter drive for failure 1 alone: "sababa" answers the owner-name beat
  // and then the business-name beat, so the doubling gets two clean chances in
  // one interview. The founder's full input order is the test above.
  const email = `w9b-${Date.now()}@founder.dev`;
  await loginInChat(page, request, email);
  await page.waitForURL("**/onboarding");
  await waitIdle(page);

  await say(page, "sababa");
  await page.screenshot({ path: `${SHOTS}/w9-b1-owner-name-sababa.png`, fullPage: true });

  await say(page, "sababa");
  await page.screenshot({ path: `${SHOTS}/w9-b2-business-name-sababa.png`, fullPage: true });

  await say(page, "middle eastern cafe");
  await page.screenshot({ path: `${SHOTS}/w9-b3-middle-eastern-cafe.png`, fullPage: true });
});
