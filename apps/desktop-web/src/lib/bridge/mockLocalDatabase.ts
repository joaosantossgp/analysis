import type { LocalDatabaseState, LocalDatabaseStateKey } from "./types.localDatabase";

/**
 * Mock-bridge scenarios for the local database state. Pick one in dev with
 * `localStorage.setItem("cvm_mock_local_database", "empty")` and reload.
 * Simulated values only; never shown outside mock mode.
 */
export const MOCK_LOCAL_DATABASE_SCENARIO_KEY = "cvm_mock_local_database";

const BASE: LocalDatabaseState = {
  state: "current",
  has_statements: true,
  last_full_update_at: "2026-11-20T11:00:00+00:00",
  stale_reason: null,
  run: null,
  last_run: {
    job_id: "mock-full",
    scope: "data_update",
    state: "success",
    finished_at: "2026-11-20T11:00:00+00:00",
    queued: 438,
    processed: 438,
    failures: 0,
    error: null,
  },
  failures: [],
  generated_at: "2026-11-25T12:00:00+00:00",
};

const RUN = {
  job_id: "mock-run",
  scope: "data_update",
  failures: 0,
  started_at: "2026-11-25T11:40:00+00:00",
};

export const MOCK_LOCAL_DATABASE_STATES: Record<Exclude<LocalDatabaseStateKey, "unknown">, LocalDatabaseState> = {
  empty: { ...BASE, state: "empty", has_statements: false, last_full_update_at: null, last_run: null },
  files: {
    ...BASE,
    state: "files",
    has_statements: false,
    last_full_update_at: null,
    last_run: null,
    run: { ...RUN, phase: "files", files_done: 6, files_total: 10, processed: 0, queued: 438, eta_seconds: null },
  },
  updating: {
    ...BASE,
    state: "updating",
    run: { ...RUN, phase: "companies", files_done: null, files_total: null, processed: 162, queued: 438, eta_seconds: 1440 },
  },
  current: BASE,
  stale: {
    ...BASE,
    state: "stale",
    last_full_update_at: "2026-08-02T10:00:00+00:00",
    stale_reason: { label: "ITR 3Q26", due: "2026-11-14" },
  },
  partial: {
    ...BASE,
    state: "partial",
    last_run: { ...BASE.last_run!, state: "partial", failures: 3 },
    failures: [
      { cd_cvm: 4170, company_name: "OI SA", error: "DFP 2024 rows rejected by validation" },
      { cd_cvm: 5258, company_name: "XP INC", error: "No ITR filed for 3Q26 yet" },
      { cd_cvm: 99001, company_name: "EMPRESA DEMO LTDA", error: "Statement parse error (BPP 2023)" },
    ],
  },
  failed: {
    ...BASE,
    state: "failed",
    has_statements: false,
    last_full_update_at: null,
    last_run: { ...BASE.last_run!, state: "error", processed: 0, error: "The CVM server did not respond." },
  },
};

export function mockLocalDatabaseState(): LocalDatabaseState {
  let key: string | null = null;
  try {
    key = globalThis.localStorage?.getItem(MOCK_LOCAL_DATABASE_SCENARIO_KEY) ?? null;
  } catch {
    key = null;
  }
  return MOCK_LOCAL_DATABASE_STATES[(key ?? "current") as keyof typeof MOCK_LOCAL_DATABASE_STATES] ?? BASE;
}
