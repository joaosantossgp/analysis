import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  BaseHealthSnapshot,
  CancelRefreshResponse,
  RefreshDispatchResponse,
  RefreshJobListResponse,
  RefreshJobStatus,
  RefreshMode,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser mode - pywebview bridge is unavailable. Launch with python -m desktop.app --vite or the packaged exe.";

export type BaseHealthResult =
  | { mode: "desktop"; snapshot: BaseHealthSnapshot }
  | { mode: "browser"; snapshot: null; reason: string };

export type RefreshJobsResult =
  | { mode: "desktop"; items: RefreshJobStatus[] }
  | { mode: "browser"; items: RefreshJobStatus[]; reason: string };

export type RefreshJobResult =
  | { mode: "desktop"; job: RefreshJobStatus }
  | { mode: "browser"; job: null; reason: string };

export type StartRefreshParams = {
  mode: RefreshMode;
  limit: number;
  startYear: number;
  endYear: number;
  cdCvm?: number | null;
};

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

export function refreshProgress(job: RefreshJobStatus | null | undefined): number {
  if (!job) return 0;
  if (job.state === "success") return 100;
  const queued = Math.max(1, Number(job.queued || 0));
  const processedPct = Math.round((Number(job.processed || 0) / queued) * 100);
  const stageFloor = stageProgressFloor(job.stage);
  return Math.max(0, Math.min(99, Math.max(processedPct, stageFloor)));
}

function stageProgressFloor(stage: string | null | undefined): number {
  switch (stage) {
    case "planning":
      return 8;
    case "download_extract":
      return 35;
    case "process_data":
      return 58;
    case "persist_reports":
      return 82;
    case "finalizing":
      return 95;
    default:
      return 0;
  }
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
    limit: Math.max(1, Math.min(100, Math.trunc(params.limit))),
    start_year: params.startYear,
    end_year: params.endYear,
    ...(params.cdCvm != null ? { cd_cvm: params.cdCvm } : {}),
  });
  if (response.error) {
    throw new Error(response.error);
  }
  if (response.status === "error") {
    throw new Error(response.message || response.status_reason_message || "Refresh failed to start.");
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
