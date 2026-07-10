"use client";

import { useId, type InputHTMLAttributes } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  help?: string;
  error?: string;
}

/**
 * docs/design/frontend.md section 6: label above, help/error text below;
 * default, focus, error (danger border + text), disabled states.
 */
export function Input({ label, help, error, id, className = "", ...rest }: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const messageId = `${inputId}-message`;
  const message = error ?? help;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-body-sm font-medium text-text">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={message ? messageId : undefined}
        className={[
          "w-full rounded-md border bg-surface px-3 py-2 text-body text-text",
          "placeholder:text-text-tertiary transition-colors duration-fast",
          "disabled:opacity-50 disabled:bg-surface-sunken",
          error ? "border-danger" : "border-border hover:border-border-strong",
          className,
        ].join(" ")}
        {...rest}
      />
      {message ? (
        <p
          id={messageId}
          className={`text-footnote ${error ? "text-danger" : "text-text-secondary"}`}
        >
          {message}
        </p>
      ) : null}
    </div>
  );
}
