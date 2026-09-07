import { formatCents } from "@/lib/money";

export interface PriceSummaryLineItem {
  kind: "rule" | "item";
  code?: string;
  item_id?: string;
  label: string;
  quantity: number;
  unit_amount_cents: number;
  line_total_cents: number;
}

export interface PriceSummaryPayload {
  line_items: PriceSummaryLineItem[];
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  disclaimer: string;
}

export function PriceSummaryCard({ summary }: { summary: PriceSummaryPayload }) {
  return (
    <div
      aria-label="Price summary"
      className="mt-2 w-full max-w-[420px] rounded-card border border-border bg-surface p-4"
    >
      <h3 className="mb-3 text-body font-semibold text-text">Price summary</h3>
      <ul className="flex flex-col gap-1.5">
        {summary.line_items.map((item) => (
          <li
            key={item.code ?? item.item_id ?? item.label}
            className="flex items-baseline justify-between gap-3 border-b border-hairline pb-1.5 text-body-sm text-text last:border-0"
          >
            <span>
              {item.label}
              {item.quantity > 1 ? (
                <span className="text-text-secondary"> ×{item.quantity}</span>
              ) : null}
            </span>
            <span className="shrink-0 tabular-nums">{formatCents(item.line_total_cents)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-col gap-1 border-t border-border pt-2">
        <div className="flex items-baseline justify-between text-body-sm text-text-secondary">
          <span>Subtotal</span>
          <span className="tabular-nums">{formatCents(summary.subtotal_cents)}</span>
        </div>
        {summary.tax_cents > 0 ? (
          <div className="flex items-baseline justify-between text-body-sm text-text-secondary">
            <span>Tax</span>
            <span className="tabular-nums">{formatCents(summary.tax_cents)}</span>
          </div>
        ) : null}
        <div className="flex items-baseline justify-between text-body font-semibold text-text">
          <span>Total</span>
          <span className="tabular-nums">{formatCents(summary.total_cents)}</span>
        </div>
      </div>
      <p className="mt-3 text-footnote text-text-secondary">{summary.disclaimer}</p>
    </div>
  );
}
