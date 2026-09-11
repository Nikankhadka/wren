import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { insertOwnerOffering, offeringPage, offeringPageCount, pageForOffering, Pagination, ReviewSheet, toWorkingOffering } from "./ReviewSheet";
import type { KnowledgeRecord, ReviewOffering, ReviewWorkspace } from "./types";

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

describe("review toolbar", () => {
  function record(overrides: Partial<KnowledgeRecord> = {}): KnowledgeRecord {
    return {
      id: "doc-1",
      filename: "menu.pdf",
      doc_type: "other",
      status: "draft",
      error: null,
      sections: [],
      ...overrides,
    };
  }

  function workspaceWith(offeringCount: number): ReviewWorkspace {
    return {
      id: "ws-1",
      documents: [record()],
      offering_candidates: Array.from({ length: offeringCount }, (_, index) => ({
        name: `Offering ${index + 1}`,
        description: "",
        price_cents: null,
        sources: ["owner"] as const,
      })),
    };
  }

  function renderSheet(workspace: ReviewWorkspace): string {
    return renderToStaticMarkup(
      <ReviewSheet
        workspace={workspace}
        open
        busy={false}
        priceConflict={null}
        onClose={() => {}}
        onSave={async () => null}
        onDiscard={() => {}}
      />,
    );
  }

  it("keeps Review all and Add offering at opposite ends of one row", () => {
    const html = renderSheet(workspaceWith(7));
    expect(html).toContain('<div class="mt-3 flex items-center justify-between">');
    expect(html).toContain("Review all 7");
    expect(html).toContain("Add offering");
    expect(html.indexOf("Review all 7")).toBeLessThan(html.indexOf("Add offering"));
    // Collapsed: only the first page of rows renders, pagination stays hidden.
    for (const name of ["Offering 1", "Offering 5"]) {
      expect(html).toContain(`>${name}</h4>`);
    }
    expect(html).not.toContain(">Offering 6</h4>");
    expect(html).not.toContain("Page 1 of");
  });

  it("right-aligns Add offering with an empty span when Review all is hidden", () => {
    const html = renderSheet(workspaceWith(4));
    expect(html).not.toContain("Review all");
    expect(html).not.toContain("Edit offerings");
    expect(html).toContain(
      '<span></span><button type="button" class="text-action font-medium text-accent-active">Add offering</button>',
    );
  });

  it("inserts a new offering after the last owner row and pages to it", () => {
    const owners = Array.from({ length: 11 }, (_, index) =>
      toWorkingOffering({
        name: `Owner ${index + 1}`,
        description: "",
        price_cents: null,
        sources: ["owner"],
      }),
    );
    const imported = toWorkingOffering({
      name: "Imported",
      description: "",
      price_cents: null,
      sources: ["document"],
    });
    const fresh = toWorkingOffering({
      name: "Fresh",
      description: "",
      price_cents: null,
      sources: ["owner"],
    });
    const after = insertOwnerOffering([...owners, imported], fresh);
    expect(after.list.map((item) => item.name)).toEqual([
      ...owners.map((item) => item.name),
      "Fresh",
      "Imported",
    ]);
    expect(after.page).toBe(pageForOffering(11));
    // No owner rows: the fresh row leads the list on page 1.
    const top = insertOwnerOffering([imported], fresh);
    expect(top.list.map((item) => item.name)).toEqual(["Fresh", "Imported"]);
    expect(top.page).toBe(0);
  });
});

describe("pagination copy", () => {
  function renderPagination(page: number, pages: number, count: number): string {
    return renderToStaticMarkup(
      <Pagination page={page} pages={pages} count={count} onPage={() => {}} />,
    );
  }

  it("says Page X of Y and Showing A-B of N offerings", () => {
    const first = renderPagination(0, 3, 12);
    expect(first).toContain("Page 1 of 3");
    expect(first).toContain("Showing 1-5 of 12 offerings");
    expect(first).toContain('disabled=""');
    const middle = renderPagination(1, 3, 12);
    expect(middle).toContain("Page 2 of 3");
    expect(middle).toContain("Showing 6-10 of 12 offerings");
    const last = renderPagination(2, 3, 12);
    expect(last).toContain("Page 3 of 3");
    expect(last).toContain("Showing 11-12 of 12 offerings");
  });

  it("always says offerings, even for a single row on the last page", () => {
    const html = renderPagination(1, 2, 6);
    expect(html).toContain("Showing 6-6 of 6 offerings");
  });

  it("disables Previous on the first page and Next on the last", () => {
    const first = renderPagination(0, 3, 12);
    expect(first).toMatch(/<button type="button" disabled=""[^>]*>Previous<\/button>/);
    expect(first).not.toMatch(/<button type="button" disabled=""[^>]*>Next<\/button>/);
    const last = renderPagination(2, 3, 12);
    expect(last).not.toMatch(/<button type="button" disabled=""[^>]*>Previous<\/button>/);
    expect(last).toMatch(/<button type="button" disabled=""[^>]*>Next<\/button>/);
  });
});
