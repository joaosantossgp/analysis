import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ChartAesthetics, ChartType } from "@/lib/indicators/types";

import {
  MARKET_DEFAULT_CHART_TYPE,
  MARKET_DEFAULT_SERIES,
  MARKET_MAX_SELECTED_SERIES,
  MARKET_PERIOD_OPTIONS,
  normalizeMarketChartType,
  sanitizeMarketMetricSelection,
  type MarketPeriod,
  type MarketSeriesId,
  type MarketView,
} from "./series";

const STORAGE_KEY = "cvm:market-history:chart-config:v1";

export interface MarketHistoryChartConfig {
  selectedViews: MarketView[];
  period: MarketPeriod;
  selectedSeriesByView: Record<MarketView, MarketSeriesId[]>;
  seriesStyles: Partial<Record<MarketSeriesId, { color?: string; type?: ChartType }>>;
  chartType: ChartType;
  smooth: boolean;
  markers: boolean;
  legend: boolean;
  grid: boolean;
  dataLabels: boolean;
  indexMode: boolean;
}

const MARKET_VIEWS: MarketView[] = ["price", "return", "yield", "volume"];
const NON_CUSTOM_PERIODS = MARKET_PERIOD_OPTIONS.map((option) => option.value).filter(
  (value): value is Exclude<MarketPeriod, "custom"> => value !== "custom",
);

function defaultConfig(): MarketHistoryChartConfig {
  return {
    selectedViews: ["price"],
    period: "1Y",
    selectedSeriesByView: {
      price: [...MARKET_DEFAULT_SERIES.price],
      return: [...MARKET_DEFAULT_SERIES.return],
      yield: [...MARKET_DEFAULT_SERIES.yield],
      volume: [...MARKET_DEFAULT_SERIES.volume],
    },
    seriesStyles: {},
    chartType: MARKET_DEFAULT_CHART_TYPE.price,
    smooth: false,
    markers: true,
    legend: true,
    grid: true,
    dataLabels: false,
    indexMode: false,
  };
}

function isMarketView(value: unknown): value is MarketView {
  return typeof value === "string" && MARKET_VIEWS.includes(value as MarketView);
}

function sanitizeSelectedSeries(
  view: MarketView,
  raw: unknown,
): MarketSeriesId[] {
  const allowed = new Set<MarketSeriesId>(
    view === "price"
      ? ["adjusted_close", "close"]
      : view === "return"
        ? ["price_return_index", "total_return_index"]
        : MARKET_DEFAULT_SERIES[view],
  );
  if (!Array.isArray(raw)) return [...MARKET_DEFAULT_SERIES[view]];
  const out: MarketSeriesId[] = [];
  for (const item of raw) {
    if (typeof item !== "string" || !allowed.has(item as MarketSeriesId)) continue;
    if (!out.includes(item as MarketSeriesId)) out.push(item as MarketSeriesId);
  }
  return out.length > 0 ? out.slice(0, MARKET_MAX_SELECTED_SERIES[view]) : [...MARKET_DEFAULT_SERIES[view]];
}

function sanitizeConfig(raw: unknown): MarketHistoryChartConfig {
  const base = defaultConfig();
  if (!raw || typeof raw !== "object") return base;
  const obj = raw as Record<string, unknown>;
  const selectedViews = sanitizeMarketMetricSelection(
    Array.isArray(obj.selectedViews)
      ? obj.selectedViews.filter(isMarketView)
      : [isMarketView(obj.view) ? obj.view : base.selectedViews[0]],
  );
  const period =
    typeof obj.period === "string" && NON_CUSTOM_PERIODS.includes(obj.period as Exclude<MarketPeriod, "custom">)
      ? (obj.period as MarketPeriod)
      : base.period;

  const selectedRaw = (obj.selectedSeriesByView ?? {}) as Record<string, unknown>;
  const styleRaw = (obj.seriesStyles ?? {}) as Record<string, unknown>;
  const typeRaw = (obj.chartTypeByView ?? {}) as Record<string, unknown>;
  const selectedSeriesByView = MARKET_VIEWS.reduce(
    (acc, item) => {
      acc[item] = sanitizeSelectedSeries(item, selectedRaw[item]);
      return acc;
    },
    {} as Record<MarketView, MarketSeriesId[]>,
  );
  const legacyView = selectedViews[0];
  const chartType = normalizeMarketChartType(
    selectedViews,
    (obj.chartType as ChartType | undefined) ?? (typeRaw[legacyView] as ChartType),
  );

  return {
    selectedViews,
    period,
    selectedSeriesByView,
    seriesStyles: Object.fromEntries(
      Object.entries(styleRaw).flatMap(([id, style]) => {
        if (!style || typeof style !== "object") return [];
        const value = style as Record<string, unknown>;
        const color = typeof value.color === "string" && /^#[0-9a-f]{6}$/i.test(value.color) ? value.color : undefined;
        const type = value.type === "line" || value.type === "bar" || value.type === "area" ? value.type : undefined;
        return color || type ? [[id, { ...(color ? { color } : {}), ...(type ? { type } : {}) }]] : [];
      }),
    ) as MarketHistoryChartConfig["seriesStyles"],
    chartType,
    smooth: typeof obj.smooth === "boolean" ? obj.smooth : base.smooth,
    markers: typeof obj.markers === "boolean" ? obj.markers : base.markers,
    legend: typeof obj.legend === "boolean" ? obj.legend : base.legend,
    grid: typeof obj.grid === "boolean" ? obj.grid : base.grid,
    dataLabels: typeof obj.dataLabels === "boolean" ? obj.dataLabels : base.dataLabels,
    indexMode: typeof obj.indexMode === "boolean" ? obj.indexMode : base.indexMode,
  };
}

