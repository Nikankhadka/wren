export type BadgeTone = "info" | "warning" | "success" | "danger" | "neutral";

const TONE_CLASSES: Record<BadgeTone, string> = {
  info: "bg-info-subtle text-info",
  warning: "bg-warning-subtle text-warning",
  success: "bg-success-subtle text-success",
  danger: "bg-danger-subtle text-danger",
  neutral: "bg-surface-sunken text-text-secondary",
};

/**
 * docs/design/frontend.md section 6: status pill mapping every status
 * vocabulary in database.md to functional tokens - info = open/sent;
 * warning = escalated/claimed/processing/provisioning; success =
 * resolved/closed/active/ready; danger = failed/suspended; neutral =
 * pending/draft/expired.
 */
const STATUS_TONE: Record<string, BadgeTone> = {
  open: "info",
  sent: "info",
  escalated: "warning",
  claimed: "warning",
  processing: "warning",
  provisioning: "warning",
  resolved: "success",
  closed: "success",
  active: "success",
  ready: "success",
  failed: "danger",
  suspended: "danger",
  pending: "neutral",
  draft: "neutral",
  expired: "neutral",
};

export function toneForStatus(status: string): BadgeTone {
  return STATUS_TONE[status] ?? "neutral";
}

export interface BadgeProps {
  tone: BadgeTone;
  children: string;
}

export function Badge({ tone, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-footnote font-medium ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
