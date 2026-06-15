import { callBridge, getBridgeMode } from "../bridge/adapter";
import type { SettingsHealthSummary } from "../bridge/types";

const BROWSER_REASON =
  "Running in browser preview: pywebview bridge is unavailable. Launch through the desktop shell to inspect local data health.";

export type SettingsHealthResult =
  | { mode: "desktop" | "mock"; summary: SettingsHealthSummary }
  | { mode: "browser"; summary: SettingsHealthSummary; reason: string };

export async function fetchSettingsHealthSummary(): Promise<SettingsHealthResult> {
  const mode = getBridgeMode();
  if (mode === "browser") {
    return {
      mode: "browser",
      reason: BROWSER_REASON,
      summary: browserFallbackSummary(),
    };
  }
  const summary = await callBridge("get_settings_health_summary", {});
  return { mode, summary };
}

function browserFallbackSummary(): SettingsHealthSummary {
  return {
    generated_at: new Date().toISOString(),
    overall_status: "unavailable",
    summary: {
      title: "Desktop bridge unavailable",
      message: BROWSER_REASON,
      initial_bridge_calls: 0,
      full_table_scans: false,
      deferred_detail_contracts: [],
    },
    segments: [],
    active_jobs: [],
    warnings: [
      {
        segment_id: "runtime",
        severity: "warning",
        message: BROWSER_REASON,
        action_route: "/settings/diagnostics",
      },
    ],
    errors: [],
    storage: {},
    runtime: {
      version: "browser-preview",
      runtime_mode: "unknown",
      bridge_status: "unknown",
      frozen: false,
      desktop_shell: null,
      local_first: true,
      write_mode: "read-only",
    },
    provenance: [
      {
        metric: "browser_fallback",
        source: "apps/desktop-web/src/lib/api/settingsHealth.ts",
        meaning: "Explicit browser-only state when pywebview bridge is unavailable.",
        cost: "none",
        cache_policy: "static fallback",
        failure_behavior: "local health is marked unavailable",
      },
    ],
  };
}
