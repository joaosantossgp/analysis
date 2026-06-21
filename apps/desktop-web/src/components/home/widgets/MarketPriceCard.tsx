import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchMarketHistory } from "@/lib/api/marketHistory";
import { Panel } from "@/components/surface/Panel";
import { Sparkline } from "@/components/data/Sparkline";
import { Button } from "@/components/ui/Button";
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

  const { data, isLoading, error } = useQuery({
    queryKey: ["company-market-history", config.cdCvm, config.ticker],
    queryFn: () => fetchMarketHistory(config.cdCvm, config.ticker, null, null, "30d"),
    enabled: Boolean(config.cdCvm),
  });

  const prices: Array<number | null | undefined> = useMemo(() => {
    if (data?.mode !== "desktop" || !data.data?.observations) return [];
    return data.data.observations.map((p) => p.close).reverse();
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

  const isOffline = data?.mode === "browser" || error;

  const selectCompany = (cdCvm: number, name: string, ticker: string) => {
    onConfigure({ cdCvm, companyName: name, ticker });
    setIsConfiguring(false);
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
      title={config.ticker ? `${config.ticker} Performance` : "Stock Price Watch"}
      subtitle={isMinimized ? undefined : config.companyName || "Daily quotes"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1.5">
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
          {isConfiguring && (
            <div className="border-b border-zinc-850 pb-3 space-y-2">
              <p className="text-2xs text-zinc-550 uppercase">Select Target Ticker</p>
              <CompanySelector onSelect={selectCompany} placeholder="Search ticker (e.g. PETR4)..." />
            </div>
          )}

          {!config.cdCvm ? (
            <div className={`${isCompact ? "py-3" : "py-6"} text-center space-y-2`}>
              <p className="text-xs text-zinc-550">No ticker selected.</p>
              {!isConfiguring && (
                <Button onClick={() => setIsConfiguring(true)} size="xs" variant="secondary">
                  Choose Ticker
                </Button>
              )}
            </div>
          ) : (
            <>
              {isOffline && !isCompact && (
                <div className="rounded border border-amber-900/30 bg-amber-955/20 p-2 text-2xs text-amber-200">
                  ⚠️ Offline Preview Mode: Displaying mock quotes.
                </div>
              )}

              {isLoading ? (
                <p className="py-4 text-center text-2xs text-zinc-600">Loading quotes...</p>
              ) : prices.length === 0 ? (
                <p className="py-4 text-center text-2xs text-zinc-555">No quotes available.</p>
              ) : (
                <div className={isFocused ? "grid grid-cols-3 gap-6" : isCompact ? "space-y-1.5" : "space-y-3"}>
                  <div className={isFocused ? "col-span-1 space-y-3" : ""}>
                    <div className="flex items-baseline justify-between">
                      <span className={`${isFocused ? "text-2xl" : isCompact ? "text-sm" : "text-lg"} font-semibold text-zinc-100`}>
                        R$ {stats.current ? stats.current.toFixed(2) : "—"}
                      </span>
                      <span className="text-2xs text-zinc-555">{isFocused ? "Current Price" : "Last 30 Days"}</span>
                    </div>

                    <div className="flex flex-col gap-1.5 text-2xs text-zinc-400 border-t border-zinc-850 pt-2 font-mono">
                      <div className="flex justify-between">
                        <span>MIN PRICE:</span>
                        <span className="font-semibold text-zinc-200">R$ {stats.min?.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>MAX PRICE:</span>
                        <span className="font-semibold text-zinc-200">R$ {stats.max?.toFixed(2)}</span>
                      </div>
                      {isFocused && data?.data?.observations && (
                        <div className="flex justify-between">
                          <span>QUOTES COUNT:</span>
                          <span className="font-semibold text-zinc-200">{data.data.observations.length}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className={isFocused ? "col-span-2 flex flex-col gap-3" : ""}>
                    <div className={`flex items-center justify-center bg-zinc-950/40 rounded border border-zinc-900/60 ${isFocused ? "py-4 flex-1 min-h-[140px]" : isCompact ? "py-1" : "py-2"}`}>
                      <Sparkline values={prices} width={isFocused ? 580 : isCompact ? 220 : 280} height={isFocused ? 100 : isCompact ? 25 : 45} />
                    </div>
                    {!isFocused && !isCompact && (
                      <div className="flex items-center justify-between text-2xs text-zinc-555 border-t border-zinc-800/40 pt-2">
                        <span>MIN: R$ {stats.min?.toFixed(2)}</span>
                        <span>MAX: R$ {stats.max?.toFixed(2)}</span>
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
