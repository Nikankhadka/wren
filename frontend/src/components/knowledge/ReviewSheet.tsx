"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { apiFetch } from "@/lib/api";
import { ACCEPTED_UPLOAD_EXTENSIONS } from "@/lib/onboarding";
import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import type { ConfirmOptions } from "@/components/ui/ConfirmDialog";
import {
  mergeIncomingCandidates,
  offeringLabel,
  reconcileAfterSave,
  reconcileOfferings,
} from "./offerings";
import type { KnowledgeRecord, KnowledgeSection, PendingOffering, ReviewOffering, ReviewWorkspace, SourceDetail } from "./types";
import { sourceLabel } from "./types";

const PAGE_SIZE = 5;
const SECTION_ORDER = ["business_overview", "hours", "location", "other"] as const;

/** Shared press feedback for the sheet's text actions: underline on hover, dim on press. */
const TEXT_PRESS = "transition-colors duration-(--duration-fast) hover:underline active:opacity-60";

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
  // W-11c: onboarding-only source actions. Their presence (onAddSource defined)
  // is what turns on the Sources panel - the Business page never passes them.
  onAddSource?: (files: File[]) => Promise<KnowledgeRecord[]>;
  onReplaceSource?: (documentId: string, file: File) => Promise<KnowledgeRecord | null>;
  onRemoveSource?: (documentId: string) => Promise<void>;
  /**
   * The parent's `confirm` (its dialog renders at page level, above this
   * sheet) - the sheet asks through it before dropping a source, so the
   * dialog never renders inside the sheet's own transformed panel.
   */
  confirmRemove?: (options: ConfirmOptions) => Promise<boolean>;
}

export function ReviewSheet({ workspace, open, busy, priceConflict, onboarding = false, onClose, onSave, onDiscard, onAddSource, onReplaceSource, onRemoveSource, confirmRemove }: ReviewSheetProps) {
  return <Sheet open={open} onClose={onClose} desktop title={onboarding ? "Review your information" : workspace?.documents[0]?.status === "draft" ? "Read this back" : "Edit what I know"}>
    {workspace ? <ReviewDocument key={workspace.id} workspace={workspace} busy={busy} priceConflict={priceConflict} onboarding={onboarding} onSave={onSave} onDiscard={onDiscard} onAddSource={onAddSource} onReplaceSource={onReplaceSource} onRemoveSource={onRemoveSource} confirmRemove={confirmRemove} /> : null}
  </Sheet>;
}

