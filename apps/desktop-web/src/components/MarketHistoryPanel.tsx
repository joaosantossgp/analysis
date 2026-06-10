import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { IndicatorChart } from "@/components/indicators/IndicatorChart";
import { IndicatorPicker } from "@/components/indicators/IndicatorPicker";
import { Segmented } from "@/components/indicators/Segmented";
import { Panel } from "@/components/surface/Panel";
import { Checkbox } from "@/components/ui/Checkbox";
import { PeriodSelect } from "@/components/ui/PeriodSelect";
import { fetchMarketHistory, fetchMarketHistoryStatus, triggerMarketHistoryRefresh } from "@/lib/api/marketHistory";
import type { CompanyMarketHistoryObservation, CompanyMarketHistorySummary } from "@/lib/bridge/types";
import { formatValue } from "@/lib/indicators/format";
import type { ChartAesthetics, ChartType, ResolvedSeries } from "@/lib/indicators/types";
import {
  MARKET_CHART_TYPES,
  MARKET_MAX_SELECTED_SERIES,
  MARKET_PERIOD_OPTIONS,
  MARKET_VIEW_LABEL,
  MARKET_VIEW_OPTIONS,
  buildMarketChartSeries,
  buildMarketPeriods,
  formatMarketDateTick,
  getAvailableMarketSeries,
  getMarketSeriesPickerDefs,
  normalizeMarketChartType,
  sanitizeMarketSeriesSelection,
  shouldRenderMarketMarkers,
  type MarketPeriod,
  type MarketSeriesId,
  type MarketView,
} from "@/lib/marketHistory/series";
import { useMarketHistoryConfig } from "@/lib/marketHistory/useMarketHistoryConfig";

interface MarketHistoryPanelProps {
  cdCvm: number;
  bridgeReady: boolean;
  compact?: boolean;
}

const CHART_HEIGHT = 320;

