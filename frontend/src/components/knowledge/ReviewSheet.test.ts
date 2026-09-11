import { describe, expect, it } from "vitest";
import { offeringPage, offeringPageCount, pageForOffering, toWorkingOffering } from "./ReviewSheet";
import type { ReviewOffering } from "./types";

/**
 * W-6. What the owner is shown about a price is a product decision, not a
 * rendering detail: this is the surface where the extraction admits it could
 * not reduce a price to a number, and where a document-sourced offering finally
 * carries a description at all.
 */
function candidate(overrides: Partial<ReviewOffering> = {}): ReviewOffering {
  return {
    name: "Bowl",
    description: "",
    price_cents: null,
    sources: ["document"],
    ...overrides,
  };
}

describe("toWorkingOffering", () => {
  it("shows a description extracted from a document", () => {
    // The predecessor never populated `description` from a document at all -
    // every document-sourced row arrived blank and had to be typed by hand.
    const working = toWorkingOffering(
      candidate({ description: "comes with pita on the side", price_cents: 2700 }),
    );
    expect(working.description).toBe("comes with pita on the side");
    expect(working.priceText).toBe("$27.00");
  });

  it("shows the source's own wording for a price it refused to flatten", () => {
    const working = toWorkingOffering(
      candidate({ name: "Plate", needs_review: true, price_note: "both run $20–$30" }),
    );
    expect(working.priceText).toBe("");
    expect(working.priceNote).toBe("both run $20–$30");
  });

  it("does not treat a missing price as something to check", () => {
    // A source is allowed to be silent about what something costs. Flagging
    // that would put a warning on most of a real menu.
    const working = toWorkingOffering(candidate({ name: "chicken shawarma" }));
    expect(working.priceNote).toBe("");
    expect(working.priceText).toBe("");
  });

  it("carries possible matches without acting on them", () => {
    // Merging on similarity would silently delete a real offering, so the row
    // only ever points at its twin.
    const working = toWorkingOffering(
      candidate({ name: "coffe", possible_matches: ["coffee drinks"] }),
    );
    expect(working.possibleMatches).toEqual(["coffee drinks"]);
    expect(working.name).toBe("coffe");
  });

  it("defaults every new field so an owner-typed offering still works", () => {
    const working = toWorkingOffering({
      name: "Screen repair",
      description: "",
      price_cents: 8900,
      sources: ["owner"],
    });
    expect(working).toMatchObject({
      priceNote: "",
      possibleMatches: [],
      priceOptions: [],
      support_state: "supported",
      dirty: false,
    });
  });

  it("passes W-11 supporting document ids and support state through", () => {
    const working = toWorkingOffering(
      candidate({
        supporting_document_ids: ["doc-1"],
        support_state: "orphaned",
      }),
    );
    expect(working.supporting_document_ids).toEqual(["doc-1"]);
    expect(working.support_state).toBe("orphaned");
    expect(working.dirty).toBe(false);
  });
});

describe("offering pagination", () => {
  it.each([
    [0, 1],
    [5, 1],
    [6, 2],
    [40, 8],
    [51, 11],
  ])("uses five offerings per page for %i offerings", (count, pages) => {
    expect(offeringPageCount(count)).toBe(pages);
  });

  it("keeps the sixth offering on its own editor page", () => {
    const offerings = Array.from({ length: 6 }, (_, index) => `offering-${index + 1}`);
    expect(offeringPage(offerings, 0)).toEqual(offerings.slice(0, 5));
    expect(offeringPage(offerings, 1)).toEqual(["offering-6"]);
    expect(pageForOffering(5)).toBe(1);
  });
});
