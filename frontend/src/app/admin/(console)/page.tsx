"use client";

import { useState } from "react";
import { toast } from "react-hot-toast";
import { Badge, toneForStatus } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { MetricCard } from "@/components/ui/MetricCard";
import { Modal } from "@/components/ui/Modal";
import { Table, type TableColumn } from "@/components/ui/Table";
import { apiFetch, ApiError } from "@/lib/api";
import { useApiQuery, errorMessage } from "@/lib/useApiQuery";

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

/**
 * T-033: the platform-owner surface (frontend.md 7.3) - one Tenants page,
 * deliberately minimal. Metric cards and suspend/reactivate with a confirm modal.
 */
export default function PlatformHome() {
  const tenantsQuery = useApiQuery<Tenant[]>("/api/platform/tenants");
  const metricsQuery = useApiQuery<Metrics>("/api/platform/metrics");
  const tenants = tenantsQuery.data ?? [];
  const metrics = metricsQuery.data ?? null;
  const metricsError = errorMessage(metricsQuery.error, "Failed to load metrics");

  const [confirmTarget, setConfirmTarget] = useState<Tenant | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  async function submitStatusChange(tenant: Tenant, nextStatus: "active" | "suspended") {
    setConfirmBusy(true);
    try {
      await apiFetch(`/api/platform/tenants/${tenant.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      setConfirmTarget(null);
      toast.success(nextStatus === "suspended" ? "Tenant suspended" : "Tenant reactivated");
      void tenantsQuery.refetch();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : "Failed to update tenant");
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

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-title-2 font-semibold text-text">Tenants</h1>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:max-w-md sm:grid-cols-2">
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
        loading={tenantsQuery.isPending}
        error={errorMessage(tenantsQuery.error, "Failed to load tenants") ?? undefined}
        card
        emptyState={
          <EmptyState
            icon="groups"
            title="No tenants yet"
            description="Tenants appear here after an owner completes self-onboarding."
          />
        }
      />

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
