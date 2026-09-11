import type { KnowledgeRecord, PendingOffering, ReviewOffering, ReviewWorkspace } from "./types";
import { sourceLabel } from "./types";

/**
 * The offering merge and lifecycle policies, client-side twins of
 * backend/app/onboarding/flow.py. Pure functions - no React, no network - so
 * every rule is unit-testable. Where a policy mirrors the server, a one-line
 * comment names the twin.
 */

export function normalizeOfferingName(value: string): string {
  return value
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[\p{P}]/gu, " ")
    .replace(/\s+/g, " ");
}

/** Combine two candidates for the same offering, document values winning.
 *  Mirrors flow.py merge_offerings: the document wins name, price and
 *  description; sources and supporting_document_ids union; conflicting prices
 *  become `price_options` instead of one of them quietly winning. */
export function mergeOffering(existing: ReviewOffering, incoming: ReviewOffering): ReviewOffering {
  const document = [existing, incoming].find((item) => item.sources.includes("document"));
  const preferred = document ? [document, existing, incoming] : [existing, incoming];
  const priceCents = preferred.find((item) => item.price_cents != null)?.price_cents ?? null;
  const description = preferred.find((item) => item.description)?.description ?? "";
  const offered = [existing.price_cents, incoming.price_cents].filter(
    (price): price is number => price != null,
  );
  const conflicting = [...new Set([...offered, ...(existing.price_options ?? []), ...(incoming.price_options ?? [])])].sort((left, right) => left - right);
  return {
    ...incoming,
    name: document?.name ?? existing.name,
    candidate_id: document?.candidate_id ?? existing.candidate_id,
    description,
    price_cents: priceCents,
    sources: [...new Set([...existing.sources, ...incoming.sources])],
    supporting_document_ids: [...new Set([...(existing.supporting_document_ids ?? []), ...(incoming.supporting_document_ids ?? [])])],
    support_state: "supported",
    price_options: conflicting.length > 1 ? conflicting : undefined,
  };
}

/** Owner-typed offerings unioned with every document's candidates, for review.
 *  Owner rows first (insertion order), then document-only rows in record/upload
 *  order; merged rows keep the owner position. Run ONCE per workspace build,
 *  never per draft. */
export function withCombinedOfferings(
  records: KnowledgeRecord[],
  ownerOfferings: PendingOffering[],
): ReviewOffering[] {
  const merged = new Map<string, ReviewOffering>();
  for (const item of ownerOfferings) merged.set(normalizeOfferingName(item.name), { ...item });
  for (const record of records) {
    for (const item of record.offering_candidates ?? []) {
      const key = normalizeOfferingName(item.name);
      const owner = merged.get(key);
      merged.set(key, owner ? mergeOffering(owner, item) : { ...item });
    }
  }
  return [...merged.values()];
}

/** Which offerings survive when the owner replaces one source document.
 *  Mirrors flow.py reconcile_replacement: matched names merge; unedited
 *  doc-only candidates drop; edited ones orphan (`support_state: "orphaned"`);
 *  owner/other-doc-backed survive; the owner source is stripped when a merged
 *  row's only document support came from the replaced document; unmatched
 *  incoming candidates are appended at the end. */
