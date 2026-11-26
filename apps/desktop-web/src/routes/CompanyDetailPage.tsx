import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { CompanyCommandBar, CompanyExportCard } from "@/components/CompanyCommandBar";
import { EntityHeader } from "@/components/EntityHeader";
import { MarketHistoryPanel } from "@/components/MarketHistoryPanel";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { DEFAULT_INDICATOR_CHART_HEIGHT, IndicatorChart } from "@/components/indicators/IndicatorChart";
import { IndicatorControls } from "@/components/indicators/IndicatorControls";
import { EditableSeriesLegend } from "@/components/indicators/IndicatorLegend";
import {
  fetchCompanyKpis,
  fetchCompanyYears,
  type CompanyKpisResult,
  type CompanyYearsResultUI,
} from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type {
  CompanyFinancialReadiness,
  KPIBundle,
} from "@/lib/bridge/types";
import { buildIndicatorDefs, defaultSelectedIds } from "@/lib/indicators/catalog";
import { resolveSeries, selectPeriods } from "@/lib/indicators/series";
import type { ChartType, Frequency, IndicatorSelection } from "@/lib/indicators/types";
import { useIndicatorConfig } from "@/lib/indicators/useIndicatorConfig";
import { QueuedCompanyNotice } from "@/components/shell/QueuedCompanyNotice";

const MAX_SELECTED = 6;
const DEFAULT_RECENT_YEARS = 5;
type YearPeriodPreset = "last5" | "last10" | "all";

export const COMPANY_OVERVIEW_SECTIONS = [
  "company-command-bar",
  "market-history",
  "financial-indicators",
] as const;

const YEAR_PERIOD_OPTIONS: Array<{ value: YearPeriodPreset; label: string }> = [
  { value: "last5", label: "Last 5" },
  { value: "last10", label: "Last 10" },
  { value: "all", label: "All" },
];

export function selectedYearsForPreset(
  years: number[],
  preset: YearPeriodPreset,
): number[] {
  const sortedYears = [...years].sort((a, b) => a - b);
  if (preset === "all") return sortedYears;
  const count = preset === "last10" ? 10 : DEFAULT_RECENT_YEARS;
  return sortedYears.slice(-count);
}

// ---------------------------------------------------------------------------
// Page root
// ---------------------------------------------------------------------------

export function CompanyDetailPage() {
  const params = useParams<{ cdCvm: string }>();
  const cdCvm = Number.parseInt(params.cdCvm ?? "", 10);
  const [bridgeReady, setBridgeReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!Number.isFinite(cdCvm) || cdCvm <= 0) {
    return (
      <StateBanner variant="error" message={`Invalid CVM: "${params.cdCvm}"`} />
    );
  }

  return (
    <section className="space-y-4">
      <div className="grid items-stretch gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)_minmax(260px,1fr)]">
        <EntityHeader cdCvm={cdCvm} activeTab="overview" />
        <QueuedCompanyNotice cdCvm={cdCvm} />
        <CompanyCommandBar cdCvm={cdCvm} bridgeReady={bridgeReady} hideExport downloadControls />
        <CompanyExportCard cdCvm={cdCvm} />
      </div>
      <CompanyReferenceWorkspace cdCvm={cdCvm} bridgeReady={bridgeReady} />
    </section>
  );
}

// ---------------------------------------------------------------------------
// Workspace: command bar + two-column analytical grid
// ---------------------------------------------------------------------------

function CompanyReferenceWorkspace({
  cdCvm,
  bridgeReady,
}: {
  cdCvm: number;
  bridgeReady: boolean;
}) {
  const yearsQuery = useQuery<CompanyYearsResultUI>({
    queryKey: ["company-years", cdCvm],
    queryFn: () => fetchCompanyYears(cdCvm),
    enabled: bridgeReady,
  });

  const allYears = useMemo(
    () => (yearsQuery.data?.mode === "desktop" ? yearsQuery.data.years : []),
    [yearsQuery.data],
  );

  const [yearPreset, setYearPreset] = useState<YearPeriodPreset>("last5");
  const sortedYears = useMemo(() => [...allYears].sort((a, b) => a - b), [allYears]);
  const selectedYears = useMemo(
    () => selectedYearsForPreset(sortedYears, yearPreset),
    [sortedYears, yearPreset],
  );

  const kpiQuery = useQuery<CompanyKpisResult>({
    queryKey: ["company-kpis", cdCvm, selectedYears.join(",")],
    queryFn: () => fetchCompanyKpis(cdCvm, selectedYears),
    enabled: bridgeReady && selectedYears.length > 0,
  });

  const bundle = kpiQuery.data?.mode === "desktop" ? kpiQuery.data.bundle : null;

  return (
    <div className="space-y-4">

      {/* Two-column analytical workspace */}
      <AnalyticalWorkspace
        cdCvm={cdCvm}
        bridgeReady={bridgeReady}
        bundle={bundle}
        yearsQuery={yearsQuery}
        kpiQuery={kpiQuery}
        sortedYears={sortedYears}
        selectedYears={selectedYears}
        yearPreset={yearPreset}
        onYearPresetChange={setYearPreset}
      />
    </div>
  );
}


