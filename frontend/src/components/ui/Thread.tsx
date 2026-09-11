"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { ThinkingDots } from "./ThinkingDots";

/**
 * The onboarding conversation surface, ported from the ONBOARDING section of
 * docs/agencx/design/prototypes/agencx-prototype-v6.html (`#thread`,
 * `agentMsg()`, `userMsg()`, `.typing`, `.sys-pill`).
 *
 * This thread is deliberately NOT `ChatBubble`. The prototype gives onboarding
 * its own idiom - the assistant speaks as bare prose with no bubble at all, and
 * only the owner's answers get a filled bubble (20px radius, tip at the BOTTOM
 * right). `ChatBubble` correctly ports the *operator* thread's two-bubble idiom
 * (18px, tip at the top). They look similar and are not the same thing; do not
 * unify them.
 *
 * Every visual value here is a token from theme.css - the prototype's numbers,
 * not new decisions.
 */

/** The prototype's `scrollThread()`: two frames, then a 160ms catch-up. */
function scrollToBottom(el: HTMLElement) {
  const stick = () => {
    el.scrollTop = el.scrollHeight;
  };
  requestAnimationFrame(() => requestAnimationFrame(stick));
  // Streamed text reflows after paint - one late catch-up keeps the tail visible.
  return setTimeout(stick, 160);
}

export function Thread({
  children,
  label,
  watch,
  ...rest
}: {
  children: ReactNode;
  label: string;
  /** Changes to this value re-stick the scroll to the bottom. */
  watch?: unknown;
} & { "data-testid"?: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const timer = scrollToBottom(el);
    return () => clearTimeout(timer);
  }, [watch]);

  return (
    <div
      ref={ref}
      // role="log" already implies aria-live="polite" - do not add an explicit
      // one here, and do not nest another live region inside (a nested region
      // makes screen readers announce the same text twice, or neither).
      role="log"
      aria-label={label}
      className="flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden px-gutter pb-thread-tail pt-[calc(var(--space-thread-top)+env(safe-area-inset-top))]"
      {...rest}
    >
      <div className="mx-auto flex w-full max-w-thread flex-1 flex-col">{children}</div>
    </div>
  );
}

/**
 * The opening message (`#first-msg`): larger than ordinary prose, with the beat
 * question as a medium-weight block beneath it. Its top offset lives on the
 * `Thread` container, so a restored thread clears the top edge the same way. Only the *first* message of a
 * fresh conversation gets this treatment - restored history is all `AgentLine`.
 */
export function LedeMessage({ children, question }: { children: ReactNode; question?: ReactNode }) {
  return (
    <p className="animate-rise text-lede text-text">
      {children}
      {question ? (
        <span className="mt-thread-lede-gap block text-lede-q font-medium text-text">
          {question}
        </span>
      ) : null}
    </p>
  );
}

/**
 * An assistant turn (`.a-prose`): bare prose, no bubble, no avatar. While
 * `streaming`, a caret trails the text the SSE tokens are building.
 */
export function AgentLine({
  children,
  streaming = false,
}: {
  children: ReactNode;
  streaming?: boolean;
}) {
  return (
    <p className="animate-rise mt-thread-gap break-words text-prose text-text">
      {children}
      {streaming ? (
        <span
          aria-hidden="true"
          className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-text align-middle"
        />
      ) : null}
    </p>
  );
}

/**
 * An owner turn (`.u-bubble`): filled brand red, right-aligned, tip bottom-right.
 * `bg-bubble-out` is the Rausch shade that can carry white body text
 * (`--primary-35`, 4.57:1); flat `--color-accent` would fail AA.
 * `break-words` because a pasted URL is a normal turn here (O-3) and one
 * unbreakable token would otherwise run straight past the screen edge.
 */
export function OwnerBubble({ children }: { children: ReactNode }) {
  return (
    <div className="animate-rise-fast mt-thread-gap max-w-[78%] self-end break-words rounded-[var(--radius-bubble-lg)_var(--radius-bubble-lg)_var(--radius-bubble-tip)_var(--radius-bubble-lg)] bg-bubble-out px-4 py-2.5 text-bubble text-text-inverse">
      {children}
    </div>
  );
}

/**
 * The pending-turn indicator (`.typing`): its own row in the thread, never
 * inside a bubble. Held through the failover window (P-5) and shown ahead of
 * static messages too, so pacing reads the same from the first beat.
 */
export function TypingLine() {
  return (
    <div className="animate-rise-fast mt-thread-gap-lg flex h-[22px] items-center">
      <ThinkingDots />
    </div>
  );
}

/**
 * The prototype's `.proc-txt`: a quiet italic line naming the slow thing the
 * assistant is doing right now ("Reading your site..."), left-aligned in the
 * thread rather than centred like a stamp, and replaced by the reply it
 * precedes. Distinct from `TypingLine` on purpose - dots say "thinking", this
 * says what is being read.
 */
export function ProcessingLine({ children }: { children: ReactNode }) {
  // W-3: no role="status" here - this renders inside Thread's own role="log"
  // (page.tsx), and that enclosing log already announces it (see the
  // nested-live-region note on Thread above).
  return (
    <p className="animate-rise-fast mt-3 text-proc italic text-ink-a35">
      {children}
    </p>
  );
}

/** A centered system stamp (`.sys-pill`) - "Code sent to ...", state changes. */
export function ThreadPill({ children }: { children: ReactNode }) {
  return (
    <p className="animate-rise mt-thread-gap self-center whitespace-nowrap rounded-chip bg-ink-a05 px-3.5 py-[5px] text-meta text-ink-a40">
      {children}
    </p>
  );
}

/**
 * The brand veil (`#s1-grad`): a gradient over the bottom of the screen that
 * fades away for good once the owner has answered once. Purely decorative.
 */
export function ThreadVeil({ started }: { started: boolean }) {
  return (
    <div
      aria-hidden="true"
      className={[
        "pointer-events-none absolute inset-x-0 bottom-0 -z-10 h-[56%] bg-veil",
        "transition-opacity duration-(--duration-veil) ease-out",
        started ? "opacity-0" : "opacity-100",
      ].join(" ")}
    />
  );
}
