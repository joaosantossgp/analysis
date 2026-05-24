import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { DeltaBadge } from "@/components/data/DeltaBadge";
import { IdentifierBadge } from "@/components/data/IdentifierBadge";
import { MetricTape, type MetricTapeItem } from "@/components/data/MetricTape";
import { NumberCell } from "@/components/data/NumberCell";
import { Sparkline } from "@/components/data/Sparkline";
import { EntityHeader } from "@/components/EntityHeader";
import { ExportCompanyButton } from "@/components/ExportCompanyButton";
import { CompanyRefreshPanel } from "@/components/CompanyRefreshPanel";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import {
  fetchCompanyInfo,
  fetchCompanyKpis,
  fetchCompanyYears,
  type CompanyInfoResult,
  type CompanyKpisResult,
  type CompanyYearsResultUI,
} from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { CompanyInfo, KPIBundle, TabularRow } from "@/lib/bridge/types";
import { formatBRDateTime } from "@/lib/format/date";
import { formatUnit } from "@/lib/formatters";

const MAX_KPI_YEARS = 5;
const TAPE_KPI_IDS = ["MG_EBITDA", "MG_LIQ", "ROE", "DIV_EBITDA"] as const;

export function CompanyDetailPage() {
  const params = useParams<{ cdCvm: string }>();
  const cdCvm = Number.parseInt(params.cdCvm ?? "", 10);
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

  if (!Number.isFinite(cdCvm) || cdCvm <= 0) {
    return (
      <StateBanner variant="error" message={`CVM inválido: "${params.cdCvm}"`} />
    );
  }

  return (
    <section className="space-y-4">
      <EntityHeader cdCvm={cdCvm} activeTab="overview" showExports={false} />
      <CompanyReferenceWorkspace cdCvm={cdCvm} bridgeReady={bridgeReady} />
    </section>
  );
}

function CompanyReferenceWorkspace({
  cdCvm,
  bridgeReady,
}: {
  cdCvm: number;
  bridgeReady: boolean;
}) {
  const companyQuery = useQuery<CompanyInfoResult>({
    queryKey: ["company-info", cdCvm],
    queryFn: () => fetchCompanyInfo(cdCvm),
  });

  const yearsQuery = useQuery<CompanyYearsResultUI>({
    queryKey: ["company-years", cdCvm],
    queryFn: () => fetchCompanyYears(cdCvm),
    enabled: bridgeReady,
  });

  const allYears = yearsQuery.data?.mode === "desktop" ? yearsQuery.data.years : [];
  const selectedYears = useMemo(() => {
    if (allYears.length === 0) return [] as number[];
    const sorted = [...allYears].sort((a, b) => b - a);
    return sorted.slice(0, MAX_KPI_YEARS).sort((a, b) => a - b);
  }, [allYears]);

  const kpiQuery = useQuery<CompanyKpisResult>({
    queryKey: ["company-kpis", cdCvm, selectedYears.join(",")],
    queryFn: () => fetchCompanyKpis(cdCvm, selectedYears),
    enabled: bridgeReady && selectedYears.length > 0,
  });

  const info =
    companyQuery.data?.mode === "desktop" ? companyQuery.data.info : null;
  const bundle = kpiQuery.data?.mode === "desktop" ? kpiQuery.data.bundle : null;
  const metricItems = useMemo(
    () => buildMetricTapeItems(info, bundle, selectedYears),
    [bundle, info, selectedYears],
  );

  return (
    <div className="space-y-4">
      <MetricTape items={metricItems} ariaLabel="Company reference metrics" />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4">
          <WorkspaceLinksPanel cdCvm={cdCvm} />
          <KpiHistoryPanel
            yearsQuery={yearsQuery}
            kpiQuery={kpiQuery}
            selectedYears={selectedYears}
            bridgeReady={bridgeReady}
          />
        </div>

        <aside className="space-y-4 self-start xl:sticky xl:top-0">
          <CompanyRefreshPanel cdCvm={cdCvm} bridgeReady={bridgeReady} />
          <ExportPanel cdCvm={cdCvm} />
          <DataStatusPanel
            companyQuery={companyQuery}
            yearsQuery={yearsQuery}
            kpiQuery={kpiQuery}
            selectedYears={selectedYears}
          />
        </aside>
      </div>
    </div>
  );
}

