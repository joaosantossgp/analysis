import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  BaseHealthSnapshot,
  CancelRefreshResponse,
  CompanyUniversePreset,
  CompanyUniverseSelection,
  DatabaseDiagnostics,
  DataUpdateSettings,
  DataUpdateStartResponse,
  RefreshDispatchResponse,
  RefreshJobListResponse,
  RefreshJobStatus,
  RefreshMode,
  ResetLocalDatabaseResponse,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser mode - pywebview bridge is unavailable. Launch with python -m desktop.app --vite or the packaged exe.";

export type BaseHealthResult =
  | { mode: "desktop"; snapshot: BaseHealthSnapshot }
  | { mode: "browser"; snapshot: null; reason: string };

export type DatabaseDiagnosticsResult =
  | { mode: "desktop"; diagnostics: DatabaseDiagnostics }
  | { mode: "browser"; diagnostics: null; reason: string };

export type RefreshJobsResult =
  | { mode: "desktop"; items: RefreshJobStatus[] }
  | { mode: "browser"; items: RefreshJobStatus[]; reason: string };

export type RefreshJobResult =
  | { mode: "desktop"; job: RefreshJobStatus }
  | { mode: "browser"; job: null; reason: string };

export type DataUpdateSettingsResult =
  | { mode: "desktop"; settings: DataUpdateSettings }
  | { mode: "browser"; settings: DataUpdateSettings; reason: string };

export type CompanyUniverseSelectionResult =
  | { mode: "desktop"; selection: CompanyUniverseSelection }
  | { mode: "browser"; selection: null; reason: string };

export type StartRefreshParams = {
  mode: RefreshMode;
  limit: number;
  startYear: number;
  endYear: number;
  cdCvm?: number | null;
  companyIds?: number[];
};

export type StartDataUpdateParams = {
  mode?: RefreshMode;
  universePreset: CompanyUniversePreset;
  batchSize: DataUpdateSettings["batch_size"];
  retryFailed: boolean;
  recomputeCoverage: boolean;
  startYear: number;
  endYear: number;
};

export type ResetLocalDatabaseParams = {
  action: "restart_current" | "recreate_local";
  confirm: "RESET" | "REBUILD" | string;
};

/**
 * Raised when an update cannot start because of a configuration gap (e.g. the
 * Top N market-cap universe has no ranking source). This is a "blocked" state,
 * not a runtime failure — the UI presents it as a configuration notice and no
 * job is ever dispatched.
 */
export class DataUpdateBlockedError extends Error {
  readonly reasonCode: string;
  constructor(message: string, reasonCode: string) {
    super(message);
    this.name = "DataUpdateBlockedError";
    this.reasonCode = reasonCode;
  }
}

export const BATCH_SIZE_OPTIONS: DataUpdateSettings["batch_size"][] = [
  50,
  100,
  200,
  500,
];

export const REFRESH_MODES: Array<{
  value: RefreshMode;
  label: string;
  description: string;
}> = [
  {
    value: "missing",
    label: "Missing data",
    description: "Fill gaps in the selected years. Best first-run choice.",
  },
  {
    value: "failed",
    label: "Failed only",
    description: "Retry companies with previous refresh errors.",
  },
  {
    value: "outdated",
    label: "Outdated",
    description: "Refresh companies with stale local coverage.",
  },
  {
    value: "full",
    label: "Full refresh",
    description: "Reprocess selected companies even if data exists.",
  },
];

export function defaultRefreshWindow(referenceDate = new Date()): {
  startYear: number;
  endYear: number;
} {
  const endYear = referenceDate.getFullYear() - 1;
  return { startYear: endYear - 1, endYear };
}

export const CVM_MIN_YEAR = 2010;

export function isActiveRefreshJob(job: RefreshJobStatus | null | undefined): boolean {
  return job != null && (job.state === "queued" || job.state === "running");
}

export function isTerminalRefreshJob(job: RefreshJobStatus | null | undefined): boolean {
  return (
    job != null &&
    (job.state === "success" ||
      job.state === "error" ||
      job.state === "cancelled" ||
      job.state === "interrupted")
  );
}

/**
 * Continuous, phase-aware progress for a refresh job.
 *
 * Each stage owns a contiguous sub-range of overall progress and the actual
 * processed/queued fraction interpolates within that sub-range. Adjacent
 * stages share boundary values (e.g. process_data ends at 80, persist_reports
 * starts at 80) so transitioning between stages NEVER causes a discrete jump
 * in the rendered percentage.
 *
 * If `queued` is unknown (still planning), progress holds at the floor of the
 * current stage rather than faking precision.
 */
export function refreshProgress(job: RefreshJobStatus | null | undefined): number {
  if (!job) return 0;
  if (job.state === "success") return 100;

  const queued = Number(job.queued || 0);
  const processed = Number(job.processed || 0);
  const innerFrac = queued > 0 ? Math.min(1, Math.max(0, processed / queued)) : 0;

  const [lo, hi] = stageRange(job.stage);
  if (hi === 0) {
    // Unknown / no stage yet — fall back to processed/queued ratio if known.
    if (queued <= 0) return 0;
    return clampProgress(Math.round((processed / queued) * 100));
  }
  return clampProgress(Math.round(lo + innerFrac * (hi - lo)));
}

