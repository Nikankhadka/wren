"use client";

import { useState } from "react";
import { Badge } from "./Badge";
import { formatUsd } from "@/lib/money";

export interface TraceToolCall {
  id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  result: unknown;
  success: boolean;
  latency_ms: number | null;
}

export interface TraceCheckVerdict {
  passed: boolean;
  reason: string;
}

export interface TraceTreeProps {
  agentNode: string | null;
  costUsd: number | null;
  toolCalls: TraceToolCall[];
  /** metadata.inspection: per-check {passed, reason}. Shape may vary. */
  inspection?: Record<string, TraceCheckVerdict>;
  loading?: boolean;
  error?: string;
}

/**
 * docs/design/frontend.md section 6: collapsible run tree - agent node -> tool
 * calls (name, args, latency, success), mono font, with loading/error/empty
 * states. The real per-message trace (T-031's conversations detail) is flatter
 * than a full multi-level graph, so the tree is one collapsed row (node name +
 * cost + overall inspection verdict) that expands to the tool calls and the
 * individual inspection check verdicts.
 */
export function TraceTree({
  agentNode,
  costUsd,
  toolCalls,
  inspection,
  loading,
  error,
}: TraceTreeProps) {
  const [open, setOpen] = useState(false);

  if (loading) {
    return (
      <div className="mt-1 rounded-md border border-border bg-surface-sunken p-2">
        <div className="h-4 w-40 animate-pulse rounded bg-surface" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-1 rounded-md border border-border bg-surface-sunken p-2 font-mono text-caption text-danger">
        {error}
      </div>
    );
  }

  const checks = inspection ? Object.entries(inspection) : [];
  const isEmpty = toolCalls.length === 0 && checks.length === 0;

  if (isEmpty) {
    return (
      <div className="mt-1 rounded-md border border-border bg-surface-sunken p-2 font-mono text-caption text-text-tertiary">
        {agentNode ? `${agentNode} - no trace details` : "No trace details"}
      </div>
    );
  }

  const allPassed = checks.every(([, verdict]) => verdict.passed);

  return (
    <div className="mt-1 rounded-md border border-border bg-surface-sunken">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left font-mono text-caption text-text-secondary hover:bg-surface"
      >
        <span aria-hidden="true" className="text-text-tertiary">
          {open ? "▾" : "▸"}
        </span>
        <span className="font-medium text-text">{agentNode ?? "trace"}</span>
        {costUsd !== null ? (
          <span className="tabular-nums text-text-tertiary">{formatUsd(costUsd)}</span>
        ) : null}
        {toolCalls.length > 0 ? (
          <span className="text-text-tertiary">
            {toolCalls.length} tool{toolCalls.length === 1 ? "" : "s"}
          </span>
        ) : null}
        {checks.length > 0 ? (
          <span className="ml-auto">
            <Badge tone={allPassed ? "success" : "danger"}>
              {allPassed ? "inspection ok" : "inspection failed"}
            </Badge>
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="flex flex-col gap-3 border-t border-border px-3 py-2">
          {toolCalls.length > 0 ? (
            <div className="flex flex-col gap-2">
              <p className="font-mono text-caption font-medium uppercase tracking-wide text-text-tertiary">
                Tool calls
              </p>
              {toolCalls.map((call) => (
                <div key={call.id} className="flex flex-col gap-1 font-mono text-caption">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text">{call.tool_name}</span>
                    <Badge tone={call.success ? "success" : "danger"}>
                      {call.success ? "ok" : "failed"}
                    </Badge>
                    {call.latency_ms !== null ? (
                      <span className="tabular-nums text-text-tertiary">{call.latency_ms}ms</span>
                    ) : null}
                  </div>
                  <pre className="overflow-x-auto rounded bg-surface p-2 text-text-secondary">
                    {JSON.stringify(call.arguments, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          ) : null}

          {checks.length > 0 ? (
            <div className="flex flex-col gap-1.5">
              <p className="font-mono text-caption font-medium uppercase tracking-wide text-text-tertiary">
                Inspection
              </p>
              {checks.map(([name, verdict]) => (
                <div key={name} className="flex items-start gap-2 font-mono text-caption">
                  <Badge tone={verdict.passed ? "success" : "danger"}>
                    {verdict.passed ? "pass" : "fail"}
                  </Badge>
                  <span className="text-text">{name}</span>
                  {verdict.reason ? (
                    <span className="text-text-tertiary">{verdict.reason}</span>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
