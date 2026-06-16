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
  refresh_mode?: "manual_file" | "automatic_refresh" | string | null;
  refresh_id?: string | null;
  refresh_import_id?: string | null;
  refresh_total_files?: number | null;
  refresh_current_file_index?: number | null;
  refresh_current_file_name?: string | null;
  refresh_rows_inserted?: number | null;
  refresh_rows_skipped?: number | null;
  refresh_started_at?: string | null;
  refresh_updated_at?: string | null;
  refresh_finished_at?: string | null;
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
  owner_name?: string | null;
  owner_ticker?: string | null;
  is_custom_owner?: boolean;
  mapping_source?: string;
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
  owner?: {
    cd_cvm: number | null;
    owner_name: string;
    ticker_b3: string | null;
    is_custom: boolean;
    source: string;
  } | null;
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
  files?: PlantParcelManualImportFileParam[];
}

export interface PlantParcelManualImportFileParam {
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
