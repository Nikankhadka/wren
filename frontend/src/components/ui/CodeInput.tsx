"use client";

import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";

export interface CodeInputProps {
  value: string;
  onChange: (value: string) => void;
  onComplete: (code: string) => void;
  disabled?: boolean;
  /**
   * Bump (to any new value) whenever the parent wants Digit 1 refocused even
   * if the cells are already empty - e.g. a resend clicked before anything
   * was typed. `value` alone can't signal that: an effect only reruns when a
   * dependency actually changes, and `value` would stay `""` throughout.
   */
  resetSignal?: number | null;
}

const LENGTH = 6;

const empty = (): string[] => Array.from({ length: LENGTH }, () => "");

/**
 * The six-digit login-code input (S1 login-in-chat), ported from the
 * prototype's `.otp-cell` rules and `initOtp()`. Six 46x52 cells, first
 * auto-focused, numeric keyboard on mobile, auto-submit when six digits are
 * filled. Backspace moves back; paste spreads a six-digit string across the
 * cells. The empty focused cell shows the prototype's blinking caret; a filled
 * cell firms its border. The prototype's 500ms `verif` tint is deliberately not
 * ported - O-2's spec is that success silently continues.
 *
 * The cells are the source of truth, held as a fixed-length array mirrored in a
 * ref. Deriving the next code from the `value` prop instead would break under
 * fast input - a password manager, or any autofill that writes several cells
 * within one React batch - because each cell's handler would still read the
 * pre-update prop, and because `value.split("")` collapses the gaps in a
 * partly-filled code and so misaligns every later digit.
 */
export function CodeInput({ value, onChange, onComplete, disabled, resetSignal }: CodeInputProps) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const [digits, setDigits] = useState<string[]>(empty);
  const digitsRef = useRef<string[]>(digits);
  const prevResetSignal = useRef(resetSignal);

  // The parent clears `value` to reset the cells (e.g. after a wrong code or
  // a resend) - also return focus to Digit 1 so typing can start immediately.
  // Only an external reset should steal focus: `value` also passes through
  // "" when the user backspaces the last digit they typed themselves, and by
  // that point `digitsRef` (updated synchronously in `commit`, ahead of the
  // `value` prop echoing back) already agrees with it - `some(Boolean)`
  // is false, same as it would be for a no-op re-render. An external reset
  // either leaves stale digits behind (`some(Boolean)` true) or, when the
  // cells were already empty, still bumps `resetSignal` - that's the signal
  // this effect can't get from `value` alone in that second case. The
  // comparison runs inside the effect, not the render body, so it isn't
  // thrown off by React Strict Mode's extra render pass.
  useEffect(() => {
    const signalChanged = prevResetSignal.current !== resetSignal;
    prevResetSignal.current = resetSignal;
    if (value !== "") return;
    const hadStaleDigits = digitsRef.current.some(Boolean);
    if (hadStaleDigits) {
      digitsRef.current = empty();
      setDigits(digitsRef.current);
    }
    if (!hadStaleDigits && !signalChanged) return;
    refs.current[0]?.focus();
  }, [value, resetSignal]);

  function commit(next: string[]) {
    digitsRef.current = next;
    setDigits(next);
    const joined = next.join("");
    onChange(joined);
    if (next.every((digit) => /^\d$/.test(digit))) {
      onComplete(joined);
    }
  }

  function setDigit(index: number, digit: string) {
    const next = [...digitsRef.current];
    next[index] = digit;
    commit(next);
    if (digit && index < LENGTH - 1) {
      refs.current[index + 1]?.focus();
    }
  }

  function handleKeyDown(index: number, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Backspace" && !digitsRef.current[index] && index > 0) {
      refs.current[index - 1]?.focus();
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const text = event.clipboardData.getData("text").replace(/\D/g, "").slice(0, LENGTH);
    if (text.length === LENGTH) {
      event.preventDefault();
      commit(text.split(""));
    }
  }

  return (
    <div className="flex justify-center gap-2" aria-label="6-digit code">
      {Array.from({ length: LENGTH }, (_, index) => {
        const filled = Boolean(digits[index]);
        return (
          <div key={index} className="relative">
            <input
              ref={(el) => {
                refs.current[index] = el;
              }}
              value={digits[index] ?? ""}
              onChange={(event) => {
                const digit = event.target.value.replace(/\D/g, "").slice(-1);
                setDigit(index, digit);
              }}
              onKeyDown={(event) => handleKeyDown(index, event)}
              onPaste={handlePaste}
              inputMode="numeric"
              autoComplete="one-time-code"
              aria-label={`Digit ${index + 1}`}
              disabled={disabled}
              autoFocus={index === 0}
              className={[
                "peer h-code-cell-h w-code-cell-w rounded-md text-center text-title-2 font-medium text-text",
                "border-[length:var(--border-chip)] outline-none",
                "transition-colors duration-(--duration-fast) ease-out disabled:opacity-50",
                "focus:border-accent focus:bg-surface",
                filled ? "border-accent-a45 bg-surface" : "border-accent-a16 bg-surface-sunken",
              ].join(" ")}
            />
            {/* The prototype's .otp-cursor: shown only while the cell is both
                focused and empty, so the caret marks where typing will land. */}
            {filled ? null : (
              <span
                aria-hidden="true"
                className="animate-caret-blink pointer-events-none absolute left-1/2 top-1/2 hidden h-[26px] w-[1.5px] -translate-x-1/2 -translate-y-1/2 rounded-[1px] bg-accent peer-focus:block"
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
