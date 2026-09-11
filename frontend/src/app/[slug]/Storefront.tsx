"use client";
/* eslint-disable @next/next/no-img-element -- storefront cover is a tenant API response. */

import { useRef, useState } from "react";
import { BrandMark } from "@/components/ui/BrandMark";
import { Icon } from "@/components/ui/Icon";
import { Sheet } from "@/components/ui/Sheet";
import type { StorefrontData } from "@/lib/tenant";
import { CustomerChat } from "./CustomerChat";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function linkLabel(key: string) {
  return key === "website" ? "Website" : key.slice(0, 1).toUpperCase() + key.slice(1);
}

/**
 * The owner's price, rendered. Integer cents in, one string out - this is
 * formatting, not arithmetic: nothing here rounds, marks up, or derives an
 * amount, and an offering with no published price simply shows none.
 */
function priceLabel(cents: number) {
  return `$${(cents / 100).toFixed(2)}`;
}

function videoEmbedUrl(provider: string, rawUrl: string): string | null {
  try {
    const parsed = new URL(rawUrl);
    const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
    if (provider === "youtube" && (host === "youtube.com" || host === "youtube-nocookie.com" || host === "youtu.be")) {
      const id = host === "youtu.be"
        ? parsed.pathname.split("/").filter(Boolean)[0]
        : parsed.searchParams.get("v") || parsed.pathname.match(/^\/(?:embed|shorts)\/([^/]+)/)?.[1];
      return id ? `https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?rel=0` : null;
    }
    if (provider === "vimeo" && (host === "vimeo.com" || host === "player.vimeo.com")) {
      const id = parsed.pathname.match(/\/(?:video\/)?(\d+)(?:\/|$)/)?.[1];
      return id ? `https://player.vimeo.com/video/${id}?title=0` : null;
    }
  } catch {
    return null;
  }
  return null;
}

function VideoMedia({ media }: { media: NonNullable<StorefrontData["offerings"][number]["media"]> }) {
  if (media.provider === "cloudinary") {
    return (
      <video
        controls
        preload="metadata"
        poster={media.poster_url ?? undefined}
        className="max-h-72 w-full rounded-card bg-surface-container object-contain"
      >
        <source src={media.url} />
        Your browser does not support this video.
      </video>
    );
  }
  const embed = videoEmbedUrl(media.provider, media.url);
  if (embed) {
    return (
      <iframe
        src={embed}
        title="Offering video"
        loading="lazy"
        allow="fullscreen; picture-in-picture"
        className="aspect-video w-full rounded-card border-0 bg-surface-container"
      />
    );
  }
  return (
    <a href={media.url} target="_blank" rel="noreferrer" className="block rounded-card bg-surface-container p-6 text-center text-action text-accent-active">
      Open video
    </a>
  );
}

