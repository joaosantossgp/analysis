// Company directory, financial statements, sectors, market history, and classification bridge types.

export type CompanyDataStatus = "no_history" | "partial" | "complete" | "failed" | "unmapped" | string;

export type CompanyDirectoryItem = {
  cd_cvm: number;
  company_name: string;
  ticker_b3: string | null;
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
  /** Canonical classification origin; null before the curated layer loads. */
  classification_origin?: ClassificationOrigin | null;
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
  sort_by?: "company" | "ticker" | "sector" | "industryGroup" | "marketCap" | "data" | "years" | "cvm";
  sort_direction?: "asc" | "desc";
};

export type CompanyInfo = {
  cd_cvm: number;
  company_name: string;
  nome_comercial: string | null;
  cnpj: string | null;
  ticker_b3: string | null;
  is_active: boolean;
  company_type: string | null;
  setor_cvm: string | null;
  sector_name?: string | null;
  sector_slug?: string | null;
  gics_sector?: string | null;
  gics_sector_slug?: string | null;
  gics_industry_group?: string | null;
  gics_industry?: string | null;
  gics_sub_industry?: string | null;
  /** Canonical classification with curation evidence; null before the curated layer loads. */
  classification?: CompanyClassification | null;
  /** B3 sector labels as published by B3, from the last explicit refresh; null if never fetched. */
  b3_classification?: B3Classification | null;
  has_local_financial_reports: boolean;
  has_readable_current_data: boolean;
  readable_years_count: number;
  latest_readable_year: number | null;
  readable_financial_periods_count: number;
  latest_financial_period_label: string | null;
  latest_financial_period_display: string | null;
  latest_financial_period_type: string | null;
  latest_financial_period_year: number | null;
  latest_financial_period_quarter: number | null;
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

export type CompanyFinancialPeriod = {
  period_label: string;
  period_display: string;
  period_type: string;
  period_year: number;
  period_quarter: number | null;
};

/**
 * Additive local financial-evidence contract from
 * CVMBridge.get_company_financial_readiness.
 *
 * The backend keeps unknown refresh values visible for auditability, so the
 * frontend must handle state strings outside the known vocabulary explicitly.
 */
export type CompanyFinancialReadiness = {
  cd_cvm: number;
  source_class: string;
  source_label: string;
  availability_state: "ready" | "partial" | "missing" | (string & {});
  freshness_state: "fresh" | "stale" | "unknown" | (string & {});
  refresh_state:
    | "not_recorded"
    | "successful"
    | "failed"
    | "in_progress"
    | "no_data"
    | (string & {});
  has_local_financial_reports: boolean;
  available_periods: CompanyFinancialPeriod[];
  local_read_model_updated_at: string | null;
  last_successful_refresh_at: string | null;
  latest_local_evidence_at: string | null;
  last_refresh_error: string | null;
  financial_export_eligible: boolean;
  exportable_years: number[];
  refresh_available: boolean;
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
  quality_evidence?: "available" | "partial" | "legacy_unknown";
  qa_events?: Array<{
    type?: string; cd_conta?: string; period?: string; year?: number;
    description?: string; unit?: string; missing_inputs?: string[];
    diff?: number; action?: string;
    source_inputs?: Array<{ observation_id?: string; evidence_status?: "missing"; SOURCE_FILE?: string; VERSAO?: string; DT_INI_EXERC?: string; DT_FIM_EXERC?: string; RAW_VL_CONTA?: string }>;
  }>;
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

/**
 * Per-year historical indicators for a single company (ROE, margins, price).
 * Mirrors `CVMBridge.get_company_historical_indicators`: success carries
 * `ok`/`cd_cvm`/`ticker_b3`/`yearly_data`; the failure path sets `error`.
 */
export interface CompanyHistoricalIndicatorsResult {
  ok: boolean;
  cd_cvm: number;
  ticker_b3: string | null;
  /** "local" from market_history; "missing" means no local prices (never fetched on view). */
  price_history_status?: "local" | "missing" | "no_ticker" | "unavailable";
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

export interface CompanyMarketHistoryStatus {
  cd_cvm: number;
  ticker: string | null;
  available_tickers: string[];
  has_local_data: boolean;
  first_date: string | null;
  last_date: string | null;
  row_count: number;
  last_downloaded_at: string | null;
  is_stale: boolean;
  warnings: string[];
  error?: string;
}

export interface CompanyMarketHistoryObservation {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  adjusted_close: number | null;
  volume: number | null;
  dividend: number;
  split_ratio: number;
  price_return_index: number | null;
  total_return_index: number | null;
  ttm_dividend_yield: number | null;
}

export interface CompanyMarketHistorySummary {
  initial_close: number | null;
  final_close: number | null;
  absolute_change: number | null;
  price_return: number | null;
  total_return: number | null;
  annualized_total_return: number | null;
  period_high: number | null;
  period_low: number | null;
  average_daily_volume: number | null;
  dividends_per_share: number | null;
  first_available_date: string | null;
  last_available_date: string | null;
}

export interface CompanyMarketHistoryResult {
  cd_cvm: number;
  ticker: string;
  source: string;
  provider_status: string;
  requested_start_date: string | null;
  requested_end_date: string | null;
  actual_start_date: string | null;
  actual_end_date: string | null;
  interval: string;
  last_downloaded_at: string | null;
  is_stale: boolean;
  has_local_data: boolean;
  warnings: string[];
  observations: CompanyMarketHistoryObservation[];
  summary: CompanyMarketHistorySummary | null;
  error?: string;
}

export interface CompanyMarketHistoryRefreshResult {
  ok: boolean;
  ticker: string;
  requested_start_date: string | null;
  requested_end_date: string | null;
  provider_date_range?: string | null;
  downloaded_rows: number;
  inserted_rows: number;
  updated_rows: number;
  unchanged_rows: number;
  rejected_rows: number;
  first_stored_date?: string | null;
  last_stored_date?: string | null;
  provider_warnings: string[];
  completion_timestamp: string;
  refresh_duration_seconds: number;
  error?: string;
}

export interface CompanyMarketHistoryAllRefreshResult {
  ok: boolean;
  cd_cvm: number;
  attempted_count: number;
  success_count: number;
  failure_count: number;
  results: CompanyMarketHistoryRefreshResult[];
  error?: string | null;
}

/** Where a company's canonical GICS classification comes from. */
export type ClassificationOrigin = "user" | "curated" | "unclassified" | "pending";

/** Canonical GICS classification curated by CVMAnalytics (never an official MSCI/S&P assignment). */
export interface CompanyClassification {
  origin: ClassificationOrigin;
  official: false;
  sub_industry_code?: string | null;
  sector_code?: string | null;
  industry_group_code?: string | null;
  industry_code?: string | null;
  unclassified_reason?: string | null;
  confidence?: "high" | "medium" | "low" | null;
  rationale?: string | null;
  evidence_url?: string | null;
  review_status?: string | null;
  gics_version?: string | null;
  gics_sub_industry_code?: string | null;
  /** Present when the analyst edited the classification locally. */
  user_edit?: {
    edited_at: string;
    curated_sub_industry_code: string | null;
    curated_sub_industry: string | null;
    curated_changed_since_edit: boolean;
  } | null;
}

/** One current GICS sub-industry with its full path. */
export interface GicsSubIndustry {
  sector_code: string;
  sector: string;
  industry_group_code: string;
  industry_group: string;
  industry_code: string;
  industry: string;
  sub_industry_code: string;
  sub_industry: string;
  gics_version: string;
}

/** B3 sector classification for one company, stored as published by B3. */
export interface B3Classification {
  b3_sector: string | null;
  b3_subsector: string | null;
  b3_segment: string | null;
  raw_classification: string | null;
  source_url: string;
  fetched_at: string;
  stale: boolean;
}

export interface B3RefreshRun {
  started_at: string;
  finished_at: string;
  requested: number;
  succeeded: number;
  not_listed: number;
  failed: number;
  errors: string[] | string | null;
}

export interface B3RefreshStatus {
  ok: boolean;
  error?: string;
  last_run: B3RefreshRun | null;
  stored_companies: number;
  stale: boolean;
  stale_after_days: number;
}
