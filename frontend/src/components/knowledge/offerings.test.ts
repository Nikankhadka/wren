import { describe, expect, it } from "vitest";
import {
  buildWorkspace,
  mergeIncomingCandidates,
  mergeOffering,
  offeringLabel,
  reconcileAfterSave,
  reconcileOfferings,
  withCombinedOfferings,
} from "./offerings";
import type { KnowledgeRecord, PendingOffering, ReviewOffering } from "./types";

/** W-11c. The offering merge and lifecycle policies, mirrored from
 *  backend/app/onboarding/flow.py - the tests here pin the client-side twins
 *  to the server's behavior so a replacement never surprises the owner. */
function offering(overrides: Partial<ReviewOffering> = {}): ReviewOffering {
  return {
    name: "Bowl",
    description: "",
    price_cents: null,
    sources: ["document"],
    supporting_document_ids: [],
    support_state: "supported",
    ...overrides,
  };
}

function record(overrides: Partial<KnowledgeRecord> = {}): KnowledgeRecord {
  return {
    id: crypto.randomUUID(),
    filename: "menu.pdf",
    doc_type: "other",
    status: "draft",
    error: null,
    sections: [],
    offering_candidates: [],
    extraction_status: "full",
    ...overrides,
  };
}

describe("withCombinedOfferings ordering", () => {
  it("lists owner rows first in insertion order, then document rows in record order", () => {
    const docs = [
      record({
        id: "d1",
        offering_candidates: [
          offering({ name: "Lamb Bowl" }),
          offering({ name: "Falafel" }),
        ],
      }),
      record({
        id: "d2",
        offering_candidates: [offering({ name: "Shawarma" })],
      }),
    ];
    const owner: PendingOffering[] = [
      { name: "Hummus", description: "", price_cents: 500, sources: ["owner"] },
      { name: "Tea", description: "", price_cents: 200, sources: ["owner"] },
    ];
    const result = withCombinedOfferings(docs, owner);
    expect(result.map((item) => item.name)).toEqual([
      "Hummus",
      "Tea",
      "Lamb Bowl",
      "Falafel",
      "Shawarma",
    ]);
  });

  it("keeps a merged row at the owner's position", () => {
    const docs = [
      record({
        offering_candidates: [
          offering({ name: "Bowl", price_cents: 1500, description: "lamb bowl" }),
        ],
      }),
    ];
    const owner: PendingOffering[] = [
      { name: "Bowl", description: "", price_cents: 1200, sources: ["owner"] },
      { name: "Tea", description: "", price_cents: 200, sources: ["owner"] },
    ];
    const result = withCombinedOfferings(docs, owner);
    expect(result.map((item) => item.name)).toEqual(["Bowl", "Tea"]);
  });
});

describe("mergeOffering precedence", () => {
  it("lets the document win name, price and description over an owner row", () => {
    const owner = offering({
      name: "Bowl",
      description: "typed",
      price_cents: 1000,
      sources: ["owner"],
      candidate_id: "owner-1",
    });
    const doc = offering({
      name: "Lamb Bowl",
      description: "extracted",
      price_cents: 1500,
      sources: ["document"],
      candidate_id: "doc-1",
    });
    const merged = mergeOffering(owner, doc);
    expect(merged.name).toBe("Lamb Bowl");
    expect(merged.description).toBe("extracted");
    expect(merged.price_cents).toBe(1500);
    expect(merged.candidate_id).toBe("doc-1");
  });

  it("unions sources and supporting document ids", () => {
    const owner = offering({ name: "Bowl", sources: ["owner"] });
    const doc = offering({
      name: "Bowl",
      sources: ["document"],
      supporting_document_ids: ["d1"],
    });
    const merged = mergeOffering(owner, doc);
    expect(merged.sources).toEqual(["owner", "document"]);
    expect(merged.supporting_document_ids).toEqual(["d1"]);
  });

  it("keeps two distinct prices as price_options instead of choosing", () => {
    const owner = offering({ name: "Bowl", price_cents: 1000, sources: ["owner"] });
    const doc = offering({ name: "Bowl", price_cents: 1500, sources: ["document"] });
    const merged = mergeOffering(owner, doc);
    expect(merged.price_options).toEqual([1000, 1500]);
  });

  it("keeps a single agreeing price without raising price_options", () => {
    const owner = offering({ name: "Bowl", price_cents: 1000, sources: ["owner"] });
    const doc = offering({ name: "Bowl", price_cents: 1000, sources: ["document"] });
    const merged = mergeOffering(owner, doc);
    expect(merged.price_cents).toBe(1000);
    expect(merged.price_options).toBeUndefined();
  });
});

