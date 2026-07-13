"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/**
 * T-031: the Surface-2 admin-console shell (frontend.md 7.2). A left sidebar
 * nav wraps every authed console page; login/signup stay outside this route
 * group and keep their own centered-card layout. Route groups never appear in
 * the URL, so /knowledge and /onboarding are unchanged by living under
 * (console).
 *
 * Dashboards and Settings are specced (7.2) but land in T-034/later - they
 * render as visibly-disabled items rather than dead links so the nav is
 * honest about what exists today.
 *
 * 7.2 specs "icons + labels"; no icon set exists yet in this codebase (see
 * EmptyState's same note), so this ships labels-only until one is chosen.
 */
const NAV_ITEMS = [
  { href: "/onboarding", label: "Onboarding" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/conversations", label: "Conversations" },
  { href: "/escalations", label: "Escalations" },
  { href: "/pricing", label: "Pricing" },
] as const;

const SOON_ITEMS = ["Dashboards", "Settings"] as const;

export default function ConsoleLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen w-full">
      <nav
        aria-label="Console"
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
                    "block rounded-md px-3 py-2 text-body-sm font-medium transition-colors duration-fast",
                    active
                      ? "bg-accent-subtle text-accent"
                      : "text-text-secondary hover:bg-surface hover:text-text",
                  ].join(" ")}
                >
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

      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">{children}</div>
    </div>
  );
}
