"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { ScreenTopbar } from "@/components/ui/ScreenTopbar";
import { apiFetch, ApiError } from "@/lib/api";
import { ACCEPTED_UPLOAD_EXTENSIONS, describeUpload } from "@/lib/onboarding";
import { KnowledgeDocument, ReviewSheet } from "./components/ReviewSheet";
import {
  sourceLabel,
  statusLine,
  type KnowledgeRecord,
  type KnowledgeSection,
  type PendingOffering,
  type ReviewWorkspace,
} from "./lib/types";

/**
 * Settings > Knowledge: what the assistant answers from, as one readable text.
 *
 * Deliberately not a document manager. A source - a link or a file - is read,
 * processed into sections, and shown back for the owner to correct; what they
 * save is what the assistant answers from. There is no table, no per-file type
 * picker and no status column, because none of that is what the owner came here
 * to know: they came to see what their assistant thinks their business is.
 *
 * Built from agencx-prototype-v6.html's destination screens (`.dst-topbar`,
 * `.se-label` / `.se-input` / `.se-add`, the bottom sheet). The desktop console
 * components (Table, Select, FileDropzone) are Wren-era and stay out of here.
 */
export default function KnowledgePage() {
  const [records, setRecords] = useState<KnowledgeRecord[]>([]);
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<ReviewWorkspace | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [priceConflict, setPriceConflict] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    const rows = await apiFetch<KnowledgeRecord[]>("/api/knowledge/records");
    setRecords(rows);
    return rows;
  }

  useEffect(() => {
    apiFetch<KnowledgeRecord[]>("/api/knowledge/records")
      .then(setRecords)
      .catch((err) => setError(err instanceof ApiError ? err.detail : "Couldn't load this"))
      .finally(() => setLoading(false));
  }, []);

  function fail(err: unknown, fallback: string) {
    setError(err instanceof ApiError && err.detail ? err.detail : fallback);
  }

  async function addLink() {
    const trimmed = url.trim();
    if (!trimmed || working) return;
    setError(null);
    setWorking("Reading your site…");
    try {
      const draft = await apiFetch<KnowledgeRecord>("/api/knowledge/drafts/url", {
        method: "POST",
        body: JSON.stringify({ url: trimmed }),
      });
      setUrl("");
      await refresh();
      setPriceConflict(null);
      setWorkspace(draft);
      setSheetOpen(true);
    } catch (err) {
      fail(err, "I couldn't read that page. Check the link, or send me a file instead.");
    } finally {
      setWorking(null);
    }
  }

  async function addFile(file: File) {
    const verdict = describeUpload(file.name);
    if (!verdict.accepted) {
      setError(verdict.message);
      return;
    }
    setError(null);
    setWorking(`Reading ${file.name}…`);
    try {
      const form = new FormData();
      form.append("file", file);
      const draft = await apiFetch<KnowledgeRecord>("/api/knowledge/drafts/upload", {
        method: "POST",
        body: form,
      });
      await refresh();
      setPriceConflict(null);
      setWorkspace(draft);
      setSheetOpen(true);
    } catch (err) {
      fail(err, "I couldn't read that file.");
    } finally {
      setWorking(null);
    }
  }

  async function save(
    sections: KnowledgeSection[],
    offerings: PendingOffering[] = [],
    acceptPriceChanges = false,
  ) {
    if (!workspace) return;
    setError(null);
    setWorking("Saving…");
    try {
      await apiFetch<KnowledgeRecord>(`/api/knowledge/records/${workspace.id}`, {
        method: "PUT",
        body: JSON.stringify({
          sections,
          offerings,
          accept_price_changes: acceptPriceChanges,
        }),
      });
      setPriceConflict(null);
      setWorkspace(null);
      setSheetOpen(false);
      await refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setPriceConflict(err.detail);
      } else {
        fail(err, "I couldn't save that.");
      }
    } finally {
      setWorking(null);
    }
  }

  /** Re-run the ingest over what is already stored - the retry on a failed row. */
  async function retry(record: KnowledgeRecord) {
    setError(null);
    setWorking("Trying again\u2026");
    try {
      await apiFetch<KnowledgeRecord>(`/api/knowledge/records/${record.id}`, {
        method: "PUT",
        body: JSON.stringify({ sections: record.sections }),
      });
      await refresh();
    } catch (err) {
      fail(err, "That didn't work either. Try removing it and adding it again.");
    } finally {
      setWorking(null);
    }
  }

  async function remove(record: KnowledgeRecord) {
    setError(null);
    setWorking("Removing…");
    try {
      await apiFetch(`/api/knowledge/records/${record.id}`, { method: "DELETE" });
      // W-11b: only close/clear the sheet if the record just deleted is the
      // one it's showing - a row-level delete on a different, unrelated
      // document must not discard an in-progress edit elsewhere.
      if (workspace?.id === record.id) {
        setWorkspace(null);
        setSheetOpen(false);
      }
      await refresh();
    } catch (err) {
      fail(err, "I couldn't remove that.");
    } finally {
      setWorking(null);
    }
  }

  /** Open one record - fetching it first, so a source ingested before this
   *  screen existed gets processed into sections on the way in. */
  async function open(record: KnowledgeRecord) {
    setPriceConflict(null);
    if (record.sections.length > 0) {
      setWorkspace(record);
      setSheetOpen(true);
      return;
    }
    setWorking("Reading it back…");
    try {
      setWorkspace(await apiFetch<KnowledgeRecord>(`/api/knowledge/records/${record.id}`));
      setSheetOpen(true);
    } catch (err) {
      fail(err, "I couldn't read that one back.");
    } finally {
      setWorking(null);
    }
  }

  const drafts = records.filter((record) => record.status === "draft");
  const saved = records.filter((record) => record.status !== "draft");

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-surface">
      <ScreenTopbar title="Knowledge" backHref="/business/details" />

      <div className="min-h-0 flex-1 overflow-y-auto px-gutter pb-20 pt-5">
        <div className="mx-auto w-full max-w-thread">
          <p className="text-prose text-text">
            This is what your assistant answers from. Add your site or a document, read back what
            I made of it, then save.
          </p>

          <div className="mt-6">
            <label className="mb-2 block text-field-label font-medium uppercase text-ink-a40">
              Add a link
            </label>
            <div className="flex items-center gap-2">
              <input
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void addLink();
                }}
                placeholder="yourbusiness.com/about"
                inputMode="url"
                disabled={working !== null}
                data-testid="knowledge-url-input"
                className="min-w-0 flex-1 rounded-field border-[length:var(--border-chip)] border-transparent bg-surface-container px-[18px] py-3.5 text-field text-text placeholder:text-ink-a40 outline-none transition-colors duration-(--duration-fast) focus:border-accent-a35 focus:bg-accent-a06 disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => void addLink()}
                disabled={working !== null || !url.trim()}
                aria-label="Read this link"
                data-testid="knowledge-url-submit"
                className="flex size-send shrink-0 items-center justify-center rounded-full bg-accent text-text-inverse transition-opacity active:opacity-85 disabled:bg-accent-a12 disabled:text-accent-a50"
              >
                <Icon name="arrow_forward" size={20} />
              </button>
            </div>

            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={working !== null}
              data-testid="knowledge-add-document"
              className="mt-1 flex w-full items-center gap-2 border-t border-dashed border-accent-a20 py-3.5 text-action font-medium text-accent active:opacity-60 disabled:opacity-50"
            >
              <Icon name="add" size={16} />
              Add a document
            </button>
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPTED_UPLOAD_EXTENSIONS.join(",")}
              className="hidden"
              data-testid="knowledge-file-input"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void addFile(file);
              }}
            />
          </div>

          <p role="status" className="mt-3 h-4 text-proc italic text-ink-a35">
            {working ?? ""}
          </p>
          {error ? (
            <p data-testid="knowledge-error" className="mt-1 text-meta text-danger">
              {error}
            </p>
          ) : null}

          {drafts.length > 0 ? (
            <section className="mt-6 flex flex-col gap-2">
              {drafts.map((record) => (
                <button
                  key={record.id}
                  type="button"
                  onClick={() => void open(record)}
                  data-testid="knowledge-draft"
                  className="flex items-center justify-between gap-3 rounded-field bg-accent-a06 px-4 py-3.5 text-left active:opacity-85"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-row-label font-medium text-text">
                      {sourceLabel(record)}
                    </span>
                    <span className="mt-1.5 block text-meta text-ink-a40">
                      Read it back before it answers anything
                    </span>
                  </span>
                  <span aria-hidden="true" className="text-accent">
                    <Icon name="chevron_right" size={20} />
                  </span>
                </button>
              ))}
            </section>
          ) : null}

          <h2 className="mt-8 text-field-label font-medium uppercase text-ink-a40">
            What your assistant knows
          </h2>

          {loading ? (
            <p aria-busy="true" className="mt-4 text-meta text-ink-a40">
              Loading&hellip;
            </p>
          ) : saved.length === 0 ? (
            <p className="mt-3 text-prose text-text">
              Nothing yet. Send me a link or a document and I&apos;ll read it.
            </p>
          ) : (
            <div className="mt-2 flex flex-col">
              {saved.map((record) => (
                <article key={record.id} className="border-b border-hairline py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="truncate text-row-label font-medium text-text">
                        {sourceLabel(record)}
                      </h3>
                      <p
                        className={`mt-1.5 text-meta ${record.status === "failed" ? "text-danger" : "text-ink-a40"}`}
                      >
                        {statusLine(record)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {record.status === "failed" ? (
                        <button
                          type="button"
                          onClick={() => void retry(record)}
                          disabled={working !== null}
                          aria-label={`Try ${sourceLabel(record)} again`}
                          data-testid="knowledge-retry"
                          className="flex size-icon-btn items-center justify-center rounded-full text-accent active:opacity-60"
                        >
                          <Icon name="refresh" size={18} />
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => void open(record)}
                        disabled={working !== null}
                        aria-label={`Edit ${sourceLabel(record)}`}
                        data-testid="knowledge-edit"
                        className="flex size-icon-btn items-center justify-center rounded-full text-ink-a40 active:opacity-60"
                      >
                        <Icon name="edit" size={18} />
                      </button>
                      <button
                        type="button"
                        onClick={() => void remove(record)}
                        disabled={working !== null}
                        aria-label={`Remove ${sourceLabel(record)}`}
                        data-testid="knowledge-remove"
                        className="flex size-icon-btn items-center justify-center rounded-full text-ink-a40 active:opacity-60"
                      >
                        <Icon name="delete" size={18} />
                      </button>
                    </div>
                  </div>

                  <details className="mt-3">
                    <summary className="cursor-pointer text-action font-medium text-accent">
                      View reviewed document
                    </summary>
                    <KnowledgeDocument sections={record.sections} />
                  </details>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>

      <ReviewSheet
        workspace={workspace}
        open={sheetOpen}
        busy={working !== null}
        priceConflict={priceConflict}
        onClose={() => {
          setPriceConflict(null);
          setSheetOpen(false);
        }}
        onSave={(sections, offerings, acceptPriceChanges) =>
          void save(sections, offerings, acceptPriceChanges)
        }
        onDiscard={() => {
          setPriceConflict(null);
          if (workspace) void remove(workspace);
        }}
      />
    </main>
  );
}
