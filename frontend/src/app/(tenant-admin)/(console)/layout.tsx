"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Icon } from "@/components/ui/Icon";
import { BrandMark } from "@/components/ui/BrandMark";
import { TabBar, isTabActive, type TabItem } from "@/components/ui/TabBar";
import { useAuth } from "@/components/AuthProvider";
import { apiFetch } from "@/lib/api";
import { useApiQuery } from "@/lib/useApiQuery";
import type { ConversationSummary } from "@/lib/api-schemas";

/**
 * E-1 / D21: the tenant app shell. Three destinations - Home, Chats, Business
 * - as a bottom tab bar below `lg` and as the left sidebar at `lg+`. One nav
 * model, two renderings.
 *
 * D21 replaced D18's two tabs because the prototype's home Copilot thread sits
 * underneath its tab bar with no tab of its own, and `navBack()` lights Chats
 * when you land there. "Your thread with the assistant" and "the customers'
 * threads with the assistant" are different places, so they get different tabs.
 *
 * The tab bar is persistent, including over drill-downs: in the prototype
 * `#screen-layer` is z-index 20 and stops 64px short of the bottom while
 * `#tabbar` is 21, so a pushed screen never covers the bar. Drill-downs keep
 * their `ScreenTopbar` back control on top of that; a tab destination does not
 * (`back={false}`).
 *
 * /onboarding is the one chrome-free route. The prototype's app has no
 * navigation at all until the business is live (`#phone.post`), and
 * `onboarding.completed` is that signal - the page itself sends a completed
 * owner on to /home.
 *
 * E-2 - hidden until Stage 2, never deleted. The Wren-era screens
 * (/conversations with its trace viewer, /escalations, /pricing, /knowledge,
 * /dashboards) are absent from NAV_ITEMS and from nothing else: their routes,
 * code and tests all stay, and typing one of their URLs still serves it. They
 * are working machinery aimed at an operator, and Stage 2 re-lands them with a
 * purpose - deleting them now would mean rebuilding them later, and stripping
 * their tests would let them rot in place while looking fine.
 *
 * The hiding is therefore this list and nothing more. Anyone re-adding one:
 * that is a Stage 2 decision, not a nav tidy-up.
 */
const CHROME_FREE_PREFIXES = ["/onboarding"];

const NAV_ITEMS: TabItem[] = [
  { href: "/home", label: "Home", icon: "home" },
  { href: "/chats", label: "Chats", icon: "forum" },
  // No `owns` entry: M-4 moved every Business drill-down under /business
  // (page, offerings, details), so the tab claims them by prefix alone.
  { href: "/business", label: "Business", icon: "dashboard" },
];

interface TenantMe {
  slug: string;
  name: string;
  brand?: Record<string, unknown>;
}

export default function ConsoleLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, isLoading, signOut } = useAuth();
  const [tenant, setTenant] = useState<TenantMe | null>(null);

  useEffect(() => {
    if (!isLoading && !session) {
      router.replace("/");
    }
  }, [isLoading, session, router]);

  useEffect(() => {
    if (!session) return;
    apiFetch<TenantMe>("/api/tenants/me")
      .then(setTenant)
      .catch(() => setTenant(null));
  }, [session]);

  // The prototype's `#ndot`, widened into a count: the Chats tab says how
  // many are waiting, from wherever the owner happens to be standing. Same
  // source as the Chats screen's "Action needed" filter and the home
  // WaitingPanel, so none of the three can ever disagree.
  const conversations = useApiQuery<ConversationSummary[]>("/api/conversations", {
    enabled: Boolean(session),
    refetchInterval: 4000,
  });
  const waitingCount = (conversations.data ?? []).filter((row) => row.needs_attention).length;
  const items = NAV_ITEMS.map((item) =>
    item.href === "/chats" ? { ...item, count: waitingCount } : item
  );

  if (isLoading) {
    return <div aria-busy="true" className="h-dvh bg-bg" />;
  }
  if (!session) return null;
  if (CHROME_FREE_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return <>{children}</>;
  }

  const displayName =
    (tenant?.brand?.["display_name"] as string | undefined) ?? tenant?.name ?? "Agencx";
  const logoUrl = tenant?.brand?.["logo_url"] as string | undefined;

  return (
    <div className="flex h-dvh w-full">
      <nav
        aria-label="Console"
        className="hidden w-56 shrink-0 flex-col gap-1 border-r border-border bg-surface-sunken p-4 lg:flex"
      >
        <span className="flex items-center gap-2.5 px-3 py-2">
          <BrandMark logoUrl={logoUrl} name={displayName} />
          <span className="truncate text-title-3 font-semibold text-text">{displayName}</span>
        </span>
        <ul className="mt-2 flex flex-col gap-0.5">
          {items.map((item) => {
            const active = isTabActive(item, pathname);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  aria-label={item.count ? `${item.label}, ${item.count} waiting` : undefined}
                  className={[
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-body-sm font-medium transition-colors duration-(--duration-fast)",
                    active
                      ? "bg-accent-container text-accent"
                      : "text-text-secondary hover:bg-surface-container hover:text-text",
                  ].join(" ")}
                >
                  <Icon name={item.icon} filled={active} size={20} />
                  {item.label}
                  {item.count ? (
                    <span
                      aria-hidden="true"
                      className="ml-auto flex h-4 min-w-4 items-center justify-center rounded-full bg-highlight px-0.5 text-badge font-semibold text-text"
                    >
                      {item.count > 9 ? "9+" : item.count}
                    </span>
                  ) : null}
                </Link>
              </li>
            );
          })}
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
      </nav>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        <TabBar items={items} pathname={pathname} />
      </div>
    </div>
  );
}
