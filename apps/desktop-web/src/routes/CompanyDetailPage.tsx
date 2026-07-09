import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { CompanyCommandBar } from "@/components/CompanyCommandBar";
import { EntityHeader } from "@/components/EntityHeader";
import { MarketHistoryPanel } from "@/components/MarketHistoryPanel";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import { IndicatorChart } from "@/components/indicators/IndicatorChart";
import { IndicatorControls } from "@/components/indicators/IndicatorControls";
import { IndicatorLegend } from "@/components/indicators/IndicatorLegend";
import { IndicatorTable } from "@/components/indicators/IndicatorTable";
import { formatValue } from "@/lib/indicators/format";
import {
  fetchCompanyInfo,
  fetchCompanyKpis,
  fetchCompanyYears,
  type CompanyInfoResult,
  type CompanyKpisResult,
  type CompanyYearsResultUI,
} from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { KPIBundle, TabularData, TabularRow } from "@/lib/bridge/types";
import { formatUnit } from "@/lib/formatters";
import { buildIndicatorDefs, categoryLabel, defaultSelectedIds } from "@/lib/indicators/catalog";
import { resolveSeries, selectPeriods } from "@/lib/indicators/series";
import type {
  AxisSide,
  ChartType,
  Frequency,
  IndicatorSelection,
  ResolvedSeries,
} from "@/lib/indicators/types";
import { useIndicatorConfig } from "@/lib/indicators/useIndicatorConfig";

const MAX_SELECTED = 6;
const DEFAULT_RECENT_YEARS = 5;
type YearPeriodPreset = "last5" | "last10" | "all";

