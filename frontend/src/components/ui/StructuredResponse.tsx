import { CatalogCard, type CatalogPayload } from "./CatalogCard";
import { PriceSummaryCard, type PriceSummaryPayload } from "./PriceSummaryCard";

export function StructuredResponse({ response }: { response: unknown }) {
  if (!response || typeof response !== "object") return null;
  const value = response as {
    type?: unknown;
    summary?: unknown;
    catalog?: unknown;
  };
  if (value.type === "price_summary") {
    return <PriceSummaryCard summary={value.summary as PriceSummaryPayload} />;
  }
  if (value.type === "catalog") {
    return <CatalogCard catalog={value.catalog as CatalogPayload} />;
  }
  return null;
}
