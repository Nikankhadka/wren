"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

/**
 * T-033: auth guard + shell for the platform surface (frontend.md 7.3).
 * Anything other than a platform admin (401/403/network) bounces to /login.
 * Deliberately no sidebar nav - the surface is a single Tenants page at core
 * scope, so the shell is just the shared bg + content column. Login stays
 * outside this (console) group with its own centered-card layout, same
 * structure as the tenant-admin surface.
 */
export default function PlatformConsoleLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    let active = true;
    apiFetch<{ ok: boolean }>("/api/platform/ping")
      .then(() => {
        if (active) setAuthed(true);
      })
      .catch(() => {
        if (active) router.replace("/login");
      });
    return () => {
      active = false;
    };
  }, [router]);

  if (!authed) {
    return <div aria-busy="true" className="min-h-screen bg-bg" />;
  }

  return (
    <div className="min-h-screen bg-bg">
      <main className="mx-auto w-full max-w-5xl px-8 py-8">{children}</main>
    </div>
  );
}