function ReviewDocument({ workspace, busy, priceConflict, onboarding, onSave, onDiscard, onAddSource, onReplaceSource, onRemoveSource, confirmRemove }: { workspace: ReviewWorkspace; busy: boolean; priceConflict: string | null; onboarding: boolean; onSave: ReviewSheetProps["onSave"]; onDiscard: () => void; onAddSource?: ReviewSheetProps["onAddSource"]; onReplaceSource?: ReviewSheetProps["onReplaceSource"]; onRemoveSource?: ReviewSheetProps["onRemoveSource"]; confirmRemove?: ReviewSheetProps["confirmRemove"] }) {
  // W-11c: the sheet reviews every workspace document together. The state map
  // below is seeded once per workspace.id and never re-synced from the
  // workspace after mount - W-11b retention (a close/reopen or a
  // rebuilds-after-save keeps the owner's in-session edits).
  const [sectionsByDocument, setSectionsByDocument] = useState<Map<string, KnowledgeSection[]>>(() => new Map(workspace.documents.map((doc) => [doc.id, orderedSections(doc.sections)])));
  const [offerings, setOfferings] = useState(() => (workspace.offering_candidates ?? []).map(toWorkingOffering));
  const [expanded, setExpanded] = useState(offerings.length <= PAGE_SIZE);
  const [page, setPage] = useState(0);
  const [editingSection, setEditingSection] = useState<{ docId: string; index: number } | null>(null);
  const [sources, setSources] = useState<Map<string, SourceDetail>>(new Map());
  const [sourceLoading, setSourceLoading] = useState<string | null>(null);
  const [combine, setCombine] = useState<{ left: string; right: string; price: number | null } | null>(null);
  const [replaceTarget, setReplaceTarget] = useState<string | null>(null);
  const [replacingSource, setReplacingSource] = useState<string | null>(null);
  const [addingSources, setAddingSources] = useState(false);
  const cardRefs = useRef(new Map<string, HTMLInputElement>());
  // W-11c: every user edit/add/combine marks the row dirty (and enters this
  // ref) so a later replace orphans it instead of silently dropping it.
  const editedIdsRef = useRef(new Set<string>());
  const addFileRef = useRef<HTMLInputElement>(null);
  const replaceFileRef = useRef<HTMLInputElement>(null);
  const pages = offeringPageCount(offerings.length);
  const currentPage = Math.min(page, pages - 1);
  const visible = expanded ? offeringPage(offerings, currentPage) : offerings.slice(0, PAGE_SIZE);
  const duplicateIds = duplicateOfferingIds(offerings);
  const unresolvedMatches = offerings.reduce((total, item) => total + item.possibleMatches.filter((id) => offerings.some((other) => other.candidate_id === id)).length, 0) / 2;
  // W-11c: the Sources panel and the per-document actions exist only when the
  // sheet is used in onboarding mode - the Business page passes no source
  // props, so its single-document flow stays exactly as it was.
  const sourcesMode = onAddSource !== undefined;
  const firstDocument = workspace.documents[0];
  const labels = workspace.documents.map(sourceLabel).join(", ");

  function sectionsFor(docId: string, doc: KnowledgeRecord): KnowledgeSection[] {
    // Docs that entered the workspace after mount (a message turn that created
    // a draft while the sheet was closed) are not in the map - fall back to
    // the record's own sections instead of showing an empty block.
    return sectionsByDocument.get(docId) ?? orderedSections(doc.sections);
  }
  function updateSections(docId: string, update: (previous: KnowledgeSection[]) => KnowledgeSection[]) {
    setSectionsByDocument((previous) => {
      const next = new Map(previous);
      next.set(docId, update(next.get(docId) ?? []));
      return next;
    });
  }
  function updateOffering(id: string, update: Partial<WorkingOffering>) {
    editedIdsRef.current.add(id);
    setOfferings((previous) => previous.map((item) => item.candidate_id === id ? { ...item, ...update, dirty: true } : item));
  }
  function removeOffering(id: string) { setOfferings((previous) => previous.filter((item) => item.candidate_id !== id)); }
  function addOffering() {
    const candidate_id = `owner_${crypto.randomUUID()}`;
    editedIdsRef.current.add(candidate_id);
    setOfferings((previous) => {
      // W-11c: the new owner row lands right after the last owner-source row
      // (top of the list when there is none), and the sheet pages to it so
      // the focus below lands on a visible field.
      const next = insertOwnerOffering(previous, { candidate_id, name: "", description: "", price_cents: null, sources: ["owner"] as ("owner" | "document")[], source_references: [], priceText: "", priceOptions: [], priceNote: "", possibleMatches: [], support_state: "supported" as const, dirty: true });
      setExpanded(true); setPage(next.page); return next.list;
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
    editedIdsRef.current.add(retained.candidate_id);
    setOfferings((previous) => previous.filter((item) => item.candidate_id !== removed.candidate_id).map((item) => item.candidate_id !== retained.candidate_id ? item : { ...retained, price_cents: price, priceText: formatPrice(price), description: retained.description || removed.description, sources: [...new Set([...retained.sources, ...removed.sources])], source_references: [...(retained.source_references ?? []), ...(removed.source_references ?? [])], possibleMatches: [...new Set([...retained.possibleMatches, ...removed.possibleMatches])].filter((id) => id !== retained.candidate_id && id !== removed.candidate_id), dirty: true }));
    setCombine(null);
  }
  async function save() {
    if (duplicateIds.length) {
      const target = offerings.find((item) => duplicateIds.includes(item.candidate_id));
      if (target) { setExpanded(true); setPage(Math.floor(offerings.indexOf(target) / PAGE_SIZE)); requestAnimationFrame(() => cardRefs.current.get(target.candidate_id)?.focus()); }
      return;
    }
    const documents = workspace.documents.map((doc) => ({ document_id: doc.id, sections: sectionsFor(doc.id, doc) }));
    const adopted = await onSave(documents, offerings.filter((item) => item.name.trim()).map(toPendingOffering), priceConflict !== null);
    if (adopted) setOfferings(reconcileAfterSave(offerings, adopted, workspace.documents, editedIdsRef.current).map(toWorkingOffering));
  }
  async function loadSource(docId: string) { if (sources.has(docId) || sourceLoading) return; setSourceLoading(docId); try { const detail = await apiFetch<SourceDetail>(`/api/knowledge/records/${docId}/source`); setSources((previous) => { const next = new Map(previous); next.set(docId, detail); return next; }); } finally { setSourceLoading(null); } }
  async function handleAddFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length === 0 || !onAddSource) return;
    setAddingSources(true);
    try {
      const records = await onAddSource(files);
      if (records.length > 0) {
        setSectionsByDocument((previous) => {
          const next = new Map(previous);
          for (const record of records) next.set(record.id, orderedSections(record.sections));
          return next;
        });
        setOfferings((previous) => {
          const merged = mergeIncomingCandidates(previous, records);
          return merged.map((item, index) => {
            const working = toWorkingOffering(item);
            if (index < previous.length && previous[index].dirty) {
              working.dirty = true;
              editedIdsRef.current.add(working.candidate_id);
            }
            return working;
          });
        });
      }
    } finally {
      setAddingSources(false);
    }
  }
  async function handleReplaceFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    const documentId = replaceTarget;
    setReplaceTarget(null);
    if (!file || !documentId || !onReplaceSource) return;
    setReplacingSource(documentId);
    try {
      // null means the upload failed - the page's DELETE never fired and the
      // old document is untouched, so everything below stays as it was.
      const next = await onReplaceSource(documentId, file);
      if (!next) return;
      setSectionsByDocument((previous) => {
        const updated = new Map(previous);
        updated.delete(documentId);
        updated.set(next.id, orderedSections(next.sections));
        return updated;
      });
      setSources((previous) => { const updated = new Map(previous); updated.delete(documentId); return updated; });
      setOfferings((previous) => reconcileOfferings(previous, next.offering_candidates ?? [], documentId, editedIdsRef.current).map(toWorkingOffering));
    } finally {
      setReplacingSource(null);
    }
  }
  async function handleRemoveSource(documentId: string) {
    if (!onRemoveSource) return;
    if (confirmRemove) {
      const target = workspace.documents.find((doc) => doc.id === documentId);
      const confirmed = await confirmRemove({
        title: `Remove ${target ? sourceLabel(target) : "this source"}?`,
        description: "Anything it taught your assistant goes with it.",
        confirmLabel: "Remove",
        tone: "danger",
        layer: "top",
      });
      if (!confirmed) return;
    }
    try {
      await onRemoveSource(documentId);
      setSectionsByDocument((previous) => { const next = new Map(previous); next.delete(documentId); return next; });
      setSources((previous) => { const next = new Map(previous); next.delete(documentId); return next; });
    } catch {
      // The page surfaces the failure through reviewError; nothing to drop.
    }
  }

  const intro = onboarding
    ? workspace.documents.length > 1
      ? `Here's what I found in ${labels}. Review them before you use them.`
      : `Here's what I found in ${sourceLabel(firstDocument)}. Review it before you use it.`
    : `From ${labels}. Your assistant answers from the reviewed facts below.`;

  return <div className="flex min-h-0 flex-1 flex-col">
    {/* W-11c follow-up: Business > Knowledge (always one document) shows the
        document's own content before its derived offerings; onboarding keeps
        offerings first, since that IS the review there. Reordered with CSS
        `order` on this flex column rather than moving the two sections in the
        source, so neither block's own markup has to be touched. */}
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto pb-4">
      <p className="order-1 text-meta text-ink-a40">{intro}</p>
      {sourcesMode ? <section className="order-2 mt-5"><h3 className="text-row-label font-medium text-text">Sources</h3><div className="mt-2 flex flex-col gap-2">{workspace.documents.map((doc) => { const label = sourceLabel(doc); const failed = doc.status === "failed"; const replacing = replacingSource === doc.id; return <div key={doc.id} className="flex items-center justify-between gap-3 rounded-card border border-hairline px-3 py-2.5"><div className="min-w-0"><p className="truncate text-prose text-text">{label}</p>{failed && workspace.errors?.[doc.id] ? <p className="mt-1 text-meta text-danger">{workspace.errors[doc.id]}</p> : null}</div><span className={`shrink-0 rounded-full px-2 py-0.5 text-meta ${failed ? "bg-danger-subtle text-danger" : "bg-surface-container text-text-secondary"}`}>{failed ? "Failed" : "Draft"}</span>{doc.status === "draft" || failed ? <div className="flex shrink-0 items-center gap-2"><button type="button" disabled={busy || addingSources || replacingSource !== null} onClick={() => { setReplaceTarget(doc.id); replaceFileRef.current?.click(); }} aria-label={`Replace ${label}`} data-testid="review-replace-source" className={`${TEXT_PRESS} text-action font-medium text-accent-active disabled:opacity-40`}>{replacing ? "Replacing\u2026" : "Replace"}</button><button type="button" disabled={busy || addingSources || replacingSource !== null} onClick={() => void handleRemoveSource(doc.id)} aria-label={`Remove ${label}`} data-testid="review-remove-source" className={`${TEXT_PRESS} text-action text-ink-a40 disabled:opacity-40`}>Remove</button></div> : null}</div>; })}</div><button type="button" disabled={busy || replacingSource !== null} onClick={() => addFileRef.current?.click()} data-testid="review-add-source" className={`mt-3 ${TEXT_PRESS} text-action font-medium text-accent-active disabled:opacity-40`}>{addingSources ? "Adding\u2026" : "Add source"}</button><input ref={addFileRef} type="file" multiple accept={ACCEPTED_UPLOAD_EXTENSIONS.join(",")} className="hidden" data-testid="review-add-input" onChange={(event) => void handleAddFiles(event)} /><input ref={replaceFileRef} type="file" accept={ACCEPTED_UPLOAD_EXTENSIONS.join(",")} className="hidden" data-testid="review-replace-input" onChange={(event) => void handleReplaceFile(event)} /></section> : null}
      <section className={onboarding ? "order-3 mt-5" : "order-4 mt-7"}><h3 className="text-row-label font-medium text-text">Offerings</h3><p className="mt-1 text-meta text-ink-a40">{!onboarding ? `From ${labels}. ` : ""}{offerings.length} retained {offerings.length === 1 ? "offering" : "offerings"}{unresolvedMatches ? `, ${unresolvedMatches} possible ${unresolvedMatches === 1 ? "match" : "matches"} left to decide` : ""}.</p>
        <div className="mt-3 flex items-center justify-between">
          {!expanded && offerings.length > PAGE_SIZE ? <button type="button" onClick={() => { setExpanded(true); setPage(0); }} className={`${TEXT_PRESS} text-action font-medium text-accent-active`}>Review all {offerings.length}</button> : <span />}
          <button type="button" onClick={addOffering} className={`${TEXT_PRESS} text-action font-medium text-accent-active`}>Add offering</button>
        </div>
        {offerings.length === 0 ? <p className="mt-3 rounded-field bg-surface-container p-3 text-prose text-text">No offerings yet.</p> : null}
        <div className="mt-3 flex flex-col gap-3">{visible.map((offering, index) => <OfferingCard key={offering.candidate_id} offering={offering} documents={workspace.documents} position={(expanded ? currentPage * PAGE_SIZE : 0) + index + 1} all={offerings} editing={expanded} inputRef={(node) => { if (node) cardRefs.current.set(offering.candidate_id, node); }} onChange={updateOffering} onRemove={removeOffering} onKeepBoth={keepBoth} onCombine={(left, right) => setCombine({ left, right, price: null })} />)}</div>
        {expanded && offerings.length > PAGE_SIZE ? <Pagination page={currentPage} pages={pages} count={offerings.length} onPage={setPage} /> : null}
        {duplicateIds.length ? <p role="alert" className="mt-2 text-meta text-danger">Two retained offerings have the same name. Go to the highlighted offering to correct it.</p> : null}
      </section>
      <section className={onboarding ? "order-4 mt-7" : "order-3 mt-5"}><h3 className="text-row-label font-medium text-text">Business information</h3>{workspace.documents.map((doc) => { const sections = sectionsFor(doc.id, doc); const label = sourceLabel(doc); return <div key={doc.id} className="mt-4">{workspace.documents.length > 1 ? <p className="text-meta text-ink-a40">From {label}</p> : null}{doc.extraction_status === "partial" || doc.extraction_status === "failed" ? <p role="status" className="mt-3 rounded-field bg-warning-subtle p-2 text-meta text-text">{doc.extraction_status === "failed" ? "I could not read the offerings from this source." : "I could not read all of this source."} Add anything missing, or check the original source.</p> : null}<KnowledgeDocument sections={sections} editingSection={editingSection?.docId === doc.id ? editingSection.index : null} onEdit={(index) => setEditingSection((current) => index === null || (current?.docId === doc.id && current.index === index) ? null : { docId: doc.id, index })} onChange={(index, update) => updateSections(doc.id, (previous) => previous.map((section, position) => position === index ? { ...section, ...update } : section))} onRemove={(index) => updateSections(doc.id, (previous) => previous.filter((_, position) => position !== index))} onAddOther={() => { updateSections(doc.id, (previous) => [...previous, { heading: "New information", body: "", kind: "other" }]); setEditingSection({ docId: doc.id, index: sections.length }); }} /><details className="mt-4 rounded-card border border-hairline p-3" onToggle={(event) => { if ((event.currentTarget as HTMLDetailsElement).open) void loadSource(doc.id); }}><summary className={`cursor-pointer ${TEXT_PRESS} text-action font-medium text-accent-active`}>View original source</summary>{sourceLoading === doc.id ? <p className="mt-3 text-meta text-ink-a40">Loading source…</p> : null}{sources.get(doc.id) ? <><p className="mt-3 text-meta text-ink-a40">{sources.get(doc.id)!.is_fallback ? "This legacy source only retains its saved reviewed text." : "Original extracted source. It does not answer customers."}</p><pre className="mt-3 whitespace-pre-wrap break-words font-sans text-prose text-text">{sources.get(doc.id)!.text}</pre></> : null}</details></div>; })}</section>
    </div>
    {combine ? <CombinePreview combine={combine} offerings={offerings} onPrice={(price) => setCombine({ ...combine, price })} onCancel={() => setCombine(null)} onConfirm={applyCombine} /> : null}
    {priceConflict ? <p role="alert" className="mt-3 rounded-card bg-warning-subtle p-3 text-meta text-text">{priceConflict}</p> : null}
    <footer className="mt-3 flex shrink-0 gap-2 border-t border-hairline pt-3"><Button className="flex-1" loading={busy} onClick={save} data-testid={onboarding ? "onboarding-knowledge-save" : "knowledge-save"}>{onboarding ? "Use this information" : priceConflict ? "Confirm price changes" : firstDocument?.status === "draft" ? "Save it" : "Save changes"}</Button><button type="button" onClick={onDiscard} disabled={busy} className={`px-3 ${TEXT_PRESS} text-action font-medium text-ink-a40`} data-testid={onboarding ? "onboarding-knowledge-discard" : "knowledge-discard"}>{onboarding || firstDocument?.status === "draft" ? "Discard" : "Remove"}</button></footer>
  </div>;
}

