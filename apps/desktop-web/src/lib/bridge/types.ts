// Mirror of the Python bridge surface in desktop/bridge.py.
//
// This file is the single typed contract for the pywebview JS API. Components
// MUST NOT reference window.pywebview directly — they go through the adapter
// in ./adapter.ts which validates availability and forwards calls.

export type HealthPayload = {
  status: "ok" | "degraded" | string;
  version: string;
  database_dialect: string | null;
  required_tables: string[];
  warnings: Array<{ severity: string; code: string; message: string; path: string | null }>;
  errors: Array<{ severity: string; code: string; message: string; path: string | null }>;
};

export type CompanyDataStatus = "no_history" | "partial" | "complete" | "failed" | "unmapped" | string;

export type CompanyDirectoryItem = {
  cd_cvm: number;
  company_name: string;
  ticker_b3: string | null;
  setor_analitico: string | null;
  setor_cvm: string | null;
  sector_name: string;
  sector_slug: string;
  anos_disponiveis: number[];
  total_rows: number;
  has_financial_data: boolean;
  coverage_rank: number | null;
  /** Derived coverage status from Python layer. Falls back to "no_history" when unset. */
  data_status?: CompanyDataStatus;
  gics_sector?: string | null;
  gics_sector_slug?: string | null;
  gics_industry_group?: string | null;
  gics_industry?: string | null;
  gics_sub_industry?: string | null;
};

export type CompanyDirectoryPagination = {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
};

export type CompanyDirectoryFilters = {
  search: string;
  sector: string | null;
};

export type CompanyDirectoryPage = {
  items: CompanyDirectoryItem[];
  pagination: CompanyDirectoryPagination;
  applied_filters: CompanyDirectoryFilters;
  /** Bridge instrumentation. Optional, present when CVMBridge times the call. */
  _bridge_ms?: number;
  /** Present only on error (bridge swallows exceptions). */
  error?: string;
};

/** Loose parameter shape — CVMBridge.get_companies uses .get() on every key. */
export type CompaniesQuery = {
  search?: string;
  sector_slug?: string | null;
  page?: number;
  page_size?: number;
};

export type CompanyInfo = {
  cd_cvm: number;
  company_name: string;
  nome_comercial: string | null;
  cnpj: string | null;
  ticker_b3: string | null;
  company_type: string | null;
  setor_cvm: string | null;
  setor_analitico: string | null;
  sector_name?: string | null;
  sector_slug?: string | null;
  gics_sector?: string | null;
  gics_sector_slug?: string | null;
  gics_industry_group?: string | null;
  gics_industry?: string | null;
  gics_sub_industry?: string | null;
  has_local_financial_reports: boolean;
  has_readable_current_data: boolean;
  readable_years_count: number;
  latest_readable_year: number | null;
  read_model_updated_at: string | null;
  read_availability_code: string | null;
  read_availability_message: string | null;
  /** Set to true by the bridge when the cd_cvm was not found in the local catalog. */
  not_found?: boolean;
  catalog_lookup_pending?: boolean;
};

export type CompanyYearsResult = {
  years: number[];
  error?: string;
};

export type TabularRow = Record<string, string | number | boolean | null>;
export type TabularData = {
  columns: string[];
  rows: TabularRow[];
};

export type KPIBundle = {
  cd_cvm: number;
  years: number[];
  annual: TabularData;
  quarterly: TabularData;
  error?: string;
};

export type StatementMatrix = {
  cd_cvm: number;
  statement_type: string;
  years: number[];
  table: TabularData;
  exclude_conflicts: boolean;
  error?: string;
};

export type BaseHealthYearCoverage = {
  year: number;
  total_companies: number;
  completed: number;
  missing: number;
  pct: number;
  eta_hours: number | null;
};

export type BaseHealthPriority = {
  cd_cvm: number;
  company_name: string;
  sector_name: string;
  sector_slug: string;
  priority_score: number;
  missing_years_count: number;
  gap_to_leader_years: number;
  years_missing: number[];
  recommended_action: string;
  reason: string;
};

