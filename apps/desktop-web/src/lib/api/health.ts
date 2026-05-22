/**
 * Health API facade.
 *
 * Components consume this, not the bridge adapter directly. The Phase 2
 * migration to TanStack Query will wrap these facades in queryFn closures
 * without component-side churn.
 */
import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type { HealthPayload } from "../bridge/types";

export type HealthResult =
  | { mode: "desktop"; payload: HealthPayload }
  | { mode: "browser"; payload: null; reason: string };

export async function fetchHealth(): Promise<HealthResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return {
      mode: "browser",
      payload: null,
      reason:
        "Running in browser mode — pywebview bridge is unavailable. Launch via `python -m desktop.app --dev` for Vite dev shell testing, or run the packaged exe.",
    };
  }
  const payload = await callBridge("get_health", {});
  return { mode: "desktop", payload };
}
