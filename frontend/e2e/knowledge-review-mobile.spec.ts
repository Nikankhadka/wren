import { expect, test, type Page } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";
import { expectNoHorizontalOverflow } from "./mobile-helpers";
import {
  MIDDLE_DOT,
  draftRecord,
  offeringCandidate,
  recordsStore,
  stubOnboardingState,
  stubRecords,
  stubUpload,
  uploadFilePayloads,
} from "./knowledge-review-mocks";

/**
 * W-11c on a phone. Runs under the mobile-chrome project (matched by the
 * `mobile` in the filename), which is an iPhone 13 with a real touchscreen.
 *
 * The review sheet is the one onboarding surface built for a desktop-width
 * document, so the batch settle, the toolbar, the two-row pagination and the
 * ready card are all checked where they actually render - and the whole page
 * must never overflow horizontally at phone width.
 */

const FIVE_NAMES = ["menu.txt", "hours.txt", "policies.txt", "notes.txt", "faq.txt"];

function dialog(page: Page) {
  return page.getByRole("dialog", { name: "Review your information" });
}

test("five files settle into the review sheet at phone width", async ({ page, request }) => {
  const store = recordsStore([]);
  await stubOnboardingState(page, { stage: "knowledge" });
  await stubRecords(page, store);
  let nextId = 1;
  await stubUpload(page, store, {
    delayMs: 300,
    recordFor: (filename) => draftRecord({ id: `draft-${nextId++}`, filename }),
  });

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);
  const thread = page.getByTestId("onboarding-thread");
  await expect(thread).toBeVisible();

  await page.getByTestId("onboarding-file-input").setInputFiles(uploadFilePayloads(FIVE_NAMES));

  const sheet = dialog(page);
  await expect(sheet).toBeVisible();
  for (const name of FIVE_NAMES) {
    await expect(
      thread.getByText(`${name} ${MIDDLE_DOT} ready`, { exact: true }),
    ).toBeVisible();
    await expect(sheet.getByText(name, { exact: true })).toBeVisible();
  }
  await expectNoHorizontalOverflow(page);

  // Closing through the phone's own path leaves the page usable and the
  // ready card in view - still no sideways scroll. The sheet's own focus
  // effect must land before Escape can reach its keydown handler.
  await expect(sheet.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("onboarding-ready-card")).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("the toolbar keeps Review all and Add offering at opposite ends", async ({
  page,
  request,
}) => {
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

  const reviewAll = sheet.getByRole("button", { name: "Review all 12" });
  const addOffering = sheet.getByRole("button", { name: "Add offering" });
  await expect(reviewAll).toBeVisible();
  const reviewAllBox = await reviewAll.boundingBox();
  const addBox = await addOffering.boundingBox();
  expect(addBox!.x).toBeGreaterThan(reviewAllBox!.x);
  await expectNoHorizontalOverflow(page);
});

test("the pagination shows two rows after expanding", async ({ page, request }) => {
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
  await sheet.getByRole("button", { name: "Review all 12" }).click();

  // Both rows of the pagination block are visible at once - Previous | Page
  // 1 of 3 | Next on the first row, the centered summary on the second.
  const pageLine = sheet.getByText("Page 1 of 3");
  const showing = sheet.getByText("Showing 1-5 of 12 offerings");
  await expect(pageLine).toBeVisible();
  await expect(showing).toBeVisible();
  const pageBox = await pageLine.boundingBox();
  const showingBox = await showing.boundingBox();
  expect(showingBox!.y).toBeGreaterThan(pageBox!.y);
  await expectNoHorizontalOverflow(page);
});

test("the ready card stacks the button under the heading", async ({ page, request }) => {
  const store = recordsStore([draftRecord()]);
  await stubOnboardingState(page);
  await stubRecords(page, store);

  await loginAsTenantAdmin(page, request, DEMO_USERS[0]);

  const sheet = dialog(page);
  await expect(sheet).toBeVisible();
  // The sheet's own focus effect must land before Escape can reach its
  // keydown handler - the key goes to whatever has focus.
  await expect(sheet.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Escape");

  const card = page.getByTestId("onboarding-ready-card");
  await expect(card).toBeVisible();
  const heading = card.getByText("Documents ready to review");
  const button = card.getByRole("button", { name: "Review documents" });
  const headingBox = await heading.boundingBox();
  const buttonBox = await button.boundingBox();
  // Stacked, not side by side: the button sits below the heading on a phone.
  expect(buttonBox!.y).toBeGreaterThan(headingBox!.y);
  await expectNoHorizontalOverflow(page);
});