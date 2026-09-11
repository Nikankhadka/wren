export type BadgeTone = "info" | "warning" | "success" | "danger" | "neutral";

const TONE_CLASSES: Record<BadgeTone, string> = {
  info: "bg-info-subtle text-info",
  warning: "bg-warning-subtle text-warning",
  success: "bg-success-subtle text-success",
  danger: "bg-danger-subtle text-danger",
  neutral: "bg-surface-sunken text-text-secondary",
};

/**
 * B-3 US-2: every status string this product can show, mapped to a meaning.
 *
 * The convention is `docs/agencx/design/frontend.md` section 2 - green for
 * things that went well, red for things that did not, amber for things still
 * in flight, neutral for statuses carrying no good/bad/pending charge. Berry
 * is the brand accent and never appears here: a status that borrowed it would
 * read as "important" rather than as what it means.
 *
 * The keys cover both the schema's own vocabulary (documents, conversations,
 * tenants, quotes, escalations) and the tenant-defined order/repair statuses
 * the seeds use (`in_progress`, `ready_for_pickup`, `completed`, `cancelled`,
 * `shipped`, `delivered`). A tenant may invent others - `toneForStatus` falls
 * back to neutral, which is the honest answer for a word we have never seen.
 */
const STATUS_TONE: Record<string, BadgeTone> = {
  // Green - it went well, or it is done.
  approved: "success",
  success: "success",
  complete: "success",
  completed: "success",
  paid: "success",
  ready: "success",
  ready_for_pickup: "success",
  resolved: "success",
  closed: "success",
  active: "success",
  delivered: "success",
  confirmed: "success",

  // Red - it did not go well, or it was stopped.
  cancelled: "danger",
  declined: "danger",
  rejected: "danger",
  refunded: "danger",
  failed: "danger",
  suspended: "danger",
  error: "danger",

  // Amber - still in flight, and someone may need to do something.
  pending: "warning",
  warning: "warning",
  overdue: "warning",
  outstanding: "warning",
  in_progress: "warning",
  processing: "warning",
  provisioning: "warning",
  claimed: "warning",
  escalated: "warning",
  // Shipped is not delivered. Amber says "on its way", which is what the
  // customer is actually waiting on; green would claim it had arrived.
  shipped: "warning",

  // No charge either way.
  open: "info",
  sent: "info",
  draft: "neutral",
  expired: "neutral",
};

/**
 * The tone for a status string. Normalises case and separators first, so the
 * one entry `in_progress` also answers "In Progress" and "in-progress" - the
 * database, the seeds and the design doc each spell it differently, and three
 * map keys for one concept is how one of them silently goes neutral.
 */
export function toneForStatus(status: string): BadgeTone {
  const key = status.trim().toLowerCase().replace(/[\s-]+/g, "_");
  return STATUS_TONE[key] ?? "neutral";
}

export interface BadgeProps {
  tone: BadgeTone;
  children: string;
}

export function Badge({ tone, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-caption font-semibold uppercase ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
