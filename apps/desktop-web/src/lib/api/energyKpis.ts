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
  PlantParcelCatalogParams,
  PlantParcelCatalogRecord,
  PlantParcelCatalogResponse,
  PlantParcelDetailParams,
  PlantParcelDetailResponse,
  PlantParcelRefreshParams,
  PlantParcelRefreshResult,
  PlantParcelSourceStatus,
  PlantParcelSourceStatusResponse,
  PlantParcelChartDataParams,
  PlantParcelChartDataResponse,
  EnergyMartStatusResponse,
  EnergyMartRebuildState,
  StartEnergyMartRebuildParams,
  PlantParcelFilePickerResult,
  PlantParcelManualImportParams,
  PlantParcelManualImportResult,
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

export type PlantParcelSourceStatusResult =
  | { mode: "desktop"; statuses: PlantParcelSourceStatus[]; response: PlantParcelSourceStatusResponse }
  | { mode: "browser"; statuses: []; response: null; reason: string };

export type PlantParcelCatalogResult =
  | { mode: "desktop"; records: PlantParcelCatalogRecord[]; response: PlantParcelCatalogResponse }
  | { mode: "browser"; records: []; response: null; reason: string };

export type PlantParcelDetailResult =
  | { mode: "desktop"; detail: PlantParcelDetailResponse }
  | { mode: "browser"; detail: null; reason: string };

export type PlantParcelChartDataResult =
  | { mode: "desktop"; data: PlantParcelChartDataResponse }
  | { mode: "browser"; data: null; reason: string };

export type EnergyMartStatusResult =
  | { mode: "desktop"; status: EnergyMartStatusResponse }
  | { mode: "browser"; status: null; reason: string };

export type EnergyMartRebuildResult =
  | { mode: "desktop"; result: EnergyMartRebuildState }
  | { mode: "browser"; result: null; reason: string };

export type PlantParcelRefreshResult_ =
  | { mode: "desktop"; result: PlantParcelRefreshResult }
  | { mode: "browser"; result: null; reason: string };

export type PlantParcelFilePickerResult_ =
  | { mode: "desktop"; result: PlantParcelFilePickerResult }
  | { mode: "browser"; result: null; reason: string };

export type PlantParcelManualImportResult_ =
  | { mode: "desktop"; result: PlantParcelManualImportResult }
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

export async function fetchPlantParcelSourceStatuses(params?: {
  source_ids?: string[];
}): Promise<PlantParcelSourceStatusResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", statuses: [], response: null, reason: BROWSER_REASON };
  }
  const payload: PlantParcelSourceStatusResponse = await callBridge(
    "get_plant_parcel_source_statuses",
    params ?? {},
  );
  if (payload.error) throw new Error(payload.error);
  return {
    mode: "desktop",
    statuses: payload.source_statuses ?? [],
    response: payload,
  };
}

export async function fetchPlantParcelCatalog(
  params?: PlantParcelCatalogParams,
): Promise<PlantParcelCatalogResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", records: [], response: null, reason: BROWSER_REASON };
  }
  const payload: PlantParcelCatalogResponse = await callBridge(
    "get_plant_parcel_catalog",
    params ?? {},
  );
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", records: payload.records ?? [], response: payload };
}

export async function fetchPlantParcelDetail(
  params: PlantParcelDetailParams,
): Promise<PlantParcelDetailResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", detail: null, reason: BROWSER_REASON };
  }
  const payload: PlantParcelDetailResponse = await callBridge(
    "get_plant_parcel_detail",
    params,
  );
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", detail: payload };
}

export async function triggerPlantParcelRefresh(
  params: PlantParcelRefreshParams,
): Promise<PlantParcelRefreshResult_> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const payload: PlantParcelRefreshResult = await callBridge(
    "refresh_plant_parcel_source",
    { triggered_by: "user", ...params },
  );
  return { mode: "desktop", result: payload };
}

export async function selectPlantParcelImportFile(
  sourceId: string,
): Promise<PlantParcelFilePickerResult_> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const payload: PlantParcelFilePickerResult = await callBridge(
    "select_plant_parcel_import_file",
    { source_id: sourceId },
  );
  return { mode: "desktop", result: payload };
}

export async function importPlantParcelManualFile(
  params: PlantParcelManualImportParams,
): Promise<PlantParcelManualImportResult_> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const payload: PlantParcelManualImportResult = await callBridge(
    "import_plant_parcel_source_file",
    { triggered_by: "user", ...params },
  );
  return { mode: "desktop", result: payload };
}

export async function fetchPlantParcelChartData(
  params: PlantParcelChartDataParams,
): Promise<PlantParcelChartDataResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", data: null, reason: BROWSER_REASON };
  }
  const payload: PlantParcelChartDataResponse = await callBridge(
    "get_plant_parcel_chart_data",
    params,
  );
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", data: payload };
}

export async function fetchEnergyMartStatus(): Promise<EnergyMartStatusResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", status: null, reason: BROWSER_REASON };
  }
  const payload: EnergyMartStatusResponse = await callBridge("get_energy_mart_status", {});
  if (payload.error) throw new Error(payload.error);
  return { mode: "desktop", status: payload };
}

export async function startEnergyMartRebuild(
  params: StartEnergyMartRebuildParams,
): Promise<EnergyMartRebuildResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", result: null, reason: BROWSER_REASON };
  }
  const payload: EnergyMartRebuildState = await callBridge("start_energy_mart_rebuild", params);
  if (payload.status === "error" || payload.status === "blocked") {
    throw new Error(payload.error || "Energy mart rebuild could not start.");
  }
  return { mode: "desktop", result: payload };
}
