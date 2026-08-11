/**
 * Workspace configuration state with safe, scoped localStorage persistence.
 *
 * The config is a *view preference* (chart type, aesthetics, frequency,
 * selected indicators) shared across companies, so it persists under a single
 * key. All reads/writes are wrapped in try/catch and shape-validated, so a
 * corrupt or absent value degrades to defaults rather than throwing.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type {
  ChartAesthetics,
  ChartType,
  Frequency,
  IndicatorConfig,
  IndicatorSelection,
} from "./types";

const STORAGE_KEY = "cvm:indicators:config:v1";

const DEFAULT_AESTHETICS: ChartAesthetics = {
  type: "line",
  smooth: false,
  markers: true,
  legend: true,
  grid: true,
  dataLabels: false,
  indexMode: false,
};

function defaultConfig(): IndicatorConfig {
  return { frequency: "annual", selected: [], chart: { ...DEFAULT_AESTHETICS } };
}

const CHART_TYPES: ChartType[] = ["line", "bar", "area"];

function sanitizeSelection(raw: unknown): IndicatorSelection[] {
  if (!Array.isArray(raw)) return [];
  const out: IndicatorSelection[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const id = (item as { id?: unknown }).id;
    if (typeof id !== "string" || id.length === 0) continue;
    const axis = (item as { axis?: unknown }).axis;
    const type = (item as { type?: unknown }).type;
    const color = (item as { color?: unknown }).color;
    out.push({
      id,
      axis: axis === "left" || axis === "right" ? axis : "auto",
      type: type === "line" || type === "bar" || type === "area" ? type : "auto",
      ...(typeof color === "string" && /^#[0-9a-f]{6}$/i.test(color) ? { color } : {}),
    });
  }
  return out;
}

function sanitizeConfig(raw: unknown): IndicatorConfig {
  const base = defaultConfig();
  if (!raw || typeof raw !== "object") return base;
  const obj = raw as Record<string, unknown>;
  const frequency: Frequency = obj.frequency === "quarterly" ? "quarterly" : "annual";
  const chartRaw = (obj.chart ?? {}) as Record<string, unknown>;
  const chart: ChartAesthetics = {
    type: CHART_TYPES.includes(chartRaw.type as ChartType)
      ? (chartRaw.type as ChartType)
      : DEFAULT_AESTHETICS.type,
    smooth: typeof chartRaw.smooth === "boolean" ? chartRaw.smooth : DEFAULT_AESTHETICS.smooth,
    markers: typeof chartRaw.markers === "boolean" ? chartRaw.markers : DEFAULT_AESTHETICS.markers,
    legend: typeof chartRaw.legend === "boolean" ? chartRaw.legend : DEFAULT_AESTHETICS.legend,
    grid: typeof chartRaw.grid === "boolean" ? chartRaw.grid : DEFAULT_AESTHETICS.grid,
    dataLabels:
      typeof chartRaw.dataLabels === "boolean" ? chartRaw.dataLabels : DEFAULT_AESTHETICS.dataLabels,
    indexMode:
      typeof chartRaw.indexMode === "boolean" ? chartRaw.indexMode : DEFAULT_AESTHETICS.indexMode,
  };
  return { frequency, selected: sanitizeSelection(obj.selected), chart };
}

function loadConfig(): IndicatorConfig {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultConfig();
    return sanitizeConfig(JSON.parse(raw));
  } catch {
    return defaultConfig();
  }
}

export interface UseIndicatorConfig {
  config: IndicatorConfig;
  setFrequency: (frequency: Frequency) => void;
  setSelected: (selected: IndicatorSelection[]) => void;
  setChart: (patch: Partial<ChartAesthetics>) => void;
}

export function useIndicatorConfig(): UseIndicatorConfig {
  const [config, setConfig] = useState<IndicatorConfig>(loadConfig);

  // Persist (debounced via rAF) without blocking interaction.
  const frameRef = useRef<number | null>(null);
  useEffect(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(() => {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
      } catch {
        /* storage unavailable / quota — ignore, config stays in memory */
      }
    });
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [config]);

  const setFrequency = useCallback((frequency: Frequency) => {
    setConfig((c) => (c.frequency === frequency ? c : { ...c, frequency }));
  }, []);

  const setSelected = useCallback((selected: IndicatorSelection[]) => {
    setConfig((c) => ({ ...c, selected }));
  }, []);

  const setChart = useCallback((patch: Partial<ChartAesthetics>) => {
    setConfig((c) => ({ ...c, chart: { ...c.chart, ...patch } }));
  }, []);

  return { config, setFrequency, setSelected, setChart };
}