function WorkspaceLinksPanel({ cdCvm }: { cdCvm: number }) {
  return (
    <Panel
      dense
      headingLevel={2}
      title="Reference workspace"
      subtitle="CVM company dossier"
    >
      <div className="grid gap-2 sm:grid-cols-2">
        <ReferenceLink to={`/empresas/${cdCvm}/indicadores`} glyph="λ">
          Indicadores
        </ReferenceLink>
        <ReferenceLink to={`/empresas/${cdCvm}/demonstrativos`} glyph="▤">
          Demonstrativos
        </ReferenceLink>
      </div>
    </Panel>
  );
}

function ReferenceLink({
  to,
  glyph,
  children,
}: {
  to: string;
  glyph: string;
  children: ReactNode;
}) {
  return (
    <Link
      to={to}
      className="focus-visible:outline focus-visible:outline-1"
      style={{
        alignItems: "center",
        background: "var(--color-surface-1)",
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-sm)",
        color: "var(--color-text-primary)",
        display: "flex",
        fontSize: "var(--text-sm)",
        gap: 10,
        minHeight: 36,
        outlineColor: "var(--color-border-focus)",
        padding: "8px 10px",
        textDecoration: "none",
      }}
    >
      <span
        aria-hidden="true"
        className="font-mono"
        style={{ color: "var(--color-action-primary)", fontSize: "var(--text-md)" }}
      >
        {glyph}
      </span>
      <span>{children}</span>
    </Link>
  );
}

function KpiHistoryPanel({
  yearsQuery,
  kpiQuery,
  selectedYears,
  bridgeReady,
}: {
  yearsQuery: UseQueryResult<CompanyYearsResultUI>;
  kpiQuery: UseQueryResult<CompanyKpisResult>;
  selectedYears: number[];
  bridgeReady: boolean;
}) {
  return (
    <Panel
      title="Annual KPI history"
      subtitle={
        selectedYears.length
          ? `Years ${selectedYears.join(", ")}`
          : "Waiting for local annual coverage"
      }
      actions={
        kpiQuery.isFetching && kpiQuery.data ? (
          <span
            className="font-mono"
            style={{ color: "var(--color-state-warn)", fontSize: "var(--text-xs)" }}
          >
            polling
          </span>
        ) : null
      }
    >
      <KpiBody
        yearsQuery={yearsQuery}
        kpiQuery={kpiQuery}
        selectedYears={selectedYears}
        bridgeReady={bridgeReady}
      />
    </Panel>
  );
}

function KpiBody({
  yearsQuery,
  kpiQuery,
  selectedYears,
  bridgeReady,
}: {
  yearsQuery: UseQueryResult<CompanyYearsResultUI>;
  kpiQuery: UseQueryResult<CompanyKpisResult>;
  selectedYears: number[];
  bridgeReady: boolean;
}) {
  if (!bridgeReady || yearsQuery.isLoading) {
    return <StateBanner variant="loading" title="Carregando anos…" />;
  }
  if (yearsQuery.isError) {
    return (
      <StateBanner
        variant="error"
        onRetry={() => yearsQuery.refetch()}
        message={
          yearsQuery.error instanceof Error
            ? yearsQuery.error.message
            : String(yearsQuery.error)
        }
      />
    );
  }
  if (yearsQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" message={yearsQuery.data.reason} />;
  }
  if (selectedYears.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="Sem dados anuais"
        message="Sem linhas anuais para esta empresa no banco local."
      />
    );
  }
  if (kpiQuery.isLoading) {
    return <StateBanner variant="loading" title="Carregando KPIs…" />;
  }
  if (kpiQuery.isError) {
    return (
      <StateBanner
        variant="error"
        onRetry={() => kpiQuery.refetch()}
        message={
          kpiQuery.error instanceof Error
            ? kpiQuery.error.message
            : String(kpiQuery.error)
        }
      />
    );
  }
  if (!kpiQuery.data || kpiQuery.data.mode !== "desktop") {
    return (
      <StateBanner
        variant="empty"
        title="Sem KPIs"
        message="Bridge retornou payload vazio para os anos selecionados."
      />
    );
  }
  const { annual } = kpiQuery.data.bundle;
  if (annual.rows.length === 0 || annual.columns.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="Sem KPIs anuais"
        message="Sem linhas anuais para os anos selecionados."
      />
    );
  }
  return <KpiTable columns={annual.columns} rows={annual.rows} years={selectedYears} />;
}

