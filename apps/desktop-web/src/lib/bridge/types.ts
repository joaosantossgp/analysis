import type { LocalDatabaseState } from "./types.localDatabase";
import type { DevAutoRestartResponse, DevContextResponse, DevRestartResponse } from "./types.dev";
import type {
  EnergyKPIHealthResponse,
  EnergyKPICatalogParams,
  EnergyKPICatalogResponse,
  CountryKPISeriesParams,
  CountryKPISeriesResponse,
  CountryKPICompareParams,
  CountryKPICompareResponse,
  EnergyKPIRefreshResult,
  SINKPIDashboardResponse,
  SINKPISeriesParams,
  SINKPISeriesResponse,
  SINKPIDailyChartSeriesParams,
  SINKPIDailyChartSeriesResponse,
  SINKPIHealthResponse,
  SINKPIRefreshParams,
  SINKPIRefreshResult,
  PlantParcelSourceStatusResponse,
  PlantParcelCatalogParams,
  PlantParcelCatalogResponse,
  PlantParcelDetailParams,
  PlantParcelDetailResponse,
  PlantParcelRefreshParams,
  PlantParcelRefreshResult,
  PlantParcelFilePickerParams,
  PlantParcelFilePickerResult,
  PlantParcelManualImportParams,
  PlantParcelManualImportResult,
  PlantParcelChartDataParams,
  PlantParcelChartDataResponse,
  FuelDistributionProductYearSummaryParams,
  FuelDistributionProductYearSummaryResponse,
  FuelDistributionStateMonthSeriesParams,
  FuelDistributionStateMonthSeriesResponse,
  FuelDistributionDetailParams,
  FuelDistributionDetailResponse,
  EnergyMartStatusResponse,
  EnergyMartRebuildState,
  StartEnergyMartRebuildParams
} from "./types.energy";

import type {
  DistributorEntry,
  DistributorDetail,
  DistributionSeriesEntry,
  DistributionMmgdProjectsResponse,
  MmgdProjectEntry,
  DistributionRefreshStatus,
  EconomicGroupEntry,
  EconomicGroupDetail,
  DistributionHealthResponse,
  ConglomerateEntry,
  AssetMappingEntry,
  CvmRegistryEntry
} from "./types.distribution";

import type {
  AddCustomNewsSourceParams,
  AddCustomNewsSourceResult,
  BackfillNewsArticleContentParams,
  BackfillNewsArticleContentResult,
  ApplyNewsClassificationCorrectionParams,
  ApplyNewsClassificationCorrectionResult,
  NewsArticleClassificationResponse,
  NewsArticleContentResponse,
  UpdateNewsArticleStateParams,
  UpdateNewsArticleStateResult,
  NewsArticlesParams,
  NewsArticlesResponse,
  NewsCompanyScopeResponse,
  NewsCollectionRunsResponse,
  NewsGoogleCompanyFeedSettings,
  NewsOverviewParams,
  NewsOverviewResponse,
  NewsRefreshStatus,
  NewsRetentionStatus,
  NewsSourceMutationResult,
  NewsSourcesResponse,
  SaveNewsGoogleCompanyFeedSettingsParams,
  SaveNewsGoogleCompanyFeedSettingsResult,
  SaveNewsRetentionPolicyParams,
  SaveNewsRetentionPolicyResult,
  CleanupNewsExtractedContentResult,
  SetNewsCompanyScopeOverrideParams,
  SetNewsCompanyScopeOverrideResult,
  SetNewsCompanyScopeUniverseParams,
  SetNewsCompanyScopeUniverseResult
} from "./types.news";

export type {
  DistributorEntry,
  DistributorDetail,
  DistributionSeriesEntry,
  DistributionMmgdProjectsResponse,
  MmgdProjectEntry,
  DistributionRefreshStatus,
  EconomicGroupEntry,
  EconomicGroupDetail,
  DistributionHealthResponse,
  ConglomerateEntry,
  AssetMappingEntry,
  CvmRegistryEntry
};

