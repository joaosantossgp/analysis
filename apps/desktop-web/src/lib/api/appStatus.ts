import { callBridge, getBridgeMode } from "../bridge/adapter";
import type {
  AppStatusPayload,
  LocalPathInfo,
  OpenStatusPathResult,
  UpdateProgressStatus,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser preview: pywebview bridge is unavailable. Launch with python -m desktop.app --vite or CVMAnalytics.exe --vite for local diagnostics.";

export type AppStatusResult =
  | { mode: "desktop"; status: AppStatusPayload }
  | { mode: "browser"; status: AppStatusPayload; reason: string };

export type StatusPathKind = "data" | "database" | "output" | "logs" | "cache";

export async function fetchAppStatus(params?: {
  forceUpdateCheck?: boolean;
}): Promise<AppStatusResult> {
  if (getBridgeMode() === "browser") {
    return {
      mode: "browser",
      status: browserFallbackStatus(),
      reason: BROWSER_REASON,
    };
  }
  const status = await callBridge("get_app_status", {
    force_update_check: params?.forceUpdateCheck ?? false,
  });
  return { mode: "desktop", status };
}

export async function openStatusPath(
  kind: StatusPathKind,
): Promise<OpenStatusPathResult> {
  if (getBridgeMode() === "browser") {
    throw new Error("Opening local folders is available only in Vite desktop mode.");
  }
  const response = await callBridge("open_status_path", { kind });
  if (!response.ok) {
    throw new Error(response.error || `Could not open ${kind} path.`);
  }
  return response;
}

export async function triggerCheckUpdate(): Promise<{ available: boolean; version?: string; zip_url?: string; error?: string }> {
  if (getBridgeMode() === "browser") {
    return { available: false, error: "Unavailable in browser preview mode." };
  }
  return callBridge("check_update", {});
}

export async function triggerApplyUpdate(): Promise<{ started: boolean; error?: string }> {
  if (getBridgeMode() === "browser") {
    return { started: false, error: "Unavailable in browser preview mode." };
  }
  return callBridge("apply_update", {});
}

export async function fetchUpdateProgress(): Promise<UpdateProgressStatus> {
  if (getBridgeMode() === "browser") {
    return { status: "idle", percent: 0, error: null };
  }
  return callBridge("get_update_progress", {});
}

export async function triggerSnoozeUpdate(): Promise<{ ok: boolean; error?: string }> {
  if (getBridgeMode() === "browser") {
    return { ok: false, error: "Unavailable in browser preview mode." };
  }
  return callBridge("snooze_update", {});
}

function browserFallbackStatus(): AppStatusPayload {
  const path = (kind: StatusPathKind, label: string): LocalPathInfo => ({
    kind,
    path: label,
    exists: false,
    is_file: false,
    is_dir: false,
  });

  return {
    runtime: {
      version: "browser-preview",
      runtime_mode: "unknown",
      bridge_status: "unknown",
      frozen: false,
      desktop_shell: null,
      local_first: true,
    },
    paths: {
      data: path("data", "Unavailable in browser preview"),
      database: path("database", "Unavailable in browser preview"),
      output: path("output", "Unavailable in browser preview"),
      logs: path("logs", "Unavailable in browser preview"),
      cache: path("cache", "Unavailable in browser preview"),
    },
    database: null,
    update: {
      current_version: null,
      latest_version: null,
      update_available: false,
      status: "unknown",
      error: "GitHub release checks require the desktop bridge.",
      apply_supported: false,
    },
    diagnostics: {
      ok: false,
      dotnet_status: null,
      webview2_version: null,
      pythonnet_status: null,
      sqlite_status: null,
      errors: [],
      warnings: ["Desktop runtime diagnostics require pywebview bridge access."],
    },
    recent: [],
  };
}
