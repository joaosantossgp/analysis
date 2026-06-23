import { Link } from "react-router-dom";
import { Panel } from "@/components/surface/Panel";
import { WidgetCommonProps } from "./shared/widgetTypes";
import { useWorkspaceStatus, refreshProgress } from "@/lib/api/updateBase";
import { resolveBridgeMode, resolveWidgetDataState, getBridgeBadgeStyles, getDataStateBadgeStyles } from "@/lib/bridge/badgeResolver";

export function DatabaseStatusCard({
  onRemove,
  isCompact = false,
  isMinimized = false,
  headerControls,
}: WidgetCommonProps) {
  const { activeJob, isRunning, health, diagnostics: diag } = useWorkspaceStatus();
  
  const bridgeEnvMode = resolveBridgeMode();
  const bridgeBadge = getBridgeBadgeStyles(bridgeEnvMode);

  const hasData = Boolean(health);
  const dataState = resolveWidgetDataState({
    isLoading: !health && !diag,
    error: null,
    hasData,
    isOffline: bridgeEnvMode === "browser",
  });
  const dataStateBadge = getDataStateBadgeStyles(dataState);

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
      title={
        <div className="flex items-center gap-1.5">
          <span>Database Health</span>
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border leading-none uppercase tracking-wider font-mono ${bridgeBadge.className}`}>
            {bridgeBadge.text}
          </span>
          {dataStateBadge && (
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border leading-none uppercase tracking-wider font-mono ${dataStateBadge.className}`}>
              {dataStateBadge.text}
            </span>
          )}
        </div>
      }
      subtitle={isMinimized ? undefined : "Local CVM synchronization and diagnostics"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1">
          {headerControls}
          <button
            onClick={onRemove}
            className="text-zinc-550 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
            title="Remove Card"
          >
            ✕
          </button>
        </div>
      }
    >
      {!isMinimized && (
        <div
          className={`font-mono ${isCompact ? "space-y-2.5" : "space-y-3.5"}`}
          style={{ flex: 1, minHeight: 0, overflow: "auto" }}
        >
          {/* Status Header */}
          <div className="flex items-center justify-between">
            <span className="text-zinc-500 text-3xs uppercase tracking-wider">STATUS</span>
            <span className={`text-xs font-semibold ${toneClass}`}>
              {isRunning ? "UPDATING..." : pct > 80 ? "UP TO DATE" : "OUT OF DATE"}
            </span>
          </div>

          {/* CVM Coverage Progress Bar */}
          <div className="space-y-1">
            <div className="flex justify-between text-3xs font-mono text-zinc-500">
              <span>CVM COVERAGE PROGRESS</span>
              <span>{health ? `${pct.toFixed(1)}%` : "—"}</span>
            </div>
            <div className="w-full bg-zinc-950 rounded-full h-1.5 border border-zinc-850 overflow-hidden">
              <div 
                className="bg-emerald-500 h-full transition-all duration-500" 
                style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
              />
            </div>
          </div>

          {/* Active Job Progress */}
          {isRunning && activeJob && (
            <div className="space-y-1 bg-zinc-950/50 border border-orange-500/20 rounded p-2 animate-pulse">
              <div className="flex justify-between text-3xs font-mono text-orange-400">
                <span className="uppercase tracking-wider">Active Update Job ({activeJob.stage})</span>
                <span>{refreshProgress(activeJob)}%</span>
              </div>
              <div className="w-full bg-zinc-900 rounded-full h-1">
                <div 
                  className="bg-orange-500 h-full transition-all duration-300" 
                  style={{ width: `${refreshProgress(activeJob)}%` }}
                />
              </div>
            </div>
          )}

          {/* 3 Metric Blocks Grid */}
          <div className={`grid grid-cols-3 gap-2 border-y border-zinc-850/80 ${isCompact ? "py-2" : "py-3"}`}>
            <div>
              <p className="text-3xs text-zinc-500 uppercase tracking-wider">Coverage</p>
              <p className="text-xs font-bold text-zinc-100 mt-0.5">
                {health ? `${pct.toFixed(1)}%` : "—"}
              </p>
              <p className="text-[9px] text-zinc-550 mt-0.5">{health ? `${health.total_companies} cos` : "—"}</p>
            </div>
            <div>
              <p className="text-3xs text-zinc-500 uppercase tracking-wider">Freshness</p>
              <p className="text-xs font-bold text-zinc-100 mt-0.5 truncate" title={diag?.latest_success_at ? new Date(diag.latest_success_at).toLocaleString() : "Never"}>
                {diag?.latest_success_at
                  ? new Date(diag.latest_success_at).toLocaleDateString("en-US", { month: "short", day: "2-digit" })
                  : "Never"}
              </p>
              <p className="text-[9px] text-zinc-555 mt-0.5 uppercase">Last Sync</p>
            </div>
            <div>
              <p className="text-3xs text-zinc-500 uppercase tracking-wider">Gaps</p>
              <p className="text-xs font-bold text-zinc-100 mt-0.5">
                {health ? health.missing_cells : "—"}
              </p>
              <p className="text-[9px] text-zinc-555 mt-0.5 uppercase">Pending</p>
            </div>
          </div>

          {/* Detailed Coverage by Year */}
          {!isCompact && health?.per_year && health.per_year.length > 0 && (
            <div className="space-y-1.5 border-b border-zinc-850/60 pb-3">
              <span className="text-[9px] text-zinc-500 uppercase tracking-wider block font-semibold">Annual Coverage Gaps</span>
              <div className="grid grid-cols-4 gap-2 text-2xs font-mono">
                {health.per_year.map((y) => (
                  <div key={y.year} className="bg-zinc-950/45 border border-zinc-900 rounded p-1 text-center">
                    <span className="text-zinc-500 block text-3xs font-semibold">{y.year}</span>
                    <span className="text-zinc-200 font-bold">{y.pct.toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Latest Sync Failure Message */}
          {!isCompact && diag?.latest_error && (
            <div className="rounded border border-red-950/30 bg-red-950/10 p-2 text-[10px] text-red-400 space-y-1 font-mono">
              <span className="font-bold block uppercase text-3xs tracking-wider">⚠️ Latest Sync Failure</span>
              <p className="line-clamp-2 leading-relaxed">{diag.latest_error}</p>
            </div>
          )}

          <div className={isCompact ? "pt-0.5" : "pt-1"}>
            <Link
              to="/settings/updates"
              className="flex w-full items-center justify-center rounded bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 hover:text-white text-center text-xs text-zinc-300 py-1.5 transition-colors font-semibold"
            >
              {isRunning ? "View active job →" : "Manage updates & sync →"}
            </Link>
          </div>
        </div>
      )}
    </Panel>
  );
}
