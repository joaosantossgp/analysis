import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  fetchCoverageUniverses,
  fetchCoveragePriorityScores,
} from "@/lib/api/coverage";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import { downloadCsvFile } from "./shared/csvExport";
import { PriorityQueueConfig, WidgetCommonProps } from "./shared/widgetTypes";

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

  // Sort by priority score (high to low)
  const topPriorities = useMemo(() => {
    return [...priorities]
      .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))
      .slice(0, isFocused ? 25 : isCompact ? 5 : 8);
  }, [priorities, isCompact, isFocused]);

  const selectUniverse = (id: string) => {
    onConfigure({ universeId: id });
    setIsConfiguring(false);
  };

  const handleExportCSV = () => {
    if (!priorities || priorities.length === 0) return;
    const headers = ["Company Name", "CVM Code", "Tier", "Priority Score"];
    const rows = priorities.map((item) => [
      item.company_name,
      item.cd_cvm,
      item.tier || "—",
      item.priority_score ?? 0,
    ]);
    downloadCsvFile({
      filename: `priority_queue_${config.universeId || "all"}.csv`,
      headers,
      rows,
    });
  };

  return (
    <Panel
      title="Priority Queue"
      subtitle={isMinimized ? undefined : activeUniverse ? `Universe: ${activeUniverse.name}` : "Identify coverage gaps"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1.5">
          {!isMinimized && (
            <button
              onClick={() => setIsConfiguring(!isConfiguring)}
              className="text-zinc-550 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
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
          className="space-y-3"
          style={{ flex: 1, minHeight: 0, overflow: "auto" }}
        >
          {isConfiguring && (
            <div className="border-b border-zinc-850 pb-3 space-y-2">
              <p className="text-2xs font-mono text-zinc-555 uppercase">Select Coverage Universe</p>
              {universes.length === 0 ? (
                <p className="text-2xs font-mono text-zinc-650">No universes available.</p>
              ) : (
                <div className="max-h-28 overflow-y-auto space-y-1 font-mono text-2xs">
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
            </div>
          )}

          {!config.universeId ? (
            <div className={`${isCompact ? "py-3" : "py-6"} text-center space-y-2`}>
              <p className="text-xs font-mono text-zinc-555">No universe selected.</p>
              {!isConfiguring && (
                <Button onClick={() => setIsConfiguring(true)} size="xs" variant="secondary">
                  Select Universe
                </Button>
              )}
            </div>
          ) : priorityQuery.isLoading ? (
            <p className="py-4 text-center font-mono text-2xs text-zinc-600">Loading priority rankings...</p>
          ) : topPriorities.length === 0 ? (
            <p className="py-4 text-center font-mono text-2xs text-zinc-555">No priority tasks available in this universe.</p>
          ) : (
            <div className="space-y-1.5 font-mono text-xs">
              <div className="flex items-center justify-between border-b border-zinc-900 pb-1 text-3xs text-zinc-555 uppercase">
                <span>Company</span>
                <div className="flex gap-4">
                  <span>Tier</span>
                  <span className="w-10 text-right">Score</span>
                </div>
              </div>
              {topPriorities.map((item) => (
                <div key={item.cd_cvm} className="flex items-center justify-between border-b border-zinc-900/60 py-1.5 last:border-0">
                  <Link
                    to={`/empresas/${item.cd_cvm}`}
                    className="truncate text-zinc-300 hover:text-cyan-400 transition-colors mr-2 max-w-44"
                    title={item.company_name}
                  >
                    {item.company_name}
                  </Link>
                  <div className="flex items-center gap-4 shrink-0 text-2xs">
                    <span className="text-zinc-555 font-semibold">{item.tier}</span>
                    <span className="w-10 text-right text-orange-400 font-bold">
                      {item.priority_score ?? 0}
                    </span>
                  </div>
                </div>
              ))}
              {!isCompact && (
                <div className="pt-2 text-center border-t border-zinc-900/60">
                  <Link
                    to="/coverage/prioritization"
                    className="text-2xs text-cyan-400 hover:text-cyan-300 hover:underline"
                  >
                    Go to full prioritization queue →
                  </Link>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
