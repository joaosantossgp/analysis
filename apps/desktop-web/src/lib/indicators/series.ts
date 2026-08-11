/**
 * Transform a raw KPI `TabularData` into chart-ready series.
 *
 * Period handling mirrors the Python engine's PERIOD_LABEL convention:
 *   - Annual anchor:  "2023"        → (year 2023, quarter 99)
 *   - Quarter:        "1Q24"        → (year 2024, quarter 1)
 * The engine omits Q4 (redundant with the annual close) and computes quarterly
 * flow metrics on an LTM (trailing-4-quarter) basis, so quarterly points are
 * directly comparable to annual ones. We never re-derive any of that here — we
 * only select and order the columns the engine already produced.
 */
import type { TabularData, TabularRow } from "@/lib/bridge/types";
import { SERIES_PALETTE } from "./catalog";
import type {
  AxisSide,
  ChartType,
  Frequency,
  IndicatorSelection,
  IndicatorUnit,
  ResolvedSeries,
} from "./types";

interface ParsedPeriod {
  label: string;
  year: number;
  quarter: number; // 1..4 for quarters, 99 for the annual anchor
  sort: number;
}

/** Parse a PERIOD_LABEL. Returns null for non-period (meta) columns. */
export function parsePeriod(label: string): ParsedPeriod | null {
  const q = /^([1-4])Q(\d{2})$/.exec(label);
  if (q) {
    const year = 2000 + Number(q[2]);
    const quarter = Number(q[1]);
    return { label, year, quarter, sort: year * 10 + quarter };
  }
  const y = /^(\d{4})$/.exec(label);
  if (y) {
    const year = Number(y[1]);
    return { label, year, quarter: 99, sort: year * 10 + 9 };
  }
  return null;
}

/**
 * Ordered period columns for a frequency, restricted to `selectedYears`.
 *   - annual    → pure-year columns ("2023")
 *   - quarterly → quarter columns ("1Q24"); the annual anchors are dropped so
 *                 the x-axis is evenly spaced and unambiguous.
 */
export function selectPeriods(
  table: TabularData | null,
  frequency: Frequency,
  selectedYears: number[],
): string[] {
  if (!table) return [];
  const yearSet = new Set(selectedYears);
  const parsed: ParsedPeriod[] = [];
  for (const col of table.columns) {
    const p = parsePeriod(col);
    if (!p) continue;
    if (selectedYears.length > 0 && !yearSet.has(p.year)) continue;
    const isAnnual = p.quarter === 99;
    if (frequency === "annual" ? isAnnual : !isAnnual) parsed.push(p);
  }
  parsed.sort((a, b) => a.sort - b.sort);
  return parsed.map((p) => p.label);
}

function numericOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toUnit(formatType: unknown): IndicatorUnit {
  const f = typeof formatType === "string" ? formatType.toLowerCase() : "";
  if (f === "pct") return "pct";
  if (f === "ratio") return "ratio";
  return "number";
}

/** Rebase a point array so the first finite value becomes 100. */
function indexToBase100(points: Array<number | null>): Array<number | null> {
  const base = points.find((v): v is number => v !== null);
  if (base === undefined || base === 0) return points;
  return points.map((v) => (v === null ? null : (v / base) * 100));
}

/**
 * Resolve the concrete render series for the selected indicators.
 *
 * Axis resolution ("auto"): when the selection mixes pct and ratio units, pct
 * series go on the left axis and ratio series on the right. With a single unit
 * everything shares the left axis (no misleading dual axis). In index mode all
 * series collapse to the left axis since they share a unitless 0–base scale.
 */
export function resolveSeries(
  table: TabularData | null,
  periods: string[],
  selection: IndicatorSelection[],
  globalType: ChartType,
  indexMode: boolean,
): ResolvedSeries[] {
  if (!table || periods.length === 0 || selection.length === 0) return [];

  const rowsById = new Map<string, TabularRow>();
  for (const row of table.rows) {
    const id = String(row.KPI_ID ?? "").trim();
    if (id) rowsById.set(id, row);
  }

  const units = new Map<string, IndicatorUnit>();
  for (const sel of selection) {
    const row = rowsById.get(sel.id);
    if (row) units.set(sel.id, toUnit(row.FORMAT_TYPE));
  }
  const distinctUnits = new Set(units.values());
  const dualAxis = !indexMode && distinctUnits.size > 1;

  const out: ResolvedSeries[] = [];
  let colorIndex = 0;
  for (const sel of selection) {
    const row = rowsById.get(sel.id);
    if (!row) continue;
    const unit = units.get(sel.id) ?? "number";

    let points = periods.map((p) => numericOrNull(row[p]));
    if (indexMode) points = indexToBase100(points);

    let axis: AxisSide;
    if (indexMode) {
      axis = "left";
    } else if (sel.axis !== "auto") {
      axis = sel.axis;
    } else if (dualAxis) {
      axis = unit === "pct" ? "left" : "right";
    } else {
      axis = "left";
    }

    const latest = [...points].reverse().find((v): v is number => v !== null) ?? null;

    out.push({
      id: sel.id,
      label: String(row.KPI_NOME ?? sel.id),
      unit: indexMode ? "number" : unit,
      color: sel.color ?? SERIES_PALETTE[colorIndex % SERIES_PALETTE.length],
      type: sel.type === "auto" ? globalType : sel.type,
      axis,
      points,
      latest,
    });
    colorIndex += 1;
  }
  return out;
}