export type BaseHealthSnapshot = {
  generated_at: string | null;
  start_year: number;
  end_year: number;
  total_cells: number;
  completed_cells: number;
  missing_cells: number;
  pct: number;
  health_score: number;
  health_status: string;
  eta_hours: number | null;
  throughput_per_hour: number | null;
  throughput_confidence: string;
  per_year: BaseHealthYearCoverage[];
  prioritized_companies: BaseHealthPriority[];
  raw: Record<string, unknown>;
  total_companies: number;
  companies_with_historical_data: number;
  companies_without_historical_data: number;
  companies_with_any_local_financial_report: number;
  companies_partial_local: number;
  companies_fully_updated: number;
  companies_with_refresh_status_recorded: number;
  companies_with_last_refresh_error: number;
  error?: string;
};

export type RefreshMode = "missing" | "full" | "outdated" | "failed";

export type RefreshDispatchResponse = {
  status: string;
  job_id: string | null;
  accepted_at?: string | null;
  queued?: number;
  message?: string;
  status_reason_code?: string | null;
  status_reason_message?: string | null;
  is_retry_allowed?: boolean;
  error?: string;
};

export type DataUpdateSettings = {
  universe_preset: CompanyUniversePreset;
  batch_size: 50 | 100 | 200 | 500;
  retry_failed: boolean;
  recompute_coverage: boolean;
  start_year: number;
  end_year: number;
  error?: string;
};

export type DataUpdateStartResponse = RefreshDispatchResponse & {
  selection?: CompanyUniverseSelection;
  settings?: DataUpdateSettings;
};

export type ResetLocalDatabaseResponse = {
  ok: boolean;
  action: "restart_current" | "recreate_local" | string;
  message?: string;
  backup_path?: string | null;
  backup_items?: string[];
  removed?: string[];
  active_job_id?: string | null;
  error?: string;
};

export type RefreshJobStatus = {
  job_id: string;
  state: string;
  status?: string;
  mode?: RefreshMode | string | null;
  stage?: string | null;
  queued: number;
  processed: number;
  failures: number;
  current_cvm?: number | null;
  log_lines: string[];
  accepted_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
  result?: Record<string, unknown> | null;
  /** "batch" (DesktopRefreshJobManager) or "db_worker" (refresh_jobs table). */
  source?: "batch" | "db_worker" | string | null;
  /** Present on synthesized db_worker jobs; absent on batch jobs. */
  progress_current?: number | null;
  progress_total?: number | null;
};

export type RefreshJobListResponse = {
  items: RefreshJobStatus[];
  error?: string;
};

export type CompanyUniversePreset = "top_100" | "top_200" | "top_500" | "all";

export type CompanyUniverseEntry = {
  cd_cvm: number;
  ticker: string | null;
  company_name: string;
  market_cap: number | null;
  market_cap_rank: number | null;
  source: string;
  source_date: string | null;
};

export type CompanyUniverseSelection = {
  preset: CompanyUniversePreset;
  selected_count: number;
  company_ids: number[];
  source: string;
  source_date: string | null;
  warning: string | null;
  companies: CompanyUniverseEntry[];
};

export type CompanyUniverseProviderStatus = {
  provider: string;
  configured: boolean;
  available: boolean;
  source?: string | null;
  source_date?: string | null;
  ranked_companies?: number | null;
  message?: string | null;
};

export type OnboardingState = {
  first_run_completed: boolean;
  should_show: boolean;
  selected_company_universe: CompanyUniversePreset | null;
  company_universe_source: string | null;
  company_universe_source_date: string | null;
  setup_status: string;
  selected_company_count: number;
  refresh_job_id: string | null;
  refresh_job?: RefreshJobStatus;
  warning: string | null;
  has_local_financial_data: boolean;
  market_cap_source_available?: boolean;
  market_cap_source?: string | null;
  market_cap_source_date?: string | null;
  market_cap_snapshot_path?: string | null;
  market_cap_ranked_companies?: number | null;
  company_universe_provider_order?: string[];
  company_universe_provider_status?: CompanyUniverseProviderStatus[];
  brapi_configured?: boolean;
  yfinance_universe_provider_enabled?: boolean;
  error?: string;
};

export type OnboardingStartResponse = RefreshDispatchResponse & {
  selection?: CompanyUniverseSelection;
};

