import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { ExportCompanyButton } from "@/components/ExportCompanyButton";
import {
  fetchCompanyInfo,
  fetchCompanyYears,
  type CompanyInfoResult,
  type CompanyYearsResultUI,
} from "@/lib/api/companyDetail";
import {
  fetchCompanyStatement,
  normalizeStatementType,
  STATEMENT_OPTIONS,
  type CompanyStatementResult,
  type StatementType,
} from "@/lib/api/statements";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { StatementMatrix, TabularRow } from "@/lib/bridge/types";

const MAX_STATEMENT_YEARS = 3;
const META_COLUMNS = new Set(["CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"]);

const STATEMENT_COPY: Record<StatementType, string> = {
  DRE: "Demonstração de resultado",
  BPA: "Balanço patrimonial ativo",
  BPP: "Balanço patrimonial passivo",
  DFC: "Fluxo de caixa",
};

const STATEMENT_TOTAL_CODES: Partial<Record<StatementType, Set<string>>> = {
  DRE: new Set(["3.01", "3.03", "3.05", "3.07", "3.11"]),
  BPA: new Set(["1", "1.01", "1.02"]),
  BPP: new Set(["2", "2.01", "2.02", "2.03"]),
  DFC: new Set(["6.01", "6.02", "6.03"]),
};

export function CompanyStatementsPage() {
  const params = useParams<{ cdCvm: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const cdCvm = Number.parseInt(params.cdCvm ?? "", 10);
  const statementType = normalizeStatementType(searchParams.get("stmt"));
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
    return <ErrorState title="Invalid CVM code" message={`"${params.cdCvm}" is not a valid CVM code.`} />;
  }

  function handleStatementChange(next: StatementType) {
    setSearchParams((current) => {
      const updated = new URLSearchParams(current);
      updated.set("stmt", next);
      return updated;
    });
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to={`/empresas/${cdCvm}`}
          className="inline-flex items-center text-xs text-zinc-400 hover:text-zinc-200"
        >
          ← Back to company overview
        </Link>
        <Link to="/" className="text-xs text-zinc-500 hover:text-zinc-300">
          Company directory
        </Link>
      </div>

      <StatementsHeader cdCvm={cdCvm} bridgeReady={bridgeReady} />

      <StatementSelector
        active={statementType}
        onChange={handleStatementChange}
      />

      <StatementPanel
        cdCvm={cdCvm}
        statementType={statementType}
        bridgeReady={bridgeReady}
      />
    </section>
  );
}

function StatementsHeader({
  cdCvm,
  bridgeReady,
}: {
  cdCvm: number;
  bridgeReady: boolean;
}) {
  const query = useQuery<CompanyInfoResult>({
    queryKey: ["company-info", cdCvm],
    queryFn: () => fetchCompanyInfo(cdCvm),
    enabled: bridgeReady,
  });

  if (!bridgeReady || query.isLoading) {
    return <CardSkeleton title="Loading company context..." />;
  }
  if (query.isError) {
    return (
      <ErrorState
        title="Company context unavailable"
        message={query.error instanceof Error ? query.error.message : String(query.error)}
      />
    );
  }
  if (query.data?.mode === "browser") {
    return <BrowserModeBanner reason={query.data.reason} />;
  }
  if (query.data?.mode === "desktop-not-found") {
    return (
      <ErrorState
        title="Company not found"
        message={`No local catalog entry for CVM ${query.data.cd_cvm}.`}
      />
    );
  }

  const info = query.data?.info;
  if (!info) {
    return <CardSkeleton title="Loading company context..." />;
  }

  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-6 shadow-lg">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-widest text-zinc-500">
            Financial statements
          </p>
          <h2 className="text-2xl font-semibold text-zinc-50">{info.company_name}</h2>
          <p className="max-w-2xl text-sm leading-6 text-zinc-400">
            Auditable CVM statement matrix through the existing Python bridge. Values are displayed as
            compact Brazilian reais converted from CVM's stored R$ thousands.
          </p>
        </div>
        <dl className="grid min-w-48 grid-cols-2 gap-3 text-right text-sm">
          <div>
            <dt className="text-xs uppercase tracking-wider text-zinc-500">CVM</dt>
            <dd className="font-mono text-zinc-200">{info.cd_cvm}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wider text-zinc-500">Ticker</dt>
            <dd className="font-mono text-zinc-200">{info.ticker_b3 ?? "—"}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-xs uppercase tracking-wider text-zinc-500">Latest year</dt>
            <dd className="font-mono text-zinc-200">{info.latest_readable_year ?? "—"}</dd>
          </div>
        </dl>
      </div>
      <div className="mt-4 border-t border-zinc-800 pt-4">
        <ExportCompanyButton
          cdCvm={info.cd_cvm}
          scopeNote="Full company workbook — backend currently emits one .xlsx per company (all statements + KPIs). Per-statement scope is not yet supported by the export pipeline."
        />
      </div>
    </article>
  );
}

