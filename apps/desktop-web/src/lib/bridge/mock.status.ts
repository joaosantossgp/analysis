import type {
  BridgeApi,
  AppStatusPayload,
  DataCoverageResponse,
  DataCoverageRow,
  DatabaseDiagnostics,
  SettingsHealthSummary,
  StorageInventory,
  UpdateChannel,
  UpdateCheckResult,
  UpdateProgressStatus,
} from "./types";
import { mockLocalDatabaseState } from "./mockLocalDatabase";
import { MOCK_COUNTRY_KPI_VALUES } from "./mockEnergyFixtures";
import { MOCK_JOB_RUNNING } from "./mock.refresh";
import { NOW, YEAR, FIXTURE_COMPANIES } from "./mock.fixtures";

const MOCK_COVERAGE_ROWS: DataCoverageRow[] = FIXTURE_COMPANIES.map((c) => ({
  cd_cvm: c.cd_cvm,
  company_name: c.company_name,
  ticker: c.ticker_b3,
  ticker_mapped: c.ticker_b3 !== null,
  cvm_valid: c.cd_cvm < 90000,
  has_registry: c.cd_cvm < 90000,
  has_dfp: c.has_financial_data,
  has_itr: c.has_financial_data,
  latest_dfp_year: c.anos_disponiveis.at(-1) ?? null,
  latest_itr_period: c.has_financial_data ? `3T${String(YEAR - 1).slice(2)}` : null,
  last_status: c.data_status === "failed" ? "error" : c.has_financial_data ? "success" : null,
  last_attempt_at: c.has_financial_data || c.data_status === "failed"
    ? new Date(Date.now() - 86_400_000).toISOString()
    : null,
  last_success_at: c.has_financial_data
    ? new Date(Date.now() - 86_400_000).toISOString()
    : null,
  last_error: c.data_status === "failed" ? "HTTP 403 — CVM server rejected request" : null,
  update_failed: c.data_status === "failed",
  is_stale: false,
  ignored: false,
  ignored_reason: null,
  status: c.data_status as DataCoverageRow["status"],
}));

// ---------------------------------------------------------------------------
// Mock database diagnostics
// ---------------------------------------------------------------------------

const MOCK_DB_DIAGNOSTICS: DatabaseDiagnostics = {
  db_path: "[mock] /dev/mock/db/cvm_financials.db",
  data_root: "[mock] /dev/mock/data",
  db_exists: true,
  db_size_bytes: 24_500_000,
  is_empty: false,
  row_counts: {
    companies: FIXTURE_COMPANIES.length,
    financial_reports: FIXTURE_COMPANIES.reduce((s, c) => s + c.total_rows, 0),
    refresh_jobs: 2,
    company_refresh_status: 4,
    qa_logs: 12,
  },
  latest_success_at: new Date(Date.now() - 86_400_000).toISOString(),
  latest_attempt_at: new Date(Date.now() - 7_200_000).toISOString(),
  latest_error: null,
  latest_report_year: YEAR - 1,
  latest_period_label: String(YEAR - 1),
  refresh_errors_count: 1,
};

// ---------------------------------------------------------------------------
// Mock app status
// ---------------------------------------------------------------------------

const MOCK_APP_STATUS: AppStatusPayload = {
  runtime: {
    version: "0.29.1-mock",
    runtime_mode: "mock",
    bridge_status: "ready",
    frozen: false,
    desktop_shell: "browser-mock",
    local_first: false,
    using_release_data_dir: false,
    write_mode: "read-write",
    lock_status: { status: "locked_by_self", stale_recovered: false, stale_pid: null },
  },
  paths: {
    data: { kind: "data", path: "[mock] /dev/mock/data", exists: true, is_file: false, is_dir: true },
    database: { kind: "database", path: "[mock] /dev/mock/data/db/cvm_financials.db", exists: true, is_file: true, is_dir: false },
    output: { kind: "output", path: "[mock] /dev/mock/output", exists: true, is_file: false, is_dir: true },
    logs: { kind: "logs", path: "[mock] /dev/mock/logs", exists: true, is_file: false, is_dir: true },
    cache: { kind: "cache", path: "[mock] /dev/mock/cache", exists: true, is_file: false, is_dir: true },
  },
  database: MOCK_DB_DIAGNOSTICS,
  update: {
    current_version: "0.29.2",
    latest_version: "0.29.2",
    update_available: false,
    status: "up_to_date",
    channel: "releases",
    publication_kind: "release",
    apply_supported: false,
  },
  diagnostics: {
    ok: true,
    version: "0.29.1-mock",
    dotnet_status: "mock",
    webview2_version: "mock",
    pythonnet_status: "mock",
    sqlite_status: "ok:3.43.0-mock",
    db_path: "[mock] /dev/mock/data/db/cvm_financials.db",
    data_root: "[mock] /dev/mock/data",
    errors: [],
    warnings: ["Mock bridge active — fixture data only. No real database connected."],
  },
  recent: [
    { source: "mock", severity: "info", timestamp: NOW, message: "Mock bridge started — fixture data only" },
  ],
};

