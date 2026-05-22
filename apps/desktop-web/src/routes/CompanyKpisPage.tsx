import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { ExportCompanyButton } from "@/components/ExportCompanyButton";
import {
  fetchCompanyInfo,
  fetchCompanyKpis,
  fetchCompanyYears,
  type CompanyInfoResult,
  type CompanyKpisResult,
  type CompanyYearsResultUI,
} from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { CompanyInfo, TabularData, TabularRow } from "@/lib/bridge/types";

const DEFAULT_RECENT_YEARS = 5;

export function CompanyKpisPage() {
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
    return <ErrorState message={`Invalid CVM code: "${params.cdCvm}"`} />;
  }

  return (
    <section className="space-y-6">
      <BackLink cdCvm={cdCvm} />
      <KpiHeader cdCvm={cdCvm} bridgeReady={bridgeReady} />
      <KpiBody cdCvm={cdCvm} bridgeReady={bridgeReady} />
    </section>
  );
}

function BackLink({ cdCvm }: { cdCvm: number }) {
  return (
    <Link
      to={`/empresas/${cdCvm}`}
      className="inline-flex items-center text-xs text-zinc-400 hover:text-zinc-200"
    >
      ← Back to company
    </Link>
  );
}

function KpiHeader({ cdCvm, bridgeReady }: { cdCvm: number; bridgeReady: boolean }) {
  const query = useQuery<CompanyInfoResult>({
    queryKey: ["company-info", cdCvm],
    queryFn: () => fetchCompanyInfo(cdCvm),
    enabled: bridgeReady,
  });
  if (!bridgeReady || query.isLoading) {
    return <CardSkeleton title="Loading company…" />;
  }
  if (query.isError) {
    return <ErrorState message={query.error instanceof Error ? query.error.message : String(query.error)} />;
  }
  if (!query.data) return <CardSkeleton title="Loading…" />;
  if (query.data.mode === "browser") return <BrowserModeBanner reason={query.data.reason} />;
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
  return <CompanyHeaderCard info={query.data.info} cdCvm={cdCvm} />;
}

function CompanyHeaderCard({ info, cdCvm }: { info: CompanyInfo; cdCvm: number }) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-zinc-500">
            Indicadores financeiros
          </p>
          <h2 className="text-2xl font-semibold text-zinc-50">{info.company_name}</h2>
        </div>
        <div className="text-right">
          <div className="font-mono text-xs text-zinc-500">CVM {info.cd_cvm}</div>
          {info.ticker_b3 ? (
            <div className="font-mono text-sm text-zinc-200">{info.ticker_b3}</div>
          ) : null}
        </div>
      </header>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Field label="Sector" value={info.setor_cvm} />
        <Field label="Latest year" value={info.latest_readable_year?.toString() ?? null} mono />
        <Field label="Years readable" value={String(info.readable_years_count)} mono />
        <Field label="Has financial data" value={info.has_local_financial_reports ? "yes" : "no"} />
      </dl>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <Link
          to={`/empresas/${cdCvm}`}
          className="rounded-md border border-zinc-700 px-3 py-1.5 text-zinc-200 hover:border-cyan-600 hover:text-cyan-100"
        >
          Overview
        </Link>
        <Link
          to={`/empresas/${cdCvm}/demonstrativos`}
          className="rounded-md border border-zinc-700 px-3 py-1.5 text-zinc-200 hover:border-cyan-600 hover:text-cyan-100"
        >
          Financial statements
        </Link>
        <span className="rounded-md border border-cyan-500/50 bg-cyan-500/10 px-3 py-1.5 text-cyan-100">
          Indicadores
        </span>
      </div>
      <div className="mt-4 border-t border-zinc-800 pt-4">
        <ExportCompanyButton
          cdCvm={info.cd_cvm}
          scopeNote="KPIs are included in the full company workbook (no KPI-only export in the backend)."
        />
      </div>
    </article>
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

