/**
 * E2E browser tests for tenant-admin login.
 *
 * Surface: tenant-admin (http://app.localhost:3000)
 * Entry point: /login
 *
 * Test P0: login with each demo tenant-admin user, verify the post-login card.
 */

import { test, expect } from "@playwright/test";
import {
  DEMO_USERS,
  loginAsTenantAdmin,
  submitLoginForm,
  tenantAdminHost,
} from "./auth-helpers";

test.describe("tenant-admin login", () => {
  // Tenant-admin login uses the app.localhost host.
  test.use({ baseURL: `http://${tenantAdminHost()}` });

  for (const user of DEMO_USERS.filter((u) => u.surface === "tenant-admin")) {
    test(`login as ${user.email}`, async ({ page }) => {
      await loginAsTenantAdmin(page, user);

      // Verify the signed-in card is visible
      await expect(page.getByRole("heading", { name: "Signed in" })).toBeVisible();

      // Verify tenant name is shown on the card
      await expect(page.getByText(user.tenantName!)).toBeVisible();
    });

    test(`sign out after login as ${user.email}`, async ({ page }) => {
      await loginAsTenantAdmin(page, user);

      // Sign out
      await page.getByRole("button", { name: "Sign out" }).click();

      // After sign out the login form should reappear
      await expect(page.getByRole("heading", { name: "Log in" })).toBeVisible();
    });
  }
});

test.describe("tenant-admin login errors", () => {
  test.use({ baseURL: `http://${tenantAdminHost()}` });

  test("wrong password shows error", async ({ page }) => {
    await page.goto("/login");
    await submitLoginForm(page, "owner@bytefix.dev", "wrong-password");

    // The supabase-js error message should appear on the password input's error
    // label (the Input component renders error text below the field).
    // We wait for any error text to appear rather than asserting a specific
    // message since GoTrue messages may vary.
    await expect(page.locator("text=Invalid login credentials")).toBeVisible({ timeout: 10_000 });
  });

  test("missing email shows HTML5 validation", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Log in" }).click();

    // The browser's built-in form validation should prevent submission.
    // Playwright can assert the input is invalid.
    const emailInput = page.getByLabel("Email");
    await expect(emailInput).toHaveAttribute("required", "");
  });
});
