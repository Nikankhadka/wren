"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiFetch, ApiError } from "@/lib/api";
import { getSupabase } from "@/lib/supabase";

interface TenantSignupResponse {
  tenant_id: string;
  slug: string;
}

const SLUG_RE = /^[a-z0-9](-?[a-z0-9])*$/;

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}

/**
 * T-004: business signup. Creates the Supabase user, then provisions the
 * tenant (tenants + tenant_config + owner users row) via POST /api/tenants
 * with that user's access token.
 */
export default function SignupPage() {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<TenantSignupResponse | null>(null);
  const [needsConfirm, setNeedsConfirm] = useState(false);

  const slugError =
    slug && (!SLUG_RE.test(slug) || slug.length < 3)
      ? "3-40 chars: lowercase letters, digits, single dashes"
      : undefined;

  function handleNameChange(value: string) {
    setName(value);
    if (!slugTouched) setSlug(slugify(value));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (slugError || !slug) {
      setError("Choose a valid workspace address first.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const supabase = getSupabase();
      // Reuse an existing session for this email (a retry after a slug
      // conflict, or a confirmed user returning to finish setup): re-running
      // signUp for an already-registered email fails and would dead-end the
      // flow with a Supabase account that has no tenant.
      let session = (await supabase.auth.getSession()).data.session;
      if (session?.user.email?.toLowerCase() !== email.trim().toLowerCase()) {
        session = null;
      }
      if (!session) {
        const { data, error: authError } = await supabase.auth.signUp({ email, password });
        if (authError) {
          setError(authError.message);
          return;
        }
        session = data.session;
      }
      if (!session) {
        // Project has email confirmation enabled: no session yet, so the
        // tenant cannot be provisioned until the user confirms and logs in.
        setNeedsConfirm(true);
        return;
      }
      setDone(await apiFetch<TenantSignupResponse>("/api/tenants", {
        method: "POST",
        body: JSON.stringify({ slug, name }),
      }));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-1">
          <h1 className="text-title-2 font-semibold">You&apos;re in</h1>
          <p className="mt-2 text-body-sm text-text-secondary">
            <span className="font-medium text-text">{name}</span> is set up. Your assistant will
            live at <span className="font-mono text-footnote">{done.slug}.wren.app</span>.
          </p>
          <p className="mt-2 text-body-sm text-text-secondary">
            Next: onboarding walks you through teaching it your business.
          </p>
          <div className="mt-6">
            <Link href="/login">
              <Button variant="secondary">Go to your console</Button>
            </Link>
          </div>
        </div>
      </main>
    );
  }

  if (needsConfirm) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-1">
          <h1 className="text-title-2 font-semibold">Check your email</h1>
          <p className="mt-2 text-body-sm text-text-secondary">
            Confirm your address, log in, then return here and submit again to finish setting up{" "}
            {name || "your business"}.
          </p>
          <div className="mt-6">
            <Link href="/login">
              <Button variant="secondary">Go to login</Button>
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-1">
        <h1 className="text-title-2 font-semibold">Create your business</h1>
        <p className="mt-1 text-body-sm text-text-secondary">
          Your own AI support and sales agent, in minutes.
        </p>
        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4" noValidate>
          <Input
            label="Business name"
            required
            value={name}
            onChange={(e) => handleNameChange(e.target.value)}
          />
          <Input
            label="Workspace address"
            required
            value={slug}
            onChange={(e) => {
              setSlugTouched(true);
              setSlug(e.target.value);
            }}
            help={slug ? `${slug}.wren.app` : "lowercase-name for your public link"}
            error={slugError}
          />
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
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={error ?? undefined}
          />
          <Button type="submit" loading={busy}>
            Create business
          </Button>
        </form>
        <p className="mt-4 text-footnote text-text-secondary">
          Already set up?{" "}
          <Link href="/login" className="text-accent hover:text-accent-hover font-medium">
            Log in
          </Link>
        </p>
      </div>
    </main>
  );
}
