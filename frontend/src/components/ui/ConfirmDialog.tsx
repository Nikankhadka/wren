"use client";

import { useCallback, useState, type ReactNode } from "react";
import { Button } from "./Button";
import { Modal } from "./Modal";

export interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "danger" | "default";
  /** "top" paints above an open Sheet, which otherwise sits at the same z. */
  layer?: "base" | "top";
  /**
   * Runs when the owner accepts. Reports its own failures (toast or inline)
   * and never throws - `confirm` resolves false on a throw regardless.
   * Optional for confirm-then-act flows, where the caller acts on `true`.
   */
  onConfirm?: () => void | Promise<void>;
}

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "danger" | "default";
  working?: boolean;
  layer?: "base" | "top";
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * docs/agencx/design/frontend.md section 6: the app's one confirmation
 * dialog. Built on Modal, so Escape, scrim, focus trap and focus restore
 * behave like every other dialog. Stateless - all state lives in
 * `useConfirm`, which keeps this renderable to static markup for tests.
 *
 * Closed renders nothing at all - deliberately not Modal's always-mounted
 * inert shell. A mounted shell would leave an empty `<h2>` in the
 * accessibility tree on every screen that owns a hook (the layout owns one),
 * and empty headings break role-based locators as well as screen readers.
 * `confirm-accept` is therefore unique while open even with one hook per
 * layout, page, and sheet on the same screen.
 *
 * `window.confirm` is banned: a native dialog cannot wear the product's
 * voice, cannot be reached by the E2E suite's locators, and on a phone it
 * reads as the browser interrupting rather than the app asking.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "default",
  working = false,
  layer = "base",
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  if (!open) return null;
  return (
    <Modal
      open={open}
      // A working confirm is mid-mutation: Escape and the scrim wait for it
      // rather than abandoning it, and the cancel button below is disabled.
      onClose={() => {
        if (!working) onCancel();
      }}
      title={title}
      layer={layer}
    >
      <div className="flex flex-col gap-4">
        {description ? <p className="text-body-sm text-text">{description}</p> : null}
        <div className="flex gap-2">
          <Button
            variant={tone === "danger" ? "destructive" : "primary"}
            loading={working}
            onClick={onConfirm}
            data-testid="confirm-accept"
          >
            {confirmLabel}
          </Button>
          <Button variant="secondary" onClick={onCancel} disabled={working}>
            {cancelLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

interface PendingConfirm extends ConfirmOptions {
  resolve: (confirmed: boolean) => void;
}

/**
 * Promise-style confirmations. `confirm` opens the dialog and resolves true
 * once `onConfirm` settles, false on cancel, Escape, scrim, or a throw.
 * Render `dialog` once per screen, as a sibling of the content - never
 * inside a Sheet or Drawer panel, whose transform clips a fixed overlay.
 */
export function useConfirm(): {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  dialog: ReactNode;
} {
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const [working, setWorking] = useState(false);

  const confirm = useCallback((options: ConfirmOptions) => {
    setWorking(false);
    return new Promise<boolean>((resolve) => {
      setPending({ ...options, resolve });
    });
  }, []);

  function cancel() {
    pending?.resolve(false);
    setPending(null);
    setWorking(false);
  }

  async function accept() {
    const current = pending;
    if (!current || working) return;
    setWorking(true);
    try {
      await current.onConfirm?.();
      current.resolve(true);
    } catch {
      current.resolve(false);
    } finally {
      setPending(null);
      setWorking(false);
    }
  }

  return {
    confirm,
    dialog: (
      <ConfirmDialog
        open={pending !== null}
        title={pending?.title ?? ""}
        description={pending?.description}
        confirmLabel={pending?.confirmLabel ?? ""}
        cancelLabel={pending?.cancelLabel}
        tone={pending?.tone}
        layer={pending?.layer}
        working={working}
        onCancel={cancel}
        onConfirm={() => void accept()}
      />
    ),
  };
}
