"use client";

import { useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { relativeTime } from "@/lib/format";
import type { WaitingRow } from "../lib/brief";

/**
 * The escalation queue on the owner's home screen: a count on top, then one
 * row per waiting customer - name, how long ago they were raised, and the
 * assistant's own summary of why - ordered oldest first, since that is the
 * prioritisation the panel promises.
 *
 * Row surface = `.a-card` (agencx-prototype-v6.html line 53), already ported
 * as BriefCard's `rounded-card border-hairline bg-surface shadow-card
 * animate-rise`. There is no per-customer row or count-badge precedent in the
 * prototype - the row idiom below is the chats screen's `.chat-row`
 * (name / time / preview). The count pill is a solid `--color-highlight`
 * fill (the prototype's actual amber, `--amber-400`) with dark text, not
 * `Badge`'s warning tone (`--amber-500`, now the dark ochre warning text on
 * a pale wash) - that pair is for text-on-wash, not a solid fill,
 * where dark text on the solid `--amber-400` fill clears 8.6:1. It is also
 * the same token the Chats-list per-row attention dot already uses for
 * "wants the owner", so the notification count and the notification dot
 * finally agree.
 *
 * Tapping a row goes straight to that conversation (`/chats/:id`), not the
 * bare `/chats` list - the point of naming each customer is skipping the
 * "which one do they mean" step.
 */

function pluralHeadline(n: number): string {
  return n === 1 ? "1 customer is waiting for you" : `${n} customers are waiting for you`;
}

export function WaitingPanel({ rows }: { rows: WaitingRow[] }) {
  const [expanded, setExpanded] = useState(false);

  if (rows.length === 0) return null;

  const hasMore = rows.length > 3;
  const fitsAtLarge = rows.length <= 5;

  return (
    <article
      data-testid="waiting-panel"
      className="mt-4 animate-rise overflow-hidden rounded-card border border-hairline bg-surface shadow-card"
    >
      <div className="flex items-center gap-2 px-[18px] pb-3 pt-4">
        <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-highlight px-1 text-badge font-semibold text-text">
          {rows.length}
        </span>
        <p className="text-card-hl font-medium text-text">{pluralHeadline(rows.length)}</p>
      </div>

      <div
        data-testid="waiting-panel-rows"
        className={
          expanded
            ? "max-h-[288px] overflow-y-auto lg:max-h-[432px]"
            : "max-h-[216px] overflow-y-auto lg:max-h-[360px]"
        }
      >
        {rows.map((row) => (
          <Link
            key={row.id}
            href={`/chats/${row.id}`}
            data-testid="waiting-row"
            className="flex items-center gap-2 border-t border-hairline px-[18px] py-3 transition-colors duration-(--duration-fast) hover:bg-surface-container active:bg-surface-sunken"
          >
            <span className="min-w-0 flex-1">
              <span className="flex items-center justify-between gap-2">
                <span className="truncate text-body font-medium text-text">{row.name}</span>
                <span className="shrink-0 text-footnote text-text-secondary">
                  {relativeTime(row.since)}
                </span>
              </span>
              <span className="mt-0.5 block line-clamp-2 text-meta text-ink-a40">
                {row.summary}
              </span>
            </span>
            <span aria-hidden="true" className="shrink-0 text-ink-a18">
              <Icon name="chevron_right" size={20} />
            </span>
          </Link>
        ))}
      </div>

      {hasMore ? (
        <button
          type="button"
          data-testid="waiting-panel-toggle"
          onClick={() => setExpanded((value) => !value)}
            className={`block w-full border-t border-hairline px-[18px] py-2.5 text-center text-chip text-accent-active transition-colors duration-(--duration-fast) hover:underline active:opacity-60${fitsAtLarge ? " lg:hidden" : ""}`}
        >
          {expanded ? "Show fewer" : `Show all ${rows.length}`}
        </button>
      ) : null}
    </article>
  );
}
