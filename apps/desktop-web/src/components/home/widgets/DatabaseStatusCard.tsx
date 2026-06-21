import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  defaultRefreshWindow,
  fetchBaseHealth,
  fetchDatabaseDiagnostics,
  fetchRefreshJobs,
  isActiveRefreshJob,
} from "@/lib/api/updateBase";
import { Panel } from "@/components/surface/Panel";
import { WidgetCommonProps } from "./shared/widgetTypes";

export function DatabaseStatusCard({
  onRemove,
  isCompact = false,
  isMinimized = false,
  headerControls,
}: WidgetCommonProps) {
  const defaults = useMemo(() => defaultRefreshWindow(), []);
  const jobsQuery = useQuery({
    queryKey: ["refresh-jobs"],
    queryFn: fetchRefreshJobs,
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
    refetchInterval: isRunning ? 5_000 : false,
  });
  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.snapshot : null;

  const diagQuery = useQuery({
    queryKey: ["db-diagnostics"],
    queryFn: () => fetchDatabaseDiagnostics({ summaryOnly: true }),
    refetchInterval: isRunning ? 5_000 : 30_000,
  });
  const diag = diagQuery.data?.mode === "desktop" ? diagQuery.data.diagnostics : null;

  const pct = health ? health.pct : 0;
  const tone = pct > 80 ? "good" : pct > 0 ? "warn" : "neutral";
  const toneClass =
    tone === "good"
      ? "text-emerald-400"
      : tone === "warn"
        ? "text-amber-400"
        : "text-zinc-400";

  return (
    <Panel
      title="Database Monitor"
      subtitle={isMinimized ? undefined : "Local synchronization status"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1">
          {headerControls}
          <button
            onClick={onRemove}
            className="text-zinc-500 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
            title="Remove Card"
          >
            ✕
          </button>
        </div>
      }
    >
      {!isMinimized && (
        <div
          className={`font-mono ${isCompact ? "space-y-1.5" : "space-y-3"}`}
          style={{ flex: 1, minHeight: 0, overflow: "auto" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-zinc-500 text-xs">STATUS</span>
            <span className={`text-xs font-semibold ${toneClass}`}>
              {isRunning ? "UPDATING..." : pct > 80 ? "UP TO DATE" : "OUT OF DATE"}
            </span>
          </div>

          <div className={`grid grid-cols-2 gap-4 border-y border-zinc-850 ${isCompact ? "py-1.5" : "py-3"}`}>
            <div>
              <p className="text-2xs text-zinc-500">COVERAGE</p>
              <p className={`${isCompact ? "text-sm" : "text-lg"} font-semibold text-zinc-200`}>
                {health ? `${pct.toFixed(1)}%` : "—"}
              </p>
            </div>
            <div>
              <p className="text-2xs text-zinc-500">COMPANIES</p>
              <p className={`${isCompact ? "text-sm" : "text-lg"} font-semibold text-zinc-200`}>
                {health ? health.total_companies : "—"}
              </p>
            </div>
          </div>

          <div className="text-2xs text-zinc-500 space-y-0.5">
            <p>
              Last update:{" "}
              <span className="text-zinc-300">
                {diag?.latest_success_at
                  ? new Date(diag.latest_success_at).toLocaleString("en-US", {
                      dateStyle: "short",
                      timeStyle: "short",
                    })
                  : "Never"}
              </span>
            </p>
            <p>
              Pending Gaps:{" "}
              <span className="text-zinc-300">
                {health ? health.missing_cells : "—"}
              </span>
            </p>
          </div>

          <div className={isCompact ? "pt-1" : "pt-2"}>
            <Link
              to="/settings/updates"
              className="flex w-full items-center justify-center rounded bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-center text-xs text-zinc-300 py-1 transition-colors"
            >
              {isRunning ? "View active job →" : "Manage updates →"}
            </Link>
          </div>
        </div>
      )}
    </Panel>
  );
}
