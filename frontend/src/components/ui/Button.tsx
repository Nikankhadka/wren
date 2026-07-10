"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "destructive";
type Size = "sm" | "md";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-accent text-text-inverse hover:bg-accent-hover active:bg-accent-active border border-transparent",
  secondary:
    "bg-surface text-text border border-border hover:bg-surface-sunken active:bg-surface-sunken",
  ghost:
    "bg-transparent text-text border border-transparent hover:bg-surface-sunken active:bg-surface-sunken",
  destructive:
    "bg-danger text-text-inverse hover:opacity-90 active:opacity-80 border border-transparent",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "text-body-sm px-3 py-1.5 gap-1.5",
  md: "text-body px-4 py-2 gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children: ReactNode;
}

/**
 * docs/design/frontend.md section 6: primary/secondary/ghost/destructive, sm/md.
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
        "transition-colors duration-fast select-none",
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
