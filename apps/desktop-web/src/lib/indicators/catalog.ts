/**
 * Indicator catalog helpers.
 *
 * Indicators are NOT hardcoded here — they are derived at runtime from the KPI
 * table returned by the canonical Python engine, so the UI never drifts from
 * the real catalog. This module only provides presentation metadata: stable
 * category ordering, English group labels (UI-language policy: new strings in
 * English; the underlying `CATEGORIA` data is left untranslated), the default
 * indicator picks, and the colour palette.
 */
import type { TabularData, TabularRow } from "@/lib/bridge/types";
import type { IndicatorDef, IndicatorUnit } from "./types";

/** Categorical chart palette from index.css (`--color-chart-1..6`). */
export const SERIES_PALETTE = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
  "var(--color-chart-6)",
] as const;

/**
 * Display order + English labels for the engine's Portuguese categories.
 * Unknown categories fall back to their raw name and sort last, alphabetically.
 */
const CATEGORY_META: Record<string, { order: number; label: string }> = {
  Rentabilidade: { order: 0, label: "Profitability" },
  Retorno: { order: 1, label: "Returns" },
  Crescimento: { order: 2, label: "Growth" },
  Endividamento: { order: 3, label: "Leverage & Credit" },
  Liquidez: { order: 4, label: "Liquidity" },
  "Fluxo de Caixa": { order: 5, label: "Cash Flow" },
  Valuation: { order: 6, label: "Market & Valuation" },
};

/** Preferred default selection — intersected with what is actually available. */
const DEFAULT_INDICATOR_IDS = ["MG_EBITDA", "MG_LIQ", "ROE", "DIV_EBITDA"];

export function categoryLabel(category: string): string {
  return CATEGORY_META[category]?.label ?? category;
}

function categoryOrder(category: string): number {
  return CATEGORY_META[category]?.order ?? 100;
}

function toUnit(formatType: unknown): IndicatorUnit {
  const f = typeof formatType === "string" ? formatType.toLowerCase() : "";
  if (f === "pct") return "pct";
  if (f === "ratio") return "ratio";
  return "number";
}

function rowId(row: TabularRow): string {
  return String(row.KPI_ID ?? "").trim();
}

/** Period column keys (e.g. "2023", "1Q24") present on a KPI table. */
const META_COLUMNS = new Set([
  "KPI_ID",
  "KPI_NOME",
  "CATEGORIA",
  "FORMULA",
  "IS_PLACEHOLDER",
  "FORMAT_TYPE",
  "HIGHER_IS_BETTER",
  "UNIDADE",
  "DELTA_YOY",
  "DELTA_YOY_PCT",
]);

function rowHasFiniteValue(row: TabularRow, periodColumns: string[]): boolean {
  for (const col of periodColumns) {
    const v = row[col];
    if (typeof v === "number" && Number.isFinite(v)) return true;
  }
  return false;
}

/**
 * Build the list of selectable indicators from a KPI table. `available`
 * reflects whether the indicator has any finite value for THIS table
 * (frequency-specific), so a metric with annual but no quarterly coverage is
 * correctly shown as unavailable in quarterly mode.
 */
export function buildIndicatorDefs(table: TabularData | null): IndicatorDef[] {
  if (!table || table.rows.length === 0) return [];
  const periodColumns = table.columns.filter((c) => !META_COLUMNS.has(c));

  const defs: IndicatorDef[] = [];
  const seen = new Set<string>();
  for (const row of table.rows) {
    const id = rowId(row);
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const isPlaceholder = row.IS_PLACEHOLDER === true;
    defs.push({
      id,
      label: String(row.KPI_NOME ?? id),
      category: String(row.CATEGORIA ?? "—"),
      unit: toUnit(row.FORMAT_TYPE),
      isPlaceholder,
      available: !isPlaceholder && rowHasFiniteValue(row, periodColumns),
    });
  }

  defs.sort((a, b) => {
    const c = categoryOrder(a.category) - categoryOrder(b.category);
    if (c !== 0) return c;
    return a.category.localeCompare(b.category);
  });
  return defs;
}

/** Group indicators by category, preserving the sorted order. */
export function groupIndicators(
  defs: IndicatorDef[],
): Array<{ category: string; label: string; items: IndicatorDef[] }> {
  const groups: Array<{ category: string; label: string; items: IndicatorDef[] }> = [];
  const byCategory = new Map<string, IndicatorDef[]>();
  for (const def of defs) {
    let bucket = byCategory.get(def.category);
    if (!bucket) {
      bucket = [];
      byCategory.set(def.category, bucket);
      groups.push({ category: def.category, label: categoryLabel(def.category), items: bucket });
    }
    bucket.push(def);
  }
  return groups;
}

/**
 * Choose a sensible default selection: preferred ids that are available,
 * else the first few available indicators.
 */
export function defaultSelectedIds(defs: IndicatorDef[]): string[] {
  const available = defs.filter((d) => d.available);
  const preferred = DEFAULT_INDICATOR_IDS.filter((id) =>
    available.some((d) => d.id === id),
  );
  if (preferred.length > 0) return preferred;
  return available.slice(0, 3).map((d) => d.id);
}