const YEAR_PERIOD_OPTIONS: Array<{ value: YearPeriodPreset; label: string }> = [
  { value: "last5", label: "Last 5" },
  { value: "last10", label: "Last 10" },
  { value: "all", label: "All" },
];

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
      <EntityHeader cdCvm={cdCvm} activeTab="overview" />
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
  const companyQuery = useQuery<CompanyInfoResult>({
    queryKey: ["company-info", cdCvm],
    queryFn: () => fetchCompanyInfo(cdCvm),
    enabled: bridgeReady,
  });

  const yearsQuery = useQuery<CompanyYearsResultUI>({
    queryKey: ["company-years", cdCvm],
    queryFn: () => fetchCompanyYears(cdCvm),
    enabled: bridgeReady,
  });

  const allYears = useMemo(
    () => (yearsQuery.data?.mode === "desktop" ? yearsQuery.data.years : []),
    [yearsQuery.data],
  );

  // Default: last DEFAULT_RECENT_YEARS years, re-computed when years load.
  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  const sortedYears = useMemo(() => [...allYears].sort((a, b) => a - b), [allYears]);

  useEffect(() => {
    if (selectedYears.length === 0 && sortedYears.length > 0) {
      const desc = [...sortedYears].sort((a, b) => b - a);
      setSelectedYears(desc.slice(0, DEFAULT_RECENT_YEARS).sort((a, b) => a - b));
    }
  }, [sortedYears, selectedYears.length]);

  const kpiQuery = useQuery<CompanyKpisResult>({
    queryKey: ["company-kpis", cdCvm, selectedYears.join(",")],
    queryFn: () => fetchCompanyKpis(cdCvm, selectedYears),
    enabled: bridgeReady && selectedYears.length > 0,
  });

  const info =
    companyQuery.data?.mode === "desktop" ? companyQuery.data.info : null;
  const bundle = kpiQuery.data?.mode === "desktop" ? kpiQuery.data.bundle : null;

  return (
    <div className="space-y-4">
      <CompanyCommandBar
        cdCvm={cdCvm}
        bridgeReady={bridgeReady}
        latestPeriod={info?.latest_financial_period_display ?? null}
        yearsAvailable={info?.readable_years_count ?? null}
        lastModelUpdatedAt={info?.read_model_updated_at ?? null}
      />

      {/* Two-column analytical workspace */}
      <AnalyticalWorkspace
        cdCvm={cdCvm}
        bridgeReady={bridgeReady}
        bundle={bundle}
        yearsQuery={yearsQuery}
        kpiQuery={kpiQuery}
        sortedYears={sortedYears}
        selectedYears={selectedYears}
        onSelectedYearsChange={setSelectedYears}
      />
    </div>
  );
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
  onSelectedYearsChange,
}: {
  cdCvm: number;
  bridgeReady: boolean;
  bundle: KPIBundle | null;
  yearsQuery: UseQueryResult<CompanyYearsResultUI>;
  kpiQuery: UseQueryResult<CompanyKpisResult>;
  sortedYears: number[];
  selectedYears: number[];
  onSelectedYearsChange: (years: number[]) => void;
}) {
  return (
    <div
      style={{
        display: "grid",
        // Two equal columns on wide viewports; collapses via responsive class below.
        gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
        gap: "var(--spacing-4, 16px)",
        alignItems: "start",
      }}
      className="workspace-grid"
    >
      {/* Left: Historical market data */}
      <div className="min-w-0">
        <MarketHistoryPanel cdCvm={cdCvm} bridgeReady={bridgeReady} compact />
      </div>

      {/* Right: Financial indicator chart */}
      <div className="min-w-0">
        <CompactIndicatorPanel
          bundle={bundle}
          yearsQuery={yearsQuery}
          kpiQuery={kpiQuery}
          sortedYears={sortedYears}
          selectedYears={selectedYears}
          onSelectedYearsChange={onSelectedYearsChange}
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
  onSelectedYearsChange: (years: number[]) => void;
  bridgeReady: boolean;
}

function CompactIndicatorPanel({
  bundle,
  yearsQuery,
  kpiQuery,
  sortedYears,
  selectedYears,
  onSelectedYearsChange,
  bridgeReady,
}: CompactIndicatorPanelProps) {
  // Independent indicator config (persisted to localStorage, shared with any
  // future Indicators tab usage).
  const { config, setFrequency, setSelected, setChart } = useIndicatorConfig();
  const { frequency, chart } = config;

  if (!bridgeReady || yearsQuery.isLoading) {
    return (
      <Panel title="Financial indicators" subtitle="Loading…">
        <StateBanner variant="loading" title="Loading years…" />
      </Panel>
    );
  }

  if (yearsQuery.isError) {
    return (
      <Panel title="Financial indicators" subtitle="Year data unavailable">
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
      <Panel title="Financial indicators" subtitle="">
        <StateBanner variant="browser-only" message={yearsQuery.data.reason} />
      </Panel>
    );
  }

  if (sortedYears.length === 0) {
    return (
      <Panel title="Financial indicators" subtitle="No annual data">
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
      <Panel title="Financial indicators" subtitle="Loading…">
        <StateBanner variant="loading" title="Loading indicators…" />
      </Panel>
    );
  }

  if (kpiQuery.isError) {
    return (
      <Panel title="Financial indicators" subtitle="Indicator data unavailable">
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
      <Panel title="Financial indicators" subtitle="">
        <StateBanner variant="browser-only" message={kpiQuery.data.reason} />
      </Panel>
    );
  }

  if (!bundle) {
    return (
      <Panel title="Financial indicators" subtitle="No data">
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
      sortedYears={sortedYears}
      selectedYears={selectedYears}
      onSelectedYearsChange={onSelectedYearsChange}
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
  sortedYears,
  selectedYears,
  onSelectedYearsChange,
  frequency,
  setFrequency,
  chart,
  setChart,
  config,
  setSelected,
}: {
  bundle: KPIBundle;
  sortedYears: number[];
  selectedYears: number[];
  onSelectedYearsChange: (years: number[]) => void;
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

  const selectionById = useMemo(
    () => new Map(config.selected.map((s) => [s.id, s] as const)),
    [config.selected],
  );

  const plottable = useMemo(
    () => config.selected.filter((s) => defsById.get(s.id)?.available),
    [config.selected, defsById],
  );
  const plottableIds = useMemo(() => plottable.map((s) => s.id), [plottable]);

  const series = useMemo(
    () => resolveSeries(activeTable, periods, plottable, chart.type, chart.indexMode),
    [activeTable, periods, plottable, chart.type, chart.indexMode],
  );
  const latestMoves = useMemo(
    () => buildLatestMoves(series, periods, chart.indexMode),
    [series, periods, chart.indexMode],
  );

  const showAxisControls = useMemo(
    () => new Set(series.map((s) => s.unit)).size > 1,
    [series],
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

  function setAxis(id: string, axis: "auto" | AxisSide) {
    setSelected(config.selected.map((s) => (s.id === id ? { ...s, axis } : s)));
  }

  function setType(id: string, type: "auto" | ChartType) {
    setSelected(config.selected.map((s) => (s.id === id ? { ...s, type } : s)));
  }

  function yearsForPreset(preset: YearPeriodPreset) {
    const desc = [...sortedYears].sort((a, b) => b - a);
    if (preset === "all") return [...sortedYears];
    const count = preset === "last10" ? 10 : 5;
    return desc.slice(0, count).sort((a, b) => a - b);
  }

  function currentYearPreset(): YearPeriodPreset {
    for (const option of YEAR_PERIOD_OPTIONS) {
      const target = yearsForPreset(option.value);
      if (target.length === selectedYears.length && target.every((year, index) => year === selectedYears[index])) {
        return option.value;
      }
    }
    return "last5";
  }

  function setYearPreset(preset: string) {
    onSelectedYearsChange(yearsForPreset(preset as YearPeriodPreset));
  }

  const methodology =
    frequency === "annual"
      ? "Annual KPIs at fiscal-year close."
      : "Quarterly — flow metrics LTM (trailing 4Q); balance-sheet at quarter-end.";

  return (
    <div className="space-y-3">
      <Panel
        title="Financial indicators"
        subtitle={methodology}
        actions={
          <span
            className="font-mono"
            style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}
          >
            {series.length}/{config.selected.length} plotted
          </span>
        }
      >
        <div className="space-y-3">
          {/* Indicator controls: frequency + picker + chart type */}
          <IndicatorControls
            periodValue={currentYearPreset()}
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
          />

          <IndicatorMetadataRow
            selectedYears={selectedYears}
            frequency={frequency}
            plottedCount={series.length}
            selectedCount={config.selected.length}
          />

          <LatestMovesSummary moves={latestMoves} />

          {/* Chart area with state machine */}
          <ChartArea
            noIndicatorsAtAll={noIndicatorsAtAll}
            frequency={frequency}
            quarterlyAvailable={quarterlyAvailable}
            periodsCount={periods.length}
            selectedCount={config.selected.length}
            plottedCount={series.length}
          >
            <IndicatorChart series={series} periods={periods} config={chart} />
          </ChartArea>

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

          {/* Legend */}
          {chart.legend && series.length > 0 ? (
            <IndicatorLegend
              series={series}
              selectionById={selectionById}
              indexMode={chart.indexMode}
              showAxisControls={showAxisControls}
              onSetAxis={setAxis}
              onSetType={setType}
              onRemove={(id) => toggleIndicator(id)}
            />
          ) : null}
        </div>
      </Panel>

      {/* Collapsed disclosure: underlying indicator data table */}
      {series.length > 0 && periods.length > 0 ? (
        <details
          style={{
            background: "var(--color-surface-2)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-md)",
            overflow: "hidden",
          }}
        >
          <summary
            style={{
              color: "var(--color-text-tertiary)",
              cursor: "pointer",
              fontSize: "var(--text-xs)",
              fontWeight: 500,
              letterSpacing: "0.03em",
              listStyle: "none",
              padding: "8px 14px",
              userSelect: "none",
            }}
            className="focus-visible:outline focus-visible:outline-1"
          >
            <span aria-hidden="true" style={{ marginRight: 6 }}>▸</span>
            View underlying data
            <span style={{ color: "var(--color-text-muted)", marginLeft: 6 }}>
              {series.length} indicator{series.length !== 1 ? "s" : ""} · {periods.length} period{periods.length !== 1 ? "s" : ""}
            </span>
          </summary>
          <div style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
            <IndicatorMethodAudit
              table={activeTable}
              selectedIds={plottableIds}
              frequency={frequency}
              indexMode={chart.indexMode}
            />
            <IndicatorTable table={activeTable} periods={periods} selectedIds={plottableIds} />
          </div>
        </details>
      ) : null}
    </div>
  );
}

interface IndicatorAuditRow {
  id: string;
  label: string;
  category: string;
  unit: string;
  method: string;
  basis: string;
  formula: string;
}

function IndicatorMethodAudit({
  table,
  selectedIds,
  frequency,
  indexMode,
}: {
  table: TabularData;
  selectedIds: string[];
  frequency: Frequency;
  indexMode: boolean;
}) {
  const rows = useMemo(
    () => buildIndicatorAuditRows(table, selectedIds, frequency, indexMode),
    [table, selectedIds, frequency, indexMode],
  );
  if (rows.length === 0) return null;
  return (
    <section
      aria-label="Indicator source and method"
      style={{
        borderBottom: "1px solid var(--color-border-subtle)",
        padding: "10px 14px 12px",
      }}
    >
      <div
        className="mb-2 flex flex-wrap items-baseline justify-between gap-2"
      >
        <h3
          style={{
            color: "var(--color-text-primary)",
            fontSize: "var(--text-sm)",
            fontWeight: 650,
            margin: 0,
          }}
        >
          Source and method
        </h3>
        <p
          style={{
            color: "var(--color-text-tertiary)",
            fontSize: "var(--text-2xs)",
            margin: 0,
          }}
        >
          Local CVM statements · KPI engine · selected indicators
        </p>
      </div>
      <div className="grid gap-2">
        {rows.map((row) => (
          <div
            key={row.id}
            className="grid gap-2 lg:grid-cols-[minmax(10rem,1.1fr)_minmax(12rem,1.8fr)]"
            style={{
              borderTop: "1px solid var(--color-border-subtle)",
              paddingTop: 8,
            }}
          >
            <div className="min-w-0">
              <p
                className="truncate"
                style={{
                  color: "var(--color-text-primary)",
                  fontSize: "var(--text-xs)",
                  fontWeight: 650,
                  margin: 0,
                }}
                title={row.label}
              >
                {row.label}
              </p>
              <p
                className="truncate font-mono"
                style={{
                  color: "var(--color-text-tertiary)",
                  fontSize: "var(--text-2xs)",
                  margin: "2px 0 0",
                }}
                title={`${row.id} · ${row.category} · ${row.unit}`}
              >
                {row.id} · {row.category} · {row.unit}
              </p>
            </div>
            <div className="grid min-w-0 gap-1 sm:grid-cols-[minmax(8rem,0.7fr)_minmax(10rem,1fr)_minmax(12rem,1.3fr)]">
              <AuditMeta label="Method" value={row.method} />
              <AuditMeta label="Basis" value={row.basis} />
              <AuditMeta label="Formula" value={row.formula} mono />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AuditMeta({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <p
        style={{
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-2xs)",
          letterSpacing: "0.04em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        {label}
      </p>
      <p
        className={mono ? "truncate font-mono" : "truncate"}
        style={{
          color: "var(--color-text-secondary)",
          fontSize: "var(--text-xs)",
          margin: "1px 0 0",
        }}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}

function buildIndicatorAuditRows(
  table: TabularData,
  selectedIds: string[],
  frequency: Frequency,
  indexMode: boolean,
): IndicatorAuditRow[] {
  const order = new Map(selectedIds.map((id, index) => [id, index] as const));
  return table.rows
    .filter((row) => order.has(rowId(row)))
    .sort((a, b) => (order.get(rowId(a)) ?? 0) - (order.get(rowId(b)) ?? 0))
    .map((row) => {
      const id = rowId(row);
      const rawFormula = String(row.FORMULA ?? "").trim();
      const unit = indexMode ? "Index (100)" : formatUnit(row.FORMAT_TYPE);
      const basis =
        frequency === "annual"
          ? "Annual fiscal close"
          : "Quarterly view; LTM for flow metrics";
      return {
        id,
        label: String(row.KPI_NOME ?? id),
        category: categoryLabel(String(row.CATEGORIA ?? "—")),
        unit,
        method: "Calculated KPI",
        basis,
        formula: rawFormula || "Formula metadata unavailable",
      };
    });
}

function rowId(row: TabularRow): string {
  return String(row.KPI_ID ?? "").trim();
}

interface LatestMove {
  id: string;
  label: string;
  color: string;
  latestPeriod: string;
  latestValue: string;
  changeLabel: string;
}

function LatestMovesSummary({ moves }: { moves: LatestMove[] }) {
  if (moves.length === 0) return null;
  return (
    <div
      aria-label="Latest indicator moves"
      className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4"
      style={{
        borderTop: "1px solid var(--color-border-subtle)",
        paddingTop: 10,
      }}
    >
      {moves.map((move) => (
        <div
          key={move.id}
          className="min-w-0"
          style={{
            borderLeft: `2px solid ${move.color}`,
            paddingLeft: 9,
          }}
        >
          <p
            className="truncate"
            style={{
              color: "var(--color-text-tertiary)",
              fontSize: "var(--text-2xs)",
              letterSpacing: "0.04em",
              margin: 0,
              textTransform: "uppercase",
            }}
            title={move.label}
          >
            {move.label}
          </p>
          <p
            className="truncate font-mono"
            style={{
              color: "var(--color-text-primary)",
              fontSize: "var(--text-sm)",
              fontWeight: 650,
              margin: "2px 0 0",
            }}
            title={`${move.latestValue} in ${move.latestPeriod}`}
          >
            {move.latestValue}
            <span
              style={{
                color: "var(--color-text-tertiary)",
                fontSize: "var(--text-2xs)",
                marginLeft: 6,
              }}
            >
              {move.latestPeriod}
            </span>
          </p>
          <p
            className="truncate font-mono"
            style={{
              color: "var(--color-text-secondary)",
              fontSize: "var(--text-2xs)",
              margin: "1px 0 0",
            }}
            title={move.changeLabel}
          >
            {move.changeLabel}
          </p>
        </div>
      ))}
    </div>
  );
}

function buildLatestMoves(
  series: ResolvedSeries[],
  periods: string[],
  indexMode: boolean,
): LatestMove[] {
  return series.map((item) => {
    const latestIndex = findPreviousFiniteIndex(item.points, item.points.length - 1);
    if (latestIndex === -1) return null;
    const previousIndex = findPreviousFiniteIndex(item.points, latestIndex - 1);
    const latestValue = item.points[latestIndex];
    if (latestValue === null) return null;
    const changeLabel =
      previousIndex === -1 || item.points[previousIndex] === null
        ? "No prior period"
        : `${formatSignedChange(latestValue - item.points[previousIndex], item.unit, indexMode)} vs ${periods[previousIndex]}`;
    return {
      id: item.id,
      label: item.label,
      color: item.color,
      latestPeriod: periods[latestIndex] ?? "Latest",
      latestValue: formatValue(latestValue, item.unit, indexMode),
      changeLabel,
    };
  }).filter((move): move is LatestMove => move !== null);
}

function findPreviousFiniteIndex(points: Array<number | null>, startIndex: number): number {
  for (let index = startIndex; index >= 0; index -= 1) {
    const value = points[index];
    if (typeof value === "number" && Number.isFinite(value)) return index;
  }
  return -1;
}

function formatSignedChange(value: number, unit: ResolvedSeries["unit"], indexMode: boolean): string {
  if (Math.abs(value) < 0.000001) return unit === "pct" && !indexMode ? "0.0 pp" : "0";
  const sign = value > 0 ? "+" : "";
  if (indexMode) return `${sign}${value.toFixed(1)}`;
  if (unit === "pct") return `${sign}${(value * 100).toFixed(1)} pp`;
  if (unit === "ratio") return `${sign}${value.toFixed(1)}x`;
  return `${sign}${formatValue(value, unit, false)}`;
}

function IndicatorMetadataRow({
  selectedYears,
  frequency,
  plottedCount,
  selectedCount,
}: {
  selectedYears: number[];
  frequency: Frequency;
  plottedCount: number;
  selectedCount: number;
}) {
  const first = selectedYears[0];
  const last = selectedYears[selectedYears.length - 1];
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
      <span className="flex items-baseline gap-1.5">
        <span
          className="font-mono"
          style={{ color: "var(--color-text-primary)", fontSize: "var(--text-sm)", fontWeight: 650 }}
        >
          {first && last ? `${first}-${last}` : "No period"}
        </span>
        <span style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}>period</span>
      </span>
      <span className="flex items-baseline gap-1.5">
        <span style={{ color: "var(--color-text-tertiary)" }}>·</span>
        <span
          className="font-mono"
          style={{ color: "var(--color-text-primary)", fontSize: "var(--text-sm)", fontWeight: 650 }}
        >
          {frequency === "annual" ? "Annual" : "Quarterly"}
        </span>
        <span style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}>frequency</span>
      </span>
      <span className="flex items-baseline gap-1.5">
        <span style={{ color: "var(--color-text-tertiary)" }}>·</span>
        <span
          className="font-mono"
          style={{ color: "var(--color-text-primary)", fontSize: "var(--text-sm)", fontWeight: 650 }}
        >
          {plottedCount}/{selectedCount}
        </span>
        <span style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}>plotted</span>
      </span>
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