export type {
  AddCustomNewsSourceParams,
  AddCustomNewsSourceResult,
  BackfillNewsArticleContentParams,
  BackfillNewsArticleContentResult,
  ApplyNewsClassificationCorrectionParams,
  ApplyNewsClassificationCorrectionResult,
  NewsArticle,
  NewsArticleClassificationResponse,
  NewsArticleContentResponse,
  NewsArticleState,
  NewsArticlesParams,
  NewsArticlesResponse,
  NewsCompanyScopeOverride,
  NewsCompanyScopeResponse,
  NewsCollectionRun,
  NewsCollectionRunsResponse,
  NewsGoogleCompanyFeedSettings,
  NewsOverviewParams,
  NewsOverviewResponse,
  NewsOverviewSection,
  NewsRefreshSourceResult,
  NewsRefreshStatus,
  NewsRetentionPolicy,
  NewsRetentionStatus,
  NewsSource,
  NewsSourceMutationResult,
  NewsSourcesResponse,
  SaveNewsRetentionPolicyParams,
  SaveNewsRetentionPolicyResult,
  SaveNewsGoogleCompanyFeedSettingsParams,
  SaveNewsGoogleCompanyFeedSettingsResult,
  CleanupNewsExtractedContentResult,
  SetNewsCompanyScopeOverrideParams,
  SetNewsCompanyScopeOverrideResult,
  SetNewsCompanyScopeUniverseParams,
  SetNewsCompanyScopeUniverseResult,
  UpdateNewsArticleStateParams,
  UpdateNewsArticleStateResult
} from "./types.news";

export type {
  KPICatalogEntry,
  CountryKPIValue,
  EnergyKPIHealthResponse,
  EnergyKPICatalogParams,
  EnergyKPICatalogResponse,
  CountryKPISeriesParams,
  CountryKPISeriesResponse,
  CountryKPICompareParams,
  CountryKPICompareResponse,
  EnergyKPIRefreshResult,
  SINKPIObservation,
  SINKPISourceStatus,
  SINKPIDashboardResponse,
  SINKPISeriesParams,
  SINKPISeriesResponse,
  SINKPIDailyChartRawDrilldown,
  SINKPIDailyChartObservation,
  SINKPIDailyChartSeriesParams,
  SINKPIDailyChartSeriesResponse,
  SINKPIHealthResponse,
  SINKPIRefreshParams,
  SINKPIRefreshResult,
  PlantParcelSourceStatus,
  PlantParcelSourceStatusResponse,
  PlantParcelCatalogRecord,
  PlantParcelCatalogParams,
  PlantParcelCatalogResponse,
  PlantMetric,
  PlantParcelDetailParams,
  PlantParcelDetailResponse,
  PlantParcelRefreshParams,
  PlantParcelRefreshResult,
  PlantParcelFilePickerParams,
  PlantParcelFilePickerResult,
  PlantParcelManualImportParams,
  PlantParcelManualImportFileParam,
  PlantParcelManualImportResult,
  PlantParcelChartDataParams,
  PlantParcelChartSeries,
  PlantParcelChartDataResponse,
  FuelDistributionProductYearSummaryParams,
  FuelDistributionProductYearSummaryItem,
  FuelDistributionProductYearSummaryResponse,
  FuelDistributionStateMonthSeriesParams,
  FuelDistributionStateMonthSeriesItem,
  FuelDistributionStateMonthSeriesResponse,
  FuelDistributionDetailParams,
  FuelDistributionDetailResponse,
  EnergyMartBuildStatus,
  EnergyMartRebuildState,
  EnergyMartStatusResponse,
  StartEnergyMartRebuildParams
} from "./types.energy";

