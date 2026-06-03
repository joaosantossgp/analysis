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
  /** Market-cap enrichment from local snapshot. Null when company is not in the snapshot. */
  market_cap_brl?: number | null;
  market_cap_rank?: number | null;
  market_cap_as_of_date?: string | null;
  market_cap_source?: string | null;
  market_cap_provider_status?: string | null;
  dividend_yield?: number | null;
  pe_ratio?: number | null;
  pb_ratio?: number | null;
  beta?: number | null;
};

/** Present on CompanyDirectoryPage when the list was sorted by local market-cap snapshot. */
export type MarketCapSortMeta = {
  as_of_date: string;
  source: string;
  provider_status: string;
  mapped_count: number;
  total_in_snapshot: number;
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
  /** Present when the list is sorted by local market-cap snapshot. */
  market_cap_sort_meta?: MarketCapSortMeta | null;
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

export type MarketCapEntry = {
  as_of_date: string;
  rank: number;
  cd_cvm: number | null;
  cnpj: string | null;
  company_name: string;
  ticker: string | null;
  market_cap_brl: number;
  source: string;
  method: string;
  source_url_or_id: string;
  downloaded_at: string;
  mapping_status: string;
  mapping_confidence: number;
  notes?: string | null;
};

export type MarketCapStatus = {
  available: boolean;
  row_count: number;
  as_of_date?: string | null;
  downloaded_at?: string | null;
  source?: string | null;
  method?: string | null;
  source_url_or_id?: string | null;
  mapped_count?: number;
  unmapped_count?: number;
  unmapped_identifiers?: string[];
  warnings: string[];
  error?: string;
};

export type MarketCapImportResponse = {
  ok: boolean;
  error?: string;
  status?: MarketCapStatus;
};

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

export type ExcelMappingSource = {
  statement_type: string;
  line_id_base: string;
  cd_conta: string | null;
  label_snapshot: string | null;
  sign: number;
  position: number;
};

export type ExcelMappingEntry = {
  target_id: string;
  target_label: string;
  group: string;
  statement_type: string;
  display_order: number;
  indent_level: number;
  required: boolean;
  operation: "direct" | "sum" | "sum_with_sign" | string;
  is_subtotal: boolean;
  sources: ExcelMappingSource[];
};

export type ExcelMappingDefinition = {
  preset_id: string;
  name: string;
  description: string | null;
  origin: "system" | "user" | string;
  default_mapping_version: string;
  sector_tags: string[];
  notes: string | null;
  validation_status: string | null;
  created_at: string | null;
  updated_at: string | null;
  entries: ExcelMappingEntry[];
};

export type ExcelMappingPresetSummary = {
  preset_id: string;
  name: string;
  description: string | null;
  origin: "system" | "user" | string;
  default_mapping_version: string;
  sector_tags: string[];
  notes: string | null;
  validation_status: string | null;
  created_at: string | null;
  updated_at: string | null;
  company_default: boolean;
};

export type ExcelMappingRawLine = {
  statement_type: string;
  line_id_base: string;
  cd_conta: string | null;
  ds_conta: string | null;
  standard_name: string | null;
  label: string;
  normalized_label: string;
  periods_present: string[];
  sample_values_by_period?: Record<string, number | null>;
  mapped_targets?: Array<{ target_id: string; target_label: string; group: string }>;
};

export type ExcelMappingPreviewRow = {
  target_id: string;
  target_label: string;
  group: string;
  statement_type: string;
  display_order: number;
  indent_level: number;
  required: boolean;
  operation: "direct" | "sum" | "sum_with_sign" | string;
  is_subtotal: boolean;
  source_count: number;
  warning_count: number;
  error_count: number;
  values_by_period: Record<string, number | null>;
};

export type ExcelMappingValidationIssue = {
  severity: "error" | "warning" | string;
  code: string;
  message: string;
  target_id: string | null;
  source_id: string | null;
};

export type ExcelMappingWorkspace = {
  ok: boolean;
  company: CompanyInfo;
  presets: ExcelMappingPresetSummary[];
  active_preset_id: string;
  company_default_preset_id: string;
  mapping: ExcelMappingDefinition;
  preview_periods: string[];
  model_preview_rows: ExcelMappingPreviewRow[];
  raw_lines: ExcelMappingRawLine[];
  validation: ExcelMappingValidationIssue[];
  error?: string;
};

export type SaveExcelMappingPresetResult = {
  ok: boolean;
  preset?: ExcelMappingDefinition;
  presets?: ExcelMappingPresetSummary[];
  error?: string;
};

export type SetCompanyExcelMappingDefaultResult = {
  ok: boolean;
  cd_cvm?: number;
  preset_id?: string;
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
 * Per-year historical indicators for a single company (ROE, margins, price).
 * Mirrors `CVMBridge.get_company_historical_indicators`: success carries
 * `ok`/`cd_cvm`/`ticker_b3`/`yearly_data`; the failure path sets `error`.
 */
export interface CompanyHistoricalIndicatorsResult {
  ok: boolean;
  cd_cvm: number;
  ticker_b3: string | null;
  yearly_data: Array<{
    year: number;
    roe: number | null;
    mg_ebit: number | null;
    mg_liq: number | null;
    stock_price: number | null;
  }>;
  /** Present only when the bridge call failed. */
  error?: string;
}

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
  get_company_historical_indicators(
    params: Record<string, unknown>,
  ): Promise<CompanyHistoricalIndicatorsResult>;
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
  get_market_cap_list(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string; items: MarketCapEntry[] }>;
  import_market_cap_snapshot(params: { csv_content?: string; file_path?: string }): Promise<MarketCapImportResponse>;
  get_market_cap_status(params?: Record<string, unknown>): Promise<MarketCapStatus>;
  fetch_latest_market_cap(params?: Record<string, unknown>): Promise<MarketCapImportResponse>;
  get_database_diagnostics(params?: Record<string, unknown>): Promise<DatabaseDiagnostics>;
  get_data_coverage(params?: Record<string, unknown>): Promise<DataCoverageResponse>;
  set_company_ignored(params: Record<string, unknown>): Promise<SetCompanyIgnoredResponse>;
  get_company_filters(params?: Record<string, unknown>): Promise<CompanyFiltersResponse>;
  get_sectors(params?: Record<string, unknown>): Promise<SectorDirectoryResponse>;
  get_sector_detail(params: Record<string, unknown>): Promise<SectorDetailResponse>;
  export_company_excel(params: Record<string, unknown>): Promise<ExportCompanyResult>;
  get_output_dir(params?: Record<string, unknown>): Promise<OutputDirInfo>;
  get_excel_mapping_workspace(params: Record<string, unknown>): Promise<ExcelMappingWorkspace>;
  save_excel_mapping_preset(params: Record<string, unknown>): Promise<SaveExcelMappingPresetResult>;
  set_company_excel_mapping_default(
    params: Record<string, unknown>,
  ): Promise<SetCompanyExcelMappingDefaultResult>;
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
  // Energy KPI — country-level macro layer
  get_kpi_catalog(params?: EnergyKPICatalogParams): Promise<EnergyKPICatalogResponse>;
  get_country_kpi_series(params: CountryKPISeriesParams): Promise<CountryKPISeriesResponse>;
  get_country_kpi_compare(params: CountryKPICompareParams): Promise<CountryKPICompareResponse>;
  get_energy_kpi_health(params?: Record<string, unknown>): Promise<EnergyKPIHealthResponse>;
  refresh_energy_kpis(params?: { triggered_by?: string }): Promise<EnergyKPIRefreshResult>;
  export_country_kpis_excel(params?: { iso_codes?: string[]; kpi_ids?: string[] }): Promise<{ path: string | null; error?: string }>;
  get_sin_kpi_dashboard(params?: Record<string, unknown>): Promise<SINKPIDashboardResponse>;
  get_sin_kpi_series(params?: SINKPISeriesParams): Promise<SINKPISeriesResponse>;
  get_sin_kpi_health(params?: Record<string, unknown>): Promise<SINKPIHealthResponse>;
  refresh_sin_kpis(params?: SINKPIRefreshParams): Promise<SINKPIRefreshResult>;
  get_plant_parcel_source_statuses(params?: Record<string, unknown>): Promise<PlantParcelSourceStatusResponse>;
  get_plant_parcel_catalog(params?: PlantParcelCatalogParams): Promise<PlantParcelCatalogResponse>;
  get_plant_parcel_detail(params: PlantParcelDetailParams): Promise<PlantParcelDetailResponse>;
  get_plant_parcel_chart_data(params: PlantParcelChartDataParams): Promise<PlantParcelChartDataResponse>;
  refresh_plant_parcel_source(params: PlantParcelRefreshParams): Promise<PlantParcelRefreshResult>;
  select_plant_parcel_import_file(params: PlantParcelFilePickerParams): Promise<PlantParcelFilePickerResult>;
  import_plant_parcel_source_file(params: PlantParcelManualImportParams): Promise<PlantParcelManualImportResult>;
}

// ── Energy KPI types ──────────────────────────────────────────────────────────

export interface KPICatalogEntry {
  kpi_id: string;
  display_name: string;
  description: string;
  kpi_type: string;
  macro_category: string;
  subsector: string;
  unit: string;
  primary_source: string;
  calculation_method: string;
  v1_status: "v1_required" | "v1_optional" | "blocked_by_source_verification";
  dashboard_priority: "lead" | "secondary" | "detail_only" | "not_in_v1_dashboard";
  excel_export_priority: "required" | "optional" | "none";
  source_verification_status: "verified" | "pending" | "blocked";
  higher_is_better: boolean | null;
  source_caveats: string;
  audit_notes: string;
}

export interface CountryKPIValue {
  kpi_id: string;
  iso_code: string;
  country_name: string;
  period: number;
  value: number | null;
  unit: string;
  source: string;
  source_priority: number;
  source_field: string;
  data_quality_status: "ok" | "conflict" | "fallback_used" | "stale" | "missing";
  source_conflict: boolean;
  fallback_used: boolean;
  snapshot_id: string;
  value_owid: number | null;
  value_ember: number | null;
}

export interface EnergyKPIHealthResponse {
  last_refresh_at: string | null;
  last_refresh_status: string | null;
  rows_ingested: number;
  rows_conflict: number;
  is_stale: boolean;
  owid_snapshot_id: string | null;
  owid_fetched_at: string | null;
  dq_errors: number;
  dq_warnings: number;
  refresh_running: boolean;
  refresh_error: string | null;
  error?: string;
}

export interface EnergyKPICatalogParams {
  sector?: string;
  v1_status?: string;
  dashboard_priority?: string;
  excel_export_priority?: string;
  macro_category?: string;
  source_verification_status?: string;
}

export interface EnergyKPICatalogResponse {
  entries: KPICatalogEntry[];
  count: number;
  error?: string;
}

export interface CountryKPISeriesParams {
  kpi_ids?: string[];
  iso_codes?: string[];
  years?: number[];
}

export interface CountryKPISeriesResponse {
  values: CountryKPIValue[];
  count: number;
  error?: string;
}

export interface CountryKPICompareParams {
  kpi_id: string;
  year: number;
}

export interface CountryKPICompareResponse {
  kpi_id: string;
  year: number;
  values: CountryKPIValue[];
  error?: string;
}

export interface EnergyKPIRefreshResult {
  status: "started" | "already_running" | "success" | "error";
  error: string | null;
  run_id?: string;
  rows_ingested?: number;
}

export interface SINKPIObservation {
  kpi_id: string;
  subsystem_code: "S" | "SE_CO" | "NE" | "N" | string;
  subsystem_name: string;
  reference_datetime: string;
  value: number | null;
  unit: string;
  source: string;
  source_dataset: string;
  source_field: string;
  data_quality_status: "ok" | "missing" | "stale" | "conflict" | "fallback_used" | string;
  snapshot_id: string;
}

export interface SINKPISourceStatus {
  source: string;
  dataset: string;
  frequency: string;
  last_snapshot_at: string | null;
  local_records_count: number;
  last_status: string | null;
  last_error: string | null;
}

export interface SINKPIDashboardResponse {
  last_successful_update: string | null;
  latest_reference_datetime: string | null;
  is_empty: boolean;
  is_stale: boolean;
  observations: SINKPIObservation[];
  source_statuses: SINKPISourceStatus[];
  refresh_running: boolean;
  refresh_error: string | null;
  error?: string;
}

export interface SINKPISeriesParams {
  kpi_ids?: string[];
  subsystem_codes?: string[];
  start_datetime?: string;
  end_datetime?: string;
  limit?: number;
}

export interface SINKPISeriesResponse {
  values: SINKPIObservation[];
  count: number;
  error?: string;
}

export interface SINKPIHealthResponse {
  last_refresh_at: string | null;
  last_refresh_status: string | null;
  rows_ingested: number;
  latest_reference_datetime: string | null;
  is_stale: boolean;
  dq_errors: number;
  dq_warnings: number;
  refresh_running: boolean;
  refresh_error: string | null;
  error?: string;
}

export interface SINKPIRefreshParams {
  triggered_by?: string;
  years?: number[];
  include_ccee?: boolean;
}

export interface SINKPIRefreshResult {
  status: "started" | "already_running" | "success" | "partial" | "error";
  error: string | null;
  run_id?: string;
  rows_inserted?: number;
  rows_read?: number;
  snapshots?: number;
}

export interface PlantParcelSourceStatus {
  source_id: "ccee_plant_parcel_monthly" | "ccee_plant_generation_hourly" | "aneel_siga_plants" | string;
  source_name: string;
  dataset_name: string;
  provider: string;
  official_url: string | null;
  refresh_frequency: string | null;
  granularity: string | null;
  description: string | null;
  known_caveats: string | null;
  local_records_count: number;
  latest_reference: string | null;
  last_refresh_at: string | null;
  last_status: "running" | "success" | "partial" | "error" | string | null;
  last_error: string | null;
  last_warning?: string | null;
  last_requested_period?: string | null;
  last_period_start?: string | null;
  last_period_end?: string | null;
  last_source_url?: string | null;
  last_local_file_path?: string | null;
  last_checksum?: string | null;
  last_downloaded_bytes?: number | null;
  last_source_rows?: number | null;
  last_parsed_rows?: number | null;
  last_normalized_rows?: number | null;
  last_rows_inserted?: number | null;
  last_rows_updated?: number | null;
  last_rows_skipped?: number | null;
  last_detected_encoding?: string | null;
  last_import_mode?: "automatic_refresh" | "manual_file" | string | null;
  last_original_file_name?: string | null;
  last_file_size_bytes?: number | null;
  last_file_hash?: string | null;
  last_file_type?: string | null;
  last_detected_period?: string | null;
  last_manual_import_at?: string | null;
  last_manual_status?: string | null;
  last_manual_error?: string | null;
  last_manual_warning?: string | null;
  last_manual_file_name?: string | null;
  last_manual_file_size_bytes?: number | null;
  last_manual_file_hash?: string | null;
  last_manual_file_type?: string | null;
  last_manual_detected_period?: string | null;
  last_manual_rows_inserted?: number | null;
  last_manual_rows_skipped?: number | null;
  source_page_url?: string | null;
  refresh_id: string | null;
  cache_status: "never_refreshed" | "missing" | "fresh" | "stale" | "failed" | "warning" | "cached" | string;
}

export interface PlantParcelSourceStatusResponse {
  source_statuses: PlantParcelSourceStatus[];
  count: number;
  refresh_running: boolean;
  refresh_status?: "running" | "success" | "warning" | "failed" | string | null;
  refresh_error: string | null;
  refresh_warning?: string | null;
  refresh_source_id: string | null;
  database_path?: string;
  raw_data_dir?: string;
  error?: string;
}

export interface PlantParcelCatalogRecord {
  entity_type: "ccee_plant_parcel" | "aneel_plant" | string;
  entity_id: string;
  plant_parcel_code: string | null;
  plant_parcel_acronym: string | null;
  ceg: string | null;
  plant_name: string | null;
  agent_name: string | null;
  generation_source: string | null;
  submarket: string | null;
  uf: string | null;
  phase: string | null;
  capacity_mw: number | null;
  authorized_capacity_mw: number | null;
  inspected_capacity_mw: number | null;
  physical_guarantee_mwmed: number | null;
  physical_guarantee_mw: number | null;
  latest_reference_month: string | null;
  latest_generation_mwmed: number | null;
  data_status: "cached" | "missing" | "registry_only" | string;
}

export interface PlantParcelCatalogParams {
  search?: string;
  entity_type?: string;
  generation_source?: string;
  submarket?: string;
  uf?: string;
  limit?: number;
  offset?: number;
}

export interface PlantParcelCatalogResponse {
  records: PlantParcelCatalogRecord[];
  count: number;
  total: number;
  limit: number;
  offset: number;
  facets?: Record<string, string[]>;
  error?: string;
}

export interface PlantMetric {
  metric_id: string;
  label: string;
  value: number;
  unit: string;
  source_id: string;
  source: string;
  dataset: string;
  reference_period: string | null;
  local_refresh_timestamp: string | null;
  raw_or_derived: "raw" | "derived" | string;
  methodology: string;
}

export interface PlantParcelDetailParams {
  entity_id: string;
  entity_type?: string;
}

export interface PlantParcelDetailResponse {
  entity_type: "ccee_plant_parcel" | "aneel_plant" | string;
  entity_id: string;
  parcel: Record<string, unknown> | null;
  aneel_plant: Record<string, unknown> | null;
  related_parcels: Array<Record<string, unknown>>;
  metrics: PlantMetric[];
  monthly_series: Array<Record<string, unknown>>;
  hourly_preview: Array<Record<string, unknown>>;
  metadata: {
    caveats: string[];
    latest_refresh_by_source: Record<string, Record<string, unknown>>;
  };
  error?: string;
}

export interface PlantParcelRefreshParams {
  source_id: string;
  triggered_by?: string;
  year?: number;
  year_month?: string;
  use_daily_aneel?: boolean;
}

export interface PlantParcelRefreshResult {
  status: "started" | "already_running" | "success" | "partial" | "warning" | "failed" | "error";
  error: string | null;
  warning?: string | null;
  source_id?: string;
  refresh_id?: string;
  rows_inserted?: number;
  rows_read?: number;
  source_rows?: number;
  parsed_rows?: number;
  normalized_rows?: number;
  rows_skipped?: number;
  downloaded_bytes?: number | null;
  requested_period?: string | null;
  dataset?: string | null;
  source_url?: string | null;
  detected_encoding?: string | null;
  rows_updated?: number;
  period_start?: string | null;
  period_end?: string | null;
}

export interface PlantParcelFilePickerParams {
  source_id: string;
}

export interface PlantParcelFilePickerResult {
  ok: boolean;
  canceled?: boolean;
  file_path?: string | null;
  file_name?: string | null;
  file_paths?: string[];
  file_names?: string[];
  error?: string | null;
}

export interface PlantParcelManualImportParams {
  source_id: string;
  triggered_by?: string;
  expected_period?: string | null;
  file_path?: string;
  file_content_base64?: string;
  original_file_name?: string;
}

export interface PlantParcelManualImportResult extends PlantParcelRefreshResult {
  import_id?: string;
  import_mode?: "manual_file" | string;
  file_size_bytes?: number | null;
  file_hash?: string | null;
  file_type?: string | null;
  original_file_name?: string | null;
  detected_period?: string | null;
  source_page_url?: string | null;
}

export interface PlantParcelChartDataParams {
  entity_id: string;
  entity_type?: string;
  frequency: "monthly" | "daily" | "hourly";
  year_month?: string;
}

export interface PlantParcelChartSeries {
  id: string;
  label: string;
  unit: string;
  axis: "left" | "right";
  type: "line" | "bar";
  color?: string;
  points: Array<number | null>;
  latest: number | null;
}

export interface PlantParcelChartDataResponse {
  series: PlantParcelChartSeries[];
  periods: string[];
  frequency: string;
  entity_type: string;
  entity_id: string;
  error?: string;
}

declare global {
  interface Window {
    pywebview?: {
      api: BridgeApi;
    };
  }
}

export {};
