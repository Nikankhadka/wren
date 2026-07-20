/**
 * E2E browser tests for the tenant-admin Dashboards tab (T-034).
 *
 * Surface: tenant-admin (http://app.localhost:3000)
 * Entry point: /dashboards (after login)
 *
 * Seed data (backend/seeds/seed_demo.py) guarantees bytefix has cost_logs and
 * conversations but ZERO eval_runs, so the eval section exercises its empty
 * state. Dollar figures are asserted by presence/format only - month-boundary
 * effects make exact "this month" values legitimately near-zero early in a
 * month, so no exact amounts are pinned.
 */

import { test, expect } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin, tenantAdminHost } from "./auth-helpers";

const BYTEFIX = DEMO_USERS.find((u) => u.email === "owner@bytefix.dev")!;

test.describe("tenant dashboards", () => {
  test.use({ baseURL: `http://${tenantAdminHost()}` });

  test("cost + eval dashboards render for bytefix", async ({ page }) => {
    await loginAsTenantAdmin(page, BYTEFIX);
    await page.goto("/dashboards");

    const costSection = page.locator("section", {
      has: page.getByRole("heading", { name: "Cost and volume" }),
    });

    // All five metric card labels are visible.
    for (const label of [
      "Cost today",
      "Cost this month",
      "Avg cost / conversation",
      "Conversations",
      "Escalation rate",
    ]) {
      await expect(costSection.getByText(label, { exact: true }).first()).toBeVisible();
    }

    // At least one dollar-formatted value renders in the cost cards. Presence /
    // format only - never an exact figure (month-boundary safe).
    await expect(costSection.getByText(/\$\d/).first()).toBeVisible();

    // The conversations metric shows a number greater than zero (seed guarantee).
    const sectionText = await costSection.innerText();
    const convMatch = sectionText.match(/Conversations\s+(\d[\d,]*)/);
    expect(convMatch, "conversations count should render as a number").not.toBeNull();
    expect(Number(convMatch![1].replace(/,/g, ""))).toBeGreaterThan(0);

    // The sparkline is an accessible image.
    await expect(page.getByRole("img", { name: /30-day daily cost/ })).toBeVisible();

    // The eval section shows its empty state (seed guarantees zero eval_runs).
    await expect(
      page.getByText("No eval runs recorded for this tenant yet")
    ).toBeVisible();
    await expect(
      page.getByText(
        "Evals run in CI against seeded test tenants, so a fresh business normally has none."
      )
    ).toBeVisible();

    // The Dashboards nav item shows as the active/current pill.
    const dashLink = page.getByRole("link", { name: "Dashboards" });
    await expect(dashLink).toHaveAttribute("aria-current", "page");
  });

  test("no horizontal overflow at 375px", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await loginAsTenantAdmin(page, BYTEFIX);
    await page.goto("/dashboards");

    // Wait for the cost data to land so the fully-populated layout is measured.
    await expect(
      page
        .locator("section", { has: page.getByRole("heading", { name: "Cost and volume" }) })
        .getByText(/\$\d/)
        .first()
    ).toBeVisible();

    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(overflows).toBe(false);
  });
});
