/**
 * CountryKpisPage — top-level macro KPI module at /country-kpis.
 *
 * Shows country-level energy KPIs for all v1 peer countries.
 * Structured like SectorsPage / CompaniesPage: full module page with
 * header, filters, grid, and proper empty/loading/error states.
 *
 * Future: multi-sector filter once other sectors are registered.
 */
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchCountryKPISeries,
  fetchEnergyKPIHealth,
  fetchKPICatalog,
  triggerEnergyKPIRefresh,
} from "@/lib/api/energyKpis";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { CountryKPIValue, KPICatalogEntry } from "@/lib/bridge/types";
import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { NumberCell } from "@/components/data/NumberCell";

const V1_ISO_CODES = ["BRA", "USA", "CHN", "OWEU", "CHL", "ARG"] as const;

const COUNTRY_LABELS: Record<string, string> = {
  BRA: "Brazil",
  USA: "United States",
  CHN: "China",
  OWEU: "EU 27",
  CHL: "Chile",
  ARG: "Argentina",
};

const CATEGORY_LABELS: Record<string, string> = {
  renewables: "Renewables",
  fossil_dependence: "Fossil Dependence",
  hydro: "Hydro",
  thermal: "Thermal",
  nuclear: "Nuclear",
  generation: "Generation",
  demand: "Demand",
  carbon_intensity: "Carbon Intensity",
  emissions: "Emissions",
  trade: "Trade",
  energy_mix: "Primary Energy",
  transition: "Energy Transition",
  capacity: "Capacity",
};

const CATEGORY_ORDER = [
  "renewables", "fossil_dependence", "hydro", "thermal", "carbon_intensity",
  "demand", "generation", "emissions", "trade", "energy_mix", "transition",
];