function OfferingCard({ offering, documents, position, all, editing, inputRef, onChange, onRemove, onKeepBoth, onCombine }: { offering: WorkingOffering; documents: KnowledgeRecord[]; position: number; all: WorkingOffering[]; editing: boolean; inputRef: (node: HTMLInputElement | null) => void; onChange: (id: string, update: Partial<WorkingOffering>) => void; onRemove: (id: string) => void; onKeepBoth: (left: string, right: string) => void; onCombine: (left: string, right: string) => void }) {
  const matches = all.filter((item) => offering.possibleMatches.includes(item.candidate_id));
  return <article className={`rounded-card border p-3 ${matches.length ? "border-text bg-surface" : "border-border bg-surface"}`}><div className="flex items-start justify-between gap-2"><span className="text-meta text-ink-a40">{offeringLabel(offering, documents)}{offering.source_references?.length ? ` · ${offering.source_references.length} source ${offering.source_references.length === 1 ? "reference" : "references"}` : ""}</span>{editing ? <button type="button" onClick={() => onRemove(offering.candidate_id)} className={`${TEXT_PRESS} text-action text-ink-a40`}>Remove</button> : null}</div>
    {editing ? <><div className="mt-2 flex gap-2"><input ref={inputRef} value={offering.name} aria-label={`Offering ${position} name`} placeholder="Offering" onChange={(event) => onChange(offering.candidate_id, { name: event.target.value })} className="min-w-0 flex-1 rounded-field border border-border bg-surface px-3 py-2 text-field text-text outline-none focus:border-text" /><input value={offering.priceText} aria-label={`Offering ${position} price`} placeholder="Price" inputMode="decimal" onChange={(event) => onChange(offering.candidate_id, { priceText: event.target.value, priceOptions: [] })} className="w-24 rounded-field border border-border bg-surface px-3 py-2 text-field text-text outline-none focus:border-text" /></div><textarea value={offering.description} aria-label={`Offering ${position} description`} placeholder="Description (optional)" rows={2} onChange={(event) => onChange(offering.candidate_id, { description: event.target.value })} className="mt-2 w-full resize-y rounded-field border border-border bg-surface px-3 py-2 text-field text-text outline-none focus:border-text" /></> : <><div className="mt-2 flex justify-between gap-3"><h4 className="text-row-label font-medium text-text">{offering.name}</h4><span className="shrink-0 text-row-label text-text">{offering.priceText || "Price not set"}</span></div>{offering.description ? <p className="mt-1 whitespace-pre-line text-prose text-text">{offering.description}</p> : null}</>}
    {offering.priceNote ? <p className="mt-2 rounded-field bg-warning-subtle p-2 text-meta text-text">Check this price: {offering.priceNote}</p> : null}
    {offering.priceOptions.length > 1 ? <div role="alert" className="mt-2 text-meta text-text">Choose a price: {offering.priceOptions.map((price) => <button key={price} type="button" onClick={() => onChange(offering.candidate_id, { price_cents: price, priceText: formatPrice(price), priceOptions: [] })} className={`${TEXT_PRESS} ml-2 text-action text-accent-active`}>Use {formatPrice(price)}</button>)}</div> : null}
    {matches.map((match) => <div key={match.candidate_id} className="mt-3 text-meta text-text"><p>This may be the same offering as <strong>{match.name}</strong>. Both remain separate until you decide.</p><div className="mt-2 flex gap-3"><button type="button" onClick={() => onCombine(offering.candidate_id, match.candidate_id)} className={`${TEXT_PRESS} text-action font-medium text-accent-active`}>Combine</button><button type="button" onClick={() => onKeepBoth(offering.candidate_id, match.candidate_id)} className={`${TEXT_PRESS} text-action text-ink-a40`}>Keep both</button></div></div>)}</article>;
}