export function Storefront({
  slug,
  logoUrl,
  greeting,
  starterQuestions,
  storefront,
}: {
  slug: string;
  logoUrl?: string;
  greeting: string | null;
  starterQuestions: string[];
  storefront: StorefrontData;
}) {
  const [chatOpen, setChatOpen] = useState(false);
  const [selected, setSelected] = useState<StorefrontData["offerings"][number] | null>(null);
  const composerRef = useRef<((text: string) => void) | null>(null);
  const [shared, setShared] = useState(false);
  async function share() {
    const url = typeof window === "undefined" ? `/${slug}` : window.location.href;
    try {
      if (typeof navigator.share === "function") {
        await navigator.share({ title: storefront.name, url });
      } else {
        await navigator.clipboard.writeText(url);
      }
      setShared(true);
      window.setTimeout(() => setShared(false), 2000);
    } catch {
      // A cancelled native share is not an error state.
    }
  }
  function openChat() {
    setChatOpen(true);
  }
  const categories = Array.from(new Set(storefront.offerings.map((item) => item.category).filter(Boolean))) as string[];
  const hasUncategorized = storefront.offerings.some((item) => !item.category);
  const groupedCategories = categories.length > 1 ? [...categories, ...(hasUncategorized ? ["More"] : [])] : ["More"];
  const sections = groupedCategories.map((category, index) => ({
    id: `offer-category-${index + 1}`,
    label: categories.length <= 1 ? "What we offer" : category,
    offerings: storefront.offerings.filter(
      (item) => categories.length <= 1 || (item.category || "More") === category,
    ),
  }));

  return (
    <main className="min-h-dvh w-full bg-surface pb-8">
      <header className="sticky top-0 z-10 h-16 border-b border-hairline bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-gutter">
          <div className="flex min-w-0 items-center gap-2.5">
            <BrandMark logoUrl={logoUrl} name={storefront.name} />
            <span className="truncate text-title-3 font-semibold text-text">{storefront.name}</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => void share()}
              aria-label={shared ? "Link copied" : "Share page"}
              title={shared ? "Link copied" : "Share page"}
              className="grid size-11 place-items-center rounded-full border border-border text-text transition-colors duration-(--duration-fast) hover:bg-surface-container active:bg-surface-container-high"
            >
              <Icon name={shared ? "check_circle" : "share"} size={20} />
            </button>
            <button
              type="button"
              onClick={openChat}
              aria-label={`Chat with ${storefront.name}`}
              title={`Chat with ${storefront.name}`}
              className="grid size-11 place-items-center rounded-full bg-accent text-text-inverse transition-colors duration-(--duration-fast) hover:bg-accent-hover active:bg-accent-active"
            >
              <Icon name="forum" size={20} />
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl md:px-gutter md:pt-6">
        {storefront.has_cover ? (
          <img
            src={storefront.cover_url || `${API_URL}/api/public/tenant/${encodeURIComponent(slug)}/cover`}
            alt=""
            fetchPriority="high"
            className="h-40 w-full object-cover md:h-80 md:rounded-lg"
          />
        ) : null}

        <section className="px-gutter py-7 text-center md:px-0 md:py-9 md:text-left">
          <h1 className="min-w-0 wrap-anywhere text-title-1 font-bold text-text">
            {storefront.name}
          </h1>
          {storefront.tagline ? (
            <p className="mx-auto mt-2 max-w-prose text-body text-text-secondary md:mx-0">
              {storefront.tagline}
            </p>
          ) : null}
          {Object.keys(storefront.links).length > 0 ? (
            <nav aria-label={`${storefront.name} links`} className="mt-4 flex flex-wrap justify-center gap-2 md:justify-start">
              {Object.entries(storefront.links).map(([key, href]) => (
                <a
                  key={key}
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-11 items-center gap-1.5 whitespace-nowrap rounded-chip border border-border px-3 text-chip font-medium text-text transition-colors duration-(--duration-fast) hover:bg-surface-container active:bg-surface-container-high"
                >
                  {linkLabel(key)}
                  <Icon name="open_in_new" size={13} />
                </a>
              ))}
            </nav>
          ) : null}
        </section>
      </div>

      {storefront.offerings.length > 0 ? (
        <div className="border-t border-hairline">
          {sections.length > 1 ? (
            <nav
              aria-label="Offer categories"
              className="sticky top-16 z-10 flex gap-2 overflow-x-auto border-b border-hairline bg-surface/95 px-gutter py-3 backdrop-blur lg:hidden"
            >
              {sections.map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className="min-h-11 shrink-0 whitespace-nowrap rounded-chip bg-surface-container px-4 py-3 text-chip font-medium text-text-secondary active:bg-surface-container-high"
                >
                  {section.label}
                </a>
              ))}
            </nav>
          ) : null}

          <div className="mx-auto max-w-7xl lg:grid lg:grid-cols-4 lg:gap-10 lg:px-gutter">
            {sections.length > 1 ? (
              <aside className="hidden lg:col-span-1 lg:block">
                <nav aria-label="Offer categories" className="sticky top-24 py-8">
                  <p className="mb-3 text-title-3 font-semibold text-text">Browse</p>
                  <ul className="space-y-1">
                    {sections.map((section) => (
                      <li key={section.id}>
                        <a
                          href={`#${section.id}`}
                          className="block min-h-11 rounded-field px-3 py-3 text-body-sm text-text-secondary transition-colors duration-(--duration-fast) hover:bg-surface-container hover:text-text active:bg-surface-container-high"
                        >
                          {section.label}
                        </a>
                      </li>
                    ))}
                  </ul>
                </nav>
              </aside>
            ) : null}

            <div className={sections.length > 1 ? "lg:col-span-3" : "lg:col-span-4"}>
              {sections.map((section) => (
                <section
                  key={section.id}
                  id={section.id}
                  className="scroll-mt-32 border-b border-hairline px-gutter py-7 last:border-b-0 lg:px-0 lg:py-8"
                >
                  <h2 className="text-title-2 font-semibold text-text">{section.label}</h2>
                  <div className="mt-3 grid min-w-0 sm:grid-cols-2 sm:gap-x-8">
                    {section.offerings.map((offering) => (
                      <button
                        key={offering.id}
                        type="button"
                        onClick={() => setSelected(offering)}
                        className="flex min-h-36 w-full items-start justify-between gap-4 border-b border-hairline py-5 text-left transition-colors duration-(--duration-fast) last:border-b-0 hover:bg-surface-container active:bg-surface-container-high sm:px-3"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block text-card-hl font-semibold text-text">{offering.name}</span>
                          {offering.price_cents !== null ? (
                            <span
                              data-testid="offering-price"
                              className="mt-1 block text-body-sm font-medium text-text tabular-nums"
                            >
                              {priceLabel(offering.price_cents)}
                            </span>
                          ) : null}
                          {offering.description ? (
                            <span className="mt-1.5 line-clamp-3 text-body-sm text-text-secondary">
                              {offering.description}
                            </span>
                          ) : null}
                        </span>
                        {offering.media?.type === "image" ? (
                          <img
                            src={offering.media.url}
                            alt=""
                            loading="lazy"
                            className="h-24 w-24 shrink-0 rounded-field object-cover"
                          />
                        ) : offering.media?.type === "video" ? (
                          offering.media.poster_url ? (
                            <span className="relative h-24 w-24 shrink-0">
                              <img
                                src={offering.media.poster_url}
                                alt=""
                                loading="lazy"
                                className="size-full rounded-field object-cover"
                              />
                              <span className="absolute bottom-1.5 left-1.5 rounded-chip bg-scrim px-2 py-1 text-meta text-text-inverse">
                                Video
                              </span>
                            </span>
                          ) : (
                            <span className="grid h-24 w-24 shrink-0 place-items-center rounded-field bg-surface-container text-meta text-text-secondary">
                              Video
                            </span>
                          )
                        ) : null}
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      <footer className="mx-auto flex max-w-7xl items-center justify-between border-t border-hairline px-gutter py-6 text-meta text-text-tertiary">
        <span className="font-medium text-text">Agencx</span>
        <span>Powered by Agencx</span>
      </footer>

      <Sheet open={chatOpen} onClose={() => setChatOpen(false)} title={`Chat with ${storefront.name}`}>
        <div className="flex h-[calc(85dvh-7rem)] min-h-0 flex-col">
          {/* Deliberately unkeyed: the sheet keeps its children mounted, so a
              customer who closes it and reopens it from another entry point is
              back in the thread they were in, talking to the same conversation
              rather than orphaning it mid-answer. */}
          <CustomerChat
            slug={slug}
            displayName={storefront.name}
            greeting={greeting}
            starterQuestions={starterQuestions}
            composerRef={composerRef}
          />
        </div>
      </Sheet>
      <Sheet open={selected !== null} onClose={() => setSelected(null)} title={selected?.name ?? "Offering details"}>
        {selected ? (
          <div className="space-y-4 p-5">
            {selected.media?.type === "image" ? (
              <img src={selected.media.url} alt="" className="max-h-72 w-full rounded-card object-cover" />
            ) : selected.media?.type === "video" ? (
              <VideoMedia media={selected.media} />
            ) : null}
            {selected.description ? <p className="text-prose text-text-secondary">{selected.description}</p> : null}
            {selected.price_cents !== null ? <p className="text-title-2 font-semibold text-text">{priceLabel(selected.price_cents)}</p> : null}
            <button type="button" onClick={() => { setChatOpen(true); composerRef.current?.(`Tell me about ${selected.name}`); setSelected(null); }} className="w-full rounded-field bg-brand px-4 py-3 text-action font-medium text-text-inverse hover:brightness-95 active:brightness-90">Ask about this</button>
          </div>
        ) : null}
      </Sheet>
    </main>
  );
}