export function reconcileOfferings(
  existing: ReviewOffering[],
  incoming: ReviewOffering[],
  replacedDocumentId: string,
  editedCandidateIds: Set<string>,
): ReviewOffering[] {
  function withoutReplacedDocument(item: ReviewOffering): ReviewOffering {
    const supporting = item.supporting_document_ids ?? [];
    if (!supporting.includes(replacedDocumentId)) return item;
    return {
      ...item,
      supporting_document_ids: supporting.filter((id) => id !== replacedDocumentId),
    };
  }
  const incomingByKey = new Map(
    incoming.map((item) => [normalizeOfferingName(item.name), withoutReplacedDocument(item)]),
  );
  const matched = new Set<string>();
  const survivors: ReviewOffering[] = [];

  for (const item of existing) {
    const key = normalizeOfferingName(item.name);
    const match = incomingByKey.get(key);
    const supporting = item.supporting_document_ids ?? [];
    const hadOnlyReplacedSupport =
      supporting.length === 1 && supporting[0] === replacedDocumentId;
    let current = withoutReplacedDocument(item);
    if (current.sources.includes("owner") && hadOnlyReplacedSupport) {
      current = {
        ...current,
        sources: current.sources.filter((source) => source !== "document"),
      };
    }
    if (match) {
      matched.add(key);
      survivors.push(mergeOffering(current, match));
      continue;
    }
    if (
      hadOnlyReplacedSupport &&
      !current.sources.includes("owner") &&
      !editedCandidateIds.has(current.candidate_id ?? "")
    ) {
      continue;
    }
    if (hadOnlyReplacedSupport && !current.sources.includes("owner")) {
      current = { ...current, support_state: "orphaned" };
    }
    survivors.push(current);
  }

  for (const [key, item] of incomingByKey) {
    if (!matched.has(key)) survivors.push(item);
  }
  return survivors;
}

/** W-11c: adopt the server's candidates after a batch save. Every submitted
 *  document counts as replaced - the ones that published left the review, and
 *  the ones that hard-failed lost their candidates server-side - so one
 *  reconcileOfferings pass runs per submitted document. Rows the server kept
 *  merge by name; rows it withheld (support confined to a hard-failed
 *  document) drop unless the owner edited them, in which case they orphan so
 *  the edit survives. Mirrors the candidate filter in flow.py
 *  save_onboarding_knowledge_batch plus the client-side edit protection. */
export function reconcileAfterSave(
  existing: ReviewOffering[],
  incoming: ReviewOffering[],
  submittedDocuments: KnowledgeRecord[],
  editedCandidateIds: Set<string>,
): ReviewOffering[] {
  let next = existing;
  for (const document of submittedDocuments) {
    next = reconcileOfferings(next, incoming, document.id, editedCandidateIds);
  }
  return next;
}

/** W-11c: fold newly added documents' candidates into the live review list
 *  without disturbing it. Name-matched rows merge in place (the same
 *  mergeOffering policy as the workspace build - document content wins,
 *  sources and supporting ids union), unmatched rows append in record order.
 *  Position is preserved for matched rows, which lets the sheet keep its
 *  dirty marks by index. */
export function mergeIncomingCandidates(
  existing: ReviewOffering[],
  records: KnowledgeRecord[],
): ReviewOffering[] {
  const next = [...existing];
  for (const record of records) {
    for (const item of record.offering_candidates ?? []) {
      const key = normalizeOfferingName(item.name);
      const index = next.findIndex(
        (candidate) => normalizeOfferingName(candidate.name) === key,
      );
      if (index >= 0) next[index] = mergeOffering(next[index], item);
      else next.push(item);
    }
  }
  return next;
}

/** The source line on an offering card: orphaned rows explain themselves,
 *  owner rows are the owner's own words, document rows name their files. */
export function offeringLabel(offering: PendingOffering, documents: KnowledgeRecord[]): string {
  if (offering.support_state === "orphaned") return "From a replaced source";
  if (offering.sources.includes("owner")) return "Owner";
  const supporting = (offering.supporting_document_ids ?? [])
    .map((id) => documents.find((doc) => doc.id === id))
    .filter((doc): doc is KnowledgeRecord => Boolean(doc))
    .map(sourceLabel);
  return supporting.length ? `From ${supporting.join(", ")}` : "From document";
}

/** Build a review workspace. Callers pass the previous id on rebuilds so the
 *  sheet stays mounted across close/reopen and rebuilds-after-save; the id
 *  defaults to a fresh uuid when the workspace first comes into being. */
export function buildWorkspace(
  documents: KnowledgeRecord[],
  ownerOfferings: PendingOffering[],
  id?: string,
): ReviewWorkspace {
  return {
    id: id ?? crypto.randomUUID(),
    documents,
    offering_candidates: withCombinedOfferings(documents, ownerOfferings),
  };
}