/**
 * CountryKpiGrid — displays country-level Energy Utilities KPIs.
 *
 * Groups KPIs by macro_category. Shows NumberCell for scalar values.
 * Source badge per cell. "Sources disagree" indicator on conflict.
 * Stale banner when OWID data is > 90 days old.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchCountryKPISeries, fetchEnergyKPIHealth, fetchKPICatalog, triggerEnergyKPIRefresh } from "@/lib/api/energyKpis";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { CountryKPIValue, KPICatalogEntry } from "@/lib/bridge/types";
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

const MACRO_CATEGORY_LABELS: Record<string, string> = {
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
  energy_mix: "Primary Energy Mix",
  transition: "Transition",
  capacity: "Capacity",
};

type Props = {
  year?: number;
  isoCodes?: string[];
};

export function CountryKpiGrid({ year, isoCodes = [...V1_ISO_CODES] }: Props) {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [displayYear, setDisplayYear] = useState<number>(year ?? new Date().getFullYear() - 1);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => { cancelled = true; };
  }, []);

  const catalogQuery = useQuery({
    queryKey: ["energy-kpi-catalog"],
    queryFn: () => fetchKPICatalog({ dashboard_priority: "lead" }),
    enabled: bridgeReady,
    staleTime: 5 * 60_000,
  });

  const seriesQuery = useQuery({
    queryKey: ["country-kpi-series", displayYear, isoCodes],
    queryFn: () => fetchCountryKPISeries({ iso_codes: isoCodes, years: [displayYear] }),
    enabled: bridgeReady,
    staleTime: 60_000,
  });

  const healthQuery = useQuery({
    queryKey: ["energy-kpi-health"],
    queryFn: () => fetchEnergyKPIHealth(),
    enabled: bridgeReady,
    staleTime: 60_000,
  });

  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.health : null;
  const catalog = catalogQuery.data?.mode === "desktop" ? catalogQuery.data.entries : [];
  const values = seriesQuery.data?.mode === "desktop" ? seriesQuery.data.values : [];

  const isLoading = !bridgeReady || catalogQuery.isLoading || seriesQuery.isLoading;
  const isError = catalogQuery.isError || seriesQuery.isError;

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setRefreshError(null);
    try {
      await triggerEnergyKPIRefresh();
      await Promise.all([
        seriesQuery.refetch(),
        healthQuery.refetch(),
      ]);
    } catch (e) {
      setRefreshError(String(e));
    } finally {
      setIsRefreshing(false);
    }
  };

  if (!bridgeReady || isLoading) {
    return <StateBanner variant="loading" />;
  }

  if (isError) {
    return <StateBanner variant="error" message="Failed to load country KPI data." />;
  }

  const hasData = values.length > 0;

  return (
    <div className="space-y-4">
      {/* Stale banner */}
      {health?.is_stale && (
        <StateBanner
          variant="error"
          message={`Country KPI data is stale (last updated: ${health.owid_fetched_at ?? "unknown"}). Click "Update" to refresh.`}
        />
      )}

      {/* DQ errors banner */}
      {health && health.dq_errors > 0 && (
        <StateBanner
          variant="error"
          message={`${health.dq_errors} data quality error(s) in last refresh. Check source data.`}
        />
      )}

      {refreshError && (
        <StateBanner variant="error" message={`Refresh failed: ${refreshError}`} />
      )}

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <YearPicker value={displayYear} onChange={setDisplayYear} />

        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="ml-auto px-3 py-1.5 text-sm rounded border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 disabled:opacity-50 transition-colors"
        >
          {isRefreshing ? "Updating…" : "Update energy data"}
        </button>
      </div>

      {/* Source credit */}
      <p className="text-xs text-zinc-500">
        Source: Our World in Data energy dataset (CC-BY) · Electricity data via Ember Yearly Electricity Data ·{" "}
        {health?.owid_fetched_at ? `Last fetched ${health.owid_fetched_at.slice(0, 10)}` : "Not yet fetched"}
      </p>

      {!hasData ? (
        <EmptyState onRefresh={handleRefresh} isRefreshing={isRefreshing} />
      ) : (
        <KpiCategoryGroups catalog={catalog} values={values} isoCodes={isoCodes} />
      )}
    </div>
  );
}

function YearPicker({ value, onChange }: { value: number; onChange: (y: number) => void }) {
  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 10 }, (_, i) => currentYear - 1 - i);
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-zinc-400">Year</label>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200"
      >
        {years.map((y) => (
          <option key={y} value={y}>{y}</option>
        ))}
      </select>
    </div>
  );
}

