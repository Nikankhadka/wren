"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Badge, toneForStatus } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Table, type TableColumn } from "@/components/ui/Table";
import { apiFetch, ApiError } from "@/lib/api";

interface Escalation {
  id: string;
  conversation_id: string;
  reason: string;
  status: string;
  created_at: string;
  resolved_at: string | null;
}

function formatAge(iso: string): string {
  const then = new Date(iso).getTime();
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * T-031: Escalations queue (frontend.md 7.2). Claim/resolve actions per row;
 * resolving can post a human_agent reply into the transcript. A 409 (someone
 * else already moved the row) refetches rather than crashing.
 */
export default function EscalationsPage() {
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolveMessage, setResolveMessage] = useState("");
  const [rowError, setRowError] = useState<Record<string, string>>({});

  async function refresh() {
    try {
      const rows = await apiFetch<Escalation[]>("/api/escalations");
      setEscalations(rows);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load escalations");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    apiFetch<Escalation[]>("/api/escalations")
      .then((rows) => {
        if (!active) return;
        setEscalations(rows);
        setError(null);
      })
      .catch((err) => {
        if (active) setError(err instanceof ApiError ? err.detail : "Failed to load escalations");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function setErrorFor(id: string, message: string | null) {
    setRowError((prev) => {
      const next = { ...prev };
      if (message === null) delete next[id];
      else next[id] = message;
      return next;
    });
  }

  async function claim(id: string) {
    setBusyId(id);
    setErrorFor(id, null);
    try {
      await apiFetch(`/api/escalations/${id}/claim`, { method: "POST" });
      await refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Someone else already moved it - resync the row rather than crash.
        setErrorFor(id, err.detail);
        await refresh();
      } else {
        setErrorFor(id, err instanceof ApiError ? err.detail : "Failed to claim");
      }
    } finally {
      setBusyId(null);
    }
  }

  async function resolve(id: string) {
    setBusyId(id);
    setErrorFor(id, null);
    const message = resolveMessage.trim();
    try {
      await apiFetch(`/api/escalations/${id}/resolve`, {
        method: "POST",
        body: JSON.stringify({ message: message || null }),
      });
      setResolvingId(null);
      setResolveMessage("");
      await refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setErrorFor(id, err.detail);
        setResolvingId(null);
        await refresh();
      } else {
        setErrorFor(id, err instanceof ApiError ? err.detail : "Failed to resolve");
      }
    } finally {
      setBusyId(null);
    }
  }

  const columns: TableColumn<Escalation>[] = [
    { key: "reason", header: "Reason", render: (row) => row.reason },
    {
      key: "conversation",
      header: "Conversation",
      render: (row) => (
        <Link
          href={`/conversations/${row.conversation_id}`}
          className="font-medium text-accent hover:text-accent-hover"
        >
          View transcript
        </Link>
      ),
    },
    {
      key: "age",
      header: "Age",
      render: (row) => <span className="text-text-secondary">{formatAge(row.created_at)}</span>,
    },
    {
      key: "status",
      header: "Status",
      render: (row) => <Badge tone={toneForStatus(row.status)}>{row.status}</Badge>,
    },
    {
      key: "actions",
      header: "",
      render: (row) => {
        const isResolved = row.status === "resolved";
        if (isResolved) {
          return <span className="text-footnote text-text-tertiary">Resolved</span>;
        }
        const busy = busyId === row.id;
        return (
          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              {row.status === "open" ? (
                <Button size="sm" variant="secondary" loading={busy} onClick={() => claim(row.id)}>
                  Claim
                </Button>
              ) : null}
              <Button
                size="sm"
                loading={busy && resolvingId !== row.id}
                onClick={() => {
                  // Opening/switching rows always starts from a blank draft -
                  // a reply typed for one escalation must never carry over to
                  // another row's customer.
                  setResolvingId((prev) => (prev === row.id ? null : row.id));
                  setResolveMessage("");
                }}
              >
                Resolve
              </Button>
            </div>
            {resolvingId === row.id ? (
              <div className="flex w-72 flex-col gap-2">
                <textarea
                  aria-label="Reply to the customer (optional)"
                  value={resolveMessage}
                  onChange={(e) => setResolveMessage(e.target.value)}
                  placeholder="Optional reply to the customer..."
                  rows={3}
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-body-sm text-text placeholder:text-text-tertiary transition-colors duration-fast hover:border-border-strong"
                />
                <div className="flex items-center gap-2">
                  <Button size="sm" loading={busy} onClick={() => resolve(row.id)}>
                    Send &amp; resolve
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setResolvingId(null);
                      setResolveMessage("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : null}
            {rowError[row.id] ? (
              <p className="text-footnote text-danger">{rowError[row.id]}</p>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <div className="flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-title-2 font-semibold text-text">Escalations</h1>
        <p className="mt-1 text-body-sm text-text-secondary">
          Conversations your assistant handed off for a human to take over.
        </p>
      </div>

      <Table
        columns={columns}
        rows={escalations}
        rowKey={(row) => row.id}
        loading={loading}
        error={error ?? undefined}
        emptyState={
          <EmptyState
            title="Nothing needs you right now."
            description="When your assistant escalates a conversation, it will appear here."
          />
        }
      />
    </div>
  );
}
