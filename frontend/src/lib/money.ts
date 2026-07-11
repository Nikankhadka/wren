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
