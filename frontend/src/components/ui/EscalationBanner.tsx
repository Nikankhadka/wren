export interface EscalationBannerProps {
  message?: string;
}

/**
 * docs/design/frontend.md section 6: in-chat handoff state - "A human will
 * take it from here" + position/status. Replaces the composer once a
 * conversation escalates (frontend.md 7.1's Escalated row: "EscalationBanner
 * replaces composer state messaging; conversation stays readable").
 */
export function EscalationBanner({
  message = "A human will take it from here.",
}: EscalationBannerProps) {
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 border-t border-border bg-warning-subtle px-4 py-3 text-body-sm font-medium text-warning"
    >
      {message}
    </div>
  );
}
