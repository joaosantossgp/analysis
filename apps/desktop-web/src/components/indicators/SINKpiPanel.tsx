import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import {
  fetchSINKPIDashboard,
  fetchSINKPIHealth,
  fetchSINKPISeries,
  triggerSINKPIRefresh,
} from "@/lib/api/energyKpis";
import type { SINKPIDashboardResponse, SINKPIObservation } from "@/lib/bridge/types";

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

const SERIES_KPIS = [KPI.load, KPI.ear, KPI.ena, KPI.cmo, KPI.pld] as const;

type LatestIndex = Map<string, SINKPIObservation>;

export function SINKpiPanel({ bridgeReady }: { bridgeReady: boolean }) {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshStartedAt, setRefreshStartedAt] = useState<number | null>(null);
  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const seenRunning = useRef(false);
  const qc = useQueryClient();

  const startDatetime = useMemo(() => {
    const d = new Date(Date.now() - 30 * 86_400_000);
    return d.toISOString().slice(0, 19);
  }, []);

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
    queryKey: ["sin-kpi-series", startDatetime],
    queryFn: () => fetchSINKPISeries({
      kpi_ids: [...SERIES_KPIS],
      subsystem_codes: SUBSYSTEMS.map((s) => s.code),
      start_datetime: startDatetime,
      limit: 10_000,
    }),
    enabled: bridgeReady,
    staleTime: 60_000,
  });

  const dashboard =
    dashboardQuery.data?.mode === "desktop" ? dashboardQuery.data.dashboard : null;
  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.health : null;
  const series = seriesQuery.data?.mode === "desktop" ? seriesQuery.data.values : [];
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
      setStatusMsg({ text: `Refresh finished with source issues: ${refreshError}`, ok: false });
    } else {
      const status = health?.last_refresh_status;
      const prefix = status === "partial" ? "SIN cache updated with partial source coverage" : "SIN cache updated";
      setStatusMsg({ text: `${prefix} from local source snapshots.`, ok: true });
    }
    void qc.invalidateQueries({ queryKey: ["sin-kpi-dashboard"] });
    void qc.invalidateQueries({ queryKey: ["sin-kpi-health"] });
    void qc.invalidateQueries({ queryKey: ["sin-kpi-series"] });
    setTimeout(() => setStatusMsg(null), 8_000);
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

  return (
    <div className="min-w-0 max-w-full space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-4">
        <div>
          <h3 className="text-base font-semibold text-zinc-100">Energy Utilities - SIN Subsystems</h3>
          <p className="mt-0.5 text-xs text-zinc-500">
            Local cache first. Manual refresh downloads ONS operating datasets and attempts CCEE PLD.
          </p>
        </div>
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

      {statusMsg && (
        <StateBanner
          variant={statusMsg.ok ? "empty" : "error"}
          title={statusMsg.ok ? "Refresh status" : "Source issue"}
          message={statusMsg.text}
          size="dense"
        />
      )}
      {dashboard.is_stale && (
        <StateBanner
          variant="error"
          title="SIN data is stale"
          message={`Latest local reference is ${formatDateTime(dashboard.latest_reference_datetime)}.`}
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
      ) : (
        <>
          <div className="grid gap-3 xl:grid-cols-5 md:grid-cols-2">
            <MetricCard title="Load" unit="MWmed" kpiId={KPI.load} latestIndex={latestIndex} />
            <MetricCard title="EAR" unit="%" kpiId={KPI.ear} latestIndex={latestIndex} />
            <MetricCard title="ENA" unit="MWmed" kpiId={KPI.ena} latestIndex={latestIndex} />
            <MetricCard title="CMO" unit="R$/MWh" kpiId={KPI.cmo} latestIndex={latestIndex} />
            <MetricCard title="PLD" unit="R$/MWh" kpiId={KPI.pld} latestIndex={latestIndex} />
          </div>

          <div className="grid gap-4 2xl:grid-cols-[1.1fr_0.9fr]">
            <VisualPanel title="Load Trend" subtitle="Last local observations by subsystem">
              <LineCompareChart values={series} kpiId={KPI.load} unit="MWmed" />
            </VisualPanel>
            <VisualPanel title="Generation Mix" subtitle="Latest measured generation shares">
              <GenerationMix latestIndex={latestIndex} />
            </VisualPanel>
          </div>

          <div className="grid gap-4 2xl:grid-cols-[1fr_1fr]">
            <VisualPanel title="Hydrology" subtitle="EAR (%) and ENA (MWmed)">
              <HydrologyPanel latestIndex={latestIndex} />
            </VisualPanel>
            <VisualPanel title="Price Signals" subtitle="CMO and PLD by subsystem">
              <PricePanel latestIndex={latestIndex} />
            </VisualPanel>
          </div>

          <SubsystemAuditTable latestIndex={latestIndex} dashboard={dashboard} />
          <SourcePanel dashboard={dashboard} />
        </>
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
    <div className="py-14 text-center">
      <p className="text-sm text-zinc-400">No local SIN subsystem KPI data is available yet.</p>
      <p className="mx-auto mt-2 max-w-xl text-xs text-zinc-500">
        Downloading runs only when requested. Existing cached data will be used offline after the first successful refresh.
      </p>
      <button
        type="button"
        onClick={onRefresh}
        disabled={disabled}
        className="mt-5 inline-flex items-center gap-2 rounded border border-zinc-600 bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
      >
        {disabled && <Spinner />}
        {refreshRunning ? "Refresh running" : isStarting ? "Starting refresh" : "Fetch SIN data"}
      </button>
    </div>
  );
}

function MetricCard({
  title,
  unit,
  kpiId,
  latestIndex,
}: {
  title: string;
  unit: string;
  kpiId: string;
  latestIndex: LatestIndex;
}) {
  const rows = SUBSYSTEMS.map((sub) => ({
    ...sub,
    value: latestIndex.get(key(kpiId, sub.code))?.value ?? null,
  }));
  const max = Math.max(...rows.map((row) => Math.abs(row.value ?? 0)), 1);
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950/40 p-3">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-400">{title}</span>
        <span className="font-mono text-[10px] text-zinc-600">{unit}</span>
      </div>
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.code} className="grid grid-cols-[42px_1fr_72px] items-center gap-2">
            <span className="font-mono text-[10px] text-zinc-500">{row.short}</span>
            <div className="h-1.5 overflow-hidden rounded-sm bg-zinc-900">
              <div
                className="h-full rounded-sm"
                style={{ width: `${Math.min(100, Math.abs(row.value ?? 0) / max * 100)}%`, background: row.color }}
              />
            </div>
            <span className="text-right font-mono text-[11px] text-zinc-200">{formatNumber(row.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function VisualPanel({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className="min-w-0 rounded border border-zinc-800 bg-zinc-950/35 p-4">
      <div className="mb-3">
        <h4 className="text-sm font-medium text-zinc-100">{title}</h4>
        <p className="text-[11px] text-zinc-500">{subtitle}</p>
      </div>
      {children}
    </section>
  );
}

function LineCompareChart({ values, kpiId, unit }: { values: SINKPIObservation[]; kpiId: string; unit: string }) {
  const series = useMemo(() => buildChartSeries(values, kpiId), [values, kpiId]);
  if (series.every((s) => s.points.length === 0)) {
    return <StateBanner variant="empty" title="No trend data" size="dense" />;
  }
  const allValues = series.flatMap((s) => s.points.map((p) => p.value));
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const span = Math.max(max - min, 1);
  const width = 640;
  const height = 220;
  const padX = 28;
  const padY = 18;

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[220px] w-full overflow-visible">
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
          const y = padY + tick * (height - padY * 2);
          return <line key={tick} x1={padX} x2={width - padX} y1={y} y2={y} stroke="rgba(255,255,255,0.06)" />;
        })}
        {series.map((s) => {
          const points = s.points.map((p, index) => {
            const x = padX + (index / Math.max(s.points.length - 1, 1)) * (width - padX * 2);
            const y = height - padY - ((p.value - min) / span) * (height - padY * 2);
            return `${x.toFixed(1)},${y.toFixed(1)}`;
          });
          return (
            <polyline
              key={s.code}
              points={points.join(" ")}
              fill="none"
              stroke={s.color}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap justify-between gap-2 text-[10px] text-zinc-500">
        <span className="font-mono">{formatNumber(min)} {unit}</span>
        <SubsystemLegend />
        <span className="font-mono">{formatNumber(max)} {unit}</span>
      </div>
    </div>
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
                  style={{ width: `${Math.max(0, part.value)}%`, background: part.color }}
                />
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

function HydrologyPanel({ latestIndex }: { latestIndex: LatestIndex }) {
  const enaMax = Math.max(...SUBSYSTEMS.map((sub) => latestIndex.get(key(KPI.ena, sub.code))?.value ?? 0), 1);
  return (
    <div className="space-y-3">
      {SUBSYSTEMS.map((sub) => {
        const ear = latestIndex.get(key(KPI.ear, sub.code))?.value ?? null;
        const ena = latestIndex.get(key(KPI.ena, sub.code))?.value ?? null;
        return (
          <div key={sub.code} className="grid grid-cols-[58px_1fr_92px] items-center gap-3">
            <span className="font-mono text-[11px] text-zinc-400">{sub.short}</span>
            <div className="space-y-1">
              <div className="h-2 rounded-sm bg-zinc-900">
                <div className="h-full rounded-sm bg-cyan-400" style={{ width: `${Math.max(0, Math.min(100, ear ?? 0))}%` }} />
              </div>
              <div className="h-2 rounded-sm bg-zinc-900">
                <div className="h-full rounded-sm bg-green-400" style={{ width: `${Math.max(0, (ena ?? 0) / enaMax * 100)}%` }} />
              </div>
            </div>
            <span className="text-right font-mono text-[11px] text-zinc-300">
              {formatNumber(ear)}% / {formatNumber(ena)}
            </span>
          </div>
        );
      })}
      <p className="text-[10px] text-zinc-500">Top bar: EAR (%). Bottom bar: ENA (MWmed), scaled to max subsystem.</p>
    </div>
  );
}

function PricePanel({ latestIndex }: { latestIndex: LatestIndex }) {
  const max = Math.max(
    ...SUBSYSTEMS.flatMap((sub) => [
      latestIndex.get(key(KPI.cmo, sub.code))?.value ?? 0,
      latestIndex.get(key(KPI.pld, sub.code))?.value ?? 0,
    ]),
    1,
  );
  return (
    <div className="space-y-3">
      {SUBSYSTEMS.map((sub) => {
        const cmo = latestIndex.get(key(KPI.cmo, sub.code))?.value ?? null;
        const pld = latestIndex.get(key(KPI.pld, sub.code))?.value ?? null;
        return (
          <div key={sub.code} className="grid grid-cols-[58px_1fr_92px] items-center gap-3">
            <span className="font-mono text-[11px] text-zinc-400">{sub.short}</span>
            <div className="grid grid-cols-2 gap-1.5">
              <div className="h-8 rounded-sm bg-zinc-900">
                <div className="h-full rounded-sm bg-orange-400" style={{ width: `${Math.max(0, (cmo ?? 0) / max * 100)}%` }} />
              </div>
              <div className="h-8 rounded-sm bg-zinc-900">
                <div className="h-full rounded-sm bg-purple-400" style={{ width: `${Math.max(0, (pld ?? 0) / max * 100)}%` }} />
              </div>
            </div>
            <span className="text-right font-mono text-[11px] text-zinc-300">
              {formatNumber(cmo)} / {formatNumber(pld)}
            </span>
          </div>
        );
      })}
      <p className="text-[10px] text-zinc-500">Orange: CMO. Purple: PLD. Values in R$/MWh.</p>
    </div>
  );
}

function SubsystemAuditTable({ latestIndex, dashboard }: { latestIndex: LatestIndex; dashboard: SINKPIDashboardResponse }) {
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
        <table className="min-w-[1040px] w-full border-collapse text-sm">
          <thead>
            <tr className="bg-zinc-900/80 text-left text-[10px] uppercase tracking-wider text-zinc-500">
              <th className="px-3 py-2 font-medium">Subsystem</th>
              <NumHead label="Load" unit="MWmed" />
              <NumHead label="Gen." unit="MWmed" />
              <NumHead label="Hydro" unit="MWmed" />
              <NumHead label="Thermal" unit="MWmed" />
              <NumHead label="Wind" unit="MWmed" />
              <NumHead label="Solar" unit="MWmed" />
              <NumHead label="EAR" unit="%" />
              <NumHead label="ENA" unit="MWmed" />
              <NumHead label="CMO" unit="R$/MWh" />
              <NumHead label="PLD" unit="R$/MWh" />
              <NumHead label="Interchange" unit="MWmed" />
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
                <NumCell value={latestIndex.get(key(KPI.load, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.generationTotal, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.hydro, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.thermal, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.wind, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.solar, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.ear, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.ena, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.cmo, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.pld, sub.code))?.value} />
                <NumCell value={latestIndex.get(key(KPI.interchange, sub.code))?.value} signed />
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

function SubsystemLegend() {
  return (
    <span className="flex flex-wrap gap-3">
      {SUBSYSTEMS.map((sub) => (
        <span key={sub.code} className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-sm" style={{ background: sub.color }} />
          {sub.short}
        </span>
      ))}
    </span>
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

function buildChartSeries(values: SINKPIObservation[], kpiId: string) {
  return SUBSYSTEMS.map((sub) => {
    const points = values
      .filter((row) => row.kpi_id === kpiId && row.subsystem_code === sub.code && row.value !== null)
      .sort((a, b) => a.reference_datetime.localeCompare(b.reference_datetime))
      .map((row) => ({ date: row.reference_datetime, value: row.value as number }));
    return { ...sub, points };
  });
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
