import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import {
  fetchSINKPIDashboard,
  fetchSINKPIHealth,
  fetchSINKPISeries,
  triggerSINKPIRefresh,
  fetchKPICatalog,
} from "@/lib/api/energyKpis";
import type { SINKPIDashboardResponse, SINKPIObservation } from "@/lib/bridge/types";
import { useSubsystemKpiConfig } from "@/lib/indicators/useSubsystemKpiConfig";
import { IndicatorControls } from "./IndicatorControls";
import { IndicatorLegend } from "./IndicatorLegend";
import { IndicatorChart } from "./IndicatorChart";
import type { IndicatorDef, ResolvedSeries, ChartType, AxisSide } from "@/lib/indicators/types";

const SIN_NS = "energy_utilities.sin";

const SUBSYSTEMS = [
  { code: "S", short: "S", label: "South / Sul", color: "#60A5FA" },
  { code: "SE_CO", short: "SE/CO", label: "Southeast-Center West", color: "#22D3EE" },
  { code: "NE", short: "NE", label: "Northeast / Nordeste", color: "#FBBF24" },
  { code: "N", short: "N", label: "North / Norte", color: "#4ADE80" },
] as const;

const KPI = {
  load: `${SIN_NS}.load_mwmed`,
  generationTotal: `${SIN_NS}.generation_total_mwmed`,
  hydro: `${SIN_NS}.generation_hydro_mwmed`,
  thermal: `${SIN_NS}.generation_thermal_mwmed`,
  wind: `${SIN_NS}.generation_wind_mwmed`,
  solar: `${SIN_NS}.generation_solar_mwmed`,
  mixHydro: `${SIN_NS}.mix_hydro_pct`,
  mixThermal: `${SIN_NS}.mix_thermal_pct`,
  mixWind: `${SIN_NS}.mix_wind_pct`,
  mixSolar: `${SIN_NS}.mix_solar_pct`,
  ear: `${SIN_NS}.ear_stored_pct`,
  ena: `${SIN_NS}.ena_gross_mwmed`,
  cmo: `${SIN_NS}.cmo_brl_mwh`,
  pld: `${SIN_NS}.pld_brl_mwh`,
  interchange: `${SIN_NS}.net_interchange_mwmed`,
} as const;

const SIN_KPI_META_FALLBACK: Record<string, { label: string; unit: string; category: string }> = {
  "energy_utilities.sin.load_mwmed": { label: "Load", unit: "MWmed", category: "Load" },
  "energy_utilities.sin.generation_hydro_mwmed": { label: "Hydro Generation", unit: "MWmed", category: "Generation" },
  "energy_utilities.sin.generation_thermal_mwmed": { label: "Thermal Generation", unit: "MWmed", category: "Generation" },
  "energy_utilities.sin.generation_wind_mwmed": { label: "Wind Generation", unit: "MWmed", category: "Generation" },
  "energy_utilities.sin.generation_solar_mwmed": { label: "Solar Generation", unit: "MWmed", category: "Generation" },
  "energy_utilities.sin.generation_total_mwmed": { label: "Total Generation", unit: "MWmed", category: "Generation" },
  "energy_utilities.sin.mix_hydro_pct": { label: "Hydro Mix", unit: "pct", category: "Generation Mix" },
  "energy_utilities.sin.mix_thermal_pct": { label: "Thermal Mix", unit: "pct", category: "Generation Mix" },
  "energy_utilities.sin.mix_wind_pct": { label: "Wind Mix", unit: "pct", category: "Generation Mix" },
  "energy_utilities.sin.mix_solar_pct": { label: "Solar Mix", unit: "pct", category: "Generation Mix" },
  "energy_utilities.sin.ear_stored_mwmes": { label: "Stored Energy (MWmes)", unit: "number", category: "Reservoirs" },
  "energy_utilities.sin.ear_stored_pct": { label: "Stored Energy (%)", unit: "pct", category: "Reservoirs" },
  "energy_utilities.sin.ena_gross_mwmed": { label: "Gross ENA (MWmed)", unit: "number", category: "Hydrology" },
  "energy_utilities.sin.ena_gross_pct_mlt": { label: "Gross ENA % MLT", unit: "pct", category: "Hydrology" },
  "energy_utilities.sin.ena_storable_mwmed": { label: "Storable ENA (MWmed)", unit: "number", category: "Hydrology" },
  "energy_utilities.sin.ena_storable_pct_mlt": { label: "Storable ENA % MLT", unit: "pct", category: "Hydrology" },
  "energy_utilities.sin.cmo_brl_mwh": { label: "CMO", unit: "number", category: "Prices" },
  "energy_utilities.sin.pld_brl_mwh": { label: "PLD", unit: "number", category: "Prices" },
  "energy_utilities.sin.net_interchange_mwmed": { label: "Net Interchange", unit: "number", category: "Trade" },
};

