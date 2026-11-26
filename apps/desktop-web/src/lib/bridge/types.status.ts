// App health, runtime diagnostics, settings health, storage inventory, and data coverage bridge types.

export type HealthPayload = {
  status: "ok" | "degraded" | string;
  version: string;
  database_dialect: string | null;
  required_tables: string[];
  warnings: Array<{ severity: string; code: string; message: string; path: string | null }>;
  errors: Array<{ severity: string; code: string; message: string; path: string | null }>;
};

export type DatabaseDiagnostics = {
  db_path: string | null;
  data_root: string | null;
  db_exists: boolean;
  db_size_bytes: number;
  is_empty: boolean;
  row_counts: {
    companies: number | null;
    financial_reports: number | null;
    refresh_jobs: number | null;
    company_refresh_status: number | null;
    qa_logs: number | null;
  };
  latest_success_at: string | null;
  latest_attempt_at: string | null;
  latest_error: string | null;
  latest_report_year?: number | null;
  latest_period_label?: string | null;
  refresh_errors_count?: number | null;
  error?: string;
};

export type LockStatus =
  | "locked_by_self"
  | "locked_by_other"
  | "stale_recovered"
  | "no_lock"
  | string;

export type LockStatusPayload = {
  status: LockStatus;
  pid?: number | null;
  runtime_mode?: string | null;
  started_at?: string | null;
  stale_recovered?: boolean;
  stale_pid?: number | null;
};

export type RefreshWorkerRuntimeStatus = {
  status: string;
  worker_id?: string | null;
  started_at?: string | null;
  last_heartbeat_at?: string | null;
  last_error?: string | null;
  active_jobs?: number;
  heartbeat_age_seconds?: number | null;
  stale?: boolean;
};

export type AppRuntimeStatus = {
  version: string;
  build_commit?: string | null;
  build_time?: string | null;
  runtime_mode: "vite" | "vite-dev" | "vite-dev-release-data" | "mock" | "unknown" | string;
  bridge_status: "ready" | "error" | "unknown" | string;
  frozen: boolean;
  desktop_shell: string | null;
  local_first: boolean;
  using_release_data_dir?: boolean;
  write_mode?: "read-write" | "read-only" | string;
  lock_status?: LockStatusPayload | null;
  refresh_worker?: RefreshWorkerRuntimeStatus | null;
};

export type LocalPathInfo = {
  kind: "data" | "database" | "output" | "logs" | "cache" | string;
  path: string;
  exists: boolean;
  is_file: boolean;
  is_dir: boolean;
};

export type UpdateProgressStatus = {
  status: string;
  percent: number;
  error: string | null;
};

export type UpdateStatus = {
  current_version: string | null;
  latest_version: string | null;
  latest_tag?: string | null;
  update_available: boolean;
  release_url?: string | null;
  zip_url?: string | null;
  sha256_url?: string | null;
  asset_name?: string | null;
  sha256_asset_name?: string | null;
  checked_at?: string | null;
  status:
    | "available"
    | "up_to_date"
    | "check_failed"
    | "asset_missing"
    | "snoozed"
    | "no_release"
    | "available_cached"
    | "unknown"
    | string;
  error?: string | null;
  can_apply?: boolean;
  apply_supported: boolean;
  progress?: UpdateProgressStatus;
};

export type DiagnosticsSummary = {
  ok: boolean;
  version?: string | null;
  dotnet_status?: string | null;
  webview2_version?: string | null;
  pythonnet_status?: string | null;
  sqlite_status?: string | null;
  db_path?: string | null;
  data_root?: string | null;
  errors: string[];
  warnings: string[];
};

export type DiagnosticLogEntry = {
  source: string;
  severity: "info" | "warning" | "error" | string;
  timestamp?: string | null;
  message: string;
};

export type AppStatusPayload = {
  runtime: AppRuntimeStatus;
  paths: Partial<Record<"data" | "database" | "output" | "logs" | "cache", LocalPathInfo>>;
  database: DatabaseDiagnostics | null;
  update: UpdateStatus | null;
  diagnostics: DiagnosticsSummary;
  recent: DiagnosticLogEntry[];
  error?: string;
};

export type SettingsHealthStatus =
  | "healthy"
  | "degraded"
  | "critical"
  | "updating"
  | "empty"
  | "unavailable"
  | "unknown";

export type SettingsHealthDimensionStatus =
  | SettingsHealthStatus
  | "deferred";

