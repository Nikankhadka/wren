/**
 * E2E for the public storefront (M-4).
 *
 * Surface: customer (http://localhost:3000/{slug}), written by the owner from
 * the console.
 *
 * The round trip is the point: what the owner types in Business is what a
 * customer reads at `/{slug}`, with nothing in between rewriting it. The
 * offerings-and-price half of that trip lives in business-hub.spec.ts, where
 * the editor is; this file covers the sections the storefront adds and the
 * way a customer gets from the page into a conversation.
 */

import { test, expect } from "@playwright/test";
import { DEMO_USERS, loginAsTenantAdmin } from "./auth-helpers";

const BYTEFIX = DEMO_USERS.find((u) => u.email === "owner@bytefix.dev")!;

test.describe("the public storefront", () => {
  test("the owner and public page do not expose an About section", async ({
    page,
    request,
  }) => {
    await loginAsTenantAdmin(page, request, BYTEFIX);
    await page.goto("/business/page");
    await expect(page.getByTestId("storefront-about")).toHaveCount(0);

    await page.goto("/bytefix");
    await expect(page.getByTestId("storefront-about")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Repairs", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Phones", exact: true })).toBeVisible();
  });

  test("a customer can open a conversation from the page", async ({ page }) => {
    await page.goto("/bytefix");

    // The page leads with who the business is, not with a chat box.
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Bytefix");

    await page.getByRole("button", { name: "Chat with Bytefix" }).click();
    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText("Bytefix");
  });

  test("offers one customer-facing chat entry", async ({ page }) => {
    await page.goto("/bytefix");
    const chatEntries = page.getByRole("button", { name: "Chat with Bytefix" });
    await expect(chatEntries).toHaveCount(1);
    await expect(chatEntries).toHaveText("");
    await expect(page.getByRole("button", { name: "Ask a question" })).toHaveCount(0);
  });

  /**
   * W-9 US-8: the assistant says what it is before anything else, and a tenant
   * that configured its own welcome is not greeted a second time. Both demo
   * tenants have a configured `config->customer.greeting` and both of those
   * greetings open with a hello, so this is the case that used to double up.
   * `lib/greeting.test.ts` covers the normalizer; this is the surface.
   */
  for (const tenant of [
    { slug: "bytefix", name: "Bytefix Repairs", adds: "I can quote a repair" },
    { slug: "lumident", name: "Lumident Dental", adds: "I can help you understand a treatment" },
  ]) {
    test(`${tenant.slug} opens with the identity line and greets once`, async ({ page }) => {
      await page.goto(`/${tenant.slug}`);
      await page.getByRole("button", { name: `Chat with ${tenant.name}` }).click();
      const sheet = page.getByRole("dialog", { name: `Chat with ${tenant.name}` });
      await expect(sheet).toBeVisible();

      const identity = `Hi, I'm ${tenant.name}'s assistant. How can I help today?`;
      await expect(sheet).toContainText(identity);

      // The identity line leads; the configured welcome is what follows it.
      const opening = await sheet.innerText();
      expect(opening.indexOf(identity)).toBeGreaterThanOrEqual(0);
      expect(opening.indexOf(tenant.adds)).toBeGreaterThan(opening.indexOf(identity));

      // And hello is said exactly once, by the identity line.
      expect(opening.match(/\b(hi|hello|hey)\b/gi) ?? []).toHaveLength(1);
    });
  }

  test("an unknown slug still gets the calm not-found page", async ({ page }) => {
    await page.goto("/no-such-business");
    // Asserted on what renders, not on the status: Next streams this page, so
    // `notFound()` after the first byte still returns 200 with the error shell
    // - the same trap the deploy smoke test documents (deploy.md, B-4).
    await expect(page.getByText("There's no business here.")).toBeVisible();
  });
});
