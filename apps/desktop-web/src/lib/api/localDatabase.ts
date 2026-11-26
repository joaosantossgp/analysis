import { useSyncExternalStore } from "react";
import { useQuery, type QueryClient } from "@tanstack/react-query";

import { callBridge, getBridgeMode } from "../bridge/adapter";
import { retryFailedCompanies as retryCompanies, startDataUpdate } from "./updateBase";
import type { LocalDatabaseState } from "../bridge/types.localDatabase";

export const LOCAL_DATABASE_STATE_KEY = ["local-database-state"] as const;

/** Local reads only: the bridge never starts network work for this call. */
export async function fetchLocalDatabaseState(): Promise<LocalDatabaseState | null> {
  if (getBridgeMode() === "browser") return null;
  return callBridge("get_local_database_state", {});
}

export function useLocalDatabaseState() {
  return useQuery({
    queryKey: LOCAL_DATABASE_STATE_KEY,
    queryFn: fetchLocalDatabaseState,
    // Poll fast only while a data update runs.
    refetchInterval: (query) => (query.state.data?.run ? 3_000 : 30_000),
  });
}

/**
 * Refetches open company lists when the running data update makes progress
 * and once when it ends, so rows follow the run (#577). Returns the unsubscribe.
 */
export function refreshCompaniesOnRunProgress(client: QueryClient): () => void {
  let last: string | null = null;
  return client.getQueryCache().subscribe((event) => {
    if (event.type !== "updated" || event.query.queryKey[0] !== LOCAL_DATABASE_STATE_KEY[0]) return;
    const run = (event.query.state.data as LocalDatabaseState | null | undefined)?.run;
    // files_done: the company list is written while the CVM files download.
    const progress = run ? `${run.phase}:${run.files_done}:${run.processed}` : null;
    if (progress === last) return;
    last = progress;
    void client.invalidateQueries({ queryKey: ["companies"] });
  });
}

function subscribeOnline(callback: () => void) {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);
  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
}

/** Browser connectivity flag; no request is made to find it out. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribeOnline,
    () => navigator.onLine,
    () => true,
  );
}

/** Retries failed companies: all of them, or only `companyIds`. Never resets Stale. */
export async function retryFailedCompanies(companyIds?: number[]): Promise<void> {
  if (companyIds?.length) {
    await retryCompanies(companyIds);
    return;
  }
  await startDataUpdate({ mode: "failed" });
}