export function MarketHistoryPanel({ cdCvm, bridgeReady, compact = false }: MarketHistoryPanelProps) {
  const queryClient = useQueryClient();
  const [customStart, setCustomStart] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");
  const [activeTicker, setActiveTicker] = useState<string>("");
  const [showOptions, setShowOptions] = useState(false);
  const {
    config,
    chart,
    setView,
    setPeriod,
    setSelectedSeries,
    setChartType,
    setChartOptions,
  } = useMarketHistoryConfig();

  const selectedPeriod = config.period;
  const marketView = config.view;

  useEffect(() => {
    setActiveTicker("");
  }, [cdCvm]);

  const interval = useMemo(() => {
    if (selectedPeriod === "MAX" || selectedPeriod === "10Y") return "1mo";
    if (selectedPeriod === "5Y" || selectedPeriod === "3Y") return "1wk";
    return "1d";
  }, [selectedPeriod]);

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

  useEffect(() => {
    if (status && !activeTicker && status.ticker) {
      setActiveTicker(status.ticker);
    }
  }, [status, activeTicker]);

  const isCustomRangeInvalid =
    selectedPeriod === "custom" && customStart !== "" && customEnd !== "" && customStart > customEnd;

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
        interval,
      );
    },
    enabled:
      bridgeReady &&
      !isCustomRangeInvalid &&
      (hasLocalData || statusQuery.isSuccess) &&
      Boolean(activeTicker || ticker),
  });

  const historyData = historyQuery.data?.mode === "desktop" ? historyQuery.data.data : null;
  const observations = historyData?.observations ?? [];
  const summary = historyData?.summary ?? null;

  useEffect(() => {
    if (selectedPeriod === "custom" && !customStart && observations.length > 0) {
      setCustomStart(observations[0].date);
      setCustomEnd(observations[observations.length - 1].date);
    }
  }, [selectedPeriod, observations, customStart]);

  const dividendEvents = useMemo(
    () =>
      observations
        .filter((observation) => observation.dividend > 0)
        .sort((a, b) => b.date.localeCompare(a.date)),
    [observations],
  );

  const refreshMutation = useMutation({
    mutationFn: () => triggerMarketHistoryRefresh(cdCvm, activeTicker || ticker || null),
    onSuccess: (res) => {
      if (res.mode === "desktop" && res.result?.ok) {
        queryClient.invalidateQueries({ queryKey: ["market-history-status", cdCvm] });
        queryClient.invalidateQueries({ queryKey: ["market-history", cdCvm] });
        queryClient.invalidateQueries({ queryKey: ["company-kpis", cdCvm] });
      }
    },
  });

  const availableSeriesIds = useMemo(
    () => getAvailableMarketSeries(observations, marketView),
    [observations, marketView],
  );
  const selectedSeriesIds = useMemo(
    () =>
      sanitizeMarketSeriesSelection(
        marketView,
        config.selectedSeriesByView[marketView],
        availableSeriesIds,
      ),
    [availableSeriesIds, config.selectedSeriesByView, marketView],
  );
  const pickerDefs = useMemo(
    () => getMarketSeriesPickerDefs(observations, marketView),
    [observations, marketView],
  );
  const periods = useMemo(() => buildMarketPeriods(observations), [observations]);
  const series = useMemo(
    () =>
      buildMarketChartSeries({
        observations,
        view: marketView,
        selectedIds: selectedSeriesIds,
        chartType: config.chartTypeByView[marketView],
        indexMode: chart.indexMode,
      }),
    [chart.indexMode, config.chartTypeByView, marketView, observations, selectedSeriesIds],
  );
  const chartForMarket = useMemo(
    () => ({
      ...chart,
      markers: shouldRenderMarketMarkers(chart.markers, observations.length),
    }),
    [chart, observations.length],
  );

  function handleRefresh() {
    refreshMutation.mutate();
  }

  function toggleSeries(id: string) {
    const seriesId = id as MarketSeriesId;
    const exists = selectedSeriesIds.includes(seriesId);
    const next = exists
      ? selectedSeriesIds.filter((item) => item !== seriesId)
      : selectedSeriesIds.length < MARKET_MAX_SELECTED_SERIES[marketView]
        ? [...selectedSeriesIds, seriesId]
        : selectedSeriesIds;
    setSelectedSeries(marketView, next);
  }

  function handleViewChange(view: MarketView) {
    setView(view);
    setChartType(view, normalizeMarketChartType(view, config.chartTypeByView[view]));
  }

  if (!bridgeReady || (statusQuery.isLoading && !activeTicker)) {
    return (
      <Panel title="Historical market data" subtitle="Market price, return, dividend yield, and volume.">
        <StateBanner variant="loading" title="Loading market history status..." />
      </Panel>
    );
  }

  if (statusQuery.isError) {
    return (
      <Panel title="Historical market data" subtitle="Yahoo Finance · Unofficial free source">
        <StateBanner
          variant="error"
          title="Integration error"
          message={statusQuery.error instanceof Error ? statusQuery.error.message : String(statusQuery.error)}
        />
      </Panel>
    );
  }

  if (statusQuery.data?.mode === "browser") {
    return (
      <Panel title="Historical market data" subtitle="Yahoo Finance · Unofficial free source">
        <StateBanner variant="browser-only" message={statusQuery.data.reason} />
      </Panel>
    );
  }

  if (!ticker && !activeTicker) {
    return (
      <Panel title="Historical market data" subtitle="Yahoo Finance · Unofficial free source">
        <StateBanner
          variant="empty"
          title="No ticker resolved"
          message="This company's CVM code could not be mapped to a canonical B3 or Yahoo Finance symbol."
        />
      </Panel>
    );
  }

  if (historyQuery.isError && observations.length === 0) {
    return (
      <Panel
        title="Historical market data"
        subtitle="Yahoo Finance · Unofficial free source"
        actions={
          <MarketActions
            hasLocalData={hasLocalData}
            isStale={isStale}
            isError
            isUpdating={refreshMutation.isPending}
            lastDownloaded={lastDownloaded}
            onRefresh={handleRefresh}
          />
        }
      >
        <StateBanner
          variant="error"
          title="Failed to load history"
          message={historyQuery.error instanceof Error ? historyQuery.error.message : String(historyQuery.error)}
        />
      </Panel>
    );
  }

  return (
    <Panel
      title="Historical market data"
      subtitle={
        <MarketSubtitle
          ticker={activeTicker || ticker}
          availableTickers={availableTickers}
          activeTicker={activeTicker || ticker}
          onTickerChange={setActiveTicker}
        />
      }
      actions={
        <MarketActions
          hasLocalData={hasLocalData}
          isStale={isStale}
          isError={historyQuery.isError}
          isUpdating={refreshMutation.isPending}
          lastDownloaded={lastDownloaded}
          onRefresh={handleRefresh}
        />
      }
      dense={compact}
    >
      <div className="space-y-3">
        {!hasLocalData ? (
          <StateBanner
            variant="empty"
            title="No local market history cached"
            message="Download history to cache stock prices, adjusted returns, dividend yield, and volume locally."
          />
        ) : null}

        {refreshMutation.isError ? (
          <StateBanner
            variant="error"
            title="Update failed"
            message={`${refreshMutation.error instanceof Error ? refreshMutation.error.message : String(refreshMutation.error)}. Retaining previous local cache.`}
          />
        ) : null}

        {hasLocalData ? (
          <>
            <MarketControls
              period={selectedPeriod}
              view={marketView}
              chart={chart}
              selectedSeriesIds={selectedSeriesIds}
              pickerDefs={pickerDefs}
              showOptions={showOptions}
              onPeriodChange={setPeriod}
              onViewChange={handleViewChange}
              onToggleSeries={toggleSeries}
              onChartTypeChange={(type) => setChartType(marketView, type)}
              onToggleOptions={() => setShowOptions((value) => !value)}
              onChartOptionsChange={setChartOptions}
            />

            {selectedPeriod === "custom" ? (
              <CustomRangeControls
                start={customStart}
                end={customEnd}
                invalid={isCustomRangeInvalid}
                onStartChange={setCustomStart}
                onEndChange={setCustomEnd}
              />
            ) : null}

            {summary && !isCustomRangeInvalid ? (
              <MarketSummaryRow
                view={marketView}
                summary={summary}
                observations={observations}
              />
            ) : null}

            <MarketChartState
              historyLoading={historyQuery.isLoading}
              customRangeInvalid={isCustomRangeInvalid}
              observationsCount={observations.length}
              availableSeriesCount={availableSeriesIds.length}
              selectedSeriesCount={selectedSeriesIds.length}
              view={marketView}
            >
              <IndicatorChart
                series={series}
                periods={periods}
                config={chartForMarket}
                height={CHART_HEIGHT}
                xTickFormatter={formatMarketDateTick}
              />
            </MarketChartState>

            {chart.legend && series.length > 0 ? (
              <MarketLegend
                series={series}
                indexMode={chartForMarket.indexMode}
                canRemove={selectedSeriesIds.length > 1}
                onRemove={(id) => {
                  const seriesId = id as MarketSeriesId;
                  setSelectedSeries(
                    marketView,
                    selectedSeriesIds.filter((item) => item !== seriesId),
                  );
                }}
              />
            ) : null}

            {marketView === "yield" ? (
              <DividendHistoryDisclosure dividendEvents={dividendEvents} />
            ) : null}
          </>
        ) : null}
      </div>
    </Panel>
  );
}

