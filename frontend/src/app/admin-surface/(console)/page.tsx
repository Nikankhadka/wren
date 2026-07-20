"use client";

import { useEffect, useState } from "react";
import { Badge, toneForStatus } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { MetricCard } from "@/components/ui/MetricCard";
import { Modal } from "@/components/ui/Modal";
import { Table, type TableColumn } from "@/components/ui/Table";
import { apiFetch, ApiError } from "@/lib/api";

interface Tenant {
  id: string;
  slug: string;
  name: string;
  status: "provisioning" | "active" | "suspended";
  created_at: string;
  conversation_count: number;
  cost_usd: number;
}

interface Metrics {
  tenant_count: number;
  total_cost_usd: number;
}

/** cost_usd is observability metadata (database.md section 7's one non-cents
 * money column) - a plain dollar float, never pricing-engine cents, so it is
 * deliberately NOT formatted through lib/money.ts's formatCents. */
function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

const SLUG_RE = /^[a-z0-9](-?[a-z0-9])*$/;
const SLUG_CHECK_DEBOUNCE_MS = 400;

type ProvisionStep =
  | { kind: "form" }
  | { kind: "success"; note: string };

/**
 * T-033: the platform-owner surface (frontend.md 7.3) - one Tenants page,
 * deliberately minimal. Metric cards, provision flow with a live slug
 * availability check, suspend/reactivate with a confirm modal.
 */
