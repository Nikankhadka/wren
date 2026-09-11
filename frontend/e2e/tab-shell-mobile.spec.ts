/**
 * E2E for the bottom tab bar at phone width (E-1 / D18 / D21). Runs under the
 * mobile-chrome project (matched by the `mobile` in the filename).
 *
 * This is the ticket that closes the console's narrow-mobile sidebar squeeze:
 * below `lg` there is no sidebar and no hamburger at all, only the bar.
 */

import { test, expect } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";
import { MOBILE_WIDTHS, expectNoHorizontalOverflow, expectTapTargets } from "./mobile-helpers";

const BYTEFIX = DEMO_USERS.find((u) => u.email === "owner@bytefix.dev")!;

/**
 * The Chats destination carries a waiting-count badge whose text sits inside
 * the link and whose count arrives on an interval (W-1), so both the link's
 * text and its accessible name change from "Chats" to "Chats5" / "Chats, 5
 * waiting" partway through a run. Matching the destination rather than the
 * count is what keeps these assertions about the shell instead of about
 * whatever the seed happens to leave in the queue.
 */
const DESTINATIONS = [/^Home\b/, /^Chats\b/, /^Business\b/];

test.describe("tenant app shell on a phone", () => {

  test("the bottom tab bar replaces the sidebar and the hamburger", async ({ page, request }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/home");

    const bar = page.getByRole("navigation", { name: "Main" });
    await expect(bar).toBeVisible();
    const links = bar.getByRole("link");
    await expect(links).toHaveCount(DESTINATIONS.length);
    for (const [index, destination] of DESTINATIONS.entries()) {
      await expect(links.nth(index)).toHaveAccessibleName(destination);
    }

    await expect(page.getByRole("navigation", { name: "Console" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Menu" })).toHaveCount(0);
  });

  test("the bar stays put across tabs and over a drill-down", async ({ page, request }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/home");

    const bar = page.getByRole("navigation", { name: "Main" });
    await bar.getByRole("link", { name: "Business" }).click();
    await page.waitForURL("**/business");
    await expect(bar).toBeVisible();

    // The prototype keeps #tabbar above #screen-layer, so a pushed screen
    // never covers it.
    await page.getByRole("link", { name: /Business details/ }).click();
    await page.waitForURL("**/business/details");
    await expect(bar).toBeVisible();
  });

  test("the bar sits at the bottom and nothing hides behind it", async ({ page, request }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/chats");

    const bar = page.getByRole("navigation", { name: "Main" });
    const box = (await bar.boundingBox())!;
    const viewport = page.viewportSize()!;

    // Flush to the bottom edge, and tall enough to tap.
    expect(Math.round(box.y + box.height)).toBe(viewport.height);
    expect(box.height).toBeGreaterThanOrEqual(56);

    // The scroll region above it ends where the bar begins - no overlap.
    const contentBottom = await page.evaluate(() => {
      const main = document.querySelector("main");
      return main ? Math.round(main.getBoundingClientRect().bottom) : 0;
    });
    expect(contentBottom).toBeLessThanOrEqual(Math.round(box.y) + 1);
  });

  test("the active tab wears the accent wash", async ({ page, request }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/home");

    const bar = page.getByRole("navigation", { name: "Main" });
    const home = bar.getByRole("link", { name: "Home" });
    await expect(home).toHaveCSS("background-color", "rgba(255, 56, 92, 0.09)");
    await expect(home).toHaveCSS("color", "rgb(180, 0, 78)");
  });

  for (const width of MOBILE_WIDTHS) {
    test(`no overflow and tappable controls at ${width}px`, async ({ page, request }) => {
      await page.setViewportSize({ width, height: 812 });
      await loginAsTenantAdmin(page, request, BYTEFIX);
      await page.goto("/business");
      await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await expectTapTargets(page);
    });
  }
});