const MOCK_SETTINGS_HEALTH: SettingsHealthSummary = {
  generated_at: NOW,
  overall_status: "updating",
  summary: {
    title: "Data update in progress",
    message: "1 active job(s) reported. Required CVM data is usable, with fixture refresh failures for testing.",
    required_segments: 2,
    critical_segments: 0,
    degraded_segments: 1,
    empty_segments: 0,
    updating_segments: 1,
    unknown_segments: 3,
    initial_load_duration_ms: 3,
    initial_bridge_calls: 1,
    full_table_scans: false,
    deferred_detail_contracts: ["get_data_coverage", "get_distribution_health"],
  },
  segments: [
    {
      id: "cvm_financials",
      name: "CVM Financial Statements",
      required: true,
      status: "updating",
      reason: "A mock CVM data update is currently running.",
      owner: "cvm_financials.db",
      provider: "CVM filings",
      record_count: MOCK_DB_DIAGNOSTICS.row_counts.financial_reports,
      latest_reference: String(YEAR - 1),
      last_successful_update: MOCK_DB_DIAGNOSTICS.latest_success_at,
      last_attempted_update: MOCK_DB_DIAGNOSTICS.latest_attempt_at,
      dimensions: {
        availability: "healthy",
        freshness: "unknown",
        coverage: "deferred",
        integrity: "unknown",
        last_refresh: "updating",
        source: "unknown",
      },
      warnings: [],
      errors: [],
      action_route: "/",
      details: { coverage_route: "/settings/data" },
    },
    {
      id: "cvm_registry",
      name: "Companies and CVM Registry",
      required: true,
      status: "healthy",
      reason: "Mock company registry is readable.",
      owner: "cvm_financials.db",
      provider: "CVM/B3 metadata",
      record_count: FIXTURE_COMPANIES.length,
      latest_reference: null,
      last_successful_update: MOCK_DB_DIAGNOSTICS.latest_success_at,
      last_attempted_update: MOCK_DB_DIAGNOSTICS.latest_attempt_at,
      dimensions: {
        availability: "healthy",
        freshness: "unknown",
        coverage: "unknown",
        integrity: "unknown",
        last_refresh: "unknown",
        source: "unknown",
      },
      warnings: [],
      errors: [],
      action_route: "/settings/data",
      details: {},
    },
    {
      id: "energy_macro",
      name: "Energy Macro Indicators",
      required: false,
      status: "degraded",
      reason: "Mock energy KPI data has one data-quality warning.",
      owner: "energy_kpis.db",
      provider: "OWID / Ember",
      record_count: MOCK_COUNTRY_KPI_VALUES.length,
      latest_reference: new Date(Date.now() - 6 * 3_600_000).toISOString(),
      last_successful_update: new Date(Date.now() - 3_600_000).toISOString(),
      last_attempted_update: new Date(Date.now() - 3_600_000).toISOString(),
      dimensions: {
        availability: "healthy",
        freshness: "healthy",
        coverage: "unknown",
        integrity: "degraded",
        last_refresh: "unknown",
        source: "unknown",
      },
      warnings: ["1 data-quality warning"],
      errors: [],
      action_route: "/indicators",
      details: {},
    },
    {
      id: "plant_parcels",
      name: "Generation Assets and CCEE Plant Data",
      required: false,
      status: "unknown",
      reason: "Source counts are deferred to Sources and Imports.",
      owner: "energy_kpis.db",
      provider: "ANEEL / CCEE",
      record_count: null,
      latest_reference: null,
      last_successful_update: null,
      last_attempted_update: null,
      dimensions: {
        availability: "deferred",
        freshness: "deferred",
        coverage: "deferred",
        integrity: "unknown",
        last_refresh: "unknown",
        source: "deferred",
      },
      warnings: [],
      errors: [],
      action_route: "/settings/sources",
      details: { deferred_contract: "get_plant_parcel_source_statuses" },
    },
    {
      id: "distribution",
      name: "Distribution / ANEEL",
      required: false,
      status: "unknown",
      reason: "Distribution row counts and source snapshots are deferred.",
      owner: "energy_kpis.db",
      provider: "ANEEL",
      record_count: null,
      latest_reference: null,
      last_successful_update: null,
      last_attempted_update: null,
      dimensions: {
        availability: "deferred",
        freshness: "deferred",
        coverage: "deferred",
        integrity: "deferred",
        last_refresh: "unknown",
        source: "deferred",
      },
      warnings: [],
      errors: [],
      action_route: "/indicators",
      details: { deferred_contract: "get_distribution_health" },
    },
  ],
  active_jobs: [
    {
      job_id: MOCK_JOB_RUNNING.job_id,
      segment_id: "cvm_financials",
      status: MOCK_JOB_RUNNING.state,
      stage: MOCK_JOB_RUNNING.stage,
      started_at: MOCK_JOB_RUNNING.started_at,
      updated_at: MOCK_JOB_RUNNING.updated_at,
      message: MOCK_JOB_RUNNING.log_lines.at(-1) ?? null,
    },
  ],
  warnings: [
    {
      segment_id: "energy_macro",
      severity: "warning",
      message: "Mock energy KPI data has one data-quality warning.",
      action_route: "/indicators",
    },
  ],
  errors: [],
  storage: MOCK_APP_STATUS.paths,
  runtime: MOCK_APP_STATUS.runtime,
  provenance: [
    {
      metric: "mock_settings_health",
      source: "apps/desktop-web/src/lib/bridge/mock.ts",
      meaning: "Fixture Settings health summary for browser mock mode.",
      cost: "none",
      cache_policy: "static fixture",
      failure_behavior: "not applicable",
    },
  ],
};

