/**
 * Type contracts for the configurable company Indicators workspace.
 *
 * The financial calculation lives entirely in the Python KPI engine
 * (`src/financials/kpi_engine.py`, surfaced through `get_company_kpis`). These types only
 * describe the *presentation* configuration and the chart-ready shapes that the
 * transform layer (`series.ts`) produces from the raw `KPIBundle`.
 */

/** Visualisation frequency. Maps to `bundle.annual` / `bundle.quarterly`. */
export type Frequency = "annual" | "quarterly";

/** Base chart type applied globally, and the per-series override target. */
export type ChartType = "line" | "bar" | "area";

/** Y-axis a series is plotted against. */
export type AxisSide = "left" | "right";

/**
 * Indicator unit family, derived from the KPI engine `FORMAT_TYPE`.
 * The engine only emits `pct` and `ratio`, but we keep `number` as a safe
 * fallback so unknown future formats still render.
 */
export type IndicatorUnit = "pct" | "ratio" | "number" | "brl" | "volume";

/** A KPI the user can pick, derived at runtime from the active KPI table. */
export interface IndicatorDef {
  /** KPI_ID, e.g. "MG_EBITDA". */
  id: string;
  /** KPI_NOME, e.g. "Margem EBITDA". */
  label: string;
  /** CATEGORIA from the engine, e.g. "Rentabilidade". */
  category: string;
  unit: IndicatorUnit;
  /** Engine `IS_PLACEHOLDER` — indicator is defined but not yet computable. */
  isPlaceholder: boolean;
  /** True when at least one period in the active table holds a finite value. */
  available: boolean;
}

/** Aesthetic toggles that apply to the whole chart. */
export interface ChartAesthetics {
  type: ChartType;
  /** Smooth (monotone) vs straight line segments. Line/area only. */
  smooth: boolean;
  markers: boolean;
  legend: boolean;
  grid: boolean;
  dataLabels: boolean;
  /** Rebase every series to 100 at its first valid point (single-axis view). */
  indexMode: boolean;
}

/** Per-indicator selection state with optional axis / type overrides. */
export interface IndicatorSelection {
  id: string;
  /** "auto" assigns by unit (see resolveSeries). */
  axis: "auto" | AxisSide;
  /** "auto" uses the global chart type; otherwise forces a per-series type. */
  type: "auto" | ChartType;
  /** Optional analyst-selected color, persisted with this chart selection. */
  color?: string;
}

/** The full, persisted workspace configuration. */
export interface IndicatorConfig {
  frequency: Frequency;
  /** Ordered — selection order drives colour and legend order. */
  selected: IndicatorSelection[];
  chart: ChartAesthetics;
}

/** A series resolved for rendering: colour, axis and type are concrete. */
export interface ResolvedSeries {
  id: string;
  label: string;
  unit: IndicatorUnit;
  color: string;
  type: ChartType;
  axis: AxisSide;
  /** One entry per period in `periods`, aligned by index. */
  points: Array<number | null>;
  /** Latest finite value (for legend), or null. */
  latest: number | null;
  /** Optional presentation overrides for dense or secondary series. */
  opacity?: number;
  strokeDasharray?: string;
}
