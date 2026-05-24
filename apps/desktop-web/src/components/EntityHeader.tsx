import type { CSSProperties, ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { IdentifierBadge } from "@/components/data/IdentifierBadge";
import { fetchCompanyInfo, type CompanyInfoResult } from "@/lib/api/companyDetail";
import { formatBRDateTime } from "@/lib/format/date";
import { ExportCompanyButton } from "./ExportCompanyButton";
import { Breadcrumbs } from "./Breadcrumbs";
import { StateBanner } from "./feedback/StateBanner";

export interface EntityHeaderProps {
  cdCvm: number;
  activeTab: "overview" | "statements" | "kpis";
  showExports?: boolean;
}

export function EntityHeader({
  cdCvm,
  activeTab,
  showExports = true,
}: EntityHeaderProps) {
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
    return <StateBanner variant="loading" title="Carregando dados da empresa…" />;
  }

  if (query.isError) {
    return (
      <StateBanner
        variant="error"
        message={query.error instanceof Error ? query.error.message : String(query.error)}
        onRetry={() => query.refetch()}
      />
    );
  }

  if (!query.data) {
    return <StateBanner variant="loading" title="Carregando dados da empresa…" />;
  }

  if (query.data.mode === "browser") {
    return <StateBanner variant="browser-only" message={query.data.reason} />;
  }

  if (query.data.mode === "desktop-not-found") {
    return (
      <StateBanner
        variant="error"
        title="Empresa não encontrada"
        message={
          query.data.catalog_lookup_pending
            ? "Catálogo CVM ainda carregando. Tente novamente em instantes."
            : `Sem registro para CVM ${query.data.cd_cvm}.`
        }
      />
    );
  }

  const info = query.data.info;
  const subtitle = info.nome_comercial && info.nome_comercial !== info.company_name
    ? info.nome_comercial
    : null;
  const localDataLabel = info.has_local_financial_reports ? "dados locais" : "sem base local";
  const currentDataLabel = info.has_readable_current_data ? "atual legível" : "parcial";

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
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumbs items={breadcrumbs} />
        <Link
          to="/"
          className="focus-visible:outline focus-visible:outline-1"
          style={{
            color: "var(--color-text-tertiary)",
            fontSize: "var(--text-xs)",
            outlineColor: "var(--color-border-focus)",
          }}
        >
          Company directory
        </Link>
      </div>

      <article
        style={{
          background: "var(--color-surface-2)",
          border: "1px solid var(--color-border-subtle)",
          borderRadius: "var(--radius-md)",
          overflow: "hidden",
        }}
      >
        <header
          className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto]"
          style={{
            borderBottom: "1px solid var(--color-border-subtle)",
            padding: "16px",
          }}
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1
                className="truncate"
                style={{
                  color: "var(--color-text-primary)",
                  fontSize: "var(--text-2xl)",
                  fontWeight: 650,
                  letterSpacing: 0,
                  lineHeight: 1.2,
                  margin: 0,
                }}
              >
              {info.company_name}
              </h1>
              <IdentifierBadge label="CVM">{info.cd_cvm}</IdentifierBadge>
              {info.ticker_b3 ? (
                <IdentifierBadge label="B3">{info.ticker_b3}</IdentifierBadge>
              ) : null}
            </div>
            {subtitle ? (
              <p
                style={{
                  color: "var(--color-text-secondary)",
                  fontSize: "var(--text-sm)",
                  margin: "4px 0 0",
                }}
              >
                {subtitle}
              </p>
            ) : null}
            <div className="mt-3 flex flex-wrap gap-2">
              <IdentifierBadge muted>{info.sector_name ?? info.setor_cvm ?? "setor n/d"}</IdentifierBadge>
              {info.gics_sub_industry ?? info.gics_industry ? (
                <IdentifierBadge muted>
                  {info.gics_sub_industry ?? info.gics_industry}
                </IdentifierBadge>
              ) : null}
              <StatusChip tone={info.has_local_financial_reports ? "ok" : "warn"}>
                {localDataLabel}
              </StatusChip>
              <StatusChip tone={info.has_readable_current_data ? "ok" : "warn"}>
                {currentDataLabel}
              </StatusChip>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-2 xl:text-right">
            <MetaField
              label="Ano mais recente"
              value={info.latest_readable_year?.toString() ?? null}
              mono
            />
            <MetaField
              label="Anos legíveis"
              value={info.readable_years_count.toString()}
              mono
            />
            <MetaField label="CNPJ" value={info.cnpj} mono />
            <MetaField
              label="Modelo leitura"
              value={formatBRDateTime(info.read_model_updated_at)}
              mono
            />
          </div>
        </header>

        {info.read_availability_message ? (
          <p
            style={{
              background: "var(--color-surface-1)",
              borderBottom: "1px solid var(--color-border-subtle)",
              color: "var(--color-text-secondary)",
              fontSize: "var(--text-xs)",
              margin: 0,
              padding: "10px 16px",
            }}
          >
            {info.read_availability_message}
          </p>
        ) : null}

        <div
          className="flex flex-wrap items-start justify-between gap-4"
          style={{ padding: "10px 16px" }}
        >
          <nav aria-label="Company detail sections" className="flex flex-wrap gap-2">
            <TabLink to={`/empresas/${cdCvm}`} active={activeTab === "overview"}>
              Overview
            </TabLink>
            <TabLink to={`/empresas/${cdCvm}/demonstrativos`} active={activeTab === "statements"}>
              Financial statements
            </TabLink>
            <TabLink to={`/empresas/${cdCvm}/indicadores`} active={activeTab === "kpis"}>
              Indicadores
            </TabLink>
          </nav>
          {showExports ? (
            <div className="flex flex-col items-start gap-4 md:flex-row">
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
          ) : null}
        </div>
      </article>
    </div>
  );
}

