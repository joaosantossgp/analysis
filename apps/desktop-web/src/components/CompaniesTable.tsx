import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import type { MarketCapSortMeta } from "@/lib/bridge/types";

import {
  fetchCompanies,
  fetchCompanyFilters,
  type CompaniesResult,
  type CompanyFiltersResult,
} from "@/lib/api/companies";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { StateBanner } from "@/components/feedback/StateBanner";

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
}: {
  query: ReturnType<typeof useQuery<CompaniesResult>>;
  items: NonNullable<(CompaniesResult & { mode: "desktop" })["page"]>["items"];
  isDesktop: boolean;
  hasFilters: boolean;
  onResetAll: () => void;
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
  return <CompaniesGrid items={items} />;
}

function CompaniesGrid({
  items,
}: {
  items: NonNullable<(CompaniesResult & { mode: "desktop" })["page"]>["items"];
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
            <CompanyRow key={company.cd_cvm} company={company} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CompanyRow({
  company,
}: {
  company: NonNullable<
    (CompaniesResult & { mode: "desktop" })["page"]
  >["items"][number];
}) {
  const yearsSummary = useMemo(
    () => formatYears(company.anos_disponiveis),
    [company.anos_disponiveis],
  );
  return (
    <tr className="group hover:bg-zinc-900/50">
      <td className="px-3 py-2">
        <Link
          to={`/empresas/${company.cd_cvm}`}
          className="block focus:outline-none focus:ring-1 focus:ring-cyan-600"
        >
          <div className="font-medium text-zinc-100 group-hover:text-cyan-300">
            {company.company_name}
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
