"use client";

import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** Controls the panel's id so the hamburger can name it via aria-controls. */
  id?: string;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Console nav drawer: a 288px panel sliding in from the left behind a scrim.
 * The scrim animates its background-colour (bg-transparent -> bg-scrim) rather
 * than opacity; the panel slides on translate-x. Focus management
 * mirrors Modal.tsx - open saves document.activeElement and focuses the first
 * focusable in the panel, close restores it, Escape closes, Tab wraps within
 * the panel.
 *
 * Always rendered in the DOM (never conditionally unmounted) so the slide /
 * scrim transitions have something to animate between - toggling `inert` is
 * what removes it from focus/tab order and screen readers while closed.
 */
export function Drawer({ open, onClose, children, id }: DrawerProps) {
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
    <div inert={!open} onKeyDown={handleKeyDown} className="fixed inset-0 z-40">
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
        tabIndex={-1}
        id={id}
        className={[
          "absolute inset-y-0 left-0 flex h-full w-[288px] flex-col gap-1 rounded-r-[44px] bg-surface p-4 shadow-drawer",
          "transition-transform duration-(--duration-push) ease-push",
          open ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        {children}
      </div>
    </div>
  );
}