function KpiBody({ cdCvm, bridgeReady }: { cdCvm: number; bridgeReady: boolean }) {
  const yearsQuery = useQuery<CompanyYearsResultUI>({
    queryKey: ["company-years", cdCvm],
    queryFn: () => fetchCompanyYears(cdCvm),
    enabled: bridgeReady,
  });

  const availableYears = useMemo(
    () => (yearsQuery.data?.mode === "desktop" ? [...yearsQuery.data.years] : []),
    [yearsQuery.data],
  );
  const sortedYears = useMemo(
    () => [...availableYears].sort((a, b) => a - b),
    [availableYears],
  );

  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  useEffect(() => {
    if (selectedYears.length === 0 && sortedYears.length > 0) {
      const desc = [...sortedYears].sort((a, b) => b - a);
      setSelectedYears(desc.slice(0, DEFAULT_RECENT_YEARS).sort((a, b) => a - b));
    }
  }, [sortedYears, selectedYears.length]);

  const kpiQuery = useQuery<CompanyKpisResult>({
    queryKey: ["company-kpis", cdCvm, selectedYears.join(",")],
    queryFn: () => fetchCompanyKpis(cdCvm, selectedYears),
    enabled: bridgeReady && selectedYears.length > 0,
  });

  if (!bridgeReady || yearsQuery.isLoading) {
    return <CardSkeleton title="Loading available years…" />;
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
  if (sortedYears.length === 0) {
    return (
      <EmptyState
        title="No annual data"
        body="This company has no annual rows in the local database. Run Atualizar Base to populate, then refresh."
      />
    );
  }

  const bundle =
    kpiQuery.data?.mode === "desktop" ? kpiQuery.data.bundle : null;

  return (
    <div className="space-y-6">
      <YearSelector
        available={sortedYears}
        selected={selectedYears}
        onChange={setSelectedYears}
      />

      <KpiSummaryCards bundle={bundle} selectedYears={selectedYears} />

      <KpiTableCard
        title="Annual indicators"
        subtitle={`Annual KPIs for ${selectedYears.length} year(s).`}
        loading={kpiQuery.isLoading}
        fetching={kpiQuery.isFetching}
        error={kpiQuery.error}
        table={bundle?.annual ?? null}
        selectedYears={selectedYears}
      />

      <KpiTableCard
        title="Quarterly indicators"
        subtitle="Quarterly cuts when the local DB has period rows for the selected years."
        loading={kpiQuery.isLoading}
        fetching={kpiQuery.isFetching}
        error={kpiQuery.error}
        table={bundle?.quarterly ?? null}
        selectedYears={selectedYears}
        isQuarterly
      />
    </div>
  );
}

function YearSelector({
  available,
  selected,
  onChange,
}: {
  available: number[];
  selected: number[];
  onChange: (years: number[]) => void;
}) {
  const selectedSet = new Set(selected);
  function toggle(year: number) {
    if (selectedSet.has(year)) {
      onChange(selected.filter((y) => y !== year));
    } else {
      onChange([...selected, year].sort((a, b) => a - b));
    }
  }
  function selectAll() {
    onChange([...available].sort((a, b) => a - b));
  }
  function selectRecent() {
    const desc = [...available].sort((a, b) => b - a);
    onChange(desc.slice(0, DEFAULT_RECENT_YEARS).sort((a, b) => a - b));
  }
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 shadow-lg">
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-zinc-100">Years</h3>
          <p className="text-xs text-zinc-500">
            Pick which years to load. KPI matrix returns one column per year.
          </p>
        </div>
        <div className="flex gap-2 text-xs">
          <button
            type="button"
            onClick={selectRecent}
            className="rounded-md border border-zinc-700 px-2 py-1 text-zinc-300 hover:border-cyan-600 hover:text-cyan-100"
          >
            Last {DEFAULT_RECENT_YEARS}
          </button>
          <button
            type="button"
            onClick={selectAll}
            className="rounded-md border border-zinc-700 px-2 py-1 text-zinc-300 hover:border-cyan-600 hover:text-cyan-100"
          >
            All
          </button>
        </div>
      </header>
      <div className="flex flex-wrap gap-2">
        {available.map((year) => {
          const active = selectedSet.has(year);
          return (
            <button
              key={year}
              type="button"
              onClick={() => toggle(year)}
              className={
                active
                  ? "rounded-md border border-cyan-500/50 bg-cyan-500/10 px-3 py-1 font-mono text-xs text-cyan-100"
                  : "rounded-md border border-zinc-700 px-3 py-1 font-mono text-xs text-zinc-300 hover:border-zinc-500"
              }
            >
              {year}
            </button>
          );
        })}
      </div>
    </article>
  );
}

const SUMMARY_KPI_IDS = ["RECEITA_LIQUIDA", "EBITDA", "LUCRO_LIQUIDO", "MARGEM_LIQUIDA"];

function KpiSummaryCards({
  bundle,
  selectedYears,
}: {
  bundle: { annual: TabularData } | null;
  selectedYears: number[];
}) {
  if (!bundle) {
    return null;
  }
  const latestYear = selectedYears.length ? Math.max(...selectedYears) : null;
  if (latestYear == null) return null;
  const yearCol = String(latestYear);
  const rowsById = new Map<string, TabularRow>();
  for (const row of bundle.annual.rows) {
    const id = String(row.KPI_ID ?? "").trim();
    if (id) rowsById.set(id, row);
  }
  const cards = SUMMARY_KPI_IDS.map((id) => {
    const row = rowsById.get(id);
    if (!row) {
      return { id, label: humanizeKpiId(id), value: null, format: null };
    }
    return {
      id,
      label: String(row.KPI_NOME ?? humanizeKpiId(id)),
      value: row[yearCol] ?? null,
      format: typeof row.FORMAT_TYPE === "string" ? row.FORMAT_TYPE : null,
    };
  });
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <article
          key={card.id}
          className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4 shadow-lg"
        >
          <p className="text-xs uppercase tracking-wider text-zinc-500">{card.label}</p>
          <p className="mt-2 font-mono text-xl font-semibold text-zinc-100">
            {formatKpiCell(card.value, card.format)}
          </p>
          <p className="mt-1 text-[11px] text-zinc-500">Latest year: {latestYear}</p>
        </article>
      ))}
    </div>
  );
}

