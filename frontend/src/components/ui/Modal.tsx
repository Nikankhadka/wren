"use client";

import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * docs/design/frontend.md section 6: shadow-3, scrim token, open/close
 * transition, focus trap. Escape and a scrim click both close; focus returns
 * to whatever triggered the open. The Sheet (mobile) variant is deferred
 * until a surface actually needs it.
 *
 * Always rendered in the DOM (never conditionally unmounted) so the
 * open/close opacity transition has something to animate between - toggling
 * `inert` is what actually removes it from focus/tab order/screen readers
 * while closed, without needing JS timing tricks (setTimeout-after-transition,
 * a two-phase mount-then-show state dance) that a plain mount/unmount +
 * fade would otherwise require.
 */
export function Modal({ open, onClose, title, children }: ModalProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = panelRef.current;
    const first = panel?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
    (first ?? panel)?.focus();
    return () => {
      restoreFocusRef.current?.focus();
      restoreFocusRef.current = null;
    };
  }, [open]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const panel = panelRef.current;
    if (!panel) return;
    const focusables = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (!first || !last) {
      event.preventDefault();
      return;
    }
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === panel)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div
      inert={!open}
      onKeyDown={handleKeyDown}
      onMouseDown={(event) => {
        if (open && event.target === event.currentTarget) onClose();
      }}
      className={[
        "fixed inset-0 z-50 flex items-center justify-center bg-scrim p-4",
        "transition-opacity duration-base ease-out",
        open ? "opacity-100" : "pointer-events-none opacity-0",
      ].join(" ")}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={[
          "w-full max-w-md rounded-lg border border-border bg-surface p-6 shadow-3",
          "transition-[opacity,transform] duration-base ease-out",
          open ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
        ].join(" ")}
      >
        <h2 id={titleId} className="text-title-3 font-semibold text-text">
          {title}
        </h2>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}
