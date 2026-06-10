import { useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { IdentifierBadge } from "@/components/data/IdentifierBadge";
import { fetchCompanyInfo, type CompanyInfoResult } from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { formatBRDateTime } from "@/lib/format/date";
import { formatCNPJ } from "@/lib/format/cnpj";
import { ExportCompanyButton } from "./ExportCompanyButton";
import { Breadcrumbs } from "./Breadcrumbs";
import { StateBanner } from "./feedback/StateBanner";

export interface EntityHeaderProps {
  cdCvm: number;
  activeTab: "overview" | "statements" | "kpis" | "mapping";
  showExports?: boolean;
}

export function EntityHeader({
  cdCvm,
  activeTab,
  showExports = true,
}: EntityHeaderProps) {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [searchParams] = useSearchParams();
  const rawStmt = searchParams.get("stmt");
  const activeStatement = (rawStmt && ["DRE", "BPA", "BPP", "DFC"].includes(rawStmt.toUpperCase()))
    ? rawStmt.toUpperCase()
    : "DRE";

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const query = useQuery<CompanyInfoResult>({
    queryKey: ["company-info", cdCvm],
    queryFn: () => fetchCompanyInfo(cdCvm),
    enabled: bridgeReady && Number.isFinite(cdCvm) && cdCvm > 0,
  });

  if (!bridgeReady || query.isLoading) {
    return <StateBanner variant="loading" title="Loading company data…" />;
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
    return <StateBanner variant="loading" title="Loading company data…" />;
  }

  if (query.data.mode === "browser") {
    return <StateBanner variant="browser-only" message={query.data.reason} />;
  }

  if (query.data.mode === "desktop-not-found") {
    return (
      <StateBanner
        variant="error"
        title="Company not found"
        message={
          query.data.catalog_lookup_pending
            ? "CVM catalog is still loading. Try again in a moment."
            : `No record for CVM ${query.data.cd_cvm}.`
        }
      />
    );
  }

  const info = query.data.info;
  const subtitle = info.nome_comercial && info.nome_comercial !== info.company_name
    ? info.nome_comercial
    : null;
  const latestPeriodDisplay = info.latest_financial_period_display;
  const localDataLabel = info.has_local_financial_reports ? "local data" : "no local data";
  const currentDataLabel = latestPeriodDisplay ? `through ${latestPeriodDisplay}` : "partial";
  const dataFreshnessMessage = latestPeriodDisplay
    ? `Updated through ${latestPeriodDisplay}.`
    : info.has_local_financial_reports
      ? "Local financial rows exist, but no complete BPA/BPP/DRE/DFC period is available."
      : "No local financial statements found for this company.";

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
              <IdentifierBadge muted>{info.sector_name ?? info.setor_cvm ?? "sector n/a"}</IdentifierBadge>
              {info.gics_sub_industry ?? info.gics_industry ? (
                <IdentifierBadge muted>
                  {info.gics_sub_industry ?? info.gics_industry}
                </IdentifierBadge>
              ) : null}
              <StatusChip tone={info.has_local_financial_reports ? "ok" : "warn"}>
                {localDataLabel}
              </StatusChip>
              <StatusChip tone={latestPeriodDisplay ? "ok" : "warn"}>
                {currentDataLabel}
              </StatusChip>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5 xl:grid-cols-2 xl:text-right">
            <MetaField
              label="Latest period"
              value={latestPeriodDisplay}
              mono
            />
            <MetaField
              label="Annual years"
              value={info.readable_years_count.toString()}
              mono
            />
            <MetaField label="CNPJ" value={formatCNPJ(info.cnpj)} mono />
            <MetaField
              label={info.is_active === false ? "Ticker (historical)" : "Ticker"}
              value={info.ticker_b3 ? info.ticker_b3 : "Not available"}
              mono
            />
            <MetaField
              label="Read model"
              value={formatBRDateTime(info.read_model_updated_at)}
              mono
            />
          </div>
        </header>

        {dataFreshnessMessage ? (
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
            {dataFreshnessMessage}
          </p>
        ) : null}

        {showExports ? (
          <div
            className="flex flex-col items-start gap-4 md:flex-row md:items-center md:justify-end"
            style={{ padding: "10px 16px" }}
          >
            {activeTab === "statements" && (
              <ExportCompanyButton
                cdCvm={info.cd_cvm}
                statementType={activeStatement}
                scopeLabel={`${activeStatement} selected`}
                scopeNote={`Exports the cover, metadata, and ${activeStatement} sheet.`}
              />
            )}
            <ExportCompanyButton
              cdCvm={info.cd_cvm}
              scopeLabel={activeTab === "kpis" ? "KPI workbook" : "Full workbook"}
              scopeNote={
                activeTab === "kpis"
                  ? "Exports the full company workbook, including KPIs and available statements."
                  : "Includes available statements, KPIs, and local metadata."
              }
            />
          </div>
        ) : null}
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
