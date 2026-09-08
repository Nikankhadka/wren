import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CatalogCard, type CatalogPayload } from "./CatalogCard";

/**
 * W-9: the offering id (`catalog_id=` in the model's prompt, `id` on this
 * payload - backend/app/services/context_package.py, backend/app/agents/
 * agent_node.py's show_catalog handler) is how a later turn names a row, so
 * it has to be on the payload. CatalogCard only ever reads it for `key=`,
 * never prints it - these tests pin that split.
 */
describe("CatalogCard", () => {
  it("shows 'Price not listed' for an offering with no price", () => {
    const catalog: CatalogPayload = {
      offerings: [
        {
          id: "8f14e45f-ceea-467e-bd3d-46f5b2f6e242",
          name: "Custom engraving",
          description: "",
          category: null,
          price_cents: null,
        },
      ],
    };

    const html = renderToStaticMarkup(<CatalogCard catalog={catalog} />);

    expect(html).toContain("Price not listed");
  });

  it("never lets an offering id reach the rendered output", () => {
    const id = "8f14e45f-ceea-467e-bd3d-46f5b2f6e242";
    const catalog: CatalogPayload = {
      offerings: [
        {
          id,
          name: "Coffee",
          description: "Freshly brewed",
          category: "Drinks",
          price_cents: 350,
        },
      ],
    };

    const html = renderToStaticMarkup(<CatalogCard catalog={catalog} />);

    expect(html).not.toContain(id);
  });

  it("renders the server-provided price cents verbatim, no arithmetic", () => {
    // An odd amount that would look wrong under any rounding or unit
    // conversion the component might be tempted to do on its own.
    const catalog: CatalogPayload = {
      offerings: [
        {
          id: "1",
          name: "Odd amount",
          description: "",
          category: null,
          price_cents: 12345,
        },
      ],
    };

    const html = renderToStaticMarkup(<CatalogCard catalog={catalog} />);

    expect(html).toContain("$123.45");
  });
});
