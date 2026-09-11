"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "destructive";
type Size = "sm" | "md";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-brand text-text-inverse hover:brightness-95 active:brightness-90 border border-transparent",
  secondary:
    "bg-surface text-text border border-border hover:bg-surface-sunken active:bg-surface-sunken",
  ghost:
    "bg-transparent text-text border border-transparent hover:bg-surface-sunken active:bg-surface-sunken",
  destructive:
    "bg-danger text-text-inverse hover:opacity-90 active:opacity-80 border border-transparent",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "text-body-sm px-3 py-1.5 gap-1.5 min-h-[34px]",
  md: "text-body px-4 py-2 gap-2 min-h-11",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children: ReactNode;
}

/**
 * docs/agencx/design/frontend.md section 6: primary/secondary/ghost/destructive, sm/md.
 * The primary variant rides the Airbnb CTA gradient (`bg-brand`, a
 * background-image), so hover/active darken with a brightness filter, never a
 * background-color swap or opacity (opacity would lighten the gradient).
 * Loading replaces the label with a spinner while keeping the width stable
 * (label goes invisible instead of unmounting).
 */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={[
        "relative inline-flex items-center justify-center font-medium rounded-md",
        "transition-[background-color,filter,opacity] duration-(--duration-fast) select-none",
        "disabled:opacity-50 disabled:pointer-events-none",
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      ].join(" ")}
      {...rest}
    >
      <span className={loading ? "invisible" : undefined}>{children}</span>
      {loading ? (
        <span className="absolute inset-0 flex items-center justify-center" aria-hidden="true">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        </span>
      ) : null}
    </button>
  );
}
