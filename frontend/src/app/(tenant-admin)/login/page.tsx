"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiFetch, ApiError } from "@/lib/api";
import { getSupabase } from "@/lib/supabase";

interface TenantMe {
  tenant_id: string;
  slug: string;
  name: string;
}

/**
 * T-004: tenant-admin login. On success it proves the full auth path by
 * calling the authed backend probe (GET /api/tenants/me), showing the
 * caller's tenant, and redirecting into the admin console shell.
 */
export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [me, setMe] = useState<TenantMe | null>(null);

  useEffect(() => {
    // Resume an existing session on load so a signed-in admin is not shown
    // the login form again - redirect straight into the console.
    apiFetch<TenantMe>("/api/tenants/me")
      .then((data) => {
        setMe(data);
        router.replace("/dashboards");
      })
      .catch(() => setMe(null));
  }, [router]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const { error: authError } = await getSupabase().auth.signInWithPassword({
        email,
        password,
      });
      if (authError) {
        setError(authError.message);
        return;
      }
      await apiFetch<TenantMe>("/api/tenants/me");
      router.replace("/dashboards");
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        // Valid account, no tenant yet (e.g. confirmed email but never finished
        // signup) - point at the recovery path instead of the raw backend detail.
        setError("This account has no business yet - finish setup on the signup page.");
      } else {
        setError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (me) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-1">
          <h1 className="text-title-2 font-semibold">Signed in</h1>
          <p className="mt-2 text-body-sm text-text-secondary">
            Redirecting to the admin console...
          </p>
          <div className="mt-6">
            <Button variant="secondary" onClick={() => router.push("/dashboards")}>
              Go to Dashboards
            </Button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-1">
        <h1 className="text-title-2 font-semibold">Log in</h1>
        <p className="mt-1 text-body-sm text-text-secondary">Wren admin console</p>
        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4" noValidate>
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={error ?? undefined}
          />
          <Button type="submit" loading={busy}>
            Log in
          </Button>
        </form>
        <p className="mt-4 text-footnote text-text-secondary">
          New to Wren?{" "}
          <Link href="/signup" className="text-accent hover:text-accent-hover font-medium">
            Create your business
          </Link>
        </p>
      </div>
    </main>
  );
}
