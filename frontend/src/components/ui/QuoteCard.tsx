import { Badge, toneForStatus } from "./Badge";
import { formatCents } from "@/lib/money";

export interface QuoteLineItem {
  kind: "rule" | "item";
  code?: string;
  item_id?: string;
  label: string;
  quantity: number;
  unit_amount_cents: number;
  line_total_cents: number;
}

export interface QuotePayload {
  quote_id: string;
  line_items: QuoteLineItem[];
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  status: string;
}

/**
 * docs/design/frontend.md section 6: renders pricing-engine output verbatim.
 * Every figure shown is an engine-computed *_cents value passed through
 * formatCents - no arithmetic happens here, ever (deterministic-pricing
 * rule in UI form).
 */
export function QuoteCard({ quote }: { quote: QuotePayload }) {
  return (
    <div className="mt-2 w-full max-w-[420px] rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-footnote font-semibold uppercase tracking-wide text-text-secondary">
          Quote
        </span>
        <Badge tone={toneForStatus(quote.status)}>{quote.status}</Badge>
      </div>

      <ul className="flex flex-col gap-1.5">
        {quote.line_items.map((item) => (
          <li
            key={item.code ?? item.item_id}
            className="flex items-baseline justify-between gap-3 text-body-sm text-text"
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
          <span className="tabular-nums">{formatCents(quote.subtotal_cents)}</span>
        </div>
        {quote.tax_cents > 0 ? (
          <div className="flex items-baseline justify-between text-body-sm text-text-secondary">
            <span>Tax</span>
            <span className="tabular-nums">{formatCents(quote.tax_cents)}</span>
          </div>
        ) : null}
        <div className="flex items-baseline justify-between text-body font-semibold text-text">
          <span>Total</span>
          <span className="tabular-nums">{formatCents(quote.total_cents)}</span>
        </div>
      </div>
    </div>
  );
}
