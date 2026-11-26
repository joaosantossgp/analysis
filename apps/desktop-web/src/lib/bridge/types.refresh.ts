// Refresh jobs, data updates, company universe, market cap, and onboarding bridge types.

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
  action: "recreate_local" | string;
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
