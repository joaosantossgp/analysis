import { callBridge, getBridgeMode } from "../bridge/adapter";
import type { B3RefreshRun, B3RefreshStatus } from "../bridge/types";

export async function fetchB3ClassificationStatus(): Promise<B3RefreshStatus | null> {
  if (getBridgeMode() === "browser") return null;
  const result = await callBridge("get_b3_classification_status", {});
  if (!result.ok) throw new Error(result.error ?? "Could not read the B3 sector status.");
  return result;
}

export async function refreshB3Classification(): Promise<B3RefreshRun> {
  if (getBridgeMode() === "browser") throw new Error("Refreshing B3 sectors needs the desktop bridge.");
  const result = await callBridge("refresh_b3_classification", {});
  if (!result.ok) throw new Error(result.error ?? "B3 sector refresh failed.");
  return result;
}

/** One-line summary of the last refresh, keeping failures visible. */
export function describeB3Refresh(status: B3RefreshStatus | null | undefined): string {
  if (!status?.last_run) return "Never refreshed. Company pages show no B3 sector until you refresh.";
  const run = status.last_run;
  const parts = [
    `Last refresh ${run.finished_at.slice(0, 16).replace("T", " ")} UTC`,
    `${run.succeeded} updated`,
    `${run.not_listed} not listed on B3`,
    `${run.failed} failed`,
  ];
  if (status.stale) parts.push(`older than ${status.stale_after_days} days`);
  return parts.join(" · ");
}
