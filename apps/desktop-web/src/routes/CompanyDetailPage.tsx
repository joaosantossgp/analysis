import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { EntityHeader } from "@/components/EntityHeader";
import { CompanyRefreshPanel } from "@/components/CompanyRefreshPanel";
import {
  fetchCompanyKpis,
  fetchCompanyYears,
  type CompanyKpisResult,
  type CompanyYearsResultUI,
} from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { TabularRow } from "@/lib/bridge/types";

const MAX_KPI_YEARS = 5;

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
      <ErrorState message={`Invalid CVM code: "${params.cdCvm}"`} />
    );
  }

  return (
    <section className="space-y-6">
      <EntityHeader cdCvm={cdCvm} activeTab="overview" />
      <CompanyRefreshPanel cdCvm={cdCvm} bridgeReady={bridgeReady} />
      <YearsKpiPanel cdCvm={cdCvm} bridgeReady={bridgeReady} />
    </section>
  );
}

function YearsKpiPanel({
  cdCvm,
  bridgeReady,
}: {
  cdCvm: number;
  bridgeReady: boolean;
}) {
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

  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold text-zinc-100">Annual KPIs</h3>
          <p className="text-xs text-zinc-500">
            via <code className="font-mono">CVMBridge.get_company_kpis</code>
            {selectedYears.length ? (
              <span> · years {selectedYears.join(", ")}</span>
            ) : null}
          </p>
        </div>
        {kpiQuery.isFetching && kpiQuery.data ? (
          <span className="text-xs text-amber-300">Refreshing…</span>
        ) : null}
      </header>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-zinc-800 bg-zinc-950/60 px-4 py-3">
        <p className="text-sm text-zinc-400">
          Need deeper indicators or account-level statements?
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            to={`/empresas/${cdCvm}/indicadores`}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-100 hover:border-cyan-600 hover:text-cyan-100"
          >
            Open indicators
          </Link>
          <Link
            to={`/empresas/${cdCvm}/demonstrativos`}
            className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-100 hover:border-cyan-600 hover:text-cyan-100"
          >
            Open financial statements
          </Link>
        </div>
      </div>
      <KpiBody
        yearsQuery={yearsQuery}
        kpiQuery={kpiQuery}
        selectedYears={selectedYears}
        bridgeReady={bridgeReady}
      />
    </article>
  );
}

function KpiBody({
  yearsQuery,
  kpiQuery,
  selectedYears,
  bridgeReady,
}: {
  yearsQuery: ReturnType<typeof useQuery<CompanyYearsResultUI>>;
  kpiQuery: ReturnType<typeof useQuery<CompanyKpisResult>>;
  selectedYears: number[];
  bridgeReady: boolean;
}) {
  if (!bridgeReady || yearsQuery.isLoading) {
    return <p className="text-sm text-zinc-400">Loading…</p>;
  }
  if (yearsQuery.isError) {
    return (
      <ErrorState
        message={
          yearsQuery.error instanceof Error
            ? yearsQuery.error.message
            : String(yearsQuery.error)
        }
      />
    );
  }
  if (yearsQuery.data?.mode === "browser") {
    return <BrowserModeBanner reason={yearsQuery.data.reason} />;
  }
  if (selectedYears.length === 0) {
    return (
      <p className="text-sm text-zinc-400">
        No annual data available for this company in the local database.
      </p>
    );
  }
  if (kpiQuery.isLoading) {
    return <p className="text-sm text-zinc-400">Loading KPIs…</p>;
  }
  if (kpiQuery.isError) {
    return (
      <ErrorState
        message={
          kpiQuery.error instanceof Error
            ? kpiQuery.error.message
            : String(kpiQuery.error)
        }
      />
    );
  }
  if (!kpiQuery.data || kpiQuery.data.mode !== "desktop") {
    return <p className="text-sm text-zinc-400">No KPI data.</p>;
  }
  const { annual } = kpiQuery.data.bundle;
  if (annual.rows.length === 0 || annual.columns.length === 0) {
    return (
      <p className="text-sm text-zinc-400">
        No annual KPI rows for the selected years.
      </p>
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
  // The KPI matrix has metadata columns + numeric year columns. Pick the
  // small useful subset to render: name + format + per-year values + delta.
  const yearColumns = years.map((y) => String(y));
  const shownColumns = columns.filter((c) =>
    yearColumns.includes(c) || c === "DELTA_YOY_PCT",
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-zinc-500">
            <th className="px-2 py-2 font-medium">KPI</th>
            <th className="px-2 py-2 font-medium">Categoria</th>
            {shownColumns.map((c) => (
              <th key={c} className="px-2 py-2 text-right font-medium">
                {c === "DELTA_YOY_PCT" ? "ΔYoY" : c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/80 text-zinc-200">
          {rows.map((row, i) => (
            <tr key={String(row.KPI_ID ?? i)} className="hover:bg-zinc-900/50">
              <td className="px-2 py-2 text-zinc-100">{String(row.KPI_NOME ?? row.KPI_ID ?? "—")}</td>
              <td className="px-2 py-2 text-xs text-zinc-400">{String(row.CATEGORIA ?? "—")}</td>
              {shownColumns.map((c) => (
                <td key={c} className="px-2 py-2 text-right font-mono text-xs">
                  {formatKpiCell(row[c], row.FORMAT_TYPE)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatKpiCell(value: unknown, formatType: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value);
  const format = typeof formatType === "string" ? formatType : "";
  if (format === "pct") {
    return `${(value * 100).toFixed(1)}%`;
  }
  if (format === "money") {
    return value.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  }
  if (format === "ratio") {
    return value.toFixed(2);
  }
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
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

