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
    return (
      <StateBanner
        variant="error"
        title="CVM inválido"
        message={`"${params.cdCvm}" não é um código CVM válido.`}
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
    <Panel dense title="Statement" subtitle="Statement family">
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
        title="Anos indisponíveis"
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
        title="Sem demonstrações anuais"
        message="Esta empresa não tem demonstrações anuais no banco local."
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
        title="Demonstração indisponível"
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
      subtitle={`${matrix.statement_type} · years ${selectedYears.join(", ")} · ${sourceRows.length} rows · conflicts excluded: ${
        matrix.exclude_conflicts ? "yes" : "no"
      }`}
      actions={
        refreshing ? (
          <span className="font-mono" style={{ color: "var(--color-state-warn)", fontSize: "var(--text-xs)" }}>
            refreshing
          </span>
        ) : null
      }
      footer="Source: local CVM filings. Values are stored as R$ thousands and rendered as compact reais."
    >
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
