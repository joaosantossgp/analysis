import type { ReactNode } from "react";

import { formatKpiCell } from "@/lib/formatters";

import { DeltaBadge } from "./DeltaBadge";
import { NumberCell } from "./NumberCell";
import { PeriodHeader } from "./PeriodHeader";

export type FinancialValueType =
  | "currency"
  | "currency-thousands"
  | "percentage"
  | "multiple"
  | "integer"
  | "number"
  | "text"
  | "delta";

export type FinancialGridColumn = {
  id: string;
  label: string;
  valueType?: FinancialValueType;
  formatType?: unknown;
  latest?: boolean;
  minWidth?: number;
  align?: "left" | "right";
};

export type FinancialGridCell = {
  value: unknown;
  valueType?: FinancialValueType;
  formatType?: unknown;
  tone?: "neutral" | "positive" | "negative" | "muted" | "auto";
  title?: string;
  node?: ReactNode;
};

export type FinancialGridRow = {
  id: string;
  label: ReactNode;
  cells: Record<string, FinancialGridCell | unknown>;
  meta?: ReactNode;
  level?: number;
  emphasis?: boolean;
  section?: boolean;
};

type FinancialDataGridProps = {
  columns: FinancialGridColumn[];
  rows: FinancialGridRow[];
  labelHeader?: string;
  stickyFirstColumn?: boolean;
  emptyMessage?: string;
};

const EM_DASH = "—";

