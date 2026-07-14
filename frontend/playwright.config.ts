import { defineConfig, devices } from "@playwright/test";
import dotenv from "dotenv";
import path from "path";

// Load frontend/.env.local so Playwright tests (including API-level credential
// checks) can read NEXT_PUBLIC_SUPABASE_* and other env vars.
dotenv.config({ path: path.resolve(__dirname, ".env.local") });

/**
 * E2E test configuration for Wren.
 *
 * Tenant-admin surface:  http://app.localhost:3000
 * Platform surface:      http://admin.localhost:3000
 * Customer surface:      http://{slug}.localhost:3000
 *
 * The Next.js dev server is assumed to be running on port 3000. On CI the
 * config launches it automatically; locally it reuses the existing server.
 */

const PORT = 3000;
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
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
    },
  ],

  // Reuse the existing dev server in local dev; launch it in CI.
  webServer: {
    command: "npm run dev",
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    cwd: __dirname,
  },
});
