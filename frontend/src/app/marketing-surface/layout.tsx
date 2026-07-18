import type { Metadata } from "next";
import type { ReactNode } from "react";
import { headers } from "next/headers";
import { surfaceUrl } from "@/lib/tenant";

/**
 * Marketing surface shell (bare apex / www host, rewritten here by proxy.ts).
 * Its own layout on purpose: full-width bands and the serif display voice,
 * distinct from the chat and console shells - all values still tokens.
 * Every cross-surface link is derived from the request host via surfaceUrl,
 * so dev (app.localhost:3000) and prod (app.wren.app) both work unhardcoded.
 */

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
        <div className="mx-auto flex w-full max-w-[1080px] items-center justify-between px-4 py-4 sm:px-8">
          <p className="font-display text-title-3 font-semibold text-text">
            Wren<span aria-hidden="true" className="text-accent">.</span>
          </p>
          <nav aria-label="Sign in" className="flex items-center gap-2">
            <a
              href={businessLogin}
              className="rounded-md px-3 py-1.5 text-body-sm font-medium text-text transition-colors duration-fast hover:bg-surface-sunken"
            >
              Business sign in
            </a>
            <a
              href={businessSignup}
              className="rounded-md border border-transparent bg-accent px-3 py-1.5 text-body-sm font-medium text-text-inverse transition-colors duration-fast hover:bg-accent-hover active:bg-accent-active"
            >
              Get started
            </a>
          </nav>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-border">
        <div className="mx-auto flex w-full max-w-[1080px] flex-col items-start justify-between gap-3 px-4 py-6 sm:flex-row sm:items-center sm:px-8">
          <p className="font-display text-body font-semibold text-text">
            Wren<span aria-hidden="true" className="text-accent">.</span>
          </p>
          <p className="text-footnote text-text-tertiary">
            Every business gets its own private agent at its own address.
          </p>
          <a
            href={platformLogin}
            className="text-footnote text-text-tertiary underline-offset-2 transition-colors duration-fast hover:text-text-secondary hover:underline"
          >
            Platform operator sign-in
          </a>
        </div>
      </footer>
    </div>
  );
}
