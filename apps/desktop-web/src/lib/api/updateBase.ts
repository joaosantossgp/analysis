import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  BaseHealthSnapshot,
  CancelRefreshResponse,
  CompanyUniversePreset,
  DatabaseDiagnostics,
  DataUpdateSettings,
  DataUpdateStartResponse,
  MarketCapStatus,
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

/** Only `mode` matters now: the backend fixes the scope (ADR 0010). */
export type StartDataUpdateParams = {
  mode?: RefreshMode;
  universePreset?: CompanyUniversePreset;
  batchSize?: DataUpdateSettings["batch_size"];
  retryFailed?: boolean;
  recomputeCoverage?: boolean;
  startYear?: number;
  endYear?: number;
};

export type ResetLocalDatabaseParams = {
  action: "recreate_local";
  confirm: "REBUILD" | string;
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

export function defaultRefreshWindow(referenceDate = new Date()): {
  startYear: number;
  endYear: number;
} {
  const endYear = referenceDate.getFullYear() - 1;
  return { startYear: endYear - 1, endYear };
}

export function isActiveRefreshJob(job: RefreshJobStatus | null | undefined): boolean {
  return job != null && (job.state === "queued" || job.state === "running");
}

export function isTerminalRefreshJob(job: RefreshJobStatus | null | undefined): boolean {
  return (
    job != null &&
    (job.state === "success" ||
      job.state === "partial" ||
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

export async function fetchDatabaseDiagnostics(params?: { summaryOnly?: boolean }): Promise<DatabaseDiagnosticsResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", diagnostics: null, reason: BROWSER_REASON };
  }
  const diagnostics = (await callBridge(
    "get_database_diagnostics",
    { summary_only: params?.summaryOnly ?? false },
  )) as DatabaseDiagnostics;
  return { mode: "desktop", diagnostics };
}

export function useWorkspaceStatus(bridgeReady = true) {
  const defaults = useMemo(() => defaultRefreshWindow(), []);

  const jobsQuery = useQuery({
    queryKey: ["refresh-jobs"],
    queryFn: fetchRefreshJobs,
    enabled: bridgeReady,
    refetchInterval: 15_000,
  });
  const jobs = jobsQuery.data?.mode === "desktop" ? jobsQuery.data.items : [];
  const activeJob = jobs.find(isActiveRefreshJob) ?? null;
  const isRunning = Boolean(activeJob);

  const healthQuery = useQuery({
    queryKey: ["base-health", defaults.startYear, defaults.endYear],
    queryFn: () =>
      fetchBaseHealth({
        startYear: defaults.startYear,
        endYear: defaults.endYear,
        forceRefresh: false,
      }),
    enabled: bridgeReady,
    // No polling: each poll during a run rebuilds the snapshot while rows are written.
    // The shell's DataIndicator invalidates this key when the run ends.
  });
  const health = healthQuery.data?.mode === "desktop" ? healthQuery.data.snapshot : null;

  const diagQuery = useQuery({
    queryKey: ["db-diagnostics", { summaryOnly: true }],
    queryFn: () => fetchDatabaseDiagnostics({ summaryOnly: true }),
    enabled: bridgeReady,
  });
  const diagnostics = diagQuery.data?.mode === "desktop" ? diagQuery.data.diagnostics : null;
  const browserReason = diagQuery.data?.mode === "browser" ? diagQuery.data.reason : null;
  const mode = diagQuery.data?.mode || "offline";

  return {
    defaults,
    activeJob,
    isRunning,
    health,
    diagnostics,
    browserReason,
    mode,
    isLoading: jobsQuery.isLoading || healthQuery.isLoading || diagQuery.isLoading,
  };
}

/** Explicit market-cap refresh from Yahoo Finance (unofficial); writes the local snapshot. */
export async function fetchMarketCapSnapshot(): Promise<MarketCapStatus> {
  if (getBridgeMode() === "browser") throw new Error("Fetching market caps needs the desktop bridge.");
  const result = await callBridge("fetch_market_cap_snapshot", {});
  if (!result.ok || !result.status) throw new Error(result.error ?? "Could not fetch market caps.");
  return result.status;
}

/** Last fetched market-cap snapshot; a local read, never a network call. */
export async function fetchMarketCapStatus(): Promise<MarketCapStatus | null> {
  if (getBridgeMode() === "browser") return null;
  return callBridge("get_market_cap_status", {});
}

/** Retry failed companies: the shared retry contract used by every surface. */
export async function retryFailedCompanies(companyIds: number[]): Promise<RefreshDispatchResponse> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const response = await callBridge("request_refresh", {
    mode: "failed",
    scope: "retry",
    company_ids: companyIds,
  });
  if (response.error) {
    throw new Error(response.error);
  }
  if (response.status === "error") {
    throw new Error(response.message || response.status_reason_message || "Retry failed to start.");
  }
  return response;
}