function KpiTable({
  columns,
  rows,
  years,
}: {
  columns: string[];
  rows: TabularRow[];
  years: number[];
}) {
  const yearColumns = years.map((y) => String(y)).filter((year) => columns.includes(year));
  const showDelta = columns.includes("DELTA_YOY_PCT");
  return (
    <div className="overflow-x-auto">
      <table
        className="w-full border-collapse"
        style={{ fontSize: "var(--text-sm)" }}
      >
        <thead>
          <tr
            className="text-left"
            style={{
              borderBottom: "1px solid var(--color-border-default)",
              color: "var(--color-text-tertiary)",
              fontSize: "var(--text-xs)",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            <th className="sticky left-0 px-2 py-2 font-medium" style={{ background: "var(--color-surface-2)" }}>
              KPI
            </th>
            <th className="px-2 py-2 font-medium">Categoria</th>
            <th className="px-2 py-2 font-medium">Unidade</th>
            <th className="px-2 py-2 font-medium">Trend</th>
            {yearColumns.map((c) => (
              <th key={c} className="px-2 py-2 text-right font-medium">
                {c}
              </th>
            ))}
            {showDelta ? <th className="px-2 py-2 text-right font-medium">ΔYoY</th> : null}
          </tr>
        </thead>
        <tbody style={{ color: "var(--color-text-secondary)" }}>
          {rows.map((row, i) => (
            <tr
              key={String(row.KPI_ID ?? i)}
              style={{ borderBottom: "1px solid var(--color-border-subtle)" }}
            >
              <td
                className="sticky left-0 px-2 py-2"
                style={{
                  background: "var(--color-surface-2)",
                  color: "var(--color-text-primary)",
                  minWidth: 210,
                }}
              >
                <div className="flex flex-col gap-1">
                  <span>{String(row.KPI_NOME ?? row.KPI_ID ?? "—")}</span>
                  {row.KPI_ID ? (
                    <span
                      className="font-mono"
                      style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-2xs)" }}
                    >
                      {String(row.KPI_ID)}
                    </span>
                  ) : null}
                </div>
              </td>
              <td className="px-2 py-2" style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}>
                {String(row.CATEGORIA ?? "—")}
              </td>
              <td className="px-2 py-2 font-mono" style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}>
                {formatUnit(row.FORMAT_TYPE)}
              </td>
              <td className="px-2 py-2">
                <Sparkline
                  values={yearColumns.map((year) => numericOrNull(row[year]))}
                  width={84}
                  height={24}
                  label={`${String(row.KPI_NOME ?? row.KPI_ID ?? "KPI")} trend`}
                />
              </td>
              {yearColumns.map((c) => (
                <td key={c} className="px-2 py-2 text-right">
                  <NumberCell value={row[c]} formatType={row.FORMAT_TYPE} />
                </td>
              ))}
              {showDelta ? (
                <td className="px-2 py-2 text-right">
                  <DeltaBadge value={row.DELTA_YOY_PCT} />
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExportPanel({ cdCvm }: { cdCvm: number }) {
  return (
    <Panel dense headingLevel={3} title="Export" subtitle="Excel workbook">
      <ExportCompanyButton
        cdCvm={cdCvm}
        scopeNote="Full company workbook — includes DRE, BPA, BPP, DFC (plus DVA/DMPL when available) and KPIs."
      />
    </Panel>
  );
}

function DataStatusPanel({
  companyQuery,
  yearsQuery,
  kpiQuery,
  selectedYears,
}: {
  companyQuery: UseQueryResult<CompanyInfoResult>;
  yearsQuery: UseQueryResult<CompanyYearsResultUI>;
  kpiQuery: UseQueryResult<CompanyKpisResult>;
  selectedYears: number[];
}) {
  const info = companyQuery.data?.mode === "desktop" ? companyQuery.data.info : null;
  const annualRows =
    kpiQuery.data?.mode === "desktop" ? kpiQuery.data.bundle.annual.rows.length : null;
  const allYears = yearsQuery.data?.mode === "desktop" ? yearsQuery.data.years : [];

  return (
    <Panel dense headingLevel={3} title="Data status" subtitle="Local read model">
      {companyQuery.isLoading ? (
        <StateBanner variant="loading" size="dense" title="Carregando metadados…" />
      ) : companyQuery.isError ? (
        <StateBanner
          variant="error"
          size="dense"
          message={
            companyQuery.error instanceof Error
              ? companyQuery.error.message
              : String(companyQuery.error)
          }
          onRetry={() => companyQuery.refetch()}
        />
      ) : companyQuery.data?.mode === "browser" ? (
        <StateBanner variant="browser-only" size="dense" message={companyQuery.data.reason} />
      ) : companyQuery.data?.mode === "desktop-not-found" ? (
        <StateBanner
          variant="error"
          size="dense"
          title="Empresa não encontrada"
          message={`Sem registro para CVM ${companyQuery.data.cd_cvm}.`}
        />
      ) : (
        <dl className="grid gap-2">
          <StatusRow label="CVM">
            <IdentifierBadge>{info?.cd_cvm ?? "—"}</IdentifierBadge>
          </StatusRow>
          <StatusRow label="Ano mais recente" value={info?.latest_readable_year?.toString() ?? "—"} mono />
          <StatusRow label="Anos no banco" value={allYears.length ? allYears.join(", ") : "—"} mono />
          <StatusRow label="Janela do painel" value={selectedYears.length ? selectedYears.join(", ") : "—"} mono />
          <StatusRow label="KPIs anuais" value={annualRows == null ? "—" : String(annualRows)} mono />
          <StatusRow
            label="Dados locais"
            value={info?.has_local_financial_reports ? "● sim" : "▲ não"}
            tone={info?.has_local_financial_reports ? "ok" : "warn"}
            mono
          />
          <StatusRow
            label="Modelo atualizado"
            value={formatBRDateTime(info?.read_model_updated_at)}
            mono
          />
        </dl>
      )}
    </Panel>
  );
}

function StatusRow({
  label,
  value,
  children,
  mono = false,
  tone,
}: {
  label: string;
  value?: string;
  children?: ReactNode;
  mono?: boolean;
  tone?: "ok" | "warn";
}) {
  const color =
    tone === "ok"
      ? "var(--color-state-ok)"
      : tone === "warn"
        ? "var(--color-state-warn)"
        : "var(--color-text-secondary)";
  return (
    <div
      className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-2"
      style={{ minHeight: 24 }}
    >
      <dt
        style={{
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-xs)",
        }}
      >
        {label}
      </dt>
      <dd
        className={mono ? "truncate font-mono" : "truncate"}
        style={{
          color,
          fontSize: "var(--text-xs)",
          margin: 0,
        }}
        title={value}
      >
        {children ?? value ?? "—"}
      </dd>
    </div>
  );
}

function buildMetricTapeItems(
  info: CompanyInfo | null,
  bundle: KPIBundle | null,
  selectedYears: number[],
): MetricTapeItem[] {
  const latestYear = selectedYears.length ? Math.max(...selectedYears) : null;
  const rowsById = new Map<string, TabularRow>();
  for (const row of bundle?.annual.rows ?? []) {
    const id = String(row.KPI_ID ?? "").trim();
    if (id) rowsById.set(id, row);
  }

  const items: MetricTapeItem[] = [
    {
      id: "latest-year",
      label: "Ano",
      value: info?.latest_readable_year?.toString() ?? null,
      sublabel: "mais recente",
    },
    {
      id: "readable-years",
      label: "Cobertura",
      value: info?.readable_years_count ?? null,
      sublabel: "anos legíveis",
    },
    {
      id: "local-data",
      label: "Base local",
      valueNode: info ? (
        <MetricStatusValue ok={Boolean(info?.has_local_financial_reports)}>
          {info?.has_local_financial_reports ? "sim" : "não"}
        </MetricStatusValue>
      ) : (
        <NumberCell value={null} size="lg" align="left" />
      ),
      sublabel: info?.read_availability_code ?? "status",
    },
  ];

  for (const id of TAPE_KPI_IDS) {
    const row = rowsById.get(id);
    const label = row ? String(row.KPI_NOME ?? humanizeKpiId(id)) : humanizeKpiId(id);
    items.push({
      id,
      label,
      value: latestYear && row ? row[String(latestYear)] : null,
      formatType: row?.FORMAT_TYPE,
      tone: id === "DIV_EBITDA" ? "neutral" : "auto",
      sublabel: latestYear ? String(latestYear) : "sem ano",
      delta: row?.DELTA_YOY_PCT ?? null,
      sparkline: selectedYears.map((year) => numericOrNull(row?.[String(year)])),
    });
  }

  return items;
}

function MetricStatusValue({
  ok,
  children,
}: {
  ok: boolean;
  children: ReactNode;
}) {
  return (
    <span
      className="font-mono"
      style={{
        alignItems: "center",
        color: ok ? "var(--color-state-ok)" : "var(--color-state-warn)",
        display: "inline-flex",
        fontSize: "var(--text-xl)",
        fontVariantNumeric: "tabular-nums",
        fontWeight: 600,
        gap: 6,
        lineHeight: 1.2,
      }}
    >
      <span aria-hidden="true">{ok ? "●" : "▲"}</span>
      {children}
    </span>
  );
}

function numericOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function humanizeKpiId(id: string): string {
  return id
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
