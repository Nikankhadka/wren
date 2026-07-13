"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Table, type TableColumn } from "@/components/ui/Table";
import { apiFetch, ApiError } from "@/lib/api";
import { formatCents } from "@/lib/money";

interface PricingRule {
  id: string;
  code: string;
  label: string;
  unit_amount_cents: number;
  unit: string;
  active: boolean;
  updated_at: string;
}

interface CatalogItem {
  id: string;
  name: string;
  description: string;
  price_cents: number | null;
  active: boolean;
  updated_at: string;
}

interface RuleDraft {
  code: string;
  label: string;
  amount: string;
  unit: string;
  active: boolean;
}

/**
 * One-off display transform: integer cents -> the plain "120.00" string an
 * <input type="number"> needs (no currency symbol). This is not shared money
 * formatting - formatCents renders "$120.00", wrong for an editable field - so
 * it lives here rather than in src/lib/money.ts.
 */
function centsToAmountInput(cents: number): string {
  return (cents / 100).toFixed(2);
}

const INPUT_CLASS =
  "w-full rounded-md border border-border bg-surface px-2 py-1 text-body-sm text-text transition-colors duration-fast hover:border-border-strong";

/**
 * T-031: Pricing tab (frontend.md 7.2). pricing_rules with inline editing +
 * read-only catalog_items. The client sends decimal dollars; the backend does
 * the cents conversion (deterministic-pricing rule). Validation errors from
 * the PATCH render inline, never as an alert.
 */