import type {
  B3RefreshRun,
  B3RefreshStatus,
  CompanyClassification,
  CompanyDirectoryPage,
  CompanyFiltersResponse,
  CompanyFinancialReadiness,
  CompanyHistoricalIndicatorsResult,
  CompanyInfo,
  CompanyMarketHistoryAllRefreshResult,
  CompanyMarketHistoryRefreshResult,
  CompanyMarketHistoryResult,
  CompanyMarketHistoryStatus,
  CompanyYearsResult,
  GicsSubIndustry,
  KPIBundle,
  SectorDetailResponse,
  SectorDirectoryResponse,
  StatementMatrix,
} from "./types.companies";

import type {
  BaseHealthSnapshot,
  CancelRefreshResponse,
  CompanyRefreshStatusListResponse,
  CompanyUniverseSelection,
  DataUpdateSettings,
  DataUpdateStartResponse,
  MarketCapEntry,
  MarketCapImportResponse,
  MarketCapStatus,
  RefreshDispatchResponse,
  RefreshJobListResponse,
  RefreshJobStatus,
  ResetLocalDatabaseResponse,
} from "./types.refresh";

import type {
  ExcelMappingWorkspace,
  ExportCompanyResult,
  ExportMarketHistoryResult,
  OpenCompanyExcelMappingWindowResult,
  OutputDirInfo,
  SaveExcelMappingPresetResult,
  SetCompanyExcelMappingDefaultResult,
} from "./types.excel";

import type {
  AppStatusPayload,
  DataCoverageResponse,
  DatabaseDiagnostics,
  HealthPayload,
  OpenStatusPathResult,
  PingResult,
  SetCompanyIgnoredResponse,
  SettingsHealthSummary,
  StartStorageInventoryScanResult,
  StorageInventory,
  StorageScanStatus,
  UpdateProgressStatus,
} from "./types.status";

export type * from "./types.companies";

export type * from "./types.refresh";

export type * from "./types.excel";

export type * from "./types.status";

// Mirror of the Python bridge surface in desktop/bridge.py.
// Domain payload shapes live in ./types.<domain>.ts and are re-exported above.
// Components MUST NOT reference window.pywebview directly — use ./adapter.ts.

/**
 * Complete bridge method surface. Add new methods here as Phase 1 grows.
 * Keep parameter shapes loose (Record<string, unknown>) — Python normalises
 * with .get(...) so the JS side does not need to construct exact dicts.
 */
