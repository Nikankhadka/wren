import type { Metadata } from "next";
import type { ReactNode } from "react";
import { headers } from "next/headers";
import Link from "next/link";
import { surfaceUrl } from "@/lib/tenant";
import { Icon } from "@/components/ui/Icon";

/**
 * Marketing surface shell (bare apex / www host, rewritten here by proxy.ts).
 * Its own layout on purpose: full-width bands and a distinct marketing voice,
 * separate from the chat and console shells - all values still tokens.
 * Every cross-surface link is derived from the request host via surfaceUrl,
 * so dev (app.localhost:3000) and prod (app.wren.app) both work unhardcoded.
 * The in-surface nav pages (Product/Pricing/Demo/About) are relative Links;
 * they are built in a following chunk and 404 until then, by design.
 */

/** Marketing pages within this surface - relative Links, resolved by proxy.ts. */
const PAGES = [
  { href: "/product", label: "Product" },
  { href: "/pricing", label: "Pricing" },
  { href: "/demo", label: "Demo" },
  { href: "/about", label: "About" },
] as const;

export const metadata: Metadata = {
  title: "Wren - a private AI agent for your business",
  description:
    "Onboard through a conversation and get a branded AI support-and-sales agent at your own address. It answers from your documents with citations, quotes prices a deterministic engine computed, and hands off to a human when it should.",
  openGraph: {
    title: "Wren - a private AI agent for your business",
    description:
      "A branded AI support-and-sales agent at your own address, answering only from your own knowledge.",
    siteName: "Wren",
    type: "website",
  },
};

export default async function MarketingLayout({ children }: { children: ReactNode }) {
  const host = (await headers()).get("host") ?? "";
  const businessLogin = surfaceUrl({ surface: "tenant-admin" }, host, "/login");
  const businessSignup = surfaceUrl({ surface: "tenant-admin" }, host, "/signup");
  const platformLogin = surfaceUrl({ surface: "platform" }, host, "/login");

  return (
    <div className="flex min-h-dvh flex-1 flex-col">
      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-[1080px] items-center justify-between gap-4 px-4 py-4 sm:px-8">
          <div className="flex items-center gap-6">
            <p className="font-display text-title-3 font-semibold text-text">
              Wren<span aria-hidden="true" className="text-accent">.</span>
            </p>
            <nav aria-label="Product" className="hidden items-center gap-1 md:flex">
              {PAGES.map((p) => (
                <Link
                  key={p.href}
                  href={p.href}
                  className="rounded-md px-3 py-1.5 text-body-sm font-medium text-text-secondary transition-colors duration-fast hover:bg-surface-sunken hover:text-text"
                >
                  {p.label}
                </Link>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-2">
            <a
              href={businessLogin}
              className="hidden rounded-md px-3 py-1.5 text-body-sm font-medium text-text transition-colors duration-fast hover:bg-surface-sunken sm:inline-flex"
            >
              Business sign in
            </a>
            <a
              href={businessSignup}
              className="rounded-full border border-transparent bg-accent px-4 py-1.5 text-body-sm font-medium text-text-inverse transition-colors duration-fast hover:bg-accent-hover active:bg-accent-active"
            >
              Get started
            </a>

            {/* Mobile disclosure - zero client JS via native <details>. */}
            <details className="relative md:hidden">
              <summary
                aria-label="Open menu"
                className="flex h-9 w-9 cursor-pointer list-none items-center justify-center rounded-md text-text transition-colors duration-fast hover:bg-surface-sunken [&::-webkit-details-marker]:hidden"
              >
                <Icon name="menu" size={22} />
              </summary>
              <nav
                aria-label="Product"
                className="absolute right-0 z-10 mt-2 flex w-48 flex-col gap-1 rounded-lg border border-border bg-surface p-2 shadow-2"
              >
                {PAGES.map((p) => (
                  <Link
                    key={p.href}
                    href={p.href}
                    className="rounded-md px-3 py-2 text-body-sm font-medium text-text transition-colors duration-fast hover:bg-surface-sunken"
                  >
                    {p.label}
                  </Link>
                ))}
                <a
                  href={businessLogin}
                  className="rounded-md px-3 py-2 text-body-sm font-medium text-text transition-colors duration-fast hover:bg-surface-sunken"
                >
                  Business sign in
                </a>
              </nav>
            </details>
          </div>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-border">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col gap-6 px-4 py-8 sm:px-8">
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
            <p className="font-display text-body font-semibold text-text">
              Wren<span aria-hidden="true" className="text-accent">.</span>
            </p>
            <nav
              aria-label="Product"
              className="flex flex-wrap items-center gap-x-5 gap-y-2"
            >
              {PAGES.map((p) => (
                <Link
                  key={p.href}
                  href={p.href}
                  className="text-footnote text-text-secondary underline-offset-2 transition-colors duration-fast hover:text-text hover:underline"
                >
                  {p.label}
                </Link>
              ))}
              <a
                href={platformLogin}
                className="text-footnote text-text-secondary underline-offset-2 transition-colors duration-fast hover:text-text hover:underline"
              >
                Platform operator sign-in
              </a>
            </nav>
          </div>
          <p className="text-footnote text-text-tertiary">
            Every business gets its own private agent at its own address.
          </p>
        </div>
      </footer>
    </div>
  );
}