function loadConfig(): MarketHistoryChartConfig {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultConfig();
    return sanitizeConfig(JSON.parse(raw));
  } catch {
    return defaultConfig();
  }
}

function persistableConfig(config: MarketHistoryChartConfig): MarketHistoryChartConfig {
  return {
    ...config,
    period: config.period === "custom" ? "1Y" : config.period,
  };
}

export function chartAestheticsForMarketConfig(config: MarketHistoryChartConfig): ChartAesthetics {
  const type = normalizeMarketChartType(config.selectedViews, config.chartType);
  return {
    type,
    smooth: type === "bar" ? false : config.smooth,
    markers: config.markers,
    legend: config.legend,
    grid: config.grid,
    dataLabels: config.dataLabels,
    indexMode: config.selectedViews.length === 1 && config.selectedViews[0] === "price" ? config.indexMode : false,
  };
}

export function useMarketHistoryConfig() {
  const [config, setConfig] = useState<MarketHistoryChartConfig>(loadConfig);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(() => {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(persistableConfig(config)));
      } catch {
        /* localStorage unavailable / quota exceeded: keep in-memory config */
      }
    });
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [config]);

  const chart = useMemo(() => chartAestheticsForMarketConfig(config), [config]);

  const setSelectedViews = useCallback((selectedViews: MarketView[]) => {
    setConfig((current) => {
      const next = sanitizeMarketMetricSelection(selectedViews);
      return {
        ...current,
        selectedViews: next,
        chartType: normalizeMarketChartType(next, current.chartType),
      };
    });
  }, []);

  const setPeriod = useCallback((period: MarketPeriod) => {
    setConfig((current) => (current.period === period ? current : { ...current, period }));
  }, []);

  const setSelectedSeries = useCallback((view: MarketView, selected: MarketSeriesId[]) => {
    setConfig((current) => ({
      ...current,
      selectedSeriesByView: {
        ...current.selectedSeriesByView,
        [view]: selected,
      },
    }));
  }, []);

  const setChartType = useCallback((type: ChartType) => {
    setConfig((current) => ({
      ...current,
      chartType: normalizeMarketChartType(current.selectedViews, type),
    }));
  }, []);

  const setSeriesStyle = useCallback((id: MarketSeriesId, patch: { color?: string; type?: ChartType }) => {
    setConfig((current) => ({
      ...current,
      seriesStyles: { ...current.seriesStyles, [id]: { ...current.seriesStyles[id], ...patch } },
    }));
  }, []);

  const setChartOptions = useCallback((patch: Partial<Omit<ChartAesthetics, "type">>) => {
    setConfig((current) => ({
      ...current,
      smooth: patch.smooth ?? current.smooth,
      markers: patch.markers ?? current.markers,
      legend: patch.legend ?? current.legend,
      grid: patch.grid ?? current.grid,
      dataLabels: patch.dataLabels ?? current.dataLabels,
      indexMode: patch.indexMode ?? current.indexMode,
    }));
  }, []);

  return {
    config,
    chart,
    setSelectedViews,
    setPeriod,
    setSelectedSeries,
    setChartType,
    setSeriesStyle,
    setChartOptions,
    storageKey: STORAGE_KEY,
  };
}
