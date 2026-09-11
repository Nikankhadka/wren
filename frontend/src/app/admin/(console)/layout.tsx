"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Icon, type IconName } from "@/components/ui/Icon";
import { Drawer } from "@/components/ui/Drawer";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";

/**
 * T-033: auth guard + shell for the platform surface (frontend.md 7.3).
 * Anything other than a platform admin (401/403/network) bounces to /login.
 * The shell shares the tenant console's sidebar idiom (surface-container active
 * pill, filled glyph) for a single Tenants item; Dashboards/Settings sit in
 * the disabled "soon" group to match. Login stays outside this (console) group
 * with its own centered-card layout, same structure as the tenant-admin
 * surface.
 */
const NAV_ITEMS: { href: string; label: string; icon: IconName }[] = [
  { href: "/admin", label: "Tenants", icon: "groups" },
];

const SOON_ITEMS = ["Dashboards", "Settings"] as const;

export default function PlatformConsoleLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { session, isLoading: authLoading, signOut } = useAuth();
  const [platformAuthed, setPlatformAuthed] = useState(false);
  const [platformChecking, setPlatformChecking] = useState(true);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- deliberate drawer reset on navigation */
    setNavOpen(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [pathname]);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- deliberate state reset on session change */
    if (!session) {
      setPlatformChecking(false);
      return;
    }
    setPlatformAuthed(false);
    setPlatformChecking(true);
    /* eslint-enable react-hooks/set-state-in-effect */
    let active = true;
    apiFetch<{ ok: boolean }>("/api/platform/ping")
      .then(() => {
        if (active) setPlatformAuthed(true);
      })
      .catch(() => {
        if (active) router.replace("/admin/login");
      })
      .finally(() => {
        if (active) setPlatformChecking(false);
      });
    return () => { active = false; };
  }, [session, router]);

  if (authLoading || platformChecking) {
    return <div aria-busy="true" className="h-dvh bg-bg" />;
  }
  if (!session || !platformAuthed) return null;

  const navContent = (
    <>
      <span className="px-3 py-2 text-title-3 font-semibold text-text">Agencx</span>
      <ul className="mt-2 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={[
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-body-sm font-medium transition-colors duration-(--duration-fast)",
                  active
                    ? "bg-surface-container text-text"
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
              className="flex items-center justify-between rounded-md px-3 py-2 text-body-sm font-medium text-text-secondary"
            >
              {label}
              <span className="rounded-full bg-surface px-2 py-0.5 text-caption font-medium text-text-tertiary">
                soon
              </span>
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-auto pt-4">
        <button
          onClick={() => signOut()}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-body-sm font-medium text-text-secondary hover:bg-surface-container hover:text-text transition-colors duration-(--duration-fast)"
        >
          <Icon name="logout" filled={false} size={20} />
          Sign out
        </button>
      </div>
    </>
  );

  return (
    <div className="flex h-dvh w-full">
      <nav
        aria-label="Platform"
        className="hidden w-56 shrink-0 flex-col gap-1 border-r border-border bg-surface-sunken p-4 lg:flex"
      >
        {navContent}
      </nav>

      <Drawer open={navOpen} onClose={() => setNavOpen(false)}>
        {navContent}
      </Drawer>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto bg-bg">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-surface px-4 lg:hidden">
          <button type="button" onClick={() => setNavOpen(true)} aria-label="Menu">
            <Icon name="menu" size={24} />
          </button>
          <span className="truncate text-title-3 font-semibold text-text">Agencx</span>
        </header>
        <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-8 sm:py-8">{children}</main>
      </div>
    </div>
  );
}