export function KnowledgeDocument({ sections, editingSection = null, onEdit, onChange, onRemove, onAddOther }: { sections: KnowledgeSection[]; editingSection?: number | null; onEdit?: (index: number | null) => void; onChange?: (index: number, update: Partial<KnowledgeSection>) => void; onRemove?: (index: number) => void; onAddOther?: () => void }) {
  return <div className="mt-3 flex flex-col gap-4">{sections.map((section, index) => <section key={`${section.kind}-${section.heading}-${index}`} className="rounded-card border border-hairline p-3"><div className="flex items-center justify-between gap-3">{editingSection === index ? <input value={section.heading} aria-label="Section heading" onChange={(event) => onChange?.(index, { heading: event.target.value })} className="min-w-0 rounded-field border border-border bg-surface px-2 py-1 text-row-label font-medium text-text" /> : <h4 className="text-field-label font-medium uppercase text-ink-a40">{section.heading}</h4>}{onEdit ? <div className="flex gap-3"><button type="button" onClick={() => onEdit(editingSection === index ? null : index)} className={`${TEXT_PRESS} text-action text-accent-active`}>{editingSection === index ? "Done" : "Edit"}</button>{section.kind === "other" ? <button type="button" onClick={() => onRemove?.(index)} className={`${TEXT_PRESS} text-action text-ink-a40`}>Remove</button> : null}</div> : null}</div>{editingSection === index ? <textarea value={section.body} rows={4} aria-label={`${section.heading} details`} onChange={(event) => onChange?.(index, { body: event.target.value })} className="mt-2 w-full resize-y rounded-field border border-border bg-surface px-3 py-2 text-field text-text outline-none focus:border-text" /> : <FormattedBody body={section.body} />}</section>)}{onAddOther ? <button type="button" onClick={onAddOther} className={`text-left ${TEXT_PRESS} text-action font-medium text-accent-active`}>Add other information</button> : null}</div>;
}

