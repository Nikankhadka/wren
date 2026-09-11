import Link from "next/link";
import type { BriefItem } from "../lib/brief";

/**
 * The prototype's `.a-card`: headline, action chips, and a rule-marked context
 * note (`.a-hl` / `.a-chips` / `.a-chip` / `.ctx-note` in
 * agencx-prototype-v6.html). It rises in the way every other thread element
 * does - `fsu` there, `animate-rise` here, already ported.
 */
export function BriefCard({ item }: { item: BriefItem }) {
  return (
    <article
      data-testid={`brief-card-${item.kind}`}
      className="mt-4 animate-rise rounded-card border border-hairline bg-surface px-[18px] py-4 shadow-card"
    >
      <p className="mb-3 text-card-hl font-medium text-text">{item.headline}</p>
      <div className={`flex flex-wrap gap-2${item.note ? " mb-2.5" : ""}`}>
        {item.chips.map((chip) => (
          <Link
            key={chip.label}
            href={chip.href}
            className="whitespace-nowrap rounded-chip border-[1.5px] border-accent-a28 px-3.5 py-1.5 text-chip text-accent-active transition-colors duration-(--duration-fast) active:bg-accent-a07"
          >
            {chip.label}
          </Link>
        ))}
      </div>
      {item.note ? (
        <p className="border-l-2 border-accent pl-2.5 text-meta text-ink-a40">{item.note}</p>
      ) : null}
    </article>
  );
}