export function CountryKpisPage() {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [year, setYear] = useState(() => new Date().getFullYear() - 1);
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => { if (!cancelled) setBridgeReady(true); });
    return () => { cancelled = true; };
  }, []);

  // Stop polling on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const healthQuery = useQuery({
    queryKey: ["energy-kpi-health"],
    queryFn: () => fetchEnergyKPIHealth(),
    enabled: bridgeReady,
    staleTime: 10_000,
    refetchInterval: isRefreshing ? 2_000 : false,
  });

  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.health : null;

  // Detect refresh completion by watching health
  useEffect(() => {
    if (!isRefreshing) return;
    const refreshRunning = (health as any)?.refresh_running;
    const refreshError = (health as any)?.refresh_error;
    if (refreshRunning === false && health?.last_refresh_status != null) {
      setIsRefreshing(false);
      if (health.last_refresh_status === "success") {
        setRefreshMsg(`Updated — ${health.rows_ingested} rows ingested`);
        void qc.invalidateQueries({ queryKey: ["country-kpi-series"] });
        void qc.invalidateQueries({ queryKey: ["energy-kpi-catalog"] });
      } else {
        setRefreshMsg(`Refresh failed: ${refreshError ?? health.last_refresh_status}`);
      }
      setTimeout(() => setRefreshMsg(null), 8_000);
    }
  }, [health, isRefreshing, qc]);

  const catalogQuery = useQuery({
    queryKey: ["energy-kpi-catalog"],
    queryFn: () => fetchKPICatalog(),
    enabled: bridgeReady,
    staleTime: 5 * 60_000,
  });

  const seriesQuery = useQuery({
    queryKey: ["country-kpi-series", year],
    queryFn: () => fetchCountryKPISeries({ iso_codes: [...V1_ISO_CODES], years: [year] }),
    enabled: bridgeReady,
    staleTime: 60_000,
  });

  const catalog = catalogQuery.data?.mode === "desktop" ? catalogQuery.data.entries : [];
  const values = seriesQuery.data?.mode === "desktop" ? seriesQuery.data.values : [];
  const hasData = values.length > 0;

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setRefreshMsg("Downloading OWID energy dataset…");
    try {
      await triggerEnergyKPIRefresh();
    } catch (e) {
      setIsRefreshing(false);
      setRefreshMsg(`Error: ${String(e)}`);
      setTimeout(() => setRefreshMsg(null), 6_000);
    }
  };

  const isLoading = !bridgeReady || catalogQuery.isLoading || seriesQuery.isLoading;
  const isError = catalogQuery.isError || seriesQuery.isError;

  const years = Array.from({ length: 12 }, (_, i) => new Date().getFullYear() - 1 - i);
  const categories = ["all", ...CATEGORY_ORDER.filter(c =>
    catalog.some(e => e.macro_category === c && e.dashboard_priority !== "not_in_v1_dashboard")
  )];

  const breadcrumbs = [{ label: "Country KPIs" }];

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg space-y-5">
      <PageHeader
        title="Country KPIs"
        subtitle="Energy Utilities · electricity matrix, carbon intensity, demand, trade"
        breadcrumbs={breadcrumbs}
        actions={
          <RefreshButton
            isRefreshing={isRefreshing}
            onRefresh={handleRefresh}
            hasData={hasData}
          />
        }
      />

      {/* Status banners */}
      {health?.is_stale && !isRefreshing && (
        <StateBanner
          variant="error"
          message={`Data stale — last fetched ${health.owid_fetched_at?.slice(0, 10) ?? "unknown"}. Click "Update" to refresh.`}
        />
      )}
      {refreshMsg && (
        <div className={`text-sm px-3 py-2 rounded border ${
          refreshMsg.startsWith("Error") || refreshMsg.startsWith("Refresh failed")
            ? "border-red-800 bg-red-950/40 text-red-300"
            : "border-zinc-700 bg-zinc-800/60 text-zinc-300"
        }`}>
          {isRefreshing && (
            <span className="inline-block w-3 h-3 mr-2 rounded-full border-2 border-zinc-400 border-t-transparent animate-spin" />
          )}
          {refreshMsg}
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-xs text-zinc-400">Year</label>
          <select
            value={year}
            onChange={e => setYear(Number(e.target.value))}
            className="text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200"
          >
            {years.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-zinc-400">Category</label>
          <select
            value={categoryFilter}
            onChange={e => setCategoryFilter(e.target.value)}
            className="text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200"
          >
            {categories.map(c => (
              <option key={c} value={c}>
                {c === "all" ? "All categories" : (CATEGORY_LABELS[c] ?? c)}
              </option>
            ))}
          </select>
        </div>

        <p className="ml-auto text-xs text-zinc-500">
          Source: OWID energy dataset (CC-BY) · via Ember Yearly Electricity Data
          {health?.owid_fetched_at && ` · fetched ${health.owid_fetched_at.slice(0, 10)}`}
        </p>
      </div>

      {/* Body */}
      {isLoading ? (
        <StateBanner variant="loading" />
      ) : isError ? (
        <StateBanner variant="error" message="Failed to load KPI data." />
      ) : !hasData ? (
        <EmptyState onRefresh={handleRefresh} isRefreshing={isRefreshing} />
      ) : (
        <KpiGrid
          catalog={catalog}
          values={values}
          isoCodes={[...V1_ISO_CODES]}
          categoryFilter={categoryFilter}
        />
      )}
    </section>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RefreshButton({
  isRefreshing,
  onRefresh,
  hasData,
}: {
  isRefreshing: boolean;
  onRefresh: () => void;
  hasData: boolean;
}) {
  return (
    <button
      onClick={onRefresh}
      disabled={isRefreshing}
      className="px-3 py-1.5 text-sm rounded border border-zinc-600 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-50 transition-colors flex items-center gap-2"
    >
      {isRefreshing && (
        <span className="w-3 h-3 rounded-full border-2 border-zinc-400 border-t-transparent animate-spin" />
      )}
      {isRefreshing ? "Updating…" : hasData ? "Update" : "Fetch data"}
    </button>
  );
}

function EmptyState({ onRefresh, isRefreshing }: { onRefresh: () => void; isRefreshing: boolean }) {
  return (
    <div className="text-center py-16 space-y-4">
      <p className="text-zinc-400">No country KPI data yet.</p>
      <p className="text-zinc-500 text-sm max-w-md mx-auto">
        Click below to download the OWID energy dataset (~7 MB).
        This is a one-time fetch; future updates are incremental.
      </p>
      <button
        onClick={onRefresh}
        disabled={isRefreshing}
        className="px-5 py-2 text-sm rounded border border-zinc-500 hover:border-zinc-300 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-50 transition-colors flex items-center gap-2 mx-auto"
      >
        {isRefreshing && (
          <span className="w-3 h-3 rounded-full border-2 border-zinc-400 border-t-transparent animate-spin" />
        )}
        {isRefreshing ? "Downloading…" : "Fetch energy data"}
      </button>
    </div>
  );
}

function KpiGrid({
  catalog,
  values,
  isoCodes,
  categoryFilter,
}: {
  catalog: KPICatalogEntry[];
  values: CountryKPIValue[];
  isoCodes: string[];
  categoryFilter: string;
}) {
  const valueIndex = new Map<string, CountryKPIValue>();
  for (const v of values) valueIndex.set(`${v.kpi_id}|${v.iso_code}`, v);

  const grouped = new Map<string, KPICatalogEntry[]>();
  for (const e of catalog) {
    if (e.dashboard_priority === "not_in_v1_dashboard") continue;
    if (categoryFilter !== "all" && e.macro_category !== categoryFilter) continue;
    const g = grouped.get(e.macro_category) ?? [];
    g.push(e);
    grouped.set(e.macro_category, g);
  }

  const orderedCategories = [
    ...CATEGORY_ORDER.filter(c => grouped.has(c)),
    ...[...grouped.keys()].filter(c => !CATEGORY_ORDER.includes(c)),
  ];

  if (orderedCategories.length === 0) {
    return <p className="text-zinc-500 text-sm py-8 text-center">No KPIs match the selected filter.</p>;
  }

  return (
    <div className="space-y-6">
      {orderedCategories.map(cat => (
        <CategoryBlock
          key={cat}
          category={cat}
          entries={grouped.get(cat)!}
          isoCodes={isoCodes}
          valueIndex={valueIndex}
        />
      ))}
    </div>
  );
}

function CategoryBlock({
  category,
  entries,
  isoCodes,
  valueIndex,
}: {
  category: string;
  entries: KPICatalogEntry[];
  isoCodes: string[];
  valueIndex: Map<string, CountryKPIValue>;
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-400 mb-2 px-1">
        {CATEGORY_LABELS[category] ?? category}
      </h3>
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/70">
              <th className="text-left py-2 px-3 text-xs font-medium text-zinc-400 w-52">KPI</th>
              {isoCodes.map(iso => (
                <th key={iso} className="text-right py-2 px-3 text-xs font-medium text-zinc-400 min-w-[90px]">
                  {COUNTRY_LABELS[iso] ?? iso}
                </th>
              ))}
              <th className="py-2 px-3 text-xs font-medium text-zinc-400 text-left w-12">Unit</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, i) => (
              <KpiRow
                key={entry.kpi_id}
                entry={entry}
                isoCodes={isoCodes}
                valueIndex={valueIndex}
                isLast={i === entries.length - 1}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function KpiRow({
  entry,
  isoCodes,
  valueIndex,
  isLast,
}: {
  entry: KPICatalogEntry;
  isoCodes: string[];
  valueIndex: Map<string, CountryKPIValue>;
  isLast: boolean;
}) {
  return (
    <tr className={`${isLast ? "" : "border-b border-zinc-800/50"} hover:bg-zinc-800/25 transition-colors`}>
      <td className="py-2 px-3 text-zinc-300 text-xs">
        <span title={entry.description}>{entry.display_name}</span>
        {entry.v1_status === "v1_required" && (
          <span className="ml-1.5 text-[10px] text-zinc-500 select-none" title="Required KPI">●</span>
        )}
      </td>
      {isoCodes.map(iso => {
        const v = valueIndex.get(`${entry.kpi_id}|${iso}`);
        return (
          <td key={iso} className="py-2 px-3 text-right">
            <ValueCell value={v} higherIsBetter={entry.higher_is_better} />
          </td>
        );
      })}
      <td className="py-2 px-3 text-xs text-zinc-500">{entry.unit}</td>
    </tr>
  );
}

function ValueCell({
  value,
  higherIsBetter,
}: {
  value: CountryKPIValue | undefined;
  higherIsBetter: boolean | null;
}) {
  if (!value || value.value === null) {
    return <span className="text-zinc-600 text-xs">—</span>;
  }

  const tone =
    higherIsBetter === null ? "neutral"
    : higherIsBetter ? "auto"
    : value.value > 0 ? "negative" : "positive";

  return (
    <span className="inline-flex flex-col items-end gap-0.5">
      <NumberCell value={value.value} tone={tone} size="sm" />
      {value.source_conflict && (
        <span className="text-[10px] text-amber-500" title="OWID and Ember values disagree">⚠</span>
      )}
      {value.data_quality_status === "stale" && (
        <span className="text-[10px] text-zinc-500">stale</span>
      )}
    </span>
  );
}