describe("reconcileOfferings", () => {
  const doc1 = "d1";
  const doc2 = "d2";

  it("merges a candidate the new document matches by name", () => {
    const existing = [
      offering({
        name: "Flat White",
        price_cents: 550,
        supporting_document_ids: [doc1],
        candidate_id: "c1",
      }),
    ];
    const incoming = [
      offering({
        name: "Flat White",
        description: "Our house blend",
        supporting_document_ids: [doc2],
        candidate_id: "c2",
      }),
    ];
    const result = reconcileOfferings(existing, incoming, doc1, new Set());
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("Flat White");
    expect(result[0].price_cents).toBe(550);
    expect(result[0].description).toBe("Our house blend");
    expect(result[0].candidate_id).toBe("c1");
    expect(result[0].supporting_document_ids).toEqual([doc2]);
    expect(result[0].support_state).toBe("supported");
  });

  it("drops an unedited doc-only candidate the new document lacks", () => {
    const existing = [
      offering({ name: "Bowl", supporting_document_ids: [doc1], candidate_id: "c1" }),
    ];
    const result = reconcileOfferings(existing, [], doc1, new Set());
    expect(result).toEqual([]);
  });

  it("keeps an edited doc-only candidate as orphaned", () => {
    const existing = [
      offering({ name: "Bowl", supporting_document_ids: [doc1], candidate_id: "c1" }),
    ];
    const result = reconcileOfferings(existing, [], doc1, new Set(["c1"]));
    expect(result).toHaveLength(1);
    expect(result[0].support_state).toBe("orphaned");
    expect(result[0].supporting_document_ids).toEqual([]);
  });

  it("keeps an owner-typed candidate untouched", () => {
    const existing = [offering({ name: "Tea", sources: ["owner"], candidate_id: "c1" })];
    const result = reconcileOfferings(existing, [], doc1, new Set());
    expect(result).toEqual([existing[0]]);
  });

  it("keeps a candidate still backed by another document", () => {
    const existing = [
      offering({
        name: "Bowl",
        supporting_document_ids: [doc1, doc2],
        candidate_id: "c1",
      }),
    ];
    const result = reconcileOfferings(existing, [], doc1, new Set());
    expect(result).toHaveLength(1);
    expect(result[0].supporting_document_ids).toEqual([doc2]);
    expect(result[0].support_state).toBe("supported");
  });

  it("strips the document source from an owner row that lost its only document", () => {
    const existing = [
      offering({
        name: "Bowl",
        sources: ["owner", "document"],
        supporting_document_ids: [doc1],
        candidate_id: "c1",
      }),
    ];
    const result = reconcileOfferings(existing, [], doc1, new Set());
    expect(result).toHaveLength(1);
    expect(result[0].sources).toEqual(["owner"]);
    expect(result[0].support_state).toBe("supported");
  });

  it("keeps a legacy document source when support ids were already empty", () => {
    const existing = [
      offering({
        name: "Bowl",
        sources: ["owner", "document"],
        supporting_document_ids: [],
        candidate_id: "c1",
      }),
    ];
    const result = reconcileOfferings(existing, [], doc1, new Set());
    expect(result[0]).toEqual(existing[0]);
  });

  it("appends unmatched incoming candidates at the end", () => {
    const existing = [offering({ name: "Tea", sources: ["owner"], candidate_id: "c1" })];
    const incoming = [
      offering({ name: "Bowl", supporting_document_ids: [doc2], candidate_id: "c2" }),
    ];
    const result = reconcileOfferings(existing, incoming, doc1, new Set());
    expect(result.map((item) => item.name)).toEqual(["Tea", "Bowl"]);
    expect(result[1].supporting_document_ids).toEqual([doc2]);
  });
});

describe("reconcileAfterSave", () => {
  const docA = "doc-a";
  const docB = "doc-b";

  it("keeps rows the server returned, merged by name, across every submitted document", () => {
    const existing = [
      offering({
        name: "Bowl",
        supporting_document_ids: [docA],
        candidate_id: "c1",
      }),
      offering({ name: "Tea", sources: ["owner"], candidate_id: "c2" }),
    ];
    const incoming = [
      offering({ name: "Bowl", supporting_document_ids: [docA], candidate_id: "c1" }),
    ];
    const result = reconcileAfterSave(
      existing,
      incoming,
      [record({ id: docA }), record({ id: docB })],
      new Set(),
    );
    expect(result.map((item) => item.name)).toEqual(["Bowl", "Tea"]);
    expect(result[0].supporting_document_ids).toEqual([docA]);
  });

  it("drops an unedited candidate the server withheld because its only document failed", () => {
    const existing = [
      offering({ name: "Bowl", supporting_document_ids: [docA], candidate_id: "c1" }),
    ];
    const result = reconcileAfterSave(existing, [], [record({ id: docA })], new Set());
    expect(result).toEqual([]);
  });

  it("orphans an edited candidate the server withheld, keeping the owner's work", () => {
    const existing = [
      offering({ name: "Bowl", supporting_document_ids: [docA], candidate_id: "c1" }),
    ];
    const result = reconcileAfterSave(existing, [], [record({ id: docA })], new Set(["c1"]));
    expect(result).toHaveLength(1);
    expect(result[0].support_state).toBe("orphaned");
    expect(result[0].supporting_document_ids).toEqual([]);
  });

  it("keeps an owner row untouched when no document supported it", () => {
    const existing = [offering({ name: "Tea", sources: ["owner"], candidate_id: "c1" })];
    const result = reconcileAfterSave(existing, [], [record({ id: docA })], new Set());
    expect(result).toEqual([existing[0]]);
  });

  it("keeps a row still backed by a surviving document when its other document publishes", () => {
    const existing = [
      offering({
        name: "Bowl",
        supporting_document_ids: [docA, docB],
        candidate_id: "c1",
      }),
    ];
    const result = reconcileAfterSave(existing, [], [record({ id: docA })], new Set());
    expect(result).toHaveLength(1);
    expect(result[0].supporting_document_ids).toEqual([docB]);
    expect(result[0].support_state).toBe("supported");
  });
});

