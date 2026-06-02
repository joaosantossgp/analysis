/**
 * Subsystem KPI workspace config — same shape as useCountryKpiConfig but
 * stored under a separate key.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { ChartAesthetics, ChartType, IndicatorSelection } from "./types";

const STORAGE_KEY = "cvm:subsystem-kpis:config:v2";

const DEFAULT_CHART: ChartAesthetics = {
  type: "line",
  smooth: true,
  markers: true,
  legend: true,
  grid: true,
  dataLabels: false,
  indexMode: false,
};

interface SubsystemKpiConfig {
  selected: IndicatorSelection[]; // id = subsystem_code (e.g. "S", "SE_CO", "NE", "N")
  chart: ChartAesthetics;
}

const CHART_TYPES: ChartType[] = ["line", "bar", "area"];

function defaultConfig(): SubsystemKpiConfig {
  return { selected: [], chart: { ...DEFAULT_CHART } };
}

function sanitize(raw: unknown): SubsystemKpiConfig {
  const base = defaultConfig();
  if (!raw || typeof raw !== "object") return base;
  const obj = raw as Record<string, unknown>;
  const selected: IndicatorSelection[] = [];
  const VALID_CODES = ["S", "SE_CO", "NE", "N"];
  if (Array.isArray(obj.selected)) {
    for (const item of obj.selected) {
      if (!item || typeof item !== "object") continue;
      const id = (item as { id?: unknown }).id;
      if (typeof id !== "string" || !id || !VALID_CODES.includes(id)) continue;
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

function load(): SubsystemKpiConfig {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? sanitize(JSON.parse(raw)) : defaultConfig();
  } catch {
    return defaultConfig();
  }
}

export function useSubsystemKpiConfig(allSubsystemCodes: readonly string[]) {
  const [config, setConfig] = useState<SubsystemKpiConfig>(load);

  // Seed all subsystems selected on first use
  useEffect(() => {
    if (config.selected.length === 0 && allSubsystemCodes.length > 0) {
      setConfig(c => ({
        ...c,
        selected: allSubsystemCodes.map(code => ({ id: code, axis: "auto", type: "auto" })),
      }));
    }
  }, [allSubsystemCodes, config.selected.length]);

  // rAF-debounced persist
  const frame = useRef<number | null>(null);
  useEffect(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
      } catch {
        /* ignore */
      }
    });
    return () => {
      if (frame.current !== null) cancelAnimationFrame(frame.current);
    };
  }, [config]);

  const setSelected = useCallback((selected: IndicatorSelection[]) => {
    setConfig(c => ({ ...c, selected }));
  }, []);

  const setChart = useCallback((patch: Partial<ChartAesthetics>) => {
    setConfig(c => ({ ...c, chart: { ...c.chart, ...patch } }));
  }, []);

  return { config, setSelected, setChart };
}
