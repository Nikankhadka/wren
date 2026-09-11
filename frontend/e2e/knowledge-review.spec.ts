import { expect, test, type Page } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";
import {
  MIDDLE_DOT,
  draftRecord,
  offeringCandidate,
  recordsStore,
  stubBatch,
  stubOnboardingState,
  stubRecords,
  stubUpload,
  uploadFilePayloads,
} from "./knowledge-review-mocks";

/**
 * W-11c: the combined document review on desktop - bounded-concurrency batch
 * upload, the five-file cap, stored failures, the ready card with W-11b edit
 * retention, safe replace, offering reconciliation, batch publish with a
 * partial failure, and pagination/toolbar behavior.
 *
 * Fully mocked, following the pattern in onboarding-transport.spec.ts:
 * page.route on `/api/onboarding/state` and `/api/knowledge/records` (the
 * page's mount does Promise.all over both), installed before
 * loginAsTenantAdmin. Upload, batch and DELETE routes are stateful stubs the
 * tests assert against.
 */

const PRIVACY_LINE =
  "Your documents stay private to your business, and nothing answers customers until you review and save it.";

const FIVE_NAMES = ["menu.txt", "hours.txt", "policies.txt", "notes.txt", "faq.txt"];
const SEVEN_NAMES = [...FIVE_NAMES, "extra6.txt", "extra7.txt"];

function dialog(page: Page) {
  return page.getByRole("dialog", { name: "Review your information" });
}

