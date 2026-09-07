import { formatCents } from "@/lib/money";

export interface CatalogOffering {
  id: string;
  name: string;
  description: string;
  category: string | null;
  price_cents: number | null;
}

export interface CatalogPayload {
  offerings: CatalogOffering[];
}

export function CatalogCard({ catalog }: { catalog: CatalogPayload }) {
  const groups: Array<[string, CatalogOffering[]]> = [];
  for (const offering of catalog.offerings) {
    const heading = offering.category?.trim() || "Offerings";
    const group = groups.find(([name]) => name === heading);
    if (group) group[1].push(offering);
    else groups.push([heading, [offering]]);
  }

  return (
    <div
      aria-label="Catalog"
      className="mt-2 w-full max-w-[520px] rounded-card border border-border bg-surface p-4"
    >
      <h3 className="mb-3 text-body font-semibold text-text">Current offerings</h3>
      <div className="flex flex-col gap-4">
        {groups.map(([heading, offerings]) => (
          <section key={heading}>
            <h4 className="mb-1 text-footnote font-semibold uppercase tracking-wide text-text-secondary">
              {heading}
            </h4>
            <ul>
              {offerings.map((offering) => (
                <li key={offering.id} className="border-b border-hairline py-2 last:border-0">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-medium text-text">{offering.name}</span>
                    <span className="shrink-0 tabular-nums text-body-sm text-text">
                      {offering.price_cents === null
                        ? "Price not listed"
                        : formatCents(offering.price_cents)}
                    </span>
                  </div>
                  {offering.description ? (
                    <p className="mt-0.5 text-body-sm text-text-secondary">{offering.description}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