export interface BridgeApi {
  ping(params?: Record<string, unknown>): Promise<PingResult>;
  get_health(params?: Record<string, unknown>): Promise<HealthPayload>;
  get_app_status(params?: Record<string, unknown>): Promise<AppStatusPayload>;
  get_settings_health_summary(params?: Record<string, unknown>): Promise<SettingsHealthSummary>;
  get_storage_inventory(params?: Record<string, unknown>): Promise<StorageInventory>;
  start_storage_inventory_scan(params?: Record<string, unknown>): Promise<StartStorageInventoryScanResult>;
  get_storage_inventory_scan_status(params?: Record<string, unknown>): Promise<StorageScanStatus>;
  open_status_path(params: Record<string, unknown>): Promise<OpenStatusPathResult>;
  get_news_articles(params?: NewsArticlesParams): Promise<NewsArticlesResponse>;
  get_news_overview(params?: NewsOverviewParams): Promise<NewsOverviewResponse>;
  get_news_company_scope(params?: Record<string, unknown>): Promise<NewsCompanyScopeResponse>;
  get_news_google_company_feed_settings(params?: Record<string, unknown>): Promise<NewsGoogleCompanyFeedSettings>;
  get_news_retention_status(params?: Record<string, unknown>): Promise<NewsRetentionStatus>;
  get_news_article_classification(params: { article_id: string }): Promise<NewsArticleClassificationResponse>;
  get_news_article_content(params: { article_id: string }): Promise<NewsArticleContentResponse>;
  get_news_sources(params?: Record<string, unknown>): Promise<NewsSourcesResponse>;
  get_news_collection_runs(params?: { limit?: number }): Promise<NewsCollectionRunsResponse>;
  get_news_refresh_status(params?: Record<string, unknown>): Promise<NewsRefreshStatus>;
  refresh_news_sources(params?: Record<string, unknown>): Promise<NewsRefreshStatus>;
  set_news_source_enabled(params: { source_id: string; enabled: boolean }): Promise<NewsSourceMutationResult>;
  set_news_source_priority(params: { source_id: string; priority: number }): Promise<NewsSourceMutationResult>;
  add_custom_news_source(params: AddCustomNewsSourceParams): Promise<AddCustomNewsSourceResult>;
  update_news_article_state(params: UpdateNewsArticleStateParams): Promise<UpdateNewsArticleStateResult>;
  apply_news_classification_correction(params: ApplyNewsClassificationCorrectionParams): Promise<ApplyNewsClassificationCorrectionResult>;
  set_news_company_scope_override(params: SetNewsCompanyScopeOverrideParams): Promise<SetNewsCompanyScopeOverrideResult>;
  set_news_company_scope_universe(params: SetNewsCompanyScopeUniverseParams): Promise<SetNewsCompanyScopeUniverseResult>;
  save_news_google_company_feed_settings(params: SaveNewsGoogleCompanyFeedSettingsParams): Promise<SaveNewsGoogleCompanyFeedSettingsResult>;
  save_news_retention_policy(params: SaveNewsRetentionPolicyParams): Promise<SaveNewsRetentionPolicyResult>;
  cleanup_news_extracted_content(params?: { dry_run?: boolean }): Promise<CleanupNewsExtractedContentResult>;
  backfill_news_article_content(params?: BackfillNewsArticleContentParams): Promise<BackfillNewsArticleContentResult>;
  get_companies(params: Record<string, unknown>): Promise<CompanyDirectoryPage>;
  get_company_info(params: Record<string, unknown>): Promise<CompanyInfo>;
  get_company_financial_readiness(
    params: Record<string, unknown>,
  ): Promise<CompanyFinancialReadiness>;
  get_company_years(params: Record<string, unknown>): Promise<CompanyYearsResult>;
  get_company_statement_years(params: Record<string, unknown>): Promise<CompanyYearsResult>;
  get_company_kpis(params: Record<string, unknown>): Promise<KPIBundle>;
  get_company_historical_indicators(
    params: Record<string, unknown>,
  ): Promise<CompanyHistoricalIndicatorsResult>;
  get_company_market_history_status(params: Record<string, unknown>): Promise<CompanyMarketHistoryStatus>;
  get_company_market_history(params: Record<string, unknown>): Promise<CompanyMarketHistoryResult>;
  refresh_company_market_history(params: Record<string, unknown>): Promise<CompanyMarketHistoryRefreshResult>;
  refresh_all_company_market_history(params: Record<string, unknown>): Promise<CompanyMarketHistoryAllRefreshResult>;
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
  get_market_cap_list(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string; items: MarketCapEntry[] }>;
  import_market_cap_snapshot(params: { csv_content?: string; file_path?: string }): Promise<MarketCapImportResponse>;
  get_market_cap_status(params?: Record<string, unknown>): Promise<MarketCapStatus>;
  fetch_market_cap_snapshot(
    params?: Record<string, unknown>,
  ): Promise<{ ok: boolean; error?: string; status?: MarketCapStatus }>;
  get_database_diagnostics(params?: Record<string, unknown>): Promise<DatabaseDiagnostics>;
  get_local_database_state(params?: Record<string, unknown>): Promise<LocalDatabaseState>;
  get_data_coverage(params?: Record<string, unknown>): Promise<DataCoverageResponse>;
  set_company_ignored(params: Record<string, unknown>): Promise<SetCompanyIgnoredResponse>;
  get_company_filters(params?: Record<string, unknown>): Promise<CompanyFiltersResponse>;
  get_sectors(params?: Record<string, unknown>): Promise<SectorDirectoryResponse>;
  get_sector_detail(params: Record<string, unknown>): Promise<SectorDetailResponse>;
  export_company_excel(params: Record<string, unknown>): Promise<ExportCompanyResult>;
  open_company_excel_mapping_window(
    params: { cd_cvm: number },
  ): Promise<OpenCompanyExcelMappingWindowResult>;
  export_company_market_history_excel(params: Record<string, unknown>): Promise<ExportMarketHistoryResult>;
  get_output_dir(params?: Record<string, unknown>): Promise<OutputDirInfo>;
  get_excel_mapping_workspace(params: Record<string, unknown>): Promise<ExcelMappingWorkspace>;
  save_excel_mapping_preset(params: Record<string, unknown>): Promise<SaveExcelMappingPresetResult>;
  set_company_excel_mapping_default(
    params: Record<string, unknown>,
  ): Promise<SetCompanyExcelMappingDefaultResult>;
  save_excel_mapping_override(params: Record<string, unknown>): Promise<{ ok: boolean; error?: string }>;
  delete_excel_mapping_override(params: Record<string, unknown>): Promise<{ ok: boolean; error?: string }>;
  get_gics_structure(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string; items: GicsSubIndustry[] }>;
  get_b3_classification_status(params?: Record<string, unknown>): Promise<B3RefreshStatus>;
  refresh_b3_classification(params?: Record<string, unknown>): Promise<B3RefreshRun & { ok: boolean; error?: string }>;
  set_company_classification(
    params: Record<string, unknown>,
  ): Promise<{ ok: boolean; error?: string; classification?: CompanyClassification }>;
  clear_company_classification(
    params: Record<string, unknown>,
  ): Promise<{ ok: boolean; error?: string; classification?: CompanyClassification }>;
  get_sub_sector_detail(params: Record<string, unknown>): Promise<SectorDetailResponse>;
  check_update(params?: Record<string, unknown>): Promise<{ available: boolean; version?: string; zip_url?: string; status?: string; error?: string }>;
  apply_update(params?: Record<string, unknown>): Promise<{ started: boolean; error?: string }>;
  get_update_progress(params?: Record<string, unknown>): Promise<UpdateProgressStatus>;
  snooze_update(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string }>;
  // Dev tools — only callable from /dev/data-ops (DEV build + flag)
  dev_reset_universe(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string }>;
  dev_reset_jobs(params?: Record<string, unknown>): Promise<{ ok: boolean; error?: string }>;
  dev_simulate_refresh(params: { mode: "success" | "partial" | "fail" | "slow" }): Promise<{ ok: boolean; mode: string; job_id?: string; error?: string }>;
  dev_start_small_setup(params?: { count?: number }): Promise<{ status: string; job_id?: string; message?: string }>;
  dev_get_raw_state(params?: Record<string, unknown>): Promise<{ app_settings?: Array<{ key: string; value: string | null; updated_at: string | null }>; refresh_jobs?: Array<Record<string, unknown>>; error?: string }>;
  // Dev panel: dev mode only, refused in the packaged app (types.dev.ts)
  dev_get_context(params?: Record<string, unknown>): Promise<DevContextResponse>;
  dev_restart(params?: Record<string, unknown>): Promise<DevRestartResponse>;
  dev_set_auto_restart(params: { enabled: boolean }): Promise<DevAutoRestartResponse>;
  // Energy KPI — country-level macro layer
  get_kpi_catalog(params?: EnergyKPICatalogParams): Promise<EnergyKPICatalogResponse>;
  get_country_kpi_series(params: CountryKPISeriesParams): Promise<CountryKPISeriesResponse>;
  get_country_kpi_compare(params: CountryKPICompareParams): Promise<CountryKPICompareResponse>;
  get_energy_kpi_health(params?: Record<string, unknown>): Promise<EnergyKPIHealthResponse>;
  refresh_energy_kpis(params?: { triggered_by?: string }): Promise<EnergyKPIRefreshResult>;
  export_country_kpis_excel(params?: { iso_codes?: string[]; kpi_ids?: string[] }): Promise<{ path: string | null; error?: string }>;
  get_sin_kpi_dashboard(params?: Record<string, unknown>): Promise<SINKPIDashboardResponse>;
  get_sin_kpi_series(params?: SINKPISeriesParams): Promise<SINKPISeriesResponse>;
  get_sin_kpi_daily_chart_series(params?: SINKPIDailyChartSeriesParams): Promise<SINKPIDailyChartSeriesResponse>;
  get_sin_kpi_health(params?: Record<string, unknown>): Promise<SINKPIHealthResponse>;
  refresh_sin_kpis(params?: SINKPIRefreshParams): Promise<SINKPIRefreshResult>;
  get_energy_mart_status(params?: Record<string, unknown>): Promise<EnergyMartStatusResponse>;
  start_energy_mart_rebuild(params: StartEnergyMartRebuildParams): Promise<EnergyMartRebuildState>;
  get_plant_parcel_source_statuses(params?: Record<string, unknown>): Promise<PlantParcelSourceStatusResponse>;
  get_plant_parcel_catalog(params?: PlantParcelCatalogParams): Promise<PlantParcelCatalogResponse>;
  get_plant_parcel_detail(params: PlantParcelDetailParams): Promise<PlantParcelDetailResponse>;
  get_plant_parcel_chart_data(params: PlantParcelChartDataParams): Promise<PlantParcelChartDataResponse>;
  refresh_plant_parcel_source(params: PlantParcelRefreshParams): Promise<PlantParcelRefreshResult>;
  select_plant_parcel_import_file(params: PlantParcelFilePickerParams): Promise<PlantParcelFilePickerResult>;
  import_plant_parcel_source_file(params: PlantParcelManualImportParams): Promise<PlantParcelManualImportResult>;
  get_fuel_distribution_product_year_summary(params?: FuelDistributionProductYearSummaryParams): Promise<FuelDistributionProductYearSummaryResponse>;
  get_fuel_distribution_state_month_series(params: FuelDistributionStateMonthSeriesParams): Promise<FuelDistributionStateMonthSeriesResponse>;
  get_fuel_distribution_detail(params: FuelDistributionDetailParams): Promise<FuelDistributionDetailResponse>;
  // Distribution analytics domain
  get_distribution_distributors(params?: { search?: string; economic_group_id?: string; uf?: string }): Promise<{ items: DistributorEntry[]; count: number; error?: string }>;
  get_distribution_distributor_detail(params: { distributor_id: string }): Promise<DistributorDetail | { error: string }>;
  get_distribution_series(params: { entity_type: string; entity_id: string; frequency?: string }): Promise<{ series: DistributionSeriesEntry[]; count: number; error?: string }>;
  get_distribution_mmgd_projects(params: { distributor_id?: string; reference_month?: string; limit?: number; offset?: number }): Promise<DistributionMmgdProjectsResponse>;
  get_distribution_refresh_status(params?: Record<string, unknown>): Promise<DistributionRefreshStatus>;
  refresh_distribution_data(params?: { years?: number[]; force?: boolean }): Promise<{ status: string; error: string | null }>;
  get_distribution_groups(params?: Record<string, unknown>): Promise<{ items: EconomicGroupEntry[]; count: number; error?: string }>;
  get_distribution_group_detail(params: { group_id: string }): Promise<EconomicGroupDetail | { error: string }>;
  export_distribution_excel(params: { entity_type: "distributor" | "group"; entity_id: string }): Promise<{ path: string | null; error: string | null }>;
  get_distribution_health(params?: Record<string, unknown>): Promise<DistributionHealthResponse>;
  get_conglomerates(params?: Record<string, unknown>): Promise<{ items: ConglomerateEntry[]; count: number; error?: string }>;
  get_asset_mappings(params?: Record<string, unknown>): Promise<{ items: AssetMappingEntry[]; count: number; error?: string }>;
  update_asset_mapping(params: { asset_id: string; asset_type: "distributor" | "plant"; cd_cvm: number | null; custom_owner_name?: string | null; review_notes?: string | null }): Promise<{ status: string; error: string | null }>;
  run_automatic_mapping(params?: Record<string, unknown>): Promise<{ status: string; matched?: number; preserved_manual?: number; error?: string }>;
  get_company_universe(params?: Record<string, unknown>): Promise<{ items: CvmRegistryEntry[]; count: number; error?: string }>;
  get_company_connections(params: { cd_cvm: number }): Promise<{ has_financials: boolean; mapped_distributors: number; mapped_plants: number; total_capacity_mw: number; error?: string }>;
  resolve_company_identities(params: { inputs: string[] }): Promise<{ resolved: any[]; unmapped: string[]; error?: string }>;
  // Coverage Universe
  get_coverage_universes(params?: Record<string, unknown>): Promise<any>;
  get_coverage_universe(params: { id: string }): Promise<any>;
  create_coverage_universe(params: { name: string; purpose?: string; analysis_type?: string; benchmark?: string }): Promise<{ universe_id?: string; error?: string }>;
  update_coverage_universe(params: { id: string; name: string; purpose?: string; benchmark?: string; status: string; assumptions?: any }): Promise<{ success?: boolean; error?: string }>;
  delete_coverage_universe(params: { id: string }): Promise<{ success?: boolean; error?: string }>;
  duplicate_coverage_universe(params: { id: string; name: string; copy_companies?: boolean; copy_checklists?: boolean }): Promise<{ universe_id?: string; error?: string }>;
  bulk_update_companies_in_coverage_universe(params: { universe_id: string; company_ids: number[]; tier: string; rationale: string }): Promise<{ success?: boolean; error?: string }>;
  add_company_to_coverage_universe(params: { universe_id: string; cd_cvm: number; tier: string; rationale: string; owner?: string; holding_pct?: number }): Promise<{ success?: boolean; error?: string }>;
  remove_company_from_coverage_universe(params: { universe_id: string; cd_cvm: number; rationale: string }): Promise<{ success?: boolean; error?: string }>;
  calculate_coverage_priority_scores(params: { universe_id: string }): Promise<{ items?: any[]; _bridge_ms?: number; error?: string }>;
  save_manual_score_override(params: { universe_id: string; cd_cvm: number; override: number | null; rationale: string }): Promise<{ success?: boolean; error?: string }>;
  get_company_coverage_checklists(params: { universe_id: string; cd_cvm: number }): Promise<{ items?: any[]; error?: string }>;
  update_company_coverage_checklist_item(params: { universe_id: string; cd_cvm: number; item_key: string; is_completed: boolean; comments?: string; rationale: string }): Promise<{ success?: boolean; error?: string }>;
  get_coverage_work_queue(params: { universe_id: string }): Promise<{ items?: any[]; error?: string }>;
  get_coverage_capacity_data(params: { universe_id: string }): Promise<any>;
  save_coverage_capacity_scenario(params: { universe_id: string; available_hours: number; tier_hours: Record<string, number> }): Promise<{ success?: boolean; error?: string }>;
  get_coverage_decision_history(params: { universe_id: string; cd_cvm?: number }): Promise<{ items?: any[]; error?: string }>;
  download_coverage_universe_excel(params: { universe_id: string }): Promise<{ filename?: string; mime_type?: string; content_base64?: string; error?: string }>;
  update_company_owner_analyst(params: { universe_id: string; cd_cvm: number; owner: string | null; rationale: string }): Promise<{ success?: boolean; error?: string }>;
  get_coverage_recommendation(params: { universe_id: string }): Promise<any>;
  save_coverage_manager_decision(params: { universe_id: string; status: string; notes?: string }): Promise<{ success?: boolean; status?: string; decided_at?: string; error?: string }>;
}

declare global {
  interface Window {
    pywebview?: {
      api: BridgeApi;
    };
  }
}

export {};
