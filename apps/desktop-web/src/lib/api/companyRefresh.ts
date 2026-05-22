import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  CompanyRefreshStatus,
  CompanyRefreshStatusListResponse,
  RefreshDispatchResponse,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser mode - pywebview bridge is unavailable. Launch with python -m desktop.app --vite or the packaged exe.";

export type CompanyRefreshStatusResult =
  | { mode: "desktop"; status: CompanyRefreshStatus | null }
  | { mode: "browser"; status: null; reason: string };

export async function fetchCompanyRefreshStatus(
  cdCvm: number,
): Promise<CompanyRefreshStatusResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", status: null, reason: BROWSER_REASON };
  }
  const response = (await callBridge("get_refresh_status", {
    cd_cvm: cdCvm,
  })) as CompanyRefreshStatusListResponse;
  if (response.error) {
    throw new Error(response.error);
  }
  return { mode: "desktop", status: response.items?.[0] ?? null };
}

export async function requestCompanyRefresh(
  cdCvm: number,
): Promise<RefreshDispatchResponse> {
  if (getBridgeMode() === "browser") {
    throw new Error(BROWSER_REASON);
  }
  const response = await callBridge("request_refresh", { cd_cvm: cdCvm });
  if (response.error) {
    throw new Error(response.error);
  }
  if (response.status === "error") {
    throw new Error(
      response.message ||
        response.status_reason_message ||
        "Company refresh failed to start.",
    );
  }
  return response;
}

export function isActiveCompanyRefresh(
  status: CompanyRefreshStatus | null | undefined,
): boolean {
  const state = normalizedTrackingState(status);
  return state === "queued" || state === "running";
}

export function normalizedTrackingState(
  status: CompanyRefreshStatus | null | undefined,
): string {
  return String(status?.tracking_state ?? status?.last_status ?? "idle")
    .trim()
    .toLowerCase();
}

export function companyRefreshProgress(
  status: CompanyRefreshStatus | null | undefined,
): number | null {
  if (!status) return null;
  if (typeof status.estimated_progress_pct === "number") {
    return clampPercent(status.estimated_progress_pct);
  }
  if (
    typeof status.progress_current === "number" &&
    typeof status.progress_total === "number" &&
    status.progress_total > 0
  ) {
    return clampPercent((status.progress_current / status.progress_total) * 100);
  }
  return null;
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}
