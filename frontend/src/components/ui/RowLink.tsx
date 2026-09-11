"use client";

import Link from "next/link";
import type { IconName } from "./Icon";
import { Icon } from "./Icon";

export interface RowLinkProps {
  /** Where the row goes. Omitted, pass `onClick` - the row opens a sheet instead. */
  href?: string;
  label: string;
  icon: IconName;
  /** One quiet line under the label - what this row currently holds. */
  detail?: string;
  /** A row that opens something in place (the prototype's settings sheets). */
  onClick?: () => void;
}

/**
 * The prototype's `.bh-row`: icon, label, chevron, hairline underneath - the
 * whole row is the target. This is how every hub screen in
 * agencx-prototype-v6.html lists the places you can go, and it is deliberately
 * not a card: a list of rows scales to a phone without a grid.
 *
 * Some of those rows open a sheet rather than a screen - that is how the
 * prototype's Settings list edits a field. Such a row is a button, so it is
 * announced as one; everything else about it is identical.
 */
export function RowLink({ href, label, icon, detail, onClick }: RowLinkProps) {
  const className =
    "flex w-full items-center gap-3.5 border-b border-hairline px-gutter py-[15px] text-left transition-colors duration-(--duration-fast) hover:bg-surface-container active:bg-ink-a05";
  const inner = (
    <>
      <span className="flex size-5 shrink-0 items-center justify-center text-ink-a40">
        <Icon name={icon} size={20} />
      </span>
      <span className="flex-1">
        <span className="block text-row-label font-medium text-text">{label}</span>
        {detail ? <span className="mt-1.5 block text-meta text-ink-a40">{detail}</span> : null}
      </span>
      <span aria-hidden="true" className="text-ink-a18">
        <Icon name="chevron_right" size={20} />
      </span>
    </>
  );

  return href ? (
    <Link href={href} className={className}>
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={className}>
      {inner}
    </button>
  );
}