test("uploads five files three at a time and opens one combined review", async ({
  page,
  request,
}) => {
  const store = recordsStore([]);
  await stubOnboardingState(page, { stage: "knowledge" });
  await stubRecords(page, store);
  let nextId = 1;
  const upload = await stubUpload(page, store, {
    delayMs: 300,
    recordFor: (filename) =>
      draftRecord({ id: `draft-${nextId++}`, filename, sections: [{ heading: "Hours", body: "9 to 5" }] }),
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  const thread = page.getByTestId("onboarding-thread");
  await expect(thread).toBeVisible();

  await page.getByTestId("onboarding-file-input").setInputFiles(uploadFilePayloads(FIVE_NAMES));

  // Mid-flight: the review sheet has not opened - it opens only once every
  // upload has settled, never on the first accepted draft.
  await expect(dialog(page)).toHaveCount(0);

  await expect.poll(() => upload.settled()).toBe(5);
  // runBounded(5, 3): never more than three in flight, and all three of the
  // first wave really do run together.
  expect(upload.maxInFlight()).toBeLessThanOrEqual(3);
  expect(upload.maxInFlight()).toBeGreaterThanOrEqual(2);

  for (const name of FIVE_NAMES) {
    await expect(
      thread.getByText(`${name} ${MIDDLE_DOT} ready`, { exact: true }),
    ).toBeVisible();
  }
  await expect(thread.getByText("I can take up to 5 files at once...")).toHaveCount(0);

  const sheet = dialog(page);
  await expect(sheet).toBeVisible();
  for (const name of FIVE_NAMES) {
    await expect(sheet.getByText(name, { exact: true })).toBeVisible();
  }

  const disclosure = page.getByTestId("onboarding-privacy-disclosure");
  await expect(disclosure).toHaveText(PRIVACY_LINE);
  await expect(disclosure).not.toContainText(/Google|OpenAI|Anthropic|Groq|OpenRouter|Z\.ai/);
});

test("caps the batch at five files", async ({ page, request }) => {
  const store = recordsStore([]);
  await stubOnboardingState(page, { stage: "knowledge" });
  await stubRecords(page, store);
  let nextId = 1;
  const upload = await stubUpload(page, store, {
    delayMs: 200,
    recordFor: (filename) => draftRecord({ id: `draft-${nextId++}`, filename }),
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  const thread = page.getByTestId("onboarding-thread");
  await expect(thread).toBeVisible();

  await page.getByTestId("onboarding-file-input").setInputFiles(uploadFilePayloads(SEVEN_NAMES));

  // The sixth and seventh files are turned away in one line; only the first
  // five are processed and stamped.
  await expect(thread.getByText("I can take up to 5 files at once...")).toBeVisible();
  await expect.poll(() => upload.settled()).toBe(5);
  await expect(thread.getByText(new RegExp(`${MIDDLE_DOT} ready$`))).toHaveCount(5);
  await expect(thread.getByText("extra6.txt · ready", { exact: true })).toHaveCount(0);
  await expect(thread.getByText("extra7.txt · ready", { exact: true })).toHaveCount(0);

  const sheet = dialog(page);
  await expect(sheet).toBeVisible();
  for (const name of FIVE_NAMES) {
    await expect(sheet.getByText(name, { exact: true })).toBeVisible();
  }
  await expect(sheet.getByText("extra6.txt", { exact: true })).toHaveCount(0);
});

test("a stored failure stays in Knowledge and never joins the review", async ({
  page,
  request,
}) => {
  const store = recordsStore([]);
  await stubOnboardingState(page, { stage: "knowledge" });
  const records = await stubRecords(page, store);
  await stubUpload(page, store, {
    recordFor: (filename) =>
      draftRecord({
        id: "draft-failed-1",
        filename,
        status: "failed",
        error: "Extraction failed",
        failure_stage: "extract",
        failure_retryable: true,
        failed_at: "2026-09-11T00:00:00Z",
      }),
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  const thread = page.getByTestId("onboarding-thread");
  await expect(thread).toBeVisible();

  await page
    .getByTestId("onboarding-file-input")
    .setInputFiles(uploadFilePayloads(["menu.txt"]));

  await expect(thread.getByText("menu.txt · failed", { exact: true })).toBeVisible();
  await expect(thread.getByText("It's kept in Knowledge so you can retry it.")).toBeVisible();
  // Not a reviewable draft: no sheet, no ready card.
  await expect(dialog(page)).toHaveCount(0);
  await expect(page.getByTestId("onboarding-ready-card")).toHaveCount(0);

  // The failed row lives in the records list the page loads - a reload
  // refetches it (the GET happened and returned it) and still shows nothing
  // reviewable.
  await page.reload();
  await expect(thread).toBeVisible();
  expect(records.getCount()).toBeGreaterThanOrEqual(2);
  expect(JSON.parse(records.lastGetBody())).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        id: "draft-failed-1",
        status: "failed",
        failure_retryable: true,
      }),
    ]),
  );
  await expect(dialog(page)).toHaveCount(0);
  await expect(page.getByTestId("onboarding-ready-card")).toHaveCount(0);
});

test("the ready card persists and reopens with edits intact", async ({ page, request }) => {
  const store = recordsStore([draftRecord()]);
  await stubOnboardingState(page);
  await stubRecords(page, store);

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const sheet = dialog(page);
  await expect(sheet).toBeVisible();
  // One offering: collapsed, so no Review all in the toolbar.
  await expect(sheet.getByRole("button", { name: /Review all/ })).toHaveCount(0);

  // The sheet's own focus effect must land before Escape can reach its
  // keydown handler - the key goes to whatever has focus.
  await expect(sheet.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Escape");
  const card = page.getByTestId("onboarding-ready-card");
  await expect(card).toBeVisible();
  await expect(card.getByText("Documents ready to review")).toBeVisible();
  await expect(card.getByText("1 source is read and waiting")).toBeVisible();

  await page.getByTestId("onboarding-reopen-review").click();
  await expect(sheet).toBeVisible();
  // The sheet's own focus effect must land before Escape can reach its
  // keydown handler - the key goes to whatever has focus.
  await expect(sheet.getByRole("button", { name: "Close" })).toBeFocused();

  await sheet.getByRole("button", { name: "Edit" }).click();
  const edited = "9 to 5, Monday to Friday, closed Sundays";
  const details = sheet.getByLabel("Hours details");
  await details.fill(edited);
  await expect(details).toHaveValue(edited);

  // Close via Escape - not discard - so the workspace survives, then come
  // back through the card: the edit is still there (W-11b retention).
  await page.keyboard.press("Escape");
  await expect(card).toBeVisible();
  await page.getByTestId("onboarding-reopen-review").click();
  await expect(sheet).toBeVisible();
  await expect(sheet.getByLabel("Hours details")).toHaveValue(edited);
});

test("replace is safe when the upload fails", async ({ page, request }) => {
  const store = recordsStore([
    draftRecord({
      id: "draft-1",
      filename: "menu.txt",
      offering_candidates: [offeringCandidate("Menu item A", "draft-1")],
    }),
  ]);
  await stubOnboardingState(page);
  const records = await stubRecords(page, store);
  await stubUpload(page, store, {
    failAll: true,
    recordFor: () => draftRecord({ id: "draft-new", filename: "new.txt" }),
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const sheet = dialog(page);
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText("menu.txt", { exact: true })).toBeVisible();
  await expect(sheet.getByLabel("Offering 1 name")).toHaveValue("Menu item A");

  await sheet.getByRole("button", { name: "Replace menu.txt" }).click();
  await sheet.getByTestId("review-replace-input").setInputFiles({
    name: "new.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("New contents"),
  });

  // Upload failed, so the DELETE never fired and the old source and its
  // offerings are untouched.
  await expect(
    page.getByTestId("onboarding-thread").getByText("new.txt · failed", { exact: true }),
  ).toBeVisible();
  expect(records.deleteCount()).toBe(0);
  await expect(sheet.getByText("menu.txt", { exact: true })).toBeVisible();
  await expect(sheet.getByLabel("Offering 1 name")).toHaveValue("Menu item A");
});

test("a successful replace reconciles offering provenance", async ({ page, request }) => {
  const store = recordsStore([
    draftRecord({
      id: "draft-1",
      filename: "menu.txt",
      offering_candidates: [offeringCandidate("Menu item A", "draft-1")],
    }),
    draftRecord({
      id: "draft-2",
      filename: "notes.txt",
      offering_candidates: [offeringCandidate("Menu item B", "draft-2")],
    }),
  ]);
  await stubOnboardingState(page);
  const records = await stubRecords(page, store);
  await stubUpload(page, store, {
    recordFor: (filename) =>
      draftRecord({
        id: "draft-3",
        filename,
        offering_candidates: [offeringCandidate("Menu item C", "draft-3")],
      }),
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const sheet = dialog(page);
  await expect(sheet).toBeVisible();
  // Labels live on the offering cards (articles) - the Business information
  // section repeats the "From {label}" line for multi-document reviews.
  const cards = sheet.locator("article");
  await expect(cards.getByText("From menu.txt", { exact: true })).toBeVisible();
  await expect(cards.getByText("From notes.txt", { exact: true })).toBeVisible();
  await expect(sheet.getByLabel("Offering 1 name")).toHaveValue("Menu item A");

  // The owner edited item A, so a replace that loses its document orphans it
  // instead of silently dropping the edit.
  await sheet.getByLabel("Offering 1 description").fill("Owner edit");
  await expect(sheet.getByLabel("Offering 1 description")).toHaveValue("Owner edit");

  await sheet.getByRole("button", { name: "Replace menu.txt" }).click();
  await sheet.getByTestId("review-replace-input").setInputFiles({
    name: "new.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("New contents"),
  });

  await expect.poll(() => records.deleteCount()).toBe(1);
  expect(records.deletedIds()).toEqual(["draft-1"]);

  // Old source gone, new source in; item A survives as an orphan, item B
  // keeps its provenance, the new document's candidate appends.
  await expect(sheet.getByText("menu.txt", { exact: true })).toHaveCount(0);
  await expect(sheet.getByText("new.txt", { exact: true })).toBeVisible();
  await expect(cards.getByText("From a replaced source", { exact: true })).toBeVisible();
  await expect(cards.getByText("From notes.txt", { exact: true })).toBeVisible();
  await expect(cards.getByText("From new.txt", { exact: true })).toBeVisible();
  await expect(sheet.getByLabel("Offering 1 name")).toHaveValue("Menu item A");
  await expect(sheet.getByLabel("Offering 2 name")).toHaveValue("Menu item B");
  await expect(sheet.getByLabel("Offering 3 name")).toHaveValue("Menu item C");
});

test("batch publish keeps one failing document reviewable until it saves", async ({
  page,
  request,
}) => {
  const store = recordsStore([
    draftRecord({ id: "draft-1", filename: "menu.txt" }),
    draftRecord({ id: "draft-2", filename: "notes.txt" }),
  ]);
  await stubOnboardingState(page);
  await stubRecords(page, store);
  const batch = await stubBatch(page, store, {
    published: ["draft-1"],
    failed: [
      {
        document_id: "draft-2",
        error: "The price for screen repairs changed. Confirm it before saving.",
      },
    ],
    offering_candidates: [],
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const sheet = dialog(page);
  await expect(sheet).toBeVisible();
  await sheet.getByTestId("onboarding-knowledge-save").click();

  // The published source left the review; the failing one stays with its
  // per-source error and the summary line, and confirm is still blocked.
  await expect(sheet.getByText("menu.txt", { exact: true })).toHaveCount(0);
  await expect(sheet.getByText("notes.txt", { exact: true })).toBeVisible();
  await expect(
    sheet.getByText("The price for screen repairs changed. Confirm it before saving."),
  ).toBeVisible();
  await expect(
    sheet.getByText("Some documents couldn't be saved. See the message under each source, then save again."),
  ).toBeVisible();
  await expect(page.getByTestId("onboarding-confirm")).toHaveCount(0);

  // A second save that publishes everything clears the workspace and opens
  // the confirm step.
  batch.setResponse({ published: ["draft-1", "draft-2"], failed: [], offering_candidates: [] });
  await sheet.getByTestId("onboarding-knowledge-save").click();

  await expect(sheet.getByTestId("onboarding-knowledge-save")).toHaveCount(0);
  await expect(page.getByTestId("onboarding-confirm")).toBeVisible();
  await expect(page.getByTestId("onboarding-public-slug")).toHaveValue("test-repairs");
  await expect(page.getByTestId("onboarding-ready-card")).toHaveCount(0);
});

test("pagination and toolbar keep review stable while typing", async ({ page, request }) => {
  const candidates = Array.from({ length: 12 }, (_, i) =>
    offeringCandidate(`Item ${i + 1}`, "draft-1"),
  );
  const store = recordsStore([
    draftRecord({ id: "draft-1", filename: "catalog.txt", offering_candidates: candidates }),
  ]);
  await stubOnboardingState(page);
  await stubRecords(page, store);

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const sheet = dialog(page);
  await expect(sheet).toBeVisible();

  // Collapsed on load: no pagination rows, and the toolbar shows Review all.
  await expect(sheet.getByText("Page 1 of 3")).toHaveCount(0);
  await expect(sheet.getByText("Showing 1-5 of 12 offerings")).toHaveCount(0);
  const reviewAll = sheet.getByRole("button", { name: "Review all 12" });
  const addOffering = sheet.getByRole("button", { name: "Add offering" });
  await expect(reviewAll).toBeVisible();
  const reviewAllBox = await reviewAll.boundingBox();
  const addBox = await addOffering.boundingBox();
  expect(addBox!.x).toBeGreaterThan(reviewAllBox!.x);

  await reviewAll.click();
  await expect(sheet.getByText("Page 1 of 3")).toBeVisible();
  await expect(sheet.getByText("Showing 1-5 of 12 offerings")).toBeVisible();

  await sheet.getByRole("button", { name: "Next" }).click();
  await expect(sheet.getByText("Page 2 of 3")).toBeVisible();
  await expect(sheet.getByText("Showing 6-10 of 12 offerings")).toBeVisible();

  await sheet.getByRole("button", { name: "Next" }).click();
  await expect(sheet.getByText("Page 3 of 3")).toBeVisible();
  await expect(sheet.getByText("Showing 11-12 of 12 offerings")).toBeVisible();

  await sheet.getByRole("button", { name: "Previous" }).click();
  await sheet.getByRole("button", { name: "Previous" }).click();
  await expect(sheet.getByText("Page 1 of 3")).toBeVisible();

  // Typing in an offering never changes the page.
  await sheet.getByLabel("Offering 1 name").fill("Renamed item");
  await expect(sheet.getByLabel("Offering 1 name")).toHaveValue("Renamed item");
  await expect(sheet.getByText("Page 1 of 3")).toBeVisible();

  // Add offering jumps to the page holding the new owner row and focuses it.
  await sheet.getByRole("button", { name: "Next" }).click();
  await sheet.getByRole("button", { name: "Next" }).click();
  await expect(sheet.getByText("Page 3 of 3")).toBeVisible();
  await addOffering.click();
  await expect(sheet.getByText("Page 1 of 3")).toBeVisible();
  await expect(sheet.getByLabel("Offering 1 name")).toBeFocused();
  await expect(sheet.getByLabel("Offering 1 name")).toHaveValue("");

  // Escape closes the sheet; the ready card is the way back in. Focus is
  // already inside the sheet on the new offering row above.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("onboarding-ready-card")).toBeVisible();
});