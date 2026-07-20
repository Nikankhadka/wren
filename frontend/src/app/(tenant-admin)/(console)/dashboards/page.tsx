"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { MetricCard } from "@/components/ui/MetricCard";
import { Sparkline } from "@/components/ui/Sparkline";
import { apiFetch, ApiError } from "@/lib/api";

// --- API response shapes (mirror backend/app/api/dashboards.py Pydantic models).
interface DailyCost {
  day: string; // pydantic `date` -> ISO "YYYY-MM-DD"
  cost_usd: number;
}

interface CostDashboard {
  cost_today_usd: number;
  cost_yesterday_usd: number;
  cost_this_month_usd: number;
  cost_prev_month_usd: number;
  avg_cost_per_conversation_usd: number | null;
  conversation_count: number;
  escalated_conversation_count: number;
  escalation_rate: number | null;
  daily_costs: DailyCost[];
}

interface EvalCheck {
  metric: string;
  value: number | null;
  threshold: number;
  passed: boolean;
}

interface EvalRunSummary {
  run_type: string;
  created_at: string; // ISO datetime
  git_sha: string;
  metrics: Record<string, unknown>;
  checks: EvalCheck[];
  passed: boolean;
}

interface EvalDashboard {
  runs: EvalRunSummary[];
}

/**
 * These are float cost-observability dollars - database.md section 7's single
 * non-cents money column, summed straight from cost_logs. They are deliberately
 * NOT formatted through lib/money.ts (formatCents): that path is the
 * deterministic-pricing quote engine, which works in integer cents and must
 * never be mixed with these floating observability numbers (a real invariant
 * violation, per the deterministic-pricing hard rule). Kept separate on purpose.
 */
function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

/** Per-conversation averages are routinely sub-cent, so 2dp would read as "$0.00".
 * Widen precision only when the magnitude needs it. Still float observability
 * money, still never the cents pricing path. */
function formatUsdPrecise(value: number): string {
  if (value === 0) return "$0.00";
  return `$${value.toFixed(value < 0.1 ? 4 : 2)}`;
}