function humanizeKpiId(id: string): string {
  return id
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function KpiTableCard({
  title,
  subtitle,
  loading,
  fetching,
  error,
  table,
  selectedYears,
  isQuarterly = false,
}: {
  title: string;
  subtitle: string;
  loading: boolean;
  fetching: boolean;
  error: unknown;
  table: TabularData | null;
  selectedYears: number[];
  isQuarterly?: boolean;
}) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-5 shadow-lg">
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold text-zinc-100">{title}</h3>
          <p className="text-xs text-zinc-500">{subtitle}</p>
        </div>
        {fetching && !loading ? (
          <span className="text-xs text-amber-300">Refreshing…</span>
        ) : null}
      </header>
      <KpiTableBody
        loading={loading}
        error={error}
        table={table}
        selectedYears={selectedYears}
        isQuarterly={isQuarterly}
      />
    </article>
  );
}

function KpiTableBody({
  loading,
  error,
  table,
  selectedYears,
  isQuarterly,
}: {
  loading: boolean;
  error: unknown;
  table: TabularData | null;
  selectedYears: number[];
  isQuarterly: boolean;
}) {
  if (loading) {
    return <p className="text-sm text-zinc-400">Loading KPIs…</p>;
  }
  if (error) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }
  if (!table || table.rows.length === 0 || table.columns.length === 0) {
    return (
      <EmptyState
        title={isQuarterly ? "No quarterly KPI rows" : "No KPI rows"}
        body={
          isQuarterly
            ? "The local DB has no quarterly KPI rows for the selected years."
            : "No annual KPI rows for the selected years."
        }
      />
    );
  }
  return <KpiTable columns={table.columns} rows={table.rows} years={selectedYears} isQuarterly={isQuarterly} />;
}

function KpiTable({
  columns,
  rows,
  years,
  isQuarterly,
}: {
  columns: string[];
  rows: TabularRow[];
  years: number[];
  isQuarterly: boolean;
}) {
  const yearColumns = years.map((y) => String(y));
  const quarterColumnRegex = /^(?:[1-4]Q|Q[1-4])-?\d{4}$/i;
  const numericColumns = columns.filter((c) => {
    if (isQuarterly) {
      return quarterColumnRegex.test(c) || yearColumns.includes(c);
    }
    return yearColumns.includes(c) || c === "DELTA_YOY_PCT";
  });
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-zinc-500">
            <th className="px-2 py-2 font-medium">KPI</th>
            <th className="px-2 py-2 font-medium">Categoria</th>
            <th className="px-2 py-2 font-medium">Unidade</th>
            {numericColumns.map((c) => (
              <th key={c} className="px-2 py-2 text-right font-medium">
                {c === "DELTA_YOY_PCT" ? "ΔYoY" : c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/80 text-zinc-200">
          {rows.map((row, i) => (
            <tr key={String(row.KPI_ID ?? i)} className="hover:bg-zinc-900/50">
              <td className="px-2 py-2 text-zinc-100">
                {String(row.KPI_NOME ?? row.KPI_ID ?? "—")}
              </td>
              <td className="px-2 py-2 text-xs text-zinc-400">
                {String(row.CATEGORIA ?? "—")}
              </td>
              <td className="px-2 py-2 text-xs text-zinc-400">
                {formatUnit(row.FORMAT_TYPE)}
              </td>
              {numericColumns.map((c) => (
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

function formatUnit(formatType: unknown): string {
  const f = typeof formatType === "string" ? formatType.toLowerCase() : "";
  if (f === "pct") return "%";
  if (f === "money") return "R$";
  if (f === "ratio") return "x";
  if (f === "bps") return "bps";
  return "—";
}

function formatKpiCell(value: unknown, formatType: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value !== "number" || !Number.isFinite(value)) {
    const s = String(value);
    return s.length > 0 ? s : "—";
  }
  const format = typeof formatType === "string" ? formatType.toLowerCase() : "";
  if (format === "pct") {
    return `${(value * 100).toFixed(1)}%`;
  }
  if (format === "money") {
    if (Math.abs(value) >= 1_000_000) {
      return `${(value / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mn`;
    }
    return value.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  }
  if (format === "ratio") {
    return `${value.toFixed(2)}x`;
  }
  if (format === "bps") {
    return `${Math.round(value)} bps`;
  }
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

function CardSkeleton({ title }: { title: string }) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <p className="text-sm text-zinc-400">{title}</p>
    </article>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-5 text-sm text-zinc-300">
      <p className="font-medium text-zinc-100">{title}</p>
      <p className="mt-1 text-zinc-400">{body}</p>
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
