"use client";
/* eslint-disable @next/next/no-img-element -- media URLs come from tenant API responses. */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ScreenTopbar } from "@/components/ui/ScreenTopbar";
import { Icon } from "@/components/ui/Icon";
import { apiFetch } from "@/lib/api";
import type { BookingPage } from "@/lib/api-schemas";
import { CoverPhoto } from "./components/CoverPhoto";
import { PlatformLinks } from "./components/PlatformLinks";

/**
 * E-5/E-6/M-4: the Business page - the business as a customer finds it, and the
 * link that takes them there. Built from `renderScreen('booking')` in
 * agencx-prototype-v6.html: the cover photo, the name and its one-line
 * description, "How leads come in" with the shareable link and the platform
 * tiles, plus the compact What we offer summary.
 *
 * Two parts of the prototype's screen do not ship, by founder decision: the
 * "Get a quote" CTA (quoting is a Stage 2 opt-in and this owner will not use
 * it) and the QR code E-5 added, which was never in the prototype's owner
 * screen and was not being used.
 *
 * The offerings list is not here either: M-4 gave it its own screen at
 * `/business/offerings`, and the owner sees it as a customer does through the
 * preview link below - which now opens the real storefront at `/{slug}`, so
 * this screen's "what customers see" headings are literally true.
 */

export default function BusinessPageScreen() {
  const [page, setPage] = useState<BookingPage | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    apiFetch<BookingPage>("/api/business/page")
      .then(setPage)
      .catch(() => setPage(null));
  }, []);

  useEffect(load, [load]);

  const slug = page?.slug;
  // The tenant's page is a path on this same origin (D22), so the base domain
  // and port carry over for free - localhost:3000 in dev, the real domain in
  // production, never hardcoded. This address goes into a text message or onto
  // a shop window, so it stays as short as the scheme allows.
  const publicUrl =
    slug && typeof window !== "undefined"
      ? `${window.location.origin}/${slug}`
      : null;
  // The pill shows the address without its scheme, the way the prototype does;
  // what gets copied is the whole URL, which is what a customer needs.
  const shown = publicUrl?.replace(/^https?:\/\//, "");

  async function copy() {
    if (!publicUrl) return;
    await navigator.clipboard.writeText(publicUrl);
    setCopied(true);
    // Resets, unlike the prototype's one-way `this.textContent='Copied ✓'` -
    // a control stuck in its confirmed state cannot confirm the next copy.
    window.setTimeout(() => setCopied(false), 2000);
  }

  async function share() {
    if (!publicUrl || !page) return;
    // Web Share where it exists (every phone this is designed for), clipboard
    // everywhere else. No custom sheet: the native one already lists the apps
    // the owner actually has, which a hardcoded four-icon row cannot.
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: page.name, url: publicUrl });
        return;
      } catch {
        // Cancelled, or refused by the browser - fall through to copying.
      }
    }
    await copy();
  }

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-surface">
      <ScreenTopbar title="Business page" backHref="/business" />
      <div className="min-h-0 flex-1 overflow-y-auto pb-thread-tail lg:mx-auto lg:w-full lg:max-w-thread">
        <CoverPhoto hasCover={page?.has_cover ?? false} onChanged={load} />

        <div className="px-gutter pt-[18px]">
          <h2 className="mb-1.5 text-display-sm font-bold tracking-[var(--text-display-sm-tracking)] text-text">
            {page?.name ?? "Your business"}
          </h2>
          {/* Clamped: the prototype's subtitle is one tight line because Sababa's
              services are, and a real business's list runs to five. Two lines
              is the gist; the full text lives in Business > Details > Knowledge. */}
          {page?.tagline ? (
            <p className="line-clamp-2 text-meta text-ink-a40">
              {page.tagline}
            </p>
          ) : null}
          {page?.offerings.length ? (
            <section
              data-testid="offerings-summary"
              className="mt-5 rounded-card bg-accent-a06 p-4"
            >
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-eyebrow font-medium uppercase text-ink-a40">
                  What we offer
                </h3>
                <Link
                  href="/business/offerings"
                  className="whitespace-nowrap text-chip font-medium text-accent-active transition-colors duration-(--duration-fast) hover:underline active:opacity-60"
                >
                  Manage
                </Link>
              </div>
              <div className="mt-3 divide-y divide-hairline">
                {page.offerings.map((offering) => (
                  <div
                    key={offering.name}
                    className="flex items-center gap-2.5 py-2.5 first:pt-0 last:pb-0"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-md bg-accent-a09 text-accent-active">
                      {offering.media?.type === "image" ? (
                        <img
                          src={offering.media.url}
                          alt=""
                          className="size-full object-cover"
                        />
                      ) : offering.media?.type === "video" &&
                        offering.media.poster_url ? (
                        <img
                          src={offering.media.poster_url}
                          alt=""
                          className="size-full object-cover"
                        />
                      ) : (
                        <Icon name="sell" size={18} />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-body-sm text-text">{offering.name}</span>
                      {offering.price_cents !== null || offering.category ? (
                        <span className="mt-0.5 block truncate text-meta text-ink-a40 tabular-nums">
                          {offering.price_cents !== null
                            ? `$${(offering.price_cents / 100).toFixed(2)}`
                            : null}
                          {offering.price_cents !== null && offering.category
                            ? " · "
                            : null}
                          {offering.category}
                        </span>
                      ) : null}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
          {publicUrl ? (
            <a
              href={publicUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-flex items-center gap-1.5 rounded-field border border-accent-a28 px-3 py-2 text-chip font-medium text-accent-active transition-colors duration-(--duration-fast) hover:bg-accent-a07 active:bg-accent-a09"
            >
              Preview your business page
              <Icon name="open_in_new" size={14} />
            </a>
          ) : null}
        </div>

        {/* `.bk-entry-wrap` - the tinted card holding the link and the tiles. */}
        <section
          data-testid="booking-links"
          className="mx-gutter mt-3.5 rounded-card bg-accent-a06 p-4"
        >
          <h3 className="mb-1 text-chip font-medium text-accent-active">
            How customers reach you
          </h3>
          <p className="mb-3.5 text-meta text-ink-a40">
            Share this link and anyone can ask you a question, any time.
          </p>

          {shown ? (
            <div className="mb-3 flex items-center gap-3 rounded-field bg-surface px-3.5 py-2.5">
              <span
                data-testid="booking-link"
                className="min-w-0 flex-1 truncate text-body-sm text-text"
              >
                {shown}
              </span>
              <button
                type="button"
                onClick={copy}
                data-testid="booking-copy"
                className="shrink-0 whitespace-nowrap text-chip font-medium text-accent-active transition-colors duration-(--duration-fast) hover:underline active:opacity-60"
              >
                {copied ? "Copied ✓" : "Copy link"}
              </button>
            </div>
          ) : (
            <div
              aria-busy="true"
              className="mb-3 h-11 rounded-field bg-surface"
            />
          )}

          <PlatformLinks
            links={page?.links ?? {}}
            onSaved={(links) =>
              setPage((prev) => (prev ? { ...prev, links } : prev))
            }
          />
        </section>

        <div className="px-gutter pt-5">
          <button
            type="button"
            onClick={share}
            data-testid="booking-share"
            className="flex w-full items-center justify-center gap-1.5 rounded-field border-[1.5px] border-accent-a28 py-3 text-chip font-medium text-accent-active transition-colors duration-(--duration-fast) hover:bg-accent-a07 active:bg-accent-a07"
          >
            <Icon name="share" size={14} />
            Share
          </button>
        </div>
      </div>
    </main>
  );
}
