import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { DEFAULT_INDICATOR_CHART_HEIGHT, IndicatorChart } from "@/components/indicators/IndicatorChart";
import { IndicatorPicker } from "@/components/indicators/IndicatorPicker";
import { EditableSeriesLegend } from "@/components/indicators/IndicatorLegend";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { PeriodSelect } from "@/components/ui/PeriodSelect";
import { exportMarketHistoryWorkbook } from "@/lib/api/exports";
import { fetchMarketHistory, fetchMarketHistoryStatus, triggerMarketHistoryRefresh } from "@/lib/api/marketHistory";
import type { CompanyMarketHistoryObservation, CompanyMarketHistorySummary } from "@/lib/bridge/types";
import type { ChartAesthetics } from "@/lib/indicators/types";
import {
  MARKET_MAX_SELECTED_SERIES,
  MARKET_SERIES_DEFS,
  MARKET_PERIOD_OPTIONS,
  MARKET_VIEW_OPTIONS,
  buildMarketChartSeries,
  buildMarketPeriods,
  canEnableMarketMetric,
  formatMarketDateTick,
  getAvailableMarketSeries,
  getMarketSeriesPickerDefs,
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

export function MarketHistoryPanel({ cdCvm, bridgeReady, compact = false }: MarketHistoryPanelProps) {
  const queryClient = useQueryClient();
  const [customStart, setCustomStart] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");
  const [activeTicker, setActiveTicker] = useState<string>("");
  const [showOptions, setShowOptions] = useState(false);
  const {
    config,
    chart,
    setSelectedViews,
    setPeriod,
    setSelectedSeries,
    setSeriesStyle,
    setChartOptions,
  } = useMarketHistoryConfig();

  const selectedPeriod = config.period;
  const selectedViews = config.selectedViews;

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
    () => getAvailableMarketSeries(observations, selectedViews),
    [observations, selectedViews],
  );
  const selectedSeriesIds = useMemo(
    () =>
      sanitizeMarketSeriesSelection(
        selectedViews,
        selectedViews.flatMap((view) => config.selectedSeriesByView[view]),
        availableSeriesIds,
      ),
    [availableSeriesIds, config.selectedSeriesByView, selectedViews],
  );
  const pickerDefs = useMemo(
    () => getMarketSeriesPickerDefs(observations, selectedViews),
    [observations, selectedViews],
  );
  const metricPickerDefs = useMemo(
    () => MARKET_VIEW_OPTIONS.map((option) => ({
      id: option.value,
      label: option.label,
      category: "Market metrics",
      unit: "number" as const,
      isPlaceholder: false,
      available: true,
    })),
    [],
  );
  const periods = useMemo(() => buildMarketPeriods(observations), [observations]);
  const series = useMemo(
    () =>
      buildMarketChartSeries({
        observations,
        views: selectedViews,
        selectedIds: selectedSeriesIds,
        chartType: config.chartType,
        indexMode: chart.indexMode,
        seriesStyles: config.seriesStyles,
      }),
    [chart.indexMode, config.chartType, config.seriesStyles, observations, selectedSeriesIds, selectedViews],
  );
  const chartForMarket = useMemo(
    () => ({
      ...chart,
      markers: shouldRenderMarketMarkers(chart.markers, observations.length),
    }),
    [chart, observations.length],
  );
  const exportMutation = useMutation({
    mutationFn: () =>
      exportMarketHistoryWorkbook({
        cdCvm,
        ticker: activeTicker || ticker,
        period: selectedPeriod,
        customStart: selectedPeriod === "custom" ? customStart : null,
        customEnd: selectedPeriod === "custom" ? customEnd : null,
        interval,
        view: selectedViews.join(","),
        selectedSeries: selectedSeriesIds,
        valueMode: selectedViews.length === 1 && selectedViews[0] === "price" && chart.indexMode ? "base_100" : null,
        chartType: config.chartType,
      }),
  });
  const exportResult = exportMutation.data?.mode === "desktop" ? exportMutation.data.result : null;
  const exportBrowserReason = exportMutation.data?.mode === "browser" ? exportMutation.data.reason : null;
  const exportError =
    exportMutation.error instanceof Error
      ? exportMutation.error.message
      : exportMutation.error
        ? String(exportMutation.error)
        : exportResult?.error ?? exportBrowserReason ?? null;
  const exportDisabledReason = !bridgeReady
    ? "Desktop bridge is not ready."
    : !(activeTicker || ticker)
      ? "No ticker resolved."
      : !hasLocalData
        ? "No local market history is cached."
        : historyQuery.isLoading && observations.length === 0
          ? "Market observations are still loading."
          : isCustomRangeInvalid
            ? "Custom date range is invalid."
            : observations.length === 0
              ? "The current query has no observations."
              : selectedSeriesIds.length === 0
                ? "Select at least one visible series."
                : null;
  function handleRefresh() {
    refreshMutation.mutate();
  }

  function toggleSeries(id: string) {
    const seriesId = id as MarketSeriesId;
    const view = MARKET_SERIES_DEFS[seriesId]?.view;
    if (!view) return;
    const selectedForView = config.selectedSeriesByView[view];
    const exists = selectedForView.includes(seriesId);
    const next = exists
      ? selectedForView.filter((item) => item !== seriesId)
      : selectedForView.length < MARKET_MAX_SELECTED_SERIES[view]
        ? [...selectedForView, seriesId]
        : selectedForView;
    setSelectedSeries(view, next);
  }

  function toggleMetric(view: MarketView) {
    const next = selectedViews.includes(view)
      ? selectedViews.filter((item) => item !== view)
      : [...selectedViews, view];
    setSelectedViews(next);
  }

  if (!bridgeReady || (statusQuery.isLoading && !activeTicker)) {
    return (
      <Panel title="Historical Market Data" subtitle="Market price, return, dividend yield, and volume.">
        <StateBanner variant="loading" title="Loading market history status..." />
      </Panel>
    );
  }

  if (statusQuery.isError) {
    return (
      <Panel title="Historical Market Data">
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
      <Panel title="Historical Market Data">
        <StateBanner variant="browser-only" message={statusQuery.data.reason} />
      </Panel>
    );
  }

  if (!ticker && !activeTicker) {
    return (
      <Panel title="Historical Market Data">
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
        title="Historical Market Data"
        actions={
          <MarketActions
            hasLocalData={hasLocalData}
            isStale={isStale}
            isError
            isUpdating={refreshMutation.isPending}
            isExporting={exportMutation.isPending}
            exportDisabledReason={exportDisabledReason}
            lastDownloaded={lastDownloaded}
            onRefresh={handleRefresh}
            onExport={() => exportMutation.mutate()}
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
      title={
        <span className="flex flex-wrap items-center gap-2">
          <span>Historical Market Data</span>
          {availableTickers.length > 1 ? (
            <MarketTickerSelect
              availableTickers={availableTickers}
              activeTicker={activeTicker || ticker}
              onTickerChange={setActiveTicker}
            />
          ) : null}
        </span>
      }
      actions={
        hasLocalData ? (
          <StatusBadge
            {...getMarketDataStatus({
              hasLocalData,
              isStale,
              isError: historyQuery.isError,
              isUpdating: refreshMutation.isPending,
              lastDownloaded,
            })}
          />
        ) : (
          <MarketActions
            hasLocalData={hasLocalData}
            isStale={isStale}
            isError={historyQuery.isError}
            isUpdating={refreshMutation.isPending}
            isExporting={exportMutation.isPending}
            exportDisabledReason={exportDisabledReason}
            lastDownloaded={lastDownloaded}
            onRefresh={handleRefresh}
            onExport={() => exportMutation.mutate()}
            showStatus={false}
          />
        )
      }
      dense={compact}
      style={{ display: "flex", flex: 1, flexDirection: "column", height: "100%" }}
    >
      <div className="space-y-3" style={{ flex: 1 }}>
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

        {exportMutation.isSuccess && exportResult?.ok ? (
          <StateBanner
            variant="success"
            size="dense"
            title="Export complete"
            message={`${exportResult.file_name ?? "Market data workbook"} exported with ${exportResult.observation_count ?? observations.length} observations to ${exportResult.output_dir ?? "the output folder"}.`}
          />
        ) : null}

        {exportError ? (
          <StateBanner
            variant="error"
            size="dense"
            title="Export failed"
            message={exportError}
          />
        ) : null}

        {hasLocalData ? (
          <>
            <MarketControls
              period={selectedPeriod}
              selectedViews={selectedViews}
              chart={chart}
              selectedSeriesIds={selectedSeriesIds}
              pickerDefs={pickerDefs}
              metricPickerDefs={metricPickerDefs}
              showOptions={showOptions}
              onPeriodChange={setPeriod}
              onToggleMetric={toggleMetric}
              onToggleSeries={toggleSeries}
              onToggleOptions={() => setShowOptions((value) => !value)}
              onCloseOptions={() => setShowOptions(false)}
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

            {summary && !isCustomRangeInvalid && selectedViews.length === 1 ? (
              <MarketSummaryRow
                view={selectedViews[0]}
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
            >
              <IndicatorChart
                series={series}
                periods={periods}
                config={chartForMarket}
                height={DEFAULT_INDICATOR_CHART_HEIGHT}
                xTickFormatter={formatMarketDateTick}
              />
            </MarketChartState>

            {chartForMarket.legend ? <EditableSeriesLegend series={series} stylesById={new Map(Object.entries(config.seriesStyles))} onSetColor={(id, color) => setSeriesStyle(id as MarketSeriesId, { color })} onSetType={(id, type) => setSeriesStyle(id as MarketSeriesId, { type })} /> : null}

            {selectedViews.includes("yield") ? (
              <DividendHistoryDisclosure dividendEvents={dividendEvents} />
            ) : null}
          </>
        ) : null}
      </div>
    </Panel>
  );
}

function MarketTickerSelect({
  availableTickers,
  activeTicker,
  onTickerChange,
}: {
  availableTickers: string[];
  activeTicker: string;
  onTickerChange: (ticker: string) => void;
}) {
  return (
    <select
      aria-label="Market ticker"
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
  );
}

function MarketActions({
  hasLocalData,
  isStale,
  isError,
  isUpdating,
  isExporting,
  exportDisabledReason,
  lastDownloaded,
  onRefresh,
  onExport,
  showStatus = true,
}: {
  hasLocalData: boolean;
  isStale: boolean;
  isError: boolean;
  isUpdating: boolean;
  isExporting: boolean;
  exportDisabledReason: string | null;
  lastDownloaded: string | null;
  onRefresh: () => void;
  onExport: () => void;
  showStatus?: boolean;
}) {
  const status = getMarketDataStatus({ hasLocalData, isStale, isError, isUpdating, lastDownloaded });
  return (
    <div className="flex flex-wrap items-center gap-2">
      {showStatus ? <StatusBadge label={status.label} tone={status.tone} title={status.title} /> : null}
      <button
        type="button"
        disabled={isUpdating}
        onClick={onRefresh}
        className="font-mono focus-visible:outline focus-visible:outline-1"
        style={marketActionButtonStyle(isUpdating)}
      >
        {hasLocalData ? "Update data" : "Download history"}
      </button>
      <Button
        type="button"
        variant="secondary"
        size="xs"
        loading={isExporting}
        disabled={Boolean(exportDisabledReason)}
        title={exportDisabledReason ?? "Export the currently visible market dataset to Excel."}
        onClick={onExport}
        style={{ height: 26, fontFamily: "var(--font-mono)", padding: "0 10px" }}
      >
        {isExporting ? "Exporting..." : "Export Excel"}
      </Button>
    </div>
  );
}

export function getMarketDataStatus({
  hasLocalData,
  isStale,
  isError,
  isUpdating,
  lastDownloaded,
}: {
  hasLocalData: boolean;
  isStale: boolean;
  isError: boolean;
  isUpdating: boolean;
  lastDownloaded: string | null;
}) {
  const label = isUpdating
    ? "Updating"
    : isError
      ? "Update failed"
      : !hasLocalData
        ? "No local data"
        : isStale
          ? "Stale"
          : "Current";
  const tone = isUpdating || isStale || !hasLocalData ? "warn" : isError ? "error" : "ok";
  const statusTitle = isStale && lastDownloaded
    ? `Cache stale. Local market history remains usable. Local data from ${formatDate(lastDownloaded.slice(0, 10))}.`
    : isStale
      ? "Cache stale. Local market history remains usable."
      : isError
        ? "Refresh failed. Cached local data remains visible when available."
        : undefined;
  return {
    label: isStale && lastDownloaded ? `${label} · ${formatDate(lastDownloaded.slice(0, 10))}` : label,
    tone,
    title: statusTitle,
  } as const;
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

function marketActionButtonStyle(disabled: boolean) {
  return {
    background: "var(--color-surface-1)",
    border: "1px solid var(--color-border-default)",
    borderRadius: "var(--radius-md)",
    color: "var(--color-text-secondary)",
    cursor: disabled ? "not-allowed" : "pointer",
    fontSize: "var(--text-xs)",
    height: 26,
    outlineColor: "var(--color-border-focus)",
    padding: "0 10px",
  };
}

function MarketControls({
  period,
  selectedViews,
  chart,
  selectedSeriesIds,
  pickerDefs,
  metricPickerDefs,
  showOptions,
  onPeriodChange,
  onToggleMetric,
  onToggleSeries,
  onToggleOptions,
  onCloseOptions,
  onChartOptionsChange,
}: {
  period: MarketPeriod;
  selectedViews: MarketView[];
  chart: ChartAesthetics;
  selectedSeriesIds: MarketSeriesId[];
  pickerDefs: ReturnType<typeof getMarketSeriesPickerDefs>;
  metricPickerDefs: ReturnType<typeof getMarketSeriesPickerDefs>;
  showOptions: boolean;
  onPeriodChange: (period: MarketPeriod) => void;
  onToggleMetric: (view: MarketView) => void;
  onToggleSeries: (id: string) => void;
  onToggleOptions: () => void;
  onCloseOptions: () => void;
  onChartOptionsChange: (patch: Partial<Omit<ChartAesthetics, "type">>) => void;
}) {
  const optionsRef = useRef<HTMLDivElement>(null);
  const smoothDisabled = chart.type === "bar";
  const indexDisabled = selectedViews.length !== 1 || selectedViews[0] !== "price";

  useEffect(() => {
    if (!showOptions) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseOptions();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onCloseOptions, showOptions]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="chart-toolbar company-chart-toolbar">
        <Field label="Period">
          <PeriodSelect<MarketPeriod>
            ariaLabel="Market period"
            value={period}
            options={MARKET_PERIOD_OPTIONS}
            onChange={onPeriodChange}
          />
        </Field>

        <Field label="Metrics">
          <IndicatorPicker
            label="Metrics"
            defs={metricPickerDefs}
            selectedIds={selectedViews}
            maxSelected={MARKET_VIEW_OPTIONS.length}
            onToggle={(id) => onToggleMetric(id as MarketView)}
            getDisabledReason={(id, checked) => {
              const metric = id as MarketView;
              if (checked && selectedViews.length === 1) return "required";
              return !checked && !canEnableMarketMetric(selectedViews, metric) ? "two units" : null;
            }}
          />
        </Field>

        <Field label="Series">
          <IndicatorPicker
            label="Series"
            defs={pickerDefs}
            selectedIds={selectedSeriesIds}
            onToggle={onToggleSeries}
            maxSelected={6}
          />
        </Field>

        <div ref={optionsRef} className="chart-toolbar__actions" style={{ position: "relative" }}>
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

          {showOptions ? (
            <>
              <button
                type="button"
                aria-label="Close chart options"
                tabIndex={-1}
                onClick={onCloseOptions}
                style={{
                  position: "fixed",
                  inset: 0,
                  zIndex: 40,
                  background: "transparent",
                  border: "none",
                  cursor: "default",
                }}
              />
              <div
                role="dialog"
                aria-label="Market chart options"
                className="flex flex-wrap items-center gap-x-5 gap-y-2"
                style={{
                  position: "absolute",
                  top: "calc(100% + 6px)",
                  right: 0,
                  zIndex: 50,
                  width: "min(340px, calc(100vw - 32px))",
                  background: "var(--color-surface-2)",
                  border: "1px solid var(--color-border-default)",
                  borderRadius: "var(--radius-md)",
                  boxShadow: "var(--shadow-overlay)",
                  padding: "10px 12px",
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
            </>
          ) : null}
        </div>
      </div>
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
  children,
}: {
  historyLoading: boolean;
  customRangeInvalid: boolean;
  observationsCount: number;
  availableSeriesCount: number;
  selectedSeriesCount: number;
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
        title="No market series available"
        message="The current market-history payload does not contain a plottable series for the selected metrics."
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
