import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchCoverageWorkQueue } from "@/lib/api/coverage";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { resolveCoverageWorkQueueHandoff } from "@/components/coverage/workQueueHandoffs";
import { CapacityWidget } from "@/components/coverage/CapacitySection";

// --- Work Queue / Gaps list tab ---
const SEV_COLORS: Record<string, string> = {
  high: "border-red-800/60 bg-red-950/20 text-red-400",
  medium: "border-amber-800/60 bg-amber-950/20 text-amber-400",
  low: "border-zinc-700/40 bg-zinc-900/10 text-zinc-500",
};

export function WorkQueueSection({ universeId, onOpenMethodology }: { universeId: string; onOpenMethodology: (tab: "scoring" | "capacity") => void }) {
  const [severityFilter, setSeverityFilter] = useState<"all" | "high" | "medium" | "low">("all");

  const queueQuery = useQuery({
    queryKey: ["coverage-work-queue", universeId],
    queryFn: () => fetchCoverageWorkQueue(universeId),
  });

  if (queueQuery.isLoading) return <StateBanner variant="loading" title="Compiling coverage tasks..." />;
  const allTasks = queueQuery.data || [];

  // News DB unavailable banner (single system task with type=news_db_unavailable)
  const newsBannerTask = allTasks.find((t: any) => t.task_type === "news_db_unavailable");
  const newsBannerHandoff = newsBannerTask
    ? resolveCoverageWorkQueueHandoff(newsBannerTask, { universeId })
    : null;
  const visibleTasks = allTasks.filter((t: any) => t.task_type !== "news_db_unavailable");

  const filteredTasks = severityFilter === "all"
    ? visibleTasks
    : visibleTasks.filter((t: any) => t.severity === severityFilter);

  const countBySev = (sev: string) => visibleTasks.filter((t: any) => t.severity === sev).length;

  return (
    <div className="space-y-4 font-mono text-xs">
      <CapacityWidget universeId={universeId} onOpenMethodology={onOpenMethodology} />

      {/* News unavailable banner */}
      {newsBannerTask && newsBannerHandoff ? (
        <div className="flex items-start gap-3 p-3 border border-amber-800/40 bg-amber-950/10 rounded text-amber-400 text-xs">
          <span className="font-bold shrink-0">News Workload:</span>
          <div className="min-w-0 flex-1 space-y-1">
            <span className="block">{newsBannerTask.reason}</span>
            <span className="block text-amber-600">{newsBannerTask.suggested_action}</span>
            <span className="block text-amber-300/80">{newsBannerHandoff.completionSignal}</span>
          </div>
          {newsBannerHandoff.supported && newsBannerHandoff.destination ? (
            <Link
              to={newsBannerHandoff.destination}
              className="shrink-0 px-2 py-0.5 bg-[var(--color-surface-3)] border border-amber-800/50 rounded text-2xs hover:border-amber-600 transition-colors text-amber-100 font-medium"
            >
              {newsBannerHandoff.actionLabel}
            </Link>
          ) : (
            <span className="shrink-0 text-2xs text-amber-700">{newsBannerHandoff.unsupportedReason}</span>
          )}
        </div>
      ) : null}

      <Panel title="Active Tasks" subtitle={`${visibleTasks.length} task(s) — data-quality, checklist, and news workload gaps`}>
        {/* Filter chips */}
        <div className="flex items-center gap-2 mb-3">
          {(["all", "high", "medium", "low"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setSeverityFilter(f)}
              className={`px-2 py-0.5 rounded border text-2xs uppercase tracking-wider transition-all ${
                severityFilter === f
                  ? "border-cyan-700 bg-cyan-950/40 text-cyan-400"
                  : "border-zinc-700/60 bg-zinc-900/20 text-zinc-500 hover:border-zinc-600"
              }`}
            >
              {f === "all" ? `All (${visibleTasks.length})` : `${f} (${countBySev(f)})`}
            </button>
          ))}
        </div>

        <div className="space-y-1.5">
          {filteredTasks.length === 0 ? (
            <StateBanner
              variant="empty"
              title={severityFilter === "all" ? "All up-to-date" : `No ${severityFilter}-severity tasks`}
              message={severityFilter === "all" ? "No pending coverage tasks found in this universe." : undefined}
            />
          ) : (
            filteredTasks.map((t: any, i: number) => {
              const handoff = resolveCoverageWorkQueueHandoff(t, { universeId });
              return (
                <div
                  key={i}
                  className="flex items-start justify-between gap-4 p-2.5 border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] rounded hover:border-zinc-600 transition-colors"
                >
                  <div className="flex items-start gap-2 min-w-0">
                    {/* Severity badge */}
                    <span className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-3xs border font-bold uppercase tracking-wider ${SEV_COLORS[t.severity] || SEV_COLORS.low}`}>
                      {t.severity}
                    </span>
                    <div className="space-y-0.5 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        {t.ticker_b3 && (
                          <span className="font-bold text-[var(--color-id-ticker)]">{t.ticker_b3}</span>
                        )}
                        {t.company_name && (
                          <span className="text-[var(--color-text-secondary)] truncate">{t.company_name}</span>
                        )}
                        {t.tier && (
                          <span className="text-3xs uppercase text-zinc-500 border border-zinc-800 px-1 rounded">{t.tier}</span>
                        )}
                        {t.owner ? (
                          <span className="text-3xs text-zinc-400">Owner: {t.owner}</span>
                        ) : (
                          <span className="text-3xs text-yellow-600/80 font-bold uppercase">Unassigned</span>
                        )}
                      </div>
                      <p className="text-[var(--color-text-secondary)] text-2xs font-medium">{t.reason}</p>
                      <p className="text-zinc-400 text-2xs font-normal">{t.suggested_action}</p>
                      <div className="grid gap-1 pt-1 text-3xs text-zinc-500 sm:grid-cols-3">
                        <span>
                          <span className="uppercase text-zinc-600">Question:</span> {handoff.analystQuestion}
                        </span>
                        <span>
                          <span className="uppercase text-zinc-600">Evidence:</span> {handoff.evidenceSurface}
                        </span>
                        <span>
                          <span className="uppercase text-zinc-600">Done when:</span> {handoff.completionSignal}
                        </span>
                      </div>
                      {!handoff.supported && handoff.unsupportedReason ? (
                        <p className="text-3xs text-amber-500/90">{handoff.unsupportedReason}</p>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-3xs text-zinc-500 font-mono uppercase">{t.task_type?.replace(/_/g, " ")}</span>
                    {handoff.supported && handoff.destination ? (
                      <Link
                        to={handoff.destination}
                        className="px-2 py-0.5 bg-[var(--color-surface-3)] border border-[var(--color-border-default)] rounded text-2xs hover:border-[var(--color-action-primary)] transition-colors text-[var(--color-text-primary)] font-medium"
                      >
                        {handoff.actionLabel}
                      </Link>
                    ) : (
                      <span className="px-2 py-0.5 border border-zinc-800 rounded text-2xs text-zinc-600">
                        No action
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </Panel>
    </div>
  );
}
