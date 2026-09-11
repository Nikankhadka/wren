"use client";

import { useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { offeringLabel } from "./offerings";
import type { KnowledgeRecord, KnowledgeSection, PendingOffering, ReviewOffering, ReviewWorkspace, SourceDetail } from "./types";
import { sourceLabel } from "./types";

const PAGE_SIZE = 5;
const SECTION_ORDER = ["business_overview", "hours", "location", "other"] as const;

interface WorkingOffering extends Omit<PendingOffering, "candidate_id"> {
  candidate_id: string;
  priceText: string;
  priceOptions: number[];
  priceNote: string;
  possibleMatches: string[];
  support_state: "supported" | "orphaned";
  /** W-11c: any user edit/add/combine marks the row dirty; stripped before save. */
  dirty: boolean;
}

export function toWorkingOffering(item: ReviewOffering): WorkingOffering {
  return {
    ...item,
    candidate_id: item.candidate_id ?? legacyId(item.name),
    description: item.description ?? "",
    sources: item.sources ?? ["owner"],
    source_references: item.source_references ?? [],
    priceText: item.price_cents == null ? "" : formatPrice(item.price_cents),
    priceOptions: item.price_options ?? [],
    priceNote: item.needs_review ? (item.price_note ?? "") : "",
    possibleMatches: item.possible_matches ?? [],
    support_state: item.support_state ?? "supported",
    dirty: false,
  };
}

export interface ReviewSheetProps {
  workspace: ReviewWorkspace | null;
  open: boolean;
  busy: boolean;
  priceConflict: string | null;
  onboarding?: boolean;
  onClose: () => void;
  /** W-11c: resolves with the candidates to adopt after a batch save, or null
   *  when the caller keeps its current flow. The sheet adopts the resolved
   *  list and never re-syncs from the workspace after mount. */
  onSave: (documents: { document_id: string; sections: KnowledgeSection[] }[], offerings: PendingOffering[], acceptPriceChanges?: boolean) => Promise<PendingOffering[] | null>;
  onDiscard: () => void;
  // W-11c: onboarding-only source actions, wired up in a later phase.
  onAddSource?: (files: File[]) => Promise<KnowledgeRecord[]>;
  onReplaceSource?: (documentId: string, file: File) => Promise<KnowledgeRecord | null>;
  onRemoveSource?: (documentId: string) => Promise<void>;
}

export function ReviewSheet({ workspace, open, busy, priceConflict, onboarding = false, onClose, onSave, onDiscard }: ReviewSheetProps) {
  return <Sheet open={open} onClose={onClose} desktop title={onboarding ? "Review your information" : workspace?.documents[0]?.status === "draft" ? "Read this back" : "Edit what I know"}>
    {workspace ? <ReviewDocument key={workspace.id} workspace={workspace} busy={busy} priceConflict={priceConflict} onboarding={onboarding} onSave={onSave} onDiscard={onDiscard} /> : null}
  </Sheet>;
}

function ReviewDocument({ workspace, busy, priceConflict, onboarding, onSave, onDiscard }: { workspace: ReviewWorkspace; busy: boolean; priceConflict: string | null; onboarding: boolean; onSave: ReviewSheetProps["onSave"]; onDiscard: () => void }) {
  // W-11c: the sheet reviews several documents together; this phase always has
  // exactly one, so everything below routes through `record` = documents[0].
  const record = workspace.documents[0];
  const [sectionsByDocument, setSectionsByDocument] = useState<Map<string, KnowledgeSection[]>>(() => new Map([[record.id, orderedSections(record.sections)]]));
  const sections = sectionsByDocument.get(record.id) ?? [];
  const [offerings, setOfferings] = useState(() => (record.offering_candidates ?? []).map(toWorkingOffering));
  const [expanded, setExpanded] = useState(offerings.length <= PAGE_SIZE);
  const [page, setPage] = useState(0);
  const [editingSection, setEditingSection] = useState<number | null>(null);
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [combine, setCombine] = useState<{ left: string; right: string; price: number | null } | null>(null);
  const cardRefs = useRef(new Map<string, HTMLInputElement>());
  const pages = offeringPageCount(offerings.length);
  const currentPage = Math.min(page, pages - 1);
  const visible = expanded ? offeringPage(offerings, currentPage) : offerings.slice(0, PAGE_SIZE);
  const duplicateIds = duplicateOfferingIds(offerings);
  const unresolvedMatches = offerings.reduce((total, item) => total + item.possibleMatches.filter((id) => offerings.some((other) => other.candidate_id === id)).length, 0) / 2;

  function updateSections(docId: string, update: (previous: KnowledgeSection[]) => KnowledgeSection[]) {
    setSectionsByDocument((previous) => {
      const next = new Map(previous);
      next.set(docId, update(next.get(docId) ?? []));
      return next;
    });
  }
  function updateOffering(id: string, update: Partial<WorkingOffering>) {
    setOfferings((previous) => previous.map((item) => item.candidate_id === id ? { ...item, ...update } : item));
  }
  function removeOffering(id: string) { setOfferings((previous) => previous.filter((item) => item.candidate_id !== id)); }
  function addOffering() {
    const candidate_id = `owner_${crypto.randomUUID()}`;
    setOfferings((previous) => {
      const next = [...previous, { candidate_id, name: "", description: "", price_cents: null, sources: ["owner"] as ("owner" | "document")[], source_references: [], priceText: "", priceOptions: [], priceNote: "", possibleMatches: [], support_state: "supported" as const, dirty: false }];
      setExpanded(true); setPage(Math.floor((next.length - 1) / PAGE_SIZE)); return next;
    });
    requestAnimationFrame(() => cardRefs.current.get(candidate_id)?.focus());
  }
  function keepBoth(left: string, right: string) {
    setOfferings((previous) => previous.map((item) => item.candidate_id === left || item.candidate_id === right ? { ...item, possibleMatches: item.possibleMatches.filter((id) => id !== left && id !== right) } : item));
  }
  function applyCombine() {
    if (!combine) return;
    const left = offerings.find((item) => item.candidate_id === combine.left);
    const right = offerings.find((item) => item.candidate_id === combine.right);
    if (!left || !right) return;
    const retained = left.sources.includes("owner") ? left : right.sources.includes("owner") ? right : left;
    const removed = retained === left ? right : left;
    const prices = [left.price_cents, right.price_cents].filter((price): price is number => price != null);
    if (new Set(prices).size > 1 && combine.price == null) return;
    const price = combine.price ?? retained.price_cents ?? removed.price_cents;
    setOfferings((previous) => previous.filter((item) => item.candidate_id !== removed.candidate_id).map((item) => item.candidate_id !== retained.candidate_id ? item : { ...retained, price_cents: price, priceText: formatPrice(price), description: retained.description || removed.description, sources: [...new Set([...retained.sources, ...removed.sources])], source_references: [...(retained.source_references ?? []), ...(removed.source_references ?? [])], possibleMatches: [...new Set([...retained.possibleMatches, ...removed.possibleMatches])].filter((id) => id !== retained.candidate_id && id !== removed.candidate_id), dirty: true }));
    setCombine(null);
  }
  async function save() {
    if (duplicateIds.length) {
      const target = offerings.find((item) => duplicateIds.includes(item.candidate_id));
      if (target) { setExpanded(true); setPage(Math.floor(offerings.indexOf(target) / PAGE_SIZE)); requestAnimationFrame(() => cardRefs.current.get(target.candidate_id)?.focus()); }
      return;
    }
    const adopted = await onSave([{ document_id: record.id, sections }], offerings.filter((item) => item.name.trim()).map(toPendingOffering), priceConflict !== null);
    if (adopted) setOfferings(adopted.map(toWorkingOffering));
  }
  async function loadSource() { if (source || sourceLoading) return; setSourceLoading(true); try { setSource(await apiFetch<SourceDetail>(`/api/knowledge/records/${record.id}/source`)); } finally { setSourceLoading(false); } }

  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="min-h-0 flex-1 overflow-y-auto pb-4">
      <p className="text-meta text-ink-a40">{onboarding ? `Here's what I found in ${sourceLabel(record)}. Review it before you use it.` : `From ${sourceLabel(record)}. Your assistant answers from the reviewed facts below.`}</p>
      <section className="mt-5"><h3 className="text-row-label font-medium text-text">Offerings</h3><p className="mt-1 text-meta text-ink-a40">{offerings.length} retained {offerings.length === 1 ? "offering" : "offerings"}{unresolvedMatches ? `, ${unresolvedMatches} possible ${unresolvedMatches === 1 ? "match" : "matches"} left to decide` : ""}.</p>
        {record.extraction_status === "partial" || record.extraction_status === "failed" ? <p role="status" className="mt-3 rounded-field bg-warning-subtle p-2 text-meta text-text">{record.extraction_status === "failed" ? "I could not read the offerings from this source." : "I could not read all of this source."} Add anything missing, or check the original source.</p> : null}
        {offerings.length === 0 ? <p className="mt-3 rounded-field bg-surface-container p-3 text-prose text-text">No offerings yet.</p> : null}
        <div className="mt-3 flex flex-col gap-3">{visible.map((offering, index) => <OfferingCard key={offering.candidate_id} offering={offering} documents={workspace.documents} position={(expanded ? currentPage * PAGE_SIZE : 0) + index + 1} all={offerings} editing={expanded} inputRef={(node) => { if (node) cardRefs.current.set(offering.candidate_id, node); }} onChange={updateOffering} onRemove={removeOffering} onKeepBoth={keepBoth} onCombine={(left, right) => setCombine({ left, right, price: null })} />)}</div>
        {!expanded && offerings.length > PAGE_SIZE ? <button type="button" onClick={() => setExpanded(true)} className="mt-3 text-action font-medium text-accent">Review all {offerings.length}</button> : null}
        {expanded && offerings.length <= PAGE_SIZE ? <p className="mt-3 text-action font-medium text-accent">Edit offerings</p> : null}
        {expanded && offerings.length > PAGE_SIZE ? <Pagination page={currentPage} pages={pages} count={offerings.length} onPage={setPage} /> : null}
        <button type="button" onClick={addOffering} className="mt-3 text-action font-medium text-accent">Add offering</button>
        {duplicateIds.length ? <p role="alert" className="mt-2 text-meta text-danger">Two retained offerings have the same name. Go to the highlighted offering to correct it.</p> : null}
      </section>
      {sections.length ? <section className="mt-7"><h3 className="text-row-label font-medium text-text">Business information</h3><KnowledgeDocument sections={sections} editingSection={editingSection} onEdit={setEditingSection} onChange={(index, update) => updateSections(record.id, (previous) => previous.map((section, position) => position === index ? { ...section, ...update } : section))} onRemove={(index) => updateSections(record.id, (previous) => previous.filter((_, position) => position !== index))} onAddOther={() => { updateSections(record.id, (previous) => [...previous, { heading: "New information", body: "", kind: "other" }]); setEditingSection(sections.length); }} /></section> : null}
      <details className="mt-7 rounded-card border border-hairline p-3" onToggle={(event) => { if ((event.currentTarget as HTMLDetailsElement).open) void loadSource(); }}><summary className="cursor-pointer text-action font-medium text-accent">View original source</summary>{sourceLoading ? <p className="mt-3 text-meta text-ink-a40">Loading source…</p> : null}{source ? <><p className="mt-3 text-meta text-ink-a40">{source.is_fallback ? "This legacy source only retains its saved reviewed text." : "Original extracted source. It does not answer customers."}</p><pre className="mt-3 whitespace-pre-wrap break-words font-sans text-prose text-text">{source.text}</pre></> : null}</details>
    </div>
    {combine ? <CombinePreview combine={combine} offerings={offerings} onPrice={(price) => setCombine({ ...combine, price })} onCancel={() => setCombine(null)} onConfirm={applyCombine} /> : null}
    {priceConflict ? <p role="alert" className="mt-3 rounded-card bg-accent-a06 p-3 text-meta text-text">{priceConflict}</p> : null}
    <footer className="mt-3 flex shrink-0 gap-2 border-t border-hairline pt-3"><Button className="flex-1" loading={busy} onClick={save} data-testid={onboarding ? "onboarding-knowledge-save" : "knowledge-save"}>{onboarding ? "Use this information" : priceConflict ? "Confirm price changes" : record.status === "draft" ? "Save it" : "Save changes"}</Button><button type="button" onClick={onDiscard} disabled={busy} className="px-3 text-action font-medium text-ink-a40" data-testid={onboarding ? "onboarding-knowledge-discard" : "knowledge-discard"}>{onboarding || record.status === "draft" ? "Discard" : "Remove"}</button></footer>
  </div>;
}

function OfferingCard({ offering, documents, position, all, editing, inputRef, onChange, onRemove, onKeepBoth, onCombine }: { offering: WorkingOffering; documents: KnowledgeRecord[]; position: number; all: WorkingOffering[]; editing: boolean; inputRef: (node: HTMLInputElement | null) => void; onChange: (id: string, update: Partial<WorkingOffering>) => void; onRemove: (id: string) => void; onKeepBoth: (left: string, right: string) => void; onCombine: (left: string, right: string) => void }) {
  const matches = all.filter((item) => offering.possibleMatches.includes(item.candidate_id));
  return <article className={`rounded-card border p-3 ${matches.length ? "border-accent-a35 bg-accent-a06" : "border-hairline bg-surface-container"}`}><div className="flex items-start justify-between gap-2"><span className="text-meta text-ink-a40">{offeringLabel(offering, documents)}{offering.source_references?.length ? ` · ${offering.source_references.length} source ${offering.source_references.length === 1 ? "reference" : "references"}` : ""}</span>{editing ? <button type="button" onClick={() => onRemove(offering.candidate_id)} className="text-action text-ink-a40">Remove</button> : null}</div>
    {editing ? <><div className="mt-2 flex gap-2"><input ref={inputRef} value={offering.name} aria-label={`Offering ${position} name`} placeholder="Offering" onChange={(event) => onChange(offering.candidate_id, { name: event.target.value })} className="min-w-0 flex-1 rounded-field bg-surface px-3 py-2 text-field text-text outline-none focus:ring-2 focus:ring-accent-a35" /><input value={offering.priceText} aria-label={`Offering ${position} price`} placeholder="Price" inputMode="decimal" onChange={(event) => onChange(offering.candidate_id, { priceText: event.target.value, priceOptions: [] })} className="w-24 rounded-field bg-surface px-3 py-2 text-field text-text outline-none focus:ring-2 focus:ring-accent-a35" /></div><textarea value={offering.description} aria-label={`Offering ${position} description`} placeholder="Description (optional)" rows={2} onChange={(event) => onChange(offering.candidate_id, { description: event.target.value })} className="mt-2 w-full resize-y rounded-field bg-surface px-3 py-2 text-field text-text outline-none focus:ring-2 focus:ring-accent-a35" /></> : <><div className="mt-2 flex justify-between gap-3"><h4 className="text-row-label font-medium text-text">{offering.name}</h4><span className="shrink-0 text-row-label text-text">{offering.priceText || "Price not set"}</span></div>{offering.description ? <p className="mt-1 whitespace-pre-line text-prose text-text">{offering.description}</p> : null}</>}
    {offering.priceNote ? <p className="mt-2 rounded-field bg-warning-subtle p-2 text-meta text-text">Check this price: {offering.priceNote}</p> : null}
    {offering.priceOptions.length > 1 ? <div role="alert" className="mt-2 text-meta text-text">Choose a price: {offering.priceOptions.map((price) => <button key={price} type="button" onClick={() => onChange(offering.candidate_id, { price_cents: price, priceText: formatPrice(price), priceOptions: [] })} className="ml-2 text-action text-accent">Use {formatPrice(price)}</button>)}</div> : null}
    {matches.map((match) => <div key={match.candidate_id} className="mt-3 text-meta text-text"><p>This may be the same offering as <strong>{match.name}</strong>. Both remain separate until you decide.</p><div className="mt-2 flex gap-3"><button type="button" onClick={() => onCombine(offering.candidate_id, match.candidate_id)} className="text-action font-medium text-accent">Combine</button><button type="button" onClick={() => onKeepBoth(offering.candidate_id, match.candidate_id)} className="text-action text-ink-a40">Keep both</button></div></div>)}</article>;
}

export function KnowledgeDocument({ sections, editingSection = null, onEdit, onChange, onRemove, onAddOther }: { sections: KnowledgeSection[]; editingSection?: number | null; onEdit?: (index: number | null) => void; onChange?: (index: number, update: Partial<KnowledgeSection>) => void; onRemove?: (index: number) => void; onAddOther?: () => void }) {
  return <div className="mt-3 flex flex-col gap-4">{sections.map((section, index) => <section key={`${section.kind}-${section.heading}-${index}`} className="rounded-card border border-hairline p-3"><div className="flex items-center justify-between gap-3">{editingSection === index ? <input value={section.heading} aria-label="Section heading" onChange={(event) => onChange?.(index, { heading: event.target.value })} className="min-w-0 rounded-field bg-surface-container px-2 py-1 text-row-label font-medium text-text" /> : <h4 className="text-field-label font-medium uppercase text-ink-a40">{section.heading}</h4>}{onEdit ? <div className="flex gap-3"><button type="button" onClick={() => onEdit(editingSection === index ? null : index)} className="text-action text-accent">{editingSection === index ? "Done" : "Edit"}</button>{section.kind === "other" ? <button type="button" onClick={() => onRemove?.(index)} className="text-action text-ink-a40">Remove</button> : null}</div> : null}</div>{editingSection === index ? <textarea value={section.body} rows={4} aria-label={`${section.heading} details`} onChange={(event) => onChange?.(index, { body: event.target.value })} className="mt-2 w-full resize-y rounded-field bg-surface-container px-3 py-2 text-field text-text outline-none focus:ring-2 focus:ring-accent-a35" /> : <FormattedBody body={section.body} />}</section>)}{onAddOther ? <button type="button" onClick={onAddOther} className="text-left text-action font-medium text-accent">Add other information</button> : null}</div>;
}

function FormattedBody({ body }: { body: string }) { return <div className="mt-2 whitespace-pre-line break-words text-prose text-text">{body.split("\n").map((line, index) => line.startsWith("- ") || line.startsWith("• ") ? <div key={index} className="pl-4 before:mr-2 before:content-['•']">{line.slice(2)}</div> : <p key={index} className={line ? "" : "h-3"}>{line}</p>)}</div>; }
function CombinePreview({ combine, offerings, onPrice, onCancel, onConfirm }: { combine: { left: string; right: string; price: number | null }; offerings: WorkingOffering[]; onPrice: (price: number) => void; onCancel: () => void; onConfirm: () => void }) { const pair = offerings.filter((item) => item.candidate_id === combine.left || item.candidate_id === combine.right); const retained = pair.find((item) => item.sources.includes("owner")) ?? pair[0]; const prices = [...new Set(pair.map((item) => item.price_cents).filter((price): price is number => price != null))]; if (!retained) return null; return <section className="mt-3 rounded-card border border-accent-a35 bg-accent-a06 p-3"><h3 className="text-row-label font-medium text-text">Combine offerings</h3><p className="mt-1 text-meta text-text">This keeps {retained.name}, {retained.description || "the available description"}, and {prices.length > 1 ? "the price you choose" : retained.priceText || "no price"}. Source evidence is combined.</p>{prices.length > 1 ? <div className="mt-2"><p className="text-meta text-text">Choose the retained price.</p>{prices.map((price) => <button key={price} type="button" onClick={() => onPrice(price)} className={`mr-2 mt-2 rounded-full border px-3 py-1 text-action ${combine.price === price ? "border-accent bg-accent text-text-inverse" : "border-accent-a35 text-accent"}`}>{formatPrice(price)}</button>)}</div> : null}<div className="mt-3 flex gap-3"><button type="button" onClick={onConfirm} disabled={prices.length > 1 && combine.price == null} className="text-action font-medium text-accent disabled:opacity-50">Confirm combine</button><button type="button" onClick={onCancel} className="text-action text-ink-a40">Cancel</button></div></section>; }
function Pagination({ page, pages, count, onPage }: { page: number; pages: number; count: number; onPage: (page: number) => void }) { return <div className="mt-4 flex items-center justify-between text-meta text-text"><button type="button" disabled={page === 0} onClick={() => onPage(page - 1)} className="text-action text-accent disabled:opacity-40">Previous</button><span>Offerings {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, count)} of {count}</span><button type="button" disabled={page === pages - 1} onClick={() => onPage(page + 1)} className="text-action text-accent disabled:opacity-40">Next</button></div>; }
export function offeringPageCount(count: number) { return Math.max(1, Math.ceil(count / PAGE_SIZE)); }
export function offeringPage<T>(offerings: T[], page: number) { return offerings.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE); }
export function pageForOffering(index: number) { return Math.max(0, Math.floor(index / PAGE_SIZE)); }
function orderedSections(sections: KnowledgeSection[]) { return [...sections].filter((section) => section.body.trim()).sort((left, right) => SECTION_ORDER.indexOf(left.kind ?? "other") - SECTION_ORDER.indexOf(right.kind ?? "other")); }
function duplicateOfferingIds(offerings: WorkingOffering[]) { const seen = new Map<string, string>(); const duplicates: string[] = []; for (const item of offerings) { const key = item.name.normalize("NFKC").trim().toLowerCase(); if (key && seen.has(key)) duplicates.push(item.candidate_id); else if (key) seen.set(key, item.candidate_id); } return duplicates; }
function legacyId(name: string) { return `legacy_${name.normalize("NFKC").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-")}`; }
function toPendingOffering(item: WorkingOffering): PendingOffering {
  // Strips the WorkingOffering-only fields (priceText, priceOptions, priceNote,
  // possibleMatches, dirty) before the row goes over the wire.
  return {
    candidate_id: item.candidate_id,
    name: item.name.trim(),
    description: item.description,
    price_cents: parsePriceCents(item.priceText),
    sources: item.sources,
    source_references: item.source_references,
    supporting_document_ids: item.supporting_document_ids,
    support_state: item.support_state,
    price_note: item.priceNote,
    needs_review: item.needs_review,
    possible_matches: item.possibleMatches,
    price_options: item.priceOptions,
  };
}
function formatPrice(cents: number | null) { return cents == null ? "" : `$${(cents / 100).toFixed(2)}`; }
function parsePriceCents(value: string) { const normalized = value.trim().replace(/[ $,]/g, ""); if (!normalized || !/^\d+(?:\.\d{1,2})?$/.test(normalized)) return null; const [dollars, cents = ""] = normalized.split("."); return Number(dollars) * 100 + Number(`${cents}00`.slice(0, 2)); }
