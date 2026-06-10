/**
 * Axis / tick / label formatting for indicator charts. Value formatting reuses
 * the app-wide `formatKpiCell`; this module adds compact, unit-aware variants
 * for dense axis ticks and a unit symbol resolver per axis.
 */
import { formatKpiCell } from "@/lib/formatters";
import type { IndicatorUnit } from "./types";

function formatCompactNumber(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  return value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

/** Compact axis tick: percentages without decimals, ratios with one. */
export function formatAxisTick(value: number, unit: IndicatorUnit, indexMode: boolean): string {
  if (indexMode) return value.toFixed(0);
  if (unit === "brl") {
    return `R$ ${value.toLocaleString("pt-BR", { maximumFractionDigits: value >= 100 ? 0 : 2 })}`;
  }
  if (unit === "volume") return formatCompactNumber(value);
  if (unit === "pct") return `${(value * 100).toFixed(0)}%`;
  if (unit === "ratio") return `${value.toFixed(1)}x`;
  return value.toLocaleString("en-US", { maximumFractionDigits: 1 });
}

/** Full value for tooltips / data labels. */
export function formatValue(value: number | null, unit: IndicatorUnit, indexMode: boolean): string {
  if (value === null) return "—";
  if (indexMode) return value.toFixed(1);
  if (unit === "brl") {
    return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
  }
  if (unit === "volume") return formatCompactNumber(value);
  if (unit === "number") return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return formatKpiCell(value, unit);
}

export function axisUnitSymbol(unit: IndicatorUnit, indexMode: boolean): string {
  if (indexMode) return "Index (100)";
  if (unit === "brl") return "R$";
  if (unit === "volume") return "Volume";
  if (unit === "pct") return "%";
  if (unit === "ratio") return "x";
  return "";
}
