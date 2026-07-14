/**
 * Shared E2E auth helpers for Wren.
 *
 * Centralises demo credentials and login interaction logic so individual spec
 * files don't duplicate selectors and input sequences.
 */

import type { Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Demo identities (from backend/seeds/seed_demo.py)
// ---------------------------------------------------------------------------

export interface DemoUser {
  email: string;
  password: string;
  surface: "tenant-admin" | "platform";
  tenantName?: string; // expected tenant name on the post-login card (tenant-admin only)
}

export const DEMO_USERS: DemoUser[] = [
  {
    email: "owner@bytefix.dev",
    password: "wren-demo",
    surface: "tenant-admin",
    tenantName: "Bytefix Repairs",
  },
  {
    email: "owner@lumident.dev",
    password: "wren-demo",
    surface: "tenant-admin",
    tenantName: "Lumident Dental",
  },
  {
    email: "founder@wren.dev",
    password: "wren-demo",
    surface: "platform",
  },
];

// ---------------------------------------------------------------------------
// Host helpers (Next.js 16 proxy.ts routes by Host header)
// ---------------------------------------------------------------------------

/** Reconstruct the tenant-admin host. */
export function tenantAdminHost(): string {
  return "app.localhost:3000";
}

/** Reconstruct the platform host. */
export function platformHost(): string {
  return "admin.localhost:3000";
}

// ---------------------------------------------------------------------------
// Login interaction helpers
// ---------------------------------------------------------------------------

/** Fill and submit the login form on the current page. */
export async function submitLoginForm(
  page: Page,
  email: string,
  password: string
): Promise<void> {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
}

/**
 * Log in as a tenant-admin user, then verify the post-login card shows the
 * expected tenant name.
 */
export async function loginAsTenantAdmin(page: Page, user: DemoUser): Promise<void> {
  await page.goto("/login");
  await submitLoginForm(page, user.email, user.password);
  // T-004: on success the login page renders a "Signed in" card with the
  // tenant name and slug.
  await page.getByRole("heading", { name: "Signed in" }).waitFor({ timeout: 10_000 });
  if (user.tenantName) {
    await page.getByText(user.tenantName).waitFor({ timeout: 5_000 });
  }
}

/**
 * Log in as a platform-admin user, then verify redirect to the admin console
 * root ("/") which shows the Tenants page.
 */
export async function loginAsPlatformAdmin(page: Page, user: DemoUser): Promise<void> {
  await page.goto("/login");
  await submitLoginForm(page, user.email, user.password);
  // T-033: on success the page redirects to "/" which is the Tenants page.
  await page.getByRole("heading", { name: "Tenants" }).waitFor({ timeout: 10_000 });
}