type FinancialReadinessDisplayState =
  | "ready"
  | "partial"
  | "stale"
  | "failed"
  | "missing"
  | "unknown";

/**
 * Converts the additive bridge vocabulary into mutually exclusive UI states.
 * Unknown raw refresh states remain visible as review-required rather than
 * being inferred as successful.
 */
export function getCompanyFinancialReadinessState(
  readiness: CompanyFinancialReadiness,
): FinancialReadinessDisplayState {
  const availability = normalizeFinancialReadinessValue(readiness.availability_state);
  const freshness = normalizeFinancialReadinessValue(readiness.freshness_state);
  const refresh = normalizeFinancialReadinessValue(readiness.refresh_state);

  if (refresh === "failed" || readiness.last_refresh_error) return "failed";
  if (availability === "missing") return "missing";
  if (availability === "partial") return "partial";
  if (freshness === "stale" || refresh === "no_data") return "stale";
  if (availability === "ready" && freshness === "fresh" && refresh === "successful") {
    return "ready";
  }
  return "unknown";
}

function normalizeFinancialReadinessValue(value: string | null | undefined): string {
  return String(value || "").trim().toLowerCase();
}

// ---------------------------------------------------------------------------
// Responsive two-column grid
// ---------------------------------------------------------------------------

function AnalyticalWorkspace({
  cdCvm,
  bridgeReady,
  bundle,
  yearsQuery,
  kpiQuery,
  sortedYears,
  selectedYears,
  yearPreset,
  onYearPresetChange,
}: {
  cdCvm: number;
  bridgeReady: boolean;
  bundle: KPIBundle | null;
  yearsQuery: UseQueryResult<CompanyYearsResultUI>;
  kpiQuery: UseQueryResult<CompanyKpisResult>;
  sortedYears: number[];
  selectedYears: number[];
  yearPreset: YearPeriodPreset;
  onYearPresetChange: (preset: YearPeriodPreset) => void;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
        gap: "var(--spacing-4, 16px)",
        alignItems: "stretch",
      }}
      className="workspace-grid"
    >
      {/* Left: Historical market data */}
      <div className="min-w-0" style={{ display: "flex" }}>
        <MarketHistoryPanel cdCvm={cdCvm} bridgeReady={bridgeReady} compact />
      </div>

      {/* Right: Financial indicator chart */}
      <div className="min-w-0" style={{ display: "flex" }}>
        <CompactIndicatorPanel
          bundle={bundle}
          yearsQuery={yearsQuery}
          kpiQuery={kpiQuery}
          sortedYears={sortedYears}
          selectedYears={selectedYears}
          yearPreset={yearPreset}
          onYearPresetChange={onYearPresetChange}
          bridgeReady={bridgeReady}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Right panel: Financial indicator chart (compact, Overview-specific)
// ---------------------------------------------------------------------------

interface CompactIndicatorPanelProps {
  bundle: KPIBundle | null;
  yearsQuery: UseQueryResult<CompanyYearsResultUI>;
  kpiQuery: UseQueryResult<CompanyKpisResult>;
  sortedYears: number[];
  selectedYears: number[];
  yearPreset: YearPeriodPreset;
  onYearPresetChange: (preset: YearPeriodPreset) => void;
  bridgeReady: boolean;
}

