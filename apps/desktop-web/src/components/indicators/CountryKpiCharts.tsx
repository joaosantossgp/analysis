/**
 * CountryKpiCharts — two chart views for country-level energy KPIs.
 *
 * MatrixView: stacked horizontal bars per country — full electricity mix.
 * TrendView:  full IndicatorWorkspace-style experience — IndicatorControls
 *             (countries as indicators, chart type, options panel) +
 *             IndicatorChart + IndicatorLegend with per-series overrides.
 */
import { useMemo } from "react";

import { IndicatorChart } from "@/components/indicators/IndicatorChart";
import { IndicatorControls } from "@/components/indicators/IndicatorControls";
import { IndicatorLegend } from "@/components/indicators/IndicatorLegend";
import { StateBanner } from "@/components/feedback/StateBanner";
import type { CountryKPIValue } from "@/lib/bridge/types";
import type {
  AxisSide,
  ChartType,
  IndicatorDef,
  IndicatorSelection,
  ResolvedSeries,
} from "@/lib/indicators/types";
import { useCountryKpiConfig } from "@/lib/indicators/useCountryKpiConfig";

// ── Constants ─────────────────────────────────────────────────────────────────

const NS = "energy_utilities.country";

const MIX_SEGMENTS = [
  { kpi: `${NS}.elec_hydro_share`,   label: "Hydro",    color: "#3B82F6" },
  { kpi: `${NS}.elec_solar_share`,   label: "Solar",    color: "#FBBF24" },
  { kpi: `${NS}.elec_wind_share`,    label: "Wind",     color: "#34D399" },
  { kpi: `${NS}.elec_nuclear_share`, label: "Nuclear",  color: "#A78BFA" },
  { kpi: `${NS}.elec_gas_share`,     label: "Gas",      color: "#FB923C" },
  { kpi: `${NS}.elec_coal_share`,    label: "Coal",     color: "#A16207" },
] as const;

const REMAINDER_COLOR = "#6B7280";
const REMAINDER_LABEL = "Other";

export const TREND_KPIS = [
  { kpi: `${NS}.elec_renewables_share`,   label: "Renewable share (%)" },
  { kpi: `${NS}.elec_fossil_share`,       label: "Fossil share (%)" },
  { kpi: `${NS}.elec_hydro_share`,        label: "Hydro share (%)" },
  { kpi: `${NS}.elec_carbon_intensity`,   label: "Carbon intensity (gCO₂/kWh)" },
  { kpi: `${NS}.elec_demand_total`,       label: "Electricity demand (TWh)" },
  { kpi: `${NS}.elec_generation_total`,   label: "Electricity generation (TWh)" },
  { kpi: `${NS}.elec_demand_growth_yoy`,  label: "Demand growth YoY (%)" },
  { kpi: `${NS}.elec_net_imports_share`,  label: "Net imports share (%)" },
  { kpi: `${NS}.elec_low_carbon_share`,   label: "Low-carbon share (%)" },
  { kpi: `${NS}.elec_gas_share`,          label: "Gas share (%)" },
] as const;

export const COUNTRY_COLORS: Record<string, string> = {
  BRA: "#22D3EE",
  USA: "#818CF8",
  CHN: "#F87171",
  OWEU: "#34D399",
  CHL: "#FBBF24",
  ARG: "#FB923C",
};

/** v1 country universe — shared by the page and the Explorer detail chart. */
export const COUNTRY_ISO_CODES = ["BRA", "USA", "CHN", "OWEU", "CHL", "ARG"] as const;

export const COUNTRY_LABELS: Record<string, string> = {
  BRA: "Brazil",
  USA: "United States",
  CHN: "China",
  OWEU: "EU 27",
  CHL: "Chile",
  ARG: "Argentina",
};

const MAX_SELECTED = 6;

// Share KPIs whose raw values are 0–100 and need /100 for IndicatorChart pct format
const PCT_KPI_SUFFIXES = [
  "share", "growth_yoy", "net_imports_share",
];

export function isPctKpi(kpiId: string): boolean {
  return PCT_KPI_SUFFIXES.some(s => kpiId.endsWith(s));
}

// ── MatrixView ────────────────────────────────────────────────────────────────

interface MatrixViewProps {
  values: CountryKPIValue[];
  year: number;
  isoCodes: readonly string[];
}