function EmptyState({ onRefresh, isRefreshing }: { onRefresh: () => void; isRefreshing: boolean }) {
  return (
    <div className="text-center py-12 text-zinc-500 space-y-3">
      <p className="text-sm">No country KPI data yet.</p>
      <button
        onClick={onRefresh}
        disabled={isRefreshing}
        className="px-4 py-2 text-sm rounded border border-zinc-600 hover:border-zinc-400 bg-zinc-800 text-zinc-300 disabled:opacity-50 transition-colors"
      >
        {isRefreshing ? "Fetching OWID data…" : "Fetch energy data now"}
      </button>
    </div>
  );
}

function KpiCategoryGroups({
  catalog,
  values,
  isoCodes,
}: {
  catalog: KPICatalogEntry[];
  values: CountryKPIValue[];
  isoCodes: string[];
}) {
  // Index values by kpi_id + iso_code for O(1) lookup
  const valueIndex = new Map<string, CountryKPIValue>();
  for (const v of values) {
    valueIndex.set(`${v.kpi_id}|${v.iso_code}`, v);
  }

  // Group catalog entries by macro_category
  const grouped = new Map<string, KPICatalogEntry[]>();
  for (const entry of catalog) {
    if (entry.dashboard_priority === "not_in_v1_dashboard") continue;
    const grp = grouped.get(entry.macro_category) ?? [];
    grp.push(entry);
    grouped.set(entry.macro_category, grp);
  }

  // Desired category order
  const categoryOrder = [
    "renewables", "fossil_dependence", "hydro", "thermal", "carbon_intensity",
    "demand", "generation", "emissions", "trade", "energy_mix", "transition",
  ];

  const orderedCategories = [
    ...categoryOrder.filter((c) => grouped.has(c)),
    ...[...grouped.keys()].filter((c) => !categoryOrder.includes(c)),
  ];

  return (
    <div className="space-y-6">
      {orderedCategories.map((category) => {
        const entries = grouped.get(category) ?? [];
        return (
          <KpiCategorySection
            key={category}
            category={category}
            entries={entries}
            isoCodes={isoCodes}
            valueIndex={valueIndex}
          />
        );
      })}
    </div>
  );
}

function KpiCategorySection({
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
        {MACRO_CATEGORY_LABELS[category] ?? category}
      </h3>
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/50">
              <th className="text-left py-2 px-3 text-xs font-medium text-zinc-400 w-48">KPI</th>
              {isoCodes.map((iso) => (
                <th key={iso} className="text-right py-2 px-3 text-xs font-medium text-zinc-400 min-w-[80px]">
                  {COUNTRY_LABELS[iso] ?? iso}
                </th>
              ))}
              <th className="py-2 px-3 text-xs font-medium text-zinc-400 text-left w-16">Unit</th>
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
  const rowClass = isLast ? "" : "border-b border-zinc-800/60";
  return (
    <tr className={`${rowClass} hover:bg-zinc-800/30 transition-colors`}>
      <td className="py-2 px-3 text-zinc-300 text-xs">
        <span title={entry.description}>{entry.display_name}</span>
        {entry.v1_status === "v1_required" && (
          <span className="ml-1.5 text-[10px] text-zinc-500 font-mono">*</span>
        )}
      </td>
      {isoCodes.map((iso) => {
        const v = valueIndex.get(`${entry.kpi_id}|${iso}`);
        return (
          <td key={iso} className="py-2 px-3 text-right">
            <KpiValueCell value={v} higherIsBetter={entry.higher_is_better} />
          </td>
        );
      })}
      <td className="py-2 px-3 text-xs text-zinc-500">{entry.unit}</td>
    </tr>
  );
}

function KpiValueCell({
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
    higherIsBetter === null
      ? "neutral"
      : higherIsBetter
        ? "auto"
        : value.value > 0
          ? "negative"
          : "positive";

  return (
    <span className="inline-flex flex-col items-end gap-0.5">
      <NumberCell value={value.value} tone={tone} size="sm" />
      {value.source_conflict && (
        <span
          className="text-[10px] text-amber-500"
          title="Sources disagree — OWID and Ember values differ by more than threshold"
        >
          ⚠ sources disagree
        </span>
      )}
      {value.data_quality_status === "stale" && (
        <span className="text-[10px] text-zinc-500">stale</span>
      )}
    </span>
  );
}