function formatPercent(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

function trendVs(
  current: number,
  previous: number,
  previousLabel: string
): { direction: "up" | "down" | "flat"; label: string } {
  const direction = current > previous ? "up" : current < previous ? "down" : "flat";
  return { direction, label: `vs ${formatUsd(previous)} ${previousLabel}` };
}

function formatEvalValue(value: number | null): string {
  return value === null ? "missing" : value.toFixed(2);
}

function titleCase(runType: string): string {
  return runType.charAt(0).toUpperCase() + runType.slice(1);
}

function SectionError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-border bg-surface p-6 shadow-1">
      <p className="text-body-sm text-danger">{message}</p>
      <Button size="sm" variant="secondary" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

/**
 * T-034: Surface-2 Dashboards tab (frontend.md 7.2). Two independent loads -
 * cost/volume metrics and the latest eval run per type - each with its own
 * loading/error state so one failing section never blanks the other.
 */
export default function DashboardsPage() {
  const [costs, setCosts] = useState<CostDashboard | null>(null);
  const [costsLoading, setCostsLoading] = useState(true);
  const [costsError, setCostsError] = useState<string | null>(null);
  const [costsNonce, setCostsNonce] = useState(0);

  const [evals, setEvals] = useState<EvalDashboard | null>(null);
  const [evalsLoading, setEvalsLoading] = useState(true);
  const [evalsError, setEvalsError] = useState<string | null>(null);
  const [evalsNonce, setEvalsNonce] = useState(0);

  useEffect(() => {
    let active = true;
    apiFetch<CostDashboard>("/api/dashboards/costs")
      .then((data) => {
        if (!active) return;
        setCosts(data);
        setCostsError(null);
      })
      .catch((err) => {
        if (!active) return;
        setCostsError(err instanceof ApiError ? err.detail : "Failed to load cost metrics");
      })
      .finally(() => {
        if (active) setCostsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [costsNonce]);

  useEffect(() => {
    let active = true;
    apiFetch<EvalDashboard>("/api/dashboards/evals")
      .then((data) => {
        if (!active) return;
        setEvals(data);
        setEvalsError(null);
      })
      .catch((err) => {
        if (!active) return;
        setEvalsError(err instanceof ApiError ? err.detail : "Failed to load eval runs");
      })
      .finally(() => {
        if (active) setEvalsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [evalsNonce]);

  const thirtyDayTotal = costs
    ? costs.daily_costs.reduce((sum, d) => sum + d.cost_usd, 0)
    : 0;

  return (
    <div className="flex flex-col gap-8 p-8">
      <div>
        <h1 className="text-title-2 font-semibold text-text">Dashboards</h1>
        <p className="mt-1 text-body-sm text-text-secondary">
          Cost, conversation volume, and the latest eval gate results for your assistant.
        </p>
      </div>

      <section className="flex flex-col gap-4">
        <h2 className="text-title-3 font-semibold text-text">Cost and volume</h2>
        {costsError ? (
          <SectionError
            message={costsError}
            onRetry={() => {
              setCostsError(null);
              setCostsLoading(true);
              setCostsNonce((n) => n + 1);
            }}
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Cost today"
              value={costs ? formatUsd(costs.cost_today_usd) : ""}
              loading={costsLoading}
              icon="paid"
              trend={
                costs
                  ? trendVs(costs.cost_today_usd, costs.cost_yesterday_usd, "yesterday")
                  : undefined
              }
            />
            <MetricCard
              label="Cost this month"
              value={costs ? formatUsd(costs.cost_this_month_usd) : ""}
              loading={costsLoading}
              icon="paid"
              trend={
                costs
                  ? trendVs(costs.cost_this_month_usd, costs.cost_prev_month_usd, "last month")
                  : undefined
              }
            />
            <MetricCard
              label="Avg cost / conversation"
              value={
                costs
                  ? costs.avg_cost_per_conversation_usd === null
                    ? "-"
                    : formatUsdPrecise(costs.avg_cost_per_conversation_usd)
                  : ""
              }
              loading={costsLoading}
              icon="paid"
              footer={
                costs && costs.avg_cost_per_conversation_usd === null ? (
                  <p className="text-footnote text-text-secondary">no costed conversations yet</p>
                ) : undefined
              }
            />
            <MetricCard
              label="Conversations"
              value={costs ? String(costs.conversation_count) : ""}
              loading={costsLoading}
              icon="forum"
              footer={
                costs && costs.conversation_count === 0 ? (
                  <p className="text-footnote text-text-secondary">
                    No conversations yet - share your chat link
                  </p>
                ) : undefined
              }
            />
            <MetricCard
              label="Escalation rate"
              value={
                costs
                  ? costs.escalation_rate === null
                    ? "-"
                    : formatPercent(costs.escalation_rate)
                  : ""
              }
              loading={costsLoading}
              icon="support_agent"
              footer={
                costs && costs.escalation_rate !== null ? (
                  <p className="text-footnote text-text-secondary">
                    {costs.escalated_conversation_count} of {costs.conversation_count} conversations
                  </p>
                ) : undefined
              }
            />
            <div className="sm:col-span-2 xl:col-span-4">
              <MetricCard
                label="30-day cost"
                value={costs ? formatUsd(thirtyDayTotal) : ""}
                loading={costsLoading}
                icon="paid"
                footer={
                  costs ? (
                    <Sparkline
                      points={costs.daily_costs.map((d) => d.cost_usd)}
                      label="30-day daily cost"
                      format={formatUsd}
                    />
                  ) : undefined
                }
              />
            </div>
          </div>
        )}
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-title-3 font-semibold text-text">Eval runs</h2>
        {evalsError ? (
          <SectionError
            message={evalsError}
            onRetry={() => {
              setEvalsError(null);
              setEvalsLoading(true);
              setEvalsNonce((n) => n + 1);
            }}
          />
        ) : evalsLoading && !evals ? (
          <div className="h-32 animate-pulse rounded-lg border border-border bg-surface-sunken" />
        ) : evals && evals.runs.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface shadow-1">
            <EmptyState
              icon="verified_user"
              title="No eval runs recorded for this tenant yet"
              description="Evals run in CI against seeded test tenants, so a fresh business normally has none."
            />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {evals?.runs.map((run) => (
              <div
                key={run.run_type}
                className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-6 shadow-1"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="text-body font-semibold text-text">
                      {titleCase(run.run_type)}
                    </span>
                    <Badge tone={run.passed ? "success" : "danger"}>
                      {run.passed ? "Passed" : "Failed"}
                    </Badge>
                  </div>
                  <span className="text-footnote text-text-secondary">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {run.checks.map((check) => (
                    <span
                      key={check.metric}
                      className={`inline-flex items-center rounded-md px-2.5 py-1 text-footnote font-medium ${
                        check.value === null
                          ? "bg-danger-subtle text-danger"
                          : check.passed
                            ? "bg-success-subtle text-success"
                            : "bg-danger-subtle text-danger"
                      }`}
                    >
                      <span className="tabular-nums">
                        {check.metric} {formatEvalValue(check.value)} vs{" "}
                        {check.threshold.toFixed(2)}
                      </span>
                    </span>
                  ))}
                </div>
                <p className="font-mono text-footnote text-text-tertiary">{run.git_sha}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