function CompactIndicatorPanel({
  bundle,
  yearsQuery,
  kpiQuery,
  sortedYears,
  selectedYears,
  yearPreset,
  onYearPresetChange,
  bridgeReady,
}: CompactIndicatorPanelProps) {
  // Independent indicator config (persisted to localStorage, shared with any
  // future Indicators tab usage).
  const { config, setFrequency, setSelected, setChart } = useIndicatorConfig();
  const { frequency, chart } = config;

  if (!bridgeReady || yearsQuery.isLoading) {
    return (
      <Panel title="Financial Indicators">
        <StateBanner variant="loading" title="Loading years…" />
      </Panel>
    );
  }

  if (yearsQuery.isError) {
    return (
      <Panel title="Financial Indicators">
        <StateBanner
          variant="error"
          onRetry={() => yearsQuery.refetch()}
          message={
            yearsQuery.error instanceof Error
              ? yearsQuery.error.message
              : String(yearsQuery.error)
          }
        />
      </Panel>
    );
  }

  if (yearsQuery.data?.mode === "browser") {
    return (
      <Panel title="Financial Indicators">
        <StateBanner variant="browser-only" message={yearsQuery.data.reason} />
      </Panel>
    );
  }

  if (sortedYears.length === 0) {
    return (
      <Panel title="Financial Indicators">
        <StateBanner
          variant="empty"
          title="No financial history yet"
          message="Download or update this company's data to compute indicators."
        />
      </Panel>
    );
  }

  if (kpiQuery.isLoading) {
    return (
      <Panel title="Financial Indicators">
        <StateBanner variant="loading" title="Loading indicators…" />
      </Panel>
    );
  }

  if (kpiQuery.isError) {
    return (
      <Panel title="Financial Indicators">
        <StateBanner
          variant="error"
          onRetry={() => kpiQuery.refetch()}
          message={
            kpiQuery.error instanceof Error
              ? kpiQuery.error.message
              : String(kpiQuery.error)
          }
        />
      </Panel>
    );
  }

  if (kpiQuery.data?.mode === "browser") {
    return (
      <Panel title="Financial Indicators">
        <StateBanner variant="browser-only" message={kpiQuery.data.reason} />
      </Panel>
    );
  }

  if (!bundle) {
    return (
      <Panel title="Financial Indicators">
        <StateBanner
          variant="empty"
          title="No indicators"
          message="Bridge returned an empty payload for the selected years."
        />
      </Panel>
    );
  }

  return (
    <IndicatorChartPanel
      bundle={bundle}
      selectedYears={selectedYears}
      yearPreset={yearPreset}
      onYearPresetChange={onYearPresetChange}
      frequency={frequency}
      setFrequency={setFrequency}
      chart={chart}
      setChart={setChart}
      config={config}
      setSelected={setSelected}
    />
  );
}

// ---------------------------------------------------------------------------
// Indicator chart panel body (receives a resolved bundle)
// ---------------------------------------------------------------------------

