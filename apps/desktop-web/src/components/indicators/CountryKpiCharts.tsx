/**
 * CountryKpiCharts — two chart views for country-level energy KPIs.
 *
 * MatrixView: stacked horizontal bar per country showing full electricity mix.
 * TrendView:  line chart (reuses IndicatorChart) — one series per country,
 *             for a selected KPI over all available years.
 */
import { useMemo } from "react";

import { IndicatorChart } from "@/components/indicators/IndicatorChart";
import type { CountryKPIValue } from "@/lib/bridge/types";
import type { ResolvedSeries } from "@/lib/indicators/types";

// ── Constants ─────────────────────────────────────────────────────────────────

const NS = "energy_utilities.country";

// Electricity mix segments (order matters — stacked left→right)
const MIX_SEGMENTS = [
  { kpi: `${NS}.elec_hydro_share`,     label: "Hydro",          color: "#3B82F6" },
  { kpi: `${NS}.elec_solar_share`,     label: "Solar",          color: "#FBBF24" },
  { kpi: `${NS}.elec_wind_share`,      label: "Wind",           color: "#34D399" },
  { kpi: `${NS}.elec_nuclear_share`,   label: "Nuclear",        color: "#A78BFA" },
  { kpi: `${NS}.elec_gas_share`,       label: "Gas",            color: "#FB923C" },
  { kpi: `${NS}.elec_coal_share`,      label: "Coal",           color: "#A16207" },
] as const;

// Fallback for unlabelled remainder (≈ oil + other untracked)
const REMAINDER_COLOR = "#6B7280";
const REMAINDER_LABEL = "Other";

export const TREND_KPIS = [
  { kpi: `${NS}.elec_renewables_share`,    label: "Renewable share (%)" },
  { kpi: `${NS}.elec_fossil_share`,        label: "Fossil share (%)" },
  { kpi: `${NS}.elec_hydro_share`,         label: "Hydro share (%)" },
  { kpi: `${NS}.elec_carbon_intensity`,    label: "Carbon intensity (gCO₂/kWh)" },
  { kpi: `${NS}.elec_demand_total`,        label: "Electricity demand (TWh)" },
  { kpi: `${NS}.elec_generation_total`,    label: "Electricity generation (TWh)" },
  { kpi: `${NS}.elec_demand_growth_yoy`,   label: "Demand growth YoY (%)" },
  { kpi: `${NS}.elec_net_imports_share`,   label: "Net imports share (%)" },
  { kpi: `${NS}.elec_low_carbon_share`,    label: "Low-carbon share (%)" },
  { kpi: `${NS}.elec_gas_share`,           label: "Gas share (%)" },
] as const;

export const COUNTRY_COLORS: Record<string, string> = {
  BRA: "#22D3EE",
  USA: "#818CF8",
  CHN: "#F87171",
  OWEU: "#34D399",
  CHL: "#FBBF24",
  ARG: "#FB923C",
};

const COUNTRY_LABELS: Record<string, string> = {
  BRA: "Brazil",
  USA: "United States",
  CHN: "China",
  OWEU: "EU 27",
  CHL: "Chile",
  ARG: "Argentina",
};

// ── MatrixView ────────────────────────────────────────────────────────────────

interface MatrixViewProps {
  values: CountryKPIValue[];
  year: number;
  isoCodes: string[];
}

