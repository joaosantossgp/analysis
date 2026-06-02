/**
 * CountryKpisPage — top-level macro KPI module at /country-kpis.
 *
 * Two views:
 *   Matrix — stacked horizontal bar showing full electricity mix per country
 *   Trend  — line chart, one series per country, for a selected KPI over time
 *
 * Future: multi-sector filter once other sectors are registered in the catalog.
 */
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  MatrixView,
  TrendView,
  TREND_KPIS,
} from "@/components/indicators/CountryKpiCharts";
import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import {
  fetchCountryKPISeries,
  fetchEnergyKPIHealth,
  triggerEnergyKPIRefresh,
} from "@/lib/api/energyKpis";
import { whenBridgeReady } from "@/lib/bridge/adapter";

const V1_ISO_CODES = ["BRA", "USA", "CHN", "OWEU", "CHL", "ARG"] as const;

type ViewMode = "matrix" | "trend";

export function CountryKpisPage() {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("matrix");
  const [year, setYear] = useState(() => new Date().getFullYear() - 1);
  const [trendKpiId, setTrendKpiId] = useState<string>(TREND_KPIS[0].kpi);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const seenRunning = useRef(false);
  const qc = useQueryClient();

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => { if (!cancelled) setBridgeReady(true); });
    return () => { cancelled = true; };
  }, []);

  // Health — polls every 2s while refreshing to detect completion
  const healthQuery = useQuery({
    queryKey: ["energy-kpi-health"],
    queryFn: () => fetchEnergyKPIHealth(),
    enabled: bridgeReady,
    staleTime: 10_000,
    refetchInterval: isRefreshing ? 2_000 : false,
  });
  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.health : null;

  // Detect thread completion via running→idle transition
  useEffect(() => {
    if (!isRefreshing) return;
    const running = (health as any)?.refresh_running as boolean | undefined;
    if (running === true) seenRunning.current = true;
    const done = (seenRunning.current && running !== true) || running === false;
    if (!done) return;

    seenRunning.current = false;
    setIsRefreshing(false);
    const status = health?.last_refresh_status;
    if (status === "success") {
      setStatusMsg({ text: `Updated — ${health?.rows_ingested ?? 0} rows ingested`, ok: true });
      void qc.invalidateQueries({ queryKey: ["country-kpi-all"] });
    } else {
      const err = (health as any)?.refresh_error ?? status ?? "unknown error";
      setStatusMsg({ text: `Refresh failed: ${String(err)}`, ok: false });
    }
    setTimeout(() => setStatusMsg(null), 8_000);
  }, [health, isRefreshing, qc]);

  // Fetch ALL years + ALL countries + ALL KPIs in one call
  const seriesQuery = useQuery({
    queryKey: ["country-kpi-all"],
    queryFn: () => fetchCountryKPISeries({ iso_codes: [...V1_ISO_CODES] }),
    enabled: bridgeReady,
    staleTime: 60_000,
  });
  const values = seriesQuery.data?.mode === "desktop" ? seriesQuery.data.values : [];
  const hasData = values.length > 0;

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setStatusMsg({ text: "Downloading OWID energy dataset (~7 MB)…", ok: true });
    try {
      await triggerEnergyKPIRefresh();
    } catch (e) {
      setIsRefreshing(false);
      setStatusMsg({ text: `Error: ${String(e)}`, ok: false });
      setTimeout(() => setStatusMsg(null), 6_000);
    }
  };

  const years = Array.from({ length: 12 }, (_, i) => new Date().getFullYear() - 1 - i);
  const breadcrumbs = [{ label: "Country KPIs" }];

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg space-y-5">
      <PageHeader
        title="Country KPIs"
        subtitle="Energy Utilities · electricity matrix, carbon intensity, demand, trade"
        breadcrumbs={breadcrumbs}
        actions={
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="px-3 py-1.5 text-sm rounded border border-zinc-600 bg-zinc-800 hover:bg-zinc-700
                       text-zinc-200 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {isRefreshing && <Spinner />}
            {isRefreshing ? "Updating…" : hasData ? "Update" : "Fetch data"}
          </button>
        }
      />

      {/* Status banners */}
      {health?.is_stale && !isRefreshing && (
        <StateBanner
          variant="error"
          message={`Data stale — last fetched ${health.owid_fetched_at?.slice(0, 10) ?? "unknown"}. Click Update.`}
        />
      )}
      {statusMsg && (
        <div className={`text-sm px-3 py-2 rounded border flex items-center gap-2 ${
          statusMsg.ok
            ? "border-zinc-700 bg-zinc-800/60 text-zinc-300"
            : "border-red-800 bg-red-950/40 text-red-300"
        }`}>
          {isRefreshing && <Spinner />}
          {statusMsg.text}
        </div>
      )}

      {/* View toggle + controls */}
      <div className="flex items-center gap-4 flex-wrap border-b border-zinc-800 pb-4">
        <div className="flex rounded border border-zinc-700 overflow-hidden">
          <ViewTab label="Electricity Matrix" active={viewMode === "matrix"} onClick={() => setViewMode("matrix")} />
          <ViewTab label="Trend" active={viewMode === "trend"} onClick={() => setViewMode("trend")} />
        </div>

        {viewMode === "matrix" && (
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
        )}

        {viewMode === "trend" && (
          <div className="flex items-center gap-2">
            <label className="text-xs text-zinc-400">Indicator</label>
            <select
              value={trendKpiId}
              onChange={e => setTrendKpiId(e.target.value)}
              className="text-sm bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-zinc-200 max-w-64"
            >
              {TREND_KPIS.map(k => (
                <option key={k.kpi} value={k.kpi}>{k.label}</option>
              ))}
            </select>
          </div>
        )}

        <p className="ml-auto text-xs text-zinc-500">
          Source: OWID energy dataset (CC-BY)
          {health?.owid_fetched_at && ` · ${health.owid_fetched_at.slice(0, 10)}`}
        </p>
      </div>

      {/* Body */}
      {seriesQuery.isLoading ? (
        <StateBanner variant="loading" />
      ) : seriesQuery.isError ? (
        <StateBanner variant="error" message="Failed to load KPI data." />
      ) : !hasData ? (
        <EmptyState onRefresh={handleRefresh} isRefreshing={isRefreshing} />
      ) : viewMode === "matrix" ? (
        <MatrixView values={values} year={year} isoCodes={[...V1_ISO_CODES]} />
      ) : (
        <TrendView
          values={values}
          kpiId={trendKpiId}
          isoCodes={[...V1_ISO_CODES]}
        />
      )}
    </section>
  );
}

function ViewTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? "bg-zinc-700 text-zinc-100"
          : "bg-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
      }`}
    >
      {label}
    </button>
  );
}

function Spinner() {
  return (
    <span className="w-3 h-3 rounded-full border-2 border-zinc-400 border-t-transparent animate-spin flex-shrink-0" />
  );
}

function EmptyState({ onRefresh, isRefreshing }: { onRefresh: () => void; isRefreshing: boolean }) {
  return (
    <div className="text-center py-16 space-y-4">
      <p className="text-zinc-400">No country KPI data yet.</p>
      <p className="text-zinc-500 text-sm max-w-md mx-auto">
        Click below to download the OWID energy dataset (~7 MB).
        Covers electricity mix, demand, carbon intensity, and trade for
        Brazil, US, China, EU, Chile, and Argentina.
      </p>
      <button
        onClick={onRefresh}
        disabled={isRefreshing}
        className="px-5 py-2 text-sm rounded border border-zinc-500 hover:border-zinc-300 bg-zinc-800
                   hover:bg-zinc-700 text-zinc-200 disabled:opacity-50 transition-colors flex items-center gap-2 mx-auto"
      >
        {isRefreshing && <Spinner />}
        {isRefreshing ? "Downloading…" : "Fetch energy data"}
      </button>
    </div>
  );
}
