export interface KnowledgeSection {
  heading: string;
  body: string;
  kind?: "business_overview" | "hours" | "location" | "other";
}

export interface SourceReference {
  block: string;
  excerpt: string;
  supported_fields: ("name" | "description" | "price")[];
}

export interface PendingOffering {
  candidate_id?: string;
  name: string;
  description: string;
  price_cents: number | null;
  sources: ("owner" | "document")[];
  source_references?: SourceReference[];
  /** W-11: the documents this candidate depends on. Empty for an owner-typed
   *  candidate - that emptiness is meaningful, it says the candidate depends on
   *  no document and must survive any document being replaced. */
  supporting_document_ids?: string[];
  /** W-11: set only by reconcileOfferings, when a document that supported this
   *  candidate was replaced but the owner had already edited it. No owner-facing
   *  wording lives here - the review UI renders that. */
  support_state?: "supported" | "orphaned";
  /** W-6: the source's own wording for a price the row cannot hold - a range, a
   *  "from" price, a rate - shown instead of a number picked out of it. */
  price_note?: string;
  /** W-6: this candidate needs a decision before it is right. */
  needs_review?: boolean;
  /** W-8: ids that might be this same item, never merged automatically. */
  possible_matches?: string[];
  /** W-6: competing amounts when two sources price one item differently. */
  price_options?: number[];
}

/** W-6: the server sends the full shape now - the merge that used to add
 *  `price_options` in the browser (with the opposite precedence to the server's)
 *  was deleted in favour of one policy in `merge_offerings`. */
export type ReviewOffering = PendingOffering;

/** How completely the document could be read. `partial` and `failed` mean the
 *  list below is not the whole document, and the sections are the route back to
 *  the source. */
export type ExtractionStatus = "full" | "partial" | "failed" | "pending";

export interface KnowledgeRecord {
  id: string;
  filename: string;
  doc_type: string;
  status: string;
  error: string | null;
  sections: KnowledgeSection[];
  offering_candidates?: ReviewOffering[];
  extraction_status?: ExtractionStatus;
  // W-11a: where ingest stopped when this document failed, and whether retrying
  // is possible. Mirrors the generated api-types.ts shape.
  failure_stage?: "structure" | "extract" | "embed" | null;
  failure_retryable?: boolean | null;
  failed_at?: string | null;
}

// W-11b: separates "which documents' edit state is loaded" from "is the sheet
// currently visible" - see ReviewSheet.tsx. The sheet is keyed by
// `workspace.id` - one mount across all of the documents reviewed together.
// The id must be STABLE across close/reopen and rebuilds-after-save (W-11b
// retention); it dies only when workspace goes to null.
export interface ReviewWorkspace {
  id: string;
  documents: KnowledgeRecord[];
  offering_candidates: ReviewOffering[];
  /** W-11c: per-document save failures, keyed by document id. */
  errors?: Record<string, string>;
}

export interface SourceDetail {
  text: string;
  is_fallback: boolean;
}

export function sourceLabel(record: KnowledgeRecord): string {
  if (!record.filename.startsWith("http")) return record.filename;
  try {
    return new URL(record.filename).host;
  } catch {
    return record.filename;
  }
}

export function statusLine(record: KnowledgeRecord): string {
  if (record.status === "draft") return "Not saved yet";
  if (record.status === "failed") return record.error ?? "Something went wrong";
  if (record.status === "ready") return "Answering from this";
  return "Working on it";
}