export function MatrixView({ values, year, isoCodes }: MatrixViewProps) {
  const data = useMemo(() => buildMatrixData(values, year, isoCodes), [values, year, isoCodes]);

  if (data.length === 0) {
    return (
      <p className="text-zinc-500 text-sm text-center py-12">
        No electricity mix data for {year}. Try fetching data or selecting another year.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {/* Legend */}
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

      {/* Bars */}
      <div className="space-y-3">
        {data.map(row => (
          <MatrixRow key={row.isoCode} row={row} />
        ))}
      </div>

      {/* X-axis ticks */}
      <div className="flex justify-between text-[10px] text-zinc-500 px-[72px]">
        {[0, 25, 50, 75, 100].map(v => (
          <span key={v}>{v}%</span>
        ))}
      </div>
    </div>
  );
}

interface MatrixRow {
  isoCode: string;
  countryLabel: string;
  segments: Array<{ label: string; color: string; pct: number }>;
  total: number;
}

function buildMatrixData(
  values: CountryKPIValue[],
  year: number,
  isoCodes: string[],
): MatrixRow[] {
  const rows: MatrixRow[] = [];
  for (const iso of isoCodes) {
    const yearValues = values.filter(v => v.iso_code === iso && v.period === year);
    if (yearValues.length === 0) continue;

    const byKpi = new Map(yearValues.map(v => [v.kpi_id, v.value]));

    const segments: MatrixRow["segments"] = [];
    let accounted = 0;

    for (const seg of MIX_SEGMENTS) {
      const pct = byKpi.get(seg.kpi) ?? null;
      if (pct !== null && pct > 0) {
        segments.push({ label: seg.label, color: seg.color, pct });
        accounted += pct;
      }
    }

    const remainder = Math.max(0, 100 - accounted);
    if (remainder > 1) {
      segments.push({ label: REMAINDER_LABEL, color: REMAINDER_COLOR, pct: remainder });
    }

    if (segments.length > 0) {
      rows.push({
        isoCode: iso,
        countryLabel: COUNTRY_LABELS[iso] ?? iso,
        segments,
        total: accounted + (remainder > 1 ? remainder : 0),
      });
    }
  }
  return rows;
}

function MatrixRow({ row }: { row: MatrixRow }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-zinc-400 w-16 text-right flex-shrink-0 font-mono">
        {row.countryLabel.length > 10 ? row.isoCode : row.countryLabel}
      </span>
      <div className="flex-1 relative">
        <div className="flex h-7 rounded overflow-hidden">
          {row.segments.map((seg, i) => (
            <BarSegment key={i} seg={seg} total={row.total} />
          ))}
        </div>
        {/* Grid lines */}
        <div className="absolute inset-0 pointer-events-none">
          {[25, 50, 75].map(v => (
            <div
              key={v}
              className="absolute top-0 bottom-0 w-px bg-zinc-900/60"
              style={{ left: `${v}%` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function BarSegment({
  seg,
  total,
}: {
  seg: MatrixRow["segments"][number];
  total: number;
}) {
  const pct = (seg.pct / total) * 100;
  if (pct < 0.5) return null;
  return (
    <div
      className="relative group"
      style={{ width: `${pct}%`, background: seg.color }}
    >
      {pct > 8 && (
        <span className="absolute inset-0 flex items-center justify-center text-[10px] font-medium text-zinc-900/80">
          {Math.round(seg.pct)}%
        </span>
      )}
      {/* Tooltip */}
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
  kpiLabel: string;
  isoCodes: string[];
}

export function TrendView({ values, kpiId, isoCodes }: TrendViewProps) {
  const { series, periods } = useMemo(
    () => buildTrendSeries(values, kpiId, isoCodes),
    [values, kpiId, isoCodes],
  );

  if (series.length === 0 || periods.length === 0) {
    return (
      <p className="text-zinc-500 text-sm text-center py-12">
        No trend data for this KPI. Try fetching more years or selecting another indicator.
      </p>
    );
  }

  const config = {
    type: "line" as const,
    smooth: true,
    markers: false,
    legend: true,
    grid: true,
    dataLabels: false,
    indexMode: false,
  };

  return (
    <div className="space-y-2">
      <IndicatorChart series={series} periods={periods} config={config} height={320} />
    </div>
  );
}

function buildTrendSeries(
  values: CountryKPIValue[],
  kpiId: string,
  isoCodes: string[],
): { series: ResolvedSeries[]; periods: string[] } {
  const byIso = new Map<string, Map<number, number | null>>();
  const allYears = new Set<number>();

  for (const v of values) {
    if (v.kpi_id !== kpiId) continue;
    if (!byIso.has(v.iso_code)) byIso.set(v.iso_code, new Map());
    byIso.get(v.iso_code)!.set(v.period, v.value);
    allYears.add(v.period);
  }

  const sortedYears = [...allYears].sort((a, b) => a - b);
  if (sortedYears.length === 0) return { series: [], periods: [] };

  const periods = sortedYears.map(String);

  const series: ResolvedSeries[] = isoCodes
    .filter(iso => byIso.has(iso))
    .map(iso => {
      const yearMap = byIso.get(iso)!;
      const points = sortedYears.map(y => yearMap.get(y) ?? null);
      const finite = points.filter((v): v is number => v !== null);

      // Detect unit from values: if all ≤ 100 and many are between 0-100, treat as pct
      const isPct = finite.length > 0 && Math.max(...finite) <= 101;

      return {
        id: iso,
        label: COUNTRY_LABELS[iso] ?? iso,
        unit: isPct ? ("pct" as const) : ("number" as const),
        color: COUNTRY_COLORS[iso] ?? "#94A3B8",
        type: "line" as const,
        axis: "left" as const,
        points: isPct ? points.map(v => (v !== null ? v / 100 : null)) : points,
        latest: finite.length > 0 ? finite[finite.length - 1] : null,
      };
    });

  return { series, periods };
}
