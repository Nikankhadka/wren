"use client";

import { useId, type SelectHTMLAttributes } from "react";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  label: string;
  options: SelectOption[];
  help?: string;
  error?: string;
}

/**
 * docs/design/frontend.md section 6: label above, help/error text below -
 * mirrors Input's layout so forms mixing the two stay visually consistent.
 */
export function Select({ label, options, help, error, id, className = "", ...rest }: SelectProps) {
  const autoId = useId();
  const selectId = id ?? autoId;
  const messageId = `${selectId}-message`;
  const message = error ?? help;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={selectId} className="text-body-sm font-medium text-text">
        {label}
      </label>
      <select
        id={selectId}
        aria-invalid={error ? true : undefined}
        aria-describedby={message ? messageId : undefined}
        className={[
          "w-full rounded-md border bg-surface px-3 py-2 text-body text-text",
          "transition-colors duration-fast",
          "disabled:opacity-50 disabled:bg-surface-sunken",
          error ? "border-danger" : "border-border hover:border-border-strong",
          className,
        ].join(" ")}
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
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
