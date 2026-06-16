import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import { IdentifierBadge } from "@/components/data/IdentifierBadge";
import { fetchCompanyInfo, fetchCompanyConnections, type CompanyInfoResult, type CompanyConnectionsResult } from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { formatCNPJ } from "@/lib/format/cnpj";
import { StateBanner } from "./feedback/StateBanner";

export interface EntityHeaderProps {
  cdCvm: number;
  activeTab: "overview" | "statements" | "mapping";
}

export function EntityHeader({
  cdCvm,
  activeTab: _activeTab,
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
  const subtitle = info.nome_comercial && info.nome_comercial !== info.company_name
    ? info.nome_comercial
    : null;
  const latestPeriodDisplay = info.latest_financial_period_display;
  const localDataLabel = info.has_local_financial_reports ? "local data" : "no local data";
  const dataFreshnessMessage = latestPeriodDisplay
    ? `Updated through ${latestPeriodDisplay}.`
    : info.has_local_financial_reports
      ? "Local financial rows exist, but no complete BPA/BPP/DRE/DFC period is available."
      : "No local financial statements found for this company.";
  const yearsAvailableLabel = info.readable_years_count === 1 ? "1 year available" : `${info.readable_years_count} years available`;

  return (
    <article
      style={{
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
      }}
    >
      <header
        className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]"
        style={{
          borderBottom: "1px solid var(--color-border-subtle)",
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
            <IdentifierBadge label="CVM" muted>{info.cd_cvm}</IdentifierBadge>
          </div>
          {subtitle ? (
            <p
              className="truncate"
              style={{
                color: "var(--color-text-secondary)",
                fontSize: "var(--text-xs)",
                margin: 0,
              }}
            >
              {subtitle}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <IdentifierBadge muted>{info.sector_name ?? info.setor_cvm ?? "sector n/a"}</IdentifierBadge>
            {info.gics_sub_industry ?? info.gics_industry ? (
              <IdentifierBadge muted>
                {info.gics_sub_industry ?? info.gics_industry}
              </IdentifierBadge>
            ) : null}
            <StatusChip tone={info.has_local_financial_reports ? "ok" : "warn"}>
              {localDataLabel}
            </StatusChip>
            {connections && (
              <>
                {connections.has_financials && (
                  <ConnectionChip color="amber" title="Has financial statements in the local database">
                    Financials
                  </ConnectionChip>
                )}
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

        <div className="flex min-w-[180px] flex-col items-start gap-1 lg:items-end lg:text-right">
          <span
            style={{
              color: "var(--color-text-tertiary)",
              fontSize: "var(--text-2xs)",
              fontWeight: 650,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            Data through
          </span>
          <span
            className="font-mono"
            style={{
              color: latestPeriodDisplay ? "var(--color-text-primary)" : "var(--color-state-warn)",
              fontSize: "var(--text-2xl)",
              fontVariantNumeric: "tabular-nums",
              fontWeight: 700,
              lineHeight: 1,
            }}
            title={dataFreshnessMessage}
          >
            {latestPeriodDisplay ?? "—"}
          </span>
          <span
            className="font-mono"
            style={{
              color: latestPeriodDisplay ? "var(--color-text-tertiary)" : "var(--color-state-warn)",
              fontSize: "var(--text-2xs)",
            }}
          >
            local read model
          </span>
        </div>
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
        <InlineMeta label="Years available" value={yearsAvailableLabel} mono />
        <InlineMeta
          label={info.is_active === false ? "Historical ticker" : "Ticker"}
          value={info.ticker_b3 ? info.ticker_b3 : "Not available"}
          mono
        />
      </dl>
    </article>
  );
}

function InlineMeta({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string | null;
  mono?: boolean;
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

function ConnectionChip({
  color,
  title,
  children,
}: {
  color: "amber" | "sky" | "emerald";
  title?: string;
  children: ReactNode;
}) {
  const palette = {
    amber: { bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.25)", text: "rgb(251,191,36)" },
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
