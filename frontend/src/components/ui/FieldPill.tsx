"use client";

import {
  useRef,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Icon } from "./Icon";

export interface FieldPillProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /**
   * Whether the current value may be sent. The send circle fills when true and
   * stays dimmed when false - this is how a single-value beat reports validity
   * without ever printing error text (O-2 US-1).
   */
  canSubmit: boolean;
  /**
   * Called instead of ``onSubmit`` when the send circle is pressed with an
   * invalid value. Given one, the circle stays pressable while dimmed - which
   * is how the prototype's phone beat reveals its error line, and it beats a
   * `disabled` button that answers a press with nothing at all. Omitted, the
   * circle is disabled and the dimming is the only signal (O-2 US-1).
   */
  onRejected?: () => void;
  /** The welded left-hand segment: the prototype's `.abn-pre`, or a country button. */
  leading?: ReactNode;
  /** Rendered under the pill. The phone beat's inline error line lives here. */
  below?: ReactNode;
  inputMode?: InputHTMLAttributes<HTMLInputElement>["inputMode"];
  type?: "text" | "tel" | "email";
  autoComplete?: string;
  maxLength?: number;
  "aria-label": string;
  "data-testid"?: string;
}

/**
 * A single-value pill with a segment welded inside its left edge, ported from
 * `.abn-pill` / `.ph-wrap` in agencx-prototype-v6.html. Both are the same
 * object: one rounded pill, a fixed segment, a hairline divider, the value, and
 * the 34px send circle that fills only once the value is valid.
 *
 * Distinct from CommandPill on purpose. That one is the conversation's composer
 * - a growing textarea for prose. This is a field: one line, one value, and a
 * real `<input>` so `type="tel"` and `autoComplete` reach the browser, which is
 * the whole point on the phone beat.
 */
export function FieldPill({
  value,
  onChange,
  onSubmit,
  placeholder,
  disabled,
  canSubmit,
  onRejected,
  leading,
  below,
  inputMode,
  type = "text",
  autoComplete,
  maxLength,
  "aria-label": ariaLabel,
  "data-testid": testId,
}: FieldPillProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  function submit() {
    if (disabled) return;
    if (canSubmit) onSubmit(value);
    else onRejected?.();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      {/* `command-pill` is the CSS hook that makes the pill light up as one
          rounded control on focus instead of drawing a hard rectangle around
          the input inside it (globals.css). It is the same object as the
          composer here, so it wants the same behaviour. */}
      <div className="command-pill flex items-center rounded-pill bg-surface shadow-pill">
        {leading ? (
          <div className="flex shrink-0 items-center border-r border-ink-a07">
            {leading}
          </div>
        ) : null}
        <input
          ref={inputRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          type={type}
          inputMode={inputMode}
          autoComplete={autoComplete}
          maxLength={maxLength}
          aria-label={ariaLabel}
          data-testid={testId}
          autoFocus
          className="min-w-0 flex-1 bg-transparent py-3.5 pl-2.5 pr-1 text-prose tracking-[0.02em] text-text placeholder:tracking-normal placeholder:text-ink-a40 outline-none disabled:opacity-50"
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || (!canSubmit && !onRejected)}
          aria-label="Send"
          className={[
            "m-[9px] flex size-send shrink-0 items-center justify-center rounded-full",
            "transition-colors duration-(--duration-fast) ease-out active:opacity-85",
            canSubmit
              ? "bg-accent text-text-inverse"
              : "bg-accent-a12 text-accent-a50",
          ].join(" ")}
        >
          <Icon name="send" size={20} />
        </button>
      </div>
      {below}
    </div>
  );
}
