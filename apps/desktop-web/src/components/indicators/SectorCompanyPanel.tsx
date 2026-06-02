/**
 * SectorCompanyPanel — microeconomic indicator coverage (sector snapshots +
 * company KPI availability), read from the existing CVM local database via the
 * bridge. Extracted verbatim from the former CountryKpisPage "Sector & Company"
 * tab so the Indicator Explorer can host it as a secondary view without owning
 * a new data layer. This is the UI organisation point for sector/company
 * indicators already owned by the CVM read-service / KPI engine.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueries } from "@tanstack/react-query";

import { IndicatorChart } from "@/components/indicators/IndicatorChart";
import { StateBanner } from "@/components/feedback/StateBanner";
import { fetchCompanies } from "@/lib/api/companies";
import { fetchSectors, fetchSectorDetail } from "@/lib/api/sectors";

export function SectorCompanyPanel({ bridgeReady }: { bridgeReady: boolean }) {
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
                onChange={(e) => setMicroTrendKpi(e.target.value as "roe" | "mg_ebit" | "mg_liq")}
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