export type SettingsHealthIssue = {
  segment_id: string;
  severity: "info" | "warning" | "critical" | "error" | string;
  message: string;
  action_route?: string | null;
};

export type SettingsHealthSegment = {
  id: string;
  name: string;
  required: boolean;
  status: SettingsHealthStatus;
  reason: string;
  owner: string | null;
  provider: string | null;
  record_count: number | null;
  latest_reference: string | null;
  last_successful_update: string | null;
  last_attempted_update: string | null;
  dimensions: {
    availability: SettingsHealthDimensionStatus;
    freshness: SettingsHealthDimensionStatus;
    coverage: SettingsHealthDimensionStatus;
    integrity: SettingsHealthDimensionStatus;
    last_refresh: SettingsHealthDimensionStatus;
    source: SettingsHealthDimensionStatus;
  };
  warnings: string[];
  errors: string[];
  action_route: string;
  details?: Record<string, unknown>;
};

export type SettingsHealthActiveJob = {
  job_id: string | null;
  segment_id: string;
  status: string | null;
  stage?: string | null;
  started_at?: string | null;
  updated_at?: string | null;
  message?: string | null;
};

export type SettingsHealthProvenance = {
  metric: string;
  source: string;
  meaning: string;
  cost: string;
  cache_policy: string;
  failure_behavior: string;
};

export type SettingsHealthSummary = {
  generated_at: string | null;
  overall_status: SettingsHealthStatus;
  summary: {
    title: string;
    message: string;
    required_segments?: number;
    critical_segments?: number;
    degraded_segments?: number;
    empty_segments?: number;
    updating_segments?: number;
    unknown_segments?: number;
    initial_load_duration_ms?: number;
    initial_bridge_calls?: number;
    full_table_scans?: boolean;
    deferred_detail_contracts?: string[];
  };
  segments: SettingsHealthSegment[];
  active_jobs: SettingsHealthActiveJob[];
  warnings: SettingsHealthIssue[];
  errors: SettingsHealthIssue[];
  storage: Partial<Record<"data" | "database" | "output" | "logs" | "cache", LocalPathInfo>>;
  storage_inventory?: StorageInventorySummary | null;
  runtime: AppRuntimeStatus;
  provenance: SettingsHealthProvenance[];
  error?: string;
};

export type StorageInventoryStatus =
  | "healthy"
  | "degraded"
  | "critical"
  | "updating"
  | "unavailable"
  | "unknown"
  | "partial";

export type StorageScanStatus = {
  scan_id?: string | null;
  status: "idle" | "running" | "succeeded" | "partial" | "failed";
  started_at?: string | null;
  finished_at?: string | null;
  elapsed_ms?: number | null;
  error?: string | null;
};

export type StorageAggregateRow = {
  id: string;
  label: string;
  logical_bytes: number;
  allocated_bytes?: number | null;
  file_count: number;
  directory_count?: number;
  percentage_of_total?: number;
  root_ids?: string[];
  storage_types?: string[];
  warnings?: string[];
};

export type StorageVolumeInfo = {
  id: string;
  path: string;
  total_bytes?: number;
  used_bytes?: number;
  free_bytes?: number;
  free_percent?: number | null;
  status: SettingsHealthStatus;
  error?: string;
};

export type StorageDatabaseInfo = {
  id: string;
  label: string;
  path: string;
  segment_id: string;
  segment_label: string;
  exists: boolean;
  readable: boolean | null;
  logical_bytes: number;
  wal_bytes: number;
  shm_bytes: number;
  journal_bytes: number;
  modified_at?: string | null;
  sqlite?: {
    page_size: number;
    page_count: number;
    freelist_count: number;
    estimated_allocated_bytes: number;
    estimated_internal_free_bytes: number;
    journal_mode: string;
    schema_version: number;
    user_version: number;
  } | null;
  warnings: string[];
};

export type StorageRootInfo = {
  id: string;
  label: string;
  path: string;
  exists: boolean;
  category_id: string;
  segment_id: string;
  logical_bytes: number;
  file_count: number;
  directory_count: number;
  skipped_count: number;
};

export type StorageLargestItem = {
  path: string;
  name: string;
  logical_bytes: number;
  category_id: string;
  category_label: string;
  segment_id: string;
  segment_label: string;
  storage_type: string;
  modified_at?: string | null;
};

export type StorageBackupCandidate = {
  id: string;
  label: string;
  path: string;
  logical_bytes: number;
  file_count: number;
  modified_at?: string | null;
  reclaimable_bytes: number;
  requires_confirmation: boolean;
  destructive: boolean;
  reason: string;
};

