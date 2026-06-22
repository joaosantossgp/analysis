import { useState, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchMarketHistory,
  fetchMarketHistoryStatus,
  triggerMarketHistoryRefresh,
} from "@/lib/api/marketHistory";
import { Panel } from "@/components/surface/Panel";
import { Sparkline } from "@/components/data/Sparkline";
import { CompanySelector } from "./shared/CompanySelector";
import { downloadCsvFile } from "./shared/csvExport";
import { MarketPriceConfig, WidgetCommonProps } from "./shared/widgetTypes";

interface MarketPriceCardProps extends WidgetCommonProps {
  config?: MarketPriceConfig;
  onConfigure: (newCfg: MarketPriceConfig) => void;
}

export function MarketPriceCard({
  config = { cdCvm: 0, ticker: "", companyName: "" },
  onConfigure,
  onRemove,
  isCompact = false,
  isMinimized = false,
  isFocused = false,
  headerControls,
}: MarketPriceCardProps) {
  const [isConfiguring, setIsConfiguring] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const queryClient = useQueryClient();

  const selectedPeriod = config.period || "30d";

  const { data, isLoading, error } = useQuery({
    queryKey: ["company-market-history", config.cdCvm, config.ticker, selectedPeriod],
    queryFn: () => fetchMarketHistory(config.cdCvm, config.ticker, null, null, selectedPeriod),
    enabled: Boolean(config.cdCvm),
  });

  const statusQuery = useQuery({
    queryKey: ["company-market-history-status", config.cdCvm, config.ticker],
    queryFn: () => fetchMarketHistoryStatus(config.cdCvm, config.ticker),
    enabled: Boolean(config.cdCvm),
  });
  const statusInfo = statusQuery.data?.mode === "desktop" ? statusQuery.data.status : null;

  const prices: Array<number | null | undefined> = useMemo(() => {
    if (data?.mode !== "desktop" || !data.data?.observations) return [];
    return data.data.observations.map((p: any) => p.close).reverse();
  }, [data]);

  const stats = useMemo(() => {
    if (prices.length === 0) return { current: null, min: null, max: null };
    const valid = prices.filter((p: number | null | undefined): p is number => typeof p === "number" && !Number.isNaN(p));
    return {
      current: valid[valid.length - 1] ?? null,
      min: Math.min(...valid),
      max: Math.max(...valid),
    };
  }, [prices]);

  const variation = useMemo(() => {
    if (prices.length < 2) return null;
    const valid = prices.filter((p): p is number => typeof p === "number" && !Number.isNaN(p));
    if (valid.length < 2) return null;
    const latest = valid[valid.length - 1];
    const prev = valid[0];
    if (prev === 0) return null;
    return ((latest - prev) / prev) * 100;
  }, [prices]);

  const isOffline = data?.mode === "browser" || error;

  const selectCompany = (cdCvm: number, name: string, ticker: string) => {
    onConfigure({ cdCvm, companyName: name, ticker, period: selectedPeriod });
    setIsConfiguring(false);
  };

  const changePeriod = (p: string) => {
    onConfigure({ ...config, period: p });
  };

  const handleRefresh = async () => {
    if (!config.cdCvm) return;
    setIsRefreshing(true);
    try {
      await triggerMarketHistoryRefresh(config.cdCvm, config.ticker);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["company-market-history", config.cdCvm] }),
        queryClient.invalidateQueries({ queryKey: ["company-market-history-status", config.cdCvm] }),
      ]);
    } catch (e) {
      console.error("Refresh failed:", e);
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleExportCSV = () => {
    if (!data?.data?.observations || data.data.observations.length === 0) return;
    const headers = ["Date", "Close Price"];
    const rows = data.data.observations.map((obs: any) => [
      obs.date || "",
      obs.close ?? "",
    ]);
    downloadCsvFile({
      filename: `${config.ticker || "ticker"}_market_history.csv`,
      headers,
      rows,
    });
  };

  return (
    <Panel
      title={
        <div className="flex items-center gap-2">
          <span>{config.ticker ? `${config.ticker} Price` : "Stock Price Watch"}</span>
          {config.ticker && (
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border leading-none uppercase tracking-wider font-mono ${
              isOffline
                ? "bg-amber-500/10 text-amber-400 border-amber-500/25"
                : "bg-emerald-500/10 text-emerald-400 border-emerald-500/25"
            }`}>
              {isOffline ? "MOCK" : "LIVE"}
            </span>
          )}
        </div>
      }
      subtitle={isMinimized ? undefined : config.companyName || "Daily close performance sparkline"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1.5">
          {!isMinimized && config.cdCvm > 0 && (
            <div className="flex items-center rounded border border-zinc-800 bg-zinc-950 px-1 py-0.5 text-3xs font-mono text-zinc-400 gap-1">
              {(["30d", "90d", "180d", "1y"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => changePeriod(p)}
                  className={`px-1 py-0.5 rounded leading-none transition-colors uppercase cursor-pointer ${
                    selectedPeriod === p ? "bg-orange-500/20 text-orange-400 font-bold" : "hover:text-zinc-200"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          )}
          {!isMinimized && (
            <button
              onClick={() => setIsConfiguring(!isConfiguring)}
              className="text-zinc-550 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
              title="Configure Ticker"
            >
              ⚙
            </button>
          )}
          {isFocused && (
            <button
              onClick={handleExportCSV}
              className="text-orange-400 hover:text-orange-300 font-mono text-3xs border border-zinc-800 bg-zinc-900 rounded px-1.5 py-0.5 transition-colors mr-1"
              title="Export Price History to CSV"
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
          className="space-y-3 font-mono flex flex-col"
          style={{ flex: 1, minHeight: 0, overflow: isConfiguring ? "auto" : (!config.cdCvm ? "hidden" : "auto") }}
        >
          {isConfiguring ? (
            <div className="space-y-2 flex flex-col flex-1 min-h-0">
              <p className="text-2xs text-zinc-555 uppercase shrink-0">Select Target Ticker</p>
              <div className="shrink-0">
                <CompanySelector onSelect={selectCompany} placeholder="Search ticker (e.g. PETR4)..." />
              </div>
              {config.cdCvm > 0 && (
                <button
                  onClick={() => setIsConfiguring(false)}
                  className="w-full text-center py-1 text-2xs font-mono text-orange-400 hover:text-orange-300 underline shrink-0 mt-2"
                >
                  Done configuring
                </button>
              )}
            </div>
          ) : !config.cdCvm ? (
            <div className="flex flex-col items-center justify-center p-3 py-3.5 border border-dashed border-zinc-850 rounded-md bg-zinc-900/5 text-center font-mono space-y-2 flex-1 min-h-0">
              <span className="text-zinc-500 text-sm">📈</span>
              <div>
                <p className="text-2xs font-bold text-zinc-300">No ticker selected</p>
                <p className="text-3xs text-zinc-550 max-w-xs leading-normal mt-0.5">
                  Select a B3 company ticker to monitor its daily price close sparkline.
                </p>
              </div>
              <button
                onClick={() => setIsConfiguring(true)}
                className="rounded border border-zinc-800 hover:border-zinc-700 bg-zinc-950 px-2 py-1 text-3xs font-bold text-orange-400 hover:text-orange-300 transition-colors uppercase tracking-wider"
              >
                Choose Ticker
              </button>
            </div>
          ) : (
            <>
              {error ? (
                <div className="rounded border border-red-900/30 bg-red-955/20 p-2 text-2xs text-red-400 space-y-1.5">
                  <p>⚠️ Error loading quotes: {error.message || String(error)}</p>
                  <button 
                    onClick={() => setIsConfiguring(true)}
                    className="underline text-red-300 hover:text-red-200 text-3xs uppercase tracking-wider font-bold"
                  >
                    Select Another Ticker
                  </button>
                </div>
              ) : isLoading ? (
                <p className="py-4 text-center text-2xs text-zinc-600">Loading quotes...</p>
              ) : prices.length === 0 ? (
                <div className="rounded border border-zinc-850 p-3 text-center text-2xs text-zinc-500 space-y-2">
                  <p>No quotes available for {config.ticker}.</p>
                  <button
                    onClick={handleRefresh}
                    disabled={isRefreshing}
                    className="rounded border border-zinc-800 bg-zinc-950 px-2 py-1 text-3xs font-bold text-orange-400 hover:text-orange-300 uppercase tracking-wider"
                  >
                    {isRefreshing ? "Refreshing..." : "Trigger Fetch / Refresh"}
                  </button>
                </div>
              ) : (
                <div className={isFocused ? "grid grid-cols-3 gap-6" : "space-y-3"}>
                  <div className={isFocused ? "col-span-1 space-y-3" : ""}>
                    <div className="flex items-baseline justify-between">
                      <span className={`${isFocused ? "text-2xl" : isCompact ? "text-sm" : "text-lg"} font-semibold text-zinc-100`}>
                        R$ {stats.current ? stats.current.toFixed(2) : "—"}
                      </span>
                      {variation !== null && (
                        <span className={`text-2xs font-bold ${variation > 0 ? "text-emerald-400" : variation < 0 ? "text-red-400" : "text-zinc-500"}`}>
                          {variation > 0 ? "+" : ""}{variation.toFixed(1)}%
                        </span>
                      )}
                    </div>

                    <div className="flex flex-col gap-1.5 text-[10px] text-zinc-400 border-t border-zinc-850 pt-2 font-mono">
                      <div className="flex justify-between">
                        <span>MIN PRICE ({selectedPeriod.toUpperCase()}):</span>
                        <span className="font-semibold text-zinc-200">R$ {stats.min?.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>MAX PRICE ({selectedPeriod.toUpperCase()}):</span>
                        <span className="font-semibold text-zinc-200">R$ {stats.max?.toFixed(2)}</span>
                      </div>
                      {statusInfo?.last_downloaded_at && (
                        <div className="flex justify-between text-4xs text-zinc-555">
                          <span>LAST SYNC:</span>
                          <span>
                            {new Date(statusInfo.last_downloaded_at).toLocaleString("en-US", {
                              dateStyle: "short",
                              timeStyle: "short",
                            })}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className={isFocused ? "col-span-2 flex flex-col gap-3" : "space-y-1.5"}>
                    <div className={`flex items-center justify-center bg-zinc-950/40 rounded border border-zinc-900/60 ${isFocused ? "py-4 flex-1 min-h-[140px]" : isCompact ? "py-1" : "py-2"}`}>
                      <Sparkline values={prices} width={isFocused ? 580 : isCompact ? 220 : 280} height={isFocused ? 100 : isCompact ? 25 : 45} />
                    </div>
                    {!isFocused && !isCompact && (
                      <div className="flex items-center justify-between text-4xs text-zinc-555 border-t border-zinc-850/40 pt-1">
                        <span>SOURCE: {isOffline ? "MOCK CACHE" : "YAHOO FINANCE"}</span>
                        <button
                          onClick={handleRefresh}
                          disabled={isRefreshing}
                          className="text-orange-400 hover:text-orange-300 font-bold hover:underline"
                        >
                          {isRefreshing ? "REFRESHING..." : "SYNC NOW"}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Panel>
  );
}
