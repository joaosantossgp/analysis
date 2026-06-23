import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  fetchCoverageUniverses,
  fetchCoveragePriorityScores,
} from "@/lib/api/coverage";
import { Panel } from "@/components/surface/Panel";
import { downloadCsvFile } from "./shared/csvExport";
import { PriorityQueueConfig, WidgetCommonProps } from "./shared/widgetTypes";
import { resolveBridgeMode, resolveWidgetDataState, getBridgeBadgeStyles, getDataStateBadgeStyles } from "@/lib/bridge/badgeResolver";

interface PriorityQueueCardProps extends WidgetCommonProps {
  config?: PriorityQueueConfig;
  onConfigure: (newCfg: PriorityQueueConfig) => void;
}

export function PriorityQueueCard({
  config = { universeId: "" },
  onConfigure,
  onRemove,
  isCompact = false,
  isMinimized = false,
  isFocused = false,
  headerControls,
}: PriorityQueueCardProps) {
  const [isConfiguring, setIsConfiguring] = useState(false);
  const [selectedTier, setSelectedTier] = useState<string>("ALL");
  const [selectedSector, setSelectedSector] = useState<string>("ALL");

  const universesQuery = useQuery({
    queryKey: ["coverage-universes"],
    queryFn: fetchCoverageUniverses,
  });
  const universes = universesQuery.data || [];

  const activeUniverse = universes.find((u) => u.id === config.universeId) || null;

  const priorityQuery = useQuery({
    queryKey: ["priority-scores", config.universeId],
    queryFn: () => fetchCoveragePriorityScores(config.universeId),
    enabled: Boolean(config.universeId),
  });
  const priorities = priorityQuery.data || [];

  const bridgeEnvMode = resolveBridgeMode();
  const bridgeBadge = getBridgeBadgeStyles(bridgeEnvMode);

  const hasData = config.universeId !== "" && priorities.length > 0;
  const dataState = resolveWidgetDataState({
    isLoading: priorityQuery.isLoading,
    error: priorityQuery.error,
    hasData,
    isOffline: bridgeEnvMode === "browser",
  });
  const dataStateBadge = getDataStateBadgeStyles(dataState);

  // Extract unique sectors dynamically from the priorities dataset
  const uniqueSectors = useMemo(() => {
    const sectors = new Set<string>();
    priorities.forEach((p: any) => {
      const s = p.gics_sector || p.setor_analitico;
      if (s && s !== "Unknown") sectors.add(s);
    });
    return Array.from(sectors).sort();
  }, [priorities]);

  const filteredPriorities = useMemo(() => {
    return priorities.filter((item: any) => {
      const matchTier = selectedTier === "ALL" || item.tier === selectedTier;
      const sector = item.gics_sector || item.setor_analitico;
      const matchSector = selectedSector === "ALL" || sector === selectedSector;
      return matchTier && matchSector;
    });
  }, [priorities, selectedTier, selectedSector]);

  // Sort by final_score (high to low)
  const topPriorities = useMemo(() => {
    return [...filteredPriorities]
      .sort((a, b) => (b.final_score ?? 0) - (a.final_score ?? 0))
      .slice(0, isFocused ? 25 : isCompact ? 5 : 8);
  }, [filteredPriorities, isCompact, isFocused]);

  const selectUniverse = (id: string) => {
    onConfigure({ universeId: id });
    setIsConfiguring(false);
    setSelectedTier("ALL");
    setSelectedSector("ALL");
  };

  const handleExportCSV = () => {
    if (!priorities || priorities.length === 0) return;
    const headers = ["Company Name", "CVM Code", "Ticker", "Tier", "Priority Score", "Pending Gaps"];
    const rows = priorities.map((item) => [
      item.company_name,
      item.cd_cvm,
      item.ticker_b3 || "",
      item.tier || "—",
      item.final_score ?? 0,
      item.missing_factors?.join("; ") || "None",
    ]);
    downloadCsvFile({
      filename: `priority_queue_${config.universeId || "all"}.csv`,
      headers,
      rows,
    });
  };

  return (
    <Panel
      title={
        <div className="flex items-center gap-1.5">
          <span>Priority Queue</span>
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border leading-none uppercase tracking-wider font-mono ${bridgeBadge.className}`}>
            {bridgeBadge.text}
          </span>
          {dataStateBadge && (
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border leading-none uppercase tracking-wider font-mono ${dataStateBadge.className}`}>
              {dataStateBadge.text}
            </span>
          )}
          {activeUniverse && (
            <span className="text-[9px] font-bold bg-zinc-900 border border-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded leading-none uppercase font-mono">
              {activeUniverse.name}
            </span>
          )}
        </div>
      }
      subtitle={isMinimized ? undefined : "Operational coverage priorities and action list"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1.5">
          {!isMinimized && (
            <button
              onClick={() => setIsConfiguring(!isConfiguring)}
              className="text-zinc-555 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
              title="Configure Universe"
            >
              ⚙
            </button>
          )}
          {isFocused && (
            <button
              onClick={handleExportCSV}
              className="text-orange-400 hover:text-orange-300 font-mono text-3xs border border-zinc-850 bg-zinc-950 rounded px-1.5 py-0.5 transition-colors mr-1"
              title="Export Queue to CSV"
            >
              ⬇ CSV
            </button>
          )}
          {headerControls}
          <button
            onClick={onRemove}
            className="text-zinc-555 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
            title="Remove Card"
          >
            ✕
          </button>
        </div>
      }
    >
      {!isMinimized && (
        <div
          className="space-y-2.5 flex flex-col"
          style={{ flex: 1, minHeight: 0, overflow: isConfiguring ? "auto" : (config.universeId ? "auto" : "hidden") }}
        >
          {isConfiguring ? (
            <div className="space-y-2 flex flex-col flex-1 min-h-0">
              <p className="text-2xs font-mono text-zinc-555 uppercase shrink-0">Select Coverage Universe</p>
              {universes.length === 0 ? (
                <p className="text-2xs font-mono text-zinc-650 shrink-0">No universes available.</p>
              ) : (
                <div className="flex-1 min-h-0 overflow-y-auto space-y-1 font-mono text-2xs border-t border-zinc-900 mt-2">
                  {universes.map((u) => (
                    <button
                      key={u.id}
                      onClick={() => selectUniverse(u.id)}
                      className="w-full text-left p-1 rounded hover:bg-zinc-800 text-zinc-300 hover:text-white"
                    >
                      {u.name} ({u.company_count} cos)
                    </button>
                  ))}
                </div>
              )}
              {config.universeId && (
                <button
                  onClick={() => setIsConfiguring(false)}
                  className="w-full text-center py-1 text-2xs font-mono text-orange-400 hover:text-orange-300 underline shrink-0 mt-2"
                >
                  Done selecting
                </button>
              )}
            </div>
          ) : !config.universeId ? (
            <div className="flex flex-col items-center justify-center p-3 py-3.5 border border-dashed border-zinc-850 rounded-md bg-zinc-900/5 text-center font-mono space-y-2 flex-1 min-h-0">
              <span className="text-zinc-500 text-sm">⚙</span>
              <div>
                <p className="text-2xs font-bold text-zinc-300">No coverage universe selected</p>
                <p className="text-3xs text-zinc-550 max-w-xs leading-normal mt-0.5">
                  Select a universe to view priority rankings based on market cap, volume, and coverage gaps.
                </p>
              </div>
              <button
                onClick={() => setIsConfiguring(true)}
                className="rounded border border-zinc-800 hover:border-zinc-700 bg-zinc-950 px-2 py-1 text-3xs font-bold text-orange-400 hover:text-orange-300 transition-colors uppercase tracking-wider"
              >
                Select Universe
              </button>
            </div>
          ) : priorityQuery.isLoading ? (
            <p className="py-4 text-center font-mono text-2xs text-zinc-600 shrink-0">Loading priority rankings...</p>
          ) : (
            <>
              {/* Filter Controls Row */}
              <div className="flex flex-wrap items-center gap-2 text-3xs border-b border-zinc-900 pb-2 mb-0.5 font-mono">
                <span className="text-zinc-555 uppercase">Filters:</span>
                <select
                  value={selectedTier}
                  onChange={(e) => setSelectedTier(e.target.value)}
                  className="bg-zinc-950 border border-zinc-850 rounded px-1 py-0.5 text-zinc-400 hover:text-zinc-200 outline-none cursor-pointer text-4xs uppercase"
                >
                  <option value="ALL">All Tiers</option>
                  <option value="Tier 1">Tier 1</option>
                  <option value="Tier 2">Tier 2</option>
                  <option value="Tier 3">Tier 3</option>
                </select>
                
                <select
                  value={selectedSector}
                  onChange={(e) => setSelectedSector(e.target.value)}
                  className="bg-zinc-950 border border-zinc-850 rounded px-1 py-0.5 text-zinc-400 hover:text-zinc-200 outline-none cursor-pointer max-w-[120px] truncate text-4xs uppercase"
                >
                  <option value="ALL">All Sectors</option>
                  {uniqueSectors.map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              {topPriorities.length === 0 ? (
                <p className="py-4 text-center font-mono text-2xs text-zinc-555">No priority tasks match current filters.</p>
              ) : (
                <div className="flex-1 overflow-auto">
                  <table className="w-full text-left font-mono text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-zinc-850 text-zinc-650 text-3xs uppercase">
                        <th className="py-2">Company</th>
                        <th className="py-2">Tier</th>
                        {isFocused && (
                          <>
                            <th className="py-2 text-right">Mcap</th>
                            <th className="py-2 text-right">Liquidity</th>
                            <th className="py-2 text-right">Holdings</th>
                            <th className="py-2 text-right">Sector</th>
                            <th className="py-2 text-center">Checklist</th>
                          </>
                        )}
                        <th className="py-2 text-right">Score</th>
                        <th className="py-2 pl-4">Next Action / Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topPriorities.map((item) => {
                        const hasChecklistGaps = item.total_checklist_count > 0 && item.completed_checklist_count < item.total_checklist_count;
                        const pendingItem = item.next_pending_item;
                        
                        let nextAction = "—";
                        let actionColor = "text-zinc-555";
                        if (pendingItem) {
                          nextAction = pendingItem;
                          actionColor = "text-orange-400 font-medium";
                        } else if (hasChecklistGaps) {
                          nextAction = `${item.completed_checklist_count}/${item.total_checklist_count} Checklist`;
                          actionColor = "text-amber-400";
                        } else if (item.score_status === "blocked") {
                          nextAction = "Resolve Gaps";
                          actionColor = "text-red-400";
                        } else {
                          nextAction = "Ready";
                          actionColor = "text-emerald-400";
                        }

                        // Build a concise reason from missing factors
                        const missing = item.missing_factors || [];
                        const reason = missing.length > 0 
                          ? `Missing: ${missing.join(", ").replace(/_/g, " ")}`
                          : "Score components complete";

                        return (
                          <tr key={item.cd_cvm} className="border-b border-zinc-850 hover:bg-zinc-900/35 text-xs font-mono text-zinc-300">
                            <td className="py-2 pr-2 font-semibold text-zinc-200 max-w-[120px] truncate" title={item.company_name}>
                              <Link to={`/empresas/${item.cd_cvm}`} className="hover:text-cyan-400 transition-colors">
                                {item.company_name}
                              </Link>
                              <span className="block text-4xs text-zinc-555 font-normal mt-0.5">
                                {item.ticker_b3 || `CVM ${item.cd_cvm}`}
                              </span>
                            </td>
                            <td className="py-2 text-zinc-400 text-2xs">{item.tier || "—"}</td>
                            {isFocused && (
                              <>
                                <td className="py-2 text-right text-zinc-400">{item.cap_score !== null && item.cap_score !== undefined ? item.cap_score : "—"}</td>
                                <td className="py-2 text-right text-zinc-400">{item.vol_score !== null && item.vol_score !== undefined ? item.vol_score : "—"}</td>
                                <td className="py-2 text-right text-zinc-400">{item.holding_score !== null && item.holding_score !== undefined ? item.holding_score : "—"}</td>
                                <td className="py-2 text-right text-zinc-400">{item.sector_score !== null && item.sector_score !== undefined ? item.sector_score : "—"}</td>
                                <td className="py-2 text-center text-zinc-400">{item.total_checklist_count > 0 ? `${item.completed_checklist_count}/${item.total_checklist_count}` : "—"}</td>
                              </>
                            )}
                            <td className="py-2 text-right text-orange-400 font-bold pr-2">
                              {item.final_score ?? 0}
                            </td>
                            <td className="py-2 pl-4">
                              <span className={`text-[10px] block truncate max-w-[180px] ${actionColor}`} title={nextAction}>
                                {nextAction}
                              </span>
                              <span className="block text-4xs text-zinc-555 truncate max-w-[180px]" title={reason}>
                                {reason}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {!isCompact && (
                <div className="pt-2 text-center border-t border-zinc-900/60 font-mono text-2xs shrink-0">
                  <Link
                    to="/coverage/prioritization"
                    className="text-cyan-400 hover:text-cyan-300 hover:underline"
                  >
                    Go to full prioritization dashboard →
                  </Link>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Panel>
  );
}
