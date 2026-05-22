import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { fetchSubSectorDetail } from "@/lib/api/sectors";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { PageHeader } from "@/components/PageHeader";
import { type BreadcrumbItem } from "@/components/Breadcrumbs";

function parseYear(raw: string | null): number | null {
  if (!raw) return null;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}

export function SubSectorDetailPage() {
  const { sectorSlug, subSectorSlug } = useParams<{ sectorSlug: string; subSectorSlug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedYear = parseYear(searchParams.get("ano"));
  const companyFilter = (searchParams.get("q") ?? "").trim().toLowerCase();
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

  const query = useQuery({
    queryKey: ["sub-sector-detail", sectorSlug, subSectorSlug, requestedYear],
    queryFn: () => fetchSubSectorDetail(sectorSlug ?? "", subSectorSlug ?? "", requestedYear),
    enabled: bridgeReady && !!sectorSlug && !!subSectorSlug,
    staleTime: 60_000,
  });

  const detail =
    query.data && query.data.mode === "desktop" && !query.data.notFound
      ? query.data.detail
      : null;
  const notFound =
    query.data?.mode === "desktop" && query.data.notFound === true;

  const filteredCompanies = useMemo(() => {
    if (!detail) return [];
    if (!companyFilter) return detail.companies;
    return detail.companies.filter((company) => {
      const haystack = [
        company.company_name,
        company.ticker_b3,
        String(company.cd_cvm),
        company.gics_sub_industry,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(companyFilter);
    });
  }, [detail, companyFilter]);

  const setYear = (year: number | null) => {
    const next = new URLSearchParams(searchParams);
    if (year !== null) next.set("ano", String(year));
    else next.delete("ano");
    setSearchParams(next, { replace: true });
  };

  const setCompanyFilter = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value.trim()) next.set("q", value);
    else next.delete("q");
    setSearchParams(next, { replace: true });
  };

  // Breadcrumbs items: Sectors > [Parent Sector Name] > [Sub-sector Name]
  const breadcrumbs = useMemo(() => {
    const items: BreadcrumbItem[] = [{ label: "Sectors", to: "/setores" }];
    if (detail) {
      if (detail.parent_sector_name && detail.parent_sector_slug) {
        items.push({
          label: detail.parent_sector_name,
          to: `/setores/${detail.parent_sector_slug}`,
        });
      }
      items.push({ label: detail.sector_name });
    } else {
      items.push({ label: subSectorSlug ?? "Sub-sector" });
    }
    return items;
  }, [detail, subSectorSlug]);

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg space-y-4">
      <PageHeader
        title={detail?.sector_name ?? "Sub-sector"}
        subtitle={
          detail?.parent_sector_name
            ? `GICS sub-industry inside ${detail.parent_sector_name}`
            : "GICS sub-industry"
        }
        breadcrumbs={breadcrumbs}
        actions={
          <Status query={query} notFound={notFound} />
        }
      />

      <BodyHeader detail={detail} onYearChange={setYear} sectorSlug={sectorSlug} />

      <CompanyFilterBar
        value={searchParams.get("q") ?? ""}
        onChange={setCompanyFilter}
        disabled={!detail || detail.companies.length === 0}
      />

      <Body
        query={query}
        notFound={notFound}
        detail={detail}
        filteredCompanies={filteredCompanies}
        onClearCompanyFilter={() => setCompanyFilter("")}
      />
    </section>
  );
}

function Status({
  query,
  notFound,
}: {
  query: any;
  notFound: boolean;
}) {
  if (query.isLoading) return <span className="text-xs text-zinc-500">Loading…</span>;
  if (query.isFetching) return <span className="text-xs text-amber-300">Refreshing…</span>;
  if (query.isError) return <span className="text-xs text-rose-400">Error</span>;
  if (notFound) return <span className="text-xs text-rose-400">Not found</span>;
  if (query.data?.mode === "browser")
    return <span className="text-xs text-amber-300">Browser mode</span>;
  return null;
}