function StatementSelector({
  active,
  onChange,
}: {
  active: StatementType;
  onChange: (statementType: StatementType) => void;
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-4">
      {STATEMENT_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={
            option.value === active
              ? "rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-3 text-left shadow-lg shadow-cyan-950/20"
              : "rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-3 text-left hover:border-zinc-600"
          }
        >
          <span className="block text-sm font-semibold text-zinc-100">{option.label}</span>
          <span className="mt-1 block text-xs text-zinc-500">{option.description}</span>
        </button>
      ))}
    </div>
  );
}

function StatementPanel({
  cdCvm,
  statementType,
  bridgeReady,
}: {
  cdCvm: number;
  statementType: StatementType;
  bridgeReady: boolean;
}) {
  const yearsQuery = useQuery<CompanyYearsResultUI>({
    queryKey: ["company-years", cdCvm],
    queryFn: () => fetchCompanyYears(cdCvm),
    enabled: bridgeReady,
  });

  const selectedYears = useMemo(() => {
    if (yearsQuery.data?.mode !== "desktop") return [] as number[];
    return [...yearsQuery.data.years]
      .sort((a, b) => b - a)
      .slice(0, MAX_STATEMENT_YEARS)
      .sort((a, b) => a - b);
  }, [yearsQuery.data]);

  const statementQuery = useQuery<CompanyStatementResult>({
    queryKey: ["company-statement", cdCvm, statementType, selectedYears.join(",")],
    queryFn: () => fetchCompanyStatement(cdCvm, selectedYears, statementType),
    enabled: bridgeReady && selectedYears.length > 0,
  });

  if (!bridgeReady || yearsQuery.isLoading) {
    return <CardSkeleton title="Loading statement periods..." />;
  }
  if (yearsQuery.isError) {
    return (
      <ErrorState
        title="Years unavailable"
        message={yearsQuery.error instanceof Error ? yearsQuery.error.message : String(yearsQuery.error)}
      />
    );
  }
  if (yearsQuery.data?.mode === "browser") {
    return <BrowserModeBanner reason={yearsQuery.data.reason} />;
  }
  if (selectedYears.length === 0) {
    return (
      <EmptyState
        title="No annual statements available"
        message="This company has no readable annual statements in the local database yet."
      />
    );
  }
  if (statementQuery.isLoading) {
    return <CardSkeleton title={`Loading ${statementType} statement...`} />;
  }
  if (statementQuery.isError) {
    return (
      <ErrorState
        title="Statement unavailable"
        message={
          statementQuery.error instanceof Error
            ? statementQuery.error.message
            : String(statementQuery.error)
        }
      />
    );
  }
  if (statementQuery.data?.mode === "browser") {
    return <BrowserModeBanner reason={statementQuery.data.reason} />;
  }
  if (!statementQuery.data?.matrix) {
    return <EmptyState title="No statement data" message="The bridge returned no statement payload." />;
  }

  return (
    <StatementTable
      matrix={statementQuery.data.matrix}
      statementType={statementType}
      selectedYears={selectedYears}
      refreshing={statementQuery.isFetching}
    />
  );
}