function stageRange(stage: string | null | undefined): [number, number] {
  switch (stage) {
    case "market_cap":
      return [0, 5];
    case "planning":
      return [5, 10];
    case "download_extract":
      return [10, 55];
    case "process_data":
      return [55, 80];
    case "persist_reports":
      return [80, 95];
    case "finalizing":
      return [95, 99];
    default:
      return [0, 0];
  }
}

function clampProgress(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(99, value));
}

export async function fetchBaseHealth(params: {
  startYear: number;
  endYear: number;
  forceRefresh?: boolean;
}): Promise<BaseHealthResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", snapshot: null, reason: BROWSER_REASON };
  }
  const snapshot = await callBridge("get_base_health", {
    start_year: params.startYear,
    end_year: params.endYear,
    force_refresh: params.forceRefresh ?? false,
  });
  if (snapshot.error) {
    throw new Error(snapshot.error);
  }
  return { mode: "desktop", snapshot };
}

export async function fetchRefreshJobs(): Promise<RefreshJobsResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", items: [], reason: BROWSER_REASON };
  }
  const response = (await callBridge("get_refresh_status", {})) as RefreshJobListResponse;
  if (response.error) {
    throw new Error(response.error);
  }
  return { mode: "desktop", items: response.items ?? [] };
}

export async function fetchRefreshJob(jobId: string): Promise<RefreshJobResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", job: null, reason: BROWSER_REASON };
  }
  const job = (await callBridge("get_refresh_status", { job_id: jobId })) as RefreshJobStatus;
  if (job.error && job.state === "error") {
    return { mode: "desktop", job };
  }
  return { mode: "desktop", job };
}

export async function startBaseRefresh(
  params: StartRefreshParams,
): Promise<RefreshDispatchResponse> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const response = await callBridge("request_refresh", {
    mode: params.mode,
    limit: Math.max(1, Math.min(10_000, Math.trunc(params.limit))),
    start_year: params.startYear,
    end_year: params.endYear,
    ...(params.cdCvm != null ? { cd_cvm: params.cdCvm } : {}),
    ...(params.companyIds?.length ? { company_ids: params.companyIds } : {}),
  });
  if (response.error) {
    throw new Error(response.error);
  }
  if (response.status === "error") {
    throw new Error(response.message || response.status_reason_message || "Refresh failed to start.");
  }
  return response;
}

export async function fetchDataUpdateSettings(): Promise<DataUpdateSettingsResult> {
  const currentYear = new Date().getFullYear();
  const fallback: DataUpdateSettings = {
    universe_preset: "top_200",
    batch_size: 100,
    retry_failed: true,
    recompute_coverage: true,
    start_year: currentYear - 4,
    end_year: currentYear,
  };
  if (getBridgeMode() === "browser") {
    return { mode: "browser", settings: fallback, reason: BROWSER_REASON };
  }
  const settings = (await callBridge("get_data_update_settings", {})) as DataUpdateSettings;
  if (settings.error) {
    throw new Error(settings.error);
  }
  return { mode: "desktop", settings };
}

export async function saveDataUpdateSettings(
  settings: DataUpdateSettings,
): Promise<DataUpdateSettings> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const response = (await callBridge("save_data_update_settings", settings)) as DataUpdateSettings;
  if (response.error) {
    throw new Error(response.error);
  }
  return response;
}

export async function fetchCompanyUniverseSelection(
  preset: CompanyUniversePreset,
): Promise<CompanyUniverseSelectionResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", selection: null, reason: BROWSER_REASON };
  }
  const selection = (await callBridge("get_company_universe_selection", {
    preset,
  })) as CompanyUniverseSelection & { error?: string };
  if (selection.error) {
    throw new Error(selection.error);
  }
  return { mode: "desktop", selection };
}

export async function startDataUpdate(
  params: StartDataUpdateParams,
): Promise<DataUpdateStartResponse> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const response = (await callBridge("start_data_update", {
    mode: params.mode ?? "missing",
    universe_preset: params.universePreset,
    batch_size: params.batchSize,
    retry_failed: params.retryFailed,
    recompute_coverage: params.recomputeCoverage,
    start_year: params.startYear,
    end_year: params.endYear,
  })) as DataUpdateStartResponse;
  if (response.status === "blocked") {
    throw new DataUpdateBlockedError(
      response.message ||
        response.status_reason_message ||
        response.error ||
        "Update is blocked by a configuration gap.",
      response.status_reason_code || "blocked",
    );
  }
  if (response.error) {
    throw new Error(response.error);
  }
  if (response.status === "error") {
    throw new Error(response.message || response.status_reason_message || "Failed to start update.");
  }
  return response;
}

export async function resetLocalDatabase(
  params: ResetLocalDatabaseParams,
): Promise<ResetLocalDatabaseResponse> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const response = (await callBridge("reset_local_database", params)) as ResetLocalDatabaseResponse;
  if (!response.ok) {
    throw new Error(response.error || "Failed to reset local database.");
  }
  return response;
}

export async function cancelRefresh(jobId: string): Promise<CancelRefreshResponse> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const response = await callBridge("cancel_refresh", { job_id: jobId });
  if (response.error) {
    throw new Error(response.error);
  }
  return response;
}

export async function fetchDatabaseDiagnostics(): Promise<DatabaseDiagnosticsResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", diagnostics: null, reason: BROWSER_REASON };
  }
  const diagnostics = (await callBridge(
    "get_database_diagnostics",
    {},
  )) as DatabaseDiagnostics;
  return { mode: "desktop", diagnostics };
}
