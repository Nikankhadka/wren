/**
 * E2E browser tests for tenant-admin login-in-chat (O-2).
 *
 * Surface: tenant-admin (http://localhost:3000)
 * Entry point: /login (reachable from both hosts)
 *
 * Login is now inside the conversation: email -> 6-digit code -> session. The
 * code is GoTrue OTP; the helper reads it out of Mailpit (auth-helpers.ts).
 */

import { test, expect } from "@playwright/test";
import { DEMO_USERS, fetchOtpCode, loginAsTenantAdmin } from "./auth-helpers";

test.describe("tenant-admin login-in-chat (app host)", () => {

  test("waits for tenant provisioning before entering onboarding", async ({ page, request }) => {
    let releaseProvisioning!: () => void;
    const provisioningGate = new Promise<void>((resolve) => {
      releaseProvisioning = resolve;
    });
    let sawProvisioning!: () => void;
    const provisioningStarted = new Promise<void>((resolve) => {
      sawProvisioning = resolve;
    });

    await page.route("**/api/tenants", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      sawProvisioning();
      await provisioningGate;
      await route.continue();
    });

    const email = `provision-${Date.now()}@founder.dev`;
    await page.goto("/login");
    await page.getByPlaceholder("you@example.com").fill(email);
    await page.getByRole("button", { name: "Send" }).click();
    await page.getByLabel("Digit 1").waitFor();
    const code = await fetchOtpCode(request, email);
    for (let i = 0; i < 6; i++) {
      await page.getByLabel(`Digit ${i + 1}`).fill(code[i]);
    }

    await provisioningStarted;
    await expect(page).toHaveURL(/\/login$/);
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/\/login$/);

    releaseProvisioning();
    await page.waitForURL("**/onboarding");
  });

  for (const user of DEMO_USERS.filter((u) => u.surface === "tenant-admin")) {
    test(`login as ${user.email}`, async ({ page, request }) => {
      await loginAsTenantAdmin(page, request, user);

      // The admin console shell is the post-login destination: the demo
      // tenants are seeded already-onboarded, so login lands on Home - the
      // interview only shows for a tenant that has not gone live.
      await expect(page).toHaveURL(/\/home$/);
      await expect(page.getByRole("heading", { level: 1 })).toContainText(
        /Good (morning|afternoon|evening),/,
      );
    });

    test(`signed-in session resumes into the console from /login (${user.email})`, async ({
      page,
      request,
    }) => {
      await loginAsTenantAdmin(page, request, user);

      // A signed-in admin hitting /login is redirected straight into the
      // console: /login -> /onboarding -> /home (an onboarded tenant leaves
      // the interview immediately).
      await page.goto("/login");
      await page.waitForURL(/\/home$/);
      await expect(page.getByRole("heading", { level: 1 })).toContainText(
        /Good (morning|afternoon|evening),/,
      );
    });

    test(`sign out returns to the login chat without a reload (${user.email})`, async ({
      page,
      request,
    }) => {
      await loginAsTenantAdmin(page, request, user);

      // The console shell (sidebar) renders the Sign out button on a chrome page.
      await page.goto("/home");
      await page.getByRole("button", { name: "Sign out" }).click();
      await page.getByTestId("confirm-accept").click();

      // The login chat must render immediately - no manual reload required.
      await expect(page.getByPlaceholder("you@example.com")).toBeVisible();
    });
  }
});

test.describe("tenant-admin login-in-chat (apex)", () => {

  test("the apex redirects to the login chat", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByPlaceholder("you@example.com")).toBeVisible();
  });
});

test.describe("tenant-admin login-in-chat errors", () => {

  test("wrong code shows a calm retry line", async ({ page }) => {
    await page.goto("/login");
    await page.getByPlaceholder("you@example.com").fill("owner@bytefix.dev");
    await page.getByRole("button", { name: "Send" }).click();
    await page.getByLabel("Digit 1").waitFor();

    for (let i = 0; i < 6; i++) {
      await page.getByLabel(`Digit ${i + 1}`).fill("0");
    }

    // GoTrue's own error (otp_expired) covers both "wrong" and "expired" -
    // it does not distinguish them the way the old backend-issued codes did.
    await expect(
      page.getByText("That code didn't work or expired. Try again, or resend."),
    ).toBeVisible();
  });
});
