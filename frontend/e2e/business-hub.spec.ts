/**
 * E2E for the Business hub and the screens under it (E-5 / D21 / M-1 / M-4).
 *
 * Surface: tenant-admin (http://localhost:3000)
 *
 * The hub's shape is the thing under test as much as its contents: Stage 2
 * grows it by adding rows, so "exactly the rows that open onto something" is
 * the invariant worth pinning (PRD, "never build dead surfaces").
 */

import { test, expect } from "@playwright/test";
import {
  DEMO_USERS,
  loginAsTenantAdmin,
} from "./auth-helpers";

const BYTEFIX = DEMO_USERS.find((u) => u.email === "owner@bytefix.dev")!;
const STAGE_2_ROWS = ["Schedule", "Money", "Plan"];

test.describe("Business hub", () => {

  test("holds only rows that open onto something", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business");

    const rows = page.getByRole("main").getByRole("link");
    await expect(rows).toHaveText([
      "Business pageWhat customers see and how it looks",
      "What you offerThe services and prices shown on your page",
      "Business detailsKnowledge, ABN, and tax details",
    ]);

    // Absent, not disabled - the prototype carries them, Stage 1 does not.
    for (const label of STAGE_2_ROWS) {
      await expect(page.getByText(label, { exact: true })).toHaveCount(0);
    }
  });

  test("the business page shows the business and its public link", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business");
    await page.getByRole("link", { name: /Business page/ }).click();
    await page.waitForURL("**/business/page");

    await expect(page.getByRole("heading", { level: 2 })).toContainText(
      "Bytefix",
    );

    // Derived from the current origin, so it is the address that actually
    // works from this browser - never a hardcoded domain.
    const link = page.getByTestId("booking-link");
    await expect(link).toContainText("/bytefix");
    await expect(link).not.toContainText("http");
    await expect(link).not.toContainText(/\/$/);

    const summary = page.getByRole("heading", { name: "What we offer" });
    await expect(summary).toBeVisible();
    await expect(page.getByText("iPhone 11 (Refurbished, 64GB)")).toBeVisible();
    await expect(page.getByText("$249.00")).toBeVisible();

    const sectionColors = await page
      .locator('[data-testid="offerings-summary"], [data-testid="booking-links"]')
      .evaluateAll((sections) =>
        sections.map((section) => getComputedStyle(section).backgroundColor),
      );
    expect(new Set(sectionColors).size).toBe(1);
  });

  test("an owner adds, edits, and removes an offering, and the storefront follows", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business");
    await page.getByRole("link", { name: /What you offer/ }).click();
    await page.waitForURL("**/business/offerings");

    // These specs share one seeded tenant, so start from a known state rather
    // than from whatever a previous run left behind - the same posture the
    // link-slot test below takes. Gated on the loaded list: `count()` does
    // not retry, and counting before the first fetch lands would skip the
    // cleanup while a stale row is still on its way in.
    await expect(
      page.getByTestId("offerings-list").or(page.getByText("Nothing added yet.")),
    ).toBeVisible();
    const leftovers = page.getByRole("button", { name: "Remove M1 test offering" });
    while ((await leftovers.count()) > 0) {
      await leftovers.first().click();
      await page.getByTestId("confirm-accept").click();
      await expect(leftovers).toHaveCount(0);
    }

    await page.getByTestId("offering-add").click();
    await page.getByTestId("offering-name").fill("M1 test offering");
    await page.getByText("Add details", { exact: true }).click();
    await page.getByTestId("offering-category").fill("Screen repairs");
    await page.getByTestId("offering-description").fill("Most models");
    await page.getByTestId("offering-price").fill("89.50");
    await page.getByTestId("offering-media-url").fill("https://youtu.be/example");
    await page.getByTestId("offering-save").click();
    await expect(page.getByTestId("offerings-list")).toContainText("M1 test offering");
    await expect(page.getByText("Offering added", { exact: true })).toBeVisible();

    // The price the owner typed, on the page a customer actually reads - and
    // exactly as typed. This is the assertion the money rule lives or dies by.
    // The offering is a row button, not a heading, on the catalogue layout.
    await page.goto("/bytefix");
    // `.first()`: `next dev` streams this page, so for a beat the server tree
    // and the client tree are both in the DOM - the same caveat
    // typing-indicator.spec.ts documents for the composer.
    await expect(
      page.getByRole("button", { name: /M1 test offering/ }).first(),
    ).toBeVisible();
    await expect(page.getByRole("main").last()).toContainText("$89.50");
    const card = page.getByRole("button", { name: /M1 test offering/ });
    await card.click();
    const details = page.getByRole("dialog", { name: "M1 test offering" });
    await expect(details.locator("iframe")).toHaveAttribute(
      "src",
      /youtube-nocookie\.com\/embed\//,
    );
    await details.getByRole("button", { name: "Ask about this" }).click();
    const chat = page.getByRole("dialog", { name: /Chat with Bytefix/ });
    await expect(chat.getByRole("textbox")).toHaveValue(
      "Tell me about M1 test offering",
    );

    await page.goto("/business/offerings");
    await page.getByRole("button", { name: "Edit M1 test offering" }).click();
    await page.getByTestId("offering-price").fill("99");
    await page.getByTestId("offering-save").click();
    await expect(page.getByTestId("offerings-list")).toContainText("$99.00");
    await expect(page.getByText("Offering saved", { exact: true })).toBeVisible();

    await page.goto("/bytefix");
    await expect(page.getByRole("main").last()).toContainText("$99.00");

    await page.goto("/business/offerings");
    await page.getByRole("button", { name: "Remove M1 test offering" }).click();
    await page.getByTestId("confirm-accept").click();
    await expect(page.getByTestId("offerings-list")).not.toContainText("M1 test offering");
    await expect(page.getByText("Offering removed", { exact: true })).toBeVisible();

    // Retiring it takes it off the storefront too, not just out of the editor.
    await page.goto("/bytefix");
    await expect(page.getByRole("main").last()).not.toContainText("M1 test offering");
  });

  test("escape closes the remove confirm without touching the backend", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business/offerings");

    await page.getByTestId("offering-add").click();
    await page.getByTestId("offering-name").fill("M1 cancel-remove probe");
    await page.getByTestId("offering-save").click();
    await expect(page.getByTestId("offerings-list")).toContainText("M1 cancel-remove probe");

    let deletes = 0;
    await page.route("**/api/business/offerings/*", (route) => {
      if (route.request().method() === "DELETE") deletes += 1;
      return route.continue();
    });

    await page.getByRole("button", { name: "Remove M1 cancel-remove probe" }).click();
    await expect(page.getByTestId("confirm-accept")).toBeVisible();
    await page.keyboard.press("Escape");
    // A closed confirm renders nothing, so "closed" means no accept button
    // in the tree - never a visibility assertion on the dialog role.
    await expect(page.getByTestId("confirm-accept")).toHaveCount(0);
    expect(deletes).toBe(0);
    await expect(page.getByTestId("offerings-list")).toContainText("M1 cancel-remove probe");

    // Clean up through the real confirm path.
    await page.getByRole("button", { name: "Remove M1 cancel-remove probe" }).click();
    await page.getByTestId("confirm-accept").click();
    await expect(page.getByTestId("offerings-list")).not.toContainText("M1 cancel-remove probe");
  });

  test("copying puts the full URL, scheme and all, on the clipboard", async ({
    page,
    request,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business/page");

    await page.getByTestId("booking-copy").click();
    await expect(page.getByTestId("booking-copy")).toContainText("Copied");

    const copied = await page.evaluate(() => navigator.clipboard.readText());
    // The pill hides the scheme; what a customer needs is the whole thing.
    expect(copied).toMatch(/^https?:\/\/[^/]+\/bytefix$/);
  });

  test("the cover photo and the link slots", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business/page");

    // E-6: the QR went. It was never in the prototype's owner screen, and the
    // founder does not use it. Pinned so it does not drift back in.
    await expect(page.getByTestId("booking-qr")).toHaveCount(0);
    // Nor is there a "Get a quote" CTA: quoting is a Stage 2 opt-in.
    await expect(page.getByRole("button", { name: "Get a quote" })).toHaveCount(
      0,
    );

    // The cover well invites a photo before there is one.
    await expect(page.getByTestId("booking-cover")).toBeVisible();
    await expect(page.getByTestId("booking-cover")).toContainText(
      "cover photo",
    );

    // Four slots, each either offering to take a link or offering to open one.
    // Not asserted as "all empty": these specs share one seeded tenant, so a
    // slot's contents are another test's business, not this one's.
    for (const key of ["website", "google", "facebook", "instagram"]) {
      await expect(page.getByTestId(`booking-platform-${key}`)).toContainText(
        /Add|Open/,
      );
    }
  });

  test("a link slot takes an address, keeps it, and then opens it", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business/page");

    const tile = page.getByTestId("booking-platform-instagram");

    // These specs share one seeded tenant, so start from a known slot rather
    // than from whatever a previous run left behind.
    await tile.click();
    if (await page.getByTestId("booking-link-remove").isVisible()) {
      await page.getByTestId("booking-link-remove").click();
      await page.getByTestId("confirm-accept").click();
      await expect(tile).toContainText("Add");
      await tile.click();
    }

    // Pasted without a scheme, the way an address bar shows it.
    await page.getByTestId("booking-link-input").fill("instagram.com/bytefix");
    await page.getByTestId("booking-link-save").click();
    await expect(tile).toContainText("Open");
    await expect(page.getByText("Link saved", { exact: true })).toBeVisible();

    // It survives a reload - this is the assertion that catches a save that
    // only ever updated local state.
    await page.reload();
    await expect(tile).toContainText("Open");

    // And it is a way out to that page, with the scheme filled in. Asserted on
    // the href rather than by following it: a real popup would assert on
    // whatever instagram.com redirects to that day, which is a test of their
    // infrastructure, not ours.
    await tile.click();
    await expect(page.getByTestId("booking-link-open")).toHaveAttribute(
      "href",
      "https://instagram.com/bytefix",
    );

    // Put the slot back, so this spec leaves the shared tenant as it found it.
    await page.getByTestId("booking-link-remove").click();
    await page.getByTestId("confirm-accept").click();
    await expect(tile).toContainText("Add");
    await expect(page.getByText("Link removed", { exact: true })).toBeVisible();
  });

  test("back from the business page returns to the hub", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business/page");
    await page.getByRole("button", { name: "Back" }).click();
    await page.waitForURL("**/business");
  });
});
