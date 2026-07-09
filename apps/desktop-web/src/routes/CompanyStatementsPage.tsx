import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import {
  FinancialDataGrid,
  type FinancialGridColumn,
  type FinancialGridRow,
} from "@/components/data/FinancialDataGrid";
import { StatementLineLabel } from "@/components/data/StatementLineLabel";
import { TableToolbar } from "@/components/data/TableToolbar";
import { CompanyCommandBar } from "@/components/CompanyCommandBar";
import { EntityHeader } from "@/components/EntityHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import {
  fetchCompanyYears,
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
const META_COLUMNS = new Set([
  "CD_CONTA",
  "DS_CONTA",
  "STANDARD_NAME",
  "LINE_ID_BASE",
  "Conta",
  "Descrição",
]);

const STATEMENT_COPY: Record<StatementType, string> = {
  DRE: "Income statement",
  BPA: "Balance sheet — assets",
  BPP: "Balance sheet — liabilities and equity",
  DFC: "Cash flow statement",
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
    return (
      <StateBanner
        variant="error"
        title="Invalid CVM code"
        message={`"${params.cdCvm}" is not a valid CVM code.`}
      />
    );
  }

  function handleStatementChange(next: StatementType) {
    setSearchParams((current) => {
      const updated = new URLSearchParams(current);
      updated.set("stmt", next);
      return updated;
    });
  }

  return (
    <section className="space-y-4">
      <EntityHeader cdCvm={cdCvm} activeTab="statements" />
      <CompanyCommandBar cdCvm={cdCvm} bridgeReady={bridgeReady} />
      <StatementSelector active={statementType} onChange={handleStatementChange} />
      <StatementPanel
        cdCvm={cdCvm}
        statementType={statementType}
        bridgeReady={bridgeReady}
      />
    </section>
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
    <Panel dense title="Statement" subtitle="Official CVM statement family">
      <div className="grid gap-2 sm:grid-cols-4">
        {STATEMENT_OPTIONS.map((option) => {
          const selected = option.value === active;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              className="text-left focus-visible:outline focus-visible:outline-1"
              style={{
                background: selected ? "var(--color-surface-3)" : "var(--color-surface-1)",
                border: `1px solid ${
                  selected ? "var(--color-action-primary)" : "var(--color-border-default)"
                }`,
                borderRadius: "var(--radius-sm)",
                color: selected ? "var(--color-action-primary)" : "var(--color-text-primary)",
                minHeight: 44,
                outlineColor: "var(--color-border-focus)",
                padding: "8px 10px",
              }}
            >
              <span className="block font-mono" style={{ fontSize: "var(--text-sm)" }}>
                {option.label}
              </span>
              <span
                className="block"
                style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}
              >
                {option.description}
              </span>
            </button>
          );
        })}
      </div>
    </Panel>
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
    return <StateBanner variant="loading" title="Loading periods…" />;
  }
  if (yearsQuery.isError) {
    return (
      <StateBanner
        variant="error"
        title="Periods unavailable"
        onRetry={() => yearsQuery.refetch()}
        message={yearsQuery.error instanceof Error ? yearsQuery.error.message : String(yearsQuery.error)}
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
        title="No annual statements"
        message="This company has no annual statements in the local database."
      />
    );
  }
  if (statementQuery.isLoading) {
    return <StateBanner variant="loading" title={`Loading ${statementType}…`} />;
  }
  if (statementQuery.isError) {
    return (
      <StateBanner
        variant="error"
        title="Statement unavailable"
        onRetry={() => statementQuery.refetch()}
        message={
          statementQuery.error instanceof Error
            ? statementQuery.error.message
            : String(statementQuery.error)
        }
      />
    );
  }
  if (statementQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" message={statementQuery.data.reason} />;
  }
  if (!statementQuery.data?.matrix) {
    return <StateBanner variant="empty" title="No data" message="Bridge returned an empty payload." />;
  }

  return (
    <StatementGrid
      matrix={statementQuery.data.matrix}
      statementType={statementType}
      selectedYears={selectedYears}
      refreshing={statementQuery.isFetching}
    />
  );
}

function StatementGrid({
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
  const sourceRows = matrix.table.rows;
  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return sourceRows;
    return sourceRows.filter((row) => {
      const label = `${row.CD_CONTA ?? ""} ${row.DS_CONTA ?? ""} ${row.STANDARD_NAME ?? ""}`;
      return label.toLowerCase().includes(query);
    });
  }, [sourceRows, search]);

  const { columns, rows } = useMemo(
    () => buildStatementGrid(periodColumns, filteredRows, statementType),
    [filteredRows, periodColumns, statementType],
  );

  if (sourceRows.length === 0 || periodColumns.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title={`${statementType} — no rows for ${selectedYears.join(", ")}`}
        message="Try another statement type or refresh this company in Database Updates."
      />
    );
  }

  return (
    <Panel
      title={STATEMENT_COPY[statementType]}
      subtitle={`${matrix.statement_type} · ${periodColumns.length} period${periodColumns.length !== 1 ? "s" : ""} · ${sourceRows.length} rows`}
      actions={
        refreshing ? (
          <span className="font-mono" style={{ color: "var(--color-state-warn)", fontSize: "var(--text-xs)" }}>
            refreshing
          </span>
        ) : null
      }
      footer="Rows are filtered locally. Missing values render as —; no client-side financial recalculation is applied."
    >
      <StatementSourceAudit
        matrix={matrix}
        statementTitle={STATEMENT_COPY[statementType]}
        periodColumns={periodColumns}
      />
      <TableToolbar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder="Filter account, code, or standard name..."
        meta={`showing ${filteredRows.length}/${sourceRows.length}`}
      />
      <FinancialDataGrid
        labelHeader="Account"
        columns={columns}
        rows={rows}
        emptyMessage="No rows match this filter."
      />
    </Panel>
  );
}

