"use client";

import { useState } from "react";

export interface Citation {
  index: number;
  source: string;
  snippet: string;
}

export interface CitationChipProps {
  citation: Citation;
}

/**
 * docs/design/frontend.md section 6: inline [n]-style chip after cited
 * sentences; popover shows the chunk source + snippet on hover/focus.
 */
export function CitationChip({ citation }: CitationChipProps) {
  const [open, setOpen] = useState(false);

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-subtle px-1 text-[10px] font-medium text-accent-active"
      >
        {citation.index}
      </button>
      {open ? (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 z-10 mb-1 w-48 -translate-x-1/2 rounded-md border border-border bg-surface p-2 text-left text-footnote shadow-2"
        >
          <span className="block font-medium text-text">{citation.source}</span>
          <span className="block text-text-secondary">{citation.snippet}</span>
        </span>
      ) : null}
    </span>
  );
}
