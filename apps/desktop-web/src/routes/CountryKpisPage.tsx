/**
 * CountryKpisPage — top-level indicators module at /indicators.
 *
 * Macro scope:
 *   Matrix — stacked horizontal bar showing full electricity mix per country
 *   Trend  — line chart, one series per country, for a selected KPI over time
 *   SIN    — Brazilian subsystem operating KPIs
 *
 * Micro scope:
 *   Sector and company KPI coverage from the existing CVM bridge/read-service.
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient, useQueries } from "@tanstack/react-query";

import {
  MatrixView,
  TrendView,
  TREND_KPIS,
} from "@/components/indicators/CountryKpiCharts";
import { SINKpiPanel } from "@/components/indicators/SINKpiPanel";
import { IndicatorChart } from "@/components/indicators/IndicatorChart";
import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { fetchCompanies } from "@/lib/api/companies";
import {
  fetchCountryKPISeries,
  fetchEnergyKPIHealth,
  triggerEnergyKPIRefresh,
} from "@/lib/api/energyKpis";
import { fetchSectors, fetchSectorDetail } from "@/lib/api/sectors";
import { whenBridgeReady } from "@/lib/bridge/adapter";

const V1_ISO_CODES = ["BRA", "USA", "CHN", "OWEU", "CHL", "ARG"] as const;

type ViewMode = "matrix" | "trend";
type IndicatorScope = "macro" | "micro";
type MacroPane = "country" | "sin";

export function CountryKpisPage() {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [activeScope, setActiveScope] = useState<IndicatorScope>("macro");
  const [macroPane, setMacroPane] = useState<MacroPane>("country");
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
    enabled: bridgeReady && activeScope === "macro" && macroPane === "country",
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
      setTimeout(() => setStatusMsg(null), 8_000);
    } else {
      // Failures stay until dismissed or the next refresh, so they aren't missed.
      const err = (health as any)?.refresh_error ?? status ?? "unknown error";
      setStatusMsg({ text: `Refresh failed: ${String(err)}`, ok: false });
    }
  }, [health, isRefreshing, qc]);

  // Fetch ALL years + ALL countries + ALL KPIs in one call
  const seriesQuery = useQuery({
    queryKey: ["country-kpi-all"],
    queryFn: () => fetchCountryKPISeries({ iso_codes: [...V1_ISO_CODES] }),
    enabled: bridgeReady && activeScope === "macro" && macroPane === "country",
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
    }
  };

  const years = Array.from({ length: 12 }, (_, i) => new Date().getFullYear() - 1 - i);
  const breadcrumbs = [{ label: "Indicators" }];
  const isCountryMacro = activeScope === "macro" && macroPane === "country";

  return (
    <section className="min-w-0 max-w-full rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg space-y-5">
      <PageHeader
        title="Indicators"
        subtitle={
          activeScope === "macro"
            ? "Macroeconomic operating context: country energy KPIs and Brazilian SIN subsystem data."
            : "Microeconomic context: sector snapshots and company-level KPI coverage."
        }
        breadcrumbs={breadcrumbs}
        actions={isCountryMacro ? (
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="px-3 py-1.5 text-sm rounded border border-zinc-600 bg-zinc-800 hover:bg-zinc-700
                       text-zinc-200 disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {isRefreshing && <Spinner />}
            {isRefreshing ? "Updating…" : hasData ? "Update energy data" : "Fetch energy data"}
          </button>
        ) : null}
      />

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Indicator scope">
        <TopTab
          label="Macroeconomic"
          active={activeScope === "macro"}
          onClick={() => setActiveScope("macro")}
        />
        <TopTab
          label="Sector & Company"
          active={activeScope === "micro"}
          onClick={() => setActiveScope("micro")}
        />
      </div>

      {activeScope === "micro" ? (
        <MicroIndicatorsPanel bridgeReady={bridgeReady} />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-4 border-b border-zinc-800 pb-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-500 font-mono uppercase">Analysis Scope</span>
              <div className="flex rounded border border-zinc-700 overflow-hidden" role="tablist" aria-label="Analysis scope">
                <ViewTab
                  label="Country-Level Energy"
                  active={macroPane === "country"}
                  onClick={() => setMacroPane("country")}
                />
                <ViewTab
                  label="CCEE / SIN Subsystems"
                  active={macroPane === "sin"}
                  onClick={() => setMacroPane("sin")}
                />
              </div>
            </div>
            <p className="text-xs text-zinc-500">
              Macro indicators stay local-first: reads use cached SQLite data and refresh only on request.
            </p>
          </div>

          {/* View toggle + controls */}
          <div className="flex items-center gap-4 flex-wrap border-b border-zinc-800 pb-4">
            <div className="flex rounded border border-zinc-700 overflow-hidden" role="tablist" aria-label="View mode">
              <ViewTab
                label={macroPane === "sin" ? "Generation Mix" : "Electricity Matrix"}
                active={viewMode === "matrix"}
                onClick={() => setViewMode("matrix")}
              />
              <ViewTab
                label="Trend"
                active={viewMode === "trend"}
                onClick={() => setViewMode("trend")}
              />
            </div>

            {viewMode === "matrix" && macroPane === "country" && (
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

            {viewMode === "trend" && macroPane === "country" && (
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
              Source: {macroPane === "sin" ? "ONS / CCEE datasets" : "OWID energy dataset (CC-BY)"}
              {macroPane === "country" && health?.owid_fetched_at && ` · ${health.owid_fetched_at.slice(0, 10)}`}
            </p>
          </div>

          {macroPane === "sin" ? (
            <SINKpiPanel bridgeReady={bridgeReady} viewMode={viewMode} />
          ) : (
            <>
              {/* Status banners */}
              {health?.is_stale && !isRefreshing && (
                <StateBanner
                  variant="warning"
                  title="Data may be out of date"
                  message={`Last fetched ${health.owid_fetched_at?.slice(0, 10) ?? "unknown"}. Cached values are still shown — click Update to refresh.`}
                />
              )}
              {statusMsg && (
                <div className={`text-sm px-3 py-2 rounded border flex items-center gap-2 ${
                  statusMsg.ok
                    ? "border-zinc-700 bg-zinc-800/60 text-zinc-300"
                    : "border-red-800 bg-red-950/40 text-red-300"
                }`}>
                  {isRefreshing && <Spinner />}
                  <span className="min-w-0 flex-1">{statusMsg.text}</span>
                  {!statusMsg.ok && !isRefreshing && (
                    <button
                      type="button"
                      onClick={() => setStatusMsg(null)}
                      aria-label="Dismiss message"
                      className="ml-auto flex-shrink-0 rounded px-1.5 text-red-300/80 hover:text-red-200 hover:bg-red-900/40"
                    >
                      ✕
                    </button>
                  )}
                </div>
              )}

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
            </>
          )}
        </>
      )}
    </section>
  );
}

function TopTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? "bg-zinc-800 text-zinc-100"
          : "bg-transparent text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200"
      }`}
    >
      {label}
    </button>
  );
}

function ViewTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
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
    <StateBanner
      variant="empty"
      title="No country KPI data yet"
      message="Download the OWID energy dataset (~7 MB): electricity mix, demand, carbon intensity, and trade for Brazil, US, China, EU, Chile, and Argentina."
    >
      <button
        onClick={onRefresh}
        disabled={isRefreshing}
        className="mt-1 inline-flex items-center gap-2 self-start rounded border border-zinc-600 bg-zinc-800
                   px-4 py-2 text-sm text-zinc-200 transition-colors hover:bg-zinc-700 disabled:opacity-50"
      >
        {isRefreshing && <Spinner />}
        {isRefreshing ? "Downloading…" : "Fetch energy data"}
      </button>
    </StateBanner>
  );
}

function MicroIndicatorsPanel({ bridgeReady }: { bridgeReady: boolean }) {
  const [microViewMode, setMicroViewMode] = useState<"overview" | "trend">("overview");
  const [microTrendKpi, setMicroTrendKpi] = useState<"roe" | "mg_ebit" | "mg_liq">("roe");
  const [selectedSectors, setSelectedSectors] = useState<string[]>([]);

  const sectorsQuery = useQuery({
    queryKey: ["micro-indicators-sectors"],
    queryFn: () => fetchSectors("sector"),
    enabled: bridgeReady,
    staleTime: 60_000,
  });
  const companiesQuery = useQuery({
    queryKey: ["micro-indicators-companies"],
    queryFn: () => fetchCompanies({ page: 1, page_size: 8 }),
    enabled: bridgeReady,
    staleTime: 60_000,
  });

  const sectors = sectorsQuery.data?.mode === "desktop" ? sectorsQuery.data.items : [];

  // Default selection to first 3 sectors
  useEffect(() => {
    if (sectors.length > 0 && selectedSectors.length === 0) {
      setSelectedSectors(sectors.slice(0, 3).map((s) => s.sector_slug));
    }
  }, [sectors, selectedSectors]);

  // Fetch details in parallel using useQueries for all selected sectors
  const sectorsDetails = useQueries({
    queries: selectedSectors.map((slug) => ({
      queryKey: ["micro-indicators-sector-detail", slug],
      queryFn: () => fetchSectorDetail(slug),
      enabled: bridgeReady && microViewMode === "trend",
      staleTime: 60_000,
    })),
  });

  if (!bridgeReady || sectorsQuery.isLoading || companiesQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading sector and company indicators..." />;
  }
  if (sectorsQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" message={sectorsQuery.data.reason} />;
  }
  if (companiesQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" message={companiesQuery.data.reason} />;
  }
  if (sectorsQuery.isError || companiesQuery.isError) {
    const error = sectorsQuery.error ?? companiesQuery.error;
    return (
      <StateBanner
        variant="error"
        title="Could not load microeconomic indicators"
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  const page = companiesQuery.data?.mode === "desktop" ? companiesQuery.data.page : null;
  const companies = page?.items ?? [];
  const completeCompanies = companies.filter((c) => c.data_status === "complete").length;
  const totalCompanies = page?.pagination.total_items ?? companies.length;
  const latestYear = Math.max(
    0,
    ...sectors.map((sector) => sector.latest_year ?? 0),
    ...companies.flatMap((company) => company.anos_disponiveis ?? []),
  );

  if (sectors.length === 0 && companies.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No sector or company indicators yet"
        message="Run the local database update first, then return here to review sector snapshots and company KPI coverage."
      />
    );
  }

  // --- Trend view computing ---
  // 1. Gather all years available across selected sector details
  const allYears = (() => {
    const yearsSet = new Set<number>();
    sectorsDetails.forEach((q) => {
      const detail = q.data?.mode === "desktop" ? q.data.detail : null;
      if (detail?.yearly_overview) {
        detail.yearly_overview.forEach((y) => {
          if (y.year) yearsSet.add(y.year);
        });
      }
    });
    return [...yearsSet].sort((a, b) => a - b);
  })();

  const periods = allYears.map(String);

  // 2. Build ResolvedSeries list
  const chartSeries = selectedSectors.map((slug, idx) => {
    const sector = sectors.find((s) => s.sector_slug === slug);
    const label = sector?.sector_name ?? slug;
    
    const detailQuery = sectorsDetails[idx];
    const detail = detailQuery?.data?.mode === "desktop" ? detailQuery.data.detail : null;

    const valueByYear = new Map<number, number>();
    if (detail?.yearly_overview) {
      detail.yearly_overview.forEach((y) => {
        const val = y[microTrendKpi];
        if (val !== null && val !== undefined) {
          valueByYear.set(y.year, val);
        }
      });
    }

    const points = allYears.map((yr) => {
      const v = valueByYear.get(yr);
      // IndicatorChart expects values divided by 100 for 'pct' formatting
      return v !== null && v !== undefined ? v / 100 : null;
    });

    const colors = ["#60A5FA", "#4ADE80", "#FBBF24", "#F87171", "#C084FC", "#F472B6", "#FB923C", "#22D3EE"];
    const color = colors[idx % colors.length];

    return {
      id: slug,
      label,
      unit: "pct" as const,
      color,
      type: "line" as const,
      axis: "left" as const,
      points,
      latest: points.length > 0 ? points[points.length - 1] : null,
    };
  });

  return (
    <div className="min-w-0 space-y-5">
      {/* View Toggle */}
      <div className="flex items-center gap-4 flex-wrap border-b border-zinc-800 pb-4">
        <div className="flex rounded border border-zinc-700 overflow-hidden" role="tablist" aria-label="View mode">
          <ViewTab
            label="Overview"
            active={microViewMode === "overview"}
            onClick={() => setMicroViewMode("overview")}
          />
          <ViewTab
            label="Trend"
            active={microViewMode === "trend"}
            onClick={() => setMicroViewMode("trend")}
          />
        </div>
        <p className="ml-auto text-xs text-zinc-500">
          Source: CVM local database
        </p>
      </div>

      {microViewMode === "overview" ? (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-4">
            <MicroSummaryCard label="Sectors" value={sectors.length.toLocaleString("en-US")} />
            <MicroSummaryCard label="Companies" value={totalCompanies.toLocaleString("en-US")} />
            <MicroSummaryCard label="Loaded sample" value={`${completeCompanies}/${companies.length}`} />
            <MicroSummaryCard label="Latest year" value={latestYear > 0 ? String(latestYear) : "-"} />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <section className="min-w-0 rounded border border-zinc-800 bg-zinc-950/35">
              <div className="border-b border-zinc-800 px-4 py-3">
                <h3 className="text-sm font-medium text-zinc-100">Sector KPI Snapshot</h3>
                <p className="text-[11px] text-zinc-500">Microeconomic indicators grouped by sector from the local CVM database.</p>
              </div>
              <div className="max-w-full overflow-x-auto">
                <table className="min-w-[620px] w-full border-collapse text-sm">
                  <thead>
                    <tr className="bg-zinc-900/80 text-left text-[10px] uppercase tracking-wider text-zinc-500">
                      <th className="px-3 py-2 font-medium">Sector</th>
                      <th className="px-3 py-2 text-right font-medium">Companies</th>
                      <th className="px-3 py-2 text-right font-medium">Latest</th>
                      <th className="px-3 py-2 text-right font-medium">ROE</th>
                      <th className="px-3 py-2 text-right font-medium">EBIT Margin</th>
                      <th className="px-3 py-2 text-right font-medium">Net Margin</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/80">
                    {sectors.map((sector) => (
                      <tr key={sector.sector_slug} className="hover:bg-zinc-900/50">
                        <td className="px-3 py-2">
                          <Link
                            to={`/setores/${sector.sector_slug}`}
                            className="text-zinc-100 hover:text-cyan-400 hover:underline"
                          >
                            {sector.sector_name}
                          </Link>
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-[11px] text-zinc-300">{sector.company_count}</td>
                        <td className="px-3 py-2 text-right font-mono text-[11px] text-zinc-400">{sector.latest_year ?? "-"}</td>
                        <td className="px-3 py-2 text-right font-mono text-[11px] text-zinc-300">{formatPct(sector.snapshot?.roe)}</td>
                        <td className="px-3 py-2 text-right font-mono text-[11px] text-zinc-300">{formatPct(sector.snapshot?.mg_ebit)}</td>
                        <td className="px-3 py-2 text-right font-mono text-[11px] text-zinc-300">{formatPct(sector.snapshot?.mg_liq)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="min-w-0 rounded border border-zinc-800 bg-zinc-950/35">
              <div className="border-b border-zinc-800 px-4 py-3">
                <h3 className="text-sm font-medium text-zinc-100">Company KPI Coverage</h3>
                <p className="text-[11px] text-zinc-500">Representative companies and local statement/KPI availability.</p>
              </div>
              <div className="divide-y divide-zinc-800/80">
                {companies.map((company) => (
                  <Link
                    key={company.cd_cvm}
                    to={`/empresas/${company.cd_cvm}`}
                    className="grid grid-cols-[1fr_auto] gap-3 px-4 py-3 transition-colors hover:bg-zinc-900/50"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-zinc-100">{company.company_name}</p>
                      <p className="mt-0.5 font-mono text-[10px] text-zinc-500">
                        {company.ticker_b3 ?? "no ticker"} · CVM {company.cd_cvm} · {company.sector_name}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className={`rounded border px-2 py-0.5 text-[10px] ${statusClass(company.data_status)}`}>
                        {company.data_status ?? "unknown"}
                      </span>
                      <p className="mt-1 font-mono text-[10px] text-zinc-500">
                        {company.anos_disponiveis?.length ?? 0} years · {company.total_rows.toLocaleString("en-US")} rows
                      </p>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Controls */}
          <div className="flex items-center gap-4 flex-wrap bg-zinc-950/20 border border-zinc-800 rounded p-4">
            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-400">Indicator</label>
              <select
                value={microTrendKpi}
                onChange={(e) => setMicroTrendKpi(e.target.value as any)}
                className="text-sm bg-zinc-800 border border-zinc-700 rounded px-2.5 py-1.5 text-zinc-200 focus:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-600"
              >
                <option value="roe">Return on Equity (ROE)</option>
                <option value="mg_ebit">EBIT Margin</option>
                <option value="mg_liq">Net Margin</option>
              </select>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-2 items-center">
              <label className="text-xs text-zinc-400">Sectors:</label>
              {sectors.map((s) => {
                const checked = selectedSectors.includes(s.sector_slug);
                return (
                  <label key={s.sector_slug} className="flex items-center gap-1.5 text-xs text-zinc-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {
                        if (checked) {
                          setSelectedSectors(selectedSectors.filter((x) => x !== s.sector_slug));
                        } else {
                          setSelectedSectors([...selectedSectors, s.sector_slug]);
                        }
                      }}
                      className="rounded bg-zinc-800 border-zinc-700 text-amber-500 focus:ring-amber-500 focus:ring-offset-zinc-900"
                    />
                    {s.sector_name}
                  </label>
                );
              })}
            </div>
          </div>

          {/* Chart */}
          {chartSeries.length === 0 || periods.length === 0 ? (
            <StateBanner
              variant="empty"
              title="Nothing to plot"
              message="Select at least one sector to display its trend."
            />
          ) : (
            <div className="rounded border border-zinc-800 bg-zinc-950/35 p-4">
              <IndicatorChart
                series={chartSeries}
                periods={periods}
                config={{
                  type: "line",
                  grid: true,
                  smooth: true,
                  markers: true,
                  legend: true,
                  dataLabels: false,
                  indexMode: false,
                }}
                height={320}
              />
            </div>
          )}

          {/* Audit Table */}
          {chartSeries.length > 0 && periods.length > 0 && (
            <section className="min-w-0 max-w-full rounded border border-zinc-800 bg-zinc-950/35">
              <div className="border-b border-zinc-800 px-4 py-3">
                <h4 className="text-sm font-medium text-zinc-100">Audit Table</h4>
                <p className="text-[11px] text-zinc-500">
                  Historical {microTrendKpi.toUpperCase()} values by sector (%).
                </p>
              </div>
              <div className="min-w-0 max-w-full overflow-x-auto">
                <table className="min-w-[620px] w-full border-collapse text-sm">
                  <thead>
                    <tr className="bg-zinc-900/80 text-left text-[10px] uppercase tracking-wider text-zinc-500">
                      <th className="px-3 py-2 font-medium">Sector</th>
                      {periods.map((year) => (
                        <th key={year} className="px-3 py-2 text-right font-medium">{year}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/80 text-zinc-200">
                    {selectedSectors.map((slug, idx) => {
                      const sector = sectors.find((s) => s.sector_slug === slug);
                      const detailQuery = sectorsDetails[idx];
                      const detail = detailQuery?.data?.mode === "desktop" ? detailQuery.data.detail : null;

                      const valueByYear = new Map<number, number>();
                      if (detail?.yearly_overview) {
                        detail.yearly_overview.forEach((y) => {
                          const val = y[microTrendKpi];
                          if (val !== null && val !== undefined) {
                            valueByYear.set(y.year, val);
                          }
                        });
                      }

                      return (
                        <tr key={slug} className="hover:bg-zinc-900/50">
                          <td className="px-3 py-2 font-medium text-zinc-100">
                            {sector?.sector_name ?? slug}
                          </td>
                          {allYears.map((yr) => {
                            const val = valueByYear.get(yr);
                            return (
                              <td key={yr} className="px-3 py-2 text-right font-mono text-[11px] text-zinc-300">
                                {formatPct(val)}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function MicroSummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950/40 p-3">
      <p className="text-[10px] uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 font-mono text-xl text-zinc-100">{value}</p>
    </div>
  );
}

function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${value.toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
}

function statusClass(status: string | undefined): string {
  if (status === "complete") return "border-green-800 bg-green-950/30 text-green-300";
  if (status === "partial") return "border-amber-800 bg-amber-950/30 text-amber-300";
  if (status === "failed") return "border-red-800 bg-red-950/30 text-red-300";
  return "border-zinc-700 bg-zinc-900 text-zinc-400";
}