function StatementSourceAudit({
  matrix,
  statementTitle,
  periodColumns,
}: {
  matrix: StatementMatrix;
  statementTitle: string;
  periodColumns: string[];
}) {
  const periodScope = formatPeriodScope(periodColumns);
  return (
    <section
      aria-label="Statement source and method"
      className="mb-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4"
      style={{
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-sm)",
        padding: "10px 12px",
      }}
    >
      <SourceAuditItem
        label="Source"
        value="Official CVM filings"
        detail="Local database copy"
      />
      <SourceAuditItem
        label="Statement"
        value={statementTitle}
        detail={matrix.statement_type}
      />
      <SourceAuditItem
        label="Periods"
        value={periodScope}
        detail={formatPeriodKind(periodColumns)}
        mono
      />
      <SourceAuditItem
        label="Scale / policy"
        value="R$ thousands"
        detail={`${matrix.exclude_conflicts ? "Conflicts excluded" : "Conflicts included"} · consolidation not exposed`}
      />
    </section>
  );
}

function SourceAuditItem({
  label,
  value,
  detail,
  mono = false,
}: {
  label: string;
  value: string;
  detail: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <p
        style={{
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-2xs)",
          letterSpacing: "0.04em",
          margin: 0,
          textTransform: "uppercase",
        }}
      >
        {label}
      </p>
      <p
        className={mono ? "truncate font-mono" : "truncate"}
        style={{
          color: "var(--color-text-primary)",
          fontSize: "var(--text-sm)",
          fontWeight: 650,
          margin: "2px 0 0",
        }}
        title={value}
      >
        {value}
      </p>
      <p
        className="truncate"
        style={{
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-2xs)",
          margin: "1px 0 0",
        }}
        title={detail}
      >
        {detail}
      </p>
    </div>
  );
}

function formatPeriodScope(periodColumns: string[]): string {
  if (periodColumns.length === 0) return "No periods";
  const first = periodColumns[0];
  const last = periodColumns[periodColumns.length - 1];
  return first === last ? first : `${first}-${last}`;
}

function formatPeriodKind(periodColumns: string[]): string {
  if (periodColumns.length === 0) return "No periods";
  if (periodColumns.every((period) => /^\d{4}$/.test(period))) return "Annual columns";
  if (periodColumns.every((period) => /^[1-4]Q\d{2}$/.test(period))) return "Quarterly columns";
  return "Mixed period columns";
}

function buildStatementGrid(
  periodColumns: string[],
  sourceRows: TabularRow[],
  statementType: StatementType,
): { columns: FinancialGridColumn[]; rows: FinancialGridRow[] } {
  const latest = periodColumns.at(-1);
  const columns: FinancialGridColumn[] = periodColumns.map((column) => ({
    id: column,
    label: column,
    valueType: "currency-thousands",
    latest: column === latest,
    minWidth: 118,
  }));

  const rows: FinancialGridRow[] = sourceRows.map((row, index) => {
    const accountCode = String(row.CD_CONTA ?? "");
    const level = accountCode ? Math.max(accountCode.split(".").length - 1, 0) : 0;
    const isTotal = STATEMENT_TOTAL_CODES[statementType]?.has(accountCode) ?? false;
    const cells: FinancialGridRow["cells"] = {};
    for (const column of periodColumns) {
      cells[column] = {
        value: row[column],
        valueType: "currency-thousands",
        tone: numericTone(row[column]),
      };
    }
    return {
      id: statementRowKey(row, index),
      label: (
        <StatementLineLabel
          code={accountCode}
          label={String(row.DS_CONTA ?? "Account")}
          standardName={typeof row.STANDARD_NAME === "string" ? row.STANDARD_NAME : null}
          emphasis={isTotal}
        />
      ),
      cells,
      emphasis: isTotal,
      level,
      section: isTotal,
    };
  });
  return { columns, rows };
}

function numericTone(value: unknown): "neutral" | "negative" {
  return typeof value === "number" && Number.isFinite(value) && value < 0
    ? "negative"
    : "neutral";
}

function statementRowKey(row: TabularRow, index: number): string {
  return String(row.LINE_ID_BASE ?? row.CD_CONTA ?? row.STANDARD_NAME ?? index);
}
