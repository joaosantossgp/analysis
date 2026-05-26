import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { fetchSectorDetail, type SectorDetailResult } from "@/lib/api/sectors";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";

function parseYear(raw: string | null): number | null {
  if (!raw) return null;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}

export function SectorDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug ?? "";
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

  const query = useQuery<SectorDetailResult>({
    queryKey: ["sector-detail", slug, requestedYear],
    queryFn: () => fetchSectorDetail(slug, requestedYear),
    enabled: bridgeReady && slug.length > 0,
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

  const breadcrumbsList = useMemo(() => [
    { label: "Sectors", to: "/setores" },
    { label: detail?.sector_name ?? slug },
  ], [detail, slug]);

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg space-y-4">
      <PageHeader
        title={detail?.sector_name ?? "Sector"}
        subtitle="GICS sector · CVMBridge.get_sector_detail"
        breadcrumbs={breadcrumbsList}
        actions={<Status query={query} notFound={notFound} />}
      />

      <BodyHeader detail={detail} onYearChange={setYear} />

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

// Breadcrumbs component removed as it is now unified in @/components/PageHeader

function Status({
  query,
  notFound,
}: {
  query: ReturnType<typeof useQuery<SectorDetailResult>>;
  notFound: boolean;
}) {
  if (query.isLoading) return <span className="text-xs text-zinc-500">◌ Loading…</span>;
  if (query.isFetching) return <span className="text-xs text-amber-300">↻ Refreshing…</span>;
  if (query.isError) return <span className="text-xs text-rose-400">! Error</span>;
  if (notFound) return <span className="text-xs text-rose-400">! Not found</span>;
  if (query.data?.mode === "browser")
    return <span className="text-xs text-amber-300">▲ Browser mode</span>;
  return null;
}

function BodyHeader({
  detail,
  onYearChange,
}: {
  detail: { company_count: number; available_years: number[]; selected_year: number; sector_slug: string } | null;
  onYearChange: (year: number | null) => void;
}) {
  if (!detail) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded border border-zinc-800 bg-zinc-950/40 px-3 py-2">
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
          htmlFor="sector-year"
          className="text-[10px] uppercase tracking-widest text-zinc-500"
        >
          Year
        </label>
        <select
          id="sector-year"
          value={detail.selected_year}
          onChange={(event) => onYearChange(Number.parseInt(event.target.value, 10))}
          disabled={detail.available_years.length === 0}
          className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 focus:border-cyan-600 focus:outline-none focus:ring-1 focus:ring-cyan-600 disabled:opacity-50"
        >
          {detail.available_years.length === 0 ? (
            <option value={detail.selected_year}>{detail.selected_year}</option>
          ) : (
            detail.available_years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))
          )}
        </select>
        <Link
          to={`/empresas?sector=${encodeURIComponent(detail.sector_slug)}`}
          className="ml-2 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 hover:border-cyan-700 hover:text-cyan-300"
        >
          Open in directory →
        </Link>
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
    <div className="mb-3">
      <label
        htmlFor="sector-company-filter"
        className="mb-1 block text-[10px] uppercase tracking-widest text-zinc-500"
      >
        Filter companies in sector
      </label>
      <input
        id="sector-company-filter"
        type="search"
        autoComplete="off"
        spellCheck={false}
        placeholder="Name, ticker, CVM code, or sub-industry…"
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
  query: ReturnType<typeof useQuery<SectorDetailResult>>;
  notFound: boolean;
  detail: {
    sector_slug: string;
    companies: Array<{
      cd_cvm: number;
      company_name: string;
      ticker_b3: string | null;
      gics_sub_industry: string | null;
    }>;
  } | null;
  filteredCompanies: Array<{
    cd_cvm: number;
    company_name: string;
    ticker_b3: string | null;
    gics_sub_industry: string | null;
  }>;
  onClearCompanyFilter: () => void;
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
    return (
      <StateBanner
        variant="browser-only"
        message={query.data.reason}
      />
    );
  }
  if (notFound) {
    return (
      <StateBanner
        variant="empty"
        title="Setor não encontrado"
        message="Este setor não existe no banco de dados local."
      >
        <Link
          to="/setores"
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-1"
        >
          Voltar para setores
        </Link>
      </StateBanner>
    );
  }
  if (query.isLoading || !detail) {
    return <StateBanner variant="loading" />;
  }
  if (detail.companies.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="Sem empresas"
        message="Nenhuma empresa registrada neste setor. Execute Atualizar Base para popular os dados."
      />
    );
  }
  if (filteredCompanies.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="Sem resultados"
        message="Nenhuma empresa corresponde ao filtro aplicado neste setor."
      >
        <button
          type="button"
          onClick={onClearCompanyFilter}
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-1"
        >
          Limpar filtro
        </button>
      </StateBanner>
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
    gics_sub_industry: string | null;
  }>;
}) {
  return (
    <div className="overflow-hidden rounded border border-zinc-800">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-zinc-900/80 text-left text-[10px] uppercase tracking-wider text-zinc-500">
            <th scope="col" className="px-3 py-2 font-medium">Company</th>
            <th scope="col" className="px-3 py-2 font-medium">Ticker</th>
            <th scope="col" className="px-3 py-2 font-medium">CVM</th>
            <th scope="col" className="px-3 py-2 font-medium">Sub-industry</th>
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
              <td className="px-3 py-2 text-xs text-zinc-500">
                {company.gics_sub_industry ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
