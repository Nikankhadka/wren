import { expect, test } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";
import { draftRecord, recordsStore, stubRecords } from "./knowledge-review-mocks";

// In the containerized e2e runner the backend itself fetches this URL, and
// localhost:3000 inside that container is not the frontend (F-3) - compose
// points E2E_SITE_URL at the frontend service over the compose network.
const SITE_URL =
  process.env.E2E_SITE_URL ?? "http://localhost:3000/fixtures/example-business.html";
const EDITED = "We fix phones and laptops on the north side, e2e.";

/** W-11c: the Business > Knowledge half of the ticket's privacy disclosure
 *  (15-document-review.md lines 180-187) - verbatim, no vendor name. */
const KNOWLEDGE_DISCLOSURE =
  "Original files are kept in your business's tenant-isolated Agencx file storage, and extracted sections and offerings are saved in its business database. A configured AI provider processes document text to organize it. Only content you approve can be used in customer answers. Files retained after a processing failure are kept so you can retry them. Replacing or removing a document removes the old source and its derived knowledge.";

/** A stored, retryable processing failure - the W-11a shape the page renders
 *  Retry and Replace for. */
function failedRecord(overrides: Parameters<typeof draftRecord>[0] = {}): ReturnType<typeof draftRecord> {
  return draftRecord({
    id: "failed-1",
    filename: "menu.txt",
    status: "failed",
    error: "Extraction failed",
    failure_stage: "extract",
    failure_retryable: true,
    failed_at: "2026-09-11T00:00:00Z",
    ...overrides,
  });
}

/**
 * O-3 Settings > Knowledge: an owner adds a source, reads back what we made of
 * it, and saves it. The draft gate is the point - nothing answers a customer
 * until the owner has seen the text and said yes.
 */
test("a pasted link is read back as sections, then saved", async ({
  page,
  request,
}) => {
  // The read-back is the model's work on a really-fetched page, nothing
  // stubbed, so with no provider there is nothing to wait for - skip rather
  // than time out. The Makefile derives E2E_LLM from backend/.env.
  test.skip(
    !process.env.E2E_LLM,
    "no LLM provider configured (set LLM_API_KEY in backend/.env) - this spec drives the real URL ingest",
  );

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  // Relative, like every other spec: since D22 there is one origin, so the
  // session the login helper established is simply still here.
  await page.goto("/business/details");
  await expect(page.getByRole("heading", { name: "Settings" })).toHaveCount(0);
  await page.getByText("Knowledge", { exact: true }).click();
  await page.waitForURL("**/business/details/knowledge");

  await page.getByTestId("knowledge-url-input").fill(SITE_URL);
  await page.getByTestId("knowledge-url-submit").click();

  // The review sheet opens with the page processed into readable sections.
  const sheet = page.getByRole("dialog", { name: "Read this back" });
  await expect(sheet).toBeVisible({ timeout: 90_000 });
  await sheet.getByRole("button", { name: "Edit" }).first().click();
  const sections = sheet.getByRole("textbox", { name: /details/ });
  await expect(sections.first()).toBeVisible();
  const before = await sections.first().inputValue();
  expect(before.length).toBeGreaterThan(0);

  // The owner's correction is what gets saved - this is a text they edit.
  await sections.first().fill(EDITED);
  await page.getByTestId("knowledge-save").click();

  await expect(page.getByTestId("knowledge-save")).toHaveCount(0, { timeout: 30_000 });
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();

  // The saved text is now what the assistant knows, and it says so. Scoped to
  // this record: the demo tenant may already carry others.
  const saved = page.locator("article").filter({ hasText: EDITED });
  await expect(saved).toBeVisible({ timeout: 30_000 });
  await saved.getByText("What I read from this").click();
  await expect(saved.getByText(EDITED)).toBeVisible();
  await expect(saved.getByText("Answering from this")).toBeVisible();
  await expect(page.getByTestId("knowledge-error")).toHaveCount(0);

  // Removing it takes it back out of what the assistant knows.
  await saved.getByTestId("knowledge-remove").click();
  await page.getByTestId("confirm-accept").click();
  await expect(page.locator("article").filter({ hasText: EDITED })).toHaveCount(
    0,
    {
      timeout: 30_000,
    },
  );
  await expect(page.getByText("Removed", { exact: true })).toBeVisible();
});

/**
 * W-11c: failed-source recovery on Business > Knowledge, fully mocked - no
 * LLM needed. The retry-draft stub flips the store's failed row to a draft,
 * exactly what the backend does (re-read the stored file, land on
 * status "draft", never publish).
 */
