export interface MetricCardProps {
  label: string;
  /** Pre-formatted display string - this component never does arithmetic. */
  value: string;
  loading?: boolean;
  error?: string;
}

/**
 * docs/design/frontend.md section 6: big number + label; dashboards. The
 * delta/trend part of the spec lands with T-034's dashboards - platform
 * metrics (T-033) only need the number.
 */
export function MetricCard({ label, value, loading, error }: MetricCardProps) {
  return (
    <div className="rounded-lg border border-border bg-surface p-6 shadow-1">
      <p className="text-body-sm font-medium text-text-secondary">{label}</p>
      {loading ? (
        <div className="mt-2 h-9 w-24 animate-pulse rounded-md bg-surface-sunken" />
      ) : error ? (
        <p className="mt-2 text-body-sm text-danger">{error}</p>
      ) : (
        <p className="mt-1 text-title-1 font-semibold tabular-nums text-text">{value}</p>
      )}
    </div>
  );
}
