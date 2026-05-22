import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchCompanyInfo, type CompanyInfoResult } from "@/lib/api/companyDetail";
import { ExportCompanyButton } from "./ExportCompanyButton";
import { Breadcrumbs } from "./Breadcrumbs";

export interface EntityHeaderProps {
  cdCvm: number;
  activeTab: "overview" | "statements" | "kpis";
}

export function EntityHeader({ cdCvm, activeTab }: EntityHeaderProps) {
  const [searchParams] = useSearchParams();
  const rawStmt = searchParams.get("stmt");
  const activeStatement = (rawStmt && ["DRE", "BPA", "BPP", "DFC"].includes(rawStmt.toUpperCase()))
    ? rawStmt.toUpperCase()
    : "DRE";

  const query = useQuery<CompanyInfoResult>({
    queryKey: ["company-info", cdCvm],
    queryFn: () => fetchCompanyInfo(cdCvm),
  });

  if (query.isLoading) {
    return <CardSkeleton title="Loading company details..." />;
  }

  if (query.isError) {
    return (
      <ErrorState
        message={query.error instanceof Error ? query.error.message : String(query.error)}
      />
    );
  }

  if (!query.data) {
    return <CardSkeleton title="Loading company details..." />;
  }

  if (query.data.mode === "browser") {
    return <BrowserModeBanner reason={query.data.reason} />;
  }

  if (query.data.mode === "desktop-not-found") {
    return (
      <ErrorState
        title="Company not found"
        message={
          query.data.catalog_lookup_pending
            ? "The CVM catalog lookup is still in progress. Try again in a moment."
            : `No record for CVM code ${query.data.cd_cvm}.`
        }
      />
    );
  }

  const info = query.data.info;
  const subtitle = info.nome_comercial && info.nome_comercial !== info.company_name
    ? info.nome_comercial
    : null;

  // Breadcrumbs items:
  // If sector is available: Sectors > [Sector Name] > [Company Name]
  // Else: Companies > [Company Name]
  const breadcrumbs = info.sector_name && info.sector_slug
    ? [
        { label: "Sectors", to: "/setores" },
        { label: info.sector_name, to: `/setores/${info.sector_slug}` },
        { label: `${info.company_name} (${info.ticker_b3 ?? info.cd_cvm})` },
      ]
    : [
        { label: "Companies", to: "/" },
        { label: `${info.company_name} (${info.ticker_b3 ?? info.cd_cvm})` },
      ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumbs items={breadcrumbs} />
        <Link to="/" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
          Company directory
        </Link>
      </div>

      <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
        <header className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold text-zinc-50 tracking-tight">
              {info.company_name}
            </h2>
            {subtitle ? (
              <p className="text-sm text-zinc-400 mt-0.5">{subtitle}</p>
            ) : null}
          </div>
          <div className="text-right">
            <div className="font-mono text-xs text-zinc-500">CVM {info.cd_cvm}</div>
            {info.ticker_b3 ? (
              <div className="font-mono text-sm text-zinc-200">{info.ticker_b3}</div>
            ) : null}
          </div>
        </header>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-3">
          <Field label="CNPJ" value={info.cnpj} mono />
          <Field label="Sector" value={info.setor_cvm} />
          <Field
            label="GICS sub-industry"
            value={info.gics_sub_industry ?? info.gics_industry ?? null}
          />
          <Field
            label="Latest year"
            value={info.latest_readable_year?.toString() ?? null}
            mono
          />
          <Field
            label="Years readable"
            value={info.readable_years_count.toString()}
            mono
          />
          <Field
            label="Has financial data"
            value={info.has_local_financial_reports ? "yes" : "no"}
          />
        </dl>

        {info.read_availability_message ? (
          <p className="mt-4 rounded border border-zinc-800 bg-zinc-950/60 p-3 text-xs text-zinc-400">
            {info.read_availability_message}
          </p>
        ) : null}

        <div className="mt-6 flex flex-wrap items-start justify-between gap-4 border-t border-zinc-800 pt-4">
          <div className="flex flex-wrap gap-2 text-xs mt-1">
            <TabLink to={`/empresas/${cdCvm}`} active={activeTab === "overview"}>
              Overview
            </TabLink>
            <TabLink to={`/empresas/${cdCvm}/demonstrativos`} active={activeTab === "statements"}>
              Financial statements
            </TabLink>
            <TabLink to={`/empresas/${cdCvm}/indicadores`} active={activeTab === "kpis"}>
              Indicadores
            </TabLink>
          </div>
          <div className="flex flex-col md:flex-row gap-6 items-start">
            {activeTab === "statements" && (
              <ExportCompanyButton
                cdCvm={info.cd_cvm}
                statementType={activeStatement}
                scopeNote={`Only the cover, ${activeStatement} sheet, and metadata.`}
              />
            )}
            <ExportCompanyButton
              cdCvm={info.cd_cvm}
              scopeNote="Full company workbook — includes DRE, BPA, BPP, DFC (plus DVA/DMPL when available) and KPIs."
            />
          </div>
        </div>
      </article>
    </div>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string | null;
  mono?: boolean;
}) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs uppercase tracking-wider text-zinc-500">{label}</dt>
      <dd className={mono ? "font-mono text-sm text-zinc-200" : "text-sm text-zinc-200"}>
        {value ?? "—"}
      </dd>
    </div>
  );
}

function TabLink({
  to,
  active,
  children,
}: {
  to: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return active ? (
    <span className="rounded-md border border-cyan-500/50 bg-cyan-500/10 px-3 py-1.5 font-medium text-cyan-100">
      {children}
    </span>
  ) : (
    <Link
      to={to}
      className="rounded-md border border-zinc-700 px-3 py-1.5 text-zinc-200 hover:border-cyan-600 hover:text-cyan-100 transition-colors"
    >
      {children}
    </Link>
  );
}

function CardSkeleton({ title }: { title: string }) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <p className="text-sm text-zinc-500 animate-pulse">{title}</p>
    </article>
  );
}

function BrowserModeBanner({ reason }: { reason: string }) {
  return (
    <article className="rounded-lg border border-amber-900/60 bg-amber-950/30 p-6 text-amber-200 shadow-lg">
      <p className="font-medium">Browser-mode preview</p>
      <p className="mt-1 text-sm text-amber-200/80">{reason}</p>
    </article>
  );
}

function ErrorState({
  message,
  title = "Error",
}: {
  message: string;
  title?: string;
}) {
  return (
    <article
      role="alert"
      className="rounded-lg border border-rose-900/60 bg-rose-950/40 p-6 text-rose-200 shadow-lg"
    >
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-sm text-rose-200/80">{message}</p>
    </article>
  );
}