function StatementTable({
  matrix,
  statementType,
  selectedYears,
  refreshing,
}: {
  matrix: StatementMatrix;
  statementType: StatementType;
  selectedYears: number[];
  refreshing: boolean;
}) {
  const [search, setSearch] = useState("");
  const periodColumns = useMemo(
    () => matrix.table.columns.filter((column) => !META_COLUMNS.has(column)),
    [matrix.table.columns],
  );
  const rows = matrix.table.rows;
  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter((row) => {
      const label = `${row.CD_CONTA ?? ""} ${row.DS_CONTA ?? ""} ${row.STANDARD_NAME ?? ""}`;
      return label.toLowerCase().includes(query);
    });
  }, [rows, search]);

  if (rows.length === 0 || periodColumns.length === 0) {
    return (
      <EmptyState
        title={`${statementType} has no rows for ${selectedYears.join(", ")}`}
        message="Try another statement type or refresh this company in the legacy update workflow."
      />
    );
  }

  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/70 shadow-lg">
      <header className="space-y-4 border-b border-zinc-800 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-widest text-zinc-500">
              {matrix.statement_type}
            </p>
            <h3 className="text-xl font-semibold text-zinc-50">
              {STATEMENT_COPY[statementType]}
            </h3>
            <p className="mt-1 text-sm text-zinc-400">
              Years {selectedYears.join(", ")} · {rows.length} rows · conflicts excluded:{" "}
              {matrix.exclude_conflicts ? "yes" : "no"}
            </p>
          </div>
          {refreshing ? (
            <span className="rounded-full border border-amber-400/30 px-3 py-1 text-xs text-amber-200">
              Refreshing
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="min-w-64 flex-1">
            <span className="sr-only">Filter statement rows</span>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter account or code..."
              className="h-10 w-full rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-cyan-700"
            />
          </label>
          <span className="text-xs text-zinc-500">
            Showing {filteredRows.length} of {rows.length}
          </span>
        </div>
      </header>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-zinc-950/70">
            <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
              <th className="sticky left-0 z-10 min-w-80 bg-zinc-950/95 px-4 py-3 text-left font-medium">
                Account
              </th>
              {periodColumns.map((column) => (
                <th key={column} className="min-w-28 px-3 py-3 text-right font-medium">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/80">
            {filteredRows.length ? (
              filteredRows.map((row, index) => (
                <StatementRow
                  key={statementRowKey(row, index)}
                  row={row}
                  periodColumns={periodColumns}
                  statementType={statementType}
                />
              ))
            ) : (
              <tr>
                <td colSpan={periodColumns.length + 1} className="px-4 py-10 text-center text-sm text-zinc-400">
                  No rows match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <footer className="border-t border-zinc-800 px-5 py-3 text-xs leading-5 text-zinc-500">
        Source: local CVM filings. Stored values are interpreted as R$ thousands and rendered as compact reais.
      </footer>
    </article>
  );
}

function StatementRow({
  row,
  periodColumns,
  statementType,
}: {
  row: TabularRow;
  periodColumns: string[];
  statementType: StatementType;
}) {
  const accountCode = String(row.CD_CONTA ?? "");
  const level = accountCode ? Math.max(accountCode.split(".").length - 1, 0) : 0;
  const isTotal = STATEMENT_TOTAL_CODES[statementType]?.has(accountCode) ?? false;

  return (
    <tr className={isTotal ? "bg-cyan-950/15" : "hover:bg-zinc-800/25"}>
      <td
        className="sticky left-0 z-10 min-w-80 bg-inherit px-4 py-2.5 align-top"
        style={{ paddingLeft: `${16 + level * 14}px` }}
      >
        <div className="space-y-1">
          <p className={isTotal ? "font-semibold text-zinc-100" : "text-zinc-200"}>
            {accountCode ? `${accountCode} ` : ""}
            {String(row.DS_CONTA ?? "Account")}
          </p>
          {row.STANDARD_NAME && row.STANDARD_NAME !== row.DS_CONTA ? (
            <p className="text-xs uppercase tracking-wider text-zinc-600">
              {String(row.STANDARD_NAME)}
            </p>
          ) : null}
        </div>
      </td>
      {periodColumns.map((column) => (
        <td
          key={column}
          className={
            isTotal
              ? "px-3 py-2.5 text-right font-mono text-xs font-semibold text-zinc-100"
              : "px-3 py-2.5 text-right font-mono text-xs text-zinc-300"
          }
        >
          {formatStatementValue(row[column])}
        </td>
      ))}
    </tr>
  );
}

function statementRowKey(row: TabularRow, index: number): string {
  return String(row.LINE_ID_BASE ?? row.CD_CONTA ?? row.STANDARD_NAME ?? index);
}

function formatStatementValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value);
  const reais = value * 1000;
  const absolute = Math.abs(reais);
  const sign = reais < 0 ? "-" : "";
  if (absolute >= 1_000_000_000) {
    return `${sign}R$ ${(absolute / 1_000_000_000).toLocaleString("pt-BR", {
      maximumFractionDigits: 1,
    })} bi`;
  }
  if (absolute >= 1_000_000) {
    return `${sign}R$ ${(absolute / 1_000_000).toLocaleString("pt-BR", {
      maximumFractionDigits: 1,
    })} mi`;
  }
  return `${sign}R$ ${absolute.toLocaleString("pt-BR", {
    maximumFractionDigits: 0,
  })}`;
}

function CardSkeleton({ title }: { title: string }) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg">
      <p className="text-sm text-zinc-400">{title}</p>
    </article>
  );
}

function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 text-center shadow-lg">
      <p className="font-medium text-zinc-100">{title}</p>
      <p className="mt-1 text-sm text-zinc-400">{message}</p>
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
  title,
  message,
}: {
  title: string;
  message: string;
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
