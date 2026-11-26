import { callBridge, getBridgeMode } from "../bridge/adapter";

const BROWSER_REASON = "pywebview bridge unavailable (browser mode).";

export type DevSimulateMode = "success" | "partial" | "fail" | "slow";

export type RawState = {
  app_settings: Array<{ key: string; value: string | null; updated_at: string | null }>;
  refresh_jobs: Array<Record<string, unknown>>;
  error?: string;
};

function requireDesktop(label: string): void {
  if (getBridgeMode() === "browser") {
    throw new Error(`${label}: ${BROWSER_REASON}`);
  }
}

export async function devResetUniverse(): Promise<void> {
  requireDesktop("dev_reset_universe");
  const r = await callBridge("dev_reset_universe", {});
  if (r.error) throw new Error(r.error);
}

export async function devResetJobs(): Promise<void> {
  requireDesktop("dev_reset_jobs");
  const r = await callBridge("dev_reset_jobs", {});
  if (r.error) throw new Error(r.error);
}

export async function devSimulateRefresh(mode: DevSimulateMode): Promise<string | undefined> {
  requireDesktop("dev_simulate_refresh");
  const r = await callBridge("dev_simulate_refresh", { mode });
  if (r.error) throw new Error(r.error);
  return r.job_id;
}

export async function devStartSmallSetup(count = 5): Promise<void> {
  requireDesktop("dev_start_small_setup");
  const r = await callBridge("dev_start_small_setup", { count });
  if (r.status === "error") throw new Error(r.message ?? "dev_start_small_setup failed");
}

export async function devGetRawState(): Promise<RawState> {
  requireDesktop("dev_get_raw_state");
  return (await callBridge("dev_get_raw_state", {})) as RawState;
}
