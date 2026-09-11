"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Badge, toneForStatus } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Select } from "@/components/ui/Select";
import { Table, type TableColumn } from "@/components/ui/Table";
import { useApiQuery, errorMessage } from "@/lib/useApiQuery";
import type { ConversationSummary } from "@/lib/api-schemas";

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "open", label: "Open" },
  { value: "escalated", label: "Escalated" },
  { value: "closed", label: "Closed" },
];

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

/**
 * T-031: Conversations tab (frontend.md 7.2). Status-filtered list; a row
 * opens the full-transcript detail with per-message trace.
 */
export default function ConversationsPage() {
  const router = useRouter();
  const [status, setStatus] = useState("all");
  const query = status === "all" ? "" : `?status=${status}`;
  const { data, isPending, error } = useApiQuery<ConversationSummary[]>(
    `/api/conversations${query}`,
    { queryKey: ["conversations", status] },
  );
  const conversations = data ?? [];

  const columns: TableColumn<ConversationSummary>[] = useMemo(
    () => [
      {
        key: "customer_ref",
        header: "Customer",
        render: (row) => (
          <Link
            href={`/conversations/${row.id}`}
            className="font-medium text-accent-active transition-colors duration-(--duration-fast) hover:underline active:opacity-60"
            onClick={(e) => e.stopPropagation()}
          >
            {row.customer_ref ?? "Anonymous"}
          </Link>
        ),
      },
      {
        key: "created_at",
        header: "Started",
        render: (row) => formatDateTime(row.created_at),
      },
      {
        key: "status",
        header: "Status",
        render: (row) => <Badge tone={toneForStatus(row.status)}>{row.status}</Badge>,
      },
      {
        key: "message_count",
        header: "Messages",
        render: (row) => <span className="tabular-nums">{row.message_count}</span>,
      },
    ],
    [],
  );

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-title-2 font-semibold text-text">Conversations</h1>
        <p className="mt-1 text-body-sm text-text-secondary">
          Every conversation your assistant has handled, with a per-message trace.
        </p>
      </div>

      <div className="max-w-xs">
        <Select
          label="Filter by status"
          options={STATUS_OPTIONS}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        />
      </div>

      <Table
        columns={columns}
        rows={conversations}
        rowKey={(row) => row.id}
        loading={isPending}
        error={errorMessage(error, "Failed to load conversations") ?? undefined}
        onRowClick={(row) => router.push(`/conversations/${row.id}`)}
        card
        emptyState={
          <EmptyState
            title="No conversations yet"
            description="Once customers start chatting, they'll show up here."
          />
        }
      />
    </div>
  );
}
