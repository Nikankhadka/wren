/**
 * E2E browser tests for the four marketing content pages: /product, /pricing,
 * /demo, /about (all on the bare apex host, rewritten to /marketing-surface/*
 * by proxy.ts).
 *
 * Shared checks per page: 200 status, exactly one h1, the four nav links, and
 * no horizontal overflow at 375px. Page-specific checks assert the load-bearing
 * cross-surface hrefs (built from the request host by surfaceUrl, never
 * hardcoded) and the copy that the phase-4 accept rule pins down.
 */

import { test, expect, type Page } from "@playwright/test";

const APEX = "http://localhost:3000";

const NAV_LINKS = ["Product", "Pricing", "Demo", "About"] as const;

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBe(0);
}

for (const path of ["/product", "/pricing", "/demo", "/about"]) {
  test.describe(`marketing page ${path}`, () => {
    test("returns 200 and renders exactly one h1", async ({ page }) => {
      const response = await page.goto(`${APEX}${path}`);
      expect(response?.status()).toBe(200);
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    });

    test("header nav shows all four links", async ({ page }) => {
      await page.goto(`${APEX}${path}`);
      for (const label of NAV_LINKS) {
        await expect(page.getByRole("link", { name: label }).first()).toBeVisible();
      }
    });

    test("renders without horizontal overflow at 375px", async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 812 });
      await page.goto(`${APEX}${path}`);
      await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
      await expectNoHorizontalOverflow(page);
    });
  });
}

test.describe("/product page specifics", () => {
  test("deep-links resolve to the demo chat and signup surfaces", async ({ page }) => {
    await page.goto(`${APEX}/product`);
    await expect(page.getByRole("link", { name: "Try the live demo chat" })).toHaveAttribute(
      "href",
      "http://bytefix.localhost:3000/",
    );
    await expect(page.getByRole("link", { name: "Create your agent" }).first()).toHaveAttribute(
      "href",
      "http://app.localhost:3000/signup",
    );
  });
});

test.describe("/pricing page specifics", () => {
  test("shows the beta banner and exactly three tier cards", async ({ page }) => {
    await page.goto(`${APEX}/pricing`);
    await expect(page.getByText("Wren is free while in beta.")).toBeVisible();
    await expect(page.getByRole("article")).toHaveCount(3);
  });
});

test.describe("/demo page specifics", () => {
  test("deep-links resolve to all three surfaces and creds are shown", async ({ page }) => {
    await page.goto(`${APEX}/demo`);
    await expect(page.getByRole("link", { name: "Open the Bytefix chat" })).toHaveAttribute(
      "href",
      "http://bytefix.localhost:3000/",
    );
    await expect(page.getByRole("link", { name: "Sign in to the console" })).toHaveAttribute(
      "href",
      "http://app.localhost:3000/login",
    );
    await expect(
      page.getByRole("link", { name: "Sign in to the admin console" }),
    ).toHaveAttribute("href", "http://admin.localhost:3000/login");

    await expect(page.getByText("owner@bytefix.dev").first()).toBeVisible();
    await expect(page.getByText("wren-demo").first()).toBeVisible();
  });
});

test.describe("/about page specifics", () => {
  test("states the trust mechanics verbatim", async ({ page }) => {
    await page.goto(`${APEX}/about`);
    await expect(page.getByText(/row-level security/i).first()).toBeVisible();
    await expect(page.getByText(/integer cents/i).first()).toBeVisible();
  });
});

test.describe("marketing nav wiring", () => {
  test("clicking Pricing in the header nav from / lands on a clean /pricing", async ({ page }) => {
    await page.goto(`${APEX}/`);
    await page.getByRole("link", { name: "Pricing" }).first().click();
    await expect(page).toHaveURL(`${APEX}/pricing`);
    await expect(
      page.getByRole("heading", { level: 1, name: "Simple pricing, still in beta." }),
    ).toBeVisible();
  });
});
