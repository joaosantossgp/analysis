/**
 * Energy KPI API facade.
 *
 * Wraps the 6 bridge methods for the country-level Energy Utilities KPI layer.
 * All reads hit local SQLite — no network on read path.
 */
import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type {
  CountryKPICompareResponse,
  CountryKPISeriesResponse,
  CountryKPIValue,
  EnergyKPICatalogResponse,
  EnergyKPIHealthResponse,
  EnergyKPIRefreshResult,
  KPICatalogEntry,
  SINKPIDashboardResponse,
  SINKPIHealthResponse,
  SINKPIObservation,
  SINKPIRefreshParams,
  SINKPIRefreshResult,
  SINKPISeriesParams,
  SINKPISeriesResponse,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser mode — pywebview bridge is unavailable.";

// ── Result union types ────────────────────────────────────────────────────────

export type KPICatalogResult =
  | { mode: "desktop"; entries: KPICatalogEntry[] }
  | { mode: "browser"; entries: []; reason: string };

export type CountryKPISeriesResult =
  | { mode: "desktop"; values: CountryKPIValue[] }
  | { mode: "browser"; values: []; reason: string };

export type CountryKPICompareResult =
  | { mode: "desktop"; kpi_id: string; year: number; values: CountryKPIValue[] }
  | { mode: "browser"; values: []; reason: string };

export type EnergyKPIHealthResult =
  | { mode: "desktop"; health: EnergyKPIHealthResponse }
  | { mode: "browser"; health: null; reason: string };

export type EnergyKPIRefreshResult_ =
  | { mode: "desktop"; result: EnergyKPIRefreshResult }
  | { mode: "browser"; result: null; reason: string };

export type SINKPIDashboardResult =
  | { mode: "desktop"; dashboard: SINKPIDashboardResponse }
  | { mode: "browser"; dashboard: null; reason: string };

export type SINKPISeriesResult =
  | { mode: "desktop"; values: SINKPIObservation[] }
  | { mode: "browser"; values: []; reason: string };

export type SINKPIHealthResult =
  | { mode: "desktop"; health: SINKPIHealthResponse }
  | { mode: "browser"; health: null; reason: string };

export type SINKPIRefreshResult_ =
  | { mode: "desktop"; result: SINKPIRefreshResult }
  | { mode: "browser"; result: null; reason: string };

// ── Fetch functions ───────────────────────────────────────────────────────────

export async function fetchKPICatalog(params?: {
  sector?: string;
  v1_status?: string;
  dashboard_priority?: string;
  macro_category?: string;
}): Promise<KPICatalogResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", entries: [], reason: BROWSER_REASON };
  }
  const payload: EnergyKPICatalogResponse = await callBridge(
    "get_kpi_catalog",
    params ?? {},
  );
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", entries: payload.entries ?? [] };
}

export async function fetchCountryKPISeries(params: {
  kpi_ids?: string[];
  iso_codes?: string[];
  years?: number[];
}): Promise<CountryKPISeriesResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", values: [], reason: BROWSER_REASON };
  }
  const payload: CountryKPISeriesResponse = await callBridge(
    "get_country_kpi_series",
    params,
  );
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", values: payload.values ?? [] };
}

export async function fetchCountryKPICompare(params: {
  kpi_id: string;
  year: number;
}): Promise<CountryKPICompareResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", values: [], reason: BROWSER_REASON };
  }
  const payload: CountryKPICompareResponse = await callBridge(
    "get_country_kpi_compare",
    params,
  );
  if (payload.error) throw new Error(payload.error);
  return {
    mode: "desktop",
    kpi_id: payload.kpi_id,
    year: payload.year,
    values: payload.values ?? [],
  };
}

export async function fetchEnergyKPIHealth(): Promise<EnergyKPIHealthResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", health: null, reason: BROWSER_REASON };
  }
  const payload: EnergyKPIHealthResponse = await callBridge(
    "get_energy_kpi_health",
    {},
  );
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", health: payload };
}

export async function triggerEnergyKPIRefresh(): Promise<EnergyKPIRefreshResult_> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const payload: EnergyKPIRefreshResult = await callBridge(
    "refresh_energy_kpis",
    { triggered_by: "user" },
  );
  return { mode: "desktop", result: payload };
}

export async function exportCountryKPIsExcel(params?: {
  iso_codes?: string[];
  kpi_ids?: string[];
}): Promise<{ path: string | null; error?: string }> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { path: null, error: BROWSER_REASON };
  }
  return callBridge("export_country_kpis_excel", params ?? {});
}

export async function fetchSINKPIDashboard(): Promise<SINKPIDashboardResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", dashboard: null, reason: BROWSER_REASON };
  }
  const payload: SINKPIDashboardResponse = await callBridge(
    "get_sin_kpi_dashboard",
    {},
  );
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", dashboard: payload };
}

export async function fetchSINKPISeries(
  params?: SINKPISeriesParams,
): Promise<SINKPISeriesResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", values: [], reason: BROWSER_REASON };
  }
  const payload: SINKPISeriesResponse = await callBridge(
    "get_sin_kpi_series",
    params ?? {},
  );
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", values: payload.values ?? [] };
}

export async function fetchSINKPIHealth(): Promise<SINKPIHealthResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", health: null, reason: BROWSER_REASON };
  }
  const payload: SINKPIHealthResponse = await callBridge("get_sin_kpi_health", {});
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", health: payload };
}

export async function triggerSINKPIRefresh(
  params?: SINKPIRefreshParams,
): Promise<SINKPIRefreshResult_> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const payload: SINKPIRefreshResult = await callBridge(
    "refresh_sin_kpis",
    { triggered_by: "user", include_ccee: true, ...(params ?? {}) },
  );
  return { mode: "desktop", result: payload };
}
