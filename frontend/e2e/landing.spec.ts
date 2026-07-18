/**
 * E2E browser tests for the marketing landing page.
 *
 * Surface: marketing (http://localhost:3000 - the bare apex host)
 *
 * The landing page's job is routing each visitor profile to its own front
 * door, so the load-bearing assertions here are the absolute cross-surface
 * hrefs (built from the request host by surfaceUrl, never hardcoded).
 */

import { test, expect } from "@playwright/test";

const APEX = "http://localhost:3000";

test.describe("marketing landing page", () => {
  test("bare host renders the landing page, not a 404", async ({ page }) => {
    const response = await page.goto(`${APEX}/`);
    expect(response?.status()).toBe(200);
    await expect(
      page.getByRole("heading", { level: 1, name: "Give your business its own AI agent." }),
    ).toBeVisible();
  });

  test("routes each user profile to its own surface", async ({ page }) => {
    await page.goto(`${APEX}/`);

    // Business owner -> tenant-admin surface (app.*)
    await expect(page.getByRole("link", { name: "Create your agent" })).toHaveAttribute(
      "href",
      "http://app.localhost:3000/signup",
    );
    await expect(page.getByRole("link", { name: "Sign in to your console" })).toHaveAttribute(
      "href",
      "http://app.localhost:3000/login",
    );

    // Customer -> live demo tenant chat ({slug}.*)
    await expect(page.getByRole("link", { name: "Chat with the demo shop" })).toHaveAttribute(
      "href",
      "http://bytefix.localhost:3000/",
    );

    // Platform operator -> admin surface (admin.*)
    await expect(page.getByRole("link", { name: "Platform sign in" })).toHaveAttribute(
      "href",
      "http://admin.localhost:3000/login",
    );
  });

  test("www host renders the landing page too, never a tenant named www", async ({ page }) => {
    const response = await page.goto("http://www.localhost:3000/");
    expect(response?.status()).toBe(200);
    await expect(
      page.getByRole("heading", { level: 1, name: "Give your business its own AI agent." }),
    ).toBeVisible();
  });

  test("renders without horizontal overflow at 375px", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(`${APEX}/`);
    await expect(
      page.getByRole("heading", { level: 1, name: "Give your business its own AI agent." }),
    ).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBe(0);
  });

  test("tenant subdomains still resolve to the customer surface", async ({ page }) => {
    await page.goto("http://bytefix.localhost:3000/");
    // The customer chat surface, not the landing page.
    await expect(
      page.getByRole("heading", { name: "Give your business its own AI agent." }),
    ).toHaveCount(0);
  });
});
