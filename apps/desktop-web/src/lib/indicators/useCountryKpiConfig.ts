/**
 * Country KPI workspace config — same shape as useIndicatorConfig but
 * stored under a separate key and without the frequency dimension (always annual).
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { ChartAesthetics, ChartType, IndicatorSelection } from "./types";

const STORAGE_KEY = "cvm:country-kpis:config:v1";

const DEFAULT_CHART: ChartAesthetics = {
  type: "line",
  smooth: true,
  markers: true,
  legend: true,
  grid: true,
  dataLabels: false,
  indexMode: false,
};

interface CountryKpiConfig {
  selected: IndicatorSelection[];  // id = iso_code
  chart: ChartAesthetics;
}

const CHART_TYPES: ChartType[] = ["line", "bar", "area"];

function defaultConfig(): CountryKpiConfig {
  return { selected: [], chart: { ...DEFAULT_CHART } };
}

function sanitize(raw: unknown): CountryKpiConfig {
  const base = defaultConfig();
  if (!raw || typeof raw !== "object") return base;
  const obj = raw as Record<string, unknown>;
  const selected: IndicatorSelection[] = [];
  if (Array.isArray(obj.selected)) {
    for (const item of obj.selected) {
      if (!item || typeof item !== "object") continue;
      const id = (item as { id?: unknown }).id;
      if (typeof id !== "string" || !id) continue;
      const axis = (item as { axis?: unknown }).axis;
      const type = (item as { type?: unknown }).type;
      selected.push({
        id,
        axis: axis === "left" || axis === "right" ? axis : "auto",
        type: type === "line" || type === "bar" || type === "area" ? type : "auto",
      });
    }
  }
  const cr = ((obj.chart ?? {}) as Record<string, unknown>);
  const chart: ChartAesthetics = {
    type: CHART_TYPES.includes(cr.type as ChartType) ? (cr.type as ChartType) : DEFAULT_CHART.type,
    smooth: typeof cr.smooth === "boolean" ? cr.smooth : DEFAULT_CHART.smooth,
    markers: typeof cr.markers === "boolean" ? cr.markers : DEFAULT_CHART.markers,
    legend: typeof cr.legend === "boolean" ? cr.legend : DEFAULT_CHART.legend,
    grid: typeof cr.grid === "boolean" ? cr.grid : DEFAULT_CHART.grid,
    dataLabels: typeof cr.dataLabels === "boolean" ? cr.dataLabels : DEFAULT_CHART.dataLabels,
    indexMode: typeof cr.indexMode === "boolean" ? cr.indexMode : DEFAULT_CHART.indexMode,
  };
  return { selected, chart };
}

function load(): CountryKpiConfig {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? sanitize(JSON.parse(raw)) : defaultConfig();
  } catch {
    return defaultConfig();
  }
}

export function useCountryKpiConfig(allIsoCodes: readonly string[]) {
  const [config, setConfig] = useState<CountryKpiConfig>(load);

  // Seed all countries selected on first use
  useEffect(() => {
    if (config.selected.length === 0 && allIsoCodes.length > 0) {
      setConfig(c => ({
        ...c,
        selected: allIsoCodes.map(iso => ({ id: iso, axis: "auto", type: "auto" })),
      }));
    }
  }, [allIsoCodes, config.selected.length]);

  // rAF-debounced persist
  const frame = useRef<number | null>(null);
  useEffect(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config)); } catch { /* ignore */ }
    });
    return () => { if (frame.current !== null) cancelAnimationFrame(frame.current); };
  }, [config]);

  const setSelected = useCallback((selected: IndicatorSelection[]) => {
    setConfig(c => ({ ...c, selected }));
  }, []);

  const setChart = useCallback((patch: Partial<ChartAesthetics>) => {
    setConfig(c => ({ ...c, chart: { ...c.chart, ...patch } }));
  }, []);

  return { config, setSelected, setChart };
}