function MarketSubtitle({
  ticker,
  availableTickers,
  activeTicker,
  onTickerChange,
}: {
  ticker: string;
  availableTickers: string[];
  activeTicker: string;
  onTickerChange: (ticker: string) => void;
}) {
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span>Yahoo Finance</span>
      <span className="flex items-center gap-1 text-2xs">
        <span>· Ticker</span>
        {availableTickers.length > 1 ? (
          <select
            value={activeTicker}
            onChange={(event) => onTickerChange(event.target.value)}
            className="rounded border border-[var(--color-border-default)] bg-[var(--color-surface-2)] px-1.5 py-0.5 font-mono text-2xs font-semibold text-cyan-300 focus:outline-none focus:border-cyan-500"
          >
            {availableTickers.map((item) => (
              <option key={item} value={item} className="bg-[var(--color-surface-3)] text-[var(--color-text-primary)]">
                {getShareClassLabel(item)}
              </option>
            ))}
          </select>
        ) : (
          <span className="font-mono font-semibold text-cyan-300">{ticker.replace(".SA", "")}</span>
        )}
      </span>
    </span>
  );
}

function MarketActions({
  hasLocalData,
  isStale,
  isError,
  isUpdating,
  lastDownloaded,
  onRefresh,
}: {
  hasLocalData: boolean;
  isStale: boolean;
  isError: boolean;
  isUpdating: boolean;
  lastDownloaded: string | null;
  onRefresh: () => void;
}) {
  const label = isUpdating
    ? "updating"
    : isError
      ? "error"
      : !hasLocalData
        ? "no local data"
        : isStale
          ? "stale"
          : "offline ready";
  const tone = isUpdating || isStale || !hasLocalData ? "warn" : isError ? "error" : "ok";
  const statusTitle = isStale && lastDownloaded
    ? `Cache stale. Local market history remains usable. Local data from ${formatDate(lastDownloaded.slice(0, 10))}.`
    : isStale
      ? "Cache stale. Local market history remains usable."
      : isError
        ? "Refresh failed. Cached local data remains visible when available."
        : undefined;
  return (
    <div className="flex items-center gap-2">
      <StatusBadge
        label={isStale && lastDownloaded ? `${label} · ${formatDate(lastDownloaded.slice(0, 10))}` : label}
        tone={tone}
        title={statusTitle}
      />
      <button
        type="button"
        disabled={isUpdating}
        onClick={onRefresh}
        className="font-mono focus-visible:outline focus-visible:outline-1"
        style={{
          background: "var(--color-surface-1)",
          border: "1px solid var(--color-border-default)",
          borderRadius: "var(--radius-md)",
          color: "var(--color-text-secondary)",
          cursor: isUpdating ? "not-allowed" : "pointer",
          fontSize: "var(--text-xs)",
          height: 26,
          outlineColor: "var(--color-border-focus)",
          padding: "0 10px",
        }}
      >
        {hasLocalData ? "Update Data" : "Download History"}
      </button>
    </div>
  );
}

