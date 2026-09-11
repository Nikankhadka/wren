"use client";

import { useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { apiFetch } from "@/lib/api";

/**
 * The four platform tiles, ported from `.bk-platforms` in
 * agencx-prototype-v6.html - where they are decoration. Here each one is a link
 * slot: empty it is dashed and reads "Add", filled it is solid and reads "Open".
 *
 * Tapping a tile always opens the panel beneath it - it never navigates on the
 * tap itself. An empty slot's panel takes the address; a filled one's offers
 * Open, and lets the address be changed or removed. Navigating straight from
 * the tap read better until you noticed it left no way back to a link you had
 * already saved: the field to change it was behind the tap that had just taken
 * you off the page.
 *
 * They are the owner's own addresses, not integrations. Nothing here connects
 * to Google or Meta, and nothing pretends to - a tile that looked like a
 * connection and did nothing would be exactly the dead surface the PRD forbids.
 */

const PLATFORMS = [
  { key: "website", glyph: "🌐", label: "Website" },
  { key: "google", glyph: "📍", label: "Google Business" },
  { key: "facebook", glyph: "📘", label: "Facebook" },
  { key: "instagram", glyph: "📸", label: "Instagram" },
] as const;

type PlatformKey = (typeof PLATFORMS)[number]["key"];

export interface PlatformLinksProps {
  links: Record<string, string>;
  onSaved: (links: Record<string, string>) => void;
}

export function PlatformLinks({ links, onSaved }: PlatformLinksProps) {
  const [editing, setEditing] = useState<PlatformKey | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(key: PlatformKey) {
    setEditing(editing === key ? null : key);
    setDraft(links[key] ?? "");
    setError(null);
  }

  async function save(key: PlatformKey, value: string) {
    setBusy(true);
    setError(null);
    try {
      // A pasted address rarely carries its scheme; adding it beats refusing
      // what the owner obviously meant.
      const trimmed = value.trim();
      const url =
        !trimmed || /^https?:\/\//i.test(trimmed)
          ? trimmed
          : `https://${trimmed}`;
      const saved = await apiFetch<Record<string, string>>(
        "/api/business/links",
        {
          method: "PATCH",
          body: JSON.stringify({ links: { [key]: url } }),
        },
      );
      onSaved(saved);
      setEditing(null);
    } catch {
      setError("That does not look like a web address.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        {PLATFORMS.map((platform) => {
          const saved = links[platform.key];
          const isEditing = editing === platform.key;
          return (
            <button
              key={platform.key}
              type="button"
              onClick={() => toggle(platform.key)}
              data-testid={`booking-platform-${platform.key}`}
              aria-expanded={isEditing}
              aria-label={
                saved
                  ? `${platform.label}: open or change the link`
                  : `Add your ${platform.label} link`
              }
              className={[
                // min-w-0 so a long label ("Google Business") wraps instead of
                // forcing the tile wider than its quarter and pushing the row
                // off the card - which it did at 390px.
                "flex min-w-0 flex-1 flex-col items-center gap-1.5 rounded-field px-1 py-2.5",
                "transition-colors duration-(--duration-fast) active:bg-accent-a07",
                saved || isEditing
                  ? "bg-surface"
                  : "border border-dashed border-accent-a20 bg-transparent",
              ].join(" ")}
            >
              <span aria-hidden="true" className="text-body-lg leading-none">
                {platform.glyph}
              </span>
              <span className="w-full text-center text-eyebrow text-ink-a40">
                {platform.label}
              </span>
              <span className="text-center text-eyebrow text-accent-active">
                {saved ? "Open" : "Add"}
              </span>
            </button>
          );
        })}
      </div>

      {editing ? (
        <div className="flex flex-col gap-2">
          {links[editing] ? (
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-body-sm text-text">
                {links[editing]}
              </span>
              <a
                href={links[editing]}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="booking-link-open"
                className="shrink-0 rounded-chip bg-brand px-3.5 py-2 text-chip font-medium text-text-inverse hover:brightness-95 active:brightness-90"
              >
                Open
              </a>
              <button
                type="button"
                disabled={busy}
                onClick={() => void save(editing, "")}
                aria-label="Remove this link"
                data-testid="booking-link-remove"
                className="shrink-0 rounded-chip border-[1.5px] border-border p-2 text-text-secondary active:bg-surface-sunken"
              >
                <Icon name="delete" size={16} />
              </button>
            </div>
          ) : null}

          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              void save(editing, draft);
            }}
          >
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={`Paste your ${PLATFORMS.find((p) => p.key === editing)?.label} link`}
              disabled={busy}
              autoFocus
              inputMode="url"
              aria-label="Link address"
              data-testid="booking-link-input"
              className="min-w-0 flex-1 rounded-field border border-border bg-surface px-3.5 py-2.5 text-body-sm text-text placeholder:text-ink-a40 outline-none focus-visible:border-text"
            />
            <button
              type="submit"
              disabled={busy || !draft.trim()}
              data-testid="booking-link-save"
              className="shrink-0 rounded-chip bg-brand px-3.5 py-2 text-chip font-medium text-text-inverse hover:brightness-95 active:brightness-90 disabled:opacity-50"
            >
              Save
            </button>
          </form>
          {error ? (
            <p role="alert" className="text-meta text-danger">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