function MetaField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string | null;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt
        style={{
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-2xs)",
          letterSpacing: "0.04em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </dt>
      <dd
        className={mono ? "font-mono truncate" : "truncate"}
        style={{
          color: "var(--color-text-secondary)",
          fontSize: "var(--text-xs)",
          margin: "2px 0 0",
        }}
        title={value ?? undefined}
      >
        {value ?? "—"}
      </dd>
    </div>
  );
}

function StatusChip({
  tone,
  children,
}: {
  tone: "ok" | "warn";
  children: ReactNode;
}) {
  const color = tone === "ok" ? "var(--color-state-ok)" : "var(--color-state-warn)";
  return (
    <span
      style={{
        alignItems: "center",
        border: `1px solid ${color}`,
        borderRadius: "var(--radius-sm)",
        color,
        display: "inline-flex",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-xs)",
        gap: 5,
        minHeight: 22,
        padding: "2px 7px",
      }}
    >
      <span aria-hidden="true">{tone === "ok" ? "●" : "▲"}</span>
      {children}
    </span>
  );
}

function TabLink({
  to,
  active,
  children,
}: {
  to: string;
  active: boolean;
  children: ReactNode;
}) {
  const baseStyle: CSSProperties = {
    border: "1px solid var(--color-border-default)",
    borderRadius: "var(--radius-sm)",
    display: "inline-flex",
    fontSize: "var(--text-xs)",
    fontWeight: 500,
    minHeight: 24,
    padding: "3px 9px",
    textDecoration: "none",
  };
  return active ? (
    <span
      style={{
        ...baseStyle,
        background: "var(--color-surface-3)",
        borderColor: "var(--color-action-primary)",
        color: "var(--color-action-primary)",
      }}
    >
      {children}
    </span>
  ) : (
    <Link
      to={to}
      className="focus-visible:outline focus-visible:outline-1"
      style={{
        ...baseStyle,
        color: "var(--color-text-secondary)",
        outlineColor: "var(--color-border-focus)",
      }}
    >
      {children}
    </Link>
  );
}