export type CompanyRefreshTrackingState =
  | "idle"
  | "queued"
  | "running"
  | "stalled"
  | "success"
  | "no_data"
  | "error"
  | string;

export type CompanyRefreshStatus = {
  cd_cvm: number;
  company_name: string;
  source_scope?: string | null;
  job_id?: string | null;
  stage?: string | null;
  queue_position?: number | null;
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  last_status?: string | null;
  last_error?: string | null;
  last_start_year?: number | null;
  last_end_year?: number | null;
  last_rows_inserted?: number | null;
  progress_current?: number | null;
  progress_total?: number | null;
  progress_message?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
  finished_at?: string | null;
  updated_at?: string | null;
  read_model_updated_at?: string | null;
  estimated_progress_pct?: number | null;
  estimated_eta_seconds?: number | null;
  estimated_total_seconds?: number | null;
  elapsed_seconds?: number | null;
  estimated_completion_at?: string | null;
  estimate_confidence?: string | null;
  tracking_state?: CompanyRefreshTrackingState | null;
  progress_mode?: string | null;
  is_retry_allowed?: boolean;
  status_reason_code?: string | null;
  status_reason_message?: string | null;
  has_readable_current_data?: boolean;
  readable_years_count?: number;
  latest_readable_year?: number | null;
  latest_attempt_outcome?: string | null;
  latest_attempt_reason_code?: string | null;
  latest_attempt_reason_message?: string | null;
  latest_attempt_retryable?: boolean;
  read_availability_code?: string | null;
  read_availability_message?: string | null;
  freshness_summary_code?: string | null;
  freshness_summary_message?: string | null;
  freshness_summary_severity?: "success" | "warning" | "error" | "info" | string | null;
  source_label?: string | null;
};

export type CompanyRefreshStatusListResponse = {
  items: CompanyRefreshStatus[];
  error?: string;
};

export type CancelRefreshResponse = {
  ok: boolean;
  message?: string;
  error?: string;
};

export type CompanySectorFilterOption = {
  sector_name: string;
  sector_slug: string;
  company_count: number;
  gics_sector: string | null;
  gics_sector_slug: string | null;
  gics_sub_industry: string | null;
};

export type CompanyFiltersResponse = {
  sectors: CompanySectorFilterOption[];
  error?: string;
};

export type SectorSnapshot = {
  roe: number | null;
  mg_ebit: number | null;
  mg_liq: number | null;
};

export type SubIndustryCount = {
  name: string;
  count: number;
};

export type SectorCompanyMetric = {
  cd_cvm: number;
  company_name: string;
  ticker_b3: string | null;
  gics_sub_industry: string | null;
  roe: number | null;
  mg_ebit: number | null;
  mg_liq: number | null;
};

export type SectorDirectoryItem = {
  sector_name: string;
  sector_slug: string;
  company_count: number;
  latest_year: number | null;
  snapshot: SectorSnapshot;
  sub_industries: string[];
  sub_industry_breakdown: SubIndustryCount[];
  group_type: "sector" | "sub_sector" | string;
  parent_sector_name: string | null;
  parent_sector_slug: string | null;
  companies: SectorCompanyMetric[];
};

export type SectorDirectoryResponse = {
  items: SectorDirectoryItem[];
  error?: string;
};

export type SectorYearOverview = {
  year: number;
  roe: number | null;
  mg_ebit: number | null;
  mg_liq: number | null;
};

export type SectorDetailResponse = {
  sector_name: string;
  sector_slug: string;
  company_count: number;
  available_years: number[];
  selected_year: number;
  yearly_overview: SectorYearOverview[];
  companies: SectorCompanyMetric[];
  parent_sector_name: string | null;
  parent_sector_slug: string | null;
  not_found?: boolean;
  error?: string;
};

export type ExportCompanyResult = {
  ok: boolean;
  file_path?: string;
  file_name?: string;
  output_dir?: string;
  size_bytes?: number;
  revealed?: boolean;
  error?: string;
};

