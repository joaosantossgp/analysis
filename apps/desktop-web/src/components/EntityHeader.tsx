import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import { ClassificationEditor } from "@/components/ClassificationEditor";
import { IdentifierBadge } from "@/components/data/IdentifierBadge";
import { fetchCompanyInfo, fetchCompanyConnections, type CompanyInfoResult, type CompanyConnectionsResult } from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { CompanyClassification, CompanyInfo } from "@/lib/bridge/types";
import { CLASSIFICATION_STATUS_LABEL } from "@/lib/classification";
import { formatCNPJ } from "@/lib/format/cnpj";
import { StateBanner } from "./feedback/StateBanner";

export interface EntityHeaderProps {
  cdCvm: number;
  activeTab: "overview" | "statements" | "mapping";
  rightPanel?: ReactNode;
}

type CompanyHeaderClassificationInput = Pick<
  CompanyInfo,
  | "gics_sector"
  | "gics_industry_group"
  | "gics_industry"
  | "gics_sub_industry"
  | "sector_name"
  | "setor_cvm"
  | "classification"
>;

export type CompanyHeaderClassificationBadge = {
  label: "Sector" | "Industry Group" | "Industry" | "Sub-industry";
  value: string;
  title?: string;
};

const MISSING_CLASSIFICATION = "—";

export function getCompanyHeaderClassificationBadges(
  info: CompanyHeaderClassificationInput,
): CompanyHeaderClassificationBadge[] {
  const cvmSector = cleanClassification(info.sector_name) || cleanClassification(info.setor_cvm);
  const industryGroup = cleanClassification(info.gics_industry_group);
  const classification = info.classification;
  const status = CLASSIFICATION_STATUS_LABEL[classification?.origin ?? ""];
  const sectorTitle = [
    cvmSector ? `CVM sector: ${cvmSector}` : null,
    classification?.origin === "unclassified" && classification.unclassified_reason
      ? `Not classifiable: ${classification.unclassified_reason}`
      : null,
    classification?.origin === "pending" ? "No GICS classification yet; curation pending." : null,
  ].filter(Boolean).join("\n");

  return [
    {
      label: "Sector",
      value: cleanClassification(info.gics_sector) || status || MISSING_CLASSIFICATION,
      title: sectorTitle || undefined,
    },
    {
      label: "Industry Group",
      value: industryGroup || MISSING_CLASSIFICATION,
    },
    { label: "Industry", value: cleanClassification(info.gics_industry) || MISSING_CLASSIFICATION },
    {
      label: "Sub-industry",
      value: cleanClassification(info.gics_sub_industry) || MISSING_CLASSIFICATION,
      title:
        classification?.origin === "curated"
          ? curatedClassificationTitle(classification)
          : classification?.origin === "user"
            ? userClassificationTitle(classification)
            : undefined,
    },
  ];
}

function curatedClassificationTitle(classification: CompanyClassification): string {
  return [
    `GICS ${classification.sub_industry_code ?? ""} · curated by CVMAnalytics, not an official MSCI/S&P classification`,
    classification.confidence ? `Confidence: ${classification.confidence}` : null,
    classification.rationale,
    classification.evidence_url ? `Source: ${classification.evidence_url}` : null,
  ].filter(Boolean).join("\n");
}

function userClassificationTitle(classification: CompanyClassification): string {
  const edit = classification.user_edit;
  const curated = edit?.curated_sub_industry
    ? `${edit.curated_sub_industry} (${edit.curated_sub_industry_code})`
    : "none";
  return [
    `GICS ${classification.gics_sub_industry_code ?? ""} · edited by you, stored locally`,
    `Curated classification: ${curated}`,
  ].join("\n");
}

export function formatCompanyPeriodCoverage(
  latestPeriod: string | null | undefined,
  yearsAvailable: number | null | undefined,
): string {
  const period = String(latestPeriod ?? "").trim();
  const fullYears = typeof yearsAvailable === "number" && Number.isInteger(yearsAvailable)
    ? yearsAvailable
    : null;
  if (!period || fullYears == null || fullYears <= 0) {
    return period || MISSING_CLASSIFICATION;
  }

  const quarterMatch = /^(?<quarter>[1-4])Q\d{2}$/.exec(period);
  const quarterCount = fullYears * 4 + (quarterMatch ? Number(quarterMatch.groups?.quarter) : 0);
  return `${period} · ${fullYears}Y · ${quarterCount}Q`;
}

