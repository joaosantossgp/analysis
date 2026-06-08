import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  defaultRefreshWindow,
  fetchBaseHealth,
  fetchDatabaseDiagnostics,
  fetchRefreshJobs,
  isActiveRefreshJob,
} from "@/lib/api/updateBase";
import { StateBanner } from "@/components/feedback/StateBanner";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { BaseHealthSnapshot } from "@/lib/bridge/types";

/**
 * Home page: compact status summary + quick navigation.
 *
 * This page is intentionally NOT an update control center — that lives on
 * `/atualizar-base`. Home reads the same status sources (base-health,
 * db-diagnostics, refresh-jobs) so the user sees consistent values
 * everywhere, but every action delegates to the central update page.
 */
export function HomePage() {
  const defaults = useMemo(() => defaultRefreshWindow(), []);
  const [bridgeReady, setBridgeReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const jobsQuery = useQuery({
    queryKey: ["refresh-jobs"],
    queryFn: fetchRefreshJobs,
    enabled: bridgeReady,
    refetchInterval: 10_000,
  });
  const jobs = jobsQuery.data?.mode === "desktop" ? jobsQuery.data.items : [];
  const activeJob = jobs.find(isActiveRefreshJob) ?? null;
  const isRunning = Boolean(activeJob);

  const healthQuery = useQuery({
    queryKey: ["base-health", defaults.startYear, defaults.endYear],
    queryFn: () =>
      fetchBaseHealth({
        startYear: defaults.startYear,
        endYear: defaults.endYear,
        forceRefresh: false,
      }),
    enabled: bridgeReady,
    refetchInterval: isRunning ? 5_000 : false,
  });
  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.snapshot : null;

  const diagQuery = useQuery({
    queryKey: ["db-diagnostics"],
    queryFn: () => fetchDatabaseDiagnostics({ summaryOnly: true }),
    enabled: bridgeReady,
    refetchInterval: isRunning ? 5_000 : 30_000,
  });
  const diag = diagQuery.data?.mode === "desktop" ? diagQuery.data.diagnostics : null;

  const browserReason =
    healthQuery.data?.mode === "browser" ? healthQuery.data.reason : null;

  return (
    <section className="space-y-5 p-6">
      {browserReason ? (
        <StateBanner variant="browser-only" message={browserReason} />
      ) : null}

      <StatusSummaryCard
        bridgeReady={bridgeReady}
        health={health}
        lastUpdate={diag?.latest_success_at ?? null}
        isRunning={isRunning}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <QuickNavCard
          to="/empresas"
          title="Companies"
          value={health ? fmtInt(health.total_companies) : "—"}
          detail={
            health
              ? `${fmtInt(health.companies_with_historical_data)} with history`
              : "Loading…"
          }
          accent="cyan"
        />
        <QuickNavCard
          to="/setores"
          title="Sectors"
          value="11"
          detail="GICS sectors available"
          accent="neutral"
        />
        <QuickNavCard
          to="/data-coverage"
          title="Coverage"
          value={health ? fmtPct(health.pct) : "—"}
          detail={
            health
              ? `${fmtInt(health.missing_cells)} pending`
              : "Loading…"
          }
          accent={
            health && health.pct > 80
              ? "green"
              : health && health.pct > 0
                ? "amber"
            : "neutral"
          }
        />
        <QuickNavCard
          to="/settings"
          title="Settings"
          value="DATA"
          detail="local bases and imports"
          accent="neutral"
        />
      </div>
    </section>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusSummaryCard({
  bridgeReady,
  health,
  lastUpdate,
  isRunning,
}: {
  bridgeReady: boolean;
  health: BaseHealthSnapshot | null;
  lastUpdate: string | null;
  isRunning: boolean;
}) {
  const { message, tone } = deriveStatus(health, isRunning, bridgeReady);
  const toneClass =
    tone === "good"
      ? "text-emerald-300"
      : tone === "warn"
        ? "text-amber-200"
        : "text-zinc-300";

  const pendingCount = health ? health.missing_cells : null;

  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-5 shadow-lg">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-wider text-zinc-500">
            Database Status
          </p>
          <p className={`mt-2 text-sm font-medium ${toneClass}`}>{message}</p>
          {lastUpdate ? (
            <p className="mt-1 text-xs text-zinc-500">
              Last update:{" "}
              <span className="text-zinc-300">{fmtDateTime(lastUpdate)}</span>
            </p>
          ) : null}
          {pendingCount != null ? (
            <p className="mt-1 text-xs text-zinc-500">
              Pending issues: <span className="text-zinc-300">{fmtInt(pendingCount)}</span>
            </p>
          ) : null}
        </div>
        <div className="shrink-0">
          <Link
            to="/atualizar-base"
            className="inline-flex items-center rounded-md border border-cyan-600/50 bg-cyan-500/10 px-4 py-2 text-sm font-medium text-cyan-100 hover:bg-cyan-500/15"
          >
            {isRunning ? "Update in progress →" : "Manage database →"}
          </Link>
        </div>
      </div>
    </article>
  );
}

function QuickNavCard({
  to,
  title,
  value,
  detail,
  accent,
}: {
  to: string;
  title: string;
  value: string;
  detail: string;
  accent: "cyan" | "green" | "amber" | "neutral";
}) {
  const borderClass =
    accent === "cyan"
      ? "border-cyan-500/30 hover:border-cyan-400/50"
      : accent === "green"
        ? "border-emerald-500/30 hover:border-emerald-400/50"
        : accent === "amber"
          ? "border-amber-500/30 hover:border-amber-400/50"
          : "border-zinc-800 hover:border-zinc-600";

  const valueClass =
    accent === "cyan"
      ? "text-cyan-200"
      : accent === "green"
        ? "text-emerald-200"
        : accent === "amber"
          ? "text-amber-200"
          : "text-zinc-100";

  return (
    <Link
      to={to}
      className={`block rounded-lg border bg-zinc-900/60 p-4 shadow-lg transition-colors ${borderClass}`}
    >
      <p className="text-xs uppercase tracking-wider text-zinc-500">{title}</p>
      <p className={`mt-2 font-mono text-2xl font-semibold ${valueClass}`}>{value}</p>
      <p className="mt-1 text-xs text-zinc-400">{detail} →</p>
    </Link>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function deriveStatus(
  health: BaseHealthSnapshot | null,
  isRunning: boolean,
  bridgeReady: boolean,
): { message: string; tone: "good" | "warn" | "neutral" } {
  if (!bridgeReady) return { message: "Connecting to bridge…", tone: "neutral" };
  if (isRunning) return { message: "Updating local database…", tone: "warn" };
  if (!health) return { message: "Checking database status…", tone: "neutral" };
  if (health.pct > 80) return { message: "Database is up to date.", tone: "good" };
  if (health.pct > 0)
    return {
      message: "Database partially updated. Some companies have pending issues.",
      tone: "warn",
    };
  return { message: "Database may be out of date.", tone: "warn" };
}

function fmtInt(value: number | null | undefined): string {
  return new Intl.NumberFormat("en-US").format(Number(value ?? 0));
}

function fmtPct(value: number | null | undefined): string {
  return `${Number(value ?? 0).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
}

function fmtDateTime(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-US", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
