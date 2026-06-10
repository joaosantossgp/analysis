import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Panel } from "./surface/Panel";
import { StateBanner } from "./feedback/StateBanner";
import { fetchMarketHistoryStatus, fetchMarketHistory, triggerMarketHistoryRefresh } from "../lib/api/marketHistory";
import { useElementWidth } from "./indicators/useElementSize";

interface MarketHistoryPanelProps {
  cdCvm: number;
  bridgeReady: boolean;
}

type ChartMode = "price" | "return" | "yield" | "volume";

const PERIOD_OPTIONS = [
  { label: "1M", value: "1M" },
  { label: "3M", value: "3M" },
  { label: "6M", value: "6M" },
  { label: "YTD", value: "YTD" },
  { label: "1Y", value: "1Y" },
  { label: "3Y", value: "3Y" },
  { label: "5Y", value: "5Y" },
  { label: "10Y", value: "10Y" },
  { label: "MAX", value: "MAX" },
  { label: "Custom", value: "custom" },
];

export function MarketHistoryPanel({ cdCvm, bridgeReady }: MarketHistoryPanelProps) {
  const queryClient = useQueryClient();
  const [selectedPeriod, setSelectedPeriod] = useState<string>("1Y");
  const [customStart, setCustomStart] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");
  const [chartMode, setChartMode] = useState<ChartMode>("price");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [activeTicker, setActiveTicker] = useState<string>("");

  // Reset activeTicker when company changes
  useEffect(() => {
    setActiveTicker("");
  }, [cdCvm]);

  // Responsive SVG Ref
  const [chartRef, chartWidth] = useElementWidth<HTMLDivElement>();

  // Determine interval automatically to optimize rendering
  const interval = useMemo(() => {
    if (selectedPeriod === "MAX" || selectedPeriod === "10Y") return "1mo";
    if (selectedPeriod === "5Y" || selectedPeriod === "3Y") return "1wk";
    return "1d";
  }, [selectedPeriod]);

  // Status Query (metadata: resolved ticker, availability, staleness)
  const statusQuery = useQuery({
    queryKey: ["market-history-status", cdCvm, activeTicker],
    queryFn: () => fetchMarketHistoryStatus(cdCvm, activeTicker || null),
    enabled: bridgeReady,
  });

  const status = statusQuery.data?.mode === "desktop" ? statusQuery.data.status : null;
  const ticker = status?.ticker ?? "";
  const availableTickers = status?.available_tickers ?? [];
  const hasLocalData = status?.has_local_data ?? false;
  const isStale = status?.is_stale ?? false;
  const lastDownloaded = status?.last_downloaded_at ?? null;

  // Set initial activeTicker when status loads
  useEffect(() => {
    if (status && !activeTicker && status.ticker) {
      setActiveTicker(status.ticker);
    }
  }, [status, activeTicker]);

  // History Query (observations and period summary statistics)
  const historyQuery = useQuery({
    queryKey: ["market-history", cdCvm, activeTicker || ticker, selectedPeriod, customStart, customEnd, interval],
    queryFn: () => {
      const isCustom = selectedPeriod === "custom";
      return fetchMarketHistory(
        cdCvm,
        activeTicker || ticker || null,
        isCustom ? customStart : null,
        isCustom ? customEnd : null,
        isCustom ? null : selectedPeriod,
        interval
      );
    },
    enabled: bridgeReady && (hasLocalData || statusQuery.isSuccess) && !!(activeTicker || ticker),
  });

  const historyData = historyQuery.data?.mode === "desktop" ? historyQuery.data.data : null;
  const observations = historyData?.observations ?? [];
  const summary = historyData?.summary ?? null;

  // Refresh Mutation
  const refreshMutation = useMutation({
    mutationFn: () => triggerMarketHistoryRefresh(cdCvm, activeTicker || ticker || null),
    onSuccess: (res) => {
      if (res.mode === "desktop" && res.result?.ok) {
        queryClient.invalidateQueries({ queryKey: ["market-history-status", cdCvm] });
        queryClient.invalidateQueries({ queryKey: ["market-history", cdCvm] });
        // Also invalidate annual KPI history as it fallbacks to market history
        queryClient.invalidateQueries({ queryKey: ["company-kpis", cdCvm] });
      }
    },
  });

  // Set initial dates when custom mode is chosen
  useEffect(() => {
    if (selectedPeriod === "custom" && !customStart && observations.length > 0) {
      setCustomStart(observations[0].date);
      setCustomEnd(observations[observations.length - 1].date);
    }
  }, [selectedPeriod, observations, customStart]);

  // Format Helpers
  const formatBRL = (val: number | null | undefined) => {
    if (val == null) return "—";
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(val);
  };

  const formatPct = (val: number | null | undefined) => {
    if (val == null) return "—";
    const sign = val >= 0 ? "+" : "";
    return `${sign}${(val * 100).toFixed(2)}%`;
  };

  const formatCompact = (val: number | null | undefined) => {
    if (val == null) return "—";
    if (val >= 1e9) return `${(val / 1e9).toFixed(2)}B`;
    if (val >= 1e6) return `${(val / 1e6).toFixed(2)}M`;
    if (val >= 1e3) return `${(val / 1e3).toFixed(1)}K`;
    return val.toString();
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return "—";
    const [year, month, day] = dateStr.split("-");
    return `${day}/${month}/${year}`;
  };

  // Safe date comparison validation
  const isCustomRangeInvalid = selectedPeriod === "custom" && customStart && customEnd && customStart > customEnd;

  // Filter out actual dividend events in this range
  const dividendEvents = useMemo(() => {
    return observations
      .filter((o) => o.dividend > 0)
      .sort((a, b) => b.date.localeCompare(a.date));
  }, [observations]);

  // Chart Layout Calculations
  const chartHeight = 280;
  const paddingLeft = 60;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 40;

  const chartLayout = useMemo(() => {
    if (observations.length < 2 || chartWidth <= 0) return null;

    const w = Math.max(chartWidth, 320);
    const plotW = w - paddingLeft - paddingRight;
    const plotH = chartHeight - paddingTop - paddingBottom;

    // Get active chart series values
    let yValues: number[] = [];
    if (chartMode === "price") {
      yValues = observations.flatMap((o) => {
        const vals = [];
        if (o.close != null) vals.push(o.close);
        if (o.adjusted_close != null) vals.push(o.adjusted_close);
        return vals;
      });
    } else if (chartMode === "return") {
      yValues = observations.flatMap((o) => {
        const vals = [];
        if (o.price_return_index != null) vals.push((o.price_return_index - 1) * 100);
        if (o.total_return_index != null) vals.push((o.total_return_index - 1) * 100);
        return vals;
      });
    } else if (chartMode === "yield") {
      yValues = observations.map((o) => (o.ttm_dividend_yield ?? 0) * 100);
    } else if (chartMode === "volume") {
      yValues = observations.map((o) => o.volume ?? 0);
    }

    if (yValues.length === 0) return null;

    let yMin = Math.min(...yValues);
    let yMax = Math.max(...yValues);
    
    // Add 10% margins to y-scale (except volume/yield which should start at 0 if positive)
    if (chartMode === "volume" || chartMode === "yield") {
      yMin = 0;
      yMax = yMax * 1.1 || 1;
    } else {
      const margin = (yMax - yMin) * 0.1 || 1;
      yMin = yMin - margin;
      yMax = yMax + margin;
    }

    // Scale mapping functions
    const scaleX = (index: number) => paddingLeft + (index / (observations.length - 1)) * plotW;
    const scaleY = (val: number) => paddingTop + plotH - ((val - yMin) / (yMax - yMin || 1)) * plotH;

    // Build Y Ticks
    const numTicks = 5;
    const yTicks = Array.from({ length: numTicks }, (_, i) => {
      const val = yMin + (i / (numTicks - 1)) * (yMax - yMin);
      const y = scaleY(val);
      
      let label = "";
      if (chartMode === "price") label = `R$ ${val.toFixed(2)}`;
      else if (chartMode === "return") label = `${val >= 0 ? "+" : ""}${val.toFixed(1)}%`;
      else if (chartMode === "yield") label = `${val.toFixed(2)}%`;
      else if (chartMode === "volume") label = formatVolumeCompact(val);

      return { y, label };
    });

    // Build X Ticks (limit labels to prevent overlapping)
    const step = Math.ceil(observations.length / 5);
    const xTicks = observations
      .map((o, idx) => ({ date: o.date, x: scaleX(idx), idx }))
      .filter((_, idx) => idx % step === 0 || idx === observations.length - 1);

    // Build path generation
    const getPath = (points: { x: number; y: number }[]) => {
      if (points.length < 2) return "";
      return points.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
    };

    return {
      w,
      plotW,
      plotH,
      scaleX,
      scaleY,
      yTicks,
      xTicks,
      getPath,
      yMin,
      yMax,
    };
  }, [observations, chartWidth, chartMode]);

  function formatVolumeCompact(val: number): string {
    if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
    if (val >= 1e3) return `${(val / 1e3).toFixed(0)}K`;
    return val.toFixed(0);
  }

  // Handle manual trigger refresh
  const handleRefresh = () => {
    refreshMutation.mutate();
  };

  if (!bridgeReady || (statusQuery.isLoading && !activeTicker)) {
    return <StateBanner variant="loading" title="Loading market history status…" />;
  }

  if (statusQuery.isError) {
    return (
      <Panel title="Historical market data" subtitle="Yahoo Finance Integration">
        <StateBanner
          variant="error"
          title="Integration Error"
          message={
            statusQuery.error instanceof Error
              ? statusQuery.error.message
              : String(statusQuery.error)
          }
        />
      </Panel>
    );
  }

  if (statusQuery.data?.mode === "browser") {
    return (
      <Panel title="Historical market data" subtitle="Yahoo Finance Integration">
        <StateBanner
          variant="browser-only"
          message={statusQuery.data.reason}
        />
      </Panel>
    );
  }

  if (!ticker && !activeTicker) {
    return (
      <Panel title="Historical market data" subtitle="Yahoo Finance Integration">
        <StateBanner
          variant="empty"
          title="No Ticker Resolved"
          message="This company's CVM code could not be mapped to a canonical B3 or Yahoo Finance symbol. Excel exports and pricing calculations are disabled."
        />
      </Panel>
    );
  }

  if (historyQuery.isError) {
    return (
      <Panel
        title="Historical market data"
        subtitle={
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-0.5 text-2xs">
            <span className="text-[var(--color-text-tertiary)]">Ticker:</span>
            <span className="font-mono font-semibold text-cyan-300">
              {ticker.replace(".SA", "")}
            </span>
            <span className="text-[var(--color-text-tertiary)] font-sans">· Source: Yahoo Finance (Unofficial Free)</span>
          </div>
        }
        actions={
          <button
            type="button"
            disabled={refreshMutation.isPending}
            onClick={handleRefresh}
            className="rounded border border-cyan-700 bg-cyan-950/60 px-2.5 py-1 text-2xs font-medium text-cyan-300 hover:border-cyan-500 hover:text-cyan-200 disabled:opacity-50"
          >
            {refreshMutation.isPending ? "updating..." : hasLocalData ? "Update Data" : "Download History"}
          </button>
        }
      >
        <StateBanner
          variant="error"
          title="Failed to Load History"
          message={
            historyQuery.error instanceof Error
              ? historyQuery.error.message
              : String(historyQuery.error)
          }
        />
      </Panel>
    );
  }

  const getShareClassLabel = (t: string) => {
    const symbol = t.replace(".SA", "");
    if (t.endsWith("3.SA")) return `${symbol} (Common/ON)`;
    if (t.endsWith("4.SA")) return `${symbol} (Preferred/PN)`;
    if (t.endsWith("5.SA") || t.endsWith("6.SA")) return `${symbol} (Preferred/PN)`;
    if (t.endsWith("11.SA")) return `${symbol} (Unit)`;
    return symbol;
  };

  return (
    <Panel
      title="Historical market data"
      subtitle={
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-0.5 text-2xs">
          <span className="text-[var(--color-text-tertiary)]">Ticker:</span>
          {availableTickers.length > 1 ? (
            <select
              value={activeTicker || ticker}
              onChange={(e) => setActiveTicker(e.target.value)}
              className="rounded border border-[var(--color-border-default)] bg-[var(--color-surface-2)] px-1.5 py-0.5 font-mono text-2xs font-semibold text-cyan-300 focus:outline-none focus:border-cyan-500 cursor-pointer"
            >
              {availableTickers.map((t) => (
                <option key={t} value={t} className="bg-[var(--color-surface-3)] text-[var(--color-text-primary)]">
                  {getShareClassLabel(t)}
                </option>
              ))}
            </select>
          ) : (
            <span className="font-mono font-semibold text-cyan-300">
              {ticker.replace(".SA", "")}
            </span>
          )}
          <span className="text-[var(--color-text-tertiary)] font-sans">· Source: Yahoo Finance (Unofficial Free)</span>
        </div>
      }
      actions={
        <div className="flex items-center gap-2">
          {refreshMutation.isPending && (
            <span className="font-mono text-2xs text-[var(--color-state-warn)] animate-pulse">
              updating...
            </span>
          )}
          {isStale && !refreshMutation.isPending && (
            <span className="font-mono text-2xs text-[var(--color-state-warn)] bg-[var(--color-state-warn)]/10 px-1.5 py-0.5 rounded border border-[var(--color-state-warn)]/20">
              stale
            </span>
          )}
          {!isStale && hasLocalData && (
            <span className="font-mono text-2xs text-[var(--color-state-ok)] bg-[var(--color-state-ok)]/10 px-1.5 py-0.5 rounded border border-[var(--color-state-ok)]/20">
              offline ready
            </span>
          )}
          <button
            type="button"
            disabled={refreshMutation.isPending}
            onClick={handleRefresh}
            className="rounded border border-cyan-700 bg-cyan-950/60 px-2.5 py-1 text-2xs font-medium text-cyan-300 hover:border-cyan-500 hover:text-cyan-200 disabled:opacity-50"
          >
            {hasLocalData ? "Update Data" : "Download History"}
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Warning Banner if stale / network error / no local data */}
        {!hasLocalData && (
          <StateBanner
            variant="empty"
            title="No local market history cached"
            message="Click 'Download History' above to fetch historical stock prices, adjusted returns, and dividend yield from Yahoo Finance. Once downloaded, data will remain available offline."
          />
        )}

        {refreshMutation.isError && (
          <div className="rounded border border-red-900 bg-red-950/40 p-2.5 text-xs text-red-300">
            <strong>Update failed:</strong> {refreshMutation.error instanceof Error ? refreshMutation.error.message : String(refreshMutation.error)}. Retaining previous local cache.
          </div>
        )}

        {hasLocalData && (
          <>
            {/* Range & Period Selector */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border-subtle)] pb-3">
              <div className="flex flex-wrap gap-1">
                {PERIOD_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setSelectedPeriod(opt.value)}
                    className={`rounded px-2.5 py-1 text-2xs font-mono font-medium transition ${
                      selectedPeriod === opt.value
                        ? "bg-cyan-900/60 text-cyan-300 border border-cyan-800"
                        : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)]"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {selectedPeriod === "custom" && (
                <div className="flex items-center gap-1.5 text-2xs">
                  <input
                    type="date"
                    value={customStart}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="rounded border border-[var(--color-border-default)] bg-[var(--color-surface-3)] px-2 py-1 font-mono text-[var(--color-text-primary)]"
                  />
                  <span className="text-[var(--color-text-tertiary)]">to</span>
                  <input
                    type="date"
                    value={customEnd}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="rounded border border-[var(--color-border-default)] bg-[var(--color-surface-3)] px-2 py-1 font-mono text-[var(--color-text-primary)]"
                  />
                </div>
              )}
            </div>

            {/* Custom Range Error */}
            {isCustomRangeInvalid && (
              <div className="text-2xs text-[var(--color-state-error)] font-medium">
                Invalid range: start date must be less than or equal to end date.
              </div>
            )}

            {/* Summary KPI tape */}
            {summary && !isCustomRangeInvalid && (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7 border border-[var(--color-border-subtle)] rounded bg-[var(--color-surface-3)] p-3">
                <SummaryCard
                  label="Last Price"
                  value={formatBRL(summary.final_close)}
                  sublabel={observations.length > 0 ? formatDate(observations[observations.length - 1].date) : ""}
                />
                <SummaryCard
                  label="Period Return"
                  value={formatPct(summary.price_return)}
                  tone={summary.price_return && summary.price_return >= 0 ? "ok" : "error"}
                />
                <SummaryCard
                  label="Shareholder Return"
                  value={formatPct(summary.total_return)}
                  tone={summary.total_return && summary.total_return >= 0 ? "ok" : "error"}
                  tooltip="Total return including dividends reinvested (adjusted price return)"
                />
                {summary.annualized_total_return != null && (
                  <SummaryCard
                    label="Annualized TSR"
                    value={formatPct(summary.annualized_total_return)}
                    tone={summary.annualized_total_return >= 0 ? "ok" : "error"}
                    tooltip="Compound Annual Growth Rate (CAGR) of adjusted stock return"
                  />
                )}
                <SummaryCard label="High" value={formatBRL(summary.period_high)} />
                <SummaryCard label="Low" value={formatBRL(summary.period_low)} />
                <SummaryCard label="Dividends" value={formatBRL(summary.dividends_per_share)} sublabel="paid in period" />
              </div>
            )}

            {/* Main Chart Section */}
            {!isCustomRangeInvalid && observations.length > 0 && (
              <div ref={chartRef} className="space-y-2">
                {/* Chart Mode Toggle */}
                <div className="flex gap-1.5 border-b border-[var(--color-border-subtle)] pb-1.5">
                  {(["price", "return", "yield", "volume"] as ChartMode[]).map((mode) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => {
                        setChartMode(mode);
                        setHoverIndex(null);
                      }}
                      className={`rounded-t px-3 py-1 text-2xs font-medium border-b-2 transition ${
                        chartMode === mode
                          ? "border-cyan-500 text-cyan-300 font-semibold"
                          : "border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
                      }`}
                    >
                      {mode === "price" && "Stock Price"}
                      {mode === "return" && "Cumulative Return"}
                      {mode === "yield" && "Dividend Yield (TTM)"}
                      {mode === "volume" && "Trading Volume"}
                    </button>
                  ))}
                </div>

                {/* SVG Visualizer */}
                {chartLayout ? (
                  <div className="relative w-full overflow-hidden select-none">
                    <svg
                      width={chartLayout.w}
                      height={chartHeight}
                      viewBox={`0 0 ${chartLayout.w} ${chartHeight}`}
                      className="block w-full"
                    >
                      {/* Gridlines & Y-Axis Ticks */}
                      {chartLayout.yTicks.map((tick, i) => (
                        <g key={`y-${i}`}>
                          <line
                            x1={paddingLeft}
                            x2={chartLayout.w - paddingRight}
                            y1={tick.y}
                            y2={tick.y}
                            stroke="var(--color-border-subtle)"
                            strokeWidth={1}
                            strokeDasharray={i === 0 ? undefined : "3 3"}
                            opacity={i === 0 ? 0.7 : 0.4}
                          />
                          <text
                            x={paddingLeft - 8}
                            y={tick.y + 3}
                            textAnchor="end"
                            className="font-mono text-3xs"
                            fill="var(--color-text-tertiary)"
                          >
                            {tick.label}
                          </text>
                        </g>
                      ))}

                      {/* X-Axis Dates */}
                      {chartLayout.xTicks.map((tick, i) => (
                        <text
                          key={`x-${i}`}
                          x={tick.x}
                          y={chartHeight - 12}
                          textAnchor="middle"
                          className="font-mono text-3xs"
                          fill="var(--color-text-tertiary)"
                        >
                          {formatDate(tick.date)}
                        </text>
                      ))}

                      {/* Line Paths based on chart mode */}
                      {chartMode === "price" && (
                        <>
                          {/* Close Unadjusted (Raw) */}
                          <path
                            d={chartLayout.getPath(
                              observations.map((o, idx) => ({
                                x: chartLayout.scaleX(idx),
                                y: chartLayout.scaleY(o.close ?? 0),
                              })).filter((_, idx) => observations[idx].close != null)
                            )}
                            fill="none"
                            stroke="var(--color-text-primary)"
                            strokeWidth={1.8}
                          />
                          {/* Adjusted Close */}
                          <path
                            d={chartLayout.getPath(
                              observations.map((o, idx) => ({
                                x: chartLayout.scaleX(idx),
                                y: chartLayout.scaleY(o.adjusted_close ?? 0),
                              })).filter((_, idx) => observations[idx].adjusted_close != null)
                            )}
                            fill="none"
                            stroke="var(--color-accent-teal)"
                            strokeWidth={1.8}
                            strokeDasharray="4 2"
                            opacity={0.8}
                          />
                        </>
                      )}

                      {chartMode === "return" && (
                        <>
                          {/* Price Return */}
                          <path
                            d={chartLayout.getPath(
                              observations.map((o, idx) => ({
                                x: chartLayout.scaleX(idx),
                                y: chartLayout.scaleY(((o.price_return_index ?? 1) - 1) * 100),
                              })).filter((_, idx) => observations[idx].price_return_index != null)
                            )}
                            fill="none"
                            stroke="var(--color-text-secondary)"
                            strokeWidth={1.8}
                          />
                          {/* Total Shareholder Return */}
                          <path
                            d={chartLayout.getPath(
                              observations.map((o, idx) => ({
                                x: chartLayout.scaleX(idx),
                                y: chartLayout.scaleY(((o.total_return_index ?? 1) - 1) * 100),
                              })).filter((_, idx) => observations[idx].total_return_index != null)
                            )}
                            fill="none"
                            stroke="var(--color-accent-teal)"
                            strokeWidth={2}
                          />
                        </>
                      )}

                      {chartMode === "yield" && (
                        <path
                          d={chartLayout.getPath(
                            observations.map((o, idx) => ({
                              x: chartLayout.scaleX(idx),
                              y: chartLayout.scaleY((o.ttm_dividend_yield ?? 0) * 100),
                            }))
                          )}
                          fill="none"
                          stroke="var(--color-state-ok)"
                          strokeWidth={2}
                        />
                      )}

                      {chartMode === "volume" && (
                        <g>
                          {observations.map((o, idx) => {
                            if (o.volume == null) return null;
                            const barW = Math.max(1.5, (chartLayout.plotW / observations.length) * 0.7);
                            const x = chartLayout.scaleX(idx) - barW / 2;
                            const y = chartLayout.scaleY(o.volume);
                            const h = chartHeight - paddingBottom - y;
                            return (
                              <rect
                                key={idx}
                                x={x}
                                y={y}
                                width={barW}
                                height={Math.max(1, h)}
                                fill="var(--color-accent-blue)"
                                opacity={hoverIndex === null || hoverIndex === idx ? 0.6 : 0.3}
                              />
                            );
                          })}
                        </g>
                      )}

                      {/* Hover vertical guide line */}
                      {hoverIndex !== null && (
                        <line
                          x1={chartLayout.scaleX(hoverIndex)}
                          x2={chartLayout.scaleX(hoverIndex)}
                          y1={paddingTop}
                          y2={chartHeight - paddingBottom}
                          stroke="var(--color-text-tertiary)"
                          strokeWidth={1}
                          strokeDasharray="2 2"
                          opacity={0.6}
                        />
                      )}

                      {/* Hover Event Capture Pane */}
                      <rect
                        x={paddingLeft}
                        y={paddingTop}
                        width={chartLayout.plotW}
                        height={chartHeight - paddingTop - paddingBottom}
                        fill="transparent"
                        onMouseMove={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect();
                          const mx = e.clientX - rect.left;
                          const ratio = mx / chartLayout.plotW;
                          const idx = Math.round(ratio * (observations.length - 1));
                          setHoverIndex(Math.min(Math.max(0, idx), observations.length - 1));
                        }}
                        onMouseLeave={() => setHoverIndex(null)}
                      />
                    </svg>

                    {/* Tooltip Overlay */}
                    {hoverIndex !== null && observations[hoverIndex] && (
                      <ChartTooltip
                        obs={observations[hoverIndex]}
                        x={chartLayout.scaleX(hoverIndex)}
                        y={paddingTop + 10}
                        width={chartLayout.w}
                        chartMode={chartMode}
                        formatBRL={formatBRL}
                        formatPct={formatPct}
                        formatCompact={formatCompact}
                        formatDate={formatDate}
                      />
                    )}
                  </div>
                ) : (
                  <div
                    className="flex items-center justify-center border border-dashed border-[var(--color-border-subtle)] rounded text-xs text-[var(--color-text-tertiary)]"
                    style={{ height: chartHeight }}
                  >
                    Insufficient observations to render line chart.
                  </div>
                )}

                {/* Legend/Disclosure */}
                <div className="flex flex-wrap items-center justify-between text-3xs text-[var(--color-text-tertiary)] font-mono">
                  <div className="flex gap-4">
                    {chartMode === "price" && (
                      <>
                        <div className="flex items-center gap-1">
                          <span className="inline-block w-2.5 h-0.5 bg-[var(--color-text-primary)]" />
                          <span>Close Price (Raw)</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="inline-block w-2.5 h-0.5 border-t border-dashed border-[var(--color-accent-teal)]" />
                          <span>Adjusted Close (Split & Dividend Adjusted)</span>
                        </div>
                      </>
                    )}
                    {chartMode === "return" && (
                      <>
                        <div className="flex items-center gap-1">
                          <span className="inline-block w-2.5 h-0.5 bg-[var(--color-text-secondary)]" />
                          <span>Price Return (Unadjusted)</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="inline-block w-2.5 h-0.5 bg-[var(--color-accent-teal)]" />
                          <span>Total Shareholder Return (Adjusted TSR)</span>
                        </div>
                      </>
                    )}
                  </div>
                  <div>
                    Last updated: {lastDownloaded ? formatDate(lastDownloaded.slice(0, 10)) + " " + lastDownloaded.slice(11, 16) + " UTC" : "—"}
                  </div>
                </div>
              </div>
            )}

            {/* Dividend History Section */}
            {chartMode === "yield" && (
              <div className="mt-4 space-y-2">
                <h4 className="text-xs font-semibold text-[var(--color-text-secondary)]">
                  Dividend Event History
                </h4>
                {dividendEvents.length > 0 ? (
                  <div className="max-h-56 overflow-y-auto border border-[var(--color-border-subtle)] rounded">
                    <table className="w-full border-collapse text-2xs font-mono">
                      <thead>
                        <tr className="text-left border-b border-[var(--color-border-default)] bg-[var(--color-surface-2)] text-[var(--color-text-tertiary)]">
                          <th className="px-3 py-1.5 font-medium">Ex-Date</th>
                          <th className="px-3 py-1.5 font-medium text-right">Cash Paid</th>
                          <th className="px-3 py-1.5 font-medium text-right">TTM Dividends</th>
                          <th className="px-3 py-1.5 font-medium text-right">TTM Yield</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--color-border-subtle)] text-[var(--color-text-secondary)]">
                        {dividendEvents.map((e, idx) => {
                          // Find index in main list to get computed rolling twelve-month dividends
                          const origIdx = observations.findIndex((o) => o.date === e.date);
                          const totDividendsPaid = observations.slice(Math.max(0, origIdx - 365), origIdx + 1)
                            .reduce((sum, o) => sum + o.dividend, 0);
                          
                          return (
                            <tr key={idx} className="hover:bg-[var(--color-surface-2)]">
                              <td className="px-3 py-1.5">{formatDate(e.date)}</td>
                              <td className="px-3 py-1.5 text-right text-[var(--color-state-ok)] font-medium">
                                {formatBRL(e.dividend)}
                              </td>
                              <td className="px-3 py-1.5 text-right">{formatBRL(totDividendsPaid)}</td>
                              <td className="px-3 py-1.5 text-right">
                                {e.ttm_dividend_yield != null ? `${(e.ttm_dividend_yield * 100).toFixed(2)}%` : "—"}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="rounded border border-dashed border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] p-4 text-center text-xs text-[var(--color-text-tertiary)]">
                    No cash dividend events found in the selected date range.
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </Panel>
  );
}

// Summary Card Helper Component
function SummaryCard({
  label,
  value,
  sublabel,
  tone,
  tooltip,
}: {
  label: string;
  value: string;
  sublabel?: string;
  tone?: "ok" | "error" | "neutral";
  tooltip?: string;
}) {
  const valueColor =
    tone === "ok"
      ? "var(--color-state-ok)"
      : tone === "error"
        ? "var(--color-state-error)"
        : "var(--color-text-primary)";

  return (
    <div className="flex flex-col gap-0.5 rounded bg-[var(--color-surface-1)] border border-[var(--color-border-subtle)] p-2" title={tooltip}>
      <span className="text-3xs text-[var(--color-text-tertiary)] font-medium uppercase tracking-wider">
        {label}
      </span>
      <span className="font-mono text-sm font-semibold truncate" style={{ color: valueColor }}>
        {value}
      </span>
      {sublabel && (
        <span className="text-3xs text-[var(--color-text-tertiary)] font-mono leading-tight truncate">
          {sublabel}
        </span>
      )}
    </div>
  );
}

// Chart Tooltip Component
function ChartTooltip({
  obs,
  x,
  y,
  width,
  chartMode,
  formatBRL,
  formatPct,
  formatCompact,
  formatDate,
}: {
  obs: any;
  x: number;
  y: number;
  width: number;
  chartMode: ChartMode;
  formatBRL: (v: number) => string;
  formatPct: (v: number) => string;
  formatCompact: (v: number) => string;
  formatDate: (d: string) => string;
}) {
  const boxW = 180;
  const isRightHalf = x > width / 2;
  const left = isRightHalf ? x - boxW - 12 : x + 12;

  return (
    <div
      className="absolute border rounded bg-[var(--color-surface-3)] border-[var(--color-border-default)] shadow-lg p-2.5 pointer-events-none z-10"
      style={{
        top: y,
        left: Math.max(10, Math.min(left, width - boxW - 10)),
        width: boxW,
      }}
    >
      <div className="font-mono text-3xs text-[var(--color-text-tertiary)] border-b border-[var(--color-border-subtle)] pb-1 mb-1.5 uppercase">
        {formatDate(obs.date)}
      </div>

      <div className="space-y-1 text-2xs">
        {chartMode === "price" && (
          <>
            <TooltipRow label="Raw Close" value={formatBRL(obs.close)} color="var(--color-text-primary)" />
            <TooltipRow label="Adj Close" value={formatBRL(obs.adjusted_close)} color="var(--color-accent-teal)" />
            <TooltipRow label="Open" value={formatBRL(obs.open)} />
            <TooltipRow label="High" value={formatBRL(obs.high)} />
            <TooltipRow label="Low" value={formatBRL(obs.low)} />
          </>
        )}

        {chartMode === "return" && (
          <>
            <TooltipRow
              label="Price Return"
              value={obs.price_return_index != null ? formatPct(obs.price_return_index - 1) : "—"}
              color="var(--color-text-secondary)"
            />
            <TooltipRow
              label="TSR (Total Return)"
              value={obs.total_return_index != null ? formatPct(obs.total_return_index - 1) : "—"}
              color="var(--color-accent-teal)"
            />
          </>
        )}

        {chartMode === "yield" && (
          <TooltipRow
            label="TTM Yield"
            value={obs.ttm_dividend_yield != null ? `${(obs.ttm_dividend_yield * 100).toFixed(3)}%` : "—"}
            color="var(--color-state-ok)"
          />
        )}

        {chartMode === "volume" && (
          <TooltipRow label="Volume" value={formatCompact(obs.volume)} color="var(--color-accent-blue)" />
        )}

        {obs.dividend > 0 && (
          <div className="pt-1 mt-1 border-t border-[var(--color-border-subtle)] font-medium text-[var(--color-state-ok)] flex justify-between">
            <span>Dividend Ex-date</span>
            <span>{formatBRL(obs.dividend)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function TooltipRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between items-center gap-2">
      <span className="text-[var(--color-text-secondary)]">{label}</span>
      <span className="font-mono font-semibold" style={{ color: color || "var(--color-text-primary)" }}>
        {value}
      </span>
    </div>
  );
}
