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
  const isOffline = mode === "browser" || error;

  const items = data?.mode === "desktop" || data?.mode === "dev-http" ? data.items : [];

  const handleExportCSV = () => {
    if (!items || items.length === 0) return;
    const headers = ["Source", "Published At", "Title", "URL"];
    const rows = items.map((item) => [
      item.source_name || "CVM Filings",
      item.published_at || "",
      item.title,
      item.original_url || "",
    ]);
    downloadCsvFile({
      filename: "top_news_feed.csv",
      headers,
      rows,
    });
  };

  return (
    <Panel
      title="Top News Feed"
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
          className="space-y-3 font-mono"
          style={{ flex: 1, minHeight: 0, overflow: "auto" }}
        >
          {isOffline && !isCompact && (
            <div className="rounded border border-amber-900/30 bg-amber-955/20 p-2 text-2xs text-amber-200">
              ⚠️ Offline Preview Mode: Displaying cached or mock news data.
            </div>
          )}

          {isLoading ? (
            <p className="py-4 text-center text-2xs text-zinc-600">Loading feed...</p>
          ) : items.length === 0 ? (
            <p className="py-4 text-center text-2xs text-zinc-555">No news articles found in local database.</p>
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <div key={item.article_id} className="border-b border-zinc-800/40 pb-1.5 last:border-0 last:pb-0">
                  <div className="flex items-center justify-between text-3xs text-zinc-555 mb-0.5">
                    <span className="font-semibold text-cyan-500">{item.source_name || "CVM Filings"}</span>
                    <span>
                      {item.published_at
                        ? new Date(item.published_at).toLocaleDateString("en-US", { month: "short", day: "2-digit" })
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
              ))}
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
