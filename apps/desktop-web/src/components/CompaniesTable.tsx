import { useEffect, useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";

import { fetchCompanies, type CompaniesResult } from "@/lib/api/companies";
import { whenBridgeReady } from "@/lib/bridge/adapter";

const PAGE_SIZE = 20;

export function CompaniesTable() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [bridgeReady, setBridgeReady] = useState(false);

  // Wait for pywebview.api before issuing the first query so React 19's
  // eager hydration does not race the bridge injection.
  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Debounce the search input so we do not hammer the bridge on every keystroke.
  useEffect(() => {
    const handle = setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 250);
    return () => clearTimeout(handle);
  }, [searchInput]);

  const query = useQuery<CompaniesResult>({
    queryKey: ["companies", { search, page, pageSize: PAGE_SIZE }],
    queryFn: () => fetchCompanies({ search, page, page_size: PAGE_SIZE }),
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

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">
            Companies directory
          </h2>
          <p className="text-xs text-zinc-500">
            Live data from <code className="font-mono">CVMBridge.get_companies</code>
          </p>
        </div>
        <Status query={query} totalItems={totalItems} />
      </header>

      <SearchInput value={searchInput} onChange={setSearchInput} />

      <Body
        query={query}
        items={items}
        isDesktop={isDesktop}
        searchActive={search.length > 0}
      />

      {isDesktop && totalItems > 0 ? (
        <Pagination
          page={page}
          totalPages={totalPages}
          hasNext={hasNext}
          hasPrev={hasPrev}
          onPage={setPage}
        />
      ) : null}
    </section>
  );
}

function Status({
  query,
  totalItems,
}: {
  query: ReturnType<typeof useQuery<CompaniesResult>>;
  totalItems: number;
}) {
  if (query.isFetching && query.data) {
    return <span className="text-xs text-amber-300">Refreshing…</span>;
  }
  if (query.isLoading) {
    return <span className="text-xs text-zinc-500">Loading…</span>;
  }
  if (query.isError) {
    return <span className="text-xs text-rose-400">Error</span>;
  }
  if (query.data?.mode === "browser") {
    return <span className="text-xs text-amber-300">Browser mode</span>;
  }
  return (
    <span className="text-xs text-zinc-500">
      {totalItems.toLocaleString("pt-BR")} companies
    </span>
  );
}

function SearchInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <div className="mb-4">
      <label htmlFor="company-search" className="sr-only">
        Search companies
      </label>
      <input
        id="company-search"
        type="search"
        autoComplete="off"
        placeholder="Search company name or ticker…"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-emerald-600 focus:outline-none focus:ring-1 focus:ring-emerald-600"
      />
    </div>
  );
}

function Body({
  query,
  items,
  isDesktop,
  searchActive,
}: {
  query: ReturnType<typeof useQuery<CompaniesResult>>;
  items: NonNullable<
    (CompaniesResult & { mode: "desktop" })["page"]
  >["items"];
  isDesktop: boolean;
  searchActive: boolean;
}) {
  if (query.isError) {
    return (
      <p role="alert" className="rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300">
        {query.error instanceof Error ? query.error.message : String(query.error)}
      </p>
    );
  }
  if (query.data?.mode === "browser") {
    return (
      <div className="space-y-2 rounded border border-amber-900/60 bg-amber-950/30 p-3 text-sm text-amber-200">
        <p className="font-medium">Browser-mode preview</p>
        <p className="text-amber-200/80">{query.data.reason}</p>
      </div>
    );
  }
  if (query.isLoading || !isDesktop) {
    return <p className="text-sm text-zinc-500">Loading directory…</p>;
  }
  if (items.length === 0) {
    return (
      <p className="text-sm text-zinc-400">
        {searchActive
          ? "No companies match this search. Try a shorter query or check the spelling."
          : "No companies found in the local database."}
      </p>
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
          <tr className="bg-zinc-900/80 text-left text-xs uppercase tracking-wider text-zinc-500">
            <th className="px-3 py-2 font-medium">Company</th>
            <th className="px-3 py-2 font-medium">Ticker</th>
            <th className="px-3 py-2 font-medium">Sector</th>
            <th className="px-3 py-2 font-medium">Years</th>
            <th className="px-3 py-2 text-right font-medium">Rows</th>
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
  const yearsSummary = useMemo(() => formatYears(company.anos_disponiveis), [company.anos_disponiveis]);
  return (
    <tr className="hover:bg-zinc-900/50">
      <td className="px-3 py-2">
        <div className="font-medium text-zinc-100">{company.company_name}</div>
        <div className="font-mono text-xs text-zinc-500">CVM {company.cd_cvm}</div>
      </td>
      <td className="px-3 py-2 font-mono text-xs text-zinc-300">
        {company.ticker_b3 ?? "—"}
      </td>
      <td className="px-3 py-2">
        <div className="text-zinc-200">{company.sector_name}</div>
        {company.gics_sub_industry ? (
          <div className="text-xs text-zinc-500">{company.gics_sub_industry}</div>
        ) : null}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-400">{yearsSummary}</td>
      <td className="px-3 py-2 text-right font-mono text-xs text-zinc-400">
        {company.total_rows.toLocaleString("pt-BR")}
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

function formatYears(years: number[]): string {
  if (!years.length) return "—";
  const sorted = [...years].sort((a, b) => a - b);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (first === last) return String(first);
  return `${first}–${last} (${sorted.length})`;
}