const AUDIT_KPI_IDS = [
  KPI.load,
  KPI.generationTotal,
  KPI.ear,
  KPI.cmo,
  KPI.pld,
];

type LatestIndex = Map<string, SINKPIObservation>;

function isPctKpi(kpiId: string): boolean {
  return kpiId.endsWith("pct") || kpiId.includes("share");
}

const RANGE_OPTIONS = [
  { label: "30 Days", days: 30 },
  { label: "90 Days", days: 90 },
  { label: "1 Year", days: 365 },
  { label: "2 Years", days: 730 },
  { label: "All History", days: 9999 },
];

export function SINKpiPanel({
  bridgeReady,
  viewMode,
}: {
  bridgeReady: boolean;
  viewMode: "matrix" | "trend";
}) {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshStartedAt, setRefreshStartedAt] = useState<number | null>(null);
  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const seenRunning = useRef(false);
  const qc = useQueryClient();

  const { config, setSelected, setChart } = useSubsystemKpiConfig(SUBSYSTEMS.map((s) => s.code));
  const { selected, chart } = config;

  const [trendKpiId, setTrendKpiId] = useState<string>(KPI.load);
  const [rangeDays, setRangeDays] = useState<number>(365);

  const startDatetime = useMemo(() => {
    if (rangeDays === 9999) return "2000-01-01T00:00:00";
    const d = new Date(Date.now() - rangeDays * 86_400_000);
    return d.toISOString().slice(0, 19);
  }, [rangeDays]);

  const catalogQuery = useQuery({
    queryKey: ["energy-kpi-catalog-all"],
    queryFn: () => fetchKPICatalog(),
    enabled: bridgeReady,
    staleTime: 5 * 60_000,
  });

  const sinCatalog = useMemo(() => {
    const entries = catalogQuery.data?.mode === "desktop" ? catalogQuery.data.entries : [];
    return entries.filter((e) => e.kpi_id.startsWith("energy_utilities.sin"));
  }, [catalogQuery.data]);

  const defs: IndicatorDef[] = useMemo(() => {
    if (sinCatalog.length > 0) {
      return sinCatalog.map((e) => ({
        id: e.kpi_id,
        label: e.display_name,
        category: e.macro_category || "General",
        unit: e.unit === "%" ? ("pct" as const) : e.unit === "ratio" ? ("ratio" as const) : ("number" as const),
        isPlaceholder: false,
        available: true,
      }));
    }
    return Object.entries(SIN_KPI_META_FALLBACK).map(([id, meta]) => ({
      id,
      label: meta.label,
      category: meta.category,
      unit: meta.unit as "pct" | "ratio" | "number",
      isPlaceholder: false,
      available: true,
    }));
  }, [sinCatalog]);

  const dashboardQuery = useQuery({
    queryKey: ["sin-kpi-dashboard"],
    queryFn: fetchSINKPIDashboard,
    enabled: bridgeReady,
    staleTime: 30_000,
    refetchInterval: isRefreshing ? 2_000 : false,
  });

  const healthQuery = useQuery({
    queryKey: ["sin-kpi-health"],
    queryFn: fetchSINKPIHealth,
    enabled: bridgeReady,
    staleTime: 10_000,
    refetchInterval: isRefreshing ? 2_000 : false,
  });

  const seriesQuery = useQuery({
    queryKey: ["sin-kpi-series", startDatetime, trendKpiId],
    queryFn: () => fetchSINKPISeries({
      kpi_ids: [trendKpiId],
      subsystem_codes: SUBSYSTEMS.map((s) => s.code),
      start_datetime: startDatetime,
      limit: 50_000,
    }),
    enabled: bridgeReady && !!trendKpiId,
    staleTime: 60_000,
  });

  const dashboard =
    dashboardQuery.data?.mode === "desktop" ? dashboardQuery.data.dashboard : null;
  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.health : null;
  const series = seriesQuery.data?.mode === "desktop" ? seriesQuery.data.values : [];

  const aggregatedSeries = useMemo(() => {
    if (!series || series.length === 0) return [];

    const hasTime = series.some((row) => {
      const parts = row.reference_datetime.split(/[ T]/);
      if (parts.length > 1) {
        const timePart = parts[1];
        return timePart !== "00:00:00" && timePart !== "00:00:00.000Z" && timePart !== "00:00";
      }
      return false;
    });

    if (rangeDays <= 30 || !hasTime) {
      return series;
    }

    const groups = new Map<string, { sum: number; count: number; row: (typeof series)[0] }>();
    for (const row of series) {
      if (row.value === null) continue;
      const datePart = row.reference_datetime.slice(0, 10);
      const key = `${row.subsystem_code}|${row.kpi_id}|${datePart}`;

      const existing = groups.get(key);
      if (existing) {
        existing.sum += row.value;
        existing.count += 1;
      } else {
        groups.set(key, {
          sum: row.value,
          count: 1,
          row: {
            ...row,
            reference_datetime: `${datePart}T00:00:00`,
          },
        });
      }
    }

    const result: typeof series = [];
    for (const group of groups.values()) {
      result.push({
        ...group.row,
        value: group.sum / group.count,
      });
    }
    return result;
  }, [series, rangeDays]);

  const sortedDatetimes = useMemo(() => {
    const dates = new Set<string>();
    for (const row of aggregatedSeries) {
      if (row.kpi_id === trendKpiId && row.value !== null) {
        dates.add(row.reference_datetime);
      }
    }
    return [...dates].sort();
  }, [aggregatedSeries, trendKpiId]);

  const periods = useMemo(() => {
    const hasTime = sortedDatetimes.some((dt) => {
      const parts = dt.split(/[ T]/);
      if (parts.length > 1) {
        const timePart = parts[1];
        return timePart !== "00:00:00" && timePart !== "00:00:00.000Z" && timePart !== "00:00";
      }
      return false;
    });

    const spansMultipleYears = sortedDatetimes.length > 0 &&
      sortedDatetimes[0].slice(0, 4) !== sortedDatetimes[sortedDatetimes.length - 1].slice(0, 4);

    return sortedDatetimes.map((dt) => {
      const match = dt.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
      if (!match) return dt;
      const [, year, month, day, hour, minute] = match;
      const yy = year.slice(2);
      if (hasTime && hour !== undefined && minute !== undefined) {
        if (spansMultipleYears) {
          return `${month}/${day}/${yy} ${hour}:${minute}`;
        }
        return `${month}/${day} ${hour}:${minute}`;
      }
      return `${month}/${day}/${yy}`;
    });
  }, [sortedDatetimes]);

  const plottable = useMemo(() => {
    return selected.filter((s) => SUBSYSTEMS.some((sub) => sub.code === s.id));
  }, [selected]);

  const selectionById = useMemo(() => {
    return new Map(selected.map((s) => [s.id, s] as const));
  }, [selected]);

  const chartSeries: ResolvedSeries[] = useMemo(() => {
    return plottable.map((sel) => {
      const sub = SUBSYSTEMS.find((s) => s.code === sel.id)!;
      const valueByDt = new Map<string, number>();
      for (const row of aggregatedSeries) {
        if (row.kpi_id === trendKpiId && row.subsystem_code === sub.code && row.value !== null) {
          valueByDt.set(row.reference_datetime, row.value);
        }
      }

      let points = sortedDatetimes.map((dt) => valueByDt.get(dt) ?? null);

      const def = defs.find((d) => d.id === trendKpiId) || SIN_KPI_META_FALLBACK[trendKpiId];
      const isPct = def?.unit === "pct" || trendKpiId.endsWith("pct") || trendKpiId.includes("share");
      if (isPct) {
        points = points.map((v) => (v !== null ? v / 100 : null));
      }

      if (chart.indexMode) {
        const first = points.find((v): v is number => v !== null);
        if (first != null && first !== 0) {
          points = points.map((v) => (v !== null ? v / Math.abs(first) : null));
        }
      }

      const finite = points.filter((v): v is number => v !== null);

      const resolvedType: ChartType =
        sel.type === "auto" ? chart.type : sel.type;

      const resolvedAxis: AxisSide =
        sel.axis === "auto" ? "left" : sel.axis;

      return {
        id: sub.code,
        label: sub.label,
        unit: chart.indexMode ? ("number" as const) : isPct ? ("pct" as const) : ("number" as const),
        color: sub.color,
        type: resolvedType,
        axis: resolvedAxis,
        points,
        latest: finite.length > 0 ? finite[finite.length - 1] : null,
      };
    });
  }, [series, trendKpiId, sortedDatetimes, defs, plottable, chart.type, chart.indexMode]);

  const subsystemDefs: IndicatorDef[] = useMemo(() => {
    return SUBSYSTEMS.map((sub) => ({
      id: sub.code,
      label: sub.label,
      category: "Subsystems",
      unit: isPctKpi(trendKpiId) ? ("pct" as const) : ("number" as const),
      isPlaceholder: false,
      available: series.some((row) => row.kpi_id === trendKpiId && row.subsystem_code === sub.code && row.value !== null),
    }));
  }, [series, trendKpiId]);

  function toggle(id: string) {
    const exists = selected.some((s) => s.id === id);
    if (exists) {
      setSelected(selected.filter((s) => s.id !== id));
    } else {
      setSelected([...selected, { id, axis: "auto", type: "auto" }]);
    }
  }

  function setAxis(id: string, axis: "auto" | AxisSide) {
    setSelected(selected.map((s) => (s.id === id ? { ...s, axis } : s)));
  }

  function setType(id: string, type: "auto" | ChartType) {
    setSelected(selected.map((s) => (s.id === id ? { ...s, type } : s)));
  }

  const showAxisControls = useMemo(() => {
    return new Set(chartSeries.map((s) => s.unit)).size > 1;
  }, [chartSeries]);

  const backendRefreshRunning = Boolean(dashboard?.refresh_running || health?.refresh_running);

  useEffect(() => {
    if (!isRefreshing || !dashboard) return;
    const elapsedMs = refreshStartedAt ? Date.now() - refreshStartedAt : 0;
    if (backendRefreshRunning) seenRunning.current = true;

    if (backendRefreshRunning && elapsedMs > 45_000) {
      setIsRefreshing(false);
      setRefreshStartedAt(null);
      setStatusMsg({
        text: "SIN refresh is still running in the backend. The dashboard will keep the local cache visible while the job finishes.",
        ok: true,
      });
      setTimeout(() => setStatusMsg(null), 10_000);
      return;
    }

    const done = !backendRefreshRunning && (seenRunning.current || elapsedMs > 1_200);
    if (!done) return;

    seenRunning.current = false;
    setIsRefreshing(false);
    setRefreshStartedAt(null);
    const refreshError = dashboard.refresh_error ?? health?.refresh_error ?? null;
    if (refreshError) {
      // Failures stay until dismissed or the next refresh, so they aren't missed.
      setStatusMsg({ text: `Refresh finished with source issues: ${refreshError}`, ok: false });
    } else {
      const status = health?.last_refresh_status;
      const prefix = status === "partial" ? "SIN cache updated with partial source coverage" : "SIN cache updated";
      setStatusMsg({ text: `${prefix} from local source snapshots.`, ok: true });
      setTimeout(() => setStatusMsg(null), 8_000);
    }
    void qc.invalidateQueries({ queryKey: ["sin-kpi-dashboard"] });
    void qc.invalidateQueries({ queryKey: ["sin-kpi-health"] });
    void qc.invalidateQueries({ queryKey: ["sin-kpi-series"] });
  }, [backendRefreshRunning, dashboard, health, isRefreshing, qc, refreshStartedAt]);

  const handleRefresh = async () => {
    seenRunning.current = false;
    setIsRefreshing(true);
    setRefreshStartedAt(Date.now());
    setStatusMsg({ text: "Downloading ONS subsystem datasets and attempting CCEE PLD...", ok: true });
    try {
      const response = await triggerSINKPIRefresh();
      if (response.mode === "browser") {
        setIsRefreshing(false);
        setRefreshStartedAt(null);
        setStatusMsg({ text: response.reason, ok: false });
        return;
      }
      const status = response.result.status;
      if (status === "success" || status === "partial" || status === "error") {
        setIsRefreshing(false);
        setRefreshStartedAt(null);
        setStatusMsg({
          text: status === "error"
            ? `Refresh failed: ${response.result.error ?? "unknown error"}`
            : `SIN refresh completed: ${response.result.rows_inserted ?? 0} rows inserted.`,
          ok: status !== "error",
        });
        void qc.invalidateQueries({ queryKey: ["sin-kpi-dashboard"] });
        void qc.invalidateQueries({ queryKey: ["sin-kpi-health"] });
        void qc.invalidateQueries({ queryKey: ["sin-kpi-series"] });
      }
      await Promise.all([dashboardQuery.refetch(), healthQuery.refetch()]);
    } catch (error) {
      setIsRefreshing(false);
      setRefreshStartedAt(null);
      setStatusMsg({ text: `Refresh failed: ${String(error)}`, ok: false });
    }
  };

  if (!bridgeReady || dashboardQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading SIN subsystem cache..." />;
  }
  if (dashboardQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" message={dashboardQuery.data.reason} />;
  }
  if (dashboardQuery.isError) {
    return (
      <StateBanner
        variant="error"
        title="Could not load SIN KPIs"
        message={dashboardQuery.error instanceof Error ? dashboardQuery.error.message : String(dashboardQuery.error)}
        onRetry={() => { void dashboardQuery.refetch(); }}
      />
    );
  }
  if (!dashboard) {
    return <StateBanner variant="empty" title="SIN dashboard unavailable" />;
  }

  const latestIndex = buildLatestIndex(dashboard.observations);
  const hasData = !dashboard.is_empty && dashboard.observations.length > 0;
  const refreshBusy = isRefreshing || backendRefreshRunning;

  const xTickFormatter = (value: string) => {
    if (rangeDays <= 30) return value;
    const match = value.match(/^(\d{2})\/(\d{2})\/(\d{2})/);
    if (!match) return value;
    const [, month, , year] = match;
    const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const mIdx = parseInt(month, 10) - 1;
    if (mIdx >= 0 && mIdx < 12) {
      return `${MONTHS[mIdx]}/${year}`;
    }
    return value;
  };

  return (
    <div className="min-w-0 max-w-full space-y-5">
      {/* Title & Refresh Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-4">
        <div>
          <h3 className="text-base font-semibold text-zinc-100">Energy Utilities - SIN Subsystems</h3>
          <p className="mt-0.5 text-xs text-zinc-500">
            Local cache first. Manual refresh downloads ONS operating datasets and attempts CCEE PLD.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshBusy}
            className="flex items-center gap-2 rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-200 transition-colors hover:bg-zinc-700 disabled:opacity-50"
          >
            {refreshBusy && <Spinner />}
            {backendRefreshRunning ? "Refresh running" : hasData ? "Update SIN data" : "Fetch SIN data"}
          </button>
        </div>
      </div>

      {statusMsg && (
        <StateBanner
          variant={statusMsg.ok ? "empty" : "error"}
          title={statusMsg.ok ? "Refresh status" : "Source issue"}
          message={statusMsg.text}
          size="dense"
          onRetry={statusMsg.ok || refreshBusy ? undefined : handleRefresh}
        />
      )}
      {dashboard.is_stale && (
        <StateBanner
          variant="warning"
          title="SIN data may be out of date"
          message={`Latest local reference is ${formatDateTime(dashboard.latest_reference_datetime)}. Cached values are still shown — click Update SIN data to refresh.`}
        />
      )}
      {dashboard.refresh_error && !isRefreshing && (
        <StateBanner
          variant="error"
          title="Last SIN refresh had source issues"
          message={dashboard.refresh_error}
        />
      )}
      {backendRefreshRunning && !isRefreshing && (
        <StateBanner
          variant="loading"
          title="SIN refresh is running"
          message="ONS/CCEE downloads are continuing in the backend. Existing cached values remain readable."
          size="dense"
        />
      )}

      {!hasData ? (
        <EmptySINState
          onRefresh={handleRefresh}
          isStarting={isRefreshing}
          refreshRunning={backendRefreshRunning}
        />
      ) : viewMode === "matrix" ? (
        /* Matrix View: Generation Mix */
        <div className="space-y-4">
          <VisualPanel title="Generation Mix" subtitle="Latest measured generation shares by subsystem">
            <GenerationMix latestIndex={latestIndex} />
          </VisualPanel>
          <SubsystemAuditTable
            latestIndex={latestIndex}
            dashboard={dashboard}
            selectedKpiIds={AUDIT_KPI_IDS}
            defs={defs}
          />
          <SourcePanel dashboard={dashboard} />
        </div>
      ) : (
        /* Trend View: Unified Subsystem Trend Chart */
        <div className="space-y-4">
          <div className="flex items-center gap-4 flex-wrap bg-zinc-950/20 border border-zinc-800 rounded p-4">
            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-400">Indicator</label>
              <select
                value={trendKpiId}
                onChange={(e) => setTrendKpiId(e.target.value)}
                className="text-sm bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-zinc-200 focus:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-600 max-w-xs"
              >
                {defs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-400">Range</label>
              <select
                value={rangeDays}
                onChange={(e) => setRangeDays(Number(e.target.value))}
                className="text-sm bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-zinc-200 focus:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-600"
              >
                {RANGE_OPTIONS.map((opt) => (
                  <option key={opt.days} value={opt.days}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <IndicatorControls
              frequency="annual"
              quarterlyAvailable={false}
              onFrequencyChange={() => undefined}
              showFrequency={false}
              itemNoun="Subsystems"
              defs={subsystemDefs}
              selectedIds={selected.map((s) => s.id)}
              onToggleIndicator={toggle}
              maxSelected={4}
              chart={chart}
              onChartChange={setChart}
            />
          </div>

          {chartSeries.length === 0 || periods.length === 0 ? (
            <StateBanner
              variant="empty"
              title="Nothing to plot"
              message="Select at least one subsystem using the Subsystems picker above."
            />
          ) : (
            <div className="rounded border border-zinc-800 bg-zinc-950/35 p-4">
              <IndicatorChart
                series={chartSeries}
                periods={periods}
                config={chart}
                height={320}
                xTickFormatter={xTickFormatter}
              />
            </div>
          )}

          {chart.legend && chartSeries.length > 0 && (
            <IndicatorLegend
              series={chartSeries}
              selectionById={selectionById}
              indexMode={chart.indexMode}
              showAxisControls={showAxisControls}
              onSetAxis={setAxis}
              onSetType={setType}
              onRemove={toggle}
            />
          )}

          <SubsystemAuditTable
            latestIndex={latestIndex}
            dashboard={dashboard}
            selectedKpiIds={AUDIT_KPI_IDS}
            defs={defs}
          />
          <SourcePanel dashboard={dashboard} />
        </div>
      )}
    </div>
  );
}

function EmptySINState({
  onRefresh,
  isStarting,
  refreshRunning,
}: {
  onRefresh: () => void;
  isStarting: boolean;
  refreshRunning: boolean;
}) {
  const disabled = isStarting || refreshRunning;
  return (
    <StateBanner
      variant="empty"
      title="No SIN subsystem data yet"
      message="Downloading runs only when requested. Existing cached data is used offline after the first successful refresh."
    >
      <button
        type="button"
        onClick={onRefresh}
        disabled={disabled}
        className="mt-1 inline-flex items-center gap-2 self-start rounded border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 transition-colors hover:bg-zinc-700 disabled:opacity-50"
      >
        {disabled && <Spinner />}
        {refreshRunning ? "Refresh running" : isStarting ? "Starting refresh" : "Fetch SIN data"}
      </button>
    </StateBanner>
  );
}

function VisualPanel({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="min-w-0 rounded border border-zinc-800 bg-zinc-950/35 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h4 className="text-sm font-medium text-zinc-100">{title}</h4>
          <p className="text-[11px] text-zinc-500">{subtitle}</p>
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

function GenerationMix({ latestIndex }: { latestIndex: LatestIndex }) {
  const mix = [
    { kpi: KPI.mixHydro, label: "Hydro", color: "#60A5FA" },
    { kpi: KPI.mixThermal, label: "Thermal", color: "#FB923C" },
    { kpi: KPI.mixWind, label: "Wind", color: "#4ADE80" },
    { kpi: KPI.mixSolar, label: "Solar", color: "#FBBF24" },
  ];
  return (
    <div className="space-y-4">
      {SUBSYSTEMS.map((sub) => {
        const parts = mix.map((item) => ({
          ...item,
          value: latestIndex.get(key(item.kpi, sub.code))?.value ?? 0,
        }));
        return (
          <div key={sub.code}>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-xs text-zinc-300">{sub.label}</span>
              <span className="font-mono text-[10px] text-zinc-500">{sub.short}</span>
            </div>
            <div className="flex h-7 overflow-hidden rounded border border-zinc-800 bg-zinc-900">
              {parts.map((part) => (
                <div
                  key={part.kpi}
                  title={`${part.label}: ${formatNumber(part.value)}%`}
                  className="relative flex items-center justify-center"
                  style={{ width: `${Math.max(0, part.value)}%`, background: part.color }}
                >
                  {part.value > 8 && (
                    <span className="text-[10px] font-medium text-zinc-900/80">
                      {Math.round(part.value)}%
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      })}
      <div className="flex flex-wrap gap-3 text-[10px] text-zinc-500">
        {mix.map((part) => (
          <span key={part.kpi} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: part.color }} />
            {part.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function SubsystemAuditTable({
  latestIndex,
  dashboard,
  selectedKpiIds,
  defs,
}: {
  latestIndex: LatestIndex;
  dashboard: SINKPIDashboardResponse;
  selectedKpiIds: string[];
  defs: IndicatorDef[];
}) {
  const rows = SUBSYSTEMS.map((sub) => ({
    sub,
    latest: latestReferenceForSubsystem(dashboard.observations, sub.code),
  }));
  return (
    <section className="min-w-0 max-w-full rounded border border-zinc-800 bg-zinc-950/35">
      <div className="border-b border-zinc-800 px-4 py-3">
        <h4 className="text-sm font-medium text-zinc-100">Audit Table</h4>
        <p className="text-[11px] text-zinc-500">Latest local value by subsystem, KPI, unit, and reference timestamp.</p>
      </div>
      <div className="min-w-0 max-w-full overflow-x-auto">
        <table className="min-w-[720px] w-full border-collapse text-sm">
          <thead>
            <tr className="bg-zinc-900/80 text-left text-[10px] uppercase tracking-wider text-zinc-500">
              <th className="px-3 py-2 font-medium">Subsystem</th>
              {selectedKpiIds.map((kpiId) => {
                const def = defs.find((d) => d.id === kpiId) || SIN_KPI_META_FALLBACK[kpiId];
                const obsUnit =
                  latestIndex.get(key(kpiId, "SE_CO"))?.unit ||
                  latestIndex.get(key(kpiId, "S"))?.unit ||
                  def?.unit ||
                  "";
                return (
                  <NumHead
                    key={kpiId}
                    label={def?.label || kpiId.split(".").pop() || ""}
                    unit={obsUnit}
                  />
                );
              })}
              <th className="px-3 py-2 text-right font-medium">Latest</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/80 text-zinc-200">
            {rows.map(({ sub, latest }) => (
              <tr key={sub.code} className="hover:bg-zinc-900/50">
                <td className="px-3 py-2">
                  <span className="font-medium text-zinc-100">{sub.label}</span>
                  <span className="ml-2 font-mono text-[10px] text-zinc-500">{sub.short}</span>
                </td>
                {selectedKpiIds.map((kpiId) => {
                  const isSigned = kpiId.includes("interchange");
                  return (
                    <NumCell
                      key={kpiId}
                      value={latestIndex.get(key(kpiId, sub.code))?.value}
                      signed={isSigned}
                    />
                  );
                })}
                <td className="px-3 py-2 text-right font-mono text-[11px] text-zinc-500">{formatDateTime(latest)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SourcePanel({ dashboard }: { dashboard: SINKPIDashboardResponse }) {
  return (
    <section className="rounded border border-zinc-800 bg-zinc-950/35 p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h4 className="text-sm font-medium text-zinc-100">Source Provenance</h4>
          <p className="text-[11px] text-zinc-500">
            Local records are read from `energy_kpis.db`; no live network call is required to open this dashboard.
          </p>
        </div>
        <span className="font-mono text-[10px] text-zinc-500">
          Last successful update: {formatDateTime(dashboard.last_successful_update)}
        </span>
      </div>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
        {dashboard.source_statuses.map((source) => (
          <div key={`${source.source}:${source.dataset}`} className="rounded border border-zinc-800 bg-zinc-900/35 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-zinc-200">{source.source}</span>
              <span className={source.last_error ? "text-[10px] text-amber-300" : "text-[10px] text-green-300"}>
                {source.last_error ? "partial" : source.last_status ?? "idle"}
              </span>
            </div>
            <p className="mt-1 truncate font-mono text-[10px] text-zinc-500" title={source.dataset}>{source.dataset}</p>
            <dl className="mt-3 space-y-1 text-[11px]">
              <SourceStat label="Frequency" value={source.frequency} />
              <SourceStat label="Records" value={source.local_records_count.toLocaleString("en-US")} />
              <SourceStat label="Snapshot" value={formatDateTime(source.last_snapshot_at)} />
            </dl>
            {source.last_error && (
              <p className="mt-2 line-clamp-2 text-[10px] text-amber-300" title={source.last_error}>{source.last_error}</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function SourceStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 justify-between gap-2">
      <dt className="shrink-0 text-zinc-600">{label}</dt>
      <dd className="min-w-0 break-words text-right font-mono text-zinc-400">{value}</dd>
    </div>
  );
}

function NumHead({ label, unit }: { label: string; unit: string }) {
  return (
    <th className="px-3 py-2 text-right font-medium">
      {label} <span className="normal-case text-zinc-600">({unit})</span>
    </th>
  );
}

function NumCell({ value, signed = false }: { value: number | null | undefined; signed?: boolean }) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return <td className="px-3 py-2 text-right font-mono text-[11px] text-zinc-600">-</td>;
  }
  const text = signed && value > 0 ? `+${formatNumber(value)}` : formatNumber(value);
  return (
    <td className={`px-3 py-2 text-right font-mono text-[11px] ${signed && value < 0 ? "text-red-300" : "text-zinc-300"}`}>
      {text}
    </td>
  );
}

function Spinner() {
  return (
    <span className="h-3 w-3 flex-shrink-0 rounded-full border-2 border-zinc-400 border-t-transparent animate-spin" />
  );
}

function buildLatestIndex(values: SINKPIObservation[]): LatestIndex {
  const map: LatestIndex = new Map();
  for (const row of values) {
    map.set(key(row.kpi_id, row.subsystem_code), row);
  }
  return map;
}

function latestReferenceForSubsystem(values: SINKPIObservation[], subsystemCode: string): string | null {
  const refs = values
    .filter((row) => row.subsystem_code === subsystemCode)
    .map((row) => row.reference_datetime)
    .sort();
  return refs.at(-1) ?? null;
}

function key(kpiId: string, subsystemCode: string): string {
  return `${kpiId}|${subsystemCode}`;
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  const abs = Math.abs(value);
  const digits = abs >= 1000 ? 0 : abs >= 100 ? 1 : 2;
  return value.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 16);
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