function BodyHeader({
  detail,
  onYearChange,
  sectorSlug,
}: {
  detail: any;
  onYearChange: (year: number | null) => void;
  sectorSlug: string | undefined;
}) {
  if (!detail) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-zinc-800 bg-zinc-950/40 px-3 py-2">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="font-mono text-zinc-300">
          {detail.company_count.toLocaleString("pt-BR")} companies
        </span>
        <span className="text-zinc-600">·</span>
        <span className="font-mono text-zinc-400">
          Base year {detail.selected_year}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <label
          htmlFor="subsector-year"
          className="text-[10px] uppercase tracking-widest text-zinc-500"
        >
          Year
        </label>
        <select
          id="subsector-year"
          value={detail.selected_year}
          onChange={(event) => onYearChange(Number.parseInt(event.target.value, 10))}
          disabled={detail.available_years.length === 0}
          className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 focus:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-600 disabled:opacity-50"
        >
          {detail.available_years.length === 0 ? (
            <option value={detail.selected_year}>{detail.selected_year}</option>
          ) : (
            detail.available_years.map((year: number) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))
          )}
        </select>
        {sectorSlug && (
          <Link
            to={`/?sector=${encodeURIComponent(sectorSlug)}`}
            className="ml-2 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 hover:border-cyan-700 hover:text-cyan-300"
          >
            Open in directory →
          </Link>
        )}
      </div>
    </div>
  );
}

function CompanyFilterBar({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (next: string) => void;
  disabled: boolean;
}) {
  return (
    <div>
      <label
        htmlFor="subsector-company-filter"
        className="mb-1 block text-[10px] uppercase tracking-widest text-zinc-500"
      >
        Filter companies
      </label>
      <input
        id="subsector-company-filter"
        type="search"
        autoComplete="off"
        spellCheck={false}
        placeholder="Name, ticker, or CVM code…"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-600 disabled:opacity-50"
      />
    </div>
  );
}

function Body({
  query,
  notFound,
  detail,
  filteredCompanies,
  onClearCompanyFilter,
}: {
  query: any;
  notFound: boolean;
  detail: any;
  filteredCompanies: any[];
  onClearCompanyFilter: () => void;
}) {
  if (query.isError) {
    return (
      <p
        role="alert"
        className="rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-300"
      >
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
  if (notFound) {
    return (
      <div className="space-y-2 rounded border border-rose-900/60 bg-rose-950/40 p-3 text-sm text-rose-200">
        <p>Sub-sector not found in the local database.</p>
        <Link
          to="/setores"
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
        >
          Back to sectors
        </Link>
      </div>
    );
  }
  if (query.isLoading || !detail) {
    return <p className="text-sm text-zinc-500">Loading sub-sector details…</p>;
  }
  if (detail.companies.length === 0) {
    return (
      <p className="text-sm text-zinc-400">
        No companies recorded in this sub-sector. Run Update Base to populate
        company data.
      </p>
    );
  }
  if (filteredCompanies.length === 0) {
    return (
      <div className="space-y-2 rounded border border-zinc-800 bg-zinc-950/40 p-4 text-sm text-zinc-300">
        <p>No companies match the filter inside this sub-sector.</p>
        <button
          type="button"
          onClick={onClearCompanyFilter}
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
        >
          Clear filter
        </button>
      </div>
    );
  }
  return <CompanyTable companies={filteredCompanies} />;
}

function CompanyTable({
  companies,
}: {
  companies: Array<{
    cd_cvm: number;
    company_name: string;
    ticker_b3: string | null;
    roe: number | null;
    mg_ebit: number | null;
    mg_liq: number | null;
  }>;
}) {
  const formatPercent = (val: number | null) => {
    if (val === null || val === undefined) return "—";
    return `${(val * 100).toFixed(1)}%`;
  };

  return (
    <div className="overflow-hidden rounded border border-zinc-800">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-zinc-900/80 text-left text-[10px] uppercase tracking-wider text-zinc-500">
            <th className="px-3 py-2 font-medium">Company</th>
            <th className="px-3 py-2 font-medium">Ticker</th>
            <th className="px-3 py-2 font-medium">CVM</th>
            <th className="px-3 py-2 text-right font-medium">ROE</th>
            <th className="px-3 py-2 text-right font-medium">Margem EBIT</th>
            <th className="px-3 py-2 text-right font-medium">Margem Líquida</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/80 text-zinc-200">
          {companies.map((company) => (
            <tr key={company.cd_cvm} className="group hover:bg-zinc-900/50">
              <td className="px-3 py-2">
                <Link
                  to={`/empresas/${company.cd_cvm}`}
                  className="font-medium text-zinc-100 group-hover:text-cyan-300"
                >
                  {company.company_name}
                </Link>
              </td>
              <td className="px-3 py-2 font-mono text-xs text-zinc-300">
                {company.ticker_b3 ?? "—"}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-zinc-400">
                {company.cd_cvm}
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs text-zinc-200">
                {formatPercent(company.roe)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs text-zinc-200">
                {formatPercent(company.mg_ebit)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs text-zinc-200">
                {formatPercent(company.mg_liq)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
