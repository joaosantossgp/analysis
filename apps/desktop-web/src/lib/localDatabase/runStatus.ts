import type { LocalDatabaseState } from "../bridge/types.localDatabase";

export type RunRowStatus = "downloading" | "queued" | "failed";

/** Company ids of the running data update, for O(1) row lookups. */
export function runCompanyIds(state: LocalDatabaseState | null | undefined): Set<number> {
  return new Set(state?.run?.company_ids ?? []);
}

/**
 * Directory row status from the local database state contract only: rows of
 * the current run, or failures of the last run. Never inferred for others.
 */
export function runRowStatus(
  state: LocalDatabaseState | null | undefined,
  runIds: Set<number>,
  cdCvm: number,
  hasFinancialData: boolean,
): RunRowStatus | null {
  if (!state) return null;
  if (state.run && runIds.has(cdCvm)) {
    if (state.run.current_cvm === cdCvm) return "downloading";
    return hasFinancialData ? null : "queued";
  }
  if (state.state === "partial" && state.failures.some((f) => f.cd_cvm === cdCvm)) return "failed";
  return null;
}

/** One-line phase status shown above the directory while a run is active. */
export function runStatusLine(state: LocalDatabaseState | null | undefined): string | null {
  const run = state?.run;
  if (!run) return null;
  if (run.phase === "files" && run.files_total) {
    return `Data update running · Step 1 of 2 · downloading CVM files (${run.files_done ?? 0} of ${run.files_total}) · statements start arriving after this step`;
  }
  if (run.phase === "starting") return "Data update running · getting the CVM company list";
  return `Data update running · ${run.processed} of ${run.queued} companies processed · rows update as companies finish`;
}