function IndicatorChartPanel({
  bundle,
  selectedYears,
  yearPreset,
  onYearPresetChange,
  frequency,
  setFrequency,
  chart,
  setChart,
  config,
  setSelected,
}: {
  bundle: KPIBundle;
  selectedYears: number[];
  yearPreset: YearPeriodPreset;
  onYearPresetChange: (preset: YearPeriodPreset) => void;
  frequency: Frequency;
  setFrequency: (f: Frequency) => void;
  chart: ReturnType<typeof useIndicatorConfig>["config"]["chart"];
  setChart: ReturnType<typeof useIndicatorConfig>["setChart"];
  config: ReturnType<typeof useIndicatorConfig>["config"];
  setSelected: ReturnType<typeof useIndicatorConfig>["setSelected"];
}) {
  const activeTable = frequency === "annual" ? bundle.annual : bundle.quarterly;

  const annualDefs = useMemo(() => buildIndicatorDefs(bundle.annual), [bundle.annual]);
  const defs = useMemo(() => buildIndicatorDefs(activeTable), [activeTable]);
  const defsById = useMemo(() => new Map(defs.map((d) => [d.id, d])), [defs]);

  const quarterlyPeriods = useMemo(
    () => selectPeriods(bundle.quarterly, "quarterly", selectedYears),
    [bundle.quarterly, selectedYears],
  );
  const quarterlyAvailable = quarterlyPeriods.length > 0;

  const periods = useMemo(
    () => selectPeriods(activeTable, frequency, selectedYears),
    [activeTable, frequency, selectedYears],
  );

  // Seed default indicator selection on first use.
  const seededRef = useRef(false);
  useEffect(() => {
    if (!seededRef.current && config.selected.length === 0 && annualDefs.length > 0) {
      seededRef.current = true;
      const seeded: IndicatorSelection[] = defaultSelectedIds(annualDefs).map((id) => ({
        id,
        axis: "auto",
        type: "auto",
      }));
      if (seeded.length > 0) setSelected(seeded);
    }
  }, [annualDefs, config.selected.length, setSelected]);

  // Fall back to annual if quarterly is unavailable.
  useEffect(() => {
    if (frequency === "quarterly" && !quarterlyAvailable) setFrequency("annual");
  }, [frequency, quarterlyAvailable, setFrequency]);

  const plottable = useMemo(
    () => config.selected.filter((s) => defsById.get(s.id)?.available),
    [config.selected, defsById],
  );

  const series = useMemo(
    () => resolveSeries(activeTable, periods, plottable, chart.type, chart.indexMode),
    [activeTable, periods, plottable, chart.type, chart.indexMode],
  );
  const selectionById = useMemo(
    () => new Map(config.selected.map((selection) => [selection.id, selection] as const)),
    [config.selected],
  );
  const selectedExistingCount = config.selected.filter((s) => defsById.has(s.id)).length;
  const droppedCount = selectedExistingCount - plottable.length;
  const noIndicatorsAtAll = annualDefs.filter((d) => d.available).length === 0;

  function toggleIndicator(id: string) {
    const exists = config.selected.some((s) => s.id === id);
    if (exists) {
      setSelected(config.selected.filter((s) => s.id !== id));
    } else if (config.selected.length < MAX_SELECTED) {
      setSelected([...config.selected, { id, axis: "auto", type: "auto" }]);
    }
  }

  function setSeriesStyle(id: string, patch: { color?: string; type?: ChartType }) {
    setSelected(config.selected.map((selection) => selection.id === id ? { ...selection, ...patch } : selection));
  }

  function setYearPreset(preset: string) {
    onYearPresetChange(preset as YearPeriodPreset);
  }

  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <Panel
        title="Financial Indicators"
        dense
        actions={
          <span
            className="font-mono"
            style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}
          >
            {series.length}/{config.selected.length} plotted
          </span>
        }
        style={{ display: "flex", flexDirection: "column", height: "100%" }}
      >
        <div className="space-y-3" style={{ flex: 1 }}>
          {/* Keep primary analytical choices visible; place configuration and series editing under Options. */}
          <IndicatorControls
            periodValue={yearPreset}
            periodOptions={YEAR_PERIOD_OPTIONS}
            onPeriodChange={setYearPreset}
            frequency={frequency}
            quarterlyAvailable={quarterlyAvailable}
            onFrequencyChange={setFrequency}
            defs={defs}
            selectedIds={config.selected.map((s) => s.id)}
            onToggleIndicator={toggleIndicator}
            maxSelected={MAX_SELECTED}
            chart={chart}
            onChartChange={setChart}
            showLegendOption={false}
          />

          {/* Chart area with state machine */}
          <ChartArea
            noIndicatorsAtAll={noIndicatorsAtAll}
            frequency={frequency}
            quarterlyAvailable={quarterlyAvailable}
            periodsCount={periods.length}
            selectedCount={config.selected.length}
            plottedCount={series.length}
          >
            <IndicatorChart
              series={series}
              periods={periods}
              config={chart}
              height={DEFAULT_INDICATOR_CHART_HEIGHT}
            />
          </ChartArea>

          {chart.legend ? <EditableSeriesLegend series={series} stylesById={new Map([...selectionById].map(([id, selection]) => [id, { color: selection.color, type: selection.type === "auto" ? undefined : selection.type }]))} onSetColor={(id, color) => setSeriesStyle(id, { color })} onSetType={(id, type) => setSeriesStyle(id, { type })} /> : null}

          {/* Dropped indicators warning */}
          {droppedCount > 0 ? (
            <p
              style={{
                color: "var(--color-state-warn)",
                fontSize: "var(--text-xs)",
                margin: 0,
              }}
            >
              {droppedCount} selected indicator{droppedCount > 1 ? "s are" : " is"} unavailable
              for the {frequency} view and {droppedCount > 1 ? "were" : "was"} hidden.
            </p>
          ) : null}

        </div>
      </Panel>

    </div>
  );
}

// ---------------------------------------------------------------------------
// Chart-area state machine (same logic as IndicatorWorkspace)
// ---------------------------------------------------------------------------

function ChartArea({
  noIndicatorsAtAll,
  frequency,
  quarterlyAvailable,
  periodsCount,
  selectedCount,
  plottedCount,
  children,
}: {
  noIndicatorsAtAll: boolean;
  frequency: "annual" | "quarterly";
  quarterlyAvailable: boolean;
  periodsCount: number;
  selectedCount: number;
  plottedCount: number;
  children: ReactNode;
}) {
  if (noIndicatorsAtAll) {
    return (
      <StateBanner
        variant="empty"
        title="No indicators available"
        message="The KPI engine returned no computable indicators for this company. Update this company's data and try again."
      />
    );
  }
  if (frequency === "quarterly" && (!quarterlyAvailable || periodsCount === 0)) {
    return (
      <StateBanner
        variant="empty"
        title="No quarterly data"
        message="This company has no quarterly (LTM) indicator series for the selected years. Switch to Annual or widen the year range."
      />
    );
  }
  if (selectedCount === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No indicators selected"
        message="Use the Indicators picker to choose what to plot."
      />
    );
  }
  if (plottedCount === 0) {
    return (
      <StateBanner
        variant="empty"
        title="Selected indicators unavailable"
        message={`None of the selected indicators can be computed for the ${frequency} view. Pick different indicators or switch frequency.`}
      />
    );
  }
  return <>{children}</>;
}
