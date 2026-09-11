"use client";

import type { ButtonHTMLAttributes } from "react";

export interface ChipProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> {
  label: string;
  value?: string;
  /** Dashed suggestion chip (multi-select hints). */
  dashed?: boolean;
  /** Read-only "sent" chip - records a committed selection, no interaction. */
  sent?: boolean;
  /** Toggle state for multi-select chips (e.g. inbound channels). */
  selected?: boolean;
  onClick?: () => void;
}

const BASE = [
  "inline-flex min-h-11 items-center justify-center gap-2",
  "rounded-chip border-[length:var(--border-chip)] border-accent-a28",
  "text-chip font-medium transition-colors duration-(--duration-fast) select-none",
  "active:bg-accent-a07",
].join(" ");

const VARIANT_CLASSES = {
  solid: "text-accent-active px-[14px] hover:bg-accent-a07",
  dashed: "border-dashed text-accent-active px-4 hover:bg-accent-a07",
  sent: "pointer-events-none border-accent-a16 text-ink-a40 px-[14px]",
} as const;

/**
 * The enum-shaped beat widget, ported from the prototype's `.c-reply` /
 * `.c-suggest` / `.a-chip.sent`. Three variants - solid (selectable), dashed
 * (suggestion), sent (committed). 1.5px accent-a28 border via --border-chip,
 * radius --radius-chip, accent wash on hover/press. The label uses
 * `text-accent-active` (the deep Rausch stop) because flat `--color-accent`
 * cannot carry text on white (3.52:1).
 *
 * The one deliberate deviation from the prototype: a 44px minimum touch target
 * (the prototype's chips are ~29px, below the accessibility floor in
 * design/frontend.md section 10).
 */
export function Chip({
  label,
  dashed,
  sent,
  selected,
  disabled,
  className = "",
  onClick,
  ...rest
}: ChipProps) {
  const variant = sent ? "sent" : dashed ? "dashed" : "solid";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected ? true : undefined}
      className={[BASE, VARIANT_CLASSES[variant], selected ? "bg-accent-a07" : "", className].join(
        " ",
      )}
      {...rest}
    >
      {label}
    </button>
  );
}
