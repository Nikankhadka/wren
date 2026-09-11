"use client";

import Link from "next/link";
import { Icon, type IconName } from "./Icon";

export interface TabItem {
  href: string;
  label: string;
  icon: IconName;
  /**
   * Extra path prefixes this tab owns. A drill-down does not have to live under
   * its tab's URL - Settings hangs off the Business hub but sits at /settings -
   * and a tab that goes dark while the owner is inside it is exactly the
   * "where am I" failure the bar exists to prevent.
   */
  owns?: string[];
  /**
   * How many things on this tab want the owner - the prototype's `#ndot`
   * (a bare 8px dot) widened into a number, since "5 waiting" is worth more
   * than "something is waiting". 0 or undefined draws nothing.
   */
  count?: number;
}

/**
 * Which tab owns the current path. Exported because the sidebar and the bar are
 * two renderings of one nav model: if they computed this separately they could
 * disagree, and the one that is wrong is whichever the owner is looking at.
 */
export function isTabActive(item: TabItem, pathname: string): boolean {
  const under = (base: string) => pathname === base || pathname.startsWith(`${base}/`);
  return under(item.href) || (item.owns ?? []).some(under);
}

/**
 * One nav idiom for every surface. Active is accent text on a 9% accent wash;
 * inactive is the surface's own muted text with an accent wash on hover. The
 * inactive text is the only per-surface choice, and it is a contrast choice:
 * `text-text-secondary` on the light sidebars (AA on `bg-surface-sunken`),
 * `text-ink-a40` on the mobile bar (the prototype's `--c-muted`).
 */
export function navTone(active: boolean, inactiveText: string): string {
  return active
    ? "bg-accent-a09 text-accent-active"
    : `${inactiveText} hover:bg-accent-a07 hover:text-accent-active`;
}

/**
 * E-1 / D21: the tenant app's mobile nav. Three destinations - Home, Chats,
 * Business - as a persistent bottom bar below `lg`; at `lg+` the same items
 * render as the console sidebar and this is hidden.
 *
 * Ported from `#tabbar` in agencx-prototype-v6.html. Two things about the
 * geometry are load-bearing and easy to lose: the bar is 64px but the tab
 * inside it is a 48px pill with an 8px inset (that inset is what makes the
 * active state read as a pill rather than a full-height block), and the safe
 * area is padding on the bar, not margin under it, so the bar's own surface
 * still reaches the bottom of the screen on a home-indicator device.
 *
 * The active idiom is the prototype's - accent text on a 9% accent wash - and
 * every other nav in the app wears the same one through `navTone` (tenant and
 * platform sidebars, storefront categories). Three tabs sit side by side on a
 * small surface and a solid fill repeated three times reads as loud; the wash
 * is why the active state reads as a pill rather than a block. The bar's
 * inactive text stays the prototype's muted tone; the light sidebars use
 * `text-text-secondary` instead, which is the AA choice on their background.
 */
export function TabBar({ items, pathname }: { items: TabItem[]; pathname: string }) {
  return (
    <nav
      aria-label="Main"
      className="sticky bottom-0 z-30 flex shrink-0 items-center justify-around border-t border-hairline bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden"
    >
      {items.map((item) => {
        const active = isTabActive(item, pathname);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            aria-label={item.count ? `${item.label}, ${item.count} waiting` : undefined}
            className={[
              "mx-tab-inset-x my-tab-inset flex h-tab flex-1 flex-col items-center justify-center gap-[3px] rounded-tab transition-colors duration-(--duration-fast)",
              navTone(active, "text-ink-a40"),
            ].join(" ")}
          >
            <span className="relative">
              <Icon name={item.icon} filled={active} size={20} />
              {item.count ? (
                <span
                  aria-hidden="true"
                  className="absolute -right-2 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-highlight px-0.5 text-badge font-semibold text-text"
                >
                  {item.count > 9 ? "9+" : item.count}
                </span>
              ) : null}
            </span>
            <span className="text-tab font-medium">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
