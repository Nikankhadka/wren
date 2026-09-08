import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PriceSummaryCard, type PriceSummaryPayload } from "./PriceSummaryCard";

/**
 * W-9: calculate_quote's line items carry `item_id`/`code`
 * (backend/app/agents/agent_node.py, backend/app/pricing/engine.py's
 * LineItem.to_dict) so a follow-up turn can re-select the same row, but
 * PriceSummaryCard only reads that field for React's `key=` - the printed
 * line is `label`, the tenant-authored item name. These tests pin that
 * split, plus the money-is-server-computed rule (T-017).
 */
describe("PriceSummaryCard", () => {
  it("never lets a line item's catalog item id reach the rendered output", () => {
    const itemId = "8f14e45f-ceea-467e-bd3d-46f5b2f6e242";
    const summary: PriceSummaryPayload = {
      line_items: [
        {
          kind: "item",
          item_id: itemId,
          label: "Screen repair",
          quantity: 1,
          unit_amount_cents: 8900,
          line_total_cents: 8900,
        },
      ],
      subtotal_cents: 8900,
      tax_cents: 0,
      total_cents: 8900,
      disclaimer: "Based on the business's current confirmed prices.",
    };

    const html = renderToStaticMarkup(<PriceSummaryCard summary={summary} />);

    expect(html).not.toContain(itemId);
  });

  it("renders totals from the server-provided cents verbatim, no arithmetic", () => {
    // Deliberately inconsistent subtotal/tax/total: if the component summed
    // the line items or added subtotal+tax itself, this would render the
    // wrong total instead of the exact (wrong-looking) cents given to it.
    const summary: PriceSummaryPayload = {
      line_items: [
        {
          kind: "rule",
          code: "setup-fee",
          label: "Setup fee",
          quantity: 1,
          unit_amount_cents: 100,
          line_total_cents: 100,
        },
      ],
      subtotal_cents: 100,
      tax_cents: 0,
      total_cents: 999,
      disclaimer: "",
    };

    const html = renderToStaticMarkup(<PriceSummaryCard summary={summary} />);

    expect(html).toContain("$1.00");
    expect(html).toContain("$9.99");
  });

  it("shows the quantity multiplier only when there is more than one", () => {
    const line = (quantity: number): PriceSummaryPayload => ({
      line_items: [
        {
          kind: "item",
          item_id: "1",
          label: "Widget",
          quantity,
          unit_amount_cents: 500,
          line_total_cents: 500 * quantity,
        },
      ],
      subtotal_cents: 500 * quantity,
      tax_cents: 0,
      total_cents: 500 * quantity,
      disclaimer: "",
    });

    expect(renderToStaticMarkup(<PriceSummaryCard summary={line(1)} />)).not.toContain("×1");
    expect(renderToStaticMarkup(<PriceSummaryCard summary={line(3)} />)).toContain("×3");
  });
});
