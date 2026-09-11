/**
 * E2E for the tenant app shell (E-1 / D21): three destinations - Home, Chats,
 * Business - as the sidebar at desktop width, with the advanced Wren screens
 * unlinked but still serving.
 *
 * Surface: tenant-admin (http://localhost:3000)
 *
 * The mobile half of this ticket (the bottom tab bar at 375px) lives in
 * tab-shell-mobile.spec.ts, which the mobile-chrome project picks up by
 * filename.
 */

import { test, expect } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";

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

const HIDDEN_LINKS = ["Conversations", "Escalations", "Pricing", "Dashboards", "Onboarding"];

test.describe("tenant app shell - three destinations", () => {

  test("the sidebar is Home, Chats and Business - and nothing else", async ({ page, request }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/home");

    const nav = page.getByRole("navigation", { name: "Console" });
    await expect(nav).toBeVisible();
    const links = nav.getByRole("link");
    await expect(links).toHaveCount(DESTINATIONS.length);
    for (const [index, destination] of DESTINATIONS.entries()) {
      await expect(links.nth(index)).toHaveAccessibleName(destination);
    }

    for (const label of HIDDEN_LINKS) {
      await expect(nav.getByRole("link", { name: label })).toHaveCount(0);
    }
  });

  test("each tab navigates, and the current one is marked", async ({ page, request }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/home");

    const nav = page.getByRole("navigation", { name: "Console" });
    await expect(nav.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");

    await nav.getByRole("link", { name: /^Chats\b/ }).click();
    await page.waitForURL("**/chats");
    await expect(nav.getByRole("link", { name: /^Chats\b/ })).toHaveAttribute("aria-current", "page");

    await nav.getByRole("link", { name: "Business" }).click();
    await page.waitForURL("**/business");
    await expect(nav.getByRole("link", { name: "Business" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  test("a drill-down keeps its back control and stays under the Business tab", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business");

    await page.getByRole("link", { name: /Business details/ }).click();
    await page.waitForURL("**/business/details");

    // The tab is still marked while a screen under it is open.
    const nav = page.getByRole("navigation", { name: "Console" });
    await expect(nav.getByRole("link", { name: "Business" })).toHaveAttribute(
      "aria-current",
      "page",
    );

    await page.getByRole("button", { name: "Back" }).click();
    await page.waitForURL("**/business");
  });

  test("a tab destination has no back control", async ({ page, request }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/chats");
    await expect(page.getByRole("button", { name: "Back", exact: true })).toHaveCount(0);
  });

  test("the active tab wears the accent wash, inactive tabs hover into it", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/home");

    const nav = page.getByRole("navigation", { name: "Console" });
    const home = nav.getByRole("link", { name: "Home" });
    await expect(home).toHaveCSS("background-color", "rgba(255, 56, 92, 0.09)");
    await expect(home).toHaveCSS("color", "rgb(180, 0, 78)");

    const chats = nav.getByRole("link", { name: /^Chats\b/ });
    await chats.hover();
    await expect(chats).toHaveCSS("background-color", "rgba(255, 56, 92, 0.07)");
    await expect(chats).toHaveCSS("color", "rgb(180, 0, 78)");
  });

  // The advanced screens' own posture - unlinked but still serving - is E-2's,
  // and lives in hidden-screens.spec.ts.
});
