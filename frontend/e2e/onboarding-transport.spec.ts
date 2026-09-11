import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { expect, test, type Locator } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";

/**
 * W-3: the onboarding thread's transport split (SSE for typed answers,
 * ordinary requests for chips/resume/uploads) and the pending-state cleanup
 * that rides on it - one indicator per turn, a steady composer, an upload
 * stamp that animates to an explicit outcome.
 *
 * Fully mocked, following the pattern in onboarding.spec.ts: page.route on
 * both `/api/onboarding/state` and `/api/knowledge/records` (the page's
 * mount does Promise.all over both), installed before loginAsTenantAdmin.
 */

const abnInput = {
  kind: "text",
  placeholder: "or type…",
  chips: [
    { label: "Yes", value: "yes", dashed: false, widget: null },
    { label: "No", value: "no", dashed: false, widget: null },
  ],
  mask: null,
  cta_label: null,
  prefix: null,
  suggest_owner_email: false,
};

const gstInput = {
  kind: "text",
  placeholder: "or type…",
  chips: [
    { label: "Yes", value: "yes", dashed: false, widget: null },
    { label: "Not yet", value: "not yet", dashed: false, widget: null },
  ],
  mask: null,
  cta_label: null,
  prefix: null,
  suggest_owner_email: false,
};

const FIRST_TOKEN = "Thanks for that.";
const FULL_REPLY = "Thanks for that. Are you registered for GST?";

async function noRecords(page: import("@playwright/test").Page) {
  await page.route("**/api/knowledge/records", (route) =>
    route.fulfill({ contentType: "application/json", body: "[]" }),
  );
}

async function heightOf(locator: Locator): Promise<number> {
  const box = await locator.boundingBox();
  if (!box) throw new Error("element has no box - is it visible?");
  return box.height;
}

/**
 * route.fulfill() delivers its whole body as one piece, which cannot prove a
 * client actually consumes SSE incrementally - React 18 batches every state
 * update queued inside one microtask into a single render, so a body that
 * arrives all at once would never show an intermediate frame at all. This
 * starts a real local HTTP server that writes the given frames one at a time
 * with a real delay between writes, and the caller redirects the intercepted
 * request to it with `route.continue({ url })` so the browser's stream reader
 * genuinely resolves once per frame - the same way the real backend's SSE
 * response does.
 */
async function startSseServer(
  frames: object[],
  delayMs: number,
): Promise<{ server: Server; url: string }> {
  const server = createServer((req, res) => {
    if (req.method === "OPTIONS") {
      res.writeHead(204, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers":
          req.headers["access-control-request-headers"] ?? "*",
      });
      res.end();
      return;
    }
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-cache",
    });
    void (async () => {
      for (const frame of frames) {
        res.write(`data: ${JSON.stringify(frame)}\n\n`);
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
      res.end();
    })();
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return { server, url: `http://127.0.0.1:${port}/stream` };
}

test("a typed answer streams incrementally, settles to one reply, and holds the composer's height", async ({
  page,
  request,
}) => {
  await page.route("**/api/onboarding/state", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        stage: "abn",
        prompt: "Do you have an ABN?",
        draft: { name: "Ronin", business_name: "Test Repairs" },
        completed: false,
        history: [{ role: "assistant", content: "Do you have an ABN?" }],
        input: abnInput,
        can_confirm: false,
        suggested_slug: "test-repairs",
        paused_beat: null,
      }),
    }),
  );
  await noRecords(page);

  const { server, url } = await startSseServer(
    [
      { type: "progress", stage: "processing" },
      { type: "token", text: FIRST_TOKEN },
      { type: "token", text: " Are you registered for GST?" },
      { type: "reply", text: FULL_REPLY },
      {
        type: "state",
        stage: "gst",
        draft: { name: "Ronin", business_name: "Test Repairs", abn: "51824753556" },
        completed: false,
        input: gstInput,
        can_confirm: false,
        suggested_slug: "test-repairs",
        paused_beat: null,
      },
      { type: "done" },
    ],
    400,
  );
  await page.route("**/api/onboarding/message/stream", (route) =>
    route.continue({ url }),
  );

  try {
    await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

    const thread = page.getByTestId("onboarding-thread");
    const composer = page.getByTestId("onboarding-composer");
    await expect(composer.getByTestId("onboarding-chip-yes")).toBeVisible();

    // Baseline: idle, on a chipped beat.
    const baseline = await heightOf(composer);

    await composer.getByRole("textbox").fill("Yes, ABN 51 824 753 556");
    await composer.getByRole("button", { name: "Send" }).click();

    // In flight: TypingLine's dots are the sole pending indicator - the
    // status line under the composer holds nothing (W-3 US-2) - and the
    // composer's height has not moved even though its chips just dropped out.
    await expect(page.getByTestId("thinking-dots")).toBeVisible();
    await expect(page.getByRole("status")).toHaveText("");
    expect(Math.abs((await heightOf(composer)) - baseline)).toBeLessThanOrEqual(1);

    // The first token has landed but not the second - a genuinely partial
    // reply is on screen, not yet the reconciled final text.
    await page.waitForTimeout(600);
    await expect(thread.getByText(FULL_REPLY, { exact: true })).toHaveCount(0);
    await expect(thread.getByText(FIRST_TOKEN, { exact: true })).toBeVisible();

    // Reconciliation lands exactly one assistant line for the turn.
    await expect(thread.getByText(FULL_REPLY, { exact: true })).toBeVisible({
      timeout: 5000,
    });
    await expect(thread.getByText(FULL_REPLY, { exact: true })).toHaveCount(1);

    // The next beat is chipped too, and the composer's height held through
    // the widget remount just as it did through the busy turn.
    await expect(composer.getByTestId("onboarding-chip-yes")).toBeVisible();
    expect(Math.abs((await heightOf(composer)) - baseline)).toBeLessThanOrEqual(1);

    await expect(page.getByTestId("onboarding-error")).toHaveCount(0);
  } finally {
    server.close();
  }
});