const MOCK_STORAGE_INVENTORY: StorageInventory = {
  contract_version: 1,
  status: "degraded",
  generated_at: NOW,
  scanned_at: "2026-06-15T18:30:00Z",
  is_cached: true,
  is_stale: false,
  scan_age_seconds: 9300,
  scan_status: {
    scan_id: "mock-storage-scan",
    status: "succeeded",
    started_at: "2026-06-15T18:29:56Z",
    finished_at: "2026-06-15T18:30:00Z",
    elapsed_ms: 4120,
    error: null,
  },
  logical_bytes_total: 17_179_869_184,
  allocated_bytes_total: null,
  file_count: 18432,
  directory_count: 462,
  skipped_count: 1,
  elapsed_ms: 4120,
  roots: [
    {
      id: "data",
      label: "Data root",
      path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics",
      exists: true,
      category_id: "uncategorized",
      segment_id: "shared_metadata",
      logical_bytes: 17_179_869_184,
      file_count: 18432,
      directory_count: 462,
      skipped_count: 1,
    },
  ],
  excluded_roots: [
    {
      id: "db",
      path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\db",
      reason: "nested under C:\\Users\\Analyst\\Documents\\CVMAnalytics",
    },
  ],
  volumes: [
    {
      id: "C:\\",
      path: "C:\\",
      total_bytes: 512_110_190_592,
      used_bytes: 421_906_219_008,
      free_bytes: 90_203_971_584,
      free_percent: 17.61,
      status: "healthy",
    },
  ],
  categories: [
    { id: "raw_sources", label: "Raw sources", logical_bytes: 6_980_321_280, allocated_bytes: null, file_count: 12043, percentage_of_total: 40.63, root_ids: ["data"], storage_types: ["files"], warnings: [] },
    { id: "databases", label: "Databases", logical_bytes: 3_182_919_680, allocated_bytes: null, file_count: 2, percentage_of_total: 18.53, root_ids: ["data"], storage_types: ["sqlite"], warnings: [] },
    { id: "analytical_stores", label: "Analytical stores", logical_bytes: 2_684_354_560, allocated_bytes: null, file_count: 146, percentage_of_total: 15.63, root_ids: ["data"], storage_types: ["sqlite", "parquet", "manifest"], warnings: [] },
    { id: "cache", label: "Cache", logical_bytes: 1_422_770_176, allocated_bytes: null, file_count: 3261, percentage_of_total: 8.28, root_ids: ["data"], storage_types: ["cache"], warnings: [] },
    { id: "backups", label: "Backups and rollback", logical_bytes: 1_073_741_824, allocated_bytes: null, file_count: 4, percentage_of_total: 6.25, root_ids: ["data"], storage_types: ["files"], warnings: ["Rollback backups are retained until explicitly removed."] },
    { id: "database_sidecars", label: "Database sidecars", logical_bytes: 418_381_824, allocated_bytes: null, file_count: 3, percentage_of_total: 2.44, root_ids: ["data"], storage_types: ["sqlite-sidecar"], warnings: ["Energy KPI WAL is large relative to the main database."] },
    { id: "exports_reports", label: "Exports and reports", logical_bytes: 327_155_712, allocated_bytes: null, file_count: 94, percentage_of_total: 1.9, root_ids: ["data"], storage_types: ["files"], warnings: [] },
    { id: "logs", label: "Logs", logical_bytes: 43_155_456, allocated_bytes: null, file_count: 18, percentage_of_total: 0.25, root_ids: ["data"], storage_types: ["logs"], warnings: [] },
  ],
  segments: [
    { id: "energy_macro", label: "Energy macro / SIN / CCEE / Distribution", logical_bytes: 6_699_720_704, allocated_bytes: null, file_count: 7987, percentage_of_total: 39, root_ids: ["data"], storage_types: ["sqlite", "files", "parquet"], warnings: ["Large WAL observed; diagnostic only."] },
    { id: "cvm_financials", label: "CVM financial statements", logical_bytes: 5_266_374_656, allocated_bytes: null, file_count: 5021, percentage_of_total: 30.65, root_ids: ["data"], storage_types: ["sqlite", "files"], warnings: [] },
    { id: "market_data", label: "Market data", logical_bytes: 1_422_770_176, allocated_bytes: null, file_count: 3261, percentage_of_total: 8.28, root_ids: ["data"], storage_types: ["cache"], warnings: [] },
    { id: "local_backups", label: "Local backups", logical_bytes: 1_073_741_824, allocated_bytes: null, file_count: 4, percentage_of_total: 6.25, root_ids: ["data"], storage_types: ["files"], warnings: ["Rollback backups are retained until explicitly removed."] },
    { id: "user_imports", label: "User imports", logical_bytes: 611_581_952, allocated_bytes: null, file_count: 1812, percentage_of_total: 3.56, root_ids: ["data"], storage_types: ["files"], warnings: [] },
  ],
  databases: [
    {
      id: "cvm_financials",
      label: "CVM financials",
      path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\db\\cvm_financials.db",
      segment_id: "cvm_financials",
      segment_label: "CVM financial statements",
      exists: true,
      readable: true,
      logical_bytes: 2_404_515_840,
      wal_bytes: 58_720_256,
      shm_bytes: 32_768,
      journal_bytes: 0,
      modified_at: "2026-06-15T18:12:00Z",
      sqlite: {
        page_size: 4096,
        page_count: 586_063,
        freelist_count: 12_420,
        estimated_allocated_bytes: 2_400_514_048,
        estimated_internal_free_bytes: 50_872_320,
        journal_mode: "wal",
        schema_version: 32,
        user_version: 0,
      },
      warnings: [],
    },
    {
      id: "energy_kpis",
      label: "Energy KPIs",
      path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\db\\energy_kpis.db",
      segment_id: "energy_macro",
      segment_label: "Energy macro / SIN / CCEE / Distribution",
      exists: true,
      readable: true,
      logical_bytes: 778_403_840,
      wal_bytes: 359_628_800,
      shm_bytes: 32_768,
      journal_bytes: 0,
      modified_at: "2026-06-15T18:10:00Z",
      sqlite: {
        page_size: 4096,
        page_count: 190_040,
        freelist_count: 36_100,
        estimated_allocated_bytes: 778_403_840,
        estimated_internal_free_bytes: 147_865_600,
        journal_mode: "wal",
        schema_version: 18,
        user_version: 0,
      },
      warnings: ["WAL file is large relative to the main database. No checkpoint was run."],
    },
  ],
  backup_candidates: [
    {
      id: "energy_kpis_swap_20260629T142611Z",
      label: "Energy KPI rollback backup",
      path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\backup\\energy_kpis_swap_20260629T142611Z",
      logical_bytes: 1_073_741_824,
      file_count: 4,
      modified_at: "2026-06-15T18:28:00Z",
      reclaimable_bytes: 1_073_741_824,
      requires_confirmation: true,
      destructive: true,
      reason: "Rollback backup retained after a storage migration. Remove only after current data has been validated.",
    },
  ],
  managed_snapshot_history: [
    {
      dataset_id: "fuel_distribution_sector_intake",
      domain: "energy",
      snapshot_id: "fuel_distribution_20260701T131022Z",
      path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\analytics\\energy\\fuel_distribution_sector_intake\\raw\\fuel_distribution_20260701T131022Z",
      logical_bytes: 62_920_814,
      file_count: 15,
      modified_at: "2026-07-01T13:10:22Z",
      active_in_manifest: true,
      status: "current",
      reason: "Current raw source snapshot referenced by the managed dataset manifest.",
    },
    {
      dataset_id: "fuel_distribution_sector_intake",
      domain: "energy",
      snapshot_id: "fuel_distribution_20260701T020351Z",
      path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\analytics\\energy\\fuel_distribution_sector_intake\\raw\\fuel_distribution_20260701T020351Z",
      logical_bytes: 62_920_814,
      file_count: 15,
      modified_at: "2026-07-01T02:03:51Z",
      active_in_manifest: false,
      status: "retained_audit_snapshot",
      reason: "Retained raw source snapshot for auditability; this is not a cleanup action.",
    },
  ],
  largest_items: [
    { path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\analytics\\energy\\ccee_plant_generation_hourly\\hot\\energy_hot.sqlite", name: "energy_hot.sqlite", logical_bytes: 2_147_483_648, category_id: "analytical_stores", category_label: "Analytical stores", segment_id: "energy_macro", segment_label: "Energy macro / SIN / CCEE / Distribution", storage_type: "sqlite", modified_at: "2026-06-15T18:25:00Z" },
    { path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\raw\\ccee\\hourly_2026.zip", name: "hourly_2026.zip", logical_bytes: 1_912_680_448, category_id: "raw_sources", category_label: "Raw sources", segment_id: "energy_macro", segment_label: "Energy macro / SIN / CCEE / Distribution", storage_type: "files", modified_at: "2026-06-15T17:31:00Z" },
    { path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\backup\\energy_kpis_swap_20260629T142611Z\\energy_kpis.db", name: "energy_kpis.db", logical_bytes: 1_073_741_824, category_id: "backups", category_label: "Backups and rollback", segment_id: "local_backups", segment_label: "Local backups", storage_type: "files", modified_at: "2026-06-15T18:28:00Z" },
    { path: "C:\\Users\\Analyst\\Documents\\CVMAnalytics\\db\\cvm_financials.db", name: "cvm_financials.db", logical_bytes: 2_404_515_840, category_id: "databases", category_label: "Databases", segment_id: "cvm_financials", segment_label: "CVM financial statements", storage_type: "sqlite", modified_at: "2026-06-15T18:12:00Z" },
  ],
  growth: {
    available: true,
    previous_scanned_at: "2026-06-14T18:30:00Z",
    change_since_previous_bytes: 214_958_080,
    seven_day_change_bytes: null,
    thirty_day_change_bytes: null,
  },
  warnings: ["1 path was skipped during inventory.", "Energy KPIs: WAL file is large relative to the main database. No checkpoint was run."],
  errors: [],
  measurement_notes: [
    "logical_bytes is the sum of filesystem file lengths.",
    "allocated_bytes_total is unavailable in this mock fixture.",
    "SQLite free-page bytes are internal reusable capacity, not immediately reclaimable disk space.",
  ],
  performance: {
    files_per_second: 4473.79,
    full_database_table_scans: false,
    content_hashing: false,
  },
};

MOCK_SETTINGS_HEALTH.storage_inventory = {
  status: MOCK_STORAGE_INVENTORY.status,
  generated_at: MOCK_STORAGE_INVENTORY.generated_at,
  scanned_at: MOCK_STORAGE_INVENTORY.scanned_at,
  is_cached: true,
  is_stale: false,
  scan_age_seconds: MOCK_STORAGE_INVENTORY.scan_age_seconds,
  scan_status: MOCK_STORAGE_INVENTORY.scan_status,
  logical_bytes_total: MOCK_STORAGE_INVENTORY.logical_bytes_total,
  file_count: MOCK_STORAGE_INVENTORY.file_count,
  directory_count: MOCK_STORAGE_INVENTORY.directory_count,
  skipped_count: MOCK_STORAGE_INVENTORY.skipped_count,
  largest_category: MOCK_STORAGE_INVENTORY.categories[0],
  largest_segment: MOCK_STORAGE_INVENTORY.segments[0],
  main_volume: MOCK_STORAGE_INVENTORY.volumes[0],
  growth: MOCK_STORAGE_INVENTORY.growth,
  warnings: MOCK_STORAGE_INVENTORY.warnings,
  errors: MOCK_STORAGE_INVENTORY.errors,
  measurement_notes: MOCK_STORAGE_INVENTORY.measurement_notes,
};

// ---------------------------------------------------------------------------
// Country Energy KPI fixtures
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Data update settings
// ---------------------------------------------------------------------------

/**
 * Update check fixtures: an installed 0.29.2 against the publications that
 * exist today (release 0.29.2, pre-release 0.30.0-rc.1), an offline check, a
 * newer release and a postponed one. By default the mock answers by channel;
 * pick a fixture for the shell announcement with
 * `localStorage.setItem("cvm_mock_update", "release_available")` and reload.
 */
export const MOCK_UPDATE_SCENARIO_KEY = "cvm_mock_update";

const MOCK_RELEASE_AVAILABLE: UpdateCheckResult = {
  available: true,
  version: "0.30.1",
  zip_url: "[mock] CVMAnalytics-windows-v0.30.1.zip",
  status: "available",
  error: null,
  channel: "releases",
  publication_kind: "release",
  checked_at: NOW,
  current_version: "0.29.2",
  latest_version: "0.30.1",
  release_url: "https://github.com/joaosantossgp/analisys/releases",
};

export const MOCK_UPDATE_CHECKS: Record<UpdateChannel | "offline" | "release_available" | "snoozed", UpdateCheckResult> = {
  releases: {
    available: false,
    status: "up_to_date",
    error: null,
    channel: "releases",
    publication_kind: "release",
    checked_at: NOW,
    current_version: "0.29.2",
    latest_version: "0.29.2",
    release_url: null,
  },
  prereleases: {
    available: true,
    version: "0.30.0-rc.1",
    zip_url: "[mock] CVMAnalytics-windows-v0.30.0-rc.1.zip",
    status: "available",
    error: null,
    channel: "prereleases",
    publication_kind: "pre-release",
    checked_at: NOW,
    current_version: "0.29.2",
    latest_version: "0.30.0-rc.1",
    release_url: null,
  },
  offline: {
    available: false,
    status: "check_failed",
    error: "Could not check GitHub Releases: [mock] no network",
    channel: "releases",
    publication_kind: null,
    checked_at: NOW,
    current_version: "0.29.2",
    latest_version: null,
    release_url: null,
  },
  release_available: MOCK_RELEASE_AVAILABLE,
  snoozed: postponeCheck(MOCK_RELEASE_AVAILABLE),
};

/** What check_update answers after "Later": the offer stays known, nothing to apply. */
function postponeCheck(check: UpdateCheckResult): UpdateCheckResult {
  return { ...check, available: false, version: undefined, zip_url: undefined, status: "snoozed" };
}

export const MOCK_UPDATE_PROGRESS: Record<"idle" | "downloading" | "error", UpdateProgressStatus> = {
  idle: { status: "idle", percent: 0, error: null },
  downloading: { status: "downloading", percent: 42, error: null },
  error: {
    status: "error",
    percent: 0,
    error: "[mock] Simulated failure before the swap: mock mode never replaces the app.",
  },
};

// One step per get_update_progress poll after "Update now"; mock mode always ends in the error.
const MOCK_APPLY_STEPS: UpdateProgressStatus[] = [
  { status: "downloading", percent: 0, error: null },
  { status: "downloading", percent: 18, error: null },
  MOCK_UPDATE_PROGRESS.downloading,
  { status: "downloading", percent: 71, error: null },
  { status: "validating", percent: 90, error: null },
  MOCK_UPDATE_PROGRESS.error,
];

function mockUpdateScenario(): keyof typeof MOCK_UPDATE_CHECKS | null {
  try {
    const key = globalThis.localStorage?.getItem(MOCK_UPDATE_SCENARIO_KEY) ?? null;
    return key && key in MOCK_UPDATE_CHECKS ? (key as keyof typeof MOCK_UPDATE_CHECKS) : null;
  } catch {
    return null;
  }
}

export function createMockStatusMethods(): Partial<BridgeApi> {
  let mockUpdateChannel: UpdateChannel = "releases";
  let postponed = false;
  let applyStep: number | null = null;
  const currentCheck = (): UpdateCheckResult => {
    const check = MOCK_UPDATE_CHECKS[mockUpdateScenario() ?? mockUpdateChannel];
    return postponed && check.available ? postponeCheck(check) : check;
  };
  return {
    ping: async () => ({ pong: true, ts: Date.now() / 1000 }),

    get_health: async () => ({
      status: "ok",
      version: "0.29.1-mock",
      database_dialect: "sqlite",
      required_tables: ["financial_reports", "companies", "refresh_jobs"],
      warnings: [],
      errors: [],
    }),

    get_app_status: async () => MOCK_APP_STATUS,

    get_settings_health_summary: async () => MOCK_SETTINGS_HEALTH,

    get_storage_inventory: async () => MOCK_STORAGE_INVENTORY,

    start_storage_inventory_scan: async () => ({
      started: true,
      scan_status: {
        scan_id: "mock-storage-scan-refresh",
        status: "succeeded",
        started_at: NOW,
        finished_at: NOW,
        elapsed_ms: 4120,
        error: null,
      },
      inventory: MOCK_STORAGE_INVENTORY,
    }),

    get_storage_inventory_scan_status: async () => MOCK_STORAGE_INVENTORY.scan_status,

    get_database_diagnostics: async () => MOCK_DB_DIAGNOSTICS,

    get_local_database_state: async () => mockLocalDatabaseState(),

    get_data_coverage: async () => ({
      generated_at: new Date(Date.now() - 300_000).toISOString(),
      stale_cutoff_year: YEAR - 2,
      summary: {
        total: FIXTURE_COMPANIES.length,
        complete: 2,
        partial: 1,
        no_financial: 2,
        failed: 1,
        stale: 0,
        unmapped: 1,
        ignored: 0,
      },
      filter_counts: { all: FIXTURE_COMPANIES.length, failed: 1, no_financial: 2 },
      rows: MOCK_COVERAGE_ROWS,
    } satisfies DataCoverageResponse),

    set_company_ignored: async (params) => {
      const p = params as Record<string, unknown>;
      return {
        ok: true,
        cd_cvm: Number(p?.cd_cvm ?? 0),
        ignored: Boolean(p?.ignored ?? true),
        ignored_at: NOW,
        ignored_reason: String(p?.reason ?? ""),
      };
    },

    check_update: async () => currentCheck(),

    get_update_channel: async () => ({ channel: mockUpdateChannel }),

    set_update_channel: async ({ channel }) => {
      if (channel !== "releases" && channel !== "prereleases") {
        return { ok: false, error: "invalid_channel", channel: mockUpdateChannel };
      }
      mockUpdateChannel = channel;
      return { ok: true, channel };
    },

    apply_update: async () => {
      if (!currentCheck().available) return { started: false, error: "no_update_available" };
      applyStep = 0;
      return { started: true };
    },

    get_update_progress: async () => {
      if (applyStep === null) return MOCK_UPDATE_PROGRESS.idle;
      const step = MOCK_APPLY_STEPS[applyStep];
      applyStep = Math.min(applyStep + 1, MOCK_APPLY_STEPS.length - 1);
      return step;
    },

    snooze_update: async () => {
      if (!currentCheck().available) return { ok: false, error: "no_update_info" };
      postponed = true;
      return { ok: true };
    },

    open_status_path: async () => ({
      ok: false,
      kind: "data",
      path: null,
      error: "[mock] Cannot open filesystem paths in browser mode",
    }),

    dev_reset_universe: async () => ({ ok: true }),

    dev_reset_jobs: async () => ({ ok: true }),

    dev_simulate_refresh: async () => ({ ok: true, mode: "mock" }),

    dev_start_small_setup: async () => ({ status: "accepted", message: "[mock] Small setup started" }),

    dev_get_raw_state: async () => ({ app_settings: [], refresh_jobs: [] }),
  };
}