export type StorageManagedSnapshotHistory = {
  dataset_id: string;
  domain: string;
  snapshot_id: string;
  path: string;
  logical_bytes: number;
  file_count: number;
  modified_at?: string | null;
  active_in_manifest: boolean;
  status: "current" | "retained_audit_snapshot" | string;
  reason: string;
};

export type StorageGrowthInfo = {
  available: boolean;
  reason?: string;
  previous_scanned_at?: string | null;
  change_since_previous_bytes?: number | null;
  seven_day_change_bytes?: number | null;
  thirty_day_change_bytes?: number | null;
};

export type StorageInventory = {
  contract_version: number;
  status: StorageInventoryStatus;
  generated_at: string | null;
  scanned_at: string | null;
  is_cached: boolean;
  is_stale: boolean;
  scan_age_seconds?: number | null;
  scan_status: StorageScanStatus;
  logical_bytes_total: number;
  allocated_bytes_total?: number | null;
  file_count: number;
  directory_count: number;
  skipped_count: number;
  elapsed_ms?: number | null;
  roots: StorageRootInfo[];
  excluded_roots: Array<{ id: string; path: string; reason: string }>;
  volumes: StorageVolumeInfo[];
  categories: StorageAggregateRow[];
  segments: StorageAggregateRow[];
  databases: StorageDatabaseInfo[];
  backup_candidates?: StorageBackupCandidate[];
  managed_snapshot_history?: StorageManagedSnapshotHistory[];
  largest_items: StorageLargestItem[];
  growth: StorageGrowthInfo;
  warnings: string[];
  errors: string[];
  measurement_notes: string[];
  performance?: {
    files_per_second?: number;
    full_database_table_scans?: boolean;
    content_hashing?: boolean;
  };
};

export type StorageInventorySummary = Pick<
  StorageInventory,
  | "status"
  | "generated_at"
  | "scanned_at"
  | "is_cached"
  | "is_stale"
  | "scan_age_seconds"
  | "scan_status"
  | "logical_bytes_total"
  | "file_count"
  | "directory_count"
  | "skipped_count"
  | "growth"
  | "warnings"
  | "errors"
  | "measurement_notes"
> & {
  largest_category?: StorageAggregateRow | null;
  largest_segment?: StorageAggregateRow | null;
  main_volume?: StorageVolumeInfo | null;
};

export type StartStorageInventoryScanResult = {
  started: boolean;
  scan_status: StorageScanStatus;
  inventory?: StorageInventory | null;
  error?: string;
};

export type OpenStatusPathResult = {
  ok: boolean;
  kind: string;
  path: string | null;
  error?: string;
};

export type PingResult = {
  pong: boolean;
  ts: number;
};

export type DataCoverageStatus =
  | "complete"
  | "partial"
  | "no_financial"
  | "failed"
  | "unmapped"
  | "ignored";

export type DataCoverageFilterId =
  | "all"
  | "no_dfp"
  | "no_itr"
  | "no_financial"
  | "stale"
  | "failed"
  | "ticker_unmapped"
  | "cvm_unmapped"
  | "no_registry"
  | "ignored";

export type DataCoverageRow = {
  cd_cvm: number;
  company_name: string;
  ticker: string | null;
  ticker_mapped: boolean;
  cvm_valid: boolean;
  has_registry: boolean;
  has_dfp: boolean;
  has_itr: boolean;
  latest_dfp_year: number | null;
  latest_itr_period: string | null;
  last_status: string | null;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  update_failed: boolean;
  is_stale: boolean;
  ignored: boolean;
  ignored_reason: string | null;
  status: DataCoverageStatus;
};

export type DataCoverageSummary = {
  total: number;
  complete: number;
  partial: number;
  no_financial: number;
  failed: number;
  stale: number;
  unmapped: number;
  ignored: number;
};

export type SetCompanyIgnoredResponse = {
  ok: boolean;
  cd_cvm?: number;
  ignored?: boolean;
  ignored_at?: string | null;
  ignored_reason?: string | null;
  error?: string;
};

export type DataCoverageResponse = {
  generated_at: string | null;
  stale_cutoff_year: number | null;
  summary: DataCoverageSummary;
  filter_counts: Partial<Record<DataCoverageFilterId, number>>;
  rows: DataCoverageRow[];
  error?: string;
};