test("an upload stamp animates while pending and lands on an explicit outcome", async ({
  page,
  request,
}) => {
  const servicesInput = {
    kind: "text",
    placeholder: "",
    chips: [],
    mask: null,
    cta_label: null,
    prefix: null,
    suggest_owner_email: false,
  };
  await page.route("**/api/onboarding/state", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        stage: "services",
        prompt: "What do you offer?",
        draft: { name: "Ronin", business_name: "Test Repairs" },
        completed: false,
        history: [{ role: "assistant", content: "What do you offer?" }],
        input: servicesInput,
        can_confirm: false,
        suggested_slug: "test-repairs",
        paused_beat: null,
      }),
    }),
  );
  await noRecords(page);
  await page.route("**/api/knowledge/drafts/upload", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "draft-1",
        filename: "notes.txt",
        doc_type: "other",
        status: "draft",
        error: null,
        sections: [],
        offering_candidates: [],
      }),
    });
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const thread = page.getByTestId("onboarding-thread");
  await expect(thread).toBeVisible();

  await page.getByTestId("onboarding-file-input").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Open weekdays 9 to 6."),
  });

  // Pending: the stamp names the file and animates beside it.
  await expect(thread.getByText("notes.txt", { exact: true })).toBeVisible();
  await expect(page.getByTestId("thinking-dots")).toBeVisible();

  // Resolved: an explicit outcome, dots gone.
  await expect(thread.getByText("notes.txt · ready", { exact: true })).toBeVisible({
    timeout: 5000,
  });
  await expect(page.getByTestId("thinking-dots")).toHaveCount(0);
});

test("idle onboarding issues no conversation-state request", async ({ page, request }) => {
  const textInput = {
    kind: "text",
    placeholder: "",
    chips: [],
    mask: null,
    cta_label: null,
    prefix: null,
    suggest_owner_email: false,
  };
  await page.route("**/api/onboarding/state", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        stage: "business_type",
        prompt: "In a few words, what kind of business is it?",
        draft: { name: "Ronin", business_name: "Test Repairs" },
        completed: false,
        history: [
          { role: "assistant", content: "In a few words, what kind of business is it?" },
        ],
        input: textInput,
        can_confirm: false,
        suggested_slug: "test-repairs",
        paused_beat: null,
      }),
    }),
  );
  await noRecords(page);

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  await expect(page.getByTestId("onboarding-thread")).toBeVisible();
  await expect(page.getByTestId("onboarding-composer")).toBeVisible();

  let stateRequests = 0;
  await page.route("**/api/onboarding/state", (route) => {
    stateRequests += 1;
    return route.fulfill({ status: 500, body: "" });
  });
  await page.waitForTimeout(3000);
  expect(stateRequests).toBe(0);
});

test("an error ends the pending state and leaves the conversation usable", async ({
  page,
  request,
}) => {
  const textInput = {
    kind: "text",
    placeholder: "",
    chips: [],
    mask: null,
    cta_label: null,
    prefix: null,
    suggest_owner_email: false,
  };
  await page.route("**/api/onboarding/state", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        stage: "hours",
        prompt: "What days and hours are you open?",
        draft: { name: "Ronin", business_name: "Test Repairs" },
        completed: false,
        history: [{ role: "assistant", content: "What days and hours are you open?" }],
        input: textInput,
        can_confirm: false,
        suggested_slug: "test-repairs",
        paused_beat: null,
      }),
    }),
  );
  await noRecords(page);
  await page.route("**/api/onboarding/message/stream", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({
        type: "about:blank",
        title: "Internal Server Error",
        status: 500,
        detail: "The setup service is unavailable.",
        code: "upstream_error",
      }),
    });
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const composer = page.getByTestId("onboarding-composer");
  await composer.getByRole("textbox").fill("Weekdays 9 to 6");
  await composer.getByRole("button", { name: "Send" }).click();

  await expect(page.getByTestId("thinking-dots")).toBeVisible();

  await expect(page.getByTestId("onboarding-error")).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId("onboarding-error")).toHaveText(
    "The setup service is unavailable.",
  );
  await expect(page.getByTestId("thinking-dots")).toHaveCount(0);

  // The conversation is still usable - the composer is enabled and takes the
  // next answer rather than staying stuck on the failed turn.
  const textbox = composer.getByRole("textbox");
  await expect(textbox).toBeEnabled();
  await textbox.fill("Trying again");
  await expect(textbox).toHaveValue("Trying again");
});
