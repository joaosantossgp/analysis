import { useEffect, useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

// API imports
import {
  defaultRefreshWindow,
  fetchBaseHealth,
  fetchDatabaseDiagnostics,
  fetchRefreshJobs,
  isActiveRefreshJob,
} from "@/lib/api/updateBase";
import {
  fetchCompanies,
  fetchCompanyHistoricalIndicators,
} from "@/lib/api/companies";
import {
  fetchCoverageUniverses,
  fetchCoveragePriorityScores,
} from "@/lib/api/coverage";
import { fetchNewsArticles } from "@/lib/api/news";
import { fetchMarketHistory } from "@/lib/api/marketHistory";

// UI imports
import { Panel } from "@/components/surface/Panel";
import { Sparkline } from "@/components/data/Sparkline";
import { Button } from "@/components/ui/Button";

// ─── Company Selector Helper ──────────────────────────────────────────────────

function CompanySelector({
  onSelect,
  placeholder = "Search company by name or ticker...",
}: {
  onSelect: (cdCvm: number, name: string, ticker: string) => void;
  placeholder?: string;
}) {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ["companies-search", debouncedSearch],
    queryFn: () => fetchCompanies({ search: debouncedSearch, page_size: 6 }),
    enabled: debouncedSearch.length >= 2,
  });

  const list = data?.mode === "desktop" ? data.page.items : [];

  return (
    <div className="relative w-full space-y-1">
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 py-1.5 font-mono text-xs text-zinc-100 placeholder-zinc-600 focus:border-orange-500 focus:outline-none"
      />
      {isLoading && (
        <p className="px-2 text-2xs text-zinc-500 font-mono">Searching database...</p>
      )}
      {!isLoading && debouncedSearch.length >= 2 && list.length === 0 && (
        <p className="px-2 text-2xs text-zinc-500 font-mono">No matching companies found.</p>
      )}
      {list.length > 0 && (
        <div className="absolute left-0 right-0 z-50 mt-1 max-h-48 overflow-y-auto rounded-md border border-zinc-800 bg-zinc-950 p-1 shadow-xl">
          {list.map((c) => (
            <button
              key={c.cd_cvm}
              onClick={() => {
                onSelect(c.cd_cvm, c.company_name, c.ticker_b3 || "");
                setSearch("");
                setDebouncedSearch("");
              }}
              className="flex w-full items-center justify-between rounded-sm px-2 py-1 text-left font-mono text-xs hover:bg-zinc-800 text-zinc-200 hover:text-white"
            >
              <span className="truncate mr-2 text-left">{c.company_name}</span>
              <span className="shrink-0 text-2xs text-cyan-400">
                {c.ticker_b3 || `CVM ${c.cd_cvm}`}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── 1. Database Status Card ──────────────────────────────────────────────────

function DatabaseStatusCard({
  onRemove,
  isCompact = false,
  isMinimized = false,
  headerControls,
}: {
  onRemove: () => void;
  isCompact?: boolean;
  isMinimized?: boolean;
  headerControls?: React.ReactNode;
}) {
  const defaults = useMemo(() => defaultRefreshWindow(), []);
  const jobsQuery = useQuery({
    queryKey: ["refresh-jobs"],
    queryFn: fetchRefreshJobs,
    refetchInterval: 10_000,
  });
  const jobs = jobsQuery.data?.mode === "desktop" ? jobsQuery.data.items : [];
  const activeJob = jobs.find(isActiveRefreshJob) ?? null;
  const isRunning = Boolean(activeJob);

  const healthQuery = useQuery({
    queryKey: ["base-health", defaults.startYear, defaults.endYear],
    queryFn: () =>
      fetchBaseHealth({
        startYear: defaults.startYear,
        endYear: defaults.endYear,
        forceRefresh: false,
      }),
    refetchInterval: isRunning ? 5_000 : false,
  });
  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.snapshot : null;

  const diagQuery = useQuery({
    queryKey: ["db-diagnostics"],
    queryFn: () => fetchDatabaseDiagnostics({ summaryOnly: true }),
    refetchInterval: isRunning ? 5_000 : 30_000,
  });
  const diag = diagQuery.data?.mode === "desktop" ? diagQuery.data.diagnostics : null;

  const pct = health ? health.pct : 0;
  const tone = pct > 80 ? "good" : pct > 0 ? "warn" : "neutral";
  const toneClass =
    tone === "good"
      ? "text-emerald-400"
      : tone === "warn"
        ? "text-amber-400"
        : "text-zinc-400";

  return (
    <Panel
      title="Database Monitor"
      subtitle={isMinimized ? undefined : "Local synchronization status"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1">
          {headerControls}
          <button
            onClick={onRemove}
            className="text-zinc-500 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
            title="Remove Card"
          >
            ✕
          </button>
        </div>
      }
    >
      {!isMinimized && (
        <div
          className={`font-mono ${isCompact ? "space-y-1.5" : "space-y-3"}`}
          style={{ flex: 1, minHeight: 0, overflow: "auto" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-zinc-500 text-xs">STATUS</span>
            <span className={`text-xs font-semibold ${toneClass}`}>
              {isRunning ? "UPDATING..." : pct > 80 ? "UP TO DATE" : "OUT OF DATE"}
            </span>
          </div>

          <div className={`grid grid-cols-2 gap-4 border-y border-zinc-850 ${isCompact ? "py-1.5" : "py-3"}`}>
            <div>
              <p className="text-2xs text-zinc-500">COVERAGE</p>
              <p className={`${isCompact ? "text-sm" : "text-lg"} font-semibold text-zinc-200`}>
                {health ? `${pct.toFixed(1)}%` : "—"}
              </p>
            </div>
            <div>
              <p className="text-2xs text-zinc-500">COMPANIES</p>
              <p className={`${isCompact ? "text-sm" : "text-lg"} font-semibold text-zinc-200`}>
                {health ? health.total_companies : "—"}
              </p>
            </div>
          </div>

          <div className="text-2xs text-zinc-500 space-y-0.5">
            <p>
              Last update:{" "}
              <span className="text-zinc-300">
                {diag?.latest_success_at
                  ? new Date(diag.latest_success_at).toLocaleString("en-US", {
                      dateStyle: "short",
                      timeStyle: "short",
                    })
                  : "Never"}
              </span>
            </p>
            <p>
              Pending Gaps:{" "}
              <span className="text-zinc-300">
                {health ? health.missing_cells : "—"}
              </span>
            </p>
          </div>

          <div className={isCompact ? "pt-1" : "pt-2"}>
            <Link
              to="/settings/updates"
              className="flex w-full items-center justify-center rounded bg-zinc-900 border border-zinc-800 hover:bg-zinc-800 text-center text-xs text-zinc-300 py-1 transition-colors"
            >
              {isRunning ? "View active job →" : "Manage updates →"}
            </Link>
          </div>
        </div>
      )}
    </Panel>
  );
}

// ─── 2. Watchlist / Pinned Companies Card ─────────────────────────────────────

type WatchlistConfig = {
  companyIds: Array<{ cdCvm: number; name: string; ticker: string }>;
  metric: "mg_ebit" | "stock_price";
};

function WatchlistCard({
  config = { companyIds: [], metric: "mg_ebit" },
  onConfigure,
  onRemove,
  isCompact = false,
  isMinimized = false,
  isFocused = false,
  headerControls,
}: {
  config?: WatchlistConfig;
  onConfigure: (newCfg: WatchlistConfig) => void;
  onRemove: () => void;
  isCompact?: boolean;
  isMinimized?: boolean;
  isFocused?: boolean;
  headerControls?: React.ReactNode;
}) {
  const [isConfiguring, setIsConfiguring] = useState(false);

  const handleExportCSV = () => {
    if (!config.companyIds || config.companyIds.length === 0) return;
    const headers = ["Company Name", "CVM Code", "Ticker", "Metric"];
    const rows = config.companyIds.map((c) => [
      c.name.replace(/"/g, '""'),
      c.cdCvm,
      c.ticker || "",
      config.metric === "mg_ebit" ? "EBIT Margin" : "Stock Price"
    ]);
    const csvContent = [
      headers.join(","),
      ...rows.map((row) => row.map((val) => `"${val}"`).join(","))
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "watchlist_companies.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
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
              className="rounded border border-zinc-800 bg-zinc-900 px-1 py-0.5 text-3xs font-mono text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              {config.metric === "mg_ebit" ? "Prices" : "Margins"}
            </button>
          )}
          {!isMinimized && (
            <button
              onClick={() => setIsConfiguring(!isConfiguring)}
              className="text-zinc-500 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
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
            className="text-zinc-500 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
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
            <div className="border-b border-zinc-800/80 pb-3 space-y-2">
              <p className="text-2xs font-mono text-zinc-500 uppercase">Manage Watchlist</p>
              <CompanySelector onSelect={addCompany} />
              {config.companyIds.length > 0 && (
                <div className="max-h-24 overflow-y-auto space-y-1 pt-1 font-mono text-2xs">
                  {config.companyIds.map((c) => (
                    <div key={c.cdCvm} className="flex items-center justify-between bg-zinc-900/45 p-1 rounded border border-zinc-850">
                      <span className="truncate text-zinc-300 mr-2">{c.name} ({c.ticker || `CVM ${c.cdCvm}`})</span>
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
              <p className="text-xs font-mono text-zinc-500">Watchlist is empty.</p>
              {!isConfiguring && (
                <Button onClick={() => setIsConfiguring(true)} size="xs" variant="secondary">
                  Add Favorite Companies
                </Button>
              )}
            </div>
          ) : isFocused ? (
            <table className="w-full text-left font-mono text-xs border-collapse">
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-555 text-3xs uppercase">
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
      <tr className="border-b border-zinc-850/80 hover:bg-zinc-900/35 text-xs font-mono text-zinc-300">
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
        <span className="text-2xs text-zinc-500">{company.ticker || `CVM ${company.cdCvm}`}</span>
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

// ─── 3. Active Universe Priority Queue Card ───────────────────────────────────

type PriorityQueueConfig = {
  universeId: string;
};

function PriorityQueueCard({
  config = { universeId: "" },
  onConfigure,
  onRemove,
  isCompact = false,
  isMinimized = false,
  isFocused = false,
  headerControls,
}: {
  config?: PriorityQueueConfig;
  onConfigure: (newCfg: PriorityQueueConfig) => void;
  onRemove: () => void;
  isCompact?: boolean;
  isMinimized?: boolean;
  isFocused?: boolean;
  headerControls?: React.ReactNode;
}) {
  const [isConfiguring, setIsConfiguring] = useState(false);

  const universesQuery = useQuery({
    queryKey: ["coverage-universes"],
    queryFn: fetchCoverageUniverses,
  });
  const universes = universesQuery.data || [];

  const activeUniverse = universes.find((u) => u.id === config.universeId) || null;

  const priorityQuery = useQuery({
    queryKey: ["priority-scores", config.universeId],
    queryFn: () => fetchCoveragePriorityScores(config.universeId),
    enabled: Boolean(config.universeId),
  });
  const priorities = priorityQuery.data || [];

  // Sort by priority score (high to low)
  const topPriorities = useMemo(() => {
    return [...priorities]
      .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))
      .slice(0, isFocused ? 25 : isCompact ? 5 : 8);
  }, [priorities, isCompact, isFocused]);

  const selectUniverse = (id: string) => {
    onConfigure({ universeId: id });
    setIsConfiguring(false);
  };

  const handleExportCSV = () => {
    if (!priorities || priorities.length === 0) return;
    const headers = ["Company Name", "CVM Code", "Tier", "Priority Score"];
    const rows = priorities.map((item) => [
      item.company_name.replace(/"/g, '""'),
      item.cd_cvm,
      item.tier || "—",
      item.priority_score ?? 0
    ]);
    const csvContent = [
      headers.join(","),
      ...rows.map((row) => row.map((val) => `"${val}"`).join(","))
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `priority_queue_${config.universeId || "all"}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <Panel
      title="Priority Queue"
      subtitle={isMinimized ? undefined : activeUniverse ? `Universe: ${activeUniverse.name}` : "Identify coverage gaps"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1.5">
          {!isMinimized && (
            <button
              onClick={() => setIsConfiguring(!isConfiguring)}
              className="text-zinc-500 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
              title="Configure Universe"
            >
              ⚙
            </button>
          )}
          {isFocused && (
            <button
              onClick={handleExportCSV}
              className="text-orange-400 hover:text-orange-300 font-mono text-3xs border border-zinc-800 bg-zinc-900 rounded px-1.5 py-0.5 transition-colors mr-1"
              title="Export Queue to CSV"
            >
              ⬇ CSV
            </button>
          )}
          {headerControls}
          <button
            onClick={onRemove}
            className="text-zinc-500 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
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
            <div className="border-b border-zinc-800 pb-3 space-y-2">
              <p className="text-2xs font-mono text-zinc-500 uppercase">Select Coverage Universe</p>
              {universes.length === 0 ? (
                <p className="text-2xs font-mono text-zinc-650">No universes available.</p>
              ) : (
                <div className="max-h-28 overflow-y-auto space-y-1 font-mono text-2xs">
                  {universes.map((u) => (
                    <button
                      key={u.id}
                      onClick={() => selectUniverse(u.id)}
                      className="w-full text-left p-1 rounded hover:bg-zinc-800 text-zinc-300 hover:text-white"
                    >
                      {u.name} ({u.company_count} cos)
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {!config.universeId ? (
            <div className={`${isCompact ? "py-3" : "py-6"} text-center space-y-2`}>
              <p className="text-xs font-mono text-zinc-500">No universe selected.</p>
              {!isConfiguring && (
                <Button onClick={() => setIsConfiguring(true)} size="xs" variant="secondary">
                  Select Universe
                </Button>
              )}
            </div>
          ) : priorityQuery.isLoading ? (
            <p className="py-4 text-center font-mono text-2xs text-zinc-600">Loading priority rankings...</p>
          ) : topPriorities.length === 0 ? (
            <p className="py-4 text-center font-mono text-2xs text-zinc-500">No priority tasks available in this universe.</p>
          ) : (
            <div className="space-y-1.5 font-mono text-xs">
              <div className="flex items-center justify-between border-b border-zinc-900 pb-1 text-3xs text-zinc-500 uppercase">
                <span>Company</span>
                <div className="flex gap-4">
                  <span>Tier</span>
                  <span className="w-10 text-right">Score</span>
                </div>
              </div>
              {topPriorities.map((item) => (
                <div key={item.cd_cvm} className="flex items-center justify-between border-b border-zinc-900/60 py-1.5 last:border-0">
                  <Link
                    to={`/empresas/${item.cd_cvm}`}
                    className="truncate text-zinc-300 hover:text-cyan-400 transition-colors mr-2 max-w-44"
                    title={item.company_name}
                  >
                    {item.company_name}
                  </Link>
                  <div className="flex items-center gap-4 shrink-0 text-2xs">
                    <span className="text-zinc-500 font-semibold">{item.tier}</span>
                    <span className="w-10 text-right text-orange-400 font-bold">
                      {item.priority_score ?? 0}
                    </span>
                  </div>
                </div>
              ))}
              {!isCompact && (
                <div className="pt-2 text-center border-t border-zinc-900/60">
                  <Link
                    to="/coverage/prioritization"
                    className="text-2xs text-cyan-400 hover:text-cyan-300 hover:underline"
                  >
                    Go to full prioritization queue →
                  </Link>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

// ─── 4. Top News Card ─────────────────────────────────────────────────────────

function TopNewsCard({
  onRemove,
  isCompact = false,
  isMinimized = false,
  isFocused = false,
  headerControls,
}: {
  onRemove: () => void;
  isCompact?: boolean;
  isMinimized?: boolean;
  isFocused?: boolean;
  headerControls?: React.ReactNode;
}) {
  const limitCount = isFocused ? 20 : isCompact ? 5 : 10;
  const { data, isLoading, error } = useQuery({
    queryKey: ["news-latest", limitCount],
    queryFn: () => fetchNewsArticles({ limit: limitCount }),
    refetchInterval: 60_000,
  });

  const mode = data?.mode;
  const isOffline = mode === "browser" || error;

  const items = data?.mode === "desktop" || data?.mode === "dev-http" ? data.items : [];

  const handleExportCSV = () => {
    if (!items || items.length === 0) return;
    const headers = ["Source", "Published At", "Title", "URL"];
    const rows = items.map((item) => [
      item.source_name || "CVM Filings",
      item.published_at || "",
      item.title.replace(/"/g, '""'),
      item.original_url || ""
    ]);
    const csvContent = [
      headers.join(","),
      ...rows.map((row) => row.map((val) => `"${val}"`).join(","))
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "top_news_feed.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <Panel
      title="Top News Feed"
      subtitle={isMinimized ? undefined : "Aggregated filings and market alerts"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1">
          {isFocused && (
            <button
              onClick={handleExportCSV}
              className="text-orange-400 hover:text-orange-300 font-mono text-3xs border border-zinc-800 bg-zinc-900 rounded px-1.5 py-0.5 transition-colors mr-1"
              title="Export News to CSV"
            >
              ⬇ CSV
            </button>
          )}
          {headerControls}
          <button
            onClick={onRemove}
            className="text-zinc-500 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
            title="Remove Card"
          >
            ✕
          </button>
        </div>
      }
    >
      {!isMinimized && (
        <div
          className="space-y-3 font-mono"
          style={{ flex: 1, minHeight: 0, overflow: "auto" }}
        >
          {isOffline && !isCompact && (
            <div className="rounded border border-amber-900/30 bg-amber-955/20 p-2 text-2xs text-amber-200">
              ⚠️ Offline Preview Mode: Displaying cached or mock news data.
            </div>
          )}

          {isLoading ? (
            <p className="py-4 text-center text-2xs text-zinc-600">Loading feed...</p>
          ) : items.length === 0 ? (
            <p className="py-4 text-center text-2xs text-zinc-500">No news articles found in local database.</p>
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <div key={item.article_id} className="border-b border-zinc-800/40 pb-1.5 last:border-0 last:pb-0">
                  <div className="flex items-center justify-between text-3xs text-zinc-500 mb-0.5">
                    <span className="font-semibold text-cyan-500">{item.source_name || "CVM Filings"}</span>
                    <span>
                      {item.published_at
                        ? new Date(item.published_at).toLocaleDateString("en-US", { month: "short", day: "2-digit" })
                        : ""}
                    </span>
                  </div>
                  <a
                    href={item.original_url || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-xs text-zinc-300 hover:text-cyan-400 font-medium transition-colors line-clamp-2"
                  >
                    {item.title}
                  </a>
                </div>
              ))}
              {!isCompact && (
                <div className="pt-1 text-center border-t border-zinc-900/60">
                  <Link
                    to="/news"
                    className="text-2xs text-cyan-400 hover:text-cyan-300 hover:underline"
                  >
                    Open News Center →
                  </Link>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

// ─── 5. Market Price Sparkline Card ──────────────────────────────────────────

type MarketPriceConfig = {
  cdCvm: number;
  ticker: string;
  companyName: string;
};

function MarketPriceCard({
  config = { cdCvm: 0, ticker: "", companyName: "" },
  onConfigure,
  onRemove,
  isCompact = false,
  isMinimized = false,
  isFocused = false,
  headerControls,
}: {
  config?: MarketPriceConfig;
  onConfigure: (newCfg: MarketPriceConfig) => void;
  onRemove: () => void;
  isCompact?: boolean;
  isMinimized?: boolean;
  isFocused?: boolean;
  headerControls?: React.ReactNode;
}) {
  const [isConfiguring, setIsConfiguring] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["company-market-history", config.cdCvm, config.ticker],
    queryFn: () => fetchMarketHistory(config.cdCvm, config.ticker, null, null, "30d"),
    enabled: Boolean(config.cdCvm),
  });

  const prices: Array<number | null | undefined> = useMemo(() => {
    if (data?.mode !== "desktop" || !data.data?.observations) return [];
    return data.data.observations.map((p) => p.close).reverse();
  }, [data]);

  const stats = useMemo(() => {
    if (prices.length === 0) return { current: null, min: null, max: null };
    const valid = prices.filter((p: number | null | undefined): p is number => typeof p === "number" && !Number.isNaN(p));
    return {
      current: valid[valid.length - 1] ?? null,
      min: Math.min(...valid),
      max: Math.max(...valid),
    };
  }, [prices]);

  const isOffline = data?.mode === "browser" || error;

  const selectCompany = (cdCvm: number, name: string, ticker: string) => {
    onConfigure({ cdCvm, companyName: name, ticker });
    setIsConfiguring(false);
  };

  const handleExportCSV = () => {
    if (!data?.data?.observations || data.data.observations.length === 0) return;
    const headers = ["Date", "Close Price"];
    const rows = data.data.observations.map((obs: any) => [
      obs.date || "",
      obs.close ?? ""
    ]);
    const csvContent = [
      headers.join(","),
      ...rows.map((row) => row.map((val) => `"${val}"`).join(","))
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `${config.ticker || "ticker"}_market_history.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <Panel
      title={config.ticker ? `${config.ticker} Performance` : "Stock Price Watch"}
      subtitle={isMinimized ? undefined : config.companyName || "Daily quotes"}
      dense={isCompact}
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
      actions={
        <div className="flex items-center gap-1.5">
          {!isMinimized && (
            <button
              onClick={() => setIsConfiguring(!isConfiguring)}
              className="text-zinc-500 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
              title="Configure Ticker"
            >
              ⚙
            </button>
          )}
          {isFocused && (
            <button
              onClick={handleExportCSV}
              className="text-orange-400 hover:text-orange-300 font-mono text-3xs border border-zinc-800 bg-zinc-900 rounded px-1.5 py-0.5 transition-colors mr-1"
              title="Export Price History to CSV"
            >
              ⬇ CSV
            </button>
          )}
          {headerControls}
          <button
            onClick={onRemove}
            className="text-zinc-500 hover:text-zinc-300 font-mono text-2xs transition-colors px-1"
            title="Remove Card"
          >
            ✕
          </button>
        </div>
      }
    >
      {!isMinimized && (
        <div
          className="space-y-3 font-mono"
          style={{ flex: 1, minHeight: 0, overflow: "auto" }}
        >
          {isConfiguring && (
            <div className="border-b border-zinc-805 pb-3 space-y-2">
              <p className="text-2xs text-zinc-500 uppercase">Select Target Ticker</p>
              <CompanySelector onSelect={selectCompany} placeholder="Search ticker (e.g. PETR4)..." />
            </div>
          )}

          {!config.cdCvm ? (
            <div className={`${isCompact ? "py-3" : "py-6"} text-center space-y-2`}>
              <p className="text-xs text-zinc-500">No ticker selected.</p>
              {!isConfiguring && (
                <Button onClick={() => setIsConfiguring(true)} size="xs" variant="secondary">
                  Choose Ticker
                </Button>
              )}
            </div>
          ) : (
            <>
              {isOffline && !isCompact && (
                <div className="rounded border border-amber-905/30 bg-amber-955/20 p-2 text-2xs text-amber-200">
                  ⚠️ Offline Preview Mode: Displaying mock quotes.
                </div>
              )}

              {isLoading ? (
                <p className="py-4 text-center text-2xs text-zinc-600">Loading quotes...</p>
              ) : prices.length === 0 ? (
                <p className="py-4 text-center text-2xs text-zinc-500">No quotes available.</p>
              ) : (
                <div className={isFocused ? "grid grid-cols-3 gap-6" : isCompact ? "space-y-1.5" : "space-y-3"}>
                  <div className={isFocused ? "col-span-1 space-y-3" : ""}>
                    <div className="flex items-baseline justify-between">
                      <span className={`${isFocused ? "text-2xl" : isCompact ? "text-sm" : "text-lg"} font-semibold text-zinc-100`}>
                        R$ {stats.current ? stats.current.toFixed(2) : "—"}
                      </span>
                      <span className="text-2xs text-zinc-500">{isFocused ? "Current Price" : "Last 30 Days"}</span>
                    </div>

                    <div className="flex flex-col gap-1.5 text-2xs text-zinc-400 border-t border-zinc-850 pt-2 font-mono">
                      <div className="flex justify-between">
                        <span>MIN PRICE:</span>
                        <span className="font-semibold text-zinc-200">R$ {stats.min?.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>MAX PRICE:</span>
                        <span className="font-semibold text-zinc-200">R$ {stats.max?.toFixed(2)}</span>
                      </div>
                      {isFocused && data?.data?.observations && (
                        <div className="flex justify-between">
                          <span>QUOTES COUNT:</span>
                          <span className="font-semibold text-zinc-200">{data.data.observations.length}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className={isFocused ? "col-span-2 flex flex-col gap-3" : ""}>
                    <div className={`flex items-center justify-center bg-zinc-950/40 rounded border border-zinc-900/60 ${isFocused ? "py-4 flex-1 min-h-[140px]" : isCompact ? "py-1" : "py-2"}`}>
                      <Sparkline values={prices} width={isFocused ? 580 : isCompact ? 220 : 280} height={isFocused ? 100 : isCompact ? 25 : 45} />
                    </div>
                    {!isFocused && !isCompact && (
                      <div className="flex items-center justify-between text-2xs text-zinc-500 border-t border-zinc-800/40 pt-2">
                        <span>MIN: R$ {stats.min?.toFixed(2)}</span>
                        <span>MAX: R$ {stats.max?.toFixed(2)}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Panel>
  );
}

// ─── 6. Registry Map & Exports ────────────────────────────────────────────────

export type CardDef = {
  id: string;
  title: string;
  description: string;
  defaultSize: "large" | "medium" | "small";
  component: React.ComponentType<{
    config: any;
    onConfigure: (newCfg: any) => void;
    onRemove: () => void;
    isCompact?: boolean;
    isMinimized?: boolean;
    isFocused?: boolean;
    headerControls?: React.ReactNode;
  }>;
};

export const WORKSPACE_REGISTRY: Record<string, CardDef> = {
  "database-status": {
    id: "database-status",
    title: "Database Monitor",
    description: "CVM updates, diagnostics, base integrity status.",
    defaultSize: "large",
    component: DatabaseStatusCard,
  },
  watchlist: {
    id: "watchlist",
    title: "Watchlist & KPIs",
    description: "Trend lines of margins or prices for favorited companies.",
    defaultSize: "medium",
    component: WatchlistCard,
  },
  "priority-queue": {
    id: "priority-queue",
    title: "Priority Queue",
    description: "Coverage checklist updates and prioritization queue.",
    defaultSize: "medium",
    component: PriorityQueueCard,
  },
  "top-news": {
    id: "top-news",
    title: "Top News Feed",
    description: "Latest news alerts related to coverage sectors.",
    defaultSize: "medium",
    component: TopNewsCard,
  },
  "market-price": {
    id: "market-price",
    title: "Market Price Sparkline",
    description: "Standalone performance sparkline of a target ticker.",
    defaultSize: "small",
    component: MarketPriceCard,
  },
};
