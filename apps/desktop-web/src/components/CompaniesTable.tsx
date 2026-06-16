import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import type { MarketCapSortMeta } from "@/lib/bridge/types";

import {
  fetchCompanies,
  fetchCompanyFilters,
  type CompaniesResult,
  type CompanyFiltersResult,
} from "@/lib/api/companies";
import {
  fetchCoveragePriorityScores,
  fetchCoverageUniverses,
  addCompanyToCoverageUniverse,
  removeCompanyFromCoverageUniverse,
  saveManualScoreOverride,
  fetchCoverageDecisionHistory,
} from "@/lib/api/coverage";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Button } from "@/components/ui/Button";

const PAGE_SIZE = 25;

export function CompaniesTable() {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSearch = searchParams.get("search") ?? "";
  const urlSector = searchParams.get("sector") ?? "";
  const urlPage = clampPage(searchParams.get("page"));

  const [searchInput, setSearchInput] = useState(urlSearch);
  const [bridgeReady, setBridgeReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Sync local input when URL search changes externally (e.g. via reset).
  useEffect(() => {
    setSearchInput(urlSearch);
  }, [urlSearch]);

  // Debounce typing into the URL so we do not hammer the bridge per keystroke.
  useEffect(() => {
    const trimmed = searchInput.trim();
    if (trimmed === urlSearch) return;
    const handle = setTimeout(() => {
      const next = new URLSearchParams(searchParams);
      if (trimmed) next.set("search", trimmed);
      else next.delete("search");
      next.delete("page");
      setSearchParams(next, { replace: true });
    }, 250);
    return () => clearTimeout(handle);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  const filtersQuery = useQuery<CompanyFiltersResult>({
    queryKey: ["company-filters"],
    queryFn: fetchCompanyFilters,
    enabled: bridgeReady,
    staleTime: 5 * 60 * 1000,
  });

  const query = useQuery<CompaniesResult>({
    queryKey: [
      "companies",
      { search: urlSearch, sector: urlSector, page: urlPage, pageSize: PAGE_SIZE },
    ],
    queryFn: () =>
      fetchCompanies({
        search: urlSearch,
        sector_slug: urlSector || null,
        page: urlPage,
        page_size: PAGE_SIZE,
      }),
    enabled: bridgeReady,
    placeholderData: keepPreviousData,
  });

  const activeUniverseId = useMemo(() => {
    return localStorage.getItem("active_coverage_universe_id") || "";
  }, []);

  const [selectedCompany, setSelectedCompany] = useState<any | null>(null);

  const universesQuery = useQuery({
    queryKey: ["coverage-universes"],
    queryFn: fetchCoverageUniverses,
    enabled: bridgeReady,
  });

  const activeUniverseName = useMemo(() => {
    if (!universesQuery.data || !activeUniverseId) return "Default Universe";
    const u = universesQuery.data.find((x) => x.id === activeUniverseId);
    return u ? u.name : "Default Universe";
  }, [universesQuery.data, activeUniverseId]);

  const coverageQuery = useQuery({
    queryKey: ["active-coverage-scores", activeUniverseId],
    queryFn: () => fetchCoveragePriorityScores(activeUniverseId),
    enabled: bridgeReady && !!activeUniverseId,
    staleTime: 30 * 1000,
  });

  const activeCoverageItem = useMemo(() => {
    if (!selectedCompany || !coverageQuery.data) return null;
    return coverageQuery.data.find((item: any) => item.cd_cvm === selectedCompany.cd_cvm);
  }, [selectedCompany, coverageQuery.data]);

  const coverageMap = useMemo(() => {
    const map = new Map<number, string>();
    if (coverageQuery.data) {
      for (const item of coverageQuery.data) {
        map.set(item.cd_cvm, item.tier);
      }
    }
    return map;
  }, [coverageQuery.data]);

  const isDesktop = query.data?.mode === "desktop";
  const page$ = query.data?.mode === "desktop" ? query.data.page : null;
  const items = page$?.items ?? [];
  const pagination = page$?.pagination;
  const totalItems = pagination?.total_items ?? 0;
  const totalPages = pagination?.total_pages ?? 1;
  const hasNext = pagination?.has_next ?? false;
  const hasPrev = pagination?.has_previous ?? false;
  const mktMeta = page$?.market_cap_sort_meta ?? null;

  const sectors =
    filtersQuery.data?.mode === "desktop" ? filtersQuery.data.sectors : [];
  const activeSector = useMemo(
    () => sectors.find((s) => s.sector_slug === urlSector) ?? null,
    [sectors, urlSector],
  );

  const setUrl = (mut: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(searchParams);
    mut(next);
    setSearchParams(next, { replace: false });
  };

  const onSectorChange = (slug: string) => {
    setUrl((p) => {
      if (slug) p.set("sector", slug);
      else p.delete("sector");
      p.delete("page");
    });
  };

  const onPage = (next: number) => {
    setUrl((p) => {
      if (next > 1) p.set("page", String(next));
      else p.delete("page");
    });
  };

  const onResetAll = () => {
    setSearchInput("");
    setSearchParams(new URLSearchParams(), { replace: false });
  };

  const hasActiveFilters = Boolean(urlSearch || urlSector);

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">
            Companies directory
          </h2>
          <p className="text-xs text-zinc-500">
            Local CVM data ·{" "}
            <code className="font-mono">CVMBridge.get_companies</code>
          </p>
        </div>
        <Status query={query} totalItems={totalItems} hasFilters={hasActiveFilters} />
      </header>

      <FilterBar
        searchInput={searchInput}
        onSearchInput={setSearchInput}
        sectors={sectors}
        sectorsLoading={filtersQuery.isLoading}
        sectorsError={filtersQuery.isError}
        selectedSector={urlSector}
        onSectorChange={onSectorChange}
      />

      <ActiveFilters
        search={urlSearch}
        sectorLabel={activeSector?.sector_name ?? null}
        onClearSearch={() => {
          setSearchInput("");
          setUrl((p) => {
            p.delete("search");
            p.delete("page");
          });
        }}
        onClearSector={() =>
          setUrl((p) => {
            p.delete("sector");
            p.delete("page");
          })
        }
        onResetAll={onResetAll}
      />

      {mktMeta ? <MarketCapBanner meta={mktMeta} /> : null}

      <Body
        query={query}
        items={items}
        isDesktop={isDesktop}
        hasFilters={hasActiveFilters}
        onResetAll={onResetAll}
        coverageMap={coverageMap}
        onEditCoverage={setSelectedCompany}
      />

      {isDesktop && totalItems > 0 ? (
        <Pagination
          page={urlPage}
          totalPages={totalPages}
          hasNext={hasNext}
          hasPrev={hasPrev}
          onPage={onPage}
        />
      ) : null}

      {selectedCompany && activeUniverseId && (
        <CoverageQuickEditDrawer
          company={selectedCompany}
          activeUniverseId={activeUniverseId}
          activeUniverseName={activeUniverseName}
          activeCoverageItem={activeCoverageItem}
          onClose={() => setSelectedCompany(null)}
        />
      )}

      <p className="mt-3 text-[11px] text-zinc-600">
        Tip: search matches company name, ticker, or CVM code. Use the sector
        filter for industry-scoped browsing.
      </p>
    </section>
  );
}

function clampPage(raw: string | null): number {
  const n = Number.parseInt(raw ?? "1", 10);
  if (!Number.isFinite(n) || n < 1) return 1;
  return n;
}

function Status({
  query,
  totalItems,
  hasFilters,
}: {
  query: ReturnType<typeof useQuery<CompaniesResult>>;
  totalItems: number;
  hasFilters: boolean;
}) {
  if (query.isFetching && query.data) {
    return <span className="text-xs text-amber-300">↻ Refreshing…</span>;
  }
  if (query.isLoading) {
    return <span className="text-xs text-zinc-500">◌ Loading…</span>;
  }
  if (query.isError) {
    return <span className="text-xs text-rose-400">! Error</span>;
  }
  if (query.data?.mode === "browser") {
    return <span className="text-xs text-amber-300">▲ Browser mode</span>;
  }
  return (
    <span className="font-mono text-xs text-zinc-400">
      {totalItems.toLocaleString("en-US")}{" "}
      {hasFilters ? "matched" : "companies"}
    </span>
  );
}

function FilterBar({
  searchInput,
  onSearchInput,
  sectors,
  sectorsLoading,
  sectorsError,
  selectedSector,
  onSectorChange,
}: {
  searchInput: string;
  onSearchInput: (v: string) => void;
  sectors: Array<{ sector_slug: string; sector_name: string; company_count: number }>;
  sectorsLoading: boolean;
  sectorsError: boolean;
  selectedSector: string;
  onSectorChange: (slug: string) => void;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-end gap-2">
      <div className="min-w-[260px] flex-1">
        <label
          htmlFor="company-search"
          className="mb-1 block text-[10px] uppercase tracking-widest text-zinc-500"
        >
          Search
        </label>
        <input
          id="company-search"
          type="search"
          autoComplete="off"
          spellCheck={false}
          placeholder="Company name, ticker, or CVM code…"
          value={searchInput}
          onChange={(event) => onSearchInput(event.target.value)}
          className="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-600"
        />
      </div>
      <div className="min-w-[220px]">
        <label
          htmlFor="company-sector"
          className="mb-1 block text-[10px] uppercase tracking-widest text-zinc-500"
        >
          Sector (GICS)
        </label>
        <select
          id="company-sector"
          value={selectedSector}
          onChange={(event) => onSectorChange(event.target.value)}
          disabled={sectorsLoading || sectorsError}
          className="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 focus:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-600 disabled:opacity-50"
        >
          <option value="">
            {sectorsLoading
              ? "Loading sectors…"
              : sectorsError
                ? "Sectors unavailable"
                : "All sectors"}
          </option>
          {sectors.map((sector) => (
            <option key={sector.sector_slug} value={sector.sector_slug}>
              {sector.sector_name} ({sector.company_count.toLocaleString("en-US")})
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

function ActiveFilters({
  search,
  sectorLabel,
  onClearSearch,
  onClearSector,
  onResetAll,
}: {
  search: string;
  sectorLabel: string | null;
  onClearSearch: () => void;
  onClearSector: () => void;
  onResetAll: () => void;
}) {
  if (!search && !sectorLabel) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      {search ? (
        <FilterChip label={`search: ${search}`} onClear={onClearSearch} />
      ) : null}
      {sectorLabel ? (
        <FilterChip label={`sector: ${sectorLabel}`} onClear={onClearSector} />
      ) : null}
      <button
        type="button"
        onClick={onResetAll}
        className="ml-auto rounded border border-zinc-700 bg-transparent px-2 py-1 text-xs text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
      >
        Reset filters
      </button>
    </div>
  );
}

function FilterChip({
  label,
  onClear,
}: {
  label: string;
  onClear: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-200">
      <span className="font-mono">{label}</span>
      <button
        type="button"
        onClick={onClear}
        aria-label={`Clear ${label}`}
        className="text-zinc-500 hover:text-rose-300"
      >
        ×
      </button>
    </span>
  );
}

function Body({
  query,
  items,
  isDesktop,
  hasFilters,
  onResetAll,
  coverageMap,
  onEditCoverage,
}: {
  query: ReturnType<typeof useQuery<CompaniesResult>>;
  items: NonNullable<(CompaniesResult & { mode: "desktop" })["page"]>["items"];
  isDesktop: boolean;
  hasFilters: boolean;
  onResetAll: () => void;
  coverageMap: Map<number, string>;
  onEditCoverage: (company: any) => void;
}) {
  if (query.isError) {
    return (
      <StateBanner
        variant="error"
        message={query.error instanceof Error ? query.error.message : String(query.error)}
        onRetry={() => { void query.refetch(); }}
      />
    );
  }
  if (query.data?.mode === "browser") {
    return <StateBanner variant="browser-only" message={query.data.reason} />;
  }
  if (query.isLoading || !isDesktop) {
    return <StateBanner variant="loading" title="Loading directory…" />;
  }
  if (items.length === 0) {
    if (hasFilters) {
      return (
        <StateBanner
          variant="empty"
          title="No results"
          message="No companies match the active filters."
        >
          <button
            type="button"
            onClick={onResetAll}
            className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-1"
          >
            Reset filters
          </button>
        </StateBanner>
      );
    }
    return (
      <StateBanner
        variant="empty"
        title="No companies"
        message="No companies in the local database. Run Database Updates to populate data."
      />
    );
  }
  return <CompaniesGrid items={items} coverageMap={coverageMap} onEditCoverage={onEditCoverage} />;
}

function CompaniesGrid({
  items,
  coverageMap,
  onEditCoverage,
}: {
  items: NonNullable<(CompaniesResult & { mode: "desktop" })["page"]>["items"];
  coverageMap: Map<number, string>;
  onEditCoverage: (company: any) => void;
}) {
  return (
    <div className="overflow-hidden rounded border border-zinc-800">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-zinc-900/80 text-left text-[10px] uppercase tracking-wider text-zinc-500">
            <th scope="col" className="px-3 py-2 font-medium">Company</th>
            <th scope="col" className="px-3 py-2 font-medium">Ticker</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Mkt Cap</th>
            <th scope="col" className="px-3 py-2 font-medium">CVM</th>
            <th scope="col" className="px-3 py-2 font-medium">Sector</th>
            <th scope="col" className="px-3 py-2 font-medium">Sub-industry</th>
            <th scope="col" className="px-3 py-2 font-medium">Years</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Rows</th>
            <th scope="col" className="px-3 py-2 text-center font-medium">Data</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/80 text-zinc-200">
          {items.map((company) => (
            <CompanyRow key={company.cd_cvm} company={company} coverageMap={coverageMap} onEditCoverage={onEditCoverage} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CompanyRow({
  company,
  coverageMap,
  onEditCoverage,
}: {
  company: NonNullable<
    (CompaniesResult & { mode: "desktop" })["page"]
  >["items"][number];
  coverageMap: Map<number, string>;
  onEditCoverage: (company: any) => void;
}) {
  const yearsSummary = useMemo(
    () => formatYears(company.anos_disponiveis),
    [company.anos_disponiveis],
  );
  const tier = coverageMap.get(company.cd_cvm);
  return (
    <tr className="group hover:bg-zinc-900/50">
      <td className="px-3 py-2">
        <Link
          to={`/empresas/${company.cd_cvm}`}
          className="block focus:outline-none focus:ring-1 focus:ring-cyan-600"
        >
          <div className="font-medium text-zinc-100 group-hover:text-cyan-300 flex items-center gap-2">
            <span>{company.company_name}</span>
            {tier ? (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onEditCoverage(company);
                }}
                className="hover:scale-105 transition-transform cursor-pointer"
              >
                <CoverageTierBadge tier={tier} />
              </button>
            ) : (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onEditCoverage(company);
                }}
                className="opacity-0 group-hover:opacity-100 transition-all rounded border border-zinc-700 bg-zinc-800 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 cursor-pointer ml-1"
              >
                + Coverage
              </button>
            )}
          </div>
        </Link>
      </td>
      <td className="px-3 py-2 font-mono text-xs text-zinc-300">
        {company.ticker_b3 ?? "—"}
      </td>
      <td className="px-3 py-2 text-right font-mono text-xs text-zinc-300">
        {company.market_cap_brl != null ? formatMarketCap(company.market_cap_brl) : <span className="text-zinc-600">—</span>}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-zinc-400">
        {company.cd_cvm}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-200">
        {company.gics_sector ?? company.sector_name ?? "—"}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-500">
        {company.gics_sub_industry ?? "—"}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-zinc-400">{yearsSummary}</td>
      <td className="px-3 py-2 text-right font-mono text-xs text-zinc-400">
        {company.total_rows.toLocaleString("en-US")}
      </td>
      <td className="px-3 py-2 text-center text-xs">
        <DataStatusBadge status={company.data_status} hasFinancialData={company.has_financial_data} />
      </td>
    </tr>
  );
}

function CoverageTierBadge({ tier }: { tier: string }) {
  switch (tier) {
    case "must_cover":
      return (
        <span className="inline-flex items-center rounded border border-emerald-900/60 bg-emerald-950/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-emerald-400">
          Must Cover
        </span>
      );
    case "core":
      return (
        <span className="inline-flex items-center rounded border border-cyan-900/60 bg-cyan-950/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-cyan-400">
          Core
        </span>
      );
    case "watchlist":
      return (
        <span className="inline-flex items-center rounded border border-amber-900/60 bg-amber-950/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-amber-400">
          Watchlist
        </span>
      );
    case "opportunistic":
      return (
        <span className="inline-flex items-center rounded border border-indigo-900/60 bg-indigo-950/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-indigo-400">
          Opportunistic
        </span>
      );
    case "excluded":
      return (
        <span className="inline-flex items-center rounded border border-zinc-700 bg-zinc-800/50 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-zinc-400">
          Excluded
        </span>
      );
    case "inappropriate":
      return (
        <span className="inline-flex items-center rounded border border-rose-900/60 bg-rose-950/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-rose-400">
          Inappropriate
        </span>
      );
    default:
      return null;
  }
}

function Pagination({
  page,
  totalPages,
  hasNext,
  hasPrev,
  onPage,
}: {
  page: number;
  totalPages: number;
  hasNext: boolean;
  hasPrev: boolean;
  onPage: (next: number) => void;
}) {
  return (
    <nav className="mt-4 flex items-center justify-between text-sm">
      <button
        type="button"
        onClick={() => onPage(page - 1)}
        disabled={!hasPrev}
        className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
      >
        ← Previous
      </button>
      <span className="font-mono text-xs text-zinc-500">
        Page {page} of {totalPages}
      </span>
      <button
        type="button"
        onClick={() => onPage(page + 1)}
        disabled={!hasNext}
        className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Next →
      </button>
    </nav>
  );
}

function DataStatusBadge({
  status,
  hasFinancialData,
}: {
  status: string | undefined;
  hasFinancialData: boolean;
}) {
  const resolved = status ?? (hasFinancialData ? "partial" : "no_history");
  switch (resolved) {
    case "complete":
      return (
        <span
          title="Complete financial history"
          className="inline-flex items-center gap-1 rounded border border-emerald-900/60 bg-emerald-950/40 px-1.5 py-0.5 font-mono text-emerald-400"
        >
          ● Complete
        </span>
      );
    case "partial":
      return (
        <span
          title="Partial financial history"
          className="inline-flex items-center gap-1 rounded border border-amber-900/60 bg-amber-950/40 px-1.5 py-0.5 font-mono text-amber-400"
        >
          ◑ Partial
        </span>
      );
    case "failed":
      return (
        <span
          title="Last update failed"
          className="inline-flex items-center gap-1 rounded border border-rose-900/60 bg-rose-950/40 px-1.5 py-0.5 font-mono text-rose-400"
        >
          ✕ Update Failed
        </span>
      );
    case "unmapped":
      return (
        <span
          title="Company without complete mapping"
          className="inline-flex items-center gap-1 rounded border border-orange-900/60 bg-orange-950/40 px-1.5 py-0.5 font-mono text-orange-400"
        >
          ? Unmapped
        </span>
      );
    default:
      return (
        <span
          title="No financial history"
          className="inline-flex items-center gap-1 rounded border border-zinc-700/60 bg-zinc-900/40 px-1.5 py-0.5 font-mono text-zinc-500"
        >
          ○ No History
        </span>
      );
  }
}

function formatYears(years: number[]): string {
  if (!years.length) return "—";
  const sorted = [...years].sort((a, b) => a - b);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (first === last) return String(first);
  return `${first}–${last} (${sorted.length})`;
}

function formatMarketCap(brl: number): string {
  if (brl >= 1e12) return `R$ ${(brl / 1e12).toFixed(1)}T`;
  if (brl >= 1e9) return `R$ ${(brl / 1e9).toFixed(1)}B`;
  if (brl >= 1e6) return `R$ ${(brl / 1e6).toFixed(0)}M`;
  return `R$ ${brl.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function MarketCapBanner({ meta }: { meta: MarketCapSortMeta }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-zinc-800 bg-zinc-900/40 px-3 py-1.5 text-[11px] text-zinc-400">
      <span className="font-medium text-zinc-300">↓ Sorted by market cap</span>
      <span>·</span>
      <span>
        {meta.mapped_count.toLocaleString("en-US")} of{" "}
        {meta.total_in_snapshot.toLocaleString("en-US")} B3 companies ranked
      </span>
      <span>·</span>
      <span title="Yahoo Finance is an unofficial free source, not official B3/CVM data.">
        Source: Yahoo Finance (unofficial/free)
      </span>
      <span>·</span>
      <span>Snapshot: {meta.as_of_date}</span>
    </div>
  );
}

// --- Quick Edit Drawer for Directory Coverage Integration ---
function CoverageQuickEditDrawer({
  company,
  activeUniverseId,
  activeUniverseName,
  activeCoverageItem,
  onClose,
}: {
  company: any;
  activeUniverseId: string;
  activeUniverseName: string;
  activeCoverageItem: any;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [tier, setTier] = useState<string>(activeCoverageItem?.tier || "none");
  const [holdings, setHoldings] = useState<string>(
    activeCoverageItem?.holding_pct != null ? String(activeCoverageItem.holding_pct) : "0"
  );
  const [override, setOverride] = useState<string>(
    activeCoverageItem?.manual_score_override != null ? String(activeCoverageItem.manual_score_override) : ""
  );
  const [rationale, setRationale] = useState<string>("");

  const historyQuery = useQuery({
    queryKey: ["company-coverage-history-drawer", activeUniverseId, company.cd_cvm],
    queryFn: () => fetchCoverageDecisionHistory(activeUniverseId, company.cd_cvm),
    enabled: !!activeUniverseId && !!company.cd_cvm,
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!rationale) throw new Error("Rationale is mandatory for all coverage decisions");
      
      const prevTier = activeCoverageItem?.tier || "none";
      const newTier = tier;

      // 1. Handle Tier and Holdings pct
      if (newTier === "none") {
        if (prevTier !== "none") {
          await removeCompanyFromCoverageUniverse({
            universe_id: activeUniverseId,
            cd_cvm: company.cd_cvm,
            rationale,
          });
        }
      } else {
        await addCompanyToCoverageUniverse({
          universe_id: activeUniverseId,
          cd_cvm: company.cd_cvm,
          tier: newTier,
          rationale,
          holding_pct: holdings === "" ? 0.0 : Number(holdings),
        });
      }

      // 2. Handle Manual Score Override
      const prevOverride = activeCoverageItem?.manual_score_override;
      const newOverride = override === "" ? null : Number(override);
      
      if (newOverride !== prevOverride && newTier !== "none") {
        await saveManualScoreOverride({
          universe_id: activeUniverseId,
          cd_cvm: company.cd_cvm,
          override: newOverride,
          rationale,
        });
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["active-coverage-scores", activeUniverseId] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-scores", activeUniverseId] });
      void queryClient.invalidateQueries({ queryKey: ["coverage-capacity", activeUniverseId] });
      void queryClient.invalidateQueries({ queryKey: ["companies"] });
      alert("Coverage settings saved successfully!");
      onClose();
    },
    onError: (err) => {
      alert(String(err));
    }
  });

  return (
    <>
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slideIn {
          animation: slideIn 0.2s ease-out forwards;
        }
      `}</style>
      
      {/* Backdrop */}
      <div 
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-xs" 
        onClick={onClose}
      />
      
      {/* Drawer Container */}
      <div className="fixed inset-y-0 right-0 z-50 w-96 bg-zinc-900 border-l border-zinc-800 shadow-2xl p-6 flex flex-col font-mono text-xs text-zinc-100 animate-slideIn">
        {/* Header */}
        <div className="border-b border-zinc-850 pb-3 mb-4 flex justify-between items-start">
          <div className="max-w-[85%]">
            <h3 className="text-sm font-bold text-[var(--color-id-ticker)] truncate">
              {company.ticker_b3 || "N/A"} - {company.company_name}
            </h3>
            <span className="text-3xs text-zinc-500 block mt-0.5">
              CVM: {company.cd_cvm} · Sector: {company.gics_sector || company.sector_name || "N/A"}
            </span>
            <span className="text-3xs text-zinc-400 block mt-1">
              Universe: <span className="text-zinc-200">{activeUniverseName}</span>
            </span>
          </div>
          <button 
            type="button" 
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 text-sm focus:outline-none"
          >
            ✕
          </button>
        </div>

        {/* Form */}
        <form 
          onSubmit={(e) => {
            e.preventDefault();
            saveMutation.mutate();
          }}
          className="flex-1 overflow-y-auto space-y-4 pr-1"
        >
          {/* Coverage Tier */}
          <div className="space-y-1">
            <label className="block text-3xs text-zinc-400 uppercase font-semibold">Coverage Tier</label>
            <select
              value={tier}
              onChange={(e) => setTier(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 focus:outline-none focus:border-[var(--color-action-primary)] text-xs text-zinc-200"
            >
              <option value="none">Not in Universe (Remove)</option>
              <option value="must_cover">Must Cover</option>
              <option value="core">Core Coverage</option>
              <option value="watchlist">Watchlist</option>
              <option value="opportunistic">Opportunistic</option>
              <option value="excluded">Excluded</option>
              <option value="inappropriate">Not Appropriate</option>
            </select>
          </div>

          {tier !== "none" && (
            <>
              {/* Holdings % */}
              <div className="space-y-1">
                <label className="block text-3xs text-zinc-400 uppercase font-semibold">Analyst Holdings %</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="100"
                  value={holdings}
                  onChange={(e) => setHoldings(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 focus:outline-none focus:border-[var(--color-action-primary)] text-xs text-zinc-200"
                />
              </div>

              {/* Manual Score Override */}
              <div className="space-y-1">
                <label className="block text-3xs text-zinc-400 uppercase font-semibold">Manual Score Override (+/-)</label>
                <input
                  type="number"
                  step="0.5"
                  placeholder="e.g. 5.0 or -10"
                  value={override}
                  onChange={(e) => setOverride(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 focus:outline-none focus:border-[var(--color-action-primary)] text-xs text-zinc-200"
                />
              </div>
            </>
          )}

          {/* Decision Rationale */}
          <div className="space-y-1">
            <label className="block text-3xs text-zinc-400 uppercase font-semibold">Decision Rationale *</label>
            <textarea
              required
              rows={3}
              placeholder="Provide a mandatory reason for this tier, holdings, or score override change..."
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 focus:outline-none focus:border-[var(--color-action-primary)] text-xs text-zinc-200"
            />
          </div>

          {/* Save Action */}
          <div className="pt-2">
            <Button 
              type="submit" 
              className="w-full"
              disabled={saveMutation.isPending || !rationale}
            >
              {saveMutation.isPending ? "Saving..." : "Save Coverage Config"}
            </Button>
          </div>

          {/* Decision History logs */}
          <div className="border-t border-zinc-800 pt-3 mt-4">
            <span className="block text-3xs text-zinc-400 uppercase font-semibold mb-2">Audit Decision History</span>
            {historyQuery.isLoading ? (
              <div className="text-3xs text-zinc-500 animate-pulse">Loading log history...</div>
            ) : historyQuery.data?.length === 0 ? (
              <div className="text-3xs text-zinc-500 italic">No historical changes logged.</div>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {historyQuery.data?.map((h: any) => (
                  <div key={h.id} className="p-2 bg-zinc-950/60 rounded border border-zinc-850 text-3xs">
                    <div className="flex justify-between text-zinc-500 mb-1">
                      <span className="uppercase font-bold text-[var(--color-id-ticker)]">{h.event_type.replace("_", " ")}</span>
                      <span>{h.timestamp.slice(0, 16).replace("T", " ")}</span>
                    </div>
                    <div className="text-zinc-300">
                      {h.previous_value} ➔ {h.new_value}
                    </div>
                    {h.rationale && (
                      <div className="text-zinc-500 italic mt-0.5">"Rationale: {h.rationale}"</div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </form>
      </div>
    </>
  );
}
