/**
 * Credential and infrastructure validation smoke tests.
 *
 * These run first to confirm the auth stack is healthy before any browser-based
 * login tests execute. They use Playwright's API testing (request fixture) so
 * no browser is required.
 */

import { test, expect } from "@playwright/test";
import { DEMO_USERS } from "./auth-helpers";

// ---------------------------------------------------------------------------
// Environment variable checks
// ---------------------------------------------------------------------------

test.describe("environment variables", () => {
  test("NEXT_PUBLIC_SUPABASE_URL is set", () => {
    expect(process.env.NEXT_PUBLIC_SUPABASE_URL, "NEXT_PUBLIC_SUPABASE_URL must be set in frontend/.env.local").toBeTruthy();
  });

  test("NEXT_PUBLIC_SUPABASE_ANON_KEY is set", () => {
    expect(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY, "NEXT_PUBLIC_SUPABASE_ANON_KEY must be set in frontend/.env.local").toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Service health checks
// ---------------------------------------------------------------------------

test.describe("service health", () => {
  const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost:54321";
  const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  test("GoTrue auth service is healthy", async ({ request }) => {
    const resp = await request.get(`${SUPABASE_URL}/health`);
    expect(resp.status(), "GoTrue health check failed - is docker compose running?").toBe(200);
  });

  test("backend API is healthy", async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/health`);
    expect(resp.status(), "Backend health check failed - is uvicorn running?").toBe(200);
  });
});

// ---------------------------------------------------------------------------
// Demo user credential verification (direct GoTrue API, no browser)
// ---------------------------------------------------------------------------

test.describe("demo user credentials", () => {
  const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost:54321";
  const ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

  for (const user of DEMO_USERS) {
    test(`${user.email} can authenticate via GoTrue`, async ({ request }) => {
      const resp = await request.post(
        `${SUPABASE_URL}/auth/v1/token?grant_type=password`,
        {
          headers: {
            apikey: ANON_KEY,
            "Content-Type": "application/json",
          },
          data: {
            email: user.email,
            password: user.password,
          },
        }
      );
      expect(resp.status()).toBe(200);

      const body = await resp.json();
      expect(body.access_token).toBeTruthy();
      expect(body.user.email).toBe(user.email);
    });
  }

  test("invalid credentials return 400", async ({ request }) => {
    const resp = await request.post(
      `${SUPABASE_URL}/auth/v1/token?grant_type=password`,
      {
        headers: {
          apikey: ANON_KEY,
          "Content-Type": "application/json",
        },
        data: {
          email: "nobody@nowhere.dev",
          password: "wrong",
        },
      }
    );
    expect(resp.status()).toBe(400);
  });
});
