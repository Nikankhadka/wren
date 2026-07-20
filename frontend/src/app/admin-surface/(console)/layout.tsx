"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Icon, type IconName } from "@/components/ui/Icon";
import { apiFetch } from "@/lib/api";

/**
 * T-033: auth guard + shell for the platform surface (frontend.md 7.3).
 * Anything other than a platform admin (401/403/network) bounces to /login.
 * The shell shares the tenant console's sidebar idiom (accent-container active
 * pill, filled glyph) for a single Tenants item; Dashboards/Settings sit in
 * the disabled "soon" group to match. Login stays outside this (console) group
 * with its own centered-card layout, same structure as the tenant-admin
 * surface.
 */
const NAV_ITEMS: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Tenants", icon: "groups" },
];

const SOON_ITEMS = ["Dashboards", "Settings"] as const;

export default function PlatformConsoleLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
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
    <div className="flex min-h-screen w-full">
      <nav
        aria-label="Platform"
        className="flex w-56 shrink-0 flex-col gap-1 border-r border-border bg-surface-sunken p-4"
      >
        <span className="px-3 py-2 text-title-3 font-semibold text-text">Wren</span>
        <ul className="mt-2 flex flex-col gap-0.5">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-body-sm font-medium transition-colors duration-fast",
                    active
                      ? "bg-accent-container text-text-inverse"
                      : "text-text-secondary hover:bg-surface-container hover:text-text",
                  ].join(" ")}
                >
                  <Icon name={item.icon} filled={active} size={20} />
                  {item.label}
                </Link>
              </li>
            );
          })}
          {SOON_ITEMS.map((label) => (
            <li key={label}>
              <span
                aria-disabled="true"
                className="flex items-center justify-between rounded-md px-3 py-2 text-body-sm font-medium text-text-tertiary"
              >
                {label}
                <span className="rounded-full bg-surface px-2 py-0.5 text-caption font-medium text-text-tertiary">
                  soon
                </span>
              </span>
            </li>
          ))}
        </ul>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto bg-bg">
        <main className="mx-auto w-full max-w-5xl px-8 py-8">{children}</main>
      </div>
    </div>
  );
}