export function EntityHeader({
  cdCvm,
  activeTab: _activeTab,
  rightPanel,
}: EntityHeaderProps) {
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

  const query = useQuery<CompanyInfoResult>({
    queryKey: ["company-info", cdCvm],
    queryFn: () => fetchCompanyInfo(cdCvm),
    enabled: bridgeReady && Number.isFinite(cdCvm) && cdCvm > 0,
  });

  const connectionsQuery = useQuery<CompanyConnectionsResult>({
    queryKey: ["company-connections", cdCvm],
    queryFn: () => fetchCompanyConnections(cdCvm),
    enabled: bridgeReady && Number.isFinite(cdCvm) && cdCvm > 0,
    staleTime: 120_000,
  });

  const connections = connectionsQuery.data?.mode === "desktop" ? connectionsQuery.data.connections : null;

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
  const latestPeriodDisplay = info.latest_financial_period_display;
  const periodCoverage = formatCompanyPeriodCoverage(latestPeriodDisplay, info.readable_years_count);
  const dataFreshnessMessage = latestPeriodDisplay
    ? `Updated through ${latestPeriodDisplay}.`
    : info.has_local_financial_reports
      ? "Local financial rows exist, but no complete BPA/BPP/DRE/DFC period is available."
      : "No local financial statements found for this company.";

  return (
    <article
      style={{
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      <header
        className={rightPanel ? "grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(620px,0.9fr)]" : undefined}
        style={{
          borderBottom: "1px solid var(--color-border-subtle)",
          flex: 1,
          padding: "14px 16px 12px",
        }}
      >
        <div className="min-w-0 space-y-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h1
              className="min-w-0 max-w-full truncate"
              style={{
                color: "var(--color-text-primary)",
                fontSize: "var(--text-2xl)",
                fontWeight: 650,
                letterSpacing: 0,
                lineHeight: 1.05,
                margin: 0,
              }}
            >
            {info.company_name}
            </h1>
            {info.ticker_b3 ? (
              <IdentifierBadge label="B3">{info.ticker_b3}</IdentifierBadge>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {getCompanyHeaderClassificationBadges(info).map((badge) => (
              <IdentifierBadge key={badge.label} label={badge.label} muted title={badge.title}>
                {badge.value}
              </IdentifierBadge>
            ))}
            <ClassificationEditor cdCvm={cdCvm} classification={info.classification} />
            {connections && (
              <>
                {connections.mapped_distributors > 0 && (
                  <ConnectionChip
                    color="sky"
                    title={`${connections.mapped_distributors} distribution concession(s) linked`}
                  >
                    Dist ×{connections.mapped_distributors}
                  </ConnectionChip>
                )}
                {connections.mapped_plants > 0 && (
                  <ConnectionChip
                    color="emerald"
                    title={`${connections.mapped_plants} generation plant(s) — ${connections.total_capacity_mw > 0 ? `${connections.total_capacity_mw.toLocaleString("en-US", { maximumFractionDigits: 1 })} MW total` : "capacity unknown"}`}
                  >
                    Gen ×{connections.mapped_plants}
                  </ConnectionChip>
                )}
              </>
            )}
          </div>
        </div>

        {rightPanel ? <aside className="min-w-0">{rightPanel}</aside> : null}
      </header>

      <dl
        className="flex flex-wrap items-center gap-x-4 gap-y-1"
        style={{
          background: "var(--color-surface-1)",
          borderBottom: "1px solid var(--color-border-subtle)",
          color: "var(--color-text-secondary)",
          fontSize: "var(--text-xs)",
          margin: 0,
          padding: "7px 16px",
        }}
      >
        <InlineMeta label="CNPJ" value={formatCNPJ(info.cnpj)} mono />
        <InlineMeta label="CVM" value={String(info.cd_cvm)} mono />
        <InlineMeta label="Latest available period" value={periodCoverage} mono title={dataFreshnessMessage} />
      </dl>
    </article>
  );
}

function cleanClassification(value: string | null | undefined): string | null {
  const trimmed = String(value ?? "").trim();
  return trimmed.length > 0 ? trimmed : null;
}

function InlineMeta({
  label,
  value,
  mono = false,
  title,
}: {
  label: string;
  value: string | null;
  mono?: boolean;
  title?: string;
}) {
  return (
    <div className="flex min-w-0 items-baseline gap-1.5">
      <dt
        className="shrink-0"
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
        className={mono ? "min-w-0 truncate font-mono" : "min-w-0 truncate"}
        style={{
          color: "var(--color-text-secondary)",
          fontSize: "var(--text-xs)",
          margin: 0,
        }}
        title={title ?? value ?? undefined}
      >
        {value ?? "—"}
      </dd>
    </div>
  );
}

function ConnectionChip({
  color,
  title,
  children,
}: {
  color: "sky" | "emerald";
  title?: string;
  children: ReactNode;
}) {
  const palette = {
    sky:   { bg: "rgba(14,165,233,0.08)", border: "rgba(14,165,233,0.25)", text: "rgb(56,189,248)" },
    emerald: { bg: "rgba(16,185,129,0.08)", border: "rgba(16,185,129,0.25)", text: "rgb(52,211,153)" },
  }[color];
  return (
    <span
      title={title}
      style={{
        alignItems: "center",
        background: palette.bg,
        border: `1px solid ${palette.border}`,
        borderRadius: "var(--radius-sm)",
        color: palette.text,
        cursor: title ? "help" : "default",
        display: "inline-flex",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-xs)",
        fontWeight: 600,
        gap: 4,
        minHeight: 22,
        padding: "2px 7px",
      }}
    >
      <span aria-hidden="true">◆</span>
      {children}
    </span>
  );
}
