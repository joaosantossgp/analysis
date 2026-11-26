/** Local database state contract (bridge `get_local_database_state`). */

export type LocalDatabaseStateKey =
  | "empty"
  | "files"
  | "updating"
  | "current"
  | "stale"
  | "partial"
  | "failed"
  /** The bridge could not read local files; `error` says why. */
  | "unknown";

export type LocalDatabaseRun = {
  job_id: string | null;
  scope: string | null;
  phase: "starting" | "files" | "companies" | "finalizing";
  files_done: number | null;
  files_total: number | null;
  processed: number;
  queued: number;
  failures: number;
  started_at: string | null;
  eta_seconds: number | null;
};

export type LocalDatabaseLastRun = {
  job_id: string | null;
  scope: string | null;
  state: string | null;
  finished_at: string | null;
  queued: number;
  processed: number;
  failures: number;
  error: string | null;
};

export type LocalDatabaseFailure = {
  cd_cvm: number;
  company_name: string | null;
  error: string;
};

export type LocalDatabaseState = {
  state: LocalDatabaseStateKey;
  has_statements: boolean;
  last_full_update_at: string | null;
  /** label/due are null when no full data update was ever recorded. */
  stale_reason: { label: string | null; due: string | null } | null;
  run: LocalDatabaseRun | null;
  last_run: LocalDatabaseLastRun | null;
  failures: LocalDatabaseFailure[];
  generated_at: string;
  error?: string;
};