export default function PricingPage() {
  const [rules, setRules] = useState<PricingRule[]>([]);
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [rulesLoading, setRulesLoading] = useState(true);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<RuleDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  async function loadRules() {
    try {
      const rows = await apiFetch<PricingRule[]>("/api/pricing/rules");
      setRules(rows);
      setRulesError(null);
    } catch (err) {
      setRulesError(err instanceof ApiError ? err.detail : "Failed to load pricing rules");
    } finally {
      setRulesLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    apiFetch<PricingRule[]>("/api/pricing/rules")
      .then((rows) => {
        if (!active) return;
        setRules(rows);
        setRulesError(null);
      })
      .catch((err) => {
        if (active)
          setRulesError(err instanceof ApiError ? err.detail : "Failed to load pricing rules");
      })
      .finally(() => {
        if (active) setRulesLoading(false);
      });
    apiFetch<CatalogItem[]>("/api/pricing/catalog")
      .then((rows) => {
        if (!active) return;
        setCatalog(rows);
        setCatalogError(null);
      })
      .catch((err) => {
        if (active)
          setCatalogError(err instanceof ApiError ? err.detail : "Failed to load catalog");
      })
      .finally(() => {
        if (active) setCatalogLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function startEdit(rule: PricingRule) {
    setEditingId(rule.id);
    setEditError(null);
    setDraft({
      code: rule.code,
      label: rule.label,
      amount: centsToAmountInput(rule.unit_amount_cents),
      unit: rule.unit,
      active: rule.active,
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft(null);
    setEditError(null);
  }

  async function saveEdit(id: string) {
    if (!draft) return;
    setSaving(true);
    setEditError(null);
    try {
      await apiFetch(`/api/pricing/rules/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          code: draft.code,
          label: draft.label,
          unit_amount_dollars: draft.amount,
          unit: draft.unit,
          active: draft.active,
        }),
      });
      cancelEdit();
      await loadRules();
    } catch (err) {
      // 422 (validation) / 409 (duplicate code) render inline per frontend.md.
      setEditError(err instanceof ApiError ? err.detail : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }

  const ruleColumns: TableColumn<PricingRule>[] = [
    {
      key: "code",
      header: "Code",
      render: (rule) =>
        editingId === rule.id && draft ? (
          <input
            aria-label="Code"
            className={INPUT_CLASS}
            value={draft.code}
            onChange={(e) => setDraft({ ...draft, code: e.target.value })}
          />
        ) : (
          <span className="font-mono text-caption text-text">{rule.code}</span>
        ),
    },
    {
      key: "label",
      header: "Label",
      render: (rule) =>
        editingId === rule.id && draft ? (
          <input
            aria-label="Label"
            className={INPUT_CLASS}
            value={draft.label}
            onChange={(e) => setDraft({ ...draft, label: e.target.value })}
          />
        ) : (
          rule.label
        ),
    },
    {
      key: "amount",
      header: "Amount",
      render: (rule) =>
        editingId === rule.id && draft ? (
          <input
            aria-label="Amount in dollars"
            type="number"
            step="0.01"
            min="0"
            className={`${INPUT_CLASS} w-28 tabular-nums`}
            value={draft.amount}
            onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
          />
        ) : (
          <span className="tabular-nums">{formatCents(rule.unit_amount_cents)}</span>
        ),
    },
    {
      key: "unit",
      header: "Unit",
      render: (rule) =>
        editingId === rule.id && draft ? (
          <input
            aria-label="Unit"
            className={`${INPUT_CLASS} w-24`}
            value={draft.unit}
            onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
          />
        ) : (
          <span className="text-text-secondary">{rule.unit}</span>
        ),
    },
    {
      key: "active",
      header: "Active",
      render: (rule) =>
        editingId === rule.id && draft ? (
          <label className="flex items-center gap-2 text-body-sm text-text">
            <input
              type="checkbox"
              className="accent-accent"
              checked={draft.active}
              onChange={(e) => setDraft({ ...draft, active: e.target.checked })}
            />
            Active
          </label>
        ) : (
          <Badge tone={rule.active ? "success" : "neutral"}>
            {rule.active ? "active" : "inactive"}
          </Badge>
        ),
    },
    {
      key: "actions",
      header: "",
      render: (rule) =>
        editingId === rule.id ? (
          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2">
              <Button size="sm" loading={saving} onClick={() => saveEdit(rule.id)}>
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={cancelEdit}>
                Cancel
              </Button>
            </div>
            {editError ? <p className="text-footnote text-danger">{editError}</p> : null}
          </div>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            disabled={editingId !== null}
            onClick={() => startEdit(rule)}
          >
            Edit
          </Button>
        ),
    },
  ];

  const catalogColumns: TableColumn<CatalogItem>[] = [
    { key: "name", header: "Name", render: (item) => item.name },
    {
      key: "description",
      header: "Description",
      render: (item) => <span className="text-text-secondary">{item.description}</span>,
    },
    {
      key: "price",
      header: "Price",
      render: (item) => (
        <span className="tabular-nums">
          {item.price_cents === null ? "-" : formatCents(item.price_cents)}
        </span>
      ),
    },
    {
      key: "active",
      header: "Active",
      render: (item) => (
        <Badge tone={item.active ? "success" : "neutral"}>
          {item.active ? "active" : "inactive"}
        </Badge>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-title-2 font-semibold text-text">Pricing</h1>
        <p className="mt-1 text-body-sm text-text-secondary">
          The rules and catalog your assistant quotes from.
        </p>
      </div>

      <div
        role="note"
        className="rounded-md border border-border bg-info-subtle px-4 py-2 text-body-sm text-info"
      >
        Changes apply to new quotes only.
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="text-title-3 font-semibold text-text">Pricing rules</h2>
        <Table
          columns={ruleColumns}
          rows={rules}
          rowKey={(rule) => rule.id}
          loading={rulesLoading}
          error={rulesError ?? undefined}
          emptyState={
            <EmptyState
              title="No pricing rules yet"
              description="Pricing rules are captured during onboarding and power deterministic quotes."
            />
          }
        />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-title-3 font-semibold text-text">Catalog items</h2>
        <Table
          columns={catalogColumns}
          rows={catalog}
          rowKey={(item) => item.id}
          loading={catalogLoading}
          error={catalogError ?? undefined}
          emptyState={
            <EmptyState
              title="No catalog items yet"
              description="Products and services you offer will appear here once added."
            />
          }
        />
      </section>
    </div>
  );
}
