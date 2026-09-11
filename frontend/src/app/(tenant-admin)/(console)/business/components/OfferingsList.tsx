"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { ApiError, apiFetch } from "@/lib/api";

interface Offering {
  id: string;
  name: string;
  description: string;
  price_cents: number | null;
  category?: string | null;
  media?: { url: string } | null;
}

interface FormValues {
  name: string;
  description: string;
  price: string;
  category: string;
  mediaUrl: string;
  mediaFile: File | null;
  mediaChanged: boolean;
  removeMedia: boolean;
}

const EMPTY_FORM: FormValues = {
  name: "",
  description: "",
  price: "",
  category: "",
  mediaUrl: "",
  mediaFile: null,
  mediaChanged: false,
  removeMedia: false,
};

function formFor(offering: Offering): FormValues {
  return {
    name: offering.name,
    description: offering.description,
    price:
      offering.price_cents === null
        ? ""
        : (offering.price_cents / 100).toFixed(2),
    category: offering.category ?? "",
    mediaUrl: offering.media?.url ?? "",
    mediaFile: null,
    mediaChanged: false,
    removeMedia: false,
  };
}

export function OfferingsList() {
  const [offerings, setOfferings] = useState<Offering[]>([]);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [form, setForm] = useState<FormValues>(EMPTY_FORM);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setOfferings(await apiFetch<Offering[]>("/api/business/offerings"));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Couldn't load what you offer.");
    }
  }

  // Deliberately not `void load()`: react-hooks/set-state-in-effect cannot see
  // that the setState inside an async function is deferred past an await, and
  // rejects it. Written as a visible callback, the rule is satisfied and the
  // behaviour is identical. `load()` stays for the mutation handlers below.
  useEffect(() => {
    apiFetch<Offering[]>("/api/business/offerings")
      .then(setOfferings)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Couldn't load what you offer."),
      );
  }, []);

  function begin(offering?: Offering) {
    setError(null);
    setEditing(offering?.id ?? "new");
    setForm(offering ? formFor(offering) : EMPTY_FORM);
    setDetailsOpen(
      Boolean(
        offering &&
          (offering.category ||
            offering.description ||
            offering.price_cents !== null ||
            offering.media),
      ),
    );
  }

  function close() {
    if (!working) setEditing(null);
  }

  async function save() {
    if (!editing || !form.name.trim()) return;
    setWorking(true);
    setError(null);
    const body = {
      name: form.name,
      description: form.description,
      price_dollars: form.price.trim() || null,
      category: form.category.trim() || null,
    };
    try {
      const path = editing === "new" ? "/api/business/offerings" : `/api/business/offerings/${editing}`;
      const saved = await apiFetch<Offering>(path, {
        method: editing === "new" ? "POST" : "PATCH",
        body: JSON.stringify(body),
      });
      if (form.removeMedia) {
        await apiFetch(`/api/business/offerings/${saved.id}/media`, {
          method: "DELETE",
        });
      } else if (form.mediaChanged && form.mediaUrl.trim()) {
        await apiFetch(`/api/business/offerings/${saved.id}/media/url`, {
          method: "PUT",
          body: JSON.stringify({ url: form.mediaUrl.trim() }),
        });
      } else if (form.mediaChanged && form.mediaFile) {
        const media = new FormData();
        media.append("file", form.mediaFile);
        await apiFetch(`/api/business/offerings/${saved.id}/media/upload`, {
          method: "PUT",
          body: media,
        });
      }
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Couldn't save that offering.");
    } finally {
      setWorking(false);
    }
  }

  async function remove(offering: Offering) {
    if (working || !window.confirm(`Remove ${offering.name}?`)) return;
    setWorking(true);
    setError(null);
    try {
      await apiFetch(`/api/business/offerings/${offering.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Couldn't remove that offering.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <section className="border-b border-hairline px-gutter py-5" aria-labelledby="offerings-heading">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="offerings-heading" className="text-row-label font-medium text-text">
            What you offer
          </h2>
          <p className="mt-1 text-meta text-ink-a40">
            Add the services or products customers can ask about.
          </p>
        </div>
        {editing === null ? (
          <button
            type="button"
            onClick={() => begin()}
            data-testid="offering-add"
            className="flex shrink-0 items-center gap-1 text-action font-medium text-accent-active active:opacity-60"
          >
            <Icon name="add" size={16} />
            Add
          </button>
        ) : null}
      </div>

      {offerings.length > 0 ? (
        <ul className="mt-3 divide-y divide-hairline" data-testid="offerings-list">
          {offerings.map((offering) => (
            <li key={offering.id} className="flex items-center gap-3 py-3">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-card-hl font-medium text-text">{offering.name}</span>
                {offering.description ? (
                  <span className="mt-0.5 block truncate text-meta text-ink-a40">
                    {offering.description}
                  </span>
                ) : null}
                {offering.price_cents !== null ? (
                  <span className="mt-0.5 block text-meta text-ink-a40">
                    ${(offering.price_cents / 100).toFixed(2)}
                  </span>
                ) : null}
              </span>
              <button
                type="button"
                onClick={() => begin(offering)}
                disabled={working}
                aria-label={`Edit ${offering.name}`}
                data-testid="offering-edit"
                className="flex size-icon-btn shrink-0 items-center justify-center rounded-full text-ink-a40 active:opacity-60 disabled:opacity-50"
              >
                <Icon name="edit" size={18} />
              </button>
              <button
                type="button"
                onClick={() => void remove(offering)}
                disabled={working}
                aria-label={`Remove ${offering.name}`}
                data-testid="offering-remove"
                className="flex size-icon-btn shrink-0 items-center justify-center rounded-full text-ink-a40 active:opacity-60 disabled:opacity-50"
              >
                <Icon name="delete" size={18} />
              </button>
            </li>
          ))}
        </ul>
      ) : editing === null ? (
        <p className="mt-3 text-prose text-ink-a40">Nothing added yet.</p>
      ) : null}

      {editing !== null ? (
        <form
          className="mt-4 rounded-card border border-border bg-surface p-3"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="flex items-start justify-between gap-2">
            <span className="text-meta text-ink-a40">
              {editing === "new" ? "New offering" : "Edit offering"}
            </span>
            <button
              type="button"
              onClick={close}
              disabled={working}
              className="text-action text-ink-a40 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
          <div className="mt-2 flex gap-2">
            <input
              autoFocus
              required
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="Offering"
              aria-label="Offering name"
              data-testid="offering-name"
              className="min-w-0 flex-1 rounded-field border border-border bg-surface px-3 py-2 text-field text-text outline-none placeholder:text-ink-a40 focus:border-text"
            />
            <input
              value={form.price}
              onChange={(event) => setForm((current) => ({ ...current, price: event.target.value }))}
              inputMode="decimal"
              placeholder="Price"
              aria-label="Price"
              data-testid="offering-price"
              className="w-24 rounded-field border border-border bg-surface px-3 py-2 text-field text-text outline-none placeholder:text-ink-a40 focus:border-text"
            />
          </div>
          <textarea
            value={form.description}
            onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
            placeholder="Description (optional)"
            aria-label="Description"
            rows={2}
            data-testid="offering-description"
            className="mt-2 w-full resize-y rounded-field border border-border bg-surface px-3 py-2 text-field text-text outline-none placeholder:text-ink-a40 focus:border-text"
          />
          <details
            open={detailsOpen}
            onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
            className="mt-2 rounded-field border border-border bg-surface px-3 py-2"
          >
            <summary className="cursor-pointer text-field-label font-medium uppercase text-ink-a40">
              Add details
            </summary>
            <label className="mt-3 block text-field-label font-medium uppercase text-ink-a40">
              Category <span className="normal-case">(optional)</span>
              <input data-testid="offering-category" value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value }))} className="mt-1.5 w-full rounded-field border border-border bg-surface px-3 py-2 text-field text-text outline-none focus:border-text" />
            </label>
            <label className="mt-3 block text-field-label font-medium uppercase text-ink-a40">
              Image or video URL <span className="normal-case">(optional)</span>
              <input data-testid="offering-media-url" type="url" value={form.mediaUrl} onChange={(event) => setForm((current) => ({ ...current, mediaUrl: event.target.value, mediaChanged: true, removeMedia: false }))} className="mt-1.5 w-full rounded-field border border-border bg-surface px-3 py-2 text-field text-text outline-none focus:border-text" />
            </label>
            <label className="mt-3 block text-field-label font-medium uppercase text-ink-a40">
              Upload media <span className="normal-case">(optional)</span>
              <input type="file" accept="image/*,video/*" onChange={(event) => setForm((current) => ({ ...current, mediaFile: event.target.files?.[0] ?? null, mediaUrl: "", mediaChanged: true, removeMedia: false }))} className="mt-1.5 block w-full text-meta text-ink-a40" />
            </label>
            {form.removeMedia ? (
              <p className="mt-3 text-meta text-ink-a40">
                Current media will be removed when you save.
              </p>
            ) : form.mediaUrl ? (
              <button
                type="button"
                onClick={() => setForm((current) => ({ ...current, mediaChanged: true, removeMedia: true }))}
                className="mt-3 text-action font-medium text-accent-active"
              >
                Remove current media
              </button>
            ) : null}
          </details>
          {error ? <p className="mt-2 text-meta text-danger">{error}</p> : null}
          <div className="mt-3 flex justify-end">
            <button
              type="submit"
              disabled={working || !form.name.trim()}
              data-testid="offering-save"
              className="rounded-field bg-brand px-4 py-2 text-action font-medium text-text-inverse hover:brightness-95 active:brightness-90 disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </form>
      ) : error ? (
        <p className="mt-3 text-meta text-danger">{error}</p>
      ) : null}
    </section>
  );
}
