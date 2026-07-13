"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Badge, toneForStatus } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Select } from "@/components/ui/Select";
import { Table, type TableColumn } from "@/components/ui/Table";
import { apiFetch, ApiError } from "@/lib/api";

interface ConversationSummary {
  id: string;
  customer_ref: string | null;
  status: string;
  created_at: string;
  message_count: number;
}

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
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const query = status === "all" ? "" : `?status=${status}`;
    apiFetch<ConversationSummary[]>(`/api/conversations${query}`)
      .then((rows) => {
        if (!active) return;
        setConversations(rows);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof ApiError ? err.detail : "Failed to load conversations");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [status]);

  const columns: TableColumn<ConversationSummary>[] = [
    {
      key: "customer_ref",
      header: "Customer",
      render: (row) => (
        <Link
          href={`/conversations/${row.id}`}
          className="font-medium text-accent hover:text-accent-hover"
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
  ];

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
          onChange={(e) => {
            setLoading(true);
            setStatus(e.target.value);
          }}
        />
      </div>

      <Table
        columns={columns}
        rows={conversations}
        rowKey={(row) => row.id}
        loading={loading}
        error={error ?? undefined}
        onRowClick={(row) => router.push(`/conversations/${row.id}`)}
        emptyState={
          <EmptyState
            title="No conversations yet"
            description="Once customers start chatting with your assistant, they'll show up here."
          />
        }
      />
    </div>
  );
}
