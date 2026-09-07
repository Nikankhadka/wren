import { defineConfig, devices } from "@playwright/test";
import dotenv from "dotenv";
import path from "path";

// Load frontend/.env.local so Playwright tests (including API-level credential
// checks) can read NEXT_PUBLIC_SUPABASE_* and other env vars.
dotenv.config({ path: path.resolve(__dirname, ".env.local") });

/**
 * E2E test configuration for Agencx.
 *
 * One origin, three surfaces by path (D22):
 *   Tenant-admin:  http://localhost:3000        (/, /login, /home, ...)
 *   Platform:      http://localhost:3000/admin
 *   Customer:      http://localhost:3000/{slug}
 *
 * Specs use relative paths against baseURL; none of them names a host.
 *
 * The Next.js dev server is assumed to be running on port 3000. On CI the
 * config launches it automatically; locally it reuses the existing server.
 */

const PORT = 3000;
// E2E_BASE_URL exists for the containerized runner (compose profile e2e): the
// browser inside that container must use a hostname it can resolve, and
// localhost would point at itself (F-3). Defaults unchanged for local runs.
const BASE_URL = process.env.E2E_BASE_URL ?? `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  // Serial, locally as well as on CI. Every spec drives the one seeded demo
  // world (backend/seeds/seed_demo.py) against one backend, so parallel
  // workers mutate shared state: two tests logging in as the same demo owner
  // race on that owner's login code, and the newer code correctly supersedes
  // the older, failing whichever test asked first. CI already ran with one
  // worker, so this only makes local runs match it.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      testIgnore: /mobile|w7-screenshots\.spec\.ts|w9-repro\.spec\.ts/,
    },
    {
      name: "mobile-chrome",
      use: { ...devices["iPhone 13"] },
      // Must match spec files only. A per-project testMatch REPLACES the
      // default `*.spec.ts` pattern, so a bare /mobile/ also claimed
      // mobile-helpers.ts as a test file - and Playwright refuses to let one
      // test file import another. Harmless until a mobile spec imported the
      // helpers it was written for.
      testMatch: /mobile.*\.spec\.ts$/,
    },
  ],

  // Reuse the existing dev server in local dev; launch it in CI. The
  // containerized runner (compose profile e2e) drops webServer entirely: the
  // stack must already be up (make dev), and spawning next dev inside the
  // Playwright image would race the real frontend.
  ...(process.env.E2E_REUSE_SERVER
    ? {}
    : {
        webServer: {
          command: "npm run dev",
          url: BASE_URL,
          reuseExistingServer: !process.env.CI,
          timeout: 30_000,
          cwd: __dirname,
        },
      }),
});
