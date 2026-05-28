import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import {
  FinancialDataGrid,
  type FinancialGridColumn,
  type FinancialGridRow,
} from "@/components/data/FinancialDataGrid";
import { MetricTape, type MetricTapeItem } from "@/components/data/MetricTape";
import { EntityHeader } from "@/components/EntityHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { KpiTrendCharts } from "@/components/KpiTrendCharts";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import {
  fetchCompanyKpis,
  fetchCompanyYears,
  type CompanyKpisResult,
  type CompanyYearsResultUI,
} from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { KPIBundle, TabularData, TabularRow } from "@/lib/bridge/types";
import { formatUnit } from "@/lib/formatters";

const DEFAULT_RECENT_YEARS = 5;
const SUMMARY_KPI_IDS = ["MG_EBITDA", "MG_LIQ", "ROE", "DIV_EBITDA"] as const;

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
    return <StateBanner variant="error" message={`CVM inválido: "${params.cdCvm}"`} />;
  }

  return (
    <section className="space-y-4">
      <EntityHeader cdCvm={cdCvm} activeTab="kpis" />
      <KpiBody cdCvm={cdCvm} bridgeReady={bridgeReady} />
    </section>
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

  const bundle =
    kpiQuery.data?.mode === "desktop" ? kpiQuery.data.bundle : null;
  const metricItems = useMemo(
    () => buildMetricTapeItems(bundle, selectedYears),
    [bundle, selectedYears],
  );

  if (!bridgeReady || yearsQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading available years…" />;
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
  if (sortedYears.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No annual data"
        message="No annual rows in the local database. Run Database Updates to populate and try again."
      />
    );
  }

  return (
    <div className="space-y-4">
      <YearSelector
        available={sortedYears}
        selected={selectedYears}
        onChange={setSelectedYears}
      />

      <MetricTape items={metricItems} ariaLabel="Resumo de indicadores" />

      {bundle ? <KpiTrendCharts bundle={bundle} /> : null}

      <KpiGridPanel
        title="Annual indicators"
        subtitle={`Annual KPI matrix · ${selectedYears.join(", ")}`}
        loading={kpiQuery.isLoading}
        fetching={kpiQuery.isFetching}
        error={kpiQuery.error}
        table={bundle?.annual ?? null}
        selectedYears={selectedYears}
      />

      <KpiGridPanel
        title="Quarterly indicators"
        subtitle="Quarterly cuts when local period rows exist."
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
    <Panel
      dense
      title="Years"
      subtitle="Pick which periods feed the KPI matrix."
      actions={
        <div className="flex gap-2">
          <Button size="xs" onClick={selectRecent}>
            Last {DEFAULT_RECENT_YEARS}
          </Button>
          <Button size="xs" onClick={selectAll}>
            All
          </Button>
        </div>
      }
    >
      <div className="flex flex-wrap gap-2">
        {available.map((year) => {
          const active = selectedSet.has(year);
          return (
            <button
              key={year}
              type="button"
              onClick={() => toggle(year)}
              className="font-mono focus-visible:outline focus-visible:outline-1"
              style={{
                background: active ? "var(--color-surface-3)" : "transparent",
                border: `1px solid ${
                  active ? "var(--color-action-primary)" : "var(--color-border-default)"
                }`,
                borderRadius: "var(--radius-sm)",
                color: active ? "var(--color-action-primary)" : "var(--color-text-secondary)",
                fontSize: "var(--text-xs)",
                height: 24,
                outlineColor: "var(--color-border-focus)",
                padding: "2px 9px",
              }}
            >
              {year}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function KpiGridPanel({
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
    <Panel
      title={title}
      subtitle={subtitle}
      actions={
        fetching && !loading ? (
          <span className="font-mono" style={{ color: "var(--color-state-warn)", fontSize: "var(--text-xs)" }}>
            refreshing
          </span>
        ) : null
      }
    >
      <KpiGridBody
        loading={loading}
        error={error}
        table={table}
        selectedYears={selectedYears}
        isQuarterly={isQuarterly}
      />
    </Panel>
  );
}

function KpiGridBody({
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
  const { columns, rows } = useMemo(
    () => (table ? buildKpiGrid(table, selectedYears, isQuarterly) : { columns: [], rows: [] }),
    [table, selectedYears, isQuarterly],
  );

  if (loading) return <StateBanner variant="loading" title="Loading KPIs…" />;
  if (error) {
    return (
      <StateBanner
        variant="error"
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }
  if (!table || table.rows.length === 0 || table.columns.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title={isQuarterly ? "Sem KPIs trimestrais" : "Sem KPIs anuais"}
        message={
          isQuarterly
            ? "Sem linhas trimestrais para os anos selecionados."
            : "Sem linhas anuais para os anos selecionados."
        }
      />
    );
  }

  return (
    <FinancialDataGrid
      labelHeader="KPI"
      columns={columns}
      rows={rows}
      emptyMessage="Sem indicadores para exibir."
    />
  );
}

function buildKpiGrid(
  table: TabularData,
  selectedYears: number[],
  isQuarterly: boolean,
): { columns: FinancialGridColumn[]; rows: FinancialGridRow[] } {
  const yearColumns = selectedYears.map(String);
  const quarterColumnRegex = /^(?:[1-4]Q|Q[1-4])-?\d{4}$/i;
  const valueColumns = table.columns.filter((column) => {
    if (isQuarterly) return quarterColumnRegex.test(column) || yearColumns.includes(column);
    return yearColumns.includes(column) || column === "DELTA_YOY_PCT";
  });
  const latestColumn = valueColumns.filter((c) => c !== "DELTA_YOY_PCT").at(-1);
  const columns: FinancialGridColumn[] = valueColumns.map((column) => ({
    id: column,
    label: column === "DELTA_YOY_PCT" ? "ΔYoY" : column,
    valueType: column === "DELTA_YOY_PCT" ? "delta" : "number",
    latest: column === latestColumn,
  }));

  const rows: FinancialGridRow[] = table.rows.map((row, index) => {
    const formatType = row.FORMAT_TYPE;
    const cells: FinancialGridRow["cells"] = {};
    for (const column of valueColumns) {
      cells[column] = {
        value: row[column],
        valueType: column === "DELTA_YOY_PCT" ? "delta" : kpiValueType(formatType),
        formatType,
        tone: column === "DELTA_YOY_PCT" ? "auto" : "neutral",
      };
    }
    return {
      id: String(row.KPI_ID ?? index),
      label: String(row.KPI_NOME ?? row.KPI_ID ?? "—"),
      meta: `${String(row.CATEGORIA ?? "—")} · ${formatUnit(formatType)}`,
      cells,
    };
  });
  return { columns, rows };
}

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

  return SUMMARY_KPI_IDS.map((id) => {
    const row = rowsById.get(id);
    return {
      id,
      label: row ? String(row.KPI_NOME ?? humanizeKpiId(id)) : humanizeKpiId(id),
      value: latestYear && row ? row[String(latestYear)] : null,
      formatType: row?.FORMAT_TYPE,
      sublabel: latestYear ? `latest ${latestYear}` : "sem ano",
      delta: row?.DELTA_YOY_PCT ?? null,
      sparkline: selectedYears.map((year) => numericOrNull(row?.[String(year)])),
    };
  });
}

function kpiValueType(formatType: unknown): FinancialGridColumn["valueType"] {
  const f = typeof formatType === "string" ? formatType.toLowerCase() : "";
  if (f === "pct") return "percentage";
  if (f === "ratio") return "multiple";
  if (f === "money") return "currency";
  if (f === "bps") return "integer";
  return "number";
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