test("a failed source retries into a draft", async ({ page, request }) => {
  const store = recordsStore([failedRecord()]);
  await stubRecords(page, store);
  await page.route("**/api/knowledge/*/retry-draft", (route) => {
    store.records = store.records.map((record) =>
      record.id === "failed-1"
        ? {
            ...record,
            status: "draft",
            error: null,
            extraction_status: "full",
            sections: [
              { heading: "Hours", body: "9 to 5, Monday to Friday", kind: "hours" },
            ],
          }
        : record,
    );
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(store.records[0]),
    });
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  await page.goto("/business/details/knowledge");

  const failed = page.locator("article").filter({ hasText: "menu.txt" });
  await expect(failed).toBeVisible();
  await expect(failed.getByTestId("knowledge-retry")).toBeVisible();

  await failed.getByTestId("knowledge-retry").click();

  // The row leaves "What your assistant knows" and joins the drafts group -
  // reviewable, but the retry never auto-opens the sheet and never publishes.
  const draft = page.getByTestId("knowledge-draft").filter({ hasText: "menu.txt" });
  await expect(draft).toBeVisible();
  await expect(draft.getByText("Read it back before it answers anything")).toBeVisible();
  await expect(failed).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);

  // The privacy disclosure sits under the lists, verbatim and vendor-free.
  const disclosure = page.getByTestId("knowledge-privacy-disclosure");
  await expect(disclosure).toBeVisible();
  await expect(
    disclosure.getByRole("heading", { name: "How your documents are used" }),
  ).toBeVisible();
  await expect(disclosure.getByText(KNOWLEDGE_DISCLOSURE)).toBeVisible();
  await expect(disclosure).not.toContainText(/Google|OpenAI|Anthropic|Groq|OpenRouter|Z\.ai/);
});

/**
 * W-11c: replace on a failed source, fully mocked - no LLM needed. The
 * replacement is processed before the old record is deleted: a failed upload
 * leaves the old source untouched and the DELETE never fires.
 */
test("replace succeeds and is safe on failure", async ({ page, request }) => {
  const store = recordsStore([failedRecord()]);
  const records = await stubRecords(page, store);
  let failUpload = true;
  await page.route("**/api/knowledge/drafts/upload", (route) => {
    if (failUpload) {
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          type: "about:blank",
          title: "Internal Server Error",
          status: 500,
          detail: "Upload failed",
          code: "upstream_error",
        }),
      });
    }
    const filename =
      route.request().postData()?.match(/filename="([^"]+)"/)?.[1] ?? "replacement.txt";
    const record = draftRecord({ id: "replacement-1", filename });
    store.records = [...store.records, record];
    return route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(record),
    });
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  await page.goto("/business/details/knowledge");

  const failed = page.locator("article").filter({ hasText: "menu.txt" });
  await expect(failed).toBeVisible();
  await expect(failed.getByTestId("knowledge-replace")).toBeVisible();

  // Failure path: the upload 500s, so the DELETE never fires and the old
  // failed source stays exactly as it was, with the error surfaced.
  await failed.getByTestId("knowledge-replace").click();
  await page.getByTestId("knowledge-file-input").setInputFiles({
    name: "new-menu.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("New contents"),
  });
  await expect(page.getByText("Upload failed", { exact: true })).toBeVisible();
  await expect(page.getByTestId("knowledge-error")).toHaveCount(0);
  expect(records.deleteCount()).toBe(0);
  await expect(failed).toBeVisible();

  // Success path: the new draft lands first, then the old record is deleted
  // exactly once and the list refetches - the replacement is in the drafts
  // group and the failed row is gone.
  failUpload = false;
  await failed.getByTestId("knowledge-replace").click();
  await page.getByTestId("knowledge-file-input").setInputFiles({
    name: "new-menu.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("New contents"),
  });
  await expect.poll(() => records.deleteCount()).toBe(1);
  expect(records.deletedIds()).toEqual(["failed-1"]);
  await expect(
    page.getByTestId("knowledge-draft").filter({ hasText: "new-menu.txt" }),
  ).toBeVisible();
  await expect(page.locator("article").filter({ hasText: "menu.txt" })).toHaveCount(0);
});

/**
 * Discarding from the review sheet asks first for a document that already
 * has a saved version - a draft never answered anything and skips the
 * question. Fully mocked: the saved record carries sections, so opening it
 * never fetches, and the confirm paints above the sheet it came from.
 */
test("discarding a saved document asks first, escape leaves it alone", async ({
  page,
  request,
}) => {
  const store = recordsStore([
    draftRecord({ id: "saved-1", filename: "hours.txt", status: "ready" }),
  ]);
  const records = await stubRecords(page, store);
  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  await page.goto("/business/details/knowledge");

  const saved = page.locator("article").filter({ hasText: "hours.txt" });
  await expect(saved).toBeVisible();
  await saved.getByTestId("knowledge-edit").click();

  const sheet = page.getByRole("dialog", { name: "Edit what I know" });
  await expect(sheet).toBeVisible();
  const discard = page.getByTestId("knowledge-discard");
  await expect(discard).toHaveText("Remove");

  // Escape asks nothing of the backend and leaves the sheet open.
  await discard.click();
  await expect(page.getByTestId("confirm-accept")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("confirm-accept")).toHaveCount(0);
  expect(records.deleteCount()).toBe(0);
  await expect(sheet).toBeVisible();

  // Accepting removes the record exactly once and says so.
  await discard.click();
  await page.getByTestId("confirm-accept").click();
  await expect(page.getByText("Draft discarded", { exact: true })).toBeVisible();
  expect(records.deleteCount()).toBe(1);
  expect(records.deletedIds()).toEqual(["saved-1"]);
  await expect(page.locator("article").filter({ hasText: "hours.txt" })).toHaveCount(0);
});
