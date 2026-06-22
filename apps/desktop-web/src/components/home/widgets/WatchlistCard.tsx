import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchCompanyHistoricalIndicators } from "@/lib/api/companies";
import { Panel } from "@/components/surface/Panel";
import { Sparkline } from "@/components/data/Sparkline";
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
      config.metric === "mg_ebit"
        ? "EBIT Margin"
        : config.metric === "mg_liq"
          ? "Net Margin"
          : config.metric === "roe"
            ? "ROE"
            : "Stock Price",
    ]);
    downloadCsvFile({
      filename: "watchlist_companies.csv",
      headers,
      rows,
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

  const metricLabel = useMemo(() => {
    switch (config.metric) {
      case "mg_ebit":
        return "EBIT Margin";
      case "mg_liq":
        return "Net Margin";
      case "roe":
        return "ROE";
      case "stock_price":
        return "Stock Price";
      default:
        return "Metric";
    }
  }, [config.metric]);

  return (
    <Panel
      title="Watchlist & KPIs"
      subtitle={isMinimized ? undefined : `Tracking annual ${metricLabel} trends`}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1.5">
          {!isMinimized && (
            <select
              value={config.metric}
              onChange={(e) => onConfigure({ ...config, metric: e.target.value as any })}
              className="rounded border border-zinc-800 bg-zinc-950 px-1 py-0.5 text-3xs font-mono text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer outline-none"
            >
              <option value="mg_ebit">EBIT Margin</option>
              <option value="mg_liq">Net Margin</option>
              <option value="roe">ROE</option>
              <option value="stock_price">Stock Price</option>
            </select>
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
            className="text-zinc-555 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
            title="Remove Card"
          >
            ✕
          </button>
        </div>
      }
    >
      {!isMinimized && (
        <div
          className="space-y-3 flex flex-col"
          style={{ flex: 1, minHeight: 0, overflow: isConfiguring ? "auto" : (config.companyIds.length === 0 ? "hidden" : "auto") }}
        >
          {isConfiguring ? (
            <div className="space-y-2 flex flex-col flex-1 min-h-0">
              <p className="text-2xs font-mono text-zinc-555 uppercase shrink-0">Manage Watchlist</p>
              <div className="shrink-0">
                <CompanySelector onSelect={addCompany} />
              </div>
              {config.companyIds.length > 0 && (
                <div className="flex-1 min-h-0 overflow-y-auto space-y-1 pt-1 font-mono text-2xs border-t border-zinc-900 mt-2">
                  {config.companyIds.map((c) => (
                    <div key={c.cdCvm} className="flex items-center justify-between bg-zinc-950/45 p-1 rounded border border-zinc-850">
                      <span className="truncate text-zinc-350 mr-2">{c.name} ({c.ticker || `CVM ${c.cdCvm}`})</span>
                      <button
                        onClick={() => removeCompany(c.cdCvm)}
                        className="text-red-400 hover:text-red-300 hover:underline shrink-0"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <button
                onClick={() => setIsConfiguring(false)}
                className="w-full text-center py-1 text-2xs font-mono text-orange-400 hover:text-orange-300 underline shrink-0 mt-2"
              >
                Done configuring
              </button>
            </div>
          ) : config.companyIds.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-3 py-3.5 border border-dashed border-zinc-850 rounded-md bg-zinc-900/5 text-center font-mono space-y-2 flex-1 min-h-0">
              <span className="text-zinc-500 text-sm">★</span>
              <div>
                <p className="text-2xs font-bold text-zinc-300">Watchlist is empty</p>
                <p className="text-3xs text-zinc-550 max-w-xs leading-normal mt-0.5">
                  Favorite companies to track annual KPIs (EBIT Margin, ROE, Prices) side-by-side.
                </p>
              </div>
              <button 
                onClick={() => setIsConfiguring(true)}
                className="rounded border border-zinc-800 hover:border-zinc-700 bg-zinc-950 px-2 py-1 text-3xs font-bold text-orange-400 hover:text-orange-300 transition-colors uppercase tracking-wider"
              >
                Add Favorite Companies
              </button>
            </div>
          ) : (
            <table className="w-full text-left font-mono text-xs border-collapse">
              <thead>
                <tr className="border-b border-zinc-850 text-zinc-650 text-3xs uppercase">
                  <th className="py-2">Company</th>
                  <th className="py-2">Ticker</th>
                  <th className="py-2">{metricLabel}</th>
                  <th className="py-2">YoY</th>
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
                  />
                ))}
              </tbody>
            </table>
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
}: {
  company: { cdCvm: number; name: string; ticker: string };
  metric: "mg_ebit" | "stock_price" | "roe" | "mg_liq";
  isCompact: boolean;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["company-historical-indicators", company.cdCvm],
    queryFn: () => fetchCompanyHistoricalIndicators(company.cdCvm),
  });

  const values = useMemo(() => {
    if (data?.mode !== "desktop" || !data.data?.yearly_data) return [];
    return data.data.yearly_data.map((y: any) => y[metric]);
  }, [data, metric]);

  const latestVal = useMemo(() => {
    const valid = values.filter((v): v is number => typeof v === "number" && !Number.isNaN(v));
    if (valid.length === 0) return null;
    return valid[valid.length - 1];
  }, [values]);

  const yoyChange = useMemo(() => {
    const valid = values.filter((v): v is number => typeof v === "number" && !Number.isNaN(v));
    if (valid.length < 2) return null;
    const latest = valid[valid.length - 1];
    const prev = valid[valid.length - 2];
    if (prev === null || prev === undefined || prev === 0) return null;
    
    if (metric === "stock_price") {
      return { val: ((latest - prev) / prev) * 100, type: "pct" };
    }
    return { val: latest - prev, type: "pp" };
  }, [values, metric]);

  const period = useMemo(() => {
    if (data?.mode !== "desktop" || !data.data?.yearly_data) return "—";
    const years = data.data.yearly_data.filter((y: any) => typeof y[metric] === "number");
    if (years.length === 0) return "—";
    return String(years[years.length - 1].year);
  }, [data, metric]);

  const fmtVal = (val: number | null) => {
    if (val === null || val === undefined || Number.isNaN(val)) return "—";
    if (metric === "stock_price") {
      return `R$ ${val.toFixed(2)}`;
    }
    return `${(val * 100).toFixed(1)}%`;
  };

  const renderYoY = (change: { val: number; type: string } | null) => {
    if (!change || Number.isNaN(change.val)) return <span className="text-zinc-650">—</span>;
    const sign = change.val > 0 ? "+" : "";
    const color = change.val > 0 ? "text-emerald-400" : change.val < 0 ? "text-red-400" : "text-zinc-550";
    const suffix = change.type === "pp" ? "pp" : "%";
    return (
      <span className={`text-[10px] font-bold ${color}`}>
        {sign}{change.val.toFixed(1)}{suffix}
      </span>
    );
  };

  return (
    <tr className="border-b border-zinc-850 hover:bg-zinc-900/35 text-xs font-mono text-zinc-300">
      <td className="py-2 pr-4 font-semibold text-zinc-200 max-w-[120px] md:max-w-[160px] truncate" title={company.name}>
        <Link to={`/empresas/${company.cdCvm}`} className="hover:text-cyan-400 transition-colors">
          {company.name}
        </Link>
      </td>
      <td className="py-2 text-cyan-400">{company.ticker || `CVM ${company.cdCvm}`}</td>
      {isLoading ? (
        <td colSpan={3} className="py-2 text-3xs text-zinc-600">Loading...</td>
      ) : error || data?.mode === "browser" ? (
        <td colSpan={3} className="py-2 text-[10px] text-zinc-650">Browser Mock</td>
      ) : (
        <>
          <td className="py-2 font-medium text-zinc-100">
            {fmtVal(latestVal)}
            <span className="text-[9px] text-zinc-555 ml-1">({period})</span>
          </td>
          <td className="py-2">{renderYoY(yoyChange)}</td>
          <td className="py-2 text-right">
            <div className="inline-flex bg-zinc-950/45 rounded border border-zinc-900 p-0.5">
              <Sparkline values={values} width={isCompact ? 40 : 50} height={12} />
            </div>
          </td>
        </>
      )}
    </tr>
  );
}
