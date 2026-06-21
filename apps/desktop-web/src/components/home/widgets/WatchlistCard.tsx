import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchCompanyHistoricalIndicators } from "@/lib/api/companies";
import { Panel } from "@/components/surface/Panel";
import { Sparkline } from "@/components/data/Sparkline";
import { Button } from "@/components/ui/Button";
import { CompanySelector } from "./shared/CompanySelector";
import { downloadCsvFile } from "./shared/csvExport";
import { WatchlistConfig, WidgetCommonProps } from "./shared/widgetTypes";

interface WatchlistCardProps extends WidgetCommonProps {
  config?: WatchlistConfig;
  onConfigure: (newCfg: WatchlistConfig) => void;
}

export function WatchlistCard({
  config = { companyIds: [], metric: "mg_ebit" },
  onConfigure,
  onRemove,
  isCompact = false,
  isMinimized = false,
  isFocused = false,
  headerControls,
}: WatchlistCardProps) {
  const [isConfiguring, setIsConfiguring] = useState(false);

  const handleExportCSV = () => {
    if (!config.companyIds || config.companyIds.length === 0) return;
    const headers = ["Company Name", "CVM Code", "Ticker", "Metric"];
    const rows = config.companyIds.map((c) => [
      c.name,
      c.cdCvm,
      c.ticker || "",
      config.metric === "mg_ebit" ? "EBIT Margin" : "Stock Price",
    ]);
    downloadCsvFile({
      filename: "watchlist_companies.csv",
      headers,
      rows,
    });
  };

  const toggleMetric = () => {
    onConfigure({
      ...config,
      metric: config.metric === "mg_ebit" ? "stock_price" : "mg_ebit",
    });
  };

  const addCompany = (cdCvm: number, name: string, ticker: string) => {
    if (config.companyIds.some((c) => c.cdCvm === cdCvm)) return;
    onConfigure({
      ...config,
      companyIds: [...config.companyIds, { cdCvm, name, ticker }],
    });
  };

  const removeCompany = (cdCvm: number) => {
    onConfigure({
      ...config,
      companyIds: config.companyIds.filter((c) => c.cdCvm !== cdCvm),
    });
  };

  return (
    <Panel
      title="Watchlist & KPIs"
      subtitle={isMinimized ? undefined : config.metric === "mg_ebit" ? "EBIT Margin trend" : "Stock Price trend"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1.5">
          {!isMinimized && (
            <button
              onClick={toggleMetric}
              className="rounded border border-zinc-805 bg-zinc-950 px-1 py-0.5 text-3xs font-mono text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              {config.metric === "mg_ebit" ? "Prices" : "Margins"}
            </button>
          )}
          {!isMinimized && (
            <button
              onClick={() => setIsConfiguring(!isConfiguring)}
              className="text-zinc-550 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
              title="Configure watchlist"
            >
              ⚙
            </button>
          )}
          {isFocused && (
            <button
              onClick={handleExportCSV}
              className="text-orange-400 hover:text-orange-300 font-mono text-3xs border border-zinc-800 bg-zinc-900 rounded px-1.5 py-0.5 transition-colors mr-1"
              title="Export Watchlist to CSV"
            >
              ⬇ CSV
            </button>
          )}
          {headerControls}
          <button
            onClick={onRemove}
            className="text-zinc-550 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
            title="Remove Card"
          >
            ✕
          </button>
        </div>
      }
    >
      {!isMinimized && (
        <div
          className="space-y-3"
          style={{ flex: 1, minHeight: 0, overflow: "auto" }}
        >
          {isConfiguring && (
            <div className="border-b border-zinc-850 pb-3 space-y-2">
              <p className="text-2xs font-mono text-zinc-550 uppercase">Manage Watchlist</p>
              <CompanySelector onSelect={addCompany} />
              {config.companyIds.length > 0 && (
                <div className="max-h-24 overflow-y-auto space-y-1 pt-1 font-mono text-2xs">
                  {config.companyIds.map((c) => (
                    <div key={c.cdCvm} className="flex items-center justify-between bg-zinc-950/45 p-1 rounded border border-zinc-850">
                      <span className="truncate text-zinc-350 mr-2">{c.name} ({c.ticker || `CVM ${c.cdCvm}`})</span>
                      <button
                        onClick={() => removeCompany(c.cdCvm)}
                        className="text-red-400 hover:text-red-300 hover:underline"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <button
                onClick={() => setIsConfiguring(false)}
                className="w-full text-center py-1 text-2xs font-mono text-orange-400 hover:text-orange-300 underline"
              >
                Done configuring
              </button>
            </div>
          )}

          {config.companyIds.length === 0 ? (
            <div className={`${isCompact ? "py-3" : "py-6"} text-center space-y-2`}>
              <p className="text-xs font-mono text-zinc-550">Watchlist is empty.</p>
              {!isConfiguring && (
                <Button onClick={() => setIsConfiguring(true)} size="xs" variant="secondary">
                  Add Favorite Companies
                </Button>
              )}
            </div>
          ) : isFocused ? (
            <table className="w-full text-left font-mono text-xs border-collapse">
              <thead>
                <tr className="border-b border-zinc-850 text-zinc-650 text-3xs uppercase">
                  <th className="py-2">Company</th>
                  <th className="py-2">Ticker</th>
                  <th className="py-2">Latest Val</th>
                  <th className="py-2">Recent Years</th>
                  <th className="py-2 text-right">Trend</th>
                </tr>
              </thead>
              <tbody>
                {config.companyIds.map((c) => (
                  <WatchlistRow
                    key={c.cdCvm}
                    company={c}
                    metric={config.metric}
                    isCompact={isCompact}
                    isFocused={true}
                  />
                ))}
              </tbody>
            </table>
          ) : (
            <div className={isCompact ? "space-y-1.5" : "space-y-2.5"}>
              {config.companyIds.map((c) => (
                <WatchlistRow
                  key={c.cdCvm}
                  company={c}
                  metric={config.metric}
                  isCompact={isCompact}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function WatchlistRow({
  company,
  metric,
  isCompact,
  isFocused = false,
}: {
  company: { cdCvm: number; name: string; ticker: string };
  metric: "mg_ebit" | "stock_price";
  isCompact: boolean;
  isFocused?: boolean;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["company-historical-indicators", company.cdCvm],
    queryFn: () => fetchCompanyHistoricalIndicators(company.cdCvm),
  });

  const values = useMemo(() => {
    if (data?.mode !== "desktop" || !data.data?.yearly_data) return [];
    return data.data.yearly_data.map((y) => y[metric]);
  }, [data, metric]);

  const latestVal = useMemo(() => {
    const valid = values.filter((v): v is number => typeof v === "number" && !Number.isNaN(v));
    if (valid.length === 0) return null;
    return valid[valid.length - 1];
  }, [values]);

  const fmtVal = (val: number | null) => {
    if (val === null) return "—";
    if (metric === "mg_ebit") {
      return `${(val * 100).toFixed(1)}%`;
    }
    return `R$ ${val.toFixed(2)}`;
  };

  if (isFocused) {
    const years = data?.mode === "desktop" && data.data?.yearly_data ? data.data.yearly_data : [];
    return (
      <tr className="border-b border-zinc-850 hover:bg-zinc-900/35 text-xs font-mono text-zinc-300">
        <td className="py-2.5 pr-4 font-semibold text-zinc-200 max-w-[220px] truncate">
          <Link to={`/empresas/${company.cdCvm}`} className="hover:text-cyan-400 transition-colors">
            {company.name}
          </Link>
        </td>
        <td className="py-2.5 text-cyan-400">{company.ticker || `CVM ${company.cdCvm}`}</td>
        {isLoading ? (
          <td colSpan={3} className="py-2.5 text-3xs text-zinc-650">Loading...</td>
        ) : error || data?.mode === "browser" ? (
          <td colSpan={3} className="py-2.5 text-3xs text-zinc-650">Offline</td>
        ) : (
          <>
            <td className="py-2.5 font-medium text-emerald-400">{fmtVal(latestVal)}</td>
            <td className="py-2.5">
              <div className="flex flex-wrap gap-1.5">
                {years.slice(-4).map((y: any) => (
                  <span key={y.year} className="text-3xs bg-zinc-900/80 border border-zinc-850 rounded px-1 py-0.5">
                    {y.year}: <strong className="text-zinc-300">{fmtVal(y[metric])}</strong>
                  </span>
                ))}
              </div>
            </td>
            <td className="py-2.5 text-right">
              <div className="inline-flex bg-zinc-950/45 rounded border border-zinc-900 p-1">
                <Sparkline values={values} width={80} height={16} />
              </div>
            </td>
          </>
        )}
      </tr>
    );
  }

  return (
    <div className={`flex items-center justify-between border-b border-zinc-800/40 last:border-0 font-mono ${isCompact ? "pb-1.5" : "pb-2 last:pb-0"}`}>
      <div className="min-w-0 flex-1">
        <Link
          to={`/empresas/${company.cdCvm}`}
          className="block truncate text-xs font-medium text-zinc-200 hover:text-cyan-400 transition-colors"
          title={company.name}
        >
          {company.name}
        </Link>
        <span className="text-2xs text-zinc-550">{company.ticker || `CVM ${company.cdCvm}`}</span>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {isLoading ? (
          <span className="text-3xs text-zinc-650 font-sans">Loading...</span>
        ) : error || data?.mode === "browser" ? (
          <span className="text-3xs text-zinc-650">Offline</span>
        ) : (
          <>
            <div className="text-right">
              <span className="text-2xs text-zinc-400 font-semibold">
                {fmtVal(latestVal)}
              </span>
            </div>
            <Sparkline values={values} width={isCompact ? 50 : 60} height={14} />
          </>
        )}
      </div>
    </div>
  );
}
