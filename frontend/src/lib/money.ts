/**
 * T-017: the ONE place integer cents become display money
 * (docs/design/frontend.md section 6, QuoteCard row). Components never do
 * money arithmetic - they pass engine-provided *_cents values here verbatim.
 */
export function formatCents(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

/**
 * T-031: the cost-accounting side of the same rule. cost_logs stores a float
 * dollar amount (cost_usd), not integer cents, so it is formatted directly -
 * never scaled to cents and run through formatCents (that arithmetic-in-a-
 * component detour is exactly what the money rule forbids). Trace/cost
 * figures can be sub-cent, so up to 4 fraction digits are shown.
 */
export function formatUsd(dollars: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(dollars);
}
