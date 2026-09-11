/**
 * E2E for the failover typing indicator (P-5).
 *
 * Surface: customer (/<slug>)
 *
 * The ticket's promise is about continuity: the indicator is up from send
 * until the first inspected token, and nothing in between interrupts it - not
 * the progress events, and not P-2's provider race, which is decided
 * server-side and streams nothing while it runs.
 *
 * The turns here are scripted through page.route rather than driven against a
 * live provider. That is deliberate: what is under test is the client's turn
 * lifecycle, and a free-tier LLM would make the timing - the whole point -
 * non-deterministic. Live turns are covered elsewhere.
 *
 * Since M-4 the customer page is a storefront and the conversation lives in a
 * sheet, so every turn here starts by opening it. What is under test is
 * unchanged: the sheet holds the same `CustomerChat`.
 */

import { test, expect, type Page } from "@playwright/test";

const SLUG = "bytefix";
const CUSTOMER_URL = `/${SLUG}`;

const sse = (...events: object[]) =>
  events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");

/** Land on the storefront and open the conversation sheet (M-4). */
async function openChat(page: Page) {
  await page.goto(CUSTOMER_URL);
  await page.getByRole("button", { name: "Chat with Bytefix" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

async function ask(page: Page, question = "What do you charge for a screen?") {
  // `next dev` streams this page, and for a beat after load the server tree
  // and the client tree are both in the DOM - two composers, and a strict-mode
  // violation for anything addressing one of them. Settling first is what a
  // customer does anyway; nothing here is testing the first 30ms.
  //
  // A one-shot `toHaveCount(1)` before the fill is not enough: the count goes
  // 1 -> 2 -> 1 as hydration lands, so a guard that passes can be stale by the
  // time `fill` re-resolves the locator. Retrying the pair together is what
  // actually waits for the page to settle.
  await expect(async () => {
    const box = page.getByLabel("Message");
    await expect(box).toHaveCount(1);
    await box.fill(question);
  }).toPass({ timeout: 15_000 });
  await page.getByRole("button", { name: "Send" }).click();
}

test.describe("the typing indicator spans the turn", () => {
  test("it is up the moment the customer sends, before anything comes back", async ({ page }) => {
    // A turn that never answers: the indicator must still be up.
    await page.route("**/api/chat", async (route) => {
      await new Promise((r) => setTimeout(r, 3000));
      await route.fulfill({ status: 200, body: "" });
    });

    await openChat(page);
    await ask(page);

    await expect(page.getByTestId("thinking-dots")).toBeVisible();
    // Still up well past the 4s TTFT budget's first beat - a slow primary is
    // exactly the case this has to survive.
    await page.waitForTimeout(1200);
    await expect(page.getByTestId("thinking-dots")).toBeVisible();
  });

  test("progress events do not interrupt it", async ({ page }) => {
    // Stages arrive and the stream ends without a token. Progress stages carry
    // no customer-facing copy at all now - only the bubble's pulsing dots may
    // speak for the wait.
    await page.route("**/api/chat", (route) =>
      route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: sse(
          { type: "conversation", conversation_id: "11111111-1111-4111-8111-111111111111" },
          { type: "progress", stage: "routing" },
          { type: "progress", stage: "answering" },
          { type: "progress", stage: "checking" },
        ),
      })
    );

    await openChat(page);
    await ask(page);

    // Three stages later, still one unbroken indicator.
    await expect(page.getByTestId("thinking-dots")).toBeVisible();
    await expect(page.getByTestId("thinking-dots")).toHaveCount(1);

    // No stage label reaches the customer anywhere on the page - it would read
    // as a half-answer in the bubble, and there is no separate status line for
    // it to speak in any more.
    const pageText = await page.locator("main").innerText();
    for (const label of [
      "Understanding your question",
      "Finding an answer",
      "Checking the answer",
    ]) {
      expect(pageText).not.toContain(label);
    }
  });

  test("the first token swaps it for the answer, never both at once", async ({ page }) => {
    await page.route("**/api/chat", (route) =>
      route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: sse(
          { type: "conversation", conversation_id: "11111111-1111-4111-8111-111111111111" },
          { type: "progress", stage: "answering" },
          { type: "token", text: "A screen repair is " },
          { type: "token", text: "$129." },
          { type: "done" }
        ),
      })
    );

    await openChat(page);
    await ask(page);

    await expect(page.getByText("A screen repair is $129.")).toBeVisible();
    await expect(page.getByTestId("thinking-dots")).toHaveCount(0);
  });

  test("a redraft returns to the indicator rather than showing a half-retracted answer", async ({
    page,
  }) => {
    // The price gate rejected the first draft. The customer should see the
    // assistant thinking again, not the rejected sentence sitting there.
    await page.route("**/api/chat", (route) =>
      route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: sse(
          { type: "conversation", conversation_id: "11111111-1111-4111-8111-111111111111" },
          { type: "token", text: "It costs about $200" },
          { type: "redraft" },
          { type: "token", text: "A screen repair is $129." },
          { type: "done" }
        ),
      })
    );

    await openChat(page);
    await ask(page);

    await expect(page.getByText("A screen repair is $129.")).toBeVisible();
    await expect(page.getByText("about $200")).toHaveCount(0);
  });

  test("the mechanics never surface: no provider, no switch notice, no spinner", async ({
    page,
  }) => {
    // P-2 races two providers behind this indicator. None of that vocabulary
    // may reach the customer - the trace and cost surfaces own it.
    await page.route("**/api/chat", (route) =>
      route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream" },
        body: sse(
          { type: "conversation", conversation_id: "11111111-1111-4111-8111-111111111111" },
          { type: "progress", stage: "answering" },
          { type: "token", text: "We are open until 6pm." },
          { type: "done" }
        ),
      })
    );

    await openChat(page);
    await ask(page);
    await expect(page.getByText("We are open until 6pm.")).toBeVisible();

    // innerText, not textContent: the latter drags in Next's dev-mode RSC
    // payload scripts, which mention "provider" for AuthProvider and would
    // fail this on framework internals the customer never sees.
    const visible = (await page.locator("main").innerText()).toLowerCase();
    for (const word of ["provider", "failover", "switching", "fallback", "gemini", "groq", "openrouter"]) {
      expect(visible, `"${word}" must not reach the customer`).not.toContain(word);
    }
    // "Retry" is deliberately absent from this list - inline retry IS the
    // specified error affordance (US-2), it just has no place in a good turn.
    expect(visible).not.toContain("retry");
  });
});

test.describe("reduced motion", () => {
  test("the dots hold their place without pulsing", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.route("**/api/chat", async (route) => {
      await new Promise((r) => setTimeout(r, 3000));
      await route.fulfill({ status: 200, body: "" });
    });

    await openChat(page);
    await ask(page);

    const dots = page.getByTestId("thinking-dots");
    await expect(dots).toBeVisible();

    // The global guard collapses the animation rather than removing it, so the
    // indicator still occupies its space and the layout does not shift.
    const seconds = await dots
      .locator("span")
      .first()
      .evaluate((el) => parseFloat(getComputedStyle(el).animationDuration));
    expect(seconds).toBeLessThan(0.001);
  });
});
