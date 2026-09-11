"use client";

import { useLayoutEffect, useRef, type KeyboardEvent } from "react";
import { Icon } from "./Icon";

export interface CommandPillProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  /**
   * W-3: onboarding beats now leave `placeholder` blank by default (the
   * in-thread question carries the context), which would otherwise strip the
   * textarea's only accessible name. This is that name's static replacement -
   * FieldPill's callers pass their own `aria-label`; this one is the same idea
   * with a sensible default, since most CommandPill callers have nothing more
   * specific to say than "the answer goes here".
   */
  ariaLabel?: string;
  disabled?: boolean;
  /** Streaming a reply - swap the send circle for a Stop square. */
  busy?: boolean;
  onStop?: () => void;
  /** Attach affordance (file/URL upload beat); hidden when omitted. */
  onAttach?: () => void;
  /** False dims the send circle instead of arming it (e.g. email not yet valid). */
  canSubmit?: boolean;
  /**
   * `command` (default) is the prototype's `.cmd-pill`: the send circle appears
   * only once there is text. `field` is its `.plain-pill`: the circle is always
   * present and dims until the value is valid, which is how a single-value beat
   * (name, email) signals validity without error text.
   */
  variant?: "command" | "field";
}

const MAX_HEIGHT_PX = 96;

/**
 * The composer, ported from `buildCmdPill()` / `.plain-pill` in the ONBOARDING
 * section of agencx-prototype-v6.html. A textarea that auto-grows to 96px
 * (Enter submits, Shift+Enter newlines), a "+" affordance on the left, and a
 * 34px send circle on the right. Spread-ring shadow via --shadow-pill, not a
 * border - a ring plus a border would shift the geometry.
 *
 * Deliberate deviation: the prototype shows camera and mic glyphs in the empty
 * state. Stage 1 has neither voice input nor photo capture, and a control that
 * does nothing is a worse defect than an absent one, so the empty state stays
 * empty. The "+" attach affordance is real and O-3 wires it up.
 */
export function CommandPill({
  value,
  onChange,
  onSubmit,
  placeholder,
  ariaLabel = "Your answer",
  disabled,
  busy,
  onStop,
  onAttach,
  canSubmit = true,
  variant = "command",
}: CommandPillProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow, capped at MAX_HEIGHT_PX. Reset to auto first so shrinking the
  // text also shrinks the box (scrollHeight is otherwise sticky at the max).
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (value.trim() && canSubmit && !busy && !disabled) onSubmit(value);
    }
  }

  const hasText = value.trim().length > 0;
  const armed = hasText && canSubmit;
  const field = variant === "field";
  const showSend = field || hasText;

  return (
    <div
      className={[
        "command-pill flex items-end gap-2 rounded-pill bg-surface shadow-pill",
        // .plain-pill sits taller than .cmd-pill and has no left affordance.
        field ? "py-3.5 pl-5 pr-[9px]" : "py-[11px] pl-[18px] pr-[10px]",
      ].join(" ")}
    >
      {/* `.pill-plus`: a 22px hit box around an 18px glyph. Hidden (not just
          disabled) when nothing is wired to it - only the document-upload
          beat passes onAttach, and a dimmed plus on every other step reads as
          an affordance that just doesn't work yet. */}
      {field || !onAttach ? null : (
        <button
          type="button"
          onClick={onAttach}
          aria-label="Attach"
          className="mb-0.5 flex h-[22px] w-[22px] shrink-0 items-center justify-center text-ink-a40"
        >
          <Icon name="add" size={18} />
        </button>
      )}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        aria-label={ariaLabel}
        disabled={disabled}
        rows={1}
        className="max-h-24 min-h-6 flex-1 resize-none bg-transparent text-prose text-text placeholder:text-ink-a40 outline-none disabled:opacity-50"
      />
      {busy ? (
        <button
          type="button"
          onClick={onStop}
          aria-label="Stop"
          className="flex size-send shrink-0 items-center justify-center rounded-full bg-accent text-text-inverse active:opacity-85"
        >
          <span className="h-2.5 w-2.5 rounded-[2px] bg-current" aria-hidden="true" />
        </button>
      ) : showSend ? (
        <button
          type="button"
          onClick={() => onSubmit(value)}
          disabled={disabled || !armed}
          aria-label="Send"
          className={[
            "flex size-send shrink-0 items-center justify-center rounded-full",
            "transition-colors duration-(--duration-fast) ease-out active:opacity-85",
            armed ? "bg-accent text-text-inverse" : "bg-accent-a12 text-accent-a50",
          ].join(" ")}
        >
          <Icon name="arrow_forward" size={20} />
        </button>
      ) : null}
    </div>
  );
}
