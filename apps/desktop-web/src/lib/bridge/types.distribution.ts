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
  error?: string;
}
