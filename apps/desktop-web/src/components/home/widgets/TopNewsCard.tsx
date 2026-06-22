import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchNewsArticles } from "@/lib/api/news";
import { Panel } from "@/components/surface/Panel";
import { downloadCsvFile } from "./shared/csvExport";
import { WidgetCommonProps } from "./shared/widgetTypes";

export function TopNewsCard({
  onRemove,
  isCompact = false,
  isMinimized = false,
  isFocused = false,
  headerControls,
}: WidgetCommonProps) {
  const limitCount = isFocused ? 20 : isCompact ? 5 : 10;
  const { data, isLoading, error } = useQuery({
    queryKey: ["news-latest", limitCount],
    queryFn: () => fetchNewsArticles({ limit: limitCount }),
    refetchInterval: 60_000,
  });

  const mode = data?.mode;
  const isOffline = mode === "browser";

  const items = data?.mode === "desktop" || data?.mode === "dev-http" ? data.items : [];

  const handleExportCSV = () => {
    if (!items || items.length === 0) return;
    const headers = ["Source", "Published At", "Title", "Priority", "Relevance Score", "URL"];
    const rows = items.map((item) => [
      item.source_name || "CVM Filings",
      item.published_at || "",
      item.title,
      item.priority_level || "Normal",
      item.relevance_score ?? 0,
      item.original_url || "",
    ]);
    downloadCsvFile({
      filename: "top_news_feed.csv",
      headers,
      rows,
    });
  };

  const renderEmptyState = () => {
    if (isOffline) {
      return (
        <div className="flex flex-col items-center justify-center p-4 border border-dashed border-zinc-850 rounded-md bg-zinc-900/5 text-center font-mono space-y-2.5">
          <span className="text-zinc-555 text-lg">⚠️</span>
          <div>
            <p className="text-2xs font-bold text-zinc-300">Offline Preview Mode</p>
            <p className="text-3xs text-zinc-550 max-w-xs leading-normal mt-0.5">
              Connect to the desktop bridge to pull live RSS news and official CVM/B3 corporate filing feeds.
            </p>
          </div>
        </div>
      );
    }
    if (error) {
      return (
        <div className="flex flex-col items-center justify-center p-4 border border-dashed border-red-900/30 bg-red-955/5 text-center font-mono space-y-2.5 text-red-400">
          <span className="text-lg">⚠️</span>
          <div>
            <p className="text-2xs font-bold">News Source Error</p>
            <p className="text-3xs text-red-500/80 max-w-xs leading-normal mt-0.5">
              {error.message || String(error)}
            </p>
          </div>
        </div>
      );
    }
    return (
      <div className="flex flex-col items-center justify-center p-4 border border-dashed border-zinc-850 rounded-md bg-zinc-900/5 text-center font-mono space-y-2.5">
        <span className="text-zinc-555 text-lg">📰</span>
        <div>
          <p className="text-2xs font-bold text-zinc-300">No news articles found</p>
          <p className="text-3xs text-zinc-550 max-w-xs leading-normal mt-0.5">
            No articles match your filters or have been imported. Make sure you have active news sources configured.
          </p>
        </div>
        <Link
          to="/settings/sources"
          className="rounded border border-zinc-850 hover:border-zinc-700 bg-zinc-950 px-2 py-1 text-3xs font-bold text-orange-400 hover:text-orange-300 transition-colors uppercase tracking-wider"
        >
          Configure Sources
        </Link>
      </div>
    );
  };

  return (
    <Panel
      title={
        <div className="flex items-center gap-2">
          <span>Top News Feed</span>
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border leading-none uppercase tracking-wider font-mono ${
            isOffline
              ? "bg-amber-500/10 text-amber-400 border-amber-500/25"
              : "bg-emerald-500/10 text-emerald-400 border-emerald-500/25"
          }`}>
            {isOffline ? "MOCK" : "LIVE"}
          </span>
        </div>
      }
      subtitle={isMinimized ? undefined : "Aggregated filings and market alerts"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1">
          {isFocused && (
            <button
              onClick={handleExportCSV}
              className="text-orange-400 hover:text-orange-300 font-mono text-3xs border border-zinc-800 bg-zinc-900 rounded px-1.5 py-0.5 transition-colors mr-1"
              title="Export News to CSV"
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
          className="space-y-3 font-mono"
          style={{ flex: 1, minHeight: 0, overflow: "auto" }}
        >
          {isLoading ? (
            <p className="py-4 text-center text-2xs text-zinc-600">Loading feed...</p>
          ) : items.length === 0 ? (
            renderEmptyState()
          ) : (
            <div className="space-y-2">
              {items.map((item) => {
                const priority = item.priority_level;
                const hasPriority = priority && priority !== "Normal";
                const priorityClass = priority === "Critical"
                  ? "bg-red-500/10 text-red-400 border-red-500/25"
                  : "bg-amber-500/10 text-amber-400 border-amber-500/25";

                return (
                  <div key={item.article_id} className="border-b border-zinc-800/40 pb-1.5 last:border-0 last:pb-0">
                    <div className="flex flex-wrap items-center justify-between gap-1 text-[9px] text-zinc-500 mb-0.5">
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-cyan-500">{item.source_name || "CVM Filings"}</span>
                        {hasPriority && (
                          <span className={`text-[8px] font-bold px-1 rounded border leading-none uppercase font-mono ${priorityClass}`}>
                            {priority}
                          </span>
                        )}
                        {item.relevance_reasons && item.relevance_reasons.length > 0 && (
                          <span className="text-zinc-555 max-w-[140px] truncate" title={item.relevance_reasons.join(", ")}>
                            [{item.relevance_reasons[0]}]
                          </span>
                        )}
                      </div>
                      <span>
                        {item.published_at
                          ? new Date(item.published_at).toLocaleDateString("en-US", { month: "short", day: "2-digit" }) + " " + new Date(item.published_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false })
                          : ""}
                      </span>
                    </div>
                    <a
                      href={item.original_url || "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block text-xs text-zinc-300 hover:text-cyan-400 font-medium transition-colors line-clamp-2"
                    >
                      {item.title}
                    </a>
                  </div>
                );
              })}
              {!isCompact && (
                <div className="pt-1 text-center border-t border-zinc-900/60">
                  <Link
                    to="/news"
                    className="text-2xs text-cyan-400 hover:text-cyan-300 hover:underline"
                  >
                    Open News Center →
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