export default function PlatformHome() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantsLoading, setTenantsLoading] = useState(true);
  const [tenantsError, setTenantsError] = useState<string | null>(null);

  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  const [provisionOpen, setProvisionOpen] = useState(false);
  const [provisionStep, setProvisionStep] = useState<ProvisionStep>({ kind: "form" });
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugAvailable, setSlugAvailable] = useState<boolean | null>(null);
  const [slugChecking, setSlugChecking] = useState(false);
  const [provisionError, setProvisionError] = useState<string | null>(null);
  const [provisioning, setProvisioning] = useState(false);

  const [confirmTarget, setConfirmTarget] = useState<Tenant | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  function loadTenants() {
    apiFetch<Tenant[]>("/api/platform/tenants")
      .then((rows) => {
        setTenants(rows);
        setTenantsError(null);
      })
      .catch((err) => {
        setTenantsError(err instanceof ApiError ? err.detail : "Failed to load tenants");
      })
      .finally(() => setTenantsLoading(false));
  }

  function loadMetrics() {
    apiFetch<Metrics>("/api/platform/metrics")
      .then((body) => {
        setMetrics(body);
        setMetricsError(null);
      })
      .catch((err) => {
        setMetricsError(err instanceof ApiError ? err.detail : "Failed to load metrics");
      });
  }

  // Mount-only load; loadTenants/loadMetrics are also called directly (not
  // from an effect) after provision/suspend/reactivate mutations below.
  useEffect(() => {
    let active = true;
    apiFetch<Tenant[]>("/api/platform/tenants")
      .then((rows) => {
        if (!active) return;
        setTenants(rows);
        setTenantsError(null);
      })
      .catch((err) => {
        if (active) setTenantsError(err instanceof ApiError ? err.detail : "Failed to load tenants");
      })
      .finally(() => {
        if (active) setTenantsLoading(false);
      });
    apiFetch<Metrics>("/api/platform/metrics")
      .then((body) => {
        if (active) {
          setMetrics(body);
          setMetricsError(null);
        }
      })
      .catch((err) => {
        if (active) setMetricsError(err instanceof ApiError ? err.detail : "Failed to load metrics");
      });
    return () => {
      active = false;
    };
  }, []);

  const slugFormatValid = SLUG_RE.test(slug) && slug.length >= 3;

  // Live slug-availability check as the admin types, debounced. A slug too
  // short to be legal never round-trips to the API - the backend would just
  // 422 or reject it as a real conflict-check subject, neither of which is
  // useful feedback while the admin is still mid-keystroke. slugAvailable's
  // last known value is deliberately NOT reset when the format goes invalid
  // (no state to synchronize, nothing to derive) - the render below only
  // trusts it while slugFormatValid is also true, so a stale result never
  // displays against a currently-invalid slug.
  useEffect(() => {
    if (!slugFormatValid) return;
    const timer = window.setTimeout(() => {
      setSlugChecking(true);
      apiFetch<{ available: boolean }>(
        `/api/platform/tenants/slug-availability?slug=${encodeURIComponent(slug)}`
      )
        .then((body) => setSlugAvailable(body.available))
        .catch(() => setSlugAvailable(null))
        .finally(() => setSlugChecking(false));
    }, SLUG_CHECK_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [slug, slugFormatValid]);

  function openProvision() {
    setName("");
    setSlug("");
    setSlugAvailable(null);
    setProvisionError(null);
    setProvisionStep({ kind: "form" });
    setProvisionOpen(true);
  }

  function closeProvision() {
    setProvisionOpen(false);
  }

  async function submitProvision() {
    setProvisionError(null);
    setProvisioning(true);
    try {
      const body = await apiFetch<{ note: string }>("/api/platform/tenants", {
        method: "POST",
        body: JSON.stringify({ name, slug }),
      });
      setProvisionStep({ kind: "success", note: body.note });
      void loadTenants();
      void loadMetrics();
    } catch (err) {
      setProvisionError(err instanceof ApiError ? err.detail : "Failed to provision tenant");
    } finally {
      setProvisioning(false);
    }
  }

  async function submitStatusChange(tenant: Tenant, nextStatus: "active" | "suspended") {
    setConfirmError(null);
    setConfirmBusy(true);
    try {
      await apiFetch(`/api/platform/tenants/${tenant.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      setConfirmTarget(null);
      void loadTenants();
    } catch (err) {
      setConfirmError(err instanceof ApiError ? err.detail : "Failed to update tenant");
    } finally {
      setConfirmBusy(false);
    }
  }

  const columns: TableColumn<Tenant>[] = [
    { key: "name", header: "Name", render: (t) => t.name },
    { key: "slug", header: "Slug", render: (t) => t.slug },
    {
      key: "status",
      header: "Status",
      render: (t) => <Badge tone={toneForStatus(t.status)}>{t.status}</Badge>,
    },
    {
      key: "created_at",
      header: "Created",
      render: (t) => new Date(t.created_at).toLocaleDateString(),
    },
    { key: "conversations", header: "Conversations", render: (t) => t.conversation_count },
    { key: "cost", header: "Cost", render: (t) => formatUsd(t.cost_usd) },
    {
      key: "actions",
      header: "",
      render: (t) =>
        t.status === "active" ? (
          <Button size="sm" variant="secondary" onClick={() => setConfirmTarget(t)}>
            Suspend
          </Button>
        ) : t.status === "suspended" ? (
          <Button size="sm" variant="secondary" onClick={() => setConfirmTarget(t)}>
            Reactivate
          </Button>
        ) : null,
    },
  ];

  const slugHelp = !slugFormatValid
    ? undefined
    : slugChecking
      ? "Checking..."
      : slugAvailable === true
        ? "Available"
        : undefined;
  const slugFieldError =
    slugFormatValid && slugAvailable === false ? "Already taken" : undefined;
  const canSubmitProvision =
    name.trim().length > 0 && slugFormatValid && slugAvailable === true;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-title-2 font-semibold text-text">Tenants</h1>
        <Button onClick={openProvision}>Provision tenant</Button>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:max-w-md">
        <MetricCard
          label="Tenants"
          value={metrics ? String(metrics.tenant_count) : ""}
          loading={!metrics && !metricsError}
          error={metricsError ?? undefined}
          icon="groups"
        />
        <MetricCard
          label="Total cost"
          value={metrics ? formatUsd(metrics.total_cost_usd) : ""}
          loading={!metrics && !metricsError}
          error={metricsError ?? undefined}
          icon="paid"
        />
      </div>

      <Table
        columns={columns}
        rows={tenants}
        rowKey={(t) => t.id}
        loading={tenantsLoading}
        error={tenantsError ?? undefined}
        emptyState={
          <EmptyState
            icon="groups"
            title="No tenants yet"
            description="Provision the first business to get started."
            action={<Button onClick={openProvision}>Provision tenant</Button>}
          />
        }
      />

      <Modal open={provisionOpen} onClose={closeProvision} title="Provision tenant">
        {provisionStep.kind === "success" ? (
          <div className="flex flex-col gap-4">
            <p className="text-body-sm text-text">{provisionStep.note}</p>
            <Button onClick={closeProvision}>Done</Button>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void submitProvision();
            }}
            className="flex flex-col gap-4"
          >
            <Input
              label="Business name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
            <Input
              label="Slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase())}
              help={slugHelp}
              error={slugFieldError ?? provisionError ?? undefined}
              required
            />
            <Button type="submit" loading={provisioning} disabled={!canSubmitProvision}>
              Provision
            </Button>
          </form>
        )}
      </Modal>

      <Modal
        open={confirmTarget !== null}
        onClose={() => setConfirmTarget(null)}
        title={confirmTarget?.status === "active" ? "Suspend tenant" : "Reactivate tenant"}
      >
        {confirmTarget ? (
          <div className="flex flex-col gap-4">
            <p className="text-body-sm text-text">
              {confirmTarget.status === "active"
                ? `Suspend ${confirmTarget.name}? Customers will immediately see this business as unavailable.`
                : `Reactivate ${confirmTarget.name}?`}
            </p>
            {confirmError ? <p className="text-body-sm text-danger">{confirmError}</p> : null}
            <div className="flex gap-2">
              <Button
                variant={confirmTarget.status === "active" ? "destructive" : "primary"}
                loading={confirmBusy}
                onClick={() =>
                  void submitStatusChange(
                    confirmTarget,
                    confirmTarget.status === "active" ? "suspended" : "active"
                  )
                }
              >
                {confirmTarget.status === "active" ? "Suspend" : "Reactivate"}
              </Button>
              <Button variant="secondary" onClick={() => setConfirmTarget(null)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
