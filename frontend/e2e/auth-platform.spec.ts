/**
 * E2E browser tests for platform-admin login.
 *
 * Surface: platform (http://admin.localhost:3000)
 * Entry point: /login
 *
 * The platform login page lives under the internal `admin-surface/` segment
 * but proxy.ts transparently rewrites `admin.*` -> `/admin-surface/*` so the
 * browser sees a clean `/login` URL.
 */

import { test, expect } from "@playwright/test";
import {
  DEMO_USERS,
  loginAsPlatformAdmin,
  submitLoginForm,
  platformHost,
} from "./auth-helpers";

test.describe("platform admin login", () => {
  test.use({ baseURL: `http://${platformHost()}` });

  const founder = DEMO_USERS.find((u) => u.surface === "platform")!;

  test(`login as ${founder.email}`, async ({ page }) => {
    await loginAsPlatformAdmin(page, founder);

    // T-033: on success the page redirects to "/" which renders the Tenants
    // page with a heading.
    await expect(page.getByRole("heading", { name: "Tenants" })).toBeVisible();
  });

  test("non-admin user gets forbidden error on platform surface", async ({ page }) => {
    const tenantAdmin = DEMO_USERS.find((u) => u.surface === "tenant-admin")!;

    await page.goto("/login");
    await submitLoginForm(page, tenantAdmin.email, tenantAdmin.password);

    // The platform login page should show a 403 error for a non-admin user
    // since apiFetch("/api/platform/ping") returns 403.
    await expect(
      page.getByText("This account is not a platform admin.")
    ).toBeVisible({ timeout: 10_000 });
  });
});
