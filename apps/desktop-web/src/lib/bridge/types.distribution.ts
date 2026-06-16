export interface DistributorEntry {
  distributor_id: string;
  canonical_name: string;
  trade_name: string;
  normalized_cnpj: string | null;
  agent_code: string | null;
  concession_type: string | null;
  primary_uf: string | null;
  status: string;
  economic_group_id: string | null;
  group_name: string | null;
  cd_cvm: number | null;
  company_name: string | null;
  ticker_b3: string | null;
}

export interface DistributorDetail {
  identity: {
    distributor_id: string;
    canonical_name: string;
    legal_name: string | null;
    trade_name: string;
    normalized_cnpj: string | null;
    agent_code: string | null;
    distributor_code: string | null;
    concession_type: string | null;
    primary_uf: string | null;
    service_area: string | null;
    status: string;
  };
  ownership_history: Array<{
    ownership_id: string;
    valid_from: string;
    valid_to: string;
    control_status: string;
    ownership_percentage: number | null;
    operational_consolidation_flag: number;
    economic_group_id: string | null;
    group_name: string | null;
    cd_cvm: number | null;
    company_name: string | null;
    ticker_b3: string | null;
  }>;
  available_periods: string[];
}

export interface DistributionSeriesEntry {
  period: string;
  billed_energy_mwh: number | null;
  revenue_brl: number | null;
  measured_energy_mwh: number | null;
  injected_energy_mwh: number | null;
  losses_mwh: number | null;
  losses_pct: number | null;
  dec_actual: number | null;
  fec_actual: number | null;
  dec_limit: number | null;
  fec_limit: number | null;
  compensation_count: number | null;
  compensation_value: number | null;
  delinquency_pct: number | null;
  mmgd_projects_count: number | null;
  mmgd_capacity_kw: number | null;
  te_homologated: number | null;
  tusd_homologated: number | null;
}

export interface DistributionRefreshStatus {
  status: "idle" | "running" | "success" | "error";
  error: string | null;
  stage: string;
  message: string;
  progress_current: number;
  progress_total: number;
  supported_years?: number[];
  ingested_years?: number[];
}

export interface EconomicGroupEntry {
  economic_group_id: string;
  group_name: string;
  cd_cvm: number | null;
  company_name: string | null;
  ticker_b3: string | null;
  distributors_count: number;
}

export interface EconomicGroupDetail {
  identity: {
    economic_group_id: string;
    group_name: string;
    cd_cvm: number | null;
    company_name: string | null;
    ticker_b3: string | null;
  };
  portfolio: Array<{
    ownership_id: string;
    distributor_id: string;
    canonical_name: string;
    trade_name: string;
    valid_from: string;
    valid_to: string;
    control_status: string;
    ownership_percentage: number | null;
    operational_consolidation_flag: number;
  }>;
  available_periods: string[];
}

export interface DistributionRefreshLogEntry {
  refresh_id: string;
  source_id: string;
  dataset_name: string | null;
  started_at: string;
  finished_at: string | null;
  status: string;
  rows_inserted: number | null;
  rows_updated: number | null;
  rows_unchanged: number | null;
  error_message: string | null;
  warning_message: string | null;
  source_rows: number | null;
  parsed_rows: number | null;
  canonical_rows: number | null;
  final_published_rows: number | null;
  elapsed_download_ms: number | null;
  elapsed_parse_ms: number | null;
  elapsed_publish_ms: number | null;
  elapsed_aggregate_ms: number | null;
  elapsed_lock_wait_ms: number | null;
  peak_rss_mb: number | null;
  cpu_time_ms: number | null;
  unresolved_identity_rows: number | null;
  conflict_rows: number | null;
  rejected_rows: number | null;
  snapshot_id: string | null;
}

export interface DistributionHealthResponse {
  counts: {
    market: number;
    balance: number;
    continuity: number;
    tariffs: number;
    delinquency: number;
    mmgd: number;
  };
  snapshots: Array<{
    snapshot_id: string;
    source: string;
    fetched_at: string;
    sha256: string | null;
    row_count: number | null;
    status: string;
  }>;
  refresh_logs?: DistributionRefreshLogEntry[];
  error?: string;
}

export interface ConglomerateEntry {
  cd_cvm: number;
  company_name: string;
  ticker_b3: string | null;
  cnpj: string | null;
  setor_cvm: string | null;
  gics_sector: string | null;
  distributors_count: number;
  plants_count: number;
  total_capacity_mw: number;
  total_generation_mwmed: number;
}

export interface AssetMappingEntry {
  id: string;
  type: "distributor" | "plant";
  name: string;
  sub_name: string;
  mapped_cvm: number | null;
  company_name: string;
  ticker: string;
  mapping_source: "auto" | "manual" | "unmapped";
  review_notes: string | null;
  stats: string;
}