describe("mergeIncomingCandidates", () => {
  it("appends new rows in record order after the existing list", () => {
    const existing = [offering({ name: "Tea", sources: ["owner"] })];
    const records = [
      record({ id: "d1", offering_candidates: [offering({ name: "Bowl" })] }),
      record({ id: "d2", offering_candidates: [offering({ name: "Falafel" })] }),
    ];
    const result = mergeIncomingCandidates(existing, records);
    expect(result.map((item) => item.name)).toEqual(["Tea", "Bowl", "Falafel"]);
  });

  it("merges a name-matched candidate into the existing position with document content winning", () => {
    const existing = [
      offering({
        name: "Bowl",
        price_cents: 1000,
        sources: ["owner"],
        candidate_id: "owner-1",
      }),
    ];
    const records = [
      record({
        id: "d1",
        offering_candidates: [
          offering({
            name: "Bowl",
            price_cents: 1500,
            description: "lamb bowl",
            supporting_document_ids: ["d1"],
          }),
        ],
      }),
    ];
    const result = mergeIncomingCandidates(existing, records);
    expect(result).toHaveLength(1);
    expect(result[0].price_cents).toBe(1500);
    expect(result[0].description).toBe("lamb bowl");
    expect(result[0].sources).toEqual(["owner", "document"]);
    expect(result[0].supporting_document_ids).toEqual(["d1"]);
  });

  it("leaves unrelated rows untouched", () => {
    const existing = [offering({ name: "Tea", sources: ["owner"], candidate_id: "c1" })];
    const result = mergeIncomingCandidates(existing, [
      record({ id: "d1", offering_candidates: [offering({ name: "Bowl" })] }),
    ]);
    expect(result[0]).toEqual(existing[0]);
  });
});

describe("offeringLabel", () => {
  const documents = [
    record({ id: "d1", filename: "notes.txt" }),
    record({ id: "d2", filename: "menu.pdf" }),
  ];

  it("labels an orphaned offering as replaced", () => {
    expect(
      offeringLabel(
        offering({ support_state: "orphaned", supporting_document_ids: ["d1"] }),
        documents,
      ),
    ).toBe("From a replaced source");
  });

  it("labels owner rows Owner, with or without a document", () => {
    expect(offeringLabel(offering({ sources: ["owner"] }), documents)).toBe("Owner");
    expect(
      offeringLabel(
        offering({ sources: ["owner", "document"], supporting_document_ids: ["d1"] }),
        documents,
      ),
    ).toBe("Owner");
  });

  it("joins the supporting filenames for a document row", () => {
    expect(
      offeringLabel(
        offering({ sources: ["document"], supporting_document_ids: ["d1", "d2"] }),
        documents,
      ),
    ).toBe("From notes.txt, menu.pdf");
  });

  it("falls back to From document for a legacy row without supporting ids", () => {
    expect(offeringLabel(offering({ sources: ["document"] }), documents)).toBe("From document");
  });
});

describe("buildWorkspace", () => {
  it("defaults the id to a fresh uuid", () => {
    const ws = buildWorkspace([record({ id: "d1" })], []);
    expect(ws.id).toBeTruthy();
    expect(ws.documents.map((doc) => doc.id)).toEqual(["d1"]);
    expect(ws.offering_candidates).toEqual([]);
  });

  it("accepts a caller-provided id and builds candidates via withCombinedOfferings", () => {
    const owner: PendingOffering[] = [
      { name: "Tea", description: "", price_cents: 200, sources: ["owner"] },
    ];
    const ws = buildWorkspace(
      [record({ id: "d1", offering_candidates: [offering({ name: "Bowl" })] })],
      owner,
      "stable-id",
    );
    expect(ws.id).toBe("stable-id");
    expect(ws.offering_candidates.map((item) => item.name)).toEqual(["Tea", "Bowl"]);
  });
});