export function FinancialDataGrid({
  columns,
  rows,
  labelHeader = "Linha",
  stickyFirstColumn = true,
  emptyMessage = "Sem linhas para exibir.",
}: FinancialDataGridProps) {
  return (
    <div
      className="overflow-x-auto"
      style={{
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-sm)",
      }}
    >
      <table
        className="w-full border-collapse"
        style={{ fontSize: "var(--text-sm)" }}
      >
        <thead>
          <tr
            style={{
              background: "var(--color-surface-1)",
              borderBottom: "1px solid var(--color-border-default)",
              color: "var(--color-text-tertiary)",
              fontSize: "var(--text-xs)",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
            }}
          >
            <th
              className={stickyFirstColumn ? "sticky left-0 z-20" : undefined}
              scope="col"
              style={{
                background: "var(--color-surface-1)",
                minWidth: 280,
                padding: "8px 10px",
                textAlign: "left",
              }}
            >
              {labelHeader}
            </th>
            {columns.map((column) => (
              <th
                key={column.id}
                scope="col"
                style={{
                  minWidth: column.minWidth ?? 104,
                  padding: "8px 10px",
                  textAlign: column.align ?? "right",
                  whiteSpace: "nowrap",
                }}
              >
                <PeriodHeader label={column.label} latest={column.latest} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row) => (
              <tr
                key={row.id}
                style={{
                  background: row.section ? "var(--color-surface-3)" : "transparent",
                  borderBottom: "1px solid var(--color-border-subtle)",
                }}
              >
                <th
                  className={stickyFirstColumn ? "sticky left-0 z-10" : undefined}
                  scope="row"
                  style={{
                    background: row.section
                      ? "var(--color-surface-3)"
                      : "var(--color-surface-2)",
                    color: "var(--color-text-primary)",
                    fontWeight: row.emphasis || row.section ? 650 : 500,
                    minWidth: 280,
                    padding: "7px 10px",
                    textAlign: "left",
                    verticalAlign: "top",
                  }}
                >
                  <div style={{ paddingLeft: Math.max(0, row.level ?? 0) * 12 }}>
                    {row.label}
                    {row.meta ? (
                      <div
                        style={{
                          color: "var(--color-text-tertiary)",
                          fontSize: "var(--text-2xs)",
                          marginTop: 2,
                        }}
                      >
                        {row.meta}
                      </div>
                    ) : null}
                  </div>
                </th>
                {columns.map((column) => (
                  <td
                    key={column.id}
                    style={{
                      color: "var(--color-text-secondary)",
                      padding: "7px 10px",
                      textAlign: column.align ?? "right",
                      verticalAlign: "top",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {renderCell(row.cells[column.id], column)}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td
                colSpan={columns.length + 1}
                style={{
                  color: "var(--color-text-tertiary)",
                  fontSize: "var(--text-sm)",
                  padding: "28px 10px",
                  textAlign: "center",
                }}
              >
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function renderCell(raw: FinancialGridCell | unknown, column: FinancialGridColumn) {
  const cell = normalizeCell(raw);
  if (cell.node) return cell.node;

  const valueType = cell.valueType ?? column.valueType ?? "number";
  const formatType = cell.formatType ?? column.formatType ?? typeToFormat(valueType);

  if (valueType === "delta") {
    return <DeltaBadge value={cell.value} />;
  }
  if (valueType === "text") {
    return (
      <span style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-sm)" }}>
        {formatText(cell.value)}
      </span>
    );
  }
  if (valueType === "currency-thousands") {
    return (
      <span
        className="font-mono"
        title={cell.title}
        style={{
          color: numericToneColor(cell.value, cell.tone),
          fontSize: "var(--text-xs)",
          fontVariantNumeric: "tabular-nums",
          fontWeight: 500,
        }}
      >
        {formatCurrencyThousands(cell.value)}
      </span>
    );
  }

  return (
    <NumberCell
      value={cell.value}
      formatType={formatType}
      tone={cell.tone ?? "neutral"}
      size="sm"
      title={cell.title}
    />
  );
}

function normalizeCell(raw: FinancialGridCell | unknown): FinancialGridCell {
  if (
    raw &&
    typeof raw === "object" &&
    ("value" in raw || "node" in raw || "valueType" in raw)
  ) {
    return raw as FinancialGridCell;
  }
  return { value: raw };
}

function typeToFormat(valueType: FinancialValueType): unknown {
  if (valueType === "percentage") return "pct";
  if (valueType === "multiple") return "ratio";
  if (valueType === "currency") return "money";
  if (valueType === "integer") return "integer";
  return "number";
}

function formatText(value: unknown): string {
  if (value === null || value === undefined || value === "") return EM_DASH;
  return String(value);
}

function formatCurrencyThousands(value: unknown): string {
  if (value === null || value === undefined || value === "") return EM_DASH;
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value);
  const reais = value * 1000;
  const absolute = Math.abs(reais);
  const sign = reais < 0 ? "-" : "";
  if (absolute >= 1_000_000_000) {
    return `${sign}R$ ${(absolute / 1_000_000_000).toLocaleString("en-US", {
      maximumFractionDigits: 1,
    })}B`;
  }
  if (absolute >= 1_000_000) {
    return `${sign}R$ ${(absolute / 1_000_000).toLocaleString("en-US", {
      maximumFractionDigits: 1,
    })}M`;
  }
  return `${sign}R$ ${absolute.toLocaleString("en-US", {
    maximumFractionDigits: 0,
  })}`;
}

function numericToneColor(
  value: unknown,
  tone: FinancialGridCell["tone"] = "neutral",
): string {
  if (tone === "positive") return "var(--color-num-pos)";
  if (tone === "negative") return "var(--color-num-neg)";
  if (tone === "muted") return "var(--color-text-tertiary)";
  if (tone === "auto" && typeof value === "number" && Number.isFinite(value)) {
    if (value > 0) return "var(--color-num-pos)";
    if (value < 0) return "var(--color-num-neg)";
  }
  return "var(--color-text-primary)";
}

export function formatGridValue(value: unknown, valueType: FinancialValueType): string {
  if (valueType === "currency-thousands") return formatCurrencyThousands(value);
  if (valueType === "text") return formatText(value);
  return formatKpiCell(value, typeToFormat(valueType));
}
