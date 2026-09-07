/**
 * W-9 US-7: the owner chooses how the public assistant sounds.
 *
 * Surface: tenant-admin (Business > Business details > Assistant voice). The
 * sheet follows the ABN pattern, so this file follows settings-abn.spec.ts -
 * open from the row, edit, save, and prove it survives a reload.
 *
 * The keyboard test is the one that closes W-8's last open Definition-of-done
 * box: the sheet has to be reachable and operable with no pointer at all.
 */

import { expect, test, type Page } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";

const BYTEFIX = DEMO_USERS.find((u) => u.email === "owner@bytefix.dev")!;

/** The Business details row that opens the voice sheet. */
function voiceRow(page: Page) {
  return page.getByRole("button", { name: /Assistant voice/ });
}

/** The sheet is mounted even when closed, so "closed" is its editor unmounting. */
async function expectSheetClosed(page: Page) {
  await expect(page.getByTestId("voice-save")).toHaveCount(0, { timeout: 15_000 });
}

/** Put the tenant back on a known preset so each test starts from the same voice. */
async function resetToWarmCasual(page: Page) {
  await voiceRow(page).click();
  await page.getByTestId("voice-warm_casual").click();
  await page.getByTestId("voice-save").click();
  await expectSheetClosed(page);
  await expect(voiceRow(page)).toContainText("Warm and casual");
}

test("the voice row reads back the chosen voice, and edits it", async ({ page, request }) => {
  await loginAsTenantAdmin(page, request, BYTEFIX);
  await page.goto("/business/details");
  await resetToWarmCasual(page);

  await voiceRow(page).click();
  const sheet = page.getByRole("dialog", { name: "Edit assistant voice" });
  await expect(sheet).toBeVisible();

  // Each preset is a chip, and choosing one marks it as the selected voice.
  for (const preset of ["clear_professional", "direct_concise", "warm_casual"]) {
    await page.getByTestId(`voice-${preset}`).click();
    await expect(page.getByTestId(`voice-${preset}`)).toHaveAttribute("aria-pressed", "true");
    // The description field belongs to the fourth chip only.
    await expect(page.getByTestId("voice-style")).toHaveCount(0);
  }

  await page.getByTestId("voice-direct_concise").click();
  await page.getByTestId("voice-save").click();
  await expectSheetClosed(page);
  await expect(voiceRow(page)).toContainText("Direct and concise");

  // The choice survives a reload - it is saved, not just on screen.
  await page.reload();
  await expect(voiceRow(page)).toContainText("Direct and concise");
});

test("the fourth chip opens a bounded description, and it persists", async ({ page, request }) => {
  await loginAsTenantAdmin(page, request, BYTEFIX);
  await page.goto("/business/details");
  await resetToWarmCasual(page);

  await voiceRow(page).click();
  await page.getByTestId("voice-custom").click();

  const style = page.getByTestId("voice-style");
  await expect(style).toBeVisible();
  // Bounded at the same 300 the backend enforces.
  await expect(style).toHaveAttribute("maxlength", "300");

  await style.fill("Calm and reassuring, never pushy.");
  await page.getByTestId("voice-save").click();
  await expectSheetClosed(page);
  await expect(voiceRow(page)).toContainText("Calm and reassuring, never pushy.");

  await page.reload();
  await expect(voiceRow(page)).toContainText("Calm and reassuring, never pushy.");

  // Reopening starts from what is saved, not from a stale draft.
  await voiceRow(page).click();
  await expect(page.getByTestId("voice-custom")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("voice-style")).toHaveValue("Calm and reassuring, never pushy.");

  await page.getByTestId("voice-warm_casual").click();
  await page.getByTestId("voice-save").click();
  await expectSheetClosed(page);
  await expect(voiceRow(page)).toContainText("Warm and casual");
});

test("a custom voice with nothing in it is refused, in the owner's words", async ({
  page,
  request,
}) => {
  await loginAsTenantAdmin(page, request, BYTEFIX);
  await page.goto("/business/details");
  await resetToWarmCasual(page);

  await voiceRow(page).click();
  await page.getByTestId("voice-custom").click();
  await page.getByTestId("voice-style").fill("   ");
  await page.getByTestId("voice-save").click();

  // Scoped to the sheet: Next mounts its own empty role="alert" announcer.
  const sheet = page.getByRole("dialog", { name: "Edit assistant voice" });
  await expect(sheet.getByRole("alert")).toHaveText(
    "Describe how you want your assistant to sound.",
  );
  await expect(page.getByTestId("voice-save")).toBeVisible();

  // Typing again clears the complaint rather than leaving it accusing.
  await page.getByTestId("voice-style").fill("Calm and reassuring.");
  await expect(sheet.getByRole("alert")).toHaveCount(0);
});

test("the voice sheet is reachable and operable by keyboard alone", async ({ page, request }) => {
  await loginAsTenantAdmin(page, request, BYTEFIX);
  await page.goto("/business/details");
  await resetToWarmCasual(page);

  // Reachable: tab order gets to the row without a pointer. The budget is
  // generous on purpose - the assertion is that it is reachable, not where.
  const row = voiceRow(page);
  for (let press = 0; press < 40; press++) {
    if (await row.evaluate((el) => el === document.activeElement)) break;
    await page.keyboard.press("Tab");
  }
  await expect(row).toBeFocused();

  // Enter opens it, and focus moves into the sheet rather than staying behind.
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog", { name: "Edit assistant voice" });
  await expect(sheet).toBeVisible();
  const close = sheet.getByRole("button", { name: "Close" });
  await expect(close).toBeFocused();

  // Focus is trapped: Shift+Tab off the first control wraps to the last, and
  // Tab off the last wraps back to the first.
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByTestId("voice-save")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();

  // Space activates a chip, the same as a click.
  await page.keyboard.press("Tab");
  await expect(page.getByTestId("voice-warm_casual")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByTestId("voice-clear_professional")).toBeFocused();
  await page.keyboard.press(" ");
  await expect(page.getByTestId("voice-clear_professional")).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  // Enter activates one too, and the revealed description takes focus, so a
  // keyboard owner is typing where the fourth chip just sent them.
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.getByTestId("voice-custom")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("voice-style")).toBeFocused();
  await page.keyboard.type("Calm and reassuring, never pushy.");
  await expect(page.getByTestId("voice-style")).toHaveValue("Calm and reassuring, never pushy.");

  // Escape closes without saving, and focus returns to the row that opened it.
  await page.keyboard.press("Escape");
  await expectSheetClosed(page);
  await expect(row).toBeFocused();
  await expect(row).toContainText("Warm and casual");

  // Saving is reachable by keyboard too: reopen, choose, and press the button.
  await page.keyboard.press("Enter");
  await expect(sheet).toBeVisible();
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByTestId("voice-save")).toBeFocused();
  await page.keyboard.press("Enter");
  await expectSheetClosed(page);
  await expect(row).toContainText("Warm and casual");
});