function FormattedBody({ body }: { body: string }) { return <div className="mt-2 whitespace-pre-line break-words text-prose text-text">{body.split("\n").map((line, index) => line.startsWith("- ") || line.startsWith("• ") ? <div key={index} className="pl-4 before:mr-2 before:content-['•']">{line.slice(2)}</div> : <p key={index} className={line ? "" : "h-3"}>{line}</p>)}</div>; }
function CombinePreview({ combine, offerings, onPrice, onCancel, onConfirm }: { combine: { left: string; right: string; price: number | null }; offerings: WorkingOffering[]; onPrice: (price: number) => void; onCancel: () => void; onConfirm: () => void }) { const pair = offerings.filter((item) => item.candidate_id === combine.left || item.candidate_id === combine.right); const retained = pair.find((item) => item.sources.includes("owner")) ?? pair[0]; const prices = [...new Set(pair.map((item) => item.price_cents).filter((price): price is number => price != null))]; if (!retained) return null; return <section className="mt-3 rounded-card border border-text bg-surface p-3"><h3 className="text-row-label font-medium text-text">Combine offerings</h3><p className="mt-1 text-meta text-text">This keeps {retained.name}, {retained.description || "the available description"}, and {prices.length > 1 ? "the price you choose" : retained.priceText || "no price"}. Source evidence is combined.</p>{prices.length > 1 ? <div className="mt-2"><p className="text-meta text-text">Choose the retained price.</p>{prices.map((price) => <button key={price} type="button" onClick={() => onPrice(price)} className={`mr-2 mt-2 rounded-full border px-3 py-1 text-action transition-colors duration-(--duration-fast) hover:bg-surface-container ${combine.price === price ? "border-text bg-surface text-text" : "border-border text-text"}`}>{formatPrice(price)}</button>)}</div> : null}<div className="mt-3 flex gap-3"><button type="button" onClick={onConfirm} disabled={prices.length > 1 && combine.price == null} className={`${TEXT_PRESS} text-action font-medium text-accent-active disabled:opacity-50`}>Confirm combine</button><button type="button" onClick={onCancel} className={`${TEXT_PRESS} text-action text-ink-a40`}>Cancel</button></div></section>; }
export function Pagination({ page, pages, count, onPage }: { page: number; pages: number; count: number; onPage: (page: number) => void }) { return <div className="mt-4 flex flex-col gap-2 text-meta text-text"><div className="flex items-center justify-between"><button type="button" disabled={page === 0} onClick={() => onPage(page - 1)} className={`${TEXT_PRESS} text-action text-accent-active disabled:opacity-40`}>Previous</button><span>Page {page + 1} of {pages}</span><button type="button" disabled={page === pages - 1} onClick={() => onPage(page + 1)} className={`${TEXT_PRESS} text-action text-accent-active disabled:opacity-40`}>Next</button></div><p className="text-center">Showing {page * PAGE_SIZE + 1}-{Math.min((page + 1) * PAGE_SIZE, count)} of {count} offerings</p></div>; }
export function offeringPageCount(count: number) { return Math.max(1, Math.ceil(count / PAGE_SIZE)); }
export function offeringPage<T>(offerings: T[], page: number) { return offerings.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE); }
export function pageForOffering(index: number) { return Math.max(0, Math.floor(index / PAGE_SIZE)); }
/** W-11c: where a fresh owner row lands - right after the last owner-source
 *  row, or at the top of the list when there is none - and the page that
 *  shows it. Pure so the insertion rule is unit-testable. */
export function insertOwnerOffering(offerings: WorkingOffering[], item: WorkingOffering): { list: WorkingOffering[]; page: number } {
  const ownerEnd = offerings.map((offering) => offering.sources.includes("owner")).lastIndexOf(true);
  const insertAt = ownerEnd + 1;
  return { list: [...offerings.slice(0, insertAt), item, ...offerings.slice(insertAt)], page: pageForOffering(insertAt) };
}
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