export function MatrixView({ values, year, isoCodes }: MatrixViewProps) {
  const data = useMemo(
    () => buildMatrixData(values, year, isoCodes),
    [values, year, isoCodes],
  );

  if (data.length === 0) {
    return (
      <p className="text-zinc-500 text-sm text-center py-12">
        No electricity mix data for {year}. Try fetching data or selecting another year.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 px-1">
        {MIX_SEGMENTS.map(s => (
          <span key={s.kpi} className="flex items-center gap-1.5 text-xs text-zinc-300">
            <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
        <span className="flex items-center gap-1.5 text-xs text-zinc-300">
          <span className="w-3 h-3 rounded-sm flex-shrink-0" style={{ background: REMAINDER_COLOR }} />
          {REMAINDER_LABEL}
        </span>
      </div>

      <div className="space-y-3">
        {data.map(row => <MatrixRow key={row.isoCode} row={row} />)}
      </div>

      <div className="flex justify-between text-[10px] text-zinc-500 px-[72px]">
        {[0, 25, 50, 75, 100].map(v => <span key={v}>{v}%</span>)}
      </div>
    </div>
  );
}

interface MatrixRowData {
  isoCode: string;
  countryLabel: string;
  segments: Array<{ label: string; color: string; pct: number }>;
  total: number;
}

function buildMatrixData(
  values: CountryKPIValue[],
  year: number,
  isoCodes: readonly string[],
): MatrixRowData[] {
  return isoCodes.flatMap(iso => {
    const byKpi = new Map(
      values.filter(v => v.iso_code === iso && v.period === year).map(v => [v.kpi_id, v.value]),
    );
    if (byKpi.size === 0) return [];

    const segments: MatrixRowData["segments"] = [];
    let accounted = 0;
    for (const seg of MIX_SEGMENTS) {
      const pct = byKpi.get(seg.kpi) ?? null;
      if (pct !== null && pct > 0) {
        segments.push({ label: seg.label, color: seg.color, pct });
        accounted += pct;
      }
    }
    const rem = Math.max(0, 100 - accounted);
    if (rem > 1) segments.push({ label: REMAINDER_LABEL, color: REMAINDER_COLOR, pct: rem });
    if (segments.length === 0) return [];

    return [{
      isoCode: iso,
      countryLabel: COUNTRY_LABELS[iso] ?? iso,
      segments,
      total: accounted + (rem > 1 ? rem : 0),
    }];
  });
}

function MatrixRow({ row }: { row: MatrixRowData }) {
  const shortLabel = row.countryLabel.length > 10 ? row.isoCode : row.countryLabel;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-zinc-400 w-16 text-right flex-shrink-0 font-mono">
        {shortLabel}
      </span>
      <div className="flex-1 relative">
        <div className="flex h-7 rounded overflow-hidden">
          {row.segments.map((seg, i) => (
            <BarSegment key={i} seg={seg} total={row.total} />
          ))}
        </div>
        <div className="absolute inset-0 pointer-events-none">
          {[25, 50, 75].map(v => (
            <div key={v} className="absolute top-0 bottom-0 w-px bg-zinc-900/60" style={{ left: `${v}%` }} />
          ))}
        </div>
      </div>
    </div>
  );
}

function BarSegment({ seg, total }: { seg: MatrixRowData["segments"][number]; total: number }) {
  const pct = (seg.pct / total) * 100;
  if (pct < 0.5) return null;
  return (
    <div className="relative group" style={{ width: `${pct}%`, background: seg.color }}>
      {pct > 8 && (
        <span className="absolute inset-0 flex items-center justify-center text-[10px] font-medium text-zinc-900/80">
          {Math.round(seg.pct)}%
        </span>
      )}
      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:flex
                      bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200
                      whitespace-nowrap z-10 shadow-lg pointer-events-none">
        {seg.label}: {seg.pct.toFixed(1)}%
      </div>
    </div>
  );
}

// ── TrendView ─────────────────────────────────────────────────────────────────

interface TrendViewProps {
  values: CountryKPIValue[];
  kpiId: string;
  isoCodes: readonly string[];
}

export function TrendView({ values, kpiId, isoCodes }: TrendViewProps) {
  const { config, setSelected, setChart } = useCountryKpiConfig(isoCodes);
  const { selected, chart } = config;

  // Build IndicatorDef[] — countries as "indicators"
  const defs: IndicatorDef[] = useMemo(
    () => isoCodes.map(iso => ({
      id: iso,
      label: COUNTRY_LABELS[iso] ?? iso,
      category: "Countries",
      unit: isPctKpi(kpiId) ? ("pct" as const) : ("number" as const),
      isPlaceholder: false,
      available: values.some(v => v.iso_code === iso && v.kpi_id === kpiId && v.value !== null),
    })),
    [isoCodes, kpiId, values],
  );

  const selectionById = useMemo(
    () => new Map(selected.map(s => [s.id, s] as const)),
    [selected],
  );

  const plottable = useMemo(
    () => selected.filter(s => defs.find(d => d.id === s.id)?.available),
    [selected, defs],
  );

  const { series, periods } = useMemo(
    () => buildTrendSeries(values, kpiId, plottable, chart),
    [values, kpiId, plottable, chart],
  );

  function toggle(id: string) {
    const exists = selected.some(s => s.id === id);
    if (exists) {
      setSelected(selected.filter(s => s.id !== id));
    } else if (selected.length < MAX_SELECTED) {
      setSelected([...selected, { id, axis: "auto", type: "auto" }]);
    }
  }

  function setAxis(id: string, axis: "auto" | AxisSide) {
    setSelected(selected.map(s => s.id === id ? { ...s, axis } : s));
  }

  function setType(id: string, type: "auto" | ChartType) {
    setSelected(selected.map(s => s.id === id ? { ...s, type } : s));
  }

  const showAxisControls = useMemo(
    () => new Set(series.map(s => s.unit)).size > 1,
    [series],
  );

  const droppedCount = selected.filter(s => defs.find(d => d.id === s.id) && !defs.find(d => d.id === s.id)?.available).length;

  return (
    <div className="space-y-3">
      <IndicatorControls
        frequency="annual"
        quarterlyAvailable={false}
        onFrequencyChange={() => undefined}
        showFrequency={false}
        itemNoun="Countries"
        defs={defs}
        selectedIds={selected.map(s => s.id)}
        onToggleIndicator={toggle}
        maxSelected={MAX_SELECTED}
        chart={chart}
        onChartChange={setChart}
      />

      {droppedCount > 0 && (
        <p className="text-xs" style={{ color: "var(--color-state-warn)" }}>
          {droppedCount} selected {droppedCount > 1 ? "countries are" : "country is"} unavailable for this KPI and hidden.
        </p>
      )}

      {series.length === 0 || periods.length === 0 ? (
        <StateBanner
          variant="empty"
          title="Nothing to plot"
          message="Select at least one country using the Countries picker above."
        />
      ) : (
        <IndicatorChart series={series} periods={periods} config={chart} height={320} />
      )}

      {chart.legend && series.length > 0 && (
        <IndicatorLegend
          series={series}
          selectionById={selectionById}
          indexMode={chart.indexMode}
          showAxisControls={showAxisControls}
          onSetAxis={setAxis}
          onSetType={setType}
          onRemove={toggle}
        />
      )}
    </div>
  );
}

// ── Series builder ────────────────────────────────────────────────────────────

export function buildTrendSeries(
  values: CountryKPIValue[],
  kpiId: string,
  plottable: IndicatorSelection[],
  chart: { type: ChartType; indexMode: boolean },
): { series: ResolvedSeries[]; periods: string[] } {
  const asPct = isPctKpi(kpiId);

  // Collect all years that have data for this KPI
  const allYears = new Set<number>();
  for (const v of values) {
    if (v.kpi_id === kpiId && v.value !== null) allYears.add(v.period);
  }
  const sortedYears = [...allYears].sort((a, b) => a - b);
  if (sortedYears.length === 0) return { series: [], periods: [] };

  const periods = sortedYears.map(String);

  const series: ResolvedSeries[] = plottable.map(sel => {
    const iso = sel.id;
    const yearMap = new Map(
      values.filter(v => v.iso_code === iso && v.kpi_id === kpiId).map(v => [v.period, v.value]),
    );

    let points: Array<number | null> = sortedYears.map(y => yearMap.get(y) ?? null);

    // Scale % KPIs to [0,1] for IndicatorChart's pct formatter
    if (asPct) {
      points = points.map(v => (v !== null ? v / 100 : null));
    }

    // Index mode: rebase first finite value to 1.0 (→ displays as 100 in index)
    if (chart.indexMode) {
      const first = points.find((v): v is number => v !== null);
      if (first != null && first !== 0) {
        points = points.map(v => (v !== null ? v / Math.abs(first) : null));
      }
    }

    const finite = points.filter((v): v is number => v !== null);

    const resolvedType: ChartType =
      sel.type === "auto" ? chart.type : sel.type;

    const resolvedAxis: AxisSide =
      sel.axis === "auto" ? "left" : sel.axis;

    return {
      id: iso,
      label: COUNTRY_LABELS[iso] ?? iso,
      unit: chart.indexMode ? "number" : asPct ? "pct" : "number",
      color: COUNTRY_COLORS[iso] ?? "#94A3B8",
      type: resolvedType,
      axis: resolvedAxis,
      points,
      latest: finite.length > 0 ? finite[finite.length - 1] : null,
    };
  });

  return { series, periods };
}
