import { SERIES_PALETTE } from "@/lib/indicators/catalog";
import type {
  ChartType,
  IndicatorDef,
  IndicatorUnit,
  ResolvedSeries,
} from "@/lib/indicators/types";
import type { CompanyMarketHistoryObservation } from "@/lib/bridge/types";

export type MarketView = "price" | "return" | "yield" | "volume";
export type MarketPeriod = "1M" | "3M" | "6M" | "YTD" | "1Y" | "3Y" | "5Y" | "10Y" | "MAX" | "custom";
export type MarketSeriesId =
  | "close"
  | "adjusted_close"
  | "price_return_index"
  | "total_return_index"
  | "ttm_dividend_yield"
  | "volume";

export const MARKET_PERIOD_OPTIONS: Array<{ value: MarketPeriod; label: string }> = [
  { value: "1M", label: "1M" },
  { value: "3M", label: "3M" },
  { value: "6M", label: "6M" },
  { value: "YTD", label: "YTD" },
  { value: "1Y", label: "1Y" },
  { value: "3Y", label: "3Y" },
  { value: "5Y", label: "5Y" },
  { value: "10Y", label: "10Y" },
  { value: "MAX", label: "MAX" },
  { value: "custom", label: "Custom" },
];

export const MARKET_VIEW_OPTIONS: Array<{ value: MarketView; label: string }> = [
  { value: "price", label: "Price" },
  { value: "return", label: "Return" },
  { value: "yield", label: "Dividend Yield" },
  { value: "volume", label: "Volume" },
];

export const MARKET_VIEW_LABEL: Record<MarketView, string> = {
  price: "Price",
  return: "Return",
  yield: "Dividend Yield",
  volume: "Volume",
};

export const MARKET_VIEW_UNIT: Record<MarketView, IndicatorUnit> = {
  price: "brl",
  return: "pct",
  yield: "pct",
  volume: "volume",
};

export const MARKET_MAX_UNITS = 2;

export const MARKET_CHART_TYPES: Record<MarketView, ChartType[]> = {
  price: ["line", "area"],
  return: ["line", "area"],
  yield: ["line", "area", "bar"],
  volume: ["bar", "line"],
};

export const MARKET_DEFAULT_CHART_TYPE: Record<MarketView, ChartType> = {
  price: "line",
  return: "line",
  yield: "line",
  volume: "bar",
};

export const MARKET_DEFAULT_SERIES: Record<MarketView, MarketSeriesId[]> = {
  price: ["adjusted_close"],
  return: ["price_return_index", "total_return_index"],
  yield: ["ttm_dividend_yield"],
  volume: ["volume"],
};

export const MARKET_MAX_SELECTED_SERIES: Record<MarketView, number> = {
  price: 2,
  return: 2,
  yield: 1,
  volume: 1,
};

interface MarketSeriesDefinition {
  id: MarketSeriesId;
  view: MarketView;
  label: string;
  unit: IndicatorUnit;
  field: keyof CompanyMarketHistoryObservation;
}

export const MARKET_SERIES_DEFS: Record<MarketSeriesId, MarketSeriesDefinition> = {
  close: {
    id: "close",
    view: "price",
    label: "Close Price",
    unit: "brl",
    field: "close",
  },
  adjusted_close: {
    id: "adjusted_close",
    view: "price",
    label: "Adjusted Close",
    unit: "brl",
    field: "adjusted_close",
  },
  price_return_index: {
    id: "price_return_index",
    view: "return",
    label: "Price Return",
    unit: "pct",
    field: "price_return_index",
  },
  total_return_index: {
    id: "total_return_index",
    view: "return",
    label: "Total Shareholder Return",
    unit: "pct",
    field: "total_return_index",
  },
  ttm_dividend_yield: {
    id: "ttm_dividend_yield",
    view: "yield",
    label: "TTM Dividend Yield",
    unit: "pct",
    field: "ttm_dividend_yield",
  },
  volume: {
    id: "volume",
    view: "volume",
    label: "Trading Volume",
    unit: "volume",
    field: "volume",
  },
};

function uniqueViews(views: MarketView[]): MarketView[] {
  return views.filter((view, index) => views.indexOf(view) === index);
}

export function sanitizeMarketMetricSelection(views: MarketView[]): MarketView[] {
  const selected = uniqueViews(views).filter((view) => MARKET_VIEW_OPTIONS.some((option) => option.value === view));
  if (selected.length === 0) return ["price"];

  const units = new Set<IndicatorUnit>();
  return selected.filter((view) => {
    const unit = MARKET_VIEW_UNIT[view];
    if (units.has(unit) || units.size < MARKET_MAX_UNITS) {
      units.add(unit);
      return true;
    }
    return false;
  });
}

export function canEnableMarketMetric(selectedViews: MarketView[], candidate: MarketView): boolean {
  if (selectedViews.includes(candidate)) return true;
  const units = new Set(selectedViews.map((view) => MARKET_VIEW_UNIT[view]));
  return units.has(MARKET_VIEW_UNIT[candidate]) || units.size < MARKET_MAX_UNITS;
}

function seriesForViews(views: MarketView[]): MarketSeriesId[] {
  const selected = new Set(views);
  return (Object.keys(MARKET_SERIES_DEFS) as MarketSeriesId[]).filter((id) => selected.has(MARKET_SERIES_DEFS[id].view));
}

function numericOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function latestFinite(points: Array<number | null>): number | null {
  return [...points].reverse().find((v): v is number => v !== null) ?? null;
}

function indexToBase100(points: Array<number | null>): Array<number | null> {
  const base = points.find((v): v is number => v !== null);
  if (base === undefined || base === 0) return points;
  return points.map((v) => (v === null ? null : (v / base) * 100));
}

function rawPointForSeries(
  observation: CompanyMarketHistoryObservation,
  seriesId: MarketSeriesId,
): number | null {
  if (seriesId === "price_return_index") {
    const value = numericOrNull(observation.price_return_index);
    return value === null ? null : value - 1;
  }
  if (seriesId === "total_return_index") {
    const value = numericOrNull(observation.total_return_index);
    return value === null ? null : value - 1;
  }
  return numericOrNull(observation[MARKET_SERIES_DEFS[seriesId].field]);
}

export function getAvailableMarketSeries(
  observations: CompanyMarketHistoryObservation[],
  views: MarketView[],
): MarketSeriesId[] {
  return seriesForViews(sanitizeMarketMetricSelection(views)).filter((seriesId) =>
    observations.some((observation) => rawPointForSeries(observation, seriesId) !== null),
  );
}

export function getMarketSeriesPickerDefs(
  observations: CompanyMarketHistoryObservation[],
  views: MarketView[],
): IndicatorDef[] {
  const available = new Set(getAvailableMarketSeries(observations, views));
  return seriesForViews(sanitizeMarketMetricSelection(views))
    .filter((id) => available.has(id))
    .map((id) => {
      const def = MARKET_SERIES_DEFS[id];
      return {
        id,
        label: def.label,
        category: MARKET_VIEW_LABEL[def.view],
        unit: def.unit,
        isPlaceholder: false,
        available: true,
      };
    });
}

export function sanitizeMarketSeriesSelection(
  views: MarketView[],
  selectedIds: MarketSeriesId[],
  availableIds: MarketSeriesId[],
): MarketSeriesId[] {
  const available = new Set(availableIds);
  const selectedViews = new Set(sanitizeMarketMetricSelection(views));
  return selectedIds.filter((id) => selectedViews.has(MARKET_SERIES_DEFS[id]?.view) && available.has(id));
}

export function normalizeMarketChartType(views: MarketView[], chartType: ChartType): ChartType {
  const selected = sanitizeMarketMetricSelection(views);
  const supported = MARKET_CHART_TYPES[selected[0]].filter((type) =>
    selected.every((view) => MARKET_CHART_TYPES[view].includes(type)),
  );
  return supported.includes(chartType) ? chartType : supported[0] ?? "line";
}

export function buildMarketChartSeries({
  observations,
  views,
  selectedIds,
  chartType,
  indexMode,
  seriesStyles = {},
}: {
  observations: CompanyMarketHistoryObservation[];
  views: MarketView[];
  selectedIds: MarketSeriesId[];
  chartType: ChartType;
  indexMode: boolean;
  seriesStyles?: Partial<Record<MarketSeriesId, { color?: string; type?: ChartType }>>;
}): ResolvedSeries[] {
  const selectedViews = sanitizeMarketMetricSelection(views);
  const available = getAvailableMarketSeries(observations, selectedViews);
  const seriesIds = sanitizeMarketSeriesSelection(selectedViews, selectedIds, available);
  const effectiveIndexMode = selectedViews.length === 1 && selectedViews[0] === "price" && indexMode;
  const units = [...new Set(seriesIds.map((id) => MARKET_SERIES_DEFS[id].unit))];
  const primaryUnit = units[0] ?? "number";

  return seriesIds.map((id, index) => {
    const def = MARKET_SERIES_DEFS[id];
    const rawPoints = observations.map((observation) => rawPointForSeries(observation, id));
    const points = effectiveIndexMode ? indexToBase100(rawPoints) : rawPoints;
    const isSecondaryClose =
      MARKET_SERIES_DEFS[id].view === "price" && id === "close" && seriesIds.includes("adjusted_close");
    return {
      id,
      label: def.label,
      unit: effectiveIndexMode ? "number" : def.unit,
      color: seriesStyles[id]?.color ?? SERIES_PALETTE[index % SERIES_PALETTE.length],
      type: seriesStyles[id]?.type ?? normalizeMarketChartType(selectedViews, chartType),
      axis: units.length > 1 && def.unit !== primaryUnit ? "right" : "left",
      points,
      latest: latestFinite(points),
      opacity: isSecondaryClose ? 0.55 : 1,
      strokeDasharray: isSecondaryClose ? "5 4" : undefined,
    };
  });
}

export const MARKET_DENSE_MARKER_THRESHOLD = 40;

export function shouldRenderMarketMarkers(markersEnabled: boolean, observationCount: number): boolean {
  return markersEnabled && observationCount <= MARKET_DENSE_MARKER_THRESHOLD;
}

export function xTickAnchor(index: number, count: number): "start" | "middle" | "end" {
  if (index === 0) return "start";
  if (index === count - 1) return "end";
  return "middle";
}

export function buildMarketPeriods(observations: CompanyMarketHistoryObservation[]): string[] {
  return observations.map((observation) => observation.date);
}

export function formatMarketDateTick(date: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  if (!match) return date;
  return `${match[3]}/${match[2]}/${match[1].slice(2)}`;
}
