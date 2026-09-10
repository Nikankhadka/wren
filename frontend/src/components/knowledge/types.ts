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
}

// W-11b: separates "which document's edit state is loaded" from "is the sheet
// currently visible" - see ReviewSheet.tsx. A type alias for now; W-11c
// extends this to represent several documents reviewed together, at which
// point ReviewSheet's `key={workspace.id}` becomes one mount across all of
// them instead of one per document.
export type ReviewWorkspace = KnowledgeRecord;

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
