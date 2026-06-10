import { memo, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { DeltaBadge } from "@/components/data/DeltaBadge";
import { MetricTape, type MetricTapeItem } from "@/components/data/MetricTape";
import { NumberCell } from "@/components/data/NumberCell";
import { Sparkline } from "@/components/data/Sparkline";
import { CompanyCommandBar } from "@/components/CompanyCommandBar";
import { EntityHeader } from "@/components/EntityHeader";
import { MarketHistoryPanel } from "@/components/MarketHistoryPanel";
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
import type { KPIBundle, TabularRow } from "@/lib/bridge/types";
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
      <StateBanner variant="error" message={`Invalid CVM: "${params.cdCvm}"`} />
    );
  }

  return (
    <section className="space-y-4">
      <EntityHeader cdCvm={cdCvm} activeTab="overview" />
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
    enabled: bridgeReady,
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
    () => buildMetricTapeItems(bundle, selectedYears),
    [bundle, selectedYears],
  );

  return (
    <div className="space-y-4">
      <CompanyCommandBar
        cdCvm={cdCvm}
        bridgeReady={bridgeReady}
        latestPeriod={info?.latest_financial_period_display ?? null}
        yearsAvailable={info?.readable_years_count ?? null}
        lastModelUpdatedAt={info?.read_model_updated_at ?? null}
      />
      <MetricTape items={metricItems} ariaLabel="Company reference metrics" />

      <div className="min-w-0 space-y-4">
        <KpiHistoryPanel
          yearsQuery={yearsQuery}
          kpiQuery={kpiQuery}
          selectedYears={selectedYears}
          bridgeReady={bridgeReady}
        />
        <MarketHistoryPanel cdCvm={cdCvm} bridgeReady={bridgeReady} />
      </div>
    </div>
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
    return <StateBanner variant="loading" title="Loading years…" />;
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
        title="No financial history yet"
        message="Download or update this company's data to compute indicators."
      />
    );
  }
  if (kpiQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading KPIs…" />;
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
        title="No KPIs"
        message="Bridge returned an empty payload for the selected years."
      />
    );
  }
  const { annual } = kpiQuery.data.bundle;
  if (annual.rows.length === 0 || annual.columns.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No annual KPIs"
        message="No annual rows for the selected years."
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
  const yearColumns = useMemo(
    () => years.map((y) => String(y)).filter((year) => columns.includes(year)),
    [years, columns],
  );
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
            <th scope="col" className="sticky left-0 px-2 py-2 font-medium" style={{ background: "var(--color-surface-2)" }}>
              KPI
            </th>
            <th scope="col" className="px-2 py-2 font-medium">Category</th>
            <th scope="col" className="px-2 py-2 font-medium">Unit</th>
            <th scope="col" className="px-2 py-2 font-medium">Trend</th>
            {yearColumns.map((c) => (
              <th scope="col" key={c} className="px-2 py-2 text-right font-medium">
                {c}
              </th>
            ))}
            {showDelta ? <th scope="col" className="px-2 py-2 text-right font-medium">ΔYoY</th> : null}
          </tr>
        </thead>
        <tbody style={{ color: "var(--color-text-secondary)" }}>
          {rows.map((row, i) => (
            <KpiTableRow
              key={String(row.KPI_ID ?? i)}
              row={row}
              yearColumns={yearColumns}
              showDelta={showDelta}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

const KpiTableRow = memo(function KpiTableRow({
  row,
  yearColumns,
  showDelta,
}: {
  row: TabularRow;
  yearColumns: string[];
  showDelta: boolean;
}) {
  const sparklineValues = useMemo(
    () => yearColumns.map((year) => numericOrNull(row[year])),
    [row, yearColumns],
  );
  return (
    <tr style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
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
          values={sparklineValues}
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
  );
});

function buildMetricTapeItems(
  bundle: KPIBundle | null,
  selectedYears: number[],
): MetricTapeItem[] {
  const latestYear = selectedYears.length ? Math.max(...selectedYears) : null;
  const rowsById = new Map<string, TabularRow>();
  for (const row of bundle?.annual.rows ?? []) {
    const id = String(row.KPI_ID ?? "").trim();
    if (id) rowsById.set(id, row);
  }

  const items: MetricTapeItem[] = [];

  for (const id of TAPE_KPI_IDS) {
    const row = rowsById.get(id);
    const label = row ? String(row.KPI_NOME ?? humanizeKpiId(id)) : humanizeKpiId(id);
    items.push({
      id,
      label,
      value: latestYear && row ? row[String(latestYear)] : null,
      formatType: row?.FORMAT_TYPE,
      tone: id === "DIV_EBITDA" ? "neutral" : "auto",
      sublabel: latestYear ? String(latestYear) : "no year",
      delta: row?.DELTA_YOY_PCT ?? null,
      sparkline: selectedYears.map((year) => numericOrNull(row?.[String(year)])),
    });
  }

  return items;
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
