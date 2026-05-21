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
};

export type RefreshJobListResponse = {
  items: RefreshJobStatus[];
  error?: string;
};

export type CancelRefreshResponse = {
  ok: boolean;
  message?: string;
  error?: string;
};

export type PingResult = {
  pong: boolean;
  ts: number;
};

/**
 * Complete bridge method surface. Add new methods here as Phase 1 grows.
 * Keep parameter shapes loose (Record<string, unknown>) — Python normalises
 * with .get(...) so the JS side does not need to construct exact dicts.
 */
export interface BridgeApi {
  ping(params?: Record<string, unknown>): Promise<PingResult>;
  get_health(params?: Record<string, unknown>): Promise<HealthPayload>;
  get_companies(params: Record<string, unknown>): Promise<CompanyDirectoryPage>;
  get_company_info(params: Record<string, unknown>): Promise<CompanyInfo>;
  get_company_years(params: Record<string, unknown>): Promise<CompanyYearsResult>;
  get_company_kpis(params: Record<string, unknown>): Promise<KPIBundle>;
  get_company_statement(params: Record<string, unknown>): Promise<StatementMatrix>;
  get_base_health(params: Record<string, unknown>): Promise<BaseHealthSnapshot>;
  request_refresh(params: Record<string, unknown>): Promise<RefreshDispatchResponse>;
  get_refresh_status(params?: Record<string, unknown>): Promise<RefreshJobStatus | RefreshJobListResponse>;
  cancel_refresh(params: Record<string, unknown>): Promise<CancelRefreshResponse>;
}

declare global {
  interface Window {
    pywebview?: {
      api: BridgeApi;
    };
  }
}

export {};
