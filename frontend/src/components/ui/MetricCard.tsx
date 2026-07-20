import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export interface MetricCardProps {
  label: string;
  /** Pre-formatted display string - this component never does arithmetic. */
  value: string;
  loading?: boolean;
  error?: string;
  /** Material Symbol rendered top-right in an accent chip. */
  icon?: IconName;
  /**
   * Directional delta shown under the value. `flat` renders the label with no
   * glyph; up/down add the matching trend arrow. The label is pre-formatted -
   * this component never derives or computes a delta.
   */
  trend?: { direction: "up" | "down" | "flat"; label: string };
  /** Extra content below the value (e.g. a Sparkline on a wide card). */
  footer?: ReactNode;
}

/**
 * docs/design/frontend.md section 6: bento stat card - big number + label,
 * optional accent icon chip, directional trend footnote, and a footer slot.
 * Backward compatible with the label/value/loading/error API used by the
 * platform metrics (T-033); the icon/trend/footer additions serve T-034's
 * dashboards. This component never does arithmetic - callers pass formatted
 * strings.
 */
export function MetricCard({ label, value, loading, error, icon, trend, footer }: MetricCardProps) {
  return (
    <div className="rounded-lg border border-border bg-surface p-6 shadow-1 transition-shadow hover:shadow-2">
      <div className="flex items-start justify-between gap-3">
        <p className="text-body-sm font-medium text-text-secondary">{label}</p>
        {icon ? (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent-subtle text-accent">
            <Icon name={icon} size={18} />
          </span>
        ) : null}
      </div>
      {loading ? (
        <div className="mt-2 h-9 w-24 animate-pulse rounded-md bg-surface-sunken" />
      ) : error ? (
        <p className="mt-2 text-body-sm text-danger">{error}</p>
      ) : (
        <>
          <p className="mt-1 text-title-1 font-semibold tabular-nums text-text">{value}</p>
          {trend ? (
            <p className="mt-1 flex items-center gap-1 text-footnote text-text-secondary">
              {trend.direction !== "flat" ? (
                <Icon
                  name={trend.direction === "up" ? "trending_up" : "trending_down"}
                  size={16}
                />
              ) : null}
              {trend.label}
            </p>
          ) : null}
        </>
      )}
      {footer ? <div className="mt-4">{footer}</div> : null}
    </div>
  );
}