export type OutputDirInfo = {
  path: string | null;
  exists: boolean;
  error?: string;
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

/**
 * Complete bridge method surface. Add new methods here as Phase 1 grows.
 * Keep parameter shapes loose (Record<string, unknown>) — Python normalises
 * with .get(...) so the JS side does not need to construct exact dicts.
 */
export interface BridgeApi {
  ping(params?: Record<string, unknown>): Promise<PingResult>;
  get_health(params?: Record<string, unknown>): Promise<HealthPayload>;
  get_app_status(params?: Record<string, unknown>): Promise<AppStatusPayload>;
  open_status_path(params: Record<string, unknown>): Promise<OpenStatusPathResult>;
  get_companies(params: Record<string, unknown>): Promise<CompanyDirectoryPage>;
  get_company_info(params: Record<string, unknown>): Promise<CompanyInfo>;
  get_company_years(params: Record<string, unknown>): Promise<CompanyYearsResult>;
  get_company_kpis(params: Record<string, unknown>): Promise<KPIBundle>;
  get_company_statement(params: Record<string, unknown>): Promise<StatementMatrix>;
  get_base_health(params: Record<string, unknown>): Promise<BaseHealthSnapshot>;
  request_refresh(params: Record<string, unknown>): Promise<RefreshDispatchResponse>;
  get_data_update_settings(params?: Record<string, unknown>): Promise<DataUpdateSettings>;
  save_data_update_settings(params: Record<string, unknown>): Promise<DataUpdateSettings>;
  get_company_universe_selection(params?: Record<string, unknown>): Promise<CompanyUniverseSelection & { error?: string }>;
  start_data_update(params: Record<string, unknown>): Promise<DataUpdateStartResponse>;
  reset_local_database(params: Record<string, unknown>): Promise<ResetLocalDatabaseResponse>;
  get_refresh_status(
    params?: Record<string, unknown>,
  ): Promise<RefreshJobStatus | RefreshJobListResponse | CompanyRefreshStatusListResponse>;
  cancel_refresh(params: Record<string, unknown>): Promise<CancelRefreshResponse>;
  get_onboarding_state(params?: Record<string, unknown>): Promise<OnboardingState>;
  start_onboarding_setup(params: Record<string, unknown>): Promise<OnboardingStartResponse>;
  complete_onboarding_setup(params?: Record<string, unknown>): Promise<OnboardingState>;
  skip_onboarding_setup(params?: Record<string, unknown>): Promise<OnboardingState>;
  get_database_diagnostics(params?: Record<string, unknown>): Promise<DatabaseDiagnostics>;
  get_data_coverage(params?: Record<string, unknown>): Promise<DataCoverageResponse>;
  set_company_ignored(params: Record<string, unknown>): Promise<SetCompanyIgnoredResponse>;
  get_company_filters(params?: Record<string, unknown>): Promise<CompanyFiltersResponse>;
  get_sectors(params?: Record<string, unknown>): Promise<SectorDirectoryResponse>;
  get_sector_detail(params: Record<string, unknown>): Promise<SectorDetailResponse>;
  export_company_excel(params: Record<string, unknown>): Promise<ExportCompanyResult>;
  get_output_dir(params?: Record<string, unknown>): Promise<OutputDirInfo>;
  get_sub_sector_detail(params: Record<string, unknown>): Promise<SectorDetailResponse>;
  check_update(params?: Record<string, unknown>): Promise<{ available: boolean; version?: string; zip_url?: string; error?: string }>;
  apply_update(params?: Record<string, unknown>): Promise<{ started: boolean; error?: string }>;
  get_update_progress(params?: Record<string, unknown>): Promise<UpdateProgressStatus>;
  snooze_update(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string }>;
  // Dev tools — only callable from /dev/data-ops (DEV build + flag)
  dev_reset_onboarding(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string }>;
  dev_reset_universe(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string }>;
  dev_reset_jobs(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string }>;
  dev_simulate_refresh(params: { mode: "success" | "partial" | "fail" | "slow" }): Promise<{ ok: boolean; mode: string; job_id?: string; error?: string }>;
  dev_start_small_setup(params?: { count?: number }): Promise<{ status: string; job_id?: string; message?: string }>;
  dev_get_raw_state(params?: Record<string, unknown>): Promise<{ app_settings?: Array<{ key: string; value: string | null; updated_at: string | null }>; refresh_jobs?: Array<Record<string, unknown>>; error?: string }>;
}

declare global {
  interface Window {
    pywebview?: {
      api: BridgeApi;
    };
  }
}

export {};