function StatusBadge({ label, tone, title }: { label: string; tone: "ok" | "warn" | "error"; title?: string }) {
  const color =
    tone === "ok"
      ? "var(--color-state-ok)"
      : tone === "error"
        ? "var(--color-state-err)"
        : "var(--color-state-warn)";
  return (
    <span
      className="font-mono"
      title={title}
      style={{
        background: `color-mix(in srgb, ${color} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 28%, transparent)`,
        borderRadius: "var(--radius-sm)",
        color,
        fontSize: "var(--text-2xs)",
        padding: "3px 6px",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

function MarketControls({
  period,
  view,
  chart,
  selectedSeriesIds,
  pickerDefs,
  showOptions,
  onPeriodChange,
  onViewChange,
  onToggleSeries,
  onChartTypeChange,
  onToggleOptions,
  onChartOptionsChange,
}: {
  period: MarketPeriod;
  view: MarketView;
  chart: ChartAesthetics;
  selectedSeriesIds: MarketSeriesId[];
  pickerDefs: ReturnType<typeof getMarketSeriesPickerDefs>;
  showOptions: boolean;
  onPeriodChange: (period: MarketPeriod) => void;
  onViewChange: (view: MarketView) => void;
  onToggleSeries: (id: string) => void;
  onChartTypeChange: (type: ChartType) => void;
  onToggleOptions: () => void;
  onChartOptionsChange: (patch: Partial<Omit<ChartAesthetics, "type">>) => void;
}) {
  const chartTypeOptions = MARKET_CHART_TYPES[view].map((type) => ({
    value: type,
    label: type[0].toUpperCase() + type.slice(1),
  }));
  const smoothDisabled = chart.type === "bar";
  const indexDisabled = view !== "price";
  const maxSelected = MARKET_MAX_SELECTED_SERIES[view];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="chart-toolbar">
        <Field label="Period">
          <PeriodSelect<MarketPeriod>
            ariaLabel="Market period"
            value={period}
            options={MARKET_PERIOD_OPTIONS}
            onChange={onPeriodChange}
          />
        </Field>

        <Field label="View">
          <Segmented
            ariaLabel="Market view"
            value={view}
            options={MARKET_VIEW_OPTIONS}
            onChange={(value) => onViewChange(value)}
          />
        </Field>

        <Field label="Series">
          <IndicatorPicker
            label="Series"
            defs={pickerDefs}
            selectedIds={selectedSeriesIds}
            onToggle={onToggleSeries}
            maxSelected={maxSelected}
          />
        </Field>

        <Field label="Chart">
          <Segmented
            ariaLabel="Market chart type"
            value={chart.type}
            options={chartTypeOptions}
            onChange={(value) => onChartTypeChange(value)}
          />
        </Field>

        <div className="chart-toolbar__actions">
          <button
            type="button"
            aria-expanded={showOptions}
            onClick={onToggleOptions}
            className="font-mono focus-visible:outline focus-visible:outline-1"
            style={{
              background: showOptions ? "var(--color-surface-3)" : "var(--color-surface-1)",
              border: "1px solid var(--color-border-default)",
              borderRadius: "var(--radius-md)",
              color: "var(--color-text-secondary)",
              cursor: "pointer",
              fontSize: "var(--text-xs)",
              height: 26,
              outlineColor: "var(--color-border-focus)",
              padding: "0 10px",
            }}
          >
            Options
            <span aria-hidden="true" style={{ marginLeft: 6, color: "var(--color-text-tertiary)" }}>
              {showOptions ? "▴" : "▾"}
            </span>
          </button>
        </div>
      </div>

      {showOptions ? (
        <div
          className="flex flex-wrap items-center gap-x-5 gap-y-2"
          style={{
            background: "var(--color-surface-1)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-sm)",
            padding: "8px 12px",
          }}
        >
          <Checkbox
            label="Smooth lines"
            checked={chart.smooth}
            disabled={smoothDisabled}
            title={smoothDisabled ? "Smooth lines apply only to line and area charts." : undefined}
            onChange={(event) => onChartOptionsChange({ smooth: event.currentTarget.checked })}
          />
          <Checkbox
            label="Markers"
            checked={chart.markers}
            onChange={(event) => onChartOptionsChange({ markers: event.currentTarget.checked })}
          />
          <Checkbox
            label="Legend"
            checked={chart.legend}
            onChange={(event) => onChartOptionsChange({ legend: event.currentTarget.checked })}
          />
          <Checkbox
            label="Grid"
            checked={chart.grid}
            onChange={(event) => onChartOptionsChange({ grid: event.currentTarget.checked })}
          />
          <Checkbox
            label="Data labels"
            checked={chart.dataLabels}
            onChange={(event) => onChartOptionsChange({ dataLabels: event.currentTarget.checked })}
          />
          <Checkbox
            label="Index (base 100)"
            checked={chart.indexMode}
            disabled={indexDisabled}
            title={indexDisabled ? "Base-100 indexing is only enabled for price series." : undefined}
            onChange={(event) => onChartOptionsChange({ indexMode: event.currentTarget.checked })}
          />
        </div>
      ) : null}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="chart-toolbar__field" style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
      <span
        style={{
          color: "var(--color-text-tertiary)",
          flexShrink: 0,
          fontSize: "var(--text-2xs)",
          letterSpacing: "0.04em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
      {children}
    </div>
  );
}

function CustomRangeControls({
  start,
  end,
  invalid,
  onStartChange,
  onEndChange,
}: {
  start: string;
  end: string;
  invalid: boolean;
  onStartChange: (value: string) => void;
  onEndChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-2xs">
      <input
        type="date"
        value={start}
        onChange={(event) => onStartChange(event.target.value)}
        className="rounded border border-[var(--color-border-default)] bg-[var(--color-surface-3)] px-2 py-1 font-mono text-[var(--color-text-primary)]"
      />
      <span className="text-[var(--color-text-tertiary)]">to</span>
      <input
        type="date"
        value={end}
        onChange={(event) => onEndChange(event.target.value)}
        className="rounded border border-[var(--color-border-default)] bg-[var(--color-surface-3)] px-2 py-1 font-mono text-[var(--color-text-primary)]"
      />
      {invalid ? (
        <span className="font-medium text-[var(--color-state-err)]">
          Invalid range: start date must be less than or equal to end date.
        </span>
      ) : null}
    </div>
  );
}

function MarketChartState({
  historyLoading,
  customRangeInvalid,
  observationsCount,
  availableSeriesCount,
  selectedSeriesCount,
  view,
  children,
}: {
  historyLoading: boolean;
  customRangeInvalid: boolean;
  observationsCount: number;
  availableSeriesCount: number;
  selectedSeriesCount: number;
  view: MarketView;
  children: ReactNode;
}) {
  if (customRangeInvalid) {
    return <StateBanner variant="error" title="Invalid custom range" message="Adjust the start or end date." />;
  }
  if (historyLoading) {
    return <StateBanner variant="loading" title="Loading market observations..." />;
  }
  if (observationsCount === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No observations in range"
        message="Choose a wider period or download/update local market history."
      />
    );
  }
  if (availableSeriesCount === 0) {
    return (
      <StateBanner
        variant="empty"
        title={`No ${MARKET_VIEW_LABEL[view].toLowerCase()} series available`}
        message="The current market-history payload does not contain a plottable series for this view."
      />
    );
  }
  if (selectedSeriesCount === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No market series selected"
        message="Use the Series picker to choose at least one series to plot."
      />
    );
  }
  return <>{children}</>;
}

function MarketSummaryRow({
  view,
  summary,
  observations,
}: {
  view: MarketView;
  summary: CompanyMarketHistorySummary;
  observations: CompanyMarketHistoryObservation[];
}) {
  const latest = observations[observations.length - 1] ?? null;
  const chips =
    view === "price"
      ? [
          { label: "Latest price", value: formatBRL(summary.final_close) },
          { label: "Observation", value: latest ? formatDate(latest.date) : "—" },
          { label: "Period high", value: formatBRL(summary.period_high) },
          { label: "Period low", value: formatBRL(summary.period_low) },
        ]
      : view === "return"
        ? [
            { label: "Price return", value: formatPct(summary.price_return), tone: toneFor(summary.price_return) },
            { label: "TSR", value: formatPct(summary.total_return), tone: toneFor(summary.total_return) },
            {
              label: "Annualized",
              value: formatPct(summary.annualized_total_return),
              tone: toneFor(summary.annualized_total_return),
            },
          ]
        : view === "yield"
          ? [
              { label: "Latest TTM yield", value: latest?.ttm_dividend_yield != null ? formatPct(latest.ttm_dividend_yield, false) : "—" },
              { label: "Dividends", value: formatBRL(summary.dividends_per_share) },
              { label: "Observation", value: latest ? formatDate(latest.date) : "—" },
            ]
          : [
              { label: "Latest volume", value: formatCompact(latest?.volume ?? null) },
              { label: "Average volume", value: formatCompact(summary.average_daily_volume) },
              { label: "Observation", value: latest ? formatDate(latest.date) : "—" },
            ];

  return (
    <div
      className="market-summary-row"
      style={{
        alignItems: "baseline",
        color: "var(--color-text-secondary)",
        display: "flex",
        flexWrap: "wrap",
        gap: "4px 8px",
        minHeight: 24,
      }}
    >
      {chips.map((chip, index) => (
        <MetricChip key={chip.label} showSeparator={index > 0} {...chip} />
      ))}
    </div>
  );
}

function MetricChip({
  label,
  value,
  tone = "neutral",
  showSeparator,
}: {
  label: string;
  value: string;
  tone?: "ok" | "error" | "neutral";
  showSeparator: boolean;
}) {
  const color =
    tone === "ok"
      ? "var(--color-state-ok)"
      : tone === "error"
        ? "var(--color-state-err)"
        : "var(--color-text-primary)";
  return (
    <span className="flex items-baseline gap-1.5">
      {showSeparator ? <span style={{ color: "var(--color-text-tertiary)" }}>·</span> : null}
      <span
        className="font-mono"
        style={{ color, fontSize: "var(--text-sm)", fontVariantNumeric: "tabular-nums", fontWeight: 650 }}
      >
        {value}
      </span>
      <span
        style={{
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-2xs)",
        }}
      >
        {label}
      </span>
    </span>
  );
}

function MarketLegend({
  series,
  indexMode,
  canRemove,
  onRemove,
}: {
  series: ResolvedSeries[];
  indexMode: boolean;
  canRemove: boolean;
  onRemove: (id: string) => void;
}) {
  return (
    <ul className="flex flex-wrap" style={{ gap: 8, listStyle: "none", margin: 0, minWidth: 0, padding: 0 }}>
      {series.map((item) => (
        <li
          key={item.id}
          className="flex items-center"
          style={{
            background: "var(--color-surface-1)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-sm)",
            gap: 8,
            maxWidth: "100%",
            minWidth: 0,
            padding: "4px 6px",
          }}
        >
          <span aria-hidden="true" style={{ background: item.color, borderRadius: 1, flexShrink: 0, height: 10, width: 10 }} />
          <span
            className="truncate"
            style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)", minWidth: 0 }}
            title={item.label}
          >
            {item.label}
          </span>
          <span
            className="font-mono"
            style={{
              color: "var(--color-text-secondary)",
              fontSize: "var(--text-xs)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {formatValue(item.latest, item.unit, indexMode)}
          </span>
          {canRemove ? (
            <>
              <span aria-hidden="true" style={{ background: "var(--color-border-subtle)", height: 14, width: 1 }} />
              <MiniButton onClick={() => onRemove(item.id)} title="Remove from chart">
                ×
              </MiniButton>
            </>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function MiniButton({ children, onClick, title }: { children: ReactNode; onClick: () => void; title: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="font-mono focus-visible:outline focus-visible:outline-1"
      style={{
        background: "transparent",
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-sm)",
        color: "var(--color-text-tertiary)",
        cursor: "pointer",
        fontSize: "var(--text-2xs)",
        lineHeight: 1,
        outlineColor: "var(--color-border-focus)",
        padding: "3px 5px",
      }}
    >
      {children}
    </button>
  );
}

function DividendHistoryDisclosure({ dividendEvents }: { dividendEvents: CompanyMarketHistoryObservation[] }) {
  return (
    <details
      style={{
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-sm)",
        overflow: "hidden",
      }}
    >
      <summary
        className="focus-visible:outline focus-visible:outline-1"
        style={{
          color: "var(--color-text-tertiary)",
          cursor: "pointer",
          fontSize: "var(--text-xs)",
          fontWeight: 500,
          listStyle: "none",
          padding: "6px 10px",
          userSelect: "none",
        }}
      >
        <span aria-hidden="true" style={{ marginRight: 5 }}>
          ▸
        </span>
        Dividend event history
        {dividendEvents.length > 0 ? (
          <span style={{ color: "var(--color-text-muted, var(--color-text-tertiary))", marginLeft: 6 }}>
            {dividendEvents.length} event{dividendEvents.length !== 1 ? "s" : ""}
          </span>
        ) : null}
      </summary>
      <div style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
        {dividendEvents.length > 0 ? (
          <div className="max-h-56 overflow-y-auto">
            <table className="w-full border-collapse text-2xs font-mono">
              <thead>
                <tr className="border-b border-[var(--color-border-default)] bg-[var(--color-surface-2)] text-left text-[var(--color-text-tertiary)]">
                  <th className="px-3 py-1.5 font-medium">Ex-Date</th>
                  <th className="px-3 py-1.5 text-right font-medium">Cash Paid</th>
                  <th className="px-3 py-1.5 text-right font-medium">TTM Yield</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border-subtle)] text-[var(--color-text-secondary)]">
                {dividendEvents.map((event) => (
                  <tr key={event.date} className="hover:bg-[var(--color-surface-2)]">
                    <td className="px-3 py-1.5">{formatDate(event.date)}</td>
                    <td className="px-3 py-1.5 text-right font-medium text-[var(--color-state-ok)]">
                      {formatBRL(event.dividend)}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {event.ttm_dividend_yield != null ? formatPct(event.ttm_dividend_yield, false) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-4 text-center text-xs text-[var(--color-text-tertiary)]">
            No cash dividend events found in the selected date range.
          </div>
        )}
      </div>
    </details>
  );
}

function getShareClassLabel(ticker: string) {
  const symbol = ticker.replace(".SA", "");
  if (ticker.endsWith("3.SA")) return `${symbol} (Common/ON)`;
  if (ticker.endsWith("4.SA")) return `${symbol} (Preferred/PN)`;
  if (ticker.endsWith("5.SA") || ticker.endsWith("6.SA")) return `${symbol} (Preferred/PN)`;
  if (ticker.endsWith("11.SA")) return `${symbol} (Unit)`;
  return symbol;
}

function formatBRL(value: number | null | undefined) {
  if (value == null) return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function formatPct(value: number | null | undefined, showSign = true) {
  if (value == null) return "—";
  const sign = showSign && value >= 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatCompact(value: number | null | undefined) {
  if (value == null) return "—";
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function formatDate(date: string) {
  if (!date) return "—";
  const [year, month, day] = date.split("-");
  if (!year || !month || !day) return date;
  return `${day}/${month}/${year}`;
}

function toneFor(value: number | null | undefined): "ok" | "error" | "neutral" {
  if (value == null) return "neutral";
  return value >= 0 ? "ok" : "error";
}
