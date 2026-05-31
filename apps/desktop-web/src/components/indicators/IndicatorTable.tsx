import { useMemo } from "react";

import {
  FinancialDataGrid,
  type FinancialGridColumn,
  type FinancialGridRow,
  type FinancialValueType,
} from "@/components/data/FinancialDataGrid";
import type { TabularData, TabularRow } from "@/lib/bridge/types";
import { categoryLabel } from "@/lib/indicators/catalog";
import { formatUnit } from "@/lib/formatters";
import type { IndicatorUnit } from "@/lib/indicators/types";

interface IndicatorTableProps {
  table: TabularData;
  periods: string[];
  selectedIds: string[];
}

function unitToValueType(unit: IndicatorUnit): FinancialValueType {
  if (unit === "pct") return "percentage";
  if (unit === "ratio") return "multiple";
  return "number";
}

function toUnit(formatType: unknown): IndicatorUnit {
  const f = typeof formatType === "string" ? formatType.toLowerCase() : "";
  if (f === "pct") return "pct";
  if (f === "ratio") return "ratio";
  return "number";
}

/**
 * Dynamic indicator table — driven by the SAME selected indicators and the SAME
 * ordered periods as the chart, so the two views never disagree. Missing values
 * render as an em dash (never zero) via FinancialDataGrid's formatters.
 */
export function IndicatorTable({ table, periods, selectedIds }: IndicatorTableProps) {
  const { columns, rows } = useMemo(() => {
    const order = new Map(selectedIds.map((id, i) => [id, i] as const));
    const rowsById = new Map<string, TabularRow>();
    for (const row of table.rows) {
      const id = String(row.KPI_ID ?? "").trim();
      if (id && order.has(id)) rowsById.set(id, row);
    }

    const latest = periods.at(-1);
    const cols: FinancialGridColumn[] = periods.map((p) => ({
      id: p,
      label: p,
      latest: p === latest,
      minWidth: 92,
    }));

    const gridRows: FinancialGridRow[] = selectedIds
      .map((id) => rowsById.get(id))
      .filter((row): row is TabularRow => Boolean(row))
      .map((row) => {
        const id = String(row.KPI_ID ?? "");
        const unit = toUnit(row.FORMAT_TYPE);
        const valueType = unitToValueType(unit);
        const cells: FinancialGridRow["cells"] = {};
        for (const p of periods) {
          cells[p] = { value: row[p], valueType, tone: "neutral" };
        }
        return {
          id,
          label: String(row.KPI_NOME ?? id),
          meta: `${categoryLabel(String(row.CATEGORIA ?? "—"))} · ${formatUnit(row.FORMAT_TYPE)}`,
          cells,
        };
      });

    return { columns: cols, rows: gridRows };
  }, [table, periods, selectedIds]);

  return (
    <FinancialDataGrid
      labelHeader="Indicator"
      columns={columns}
      rows={rows}
      emptyMessage="No indicators selected."
    />
  );
}
