"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";

/**
 * T-031: the Surface-2 admin-console shell (frontend.md 7.2). A left sidebar
 * nav wraps every authed console page; login/signup stay outside this route
 * group and keep their own centered-card layout. Route groups never appear in
 * the URL, so /knowledge and /onboarding are unchanged by living under
 * (console).
 *
 * Settings is specced (7.2) but lands later - it renders as a visibly-disabled
 * item rather than a dead link so the nav is honest about what exists today.
 * Dashboards is live as of T-034.
 *
 * 7.2 specs "icons + labels": each item carries a Material Symbol; the active
 * item is an accent-container pill with the filled glyph, inactive items are
 * quiet text with the outlined glyph.
 */
const NAV_ITEMS: { href: string; label: string; icon: IconName }[] = [
  { href: "/dashboards", label: "Dashboards", icon: "dashboard" },
  { href: "/onboarding", label: "Onboarding", icon: "rocket_launch" },
  { href: "/knowledge", label: "Knowledge", icon: "folder_open" },
  { href: "/conversations", label: "Conversations", icon: "forum" },
  { href: "/escalations", label: "Escalations", icon: "support_agent" },
  { href: "/pricing", label: "Pricing", icon: "sell" },
];

const SOON_ITEMS = ["Settings"] as const;

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

      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">{children}</div>
    </div>
  );
}
