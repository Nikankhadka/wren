"use client";

import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Knowledge review is a document on desktop, while every other sheet stays mobile-first. */
  desktop?: boolean;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Mobile bottom sheet (the "Sheet" half of the Modal/Sheet pair in
 * design.md's component wall). Slides up from the bottom behind a scrim that
 * animates its background colour (matching the drawer), with the same focus
 * management as Modal/Drawer: save active element on open, focus the first
 * focusable, restore on close, Escape/scrim close, Tab wraps.
 *
 * Always rendered in the DOM (toggling `inert`), never conditionally
 * unmounted, so the slide transition has something to animate between.
 */
export function Sheet({ open, onClose, title, children, desktop = false }: SheetProps) {
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
      aria-hidden={!open}
      onKeyDown={handleKeyDown}
      className="fixed inset-0 z-50"
    >
      <div
        aria-hidden="true"
        onClick={onClose}
        className={[
          "absolute inset-0 transition-colors duration-(--duration-push) ease-push",
          open ? "bg-scrim" : "pointer-events-none bg-transparent",
        ].join(" ")}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={[
          "absolute inset-x-0 bottom-0 flex max-h-[85%] flex-col rounded-t-[28px] bg-surface p-4 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-sheet",
          desktop ? "sm:inset-y-8 sm:mx-auto sm:max-w-[48rem] sm:rounded-card" : "",
          "transition-transform duration-(--duration-push) ease-push",
          open
            ? "translate-y-0"
            : desktop
              ? // The desktop variant is inset from the top as well as the bottom
                // (`sm:inset-y-8`) and capped at max-h-85%, so translating by its
                // own height - the mobile behavior - stops its top short of the
                // viewport (e.g. 712px on an 800px screen) and leaves its header
                // peeking above the fold. A full viewport minus the 2rem top
                // inset clears it at any panel height.
                "translate-y-full sm:translate-y-[calc(100vh_-_2rem)]"
              : "translate-y-full",
        ].join(" ")}
      >
        <div className="mx-auto mb-3 h-1 w-[42px] shrink-0 rounded-full bg-surface-container-high" />
        <div className="mb-3 flex shrink-0 items-center justify-between">
          <h2 id={titleId} className="text-title-3 font-semibold text-text">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="flex h-11 w-11 items-center justify-center rounded-full text-text-tertiary transition-colors duration-(--duration-fast) hover:bg-surface-container hover:text-text active:bg-surface-container-high"
          >
            <span aria-hidden="true" className="text-body-lg leading-none">
              ×
            </span>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
