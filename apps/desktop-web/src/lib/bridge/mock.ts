/**
 * Mock bridge — dev-only fixture implementation of BridgeApi.
 *
 * Active only when VITE_MOCK_BRIDGE=1 AND import.meta.env.DEV is true.
 * Never compiled into production builds (tree-shaken by Vite).
 *
 * Provides realistic fixture data covering:
 *   companies with complete / partial / no-history / failed / unmapped status
 *   active and completed refresh jobs
 *   base health snapshot
 *   data coverage
 *   financial KPIs and statements (two companies)
 *   onboarding (completed state)
 *   app status with mock runtime info
 */

// Safety guard: throw immediately if somehow loaded outside a dev build.
if (!import.meta.env.DEV) {
  throw new Error("[CVMAnalytics] mock bridge loaded in non-dev build — this is a bug");
}

import { mockLocalDatabaseState } from "./mockLocalDatabase";
import type {
  BridgeApi,
  AppStatusPayload,
  BaseHealthSnapshot,
  CompanyDirectoryItem,
  CompanyDirectoryPage,
  CompanyFiltersResponse,
  CompanyInfo,
  CompanyYearsResult,
  CountryKPICompareResponse,
  CountryKPISeriesResponse,
  DataCoverageResponse,
  DataCoverageRow,
  DatabaseDiagnostics,
  DataUpdateSettings,
  EnergyKPICatalogResponse,
  EnergyKPIHealthResponse,
  EnergyMartRebuildState,
  EnergyMartStatusResponse,
  FuelDistributionDetailResponse,
  FuelDistributionProductYearSummaryResponse,
  FuelDistributionStateMonthSeriesResponse,
  EnergyKPIRefreshResult,
  KPIBundle,
  OnboardingState,
  PlantParcelCatalogResponse,
  PlantParcelRefreshResult,
  RefreshJobListResponse,
  RefreshJobStatus,
  SectorDirectoryResponse,
  SectorDetailResponse,
  SettingsHealthSummary,
  SINKPIHealthResponse,
  SINKPIDailyChartSeriesResponse,
  SINKPISeriesResponse,
  StatementMatrix,
  StorageInventory,
  TabularData,
  TabularRow,
} from "./types";
import {
  COUNTRY_NS,
  MOCK_COUNTRY_KPI_VALUES,
  MOCK_KPI_CATALOG,
  MOCK_PLANT_DETAIL,
  MOCK_PLANT_RECORDS,
  MOCK_PLANT_SOURCES,
  MOCK_SIN_DASHBOARD,
  MOCK_SIN_VALUES,
} from "./mockEnergyFixtures";

const MOCK_SIN_FREQUENCY_BY_DATASET: Record<string, string> = {
  balanco_energia_subsistema: "hourly",
  ear_diario_subsistema: "daily",
  ena_diario_subsistema: "daily",
  cmo_semihorario: "semi-hourly",
  pld_horario: "hourly",
};


// ---------------------------------------------------------------------------
// Fixture constants
// ---------------------------------------------------------------------------

const NOW = new Date().toISOString();
const YEAR = new Date().getFullYear();

interface FixtureCompany {
  cd_cvm: number;
  company_name: string;
  ticker_b3: string | null;
  sector_name: string;
  sector_slug: string;
  data_status: string;
  anos_disponiveis: number[];
  total_rows: number;
  has_financial_data: boolean;
  cnpj: string | null;
}

const FIXTURE_COMPANIES: FixtureCompany[] = [
  {
    cd_cvm: 9512,
    company_name: "PETROBRAS PN",
    ticker_b3: "PETR4",
    sector_name: "Petróleo e Gás",
    sector_slug: "petroleo-e-gas",
    data_status: "complete",
    anos_disponiveis: [YEAR - 5, YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1],
    total_rows: 18450,
    has_financial_data: true,
    cnpj: "33.000.167/0001-01",
  },
  {
    cd_cvm: 14311,
    company_name: "VALE ON",
    ticker_b3: "VALE3",
    sector_name: "Mineração",
    sector_slug: "mineracao",
    data_status: "complete",
    anos_disponiveis: [YEAR - 5, YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1],
    total_rows: 15820,
    has_financial_data: true,
    cnpj: "33.592.510/0001-54",
  },
  {
    cd_cvm: 14673,
    company_name: "AMBEV SA",
    ticker_b3: "ABEV3",
    sector_name: "Alimentos e Bebidas",
    sector_slug: "alimentos-e-bebidas",
    data_status: "partial",
    anos_disponiveis: [YEAR - 3, YEAR - 2, YEAR - 1],
    total_rows: 6200,
    has_financial_data: true,
    cnpj: "07.526.557/0001-00",
  },
  {
    cd_cvm: 4170,
    company_name: "OI SA",
    ticker_b3: "OIBR3",
    sector_name: "Telecomunicações",
    sector_slug: "telecomunicacoes",
    data_status: "failed",
    anos_disponiveis: [YEAR - 5, YEAR - 4],
    total_rows: 3100,
    has_financial_data: false,
    cnpj: "76.535.764/0001-43",
  },
  {
    cd_cvm: 5258,
    company_name: "XP INC",
    ticker_b3: null,
    sector_name: "Financeiro",
    sector_slug: "financeiro",
    data_status: "no_history",
    anos_disponiveis: [],
    total_rows: 0,
    has_financial_data: false,
    cnpj: null,
  },
  {
    cd_cvm: 99001,
    company_name: "EMPRESA DEMO LTDA",
    ticker_b3: null,
    sector_name: "Outros",
    sector_slug: "outros",
    data_status: "unmapped",
    anos_disponiveis: [],
    total_rows: 0,
    has_financial_data: false,
    cnpj: null,
  },
];

const MOCK_JOB_RUNNING: RefreshJobStatus = {
  job_id: "mock-job-running-001",
  state: "running",
  mode: "missing",
  stage: "download_extract",
  queued: 200,
  processed: 45,
  failures: 2,
  current_cvm: 9512,
  log_lines: [
    "[mock] Starting batch refresh for 200 companies",
    "[mock] Downloading PETR4 (9512)...",
    "[mock] Processing financial reports...",
  ],
  accepted_at: new Date(Date.now() - 120_000).toISOString(),
  started_at: new Date(Date.now() - 100_000).toISOString(),
  finished_at: null,
  updated_at: new Date(Date.now() - 5_000).toISOString(),
  source: "db_worker",
  progress_current: 45,
  progress_total: 200,
};

const MOCK_JOB_COMPLETED: RefreshJobStatus = {
  job_id: "mock-job-done-001",
  state: "success",
  mode: "missing",
  stage: "finalizing",
  queued: 100,
  processed: 100,
  failures: 0,
  current_cvm: null,
  log_lines: ["[mock] Completed 100/100 companies"],
  accepted_at: new Date(Date.now() - 3_600_000).toISOString(),
  started_at: new Date(Date.now() - 3_580_000).toISOString(),
  finished_at: new Date(Date.now() - 3_000_000).toISOString(),
  updated_at: new Date(Date.now() - 3_000_000).toISOString(),
  source: "db_worker",
  progress_current: 100,
  progress_total: 100,
};

// ---------------------------------------------------------------------------
// KPI / statement fixture helpers
// ---------------------------------------------------------------------------

function makeTabularData(cols: string[], rows: (string | number | null)[][]): TabularData {
  return {
    columns: cols,
    rows: rows.map((r) => Object.fromEntries(cols.map((c, i) => [c, r[i]]))),
  };
}

/**
 * KPI fixtures mirror the real engine output shape (src/financials/kpi_engine.py):
 * rows carry KPI_ID / KPI_NOME / CATEGORIA / FORMAT_TYPE / IS_PLACEHOLDER and
 * one column per period (annual "2023" or quarterly "1Q24"), plus DELTA_YOY_PCT.
 * Percentages are stored as fractions (0.31 → 31%), ratios as multiples (1.8x),
 * matching the engine and the app formatters. Valuation rows are placeholders
 * (null everywhere) exactly as the engine emits them without market data.
 */
interface MockKpiSpec {
  id: string;
  nome: string;
  categoria: string;
  fmt: "pct" | "ratio";
  base: number;
  drift: number;
  placeholder?: boolean;
}

const MOCK_KPI_SPECS: MockKpiSpec[] = [
  { id: "MG_BRUTA", nome: "Margem Bruta", categoria: "Rentabilidade", fmt: "pct", base: 0.42, drift: 0.03 },
  { id: "MG_EBITDA", nome: "Margem EBITDA", categoria: "Rentabilidade", fmt: "pct", base: 0.31, drift: 0.04 },
  { id: "MG_EBIT", nome: "Margem EBIT", categoria: "Rentabilidade", fmt: "pct", base: 0.24, drift: 0.03 },
  { id: "MG_LIQ", nome: "Margem Líquida", categoria: "Rentabilidade", fmt: "pct", base: 0.16, drift: 0.03 },
  { id: "ROE", nome: "ROE", categoria: "Rentabilidade", fmt: "pct", base: 0.18, drift: 0.05 },
  { id: "ROA", nome: "ROA", categoria: "Rentabilidade", fmt: "pct", base: 0.09, drift: 0.02 },
  { id: "ROIC", nome: "ROIC *", categoria: "Rentabilidade", fmt: "pct", base: NaN, drift: 0, placeholder: true },
  { id: "LIQ_CORR", nome: "Liquidez Corrente", categoria: "Liquidez", fmt: "ratio", base: 1.4, drift: 0.2 },
  { id: "LIQ_SECA", nome: "Liquidez Seca", categoria: "Liquidez", fmt: "ratio", base: 1.1, drift: 0.15 },
  { id: "LIQ_IMED", nome: "Liquidez Imediata", categoria: "Liquidez", fmt: "ratio", base: 0.6, drift: 0.1 },
  { id: "DIV_EBITDA", nome: "Dívida Líq./EBITDA", categoria: "Endividamento", fmt: "ratio", base: 1.8, drift: 0.4 },
  { id: "PL_PASS", nome: "PL / Passivo Total", categoria: "Endividamento", fmt: "pct", base: 0.45, drift: 0.04 },
  { id: "PC_PASS", nome: "Passivo Circ./Total", categoria: "Endividamento", fmt: "pct", base: 0.38, drift: 0.03 },
  { id: "FCO_REC", nome: "FCO / Receita", categoria: "Fluxo de Caixa", fmt: "pct", base: 0.22, drift: 0.04 },
  { id: "FCL_REC", nome: "FCL / Receita", categoria: "Fluxo de Caixa", fmt: "pct", base: 0.12, drift: 0.05 },
  { id: "CAPEX_REC", nome: "CAPEX / Receita *", categoria: "Fluxo de Caixa", fmt: "pct", base: 0.1, drift: 0.02 },
  { id: "CRESC_REC", nome: "Crescimento Receita", categoria: "Crescimento", fmt: "pct", base: 0.08, drift: 0.06 },
  { id: "CRESC_LUC", nome: "Crescimento Lucro", categoria: "Crescimento", fmt: "pct", base: 0.11, drift: 0.09 },
  { id: "CAGR_REC", nome: "CAGR Receita (5a) *", categoria: "Crescimento", fmt: "pct", base: NaN, drift: 0, placeholder: true },
  { id: "EV_EBITDA", nome: "EV/EBITDA *", categoria: "Valuation", fmt: "ratio", base: NaN, drift: 0, placeholder: true },
  { id: "PL_PRECO", nome: "P/L *", categoria: "Valuation", fmt: "ratio", base: NaN, drift: 0, placeholder: true },
  { id: "DY", nome: "Dividend Yield *", categoria: "Valuation", fmt: "pct", base: NaN, drift: 0, placeholder: true },
];

function buildMockKpiTable(periods: string[], seed: number): TabularData {
  const meta = ["KPI_ID", "KPI_NOME", "CATEGORIA", "FORMAT_TYPE", "IS_PLACEHOLDER", "HIGHER_IS_BETTER", "UNIDADE"];
  const columns = [...meta, ...periods, "DELTA_YOY_PCT"];
  const rows: TabularRow[] = MOCK_KPI_SPECS.map((spec, specIdx) => {
    const row: TabularRow = {
      KPI_ID: spec.id,
      KPI_NOME: spec.nome,
      CATEGORIA: spec.categoria,
      FORMAT_TYPE: spec.fmt,
      IS_PLACEHOLDER: spec.placeholder ?? false,
      HIGHER_IS_BETTER: false,
      UNIDADE: spec.fmt === "pct" ? "%" : "x",
    };
    periods.forEach((p, i) => {
      if (spec.placeholder) {
        row[p] = null;
        return;
      }
      // Deterministic, smooth wobble so charts show realistic trends.
      const wobble = Math.sin((i + seed + specIdx) * 0.6) * spec.drift;
      const v = spec.base + wobble + i * spec.drift * 0.15;
      row[p] = Number(v.toFixed(spec.fmt === "pct" ? 4 : 2));
    });
    const last = row[periods[periods.length - 1]];
    const prev = row[periods[periods.length - 2]];
    row.DELTA_YOY_PCT =
      typeof last === "number" && typeof prev === "number" && prev !== 0
        ? Number(((last - prev) / Math.abs(prev)).toFixed(4))
        : null;
    return row;
  });
  return { columns, rows };
}

/** Interleaved quarterly periods matching the engine: 1Q,2Q,3Q,annual per year (Q4 omitted). */
function mockQuarterlyPeriods(years: number[]): string[] {
  const out: string[] = [];
  for (const y of years) {
    const yy = String(y).slice(2);
    out.push(`1Q${yy}`, `2Q${yy}`, `3Q${yy}`, String(y));
  }
  return out;
}

function mockKpis(cdCvm: number, years: number[]): KPIBundle {
  const seed = cdCvm % 7;
  const annualYears = years.length > 0 ? years : [YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1];
  return {
    cd_cvm: cdCvm,
    years: annualYears,
    annual: buildMockKpiTable(annualYears.map(String), seed),
    quarterly: buildMockKpiTable(mockQuarterlyPeriods(annualYears), seed + 1),
  };
}

function mockStatement(cdCvm: number, statementType: string): StatementMatrix {
  const years = [YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1];
  const yearCols = years.map(String);
  const cols = ["Conta", "Descrição", ...yearCols];
  const rows: (string | number | null)[][] =
    statementType === "DRE"
      ? [
          ["3.01", "Receita de Venda de Bens e/ou Serviços", 40_000, 44_000, 38_000, 52_000],
          ["3.04", "Resultado Bruto", 18_000, 20_000, 16_500, 24_000],
          ["3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", 12_000, 14_000, 10_800, 16_500],
          ["3.09", "Lucro/Prejuízo Consolidado do Período", 7_200, 9_100, 6_800, 11_200],
        ]
      : [
          ["1", "Ativo Total", 280_000, 295_000, 310_000, 330_000],
          ["1.01", "Ativo Circulante", 55_000, 58_000, 62_000, 70_000],
          ["2", "Passivo Total", 190_000, 195_000, 205_000, 215_000],
          ["2.03", "Patrimônio Líquido Consolidado", 90_000, 100_000, 105_000, 115_000],
        ];
  return {
    cd_cvm: cdCvm,
    statement_type: statementType,
    years,
    table: makeTabularData(cols, rows),
    exclude_conflicts: true,
  };
}

// ---------------------------------------------------------------------------
// Base health fixture
// ---------------------------------------------------------------------------

const MOCK_BASE_HEALTH: BaseHealthSnapshot = {
  generated_at: new Date(Date.now() - 900_000).toISOString(),
  start_year: YEAR - 4,
  end_year: YEAR - 1,
  total_cells: 2400,
  completed_cells: 1680,
  missing_cells: 720,
  pct: 70,
  health_score: 70,
  health_status: "partial",
  eta_hours: 6,
  throughput_per_hour: 50,
  throughput_confidence: "medium",
  per_year: [YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1].map((y, i) => ({
    year: y,
    total_companies: 600,
    completed: 540 - i * 30,
    missing: 60 + i * 30,
    pct: Math.round(((540 - i * 30) / 600) * 100),
    eta_hours: i === 0 ? null : 2,
  })),
  prioritized_companies: [
    {
      cd_cvm: 14311,
      company_name: "VALE ON",
      sector_name: "Mineração",
      sector_slug: "mineracao",
      priority_score: 95,
      missing_years_count: 1,
      gap_to_leader_years: 1,
      years_missing: [YEAR - 1],
      recommended_action: "refresh",
      reason: "Missing most recent year",
    },
    {
      cd_cvm: 4170,
      company_name: "OI SA",
      sector_name: "Telecomunicações",
      sector_slug: "telecomunicacoes",
      priority_score: 72,
      missing_years_count: 3,
      gap_to_leader_years: 3,
      years_missing: [YEAR - 3, YEAR - 2, YEAR - 1],
      recommended_action: "refresh",
      reason: "Multiple years missing",
    },
  ],
  raw: {},
  total_companies: 600,
  companies_with_historical_data: 420,
  companies_without_historical_data: 180,
  companies_with_any_local_financial_report: 440,
  companies_partial_local: 80,
  companies_fully_updated: 340,
  companies_with_refresh_status_recorded: 500,
  companies_with_last_refresh_error: 22,
};

// ---------------------------------------------------------------------------
// Data coverage fixture
// ---------------------------------------------------------------------------

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
    current_version: "0.29.1",
    latest_version: "0.29.1",
    update_available: false,
    status: "up_to_date",
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
      action_route: "/settings/coverage",
      details: { coverage_route: "/settings/coverage" },
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
      action_route: "/settings/health",
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

const MOCK_ONBOARDING: OnboardingState = {
  first_run_completed: true,
  should_show: false,
  selected_company_universe: "top_200",
  company_universe_source: "mock-fixture",
  company_universe_source_date: `${YEAR - 1}-01-01`,
  setup_status: "completed",
  selected_company_count: 200,
  refresh_job_id: MOCK_JOB_COMPLETED.job_id,
  refresh_job: MOCK_JOB_COMPLETED,
  warning: null,
  has_local_financial_data: true,
  market_cap_source_available: true,
  market_cap_source: "mock-fixture",
  market_cap_ranked_companies: 200,
  yfinance_universe_provider_enabled: true,
};

// ---------------------------------------------------------------------------
// Data update settings
// ---------------------------------------------------------------------------

const MOCK_UPDATE_SETTINGS: DataUpdateSettings = {
  universe_preset: "top_200",
  batch_size: 100,
  retry_failed: true,
  recompute_coverage: true,
  start_year: YEAR - 4,
  end_year: YEAR - 1,
};

// ---------------------------------------------------------------------------
// Sector fixtures
// ---------------------------------------------------------------------------

const SECTOR_SLUGS = [
  { name: "Petróleo e Gás", slug: "petroleo-e-gas", count: 1 },
  { name: "Mineração", slug: "mineracao", count: 1 },
  { name: "Alimentos e Bebidas", slug: "alimentos-e-bebidas", count: 1 },
  { name: "Telecomunicações", slug: "telecomunicacoes", count: 1 },
  { name: "Financeiro", slug: "financeiro", count: 1 },
  { name: "Outros", slug: "outros", count: 1 },
];


// ---------------------------------------------------------------------------
// Company directory item helpers
// ---------------------------------------------------------------------------

function toDirectoryItem(c: FixtureCompany): CompanyDirectoryItem {
  return {
    cd_cvm: c.cd_cvm,
    company_name: c.company_name,
    ticker_b3: c.ticker_b3,
    setor_cvm: c.sector_name,
    sector_name: c.sector_name,
    sector_slug: c.sector_slug,
    anos_disponiveis: c.anos_disponiveis,
    total_rows: c.total_rows,
    has_financial_data: c.has_financial_data,
    coverage_rank: c.has_financial_data ? 1 : null,
    data_status: c.data_status,
    gics_sector: c.cd_cvm === 9512 ? "Energy" : c.cd_cvm === 14311 ? "Materials" : c.cd_cvm === 14673 ? "Consumer Staples" : null,
    gics_sector_slug: c.cd_cvm === 9512 ? "energy" : c.cd_cvm === 14311 ? "materials" : c.cd_cvm === 14673 ? "consumer-staples" : null,
    gics_industry_group: null,
    gics_industry: c.cd_cvm === 9512 ? "Oil, Gas & Consumable Fuels" : null,
    gics_sub_industry: c.cd_cvm === 9512 ? "Integrated Oil & Gas" : c.cd_cvm === 14311 ? "Steel" : c.cd_cvm === 14673 ? "Brewers" : null,
  };
}

const DOWNLOADED_MARKET_HISTORIES = new Set<number>([9512, 14311]);

function resolveMockTicker(cdCvm: number, requestedTicker?: string | null): string | null {
  if (requestedTicker) {
    let t = requestedTicker.trim().toUpperCase();
    if (t) {
      if (!t.includes(".")) {
        t = `${t}.SA`;
      }
      return t;
    }
  }

  const company = FIXTURE_COMPANIES.find((c) => c.cd_cvm === cdCvm);
  if (company && company.ticker_b3) {
    let t = company.ticker_b3.trim().toUpperCase();
    if (!t.includes(".")) {
      t = `${t}.SA`;
    }
    return t;
  }

  return null;
}

function resolveMockCompanyTickers(cdCvm: number, requestedTicker?: string | null): string[] {
  const primary = resolveMockTicker(cdCvm, requestedTicker);
  if (!primary) {
    return [];
  }
  
  const m = primary.match(/^([A-Z]{4})\d+/);
  if (!m) {
    return [primary];
  }
  const base = m[1];
  const suffixes = ["3", "4", "5", "6", "11"];
  const candidates = suffixes.map((s) => `${base}${s}.SA`);
  
  const result = [primary];
  for (const c of candidates) {
    if (!result.includes(c)) {
      result.push(c);
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// createMockBridge — exported factory
// ---------------------------------------------------------------------------

export function createMockBridge(): Partial<BridgeApi> {
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

    get_news_articles: async (params) => {
      const limit = Number(params?.limit ?? 50);
      const offset = Number(params?.offset ?? 0);
      const order = params?.order === "top" ? "top" : "latest";
      const items = [
        {
          article_id: "mock-news-1",
          source_id: "bcb-rss",
          source_item_id: "mock-bcb-1",
          title: "Banco Central updates market expectations bulletin",
          source_name: "Banco Central do Brasil",
          original_url: "https://www.bcb.gov.br/mock/news-1",
          canonical_url: "https://www.bcb.gov.br/mock/news-1",
          published_at: NOW,
          discovered_at: NOW,
          fetched_at: NOW,
          summary: "Mock local news item for the future News overview.",
          language: "en",
          content_status: "summary_available",
          paywall_status: null,
          read: 0,
          saved: 0,
          hidden: 0,
          read_later: 0,
          notes: null,
          relevance_score: 3.25,
          priority_level: "High",
          relevance_components: {
            source_reliability: 1,
            freshness: 0.8,
            keyword_relevance: 0.7,
            company_relevance: 0.75,
          },
          relevance_reasons: [
            "Source reliability component 1.00 from official",
            "Priority set to High by deterministic score rules",
          ],
        },
      ].slice(offset, offset + limit);
      return { items, count: items.length, total: 1, limit, offset, order };
    },

    get_news_overview: async (params) => {
      const limit = Number(params?.limit_per_section ?? 6);
      const item = {
        article_id: "mock-news-1",
        source_id: "bcb-rss",
        source_item_id: "mock-bcb-1",
        title: "Banco Central updates market expectations bulletin",
        source_name: "Banco Central do Brasil",
        original_url: "https://www.bcb.gov.br/mock/news-1",
        canonical_url: "https://www.bcb.gov.br/mock/news-1",
        published_at: NOW,
        discovered_at: NOW,
        fetched_at: NOW,
        summary: "Mock local news item for the News overview.",
        language: "en",
        content_status: "summary_available",
        paywall_status: null,
        read: 0,
        saved: 0,
        hidden: 0,
        read_later: 0,
        notes: null,
        relevance_score: 3.25,
        priority_level: "High",
        relevance_components: {
          source_reliability: 1,
          freshness: 0.8,
          keyword_relevance: 0.7,
          company_relevance: 0.75,
        },
        relevance_reasons: [
          "Source reliability component 1.00 from official",
          "Priority set to High by deterministic score rules",
        ],
      };
      const sections = [
        ["critical_news", "Critical News", "Articles with Critical priority from deterministic scoring.", []],
        ["top_market_news", "Top Market News", "Highest ranked local articles using explainable score components.", [item]],
        ["macro_watch", "Macro Watch", "Articles matched to macro topics or macro keyword rules.", [item]],
        ["my_companies", "My Companies", "Articles with deterministic company associations.", [item]],
        ["my_sectors", "My Sectors", "Articles with deterministic sector associations.", [item]],
        ["keyword_alerts", "Keyword Alerts", "Articles matched to active keyword rules.", [item]],
        ["all_news", "All News", "Most recent local articles, without ranking.", [item]],
      ].map(([section_id, title, reason, items]) => ({
        section_id: String(section_id),
        title: String(title),
        reason: String(reason),
        items: (items as typeof item[]).slice(0, limit),
      }));
      return { sections, limit_per_section: limit };
    },

    get_news_company_scope: async () => ({
      selected_preset: "top_200",
      coverage_count: 200,
      included_count: 201,
      excluded_count: 0,
      overrides: [
        {
          cd_cvm: 9512,
          action: "include",
          reason: "Mock News-specific inclusion",
          created_at: NOW,
          updated_at: NOW,
        },
      ],
    }),

    get_news_article_classification: async () => ({
      keywords: [
        {
          keyword_rule_id: "kw_macro_selic",
          group_name: "Macro",
          term: "Selic",
          matched_term: "Selic",
          match_method: "keyword_exact",
          match_reason: "Matched keyword rule kw_macro_selic term 'Selic' in summary",
          relevance_score: 0.7,
        },
      ],
      topics: [
        {
          topic_id: "topic_macro_rates",
          label: "Interest rates",
          topic_type: "macro",
          match_method: "keyword_rule",
          match_reason: "Matched keyword rule kw_macro_selic term 'Selic' in summary",
          relevance_score: 0.7,
        },
      ],
      event_types: [],
      companies: [
        {
          cd_cvm: 9512,
          match_method: "ticker",
          match_reason: "Matched company CVM 9512 by ticker 'PETR4' in title",
          relevance_score: 1,
          rule_strength: 1,
          is_primary: 1,
          manually_reviewed: 0,
        },
      ],
      sectors: [
        {
          sector_slug: "energy",
          sector_name: "Energy",
          parent_sector_slug: null,
          parent_sector_name: null,
          match_method: "company_sector",
          match_reason: "Matched sector from company CVM 9512: matched ticker PETR4",
          relevance_score: 0.8,
          rule_strength: 1,
          is_primary: 1,
          manually_reviewed: 0,
        },
        {
          sector_slug: "integrated-oil-gas",
          sector_name: "Integrated Oil & Gas",
          parent_sector_slug: "energy",
          parent_sector_name: "Energy",
          match_method: "company_sub_industry",
          match_reason: "Matched sector from company CVM 9512: matched ticker PETR4",
          relevance_score: 0.85,
          rule_strength: 1,
          is_primary: 1,
          manually_reviewed: 0,
        },
      ],
      score: {
        total_score: 3.25,
        priority_level: "High",
        components: {
          source_reliability: 1,
          freshness: 0.8,
          keyword_relevance: 0.7,
          company_relevance: 0.75,
        },
        reasons: [
          "Source reliability component 1.00 from official",
          "Priority set to High by deterministic score rules",
        ],
        updated_at: NOW,
      },
      corrections: [],
    }),

    get_news_article_content: async (params) => ({
      article_id: params.article_id,
      title: "Banco Central updates market expectations bulletin",
      content_status: "full_text_available",
      paywall_status: null,
      available: true,
      content_text: "Mock locally stored feed content for the selected News article.",
      content_format: "feed",
      source_policy: "feed_content_allowed",
      storage_bytes: 64,
      extracted_at: NOW,
      updated_at: NOW,
    }),

    apply_news_classification_correction: async (params) => ({
      status: "success",
      correction_id: "mock-correction-1",
      article_id: params.article_id,
      target_type: params.target_type,
      target_id: params.target_id,
      correction_action: params.action,
    }),

    set_news_company_scope_override: async (params) => ({
      status: "success",
      cd_cvm: params.cd_cvm,
      action: params.action || null,
      deleted: !params.action,
    }),

    get_news_retention_status: async () => ({
      content_count: 0,
      storage_bytes: 0,
      saved_content_count: 0,
      oldest_extracted_at: null,
      newest_extracted_at: null,
      policy: {
        policy_id: "default",
        metadata_retention_days: 1825,
        extracted_text_retention_days: 90,
        total_storage_limit_mb: 512,
        preserve_saved: 1,
        preserve_official_documents: 1,
        updated_at: NOW,
      },
    }),

    save_news_retention_policy: async (params) => ({
      status: "success",
      policy: {
        policy_id: "default",
        metadata_retention_days: params.metadata_retention_days ?? 1825,
        extracted_text_retention_days: params.extracted_text_retention_days ?? 90,
        total_storage_limit_mb: params.total_storage_limit_mb ?? 512,
        preserve_saved: params.preserve_saved ?? true,
        preserve_official_documents: params.preserve_official_documents ?? true,
        updated_at: NOW,
      },
    }),

    cleanup_news_extracted_content: async (params) => ({
      status: "success",
      dry_run: Boolean(params?.dry_run),
      deleted_content_count: 0,
      freed_bytes: 0,
      preserved_saved: true,
      preserved_official_documents: true,
    }),

    backfill_news_article_content: async (params) => ({
      status: "success",
      limit: params?.limit ?? 25,
      include_normal: Boolean(params?.include_normal),
      candidate_count: 0,
      attempted_count: 0,
      stored_count: 0,
      paywalled_count: 0,
      failed_count: 0,
      skipped_count: 0,
      errors: [],
    }),

    get_news_sources: async () => ({
      items: [
        {
          source_id: "bcb-rss",
          name: "Banco Central do Brasil",
          source_type: "official",
          reliability_layer: "official",
          feed_url: "https://www.bcb.gov.br/acessoinformacao/rss",
          homepage_url: "https://www.bcb.gov.br/",
          enabled: 1,
          priority: 10,
          user_defined: 0,
          allow_content_storage: 1,
          etag: null,
          last_modified: null,
          updated_at: NOW,
          last_attempt_at: NOW,
          last_success_at: NOW,
          last_status: "success",
          last_error: null,
          last_http_status: 200,
          consecutive_failures: 0,
          last_article_count: 1,
        },
        {
          source_id: "b3-rss-news",
          name: "B3 RSS News",
          source_type: "official",
          reliability_layer: "official",
          feed_url: "https://www.b3.com.br/data/rss/suporteanegociacao.xml",
          homepage_url: "https://www.b3.com.br/",
          enabled: 1,
          priority: 20,
          user_defined: 0,
          allow_content_storage: 1,
          etag: null,
          last_modified: null,
          updated_at: NOW,
          last_attempt_at: null,
          last_success_at: null,
          last_status: null,
          last_error: null,
          last_http_status: null,
          consecutive_failures: 0,
          last_article_count: 0,
        },
      ],
      count: 2,
    }),

    get_news_collection_runs: async () => ({
      items: [
        {
          run_id: "mock-news-run-1",
          trigger: "manual",
          status: "success",
          started_at: NOW,
          finished_at: NOW,
          source_count: 2,
          articles_seen: 1,
          articles_inserted: 1,
          articles_updated: 0,
          error_count: 0,
          error_message: null,
        },
      ],
      count: 1,
    }),

    get_news_refresh_status: async () => ({
      status: "idle",
      error: null,
      started_at: null,
      finished_at: NOW,
      source_count: 2,
      completed_sources: 2,
      articles_seen: 1,
      articles_inserted: 1,
      articles_updated: 0,
      error_count: 0,
      sources: [],
    }),

    refresh_news_sources: async () => ({
      status: "started",
      error: null,
      started_at: NOW,
    }),

    set_news_source_enabled: async (params) => ({
      status: "success",
      source_id: params.source_id,
      enabled: params.enabled,
    }),

    set_news_source_priority: async (params) => ({
      status: "success",
      source_id: params.source_id,
      priority: params.priority,
    }),

    add_custom_news_source: async (params) => ({
      status: "success",
      source: {
        source_id: "user_mock_feed",
        name: params.name || "Mock custom feed",
        source_type: "user_provided_rss",
        reliability_layer: "user_provided",
        feed_url: params.feed_url,
        homepage_url: null,
        enabled: params.enabled ?? true,
        priority: params.priority ?? 100,
        user_defined: true,
      },
      validation: {
        title: params.name || "Mock custom feed",
        entry_count: 1,
        http_status: 200,
        final_url: params.feed_url,
      },
    }),

    update_news_article_state: async (params) => ({
      status: "success",
      state: {
        article_id: params.article_id,
        read: params.read ?? false,
        saved: params.saved ?? false,
        hidden: params.hidden ?? false,
        read_later: params.read_later ?? false,
        notes: params.notes ?? null,
      },
    }),

    get_database_diagnostics: async () => MOCK_DB_DIAGNOSTICS,

    get_local_database_state: async () => mockLocalDatabaseState(),

    get_base_health: async () => MOCK_BASE_HEALTH,

    get_kpi_catalog: async () => ({
      entries: MOCK_KPI_CATALOG,
      count: MOCK_KPI_CATALOG.length,
    } satisfies EnergyKPICatalogResponse),

    get_country_kpi_series: async (params) => {
      const kpiIds = Array.isArray(params?.kpi_ids) ? new Set(params.kpi_ids) : null;
      const isoCodes = Array.isArray(params?.iso_codes) ? new Set(params.iso_codes) : null;
      const years = Array.isArray(params?.years) ? new Set(params.years.map(Number)) : null;
      const values = MOCK_COUNTRY_KPI_VALUES.filter((row) => {
        if (kpiIds && !kpiIds.has(row.kpi_id)) return false;
        if (isoCodes && !isoCodes.has(row.iso_code)) return false;
        if (years && !years.has(row.period)) return false;
        return true;
      });
      return { values, count: values.length } satisfies CountryKPISeriesResponse;
    },

    get_country_kpi_compare: async (params) => {
      const kpiId = params?.kpi_id ?? `${COUNTRY_NS}.elec_renewables_share`;
      const year = Number(params?.year ?? YEAR - 1);
      const values = MOCK_COUNTRY_KPI_VALUES.filter((row) => row.kpi_id === kpiId && row.period === year);
      return { kpi_id: kpiId, year, values } satisfies CountryKPICompareResponse;
    },

    get_energy_kpi_health: async () => ({
      last_refresh_at: new Date(Date.now() - 3_600_000).toISOString(),
      last_refresh_status: "success",
      rows_ingested: MOCK_COUNTRY_KPI_VALUES.length,
      rows_conflict: 0,
      is_stale: false,
      owid_snapshot_id: "mock-country-energy-snapshot",
      owid_fetched_at: NOW,
      dq_errors: 0,
      dq_warnings: 0,
      refresh_running: false,
      refresh_error: null,
    } satisfies EnergyKPIHealthResponse),

    refresh_energy_kpis: async () => ({
      status: "success",
      error: null,
      run_id: "mock-country-energy-refresh",
      rows_ingested: MOCK_COUNTRY_KPI_VALUES.length,
    } satisfies EnergyKPIRefreshResult),

    export_country_kpis_excel: async () => ({
      path: null,
      error: "Mock bridge does not write Excel exports.",
    }),

    get_sin_kpi_dashboard: async () => MOCK_SIN_DASHBOARD,

    get_sin_kpi_series: async (params) => {
      const p = params as Record<string, unknown> | undefined;
      const kpiIds = Array.isArray(p?.kpi_ids) ? new Set(p?.kpi_ids as string[]) : null;
      const subsystemCodes = Array.isArray(p?.subsystem_codes) ? new Set(p?.subsystem_codes as string[]) : null;
      const values = MOCK_SIN_VALUES.filter((row) => {
        if (kpiIds && !kpiIds.has(row.kpi_id)) return false;
        if (subsystemCodes && !subsystemCodes.has(row.subsystem_code)) return false;
        if (typeof p?.start_datetime === "string" && row.reference_datetime < p.start_datetime) return false;
        if (typeof p?.end_datetime === "string" && row.reference_datetime > p.end_datetime) return false;
        return true;
      });
      return { values, count: values.length } satisfies SINKPISeriesResponse;
    },

    get_sin_kpi_daily_chart_series: async (params) => {
      const p = params as Record<string, unknown> | undefined;
      const kpiIds = Array.isArray(p?.kpi_ids) ? new Set(p?.kpi_ids as string[]) : null;
      const subsystemCodes = Array.isArray(p?.subsystem_codes) ? new Set(p?.subsystem_codes as string[]) : null;
      const startDatetime = typeof p?.start_datetime === "string" ? p.start_datetime : null;
      const endDatetime = typeof p?.end_datetime === "string" ? p.end_datetime : null;
      const request = {
        kpi_ids: kpiIds ? [...kpiIds] : [],
        subsystem_codes: subsystemCodes ? [...subsystemCodes] : [],
        start_datetime: startDatetime,
        end_datetime: endDatetime,
      };
      if (p && Object.prototype.hasOwnProperty.call(p, "limit")) {
        return {
          values: [],
          count: 0,
          raw_row_count: 0,
          request,
          coverage: { start_date: null, end_date: null },
          generated_at: NOW,
          error: "get_sin_kpi_daily_chart_series does not accept limit",
        } satisfies SINKPIDailyChartSeriesResponse;
      }
      const rawValues = MOCK_SIN_VALUES.filter((row) => {
        if (kpiIds && !kpiIds.has(row.kpi_id)) return false;
        if (subsystemCodes && !subsystemCodes.has(row.subsystem_code)) return false;
        if (startDatetime && row.reference_datetime < startDatetime) return false;
        if (endDatetime && row.reference_datetime > endDatetime) return false;
        return true;
      });
      const groups = new Map<string, typeof rawValues>();
      const rawReaderRowCounts = new Map<string, number>();
      for (const row of rawValues) {
        const referenceDate = row.reference_datetime.slice(0, 10);
        const frequency = MOCK_SIN_FREQUENCY_BY_DATASET[row.source_dataset] ?? "unknown";
        const key = [
          row.kpi_id,
          row.subsystem_code,
          referenceDate,
          row.unit,
          frequency,
          row.source,
          row.source_dataset,
          row.source_field,
          row.snapshot_id,
        ].join("|");
        const rawReaderKey = [row.kpi_id, row.subsystem_code, referenceDate].join("|");
        rawReaderRowCounts.set(rawReaderKey, (rawReaderRowCounts.get(rawReaderKey) ?? 0) + 1);
        groups.set(key, [...(groups.get(key) ?? []), row]);
      }
      const values = [...groups.values()].map((rows) => {
        const first = rows[0];
        const usable = rows.filter((row) => row.value !== null);
        const referenceDate = first.reference_datetime.slice(0, 10);
        const dayStart = `${referenceDate}T00:00:00`;
        const dayEnd = `${referenceDate}T23:59:59.999999`;
        const rawReaderKey = [first.kpi_id, first.subsystem_code, referenceDate].join("|");
        return {
          kpi_id: first.kpi_id,
          subsystem_code: first.subsystem_code,
          subsystem_name: first.subsystem_name,
          reference_date: referenceDate,
          value: usable.length > 0
            ? usable.reduce((sum, row) => sum + (row.value ?? 0), 0) / usable.length
            : null,
          unit: first.unit,
          frequency: MOCK_SIN_FREQUENCY_BY_DATASET[first.source_dataset] ?? "unknown",
          raw_row_count: rows.length,
          contributing_observation_count: usable.length,
          sources: [...new Set(rows.map((row) => row.source))],
          source_datasets: [...new Set(rows.map((row) => row.source_dataset))],
          source_fields: [...new Set(rows.map((row) => row.source_field))],
          data_quality_statuses: [...new Set(rows.map((row) => row.data_quality_status))],
          snapshot_ids: [...new Set(rows.map((row) => row.snapshot_id))],
          aggregation: "daily_mean_non_null",
          formula: "mean(normalized_value where normalized_value is not null)",
          calculated_at: NOW,
          raw_drilldown: {
            method: "get_sin_kpi_series",
            kpi_ids: [first.kpi_id],
            subsystem_codes: [first.subsystem_code],
            start_datetime: startDatetime && startDatetime > dayStart ? startDatetime : dayStart,
            end_datetime: endDatetime && endDatetime < dayEnd ? endDatetime : dayEnd,
            unit_context: first.unit,
            raw_reader_row_count: rawReaderRowCounts.get(rawReaderKey) ?? 0,
          },
        };
      });
      return {
        values,
        count: values.length,
        raw_row_count: rawValues.length,
        request,
        coverage: {
          start_date: values.at(0)?.reference_date ?? null,
          end_date: values.at(-1)?.reference_date ?? null,
        },
        generated_at: NOW,
      } satisfies SINKPIDailyChartSeriesResponse;
    },

    get_sin_kpi_health: async () => ({
      last_refresh_at: new Date(Date.now() - 3_600_000).toISOString(),
      last_refresh_status: "partial",
      rows_ingested: MOCK_SIN_VALUES.length,
      latest_reference_datetime: MOCK_SIN_DASHBOARD.latest_reference_datetime,
      is_stale: false,
      dq_errors: 0,
      dq_warnings: 1,
      refresh_running: false,
      refresh_error: null,
    } satisfies SINKPIHealthResponse),

    refresh_sin_kpis: async () => ({
      status: "partial",
      error: null,
      rows_inserted: MOCK_SIN_VALUES.length,
      rows_read: MOCK_SIN_VALUES.length,
      snapshots: 5,
    }),

    get_energy_mart_status: async () => ({
      db_path: "mock://energy_kpis.db",
      db_size_bytes: 36_493_611_008,
      source: {
        table: "ccee_plant_parcel_hourly",
        row_estimate: 75_832_752,
        max_rowid: 75_832_752,
        latest_reference: `${YEAR}-04-30T23:00:00`,
        latest_reference_month: `${YEAR}-04`,
        count_method: "MAX(rowid)",
      },
      marts: {
        plant_parcel_daily_generation_mart: {
          mart_name: "plant_parcel_daily_generation_mart",
          status: "success",
          rebuilt_at: NOW,
          row_count_current: 2_779_986,
          period_start_current: `${YEAR - 2}-03`,
          period_end_current: `${YEAR}-04`,
          period_count_current: 26,
          parcel_count_current: 3991,
          source_observations_current: 66_719_664,
          is_current_for_latest_source_month: true,
        },
        plant_parcel_hourly_preview_mart: {
          mart_name: "plant_parcel_hourly_preview_mart",
          status: "success",
          rebuilt_at: NOW,
          row_count_current: 188_496,
          period_start_current: `${YEAR}-04`,
          period_end_current: `${YEAR}-04`,
          parcel_count_current: 3927,
        },
        plant_parcel_source_submarket_monthly_mart: {
          mart_name: "plant_parcel_source_submarket_monthly_mart",
          status: "success",
          rebuilt_at: NOW,
          row_count_current: 180,
          period_start_current: `${YEAR - 2}-03`,
          period_end_current: `${YEAR}-04`,
          period_count_current: 26,
          generation_source_count_current: 8,
          submarket_count_current: 4,
          grouped_parcel_count_current: 19_200,
          source_observations_current: 66_719_664,
        },
      },
      recommended_daily_rebuild_month: `${YEAR}-04`,
      notes: ["Mock mart status. No local database is modified."],
      rebuild: { status: "idle", error: null },
      write_mode: "read-write",
    } satisfies EnergyMartStatusResponse),

    start_energy_mart_rebuild: async (params) => ({
      status: "success",
      error: null,
      rebuild_id: "mock-energy-mart-rebuild",
      started_at: NOW,
      finished_at: new Date(Date.now() + 250).toISOString(),
      reference_months: params?.reference_month ? [params.reference_month] : null,
      rebuild_daily: params?.rebuild_daily ?? true,
      rebuild_preview: params?.rebuild_preview ?? false,
      rebuild_source_submarket: params?.rebuild_source_submarket ?? true,
      result: {
        build_version: "plant_hourly_marts_v1",
        daily_rows: 117_810,
        preview_rows: params?.rebuild_preview ? 188_496 : null,
        source_submarket_rows: 8,
        elapsed_ms: 250,
      },
    } satisfies EnergyMartRebuildState),

    get_plant_parcel_source_statuses: async () => MOCK_PLANT_SOURCES,

    get_plant_parcel_catalog: async (params) => {
      const p = params as Record<string, unknown> | undefined;
      const search = String(p?.search ?? "").toLowerCase();
      const entityType = String(p?.entity_type ?? "");
      const generationSource = String(p?.generation_source ?? "");
      const submarket = String(p?.submarket ?? "");
      const uf = String(p?.uf ?? "");
      const limit = Number(p?.limit ?? 100);
      const offset = Number(p?.offset ?? 0);
      const records = MOCK_PLANT_RECORDS.filter((row) => {
        if (search) {
          const haystack = [
            row.entity_id,
            row.plant_parcel_code,
            row.plant_parcel_acronym,
            row.ceg,
            row.plant_name,
            row.agent_name,
          ].join(" ").toLowerCase();
          if (!haystack.includes(search)) return false;
        }
        if (entityType && row.entity_type !== entityType) return false;
        if (generationSource && row.generation_source !== generationSource) return false;
        if (submarket && row.submarket !== submarket) return false;
        if (uf && row.uf !== uf) return false;
        return true;
      });
      return {
        records: records.slice(offset, offset + limit),
        count: records.slice(offset, offset + limit).length,
        total: records.length,
        limit,
        offset,
        facets: {
          entity_type: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.entity_type))],
          generation_source: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.generation_source).filter(Boolean))],
          submarket: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.submarket).filter(Boolean))],
          uf: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.uf).filter(Boolean))],
          data_status: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.data_status))],
        },
      } satisfies PlantParcelCatalogResponse;
    },

    get_plant_parcel_detail: async (params) => ({
      ...MOCK_PLANT_DETAIL,
      entity_id: params?.entity_id ?? MOCK_PLANT_DETAIL.entity_id,
    }),

    get_fuel_distribution_product_year_summary: async (params) => {
      const product = String(params?.product ?? "").trim().toUpperCase();
      const startYear = params?.start_year == null ? null : Number(params.start_year);
      const endYear = params?.end_year == null ? null : Number(params.end_year);
      const rows = [
        { source_dataset_id: "anp_fuel_sales_state_month", product: "GASOLINA C", year: YEAR - 1, unit: "m3", total_value: 44_821_000, source_row_count: 324 },
        { source_dataset_id: "anp_fuel_sales_state_month", product: "GASOLINA C", year: YEAR, unit: "m3", total_value: 21_654_000, source_row_count: 162 },
        { source_dataset_id: "anp_diesel_type_state_month", product: "ÓLEO DIESEL", year: YEAR - 1, unit: "m3", total_value: 63_210_000, source_row_count: 324 },
        { source_dataset_id: "anp_ethanol_municipality_year", product: "ETANOL HIDRATADO", year: YEAR - 1, unit: "liters", total_value: 18_940_000_000, source_row_count: 5_102 },
      ].filter((row) => {
        if (product && row.product !== product) return false;
        if (startYear != null && row.year < startYear) return false;
        if (endYear != null && row.year > endYear) return false;
        return true;
      });
      return { source: "sqlite_mart", items: rows, count: rows.length } satisfies FuelDistributionProductYearSummaryResponse;
    },

    get_fuel_distribution_state_month_series: async (params) => {
      const product = String(params?.product ?? "GASOLINA C").trim().toUpperCase() || "GASOLINA C";
      const state = String(params?.state ?? "SÃO PAULO").trim().toUpperCase() || "SÃO PAULO";
      const rows = ["01", "02", "03", "04", "05", "06"].map((month, index) => ({
        source_dataset_id: String(params?.source_dataset_id ?? "anp_fuel_sales_state_month"),
        product,
        reference_period: `${YEAR}-${month}`,
        year: YEAR,
        month: index + 1,
        region: "REGIÃO SUDESTE",
        state,
        unit: "m3",
        total_value: 760_000 + index * 22_500,
        source_row_count: 1,
      }));
      return { source: "sqlite_mart", items: rows, count: rows.length } satisfies FuelDistributionStateMonthSeriesResponse;
    },

    get_fuel_distribution_detail: async (params) => {
      const rows = [
        { reference_period: `${params?.year ?? YEAR}-01`, region: "REGIÃO SUDESTE", state: "SÃO PAULO", municipality: null, product: params?.product ?? "GASOLINA C", unit: "m3", value: 799_343.74, source_dataset_id: params?.source_dataset_id },
        { reference_period: `${params?.year ?? YEAR}-02`, region: "REGIÃO SUDESTE", state: "SÃO PAULO", municipality: null, product: params?.product ?? "GASOLINA C", unit: "m3", value: 812_904.12, source_dataset_id: params?.source_dataset_id },
        { reference_period: `${params?.year ?? YEAR}-03`, region: "REGIÃO SUDESTE", state: "SÃO PAULO", municipality: null, product: params?.product ?? "GASOLINA C", unit: "m3", value: 844_010.52, source_dataset_id: params?.source_dataset_id },
      ];
      return {
        source: "managed_parquet",
        dataset_id: "fuel_distribution_sector_intake",
        source_dataset_id: params?.source_dataset_id,
        product: params?.product,
        year: params?.year,
        rows,
        count: rows.length,
        total_matching_rows: rows.length,
        limit: params?.limit ?? 500,
        offset: params?.offset ?? 0,
        truncated: false,
      } satisfies FuelDistributionDetailResponse;
    },

    get_plant_parcel_chart_data: async (params) => {
      const freq = params.frequency || "monthly";
      if (freq === "monthly") {
        const periods = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"];
        return {
          series: [
            { id: "generation_mwmed", label: "Generation (MWmed)", unit: "number", axis: "left", type: "line", points: [42, 45, 40, 45, 48], latest: 48 },
            { id: "generation_gwh", label: "Generation (GWh)", unit: "number", axis: "left", type: "line", points: [31.2, 30.2, 29.8, 32.4, 35.7], latest: 35.7 },
            { id: "capacity_mw", label: "Capacity (MW)", unit: "number", axis: "right", type: "line", points: [100, 100, 100, 100, 100], latest: 100 },
            { id: "physical_guarantee_mwmed", label: "Physical Guarantee (MWmed)", unit: "number", axis: "right", type: "line", points: [50, 50, 50, 50, 50], latest: 50 },
            { id: "capacity_factor_pct", label: "Capacity Factor (%)", unit: "pct", axis: "left", type: "line", points: [42, 45, 40, 45, 48], latest: 48 }
          ],
          periods,
          frequency: freq,
          entity_type: params.entity_type || "ccee_plant_parcel",
          entity_id: params.entity_id,
        };
      } else if (freq === "daily") {
        const periods = Array.from({ length: 30 }, (_, i) => `2026-05-${String(i + 1).padStart(2, "0")}`);
        const pointsGen = Array.from({ length: 30 }, () => Math.round(40 + Math.random() * 20));
        return {
          series: [
            { id: "generation_mwh", label: "Generation (MWh)", unit: "number", axis: "left", type: "line", points: pointsGen, latest: pointsGen[29] },
            { id: "verified_generation_mwh", label: "Verified Generation ONS (MWh)", unit: "number", axis: "left", type: "line", points: pointsGen.map(p => p - 1), latest: pointsGen[29] - 1 },
            { id: "verified_availability_mwh", label: "Verified Availability (MWh)", unit: "number", axis: "right", type: "line", points: pointsGen.map(() => 98), latest: 98 },
            { id: "unavailability_mwh", label: "Unavailability (MWh)", unit: "number", axis: "right", type: "line", points: pointsGen.map(() => 2), latest: 2 },
            { id: "capacity_factor_pct", label: "Capacity Factor (%)", unit: "pct", axis: "left", type: "line", points: pointsGen.map(p => Math.round((p / 2400) * 100)), latest: Math.round((pointsGen[29] / 2400) * 100) }
          ],
          periods,
          frequency: freq,
          entity_type: params.entity_type || "ccee_plant_parcel",
          entity_id: params.entity_id,
        };
      } else { // hourly
        const periods = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, "0")}h`);
        const pointsGen = Array.from({ length: 24 }, () => Math.round(30 + Math.random() * 40));
        return {
          series: [
            { id: "generation_mwh", label: "Generation (MWh)", unit: "number", axis: "left", type: "line", points: pointsGen, latest: pointsGen[23] },
            { id: "verified_generation_mwh", label: "Verified Generation ONS (MWh)", unit: "number", axis: "left", type: "line", points: pointsGen.map(p => p - 1), latest: pointsGen[23] - 1 },
            { id: "verified_availability_mwh", label: "Verified Availability (MWh)", unit: "number", axis: "right", type: "line", points: pointsGen.map(() => 98), latest: 98 },
            { id: "unavailability_mwh", label: "Unavailability (MWh)", unit: "number", axis: "right", type: "line", points: pointsGen.map(() => 2), latest: 2 },
            { id: "capacity_factor_pct", label: "Capacity Factor (%)", unit: "pct", axis: "left", type: "line", points: pointsGen.map(p => Math.round((p / 100) * 100)), latest: Math.round((pointsGen[23] / 100) * 100) }
          ],
          periods,
          frequency: freq,
          entity_type: params.entity_type || "ccee_plant_parcel",
          entity_id: params.entity_id,
        };
      }
    },

    refresh_plant_parcel_source: async (params) => ({
      status: "success",
      error: null,
      source_id: params?.source_id,
      refresh_id: "mock-plant-refresh",
      rows_inserted: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      rows_read: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      period_start: params?.year_month ?? (params?.year ? `${params.year}-01` : null),
      period_end: params?.year_month ?? (params?.year ? `${params.year}-12` : null),
    } satisfies PlantParcelRefreshResult),

    select_plant_parcel_import_file: async (params) => ({
      ok: true,
      canceled: false,
      file_path: params?.source_id === "ccee_plant_generation_hourly"
        ? "C:\\mock\\geracao_horaria_usina_202605.csv.gz"
        : "C:\\mock\\parcela_usina_montante_mensal_2026.csv",
      file_name: params?.source_id === "ccee_plant_generation_hourly"
        ? "geracao_horaria_usina_202605.csv.gz"
        : "parcela_usina_montante_mensal_2026.csv",
      file_paths: params?.source_id === "ccee_plant_generation_hourly"
        ? ["C:\\mock\\geracao_horaria_usina_202605.csv.gz"]
        : ["C:\\mock\\parcela_usina_montante_mensal_2025.csv", "C:\\mock\\parcela_usina_montante_mensal_2026.csv"],
      file_names: params?.source_id === "ccee_plant_generation_hourly"
        ? ["geracao_horaria_usina_202605.csv.gz"]
        : ["parcela_usina_montante_mensal_2025.csv", "parcela_usina_montante_mensal_2026.csv"],
    }),

    import_plant_parcel_source_file: async (params: any) => ({
      status: "success",
      error: null,
      warning: null,
      source_id: params?.source_id,
      refresh_id: "mock-manual-import",
      import_id: "mock-manual-import",
      import_mode: "manual_file",
      rows_inserted: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      rows_read: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      source_rows: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      parsed_rows: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      rows_skipped: 0,
      file_size_bytes: params?.source_id === "ccee_plant_generation_hourly" ? 1_048_576 : 4096,
      file_hash: "mock-sha256",
      file_type: params?.source_id === "ccee_plant_generation_hourly" ? "gzip" : "csv",
      original_file_name: params?.original_file_name ?? null,
      requested_period: params?.expected_period ?? null,
      detected_period: params?.source_id === "ccee_plant_generation_hourly" ? "2026-05" : "2026-01..2026-05",
      period_start: params?.expected_period ?? null,
      period_end: params?.expected_period ?? null,
    }),

    get_companies: async (params) => {
      const p = params as Record<string, unknown>;
      const search = String(p?.search ?? "").toLowerCase();
      const sectorSlug = String(p?.sector_slug ?? "");
      const page = Number(p?.page ?? 1);
      const pageSize = Number(p?.page_size ?? 50);

      let items = FIXTURE_COMPANIES.map(toDirectoryItem);
      if (search) items = items.filter((c) => c.company_name.toLowerCase().includes(search) || (c.ticker_b3 ?? "").toLowerCase().includes(search));
      if (sectorSlug) items = items.filter((c) => c.sector_slug === sectorSlug);

      if (p?.sort_by) {
        const valueFor = (item: CompanyDirectoryItem): string | number | null => {
          switch (p.sort_by) {
            case "company": return item.company_name.toLowerCase();
            case "ticker": return item.ticker_b3?.trim().toLowerCase() || null;
            case "sector": return item.gics_sector?.trim().toLowerCase() || null;
            case "industryGroup": return item.gics_industry_group?.trim().toLowerCase() || null;
            case "marketCap": return item.market_cap_brl ?? null;
            case "data": return Number(item.has_financial_data);
            case "years": return item.anos_disponiveis.length;
            case "cvm": return item.cd_cvm;
            default: throw new Error("Invalid company sort column");
          }
        };
        const direction = p.sort_direction ?? "desc";
        if (direction !== "asc" && direction !== "desc") throw new Error("Invalid company sort direction");
        const factor = direction === "asc" ? 1 : -1;
        items.sort((a, b) => {
          const left = valueFor(a), right = valueFor(b);
          if (left === null) return right === null ? a.cd_cvm - b.cd_cvm : 1;
          if (right === null) return -1;
          return (left < right ? -factor : left > right ? factor : a.cd_cvm - b.cd_cvm);
        });
      }
      const totalItems = items.length;
      const totalPages = Math.ceil(totalItems / pageSize) || 1;
      const start = (page - 1) * pageSize;
      const pageItems = items.slice(start, start + pageSize);

      const result: CompanyDirectoryPage = {
        items: pageItems,
        pagination: {
          page,
          page_size: pageSize,
          total_items: totalItems,
          total_pages: totalPages,
          has_next: page < totalPages,
          has_previous: page > 1,
        },
        applied_filters: { search: String(p?.search ?? ""), sector: sectorSlug || null },
      };
      return result;
    },

    get_company_info: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const c = FIXTURE_COMPANIES.find((x) => x.cd_cvm === cdCvm);
      if (!c) {
        return {
          cd_cvm: cdCvm,
          company_name: "Unknown",
          is_active: true,
          nome_comercial: null,
          cnpj: null,
          ticker_b3: null,
          company_type: null,
          setor_cvm: null,
          has_local_financial_reports: false,
          has_readable_current_data: false,
          readable_years_count: 0,
          latest_readable_year: null,
          readable_financial_periods_count: 0,
          latest_financial_period_label: null,
          latest_financial_period_display: null,
          latest_financial_period_type: null,
          latest_financial_period_year: null,
          latest_financial_period_quarter: null,
          read_model_updated_at: null,
          read_availability_code: null,
          read_availability_message: null,
          not_found: true,
        } satisfies CompanyInfo;
      }
      return {
        cd_cvm: c.cd_cvm,
        company_name: c.company_name,
        is_active: true,
        nome_comercial: c.company_name,
        cnpj: c.cnpj,
        ticker_b3: c.ticker_b3,
        company_type: "SA",
        setor_cvm: c.sector_name,
        sector_name: c.sector_name,
        sector_slug: c.sector_slug,
        has_local_financial_reports: c.has_financial_data,
        has_readable_current_data: c.has_financial_data,
        readable_years_count: c.anos_disponiveis.length,
        latest_readable_year: c.anos_disponiveis.at(-1) ?? null,
        readable_financial_periods_count: c.anos_disponiveis.length,
        latest_financial_period_label: c.anos_disponiveis.at(-1)?.toString() ?? null,
        latest_financial_period_display: c.anos_disponiveis.at(-1)
          ? `FY${c.anos_disponiveis.at(-1)}`
          : null,
        latest_financial_period_type: c.has_financial_data ? "annual" : null,
        latest_financial_period_year: c.anos_disponiveis.at(-1) ?? null,
        latest_financial_period_quarter: null,
        read_model_updated_at: c.has_financial_data
          ? new Date(Date.now() - 86_400_000).toISOString()
          : null,
        read_availability_code: c.has_financial_data ? "readable" : "no_data",
        read_availability_message: c.has_financial_data ? "Data available" : "No financial data",
        gics_sector: c.cd_cvm === 9512 ? "Energy" : c.cd_cvm === 14311 ? "Materials" : c.cd_cvm === 14673 ? "Consumer Staples" : null,
        gics_sector_slug: c.cd_cvm === 9512 ? "energy" : c.cd_cvm === 14311 ? "materials" : c.cd_cvm === 14673 ? "consumer-staples" : null,
        gics_industry_group: null,
        gics_industry: c.cd_cvm === 9512 ? "Oil, Gas & Consumable Fuels" : null,
        gics_sub_industry: c.cd_cvm === 9512 ? "Integrated Oil & Gas" : c.cd_cvm === 14311 ? "Steel" : c.cd_cvm === 14673 ? "Brewers" : null,
      } satisfies CompanyInfo;
    },

    get_company_financial_readiness: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const company = FIXTURE_COMPANIES.find((item) => item.cd_cvm === cdCvm);
      const years = company?.anos_disponiveis ?? [];
      const hasFinancialData = Boolean(company?.has_financial_data);
      const timestamp = hasFinancialData
        ? new Date(Date.now() - 86_400_000).toISOString()
        : null;

      return {
        cd_cvm: cdCvm,
        source_class: "official_reported",
        source_label: "Mock fixture · CVM DFP/ITR filings",
        availability_state: hasFinancialData ? "ready" : "missing",
        freshness_state: hasFinancialData ? "fresh" : "unknown",
        refresh_state: hasFinancialData ? "successful" : "not_recorded",
        has_local_financial_reports: hasFinancialData,
        available_periods: years.map((year) => ({
          period_label: `FY${year}`,
          period_display: `FY ${year}`,
          period_type: "annual",
          period_year: year,
          period_quarter: null,
        })),
        local_read_model_updated_at: timestamp,
        last_successful_refresh_at: timestamp,
        latest_local_evidence_at: timestamp,
        last_refresh_error: null,
        financial_export_eligible: hasFinancialData && years.length > 0,
        exportable_years: hasFinancialData ? years : [],
        refresh_available: true,
      };
    },

    get_company_years: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const c = FIXTURE_COMPANIES.find((x) => x.cd_cvm === cdCvm);
      return { years: c?.anos_disponiveis ?? [] } satisfies CompanyYearsResult;
    },

    get_company_statement_years: async (params) => {
      const cdCvm = Number(params?.cd_cvm ?? 0);
      return { years: FIXTURE_COMPANIES.find((company) => company.cd_cvm === cdCvm)?.anos_disponiveis ?? [] };
    },

    get_company_kpis: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const c = FIXTURE_COMPANIES.find((x) => x.cd_cvm === cdCvm);
      if (!c?.has_financial_data) {
        return { cd_cvm: cdCvm, years: [], annual: { columns: [], rows: [] }, quarterly: { columns: [], rows: [] }, error: "No financial data available" };
      }
      return mockKpis(cdCvm, c.anos_disponiveis);
    },

    get_company_statement: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const statementType = String(p?.statement_type ?? p?.stmt ?? "DRE");
      const c = FIXTURE_COMPANIES.find((x) => x.cd_cvm === cdCvm);
      if (!c?.has_financial_data) {
        return { cd_cvm: cdCvm, statement_type: statementType, years: [], table: { columns: [], rows: [] }, exclude_conflicts: true, error: "No financial data" } satisfies StatementMatrix;
      }
      return mockStatement(cdCvm, statementType);
    },

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

    get_company_filters: async () => ({
      sectors: SECTOR_SLUGS.map((s) => ({
        sector_name: s.name,
        sector_slug: s.slug,
        company_count: s.count,
        gics_sector: null,
        gics_sector_slug: null,
        gics_sub_industry: null,
      })),
    } satisfies CompanyFiltersResponse),
    get_sectors: async (params) => {
      const p = params as Record<string, unknown>;
      const groupBy = String(p?.group_by ?? "sector");

      if (groupBy === "sub_sector") {
        const subSectors = [
          { name: "Integrated Oil & Gas", slug: "integrated-oil-gas", parent: "Energy", parentSlug: "energy" },
          { name: "Steel", slug: "steel", parent: "Materials", parentSlug: "materials" },
          { name: "Brewers", slug: "brewers", parent: "Consumer Staples", parentSlug: "consumer-staples" },
          { name: "Alternative Carriers", slug: "alternative-carriers", parent: "Communication Services", parentSlug: "communication-services" },
        ];
        return {
          items: subSectors.map((s) => ({
            sector_name: s.name,
            sector_slug: s.slug,
            company_count: 1,
            latest_year: YEAR - 1,
            snapshot: { roe: 10, mg_ebit: 15, mg_liq: 7 },
            sub_industries: [],
            sub_industry_breakdown: [],
            group_type: "sub_sector",
            parent_sector_name: s.parent,
            parent_sector_slug: s.parentSlug,
            companies: [],
          })),
        } satisfies SectorDirectoryResponse;
      }

      if (groupBy === "cvm_sector") {
        return {
          items: SECTOR_SLUGS.map((s) => ({
            sector_name: s.name,
            sector_slug: s.slug,
            company_count: s.count,
            latest_year: YEAR - 1,
            snapshot: { roe: null, mg_ebit: null, mg_liq: null },
            sub_industries: [],
            sub_industry_breakdown: [],
            group_type: "cvm_sector",
            parent_sector_name: null,
            parent_sector_slug: null,
            companies: [],
          })),
        } satisfies SectorDirectoryResponse;
      }

      // Default to "sector" (GICS Sectors)
      const gicsSectors = [
        { name: "Energy", slug: "energy" },
        { name: "Materials", slug: "materials" },
        { name: "Consumer Staples", slug: "consumer-staples" },
        { name: "Communication Services", slug: "communication-services" },
      ];
      return {
        items: gicsSectors.map((s) => ({
          sector_name: s.name,
          sector_slug: s.slug,
          company_count: 1,
          latest_year: YEAR - 1,
          snapshot: { roe: 12, mg_ebit: 18, mg_liq: 8 },
          sub_industries: [],
          sub_industry_breakdown: [],
          group_type: "sector",
          parent_sector_name: null,
          parent_sector_slug: null,
          companies: [],
        })),
      } satisfies SectorDirectoryResponse;
    },

    get_sector_detail: async (params) => {
      const p = params as Record<string, unknown>;
      const slug = String(p?.sector_slug ?? "");
      const sector = SECTOR_SLUGS.find((s) => s.slug === slug);
      const companies = FIXTURE_COMPANIES.filter((c) => c.sector_slug === slug);
      return {
        sector_name: sector?.name ?? slug,
        sector_slug: slug,
        company_count: companies.length,
        available_years: [YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1],
        selected_year: YEAR - 1,
        yearly_overview: [YEAR - 4, YEAR - 3, YEAR - 2, YEAR - 1].map((y) => ({ year: y, roe: 12, mg_ebit: 18, mg_liq: 8 })),
        companies: companies.map((c) => ({
          cd_cvm: c.cd_cvm,
          company_name: c.company_name,
          ticker_b3: c.ticker_b3,
          gics_sub_industry: null,
          roe: 12,
          mg_ebit: 18,
          mg_liq: 8,
        })),
        parent_sector_name: null,
        parent_sector_slug: null,
        not_found: !sector,
      } satisfies SectorDetailResponse;
    },

    get_sub_sector_detail: async (params) => {
      // Delegate to sector detail for mock purposes
      const p = params as Record<string, unknown>;
      const slug = String(p?.sector_slug ?? "");
      const sector = SECTOR_SLUGS.find((s) => s.slug === slug);
      return {
        sector_name: sector?.name ?? slug,
        sector_slug: slug,
        company_count: 0,
        available_years: [YEAR - 1],
        selected_year: YEAR - 1,
        yearly_overview: [],
        companies: [],
        parent_sector_name: null,
        parent_sector_slug: null,
      } satisfies SectorDetailResponse;
    },

    get_onboarding_state: async () => MOCK_ONBOARDING,

    complete_onboarding_setup: async () => ({ ...MOCK_ONBOARDING, setup_status: "completed" }),

    skip_onboarding_setup: async () => ({ ...MOCK_ONBOARDING, should_show: false }),

    get_data_update_settings: async () => MOCK_UPDATE_SETTINGS,

    save_data_update_settings: async (params) => ({
      ...MOCK_UPDATE_SETTINGS,
      ...(params as object),
    }),

    get_company_universe_selection: async (params) => {
      const p = params as Record<string, unknown>;
      const preset = String(p?.preset ?? "top_200");
      const countMap: Record<string, number> = { top_100: 100, top_200: 200, top_500: 500, all: 600 };
      const count = countMap[preset] ?? 200;
      return {
        preset: preset as "top_200",
        selected_count: count,
        company_ids: FIXTURE_COMPANIES.map((c) => c.cd_cvm),
        source: "mock-fixture",
        source_date: `${YEAR - 1}-01-01`,
        warning: null,
        companies: FIXTURE_COMPANIES.slice(0, Math.min(count, 6)).map((c) => ({
          cd_cvm: c.cd_cvm,
          ticker: c.ticker_b3,
          company_name: c.company_name,
          market_cap: null,
          market_cap_rank: null,
          source: "mock",
          source_date: null,
        })),
      };
    },

    get_refresh_status: async (params) => {
      const p = params as Record<string, unknown>;
      const jobId = p?.job_id;
      if (jobId === MOCK_JOB_RUNNING.job_id) return MOCK_JOB_RUNNING;
      if (jobId === MOCK_JOB_COMPLETED.job_id) return MOCK_JOB_COMPLETED;
      const result: RefreshJobListResponse = { items: [MOCK_JOB_RUNNING, MOCK_JOB_COMPLETED] };
      return result;
    },

    start_data_update: async () => ({
      status: "accepted",
      job_id: "mock-job-started-" + Date.now(),
      accepted_at: NOW,
      queued: 200,
      message: "[mock] Data update dispatched",
      is_retry_allowed: false,
    }),

    request_refresh: async () => ({
      status: "accepted",
      job_id: "mock-refresh-" + Date.now(),
      accepted_at: NOW,
      queued: 1,
      message: "[mock] Company refresh dispatched",
      is_retry_allowed: false,
    }),

    cancel_refresh: async () => ({ ok: true, message: "[mock] Job cancelled" }),

    reset_local_database: async () => ({
      ok: true,
      action: "restart_current",
      message: "[mock] Database state reset",
      backup_path: "[mock] /dev/mock/backup",
      backup_items: ["[mock] cvm_financials.db.bak"],
      removed: ["onboarding_state.json", "refresh_jobs.json"],
      active_job_id: null,
    }),

    start_onboarding_setup: async () => ({
      status: "accepted",
      job_id: "mock-setup-" + Date.now(),
      accepted_at: NOW,
      queued: 100,
      is_retry_allowed: false,
    }),

    check_update: async () => ({ available: false, version: "0.29.1" }),

    apply_update: async () => ({ started: false, error: "[mock] Software update not available in mock mode" }),

    get_update_progress: async () => ({ status: "idle", percent: 0, error: null }),

    snooze_update: async () => ({ ok: true }),

    open_status_path: async () => ({
      ok: false,
      kind: "data",
      path: null,
      error: "[mock] Cannot open filesystem paths in browser mode",
    }),

    get_output_dir: async () => ({
      path: "[mock] /dev/mock/output",
      exists: true,
    }),

    export_company_excel: async () => ({
      ok: false,
      error: "[mock] Excel export not available in browser/mock mode",
    }),

    open_company_excel_mapping_window: async () => ({
      ok: false,
      error: "[mock] Excel Mapping windows are not available in browser/mock mode",
    }),

    export_company_market_history_excel: async () => ({
      ok: false,
      error: "[mock] Market-history Excel export not available in browser/mock mode",
    }),

    get_excel_mapping_workspace: async () => ({
      ok: true,
      company: {
        cd_cvm: 9512,
        company_name: "PETROBRAS PN",
        nome_comercial: "PETROBRAS PN",
        cnpj: "33.000.167/0001-01",
        ticker_b3: "PETR4",
        is_active: true,
        company_type: "SA",
        setor_cvm: "Petróleo e Gás",
        sector_name: "Petróleo e Gás",
        sector_slug: "petroleo-e-gas",
        has_local_financial_reports: true,
        has_readable_current_data: true,
        readable_years_count: 5,
        latest_readable_year: YEAR - 1,
        readable_financial_periods_count: 5,
        latest_financial_period_label: String(YEAR - 1),
        latest_financial_period_display: `FY${YEAR - 1}`,
        latest_financial_period_type: "annual",
        latest_financial_period_year: YEAR - 1,
        latest_financial_period_quarter: null,
        read_model_updated_at: NOW,
        read_availability_code: "readable",
        read_availability_message: "Data available",
      },
      period_scope_label: "Last 5 years",
      presets: [
        {
          preset_id: "system:default",
          name: "Default",
          description: "System default model mapping shipped with CVMAnalytics.",
          origin: "system",
          default_mapping_version: "model-mapping-v1",
          sector_tags: [],
          notes: null,
          validation_status: null,
          created_at: null,
          updated_at: null,
          company_default: true,
        },
      ],
      active_preset_id: "system:default",
      company_default_preset_id: "system:default",
      mapping: {
        preset_id: "system:default",
        name: "Default",
        description: "System default model mapping shipped with CVMAnalytics.",
        origin: "system",
        default_mapping_version: "model-mapping-v1",
        sector_tags: [],
        notes: null,
        validation_status: null,
        created_at: null,
        updated_at: null,
        entries: [
          {
            target_id: "DRE:3.01",
            target_label: "Revenue",
            group: "Income Statement",
            statement_type: "DRE",
            display_order: 0,
            indent_level: 0,
            required: true,
            operation: "direct",
            is_subtotal: true,
            sources: [
              {
                statement_type: "DRE",
                line_id_base: "3.01",
                cd_conta: "3.01",
                label_snapshot: "Revenue",
                sign: 1,
                position: 0,
              },
            ],
          },
          {
            target_id: "DRE:3.05",
            target_label: "Operating Result (EBIT)",
            group: "Income Statement",
            statement_type: "DRE",
            display_order: 1,
            indent_level: 0,
            required: true,
            operation: "direct",
            is_subtotal: true,
            sources: [{
              statement_type: "DRE",
              line_id_base: "3.05",
              cd_conta: "3.05",
              label_snapshot: "Operating Result (EBIT)",
              sign: 1,
              position: 0,
            }],
          },
          {
            target_id: "BPA:1",
            target_label: "Total Assets",
            group: "Assets",
            statement_type: "BPA",
            display_order: 2,
            indent_level: 0,
            required: true,
            operation: "direct",
            is_subtotal: true,
            sources: [{
              statement_type: "BPA",
              line_id_base: "1",
              cd_conta: "1",
              label_snapshot: "Total Assets",
              sign: 1,
              position: 0,
            }],
          },
          {
            target_id: "BPP:2.03",
            target_label: "Equity",
            group: "Liabilities & Equity",
            statement_type: "BPP",
            display_order: 3,
            indent_level: 1,
            required: false,
            operation: "direct",
            is_subtotal: true,
            sources: [{
              statement_type: "BPP",
              line_id_base: "2.03",
              cd_conta: "2.03",
              label_snapshot: "Equity",
              sign: 1,
              position: 0,
            }],
          },
          {
            target_id: "DFC:6.01",
            target_label: "Cash Flow from Operations (CFO)",
            group: "Cash Flow Statement",
            statement_type: "DFC",
            display_order: 4,
            indent_level: 0,
            required: true,
            operation: "direct",
            is_subtotal: true,
            sources: [{
              statement_type: "DFC",
              line_id_base: "6.01",
              cd_conta: "6.01",
              label_snapshot: "Cash Flow from Operations (CFO)",
              sign: 1,
              position: 0,
            }],
          },
        ],
      },
      preview_periods: ["2021", "2022", "2023", "2024", "2025"],
      model_preview_rows: [
        {
          target_id: "DRE:3.01",
          target_label: "Revenue",
          group: "Income Statement",
          statement_type: "DRE",
          display_order: 0,
          indent_level: 0,
          required: true,
          operation: "direct",
          is_subtotal: true,
          source_count: 1,
          warning_count: 0,
          error_count: 0,
          values_by_period: { "2021": 412000, "2022": 641000, "2023": 512000, "2024": 489000, "2025": 511000 },
        },
        {
          target_id: "DRE:3.05",
          target_label: "Operating Result (EBIT)",
          group: "Income Statement",
          statement_type: "DRE",
          display_order: 1,
          indent_level: 0,
          required: true,
          operation: "direct",
          is_subtotal: true,
          source_count: 1,
          warning_count: 1,
          error_count: 0,
          values_by_period: { "2021": 124000, "2022": 257000, "2023": 166000, "2024": 151000, "2025": 162000 },
        },
        {
          target_id: "BPA:1",
          target_label: "Total Assets",
          group: "Assets",
          statement_type: "BPA",
          display_order: 2,
          indent_level: 0,
          required: true,
          operation: "direct",
          is_subtotal: true,
          source_count: 1,
          warning_count: 0,
          error_count: 0,
          values_by_period: { "2021": 987000, "2022": 976000, "2023": 1048000, "2024": 1088000, "2025": 1101000 },
        },
        {
          target_id: "BPP:2.03",
          target_label: "Equity",
          group: "Liabilities & Equity",
          statement_type: "BPP",
          display_order: 3,
          indent_level: 1,
          required: false,
          operation: "direct",
          is_subtotal: true,
          source_count: 1,
          warning_count: 0,
          error_count: 0,
          values_by_period: { "2021": 372000, "2022": 388000, "2023": 405000, "2024": 421000, "2025": 430000 },
        },
        {
          target_id: "DFC:6.01",
          target_label: "Cash Flow from Operations (CFO)",
          group: "Cash Flow Statement",
          statement_type: "DFC",
          display_order: 4,
          indent_level: 0,
          required: true,
          operation: "direct",
          is_subtotal: true,
          source_count: 1,
          warning_count: 0,
          error_count: 0,
          values_by_period: { "2021": 203000, "2022": 255000, "2023": 215000, "2024": 198000, "2025": 207000 },
        },
      ],
      raw_lines: [
        {
          statement_type: "DRE",
          line_id_base: "3.01",
          cd_conta: "3.01",
          ds_conta: "Receita",
          standard_name: "Revenue",
          label: "Revenue",
          normalized_label: "revenue",
          periods_present: ["2024", "2025"],
          sample_values_by_period: { "2021": 412000, "2022": 641000, "2023": 512000, "2024": 489000, "2025": 511000 },
          mapped_targets: [{ target_id: "DRE:3.01", target_label: "Revenue", group: "Income Statement" }],
        },
        {
          statement_type: "DRE",
          line_id_base: "3.05",
          cd_conta: "3.05",
          ds_conta: "Resultado Antes do Resultado Financeiro e dos Tributos",
          standard_name: "Operating Result (EBIT)",
          label: "Operating Result (EBIT)",
          normalized_label: "operating result ebit",
          periods_present: ["2021", "2022", "2023", "2024", "2025"],
          sample_values_by_period: { "2021": 124000, "2022": 257000, "2023": 166000, "2024": 151000, "2025": 162000 },
          mapped_targets: [{ target_id: "DRE:3.05", target_label: "Operating Result (EBIT)", group: "Income Statement" }],
        },
        {
          statement_type: "DRE",
          line_id_base: "3.04",
          cd_conta: "3.04",
          ds_conta: "Despesas/Receitas Operacionais",
          standard_name: "Operating Expenses (net)",
          label: "Operating Expenses (net)",
          normalized_label: "operating expenses net",
          periods_present: ["2021", "2022", "2023", "2024", "2025"],
          sample_values_by_period: { "2021": -52000, "2022": -75000, "2023": -69000, "2024": -72000, "2025": -74000 },
          mapped_targets: [],
        },
      ],
      validation: [
        {
          severity: "warning",
          code: "raw_lines_unmapped",
          message: "17 raw DRE line(s) are not used by the active mapping.",
          target_id: null,
          source_id: null,
        },
      ],
    }),

    save_excel_mapping_preset: async () => ({
      ok: false,
      error: "[mock] Mapping presets are only saved through the desktop bridge",
    }),

    set_company_excel_mapping_default: async () => ({
      ok: false,
      error: "[mock] Company mapping defaults are only saved through the desktop bridge",
    }),

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

    dev_reset_onboarding: async () => ({ ok: true }),
    dev_reset_universe: async () => ({ ok: true }),
    dev_reset_jobs: async () => ({ ok: true }),
    dev_simulate_refresh: async () => ({ ok: true, mode: "mock" }),
    dev_start_small_setup: async () => ({ status: "accepted", message: "[mock] Small setup started" }),
    dev_get_raw_state: async () => ({ app_settings: [], refresh_jobs: [] }),

    get_market_cap_list: async () => ({
      ok: true,
      items: [
        {
          as_of_date: `${YEAR}-01-01`,
          rank: 1,
          cd_cvm: 9512,
          cnpj: "33.000.167/0001-01",
          company_name: "PETROBRAS PN",
          ticker: "PETR4",
          market_cap_brl: 500000000000,
          source: "mock-fixture",
          method: "mock-method",
          source_url_or_id: "http://mock-url.com",
          downloaded_at: NOW,
          mapping_status: "mapped",
          mapping_confidence: 1.0,
        },
      ],
    }),

    import_market_cap_snapshot: async () => ({
      ok: true,
      status: {
        available: true,
        row_count: 1,
        as_of_date: `${YEAR}-01-01`,
        downloaded_at: NOW,
        source: "mock-fixture",
        warnings: [],
      },
    }),

    get_market_cap_status: async () => ({
      available: true,
      row_count: 1,
      as_of_date: `${YEAR}-01-01`,
      downloaded_at: NOW,
      source: "mock-fixture",
      warnings: [],
    }),

    get_company_market_history_status: async (params: { cd_cvm: number; ticker?: string | null }) => {
      const cdCvm = Number(params?.cd_cvm ?? 9512);
      const ticker = resolveMockTicker(cdCvm, params?.ticker);
      
      if (!ticker) {
        return {
          cd_cvm: cdCvm,
          ticker: null,
          available_tickers: [],
          has_local_data: false,
          first_date: null,
          last_date: null,
          row_count: 0,
          last_downloaded_at: null,
          is_stale: true,
          warnings: ["No ticker resolved for this CVM code."],
        };
      }

      const hasLocalData = DOWNLOADED_MARKET_HISTORIES.has(cdCvm);
      
      return {
        cd_cvm: cdCvm,
        ticker,
        available_tickers: resolveMockCompanyTickers(cdCvm, params?.ticker),
        has_local_data: hasLocalData,
        first_date: hasLocalData ? "2024-06-08" : null,
        last_date: hasLocalData ? "2026-06-08" : null,
        row_count: hasLocalData ? 730 : 0,
        last_downloaded_at: hasLocalData ? NOW : null,
        is_stale: !hasLocalData,
        warnings: [],
      };
    },

    get_company_market_history: async (params: {
      cd_cvm: number;
      ticker?: string | null;
      start_date?: string | null;
      end_date?: string | null;
      period?: string | null;
      interval?: string;
    }) => {
      const cdCvm = Number(params?.cd_cvm ?? 9512);
      const ticker = resolveMockTicker(cdCvm, params?.ticker);
      
      if (!ticker) {
        return {
          cd_cvm: cdCvm,
          ticker: "",
          source: "yahoo_finance",
          provider_status: "unofficial_free",
          requested_start_date: String(params?.start_date ?? null),
          requested_end_date: String(params?.end_date ?? null),
          actual_start_date: null,
          actual_end_date: null,
          interval: String(params?.interval ?? "1d"),
          last_downloaded_at: null,
          is_stale: true,
          has_local_data: false,
          warnings: ["No ticker resolved for this CVM code."],
          observations: [],
          summary: null,
        };
      }

      const hasLocalData = DOWNLOADED_MARKET_HISTORIES.has(cdCvm);
      if (!hasLocalData) {
        return {
          cd_cvm: cdCvm,
          ticker,
          source: "yahoo_finance",
          provider_status: "unofficial_free",
          requested_start_date: String(params?.start_date ?? null),
          requested_end_date: String(params?.end_date ?? null),
          actual_start_date: null,
          actual_end_date: null,
          interval: String(params?.interval ?? "1d"),
          last_downloaded_at: null,
          is_stale: true,
          has_local_data: false,
          warnings: ["No local market history has been downloaded yet."],
          observations: [],
          summary: null,
        };
      }

      const observations = [];
      const numDays = 730;
      const initialClose = cdCvm === 14311 ? 110.0 : 35.0;
      let prevClose = initialClose;
      
      let seed = cdCvm;
      function pseudoRandom() {
        const x = Math.sin(seed++) * 10000;
        return x - Math.floor(x);
      }

      for (let i = numDays; i >= 0; i--) {
        const d = new Date(Date.now() - i * 24 * 3600 * 1000);
        const dateStr = d.toISOString().split("T")[0];
        
        const change = (pseudoRandom() - 0.48) * 1.5;
        const close = Math.round((prevClose + change) * 100) / 100;
        const open = Math.round((prevClose + (pseudoRandom() - 0.5) * 0.5) * 100) / 100;
        const high = Math.round(Math.max(open, close) * 1.02 * 100) / 100;
        const low = Math.round(Math.min(open, close) * 0.98 * 100) / 100;
        const adjClose = Math.round(close * 0.95 * 100) / 100;
        const volume = Math.round(5_000_000 + pseudoRandom() * 10_000_000);
        
        const dividend = (i > 0 && i % 180 === 0) ? 1.25 : 0.0;
        
        prevClose = close;
        
        observations.push({
          date: dateStr,
          open,
          high,
          low,
          close,
          adjusted_close: adjClose,
          volume,
          dividend,
          split_ratio: 1.0,
          price_return_index: Math.round((close / initialClose) * 1000) / 1000,
          total_return_index: Math.round((adjClose / (initialClose * 0.95)) * 1000) / 1000,
          ttm_dividend_yield: dividend > 0 ? 0.085 : 0.082,
        });
      }

      const finalClose = prevClose;
      const annualizedTotalReturn = Math.round((Math.sqrt((finalClose * 0.95) / (initialClose * 0.95)) - 1.0) * 1000) / 1000;

      return {
        cd_cvm: cdCvm,
        ticker,
        source: "yahoo_finance",
        provider_status: "unofficial_free",
        requested_start_date: String(params?.start_date ?? null),
        requested_end_date: String(params?.end_date ?? null),
        actual_start_date: observations[0].date,
        actual_end_date: observations[observations.length - 1].date,
        interval: String(params?.interval ?? "1d"),
        last_downloaded_at: NOW,
        is_stale: false,
        has_local_data: true,
        warnings: [],
        observations,
        summary: {
          initial_close: initialClose,
          final_close: finalClose,
          absolute_change: Math.round((finalClose - initialClose) * 100) / 100,
          price_return: Math.round(((finalClose / initialClose) - 1.0) * 1000) / 1000,
          total_return: Math.round(((finalClose * 0.95 / (initialClose * 0.95)) - 1.0) * 1000) / 1000,
          annualized_total_return: annualizedTotalReturn,
          period_high: Math.round(initialClose * 1.3 * 100) / 100,
          period_low: Math.round(initialClose * 0.8 * 100) / 100,
          average_daily_volume: 8500000.0,
          dividends_per_share: 5.0,
          first_available_date: observations[0].date,
          last_available_date: observations[observations.length - 1].date,
        },
      };
    },

    refresh_company_market_history: async (params: { cd_cvm: number; ticker?: string | null }) => {
      const cdCvm = Number(params?.cd_cvm ?? 9512);
      const ticker = resolveMockTicker(cdCvm, params?.ticker);
      if (!ticker) {
        return {
          ok: false,
          ticker: "",
          requested_start_date: null,
          requested_end_date: null,
          provider_date_range: null,
          downloaded_rows: 0,
          inserted_rows: 0,
          updated_rows: 0,
          unchanged_rows: 0,
          rejected_rows: 0,
          provider_warnings: ["No ticker resolved"],
          completion_timestamp: NOW,
          refresh_duration_seconds: 0.0,
        };
      }
      
      DOWNLOADED_MARKET_HISTORIES.add(cdCvm);
      
      return {
        ok: true,
        ticker,
        requested_start_date: null,
        requested_end_date: null,
        provider_date_range: "2024-06-08 to 2026-06-08",
        downloaded_rows: 730,
        inserted_rows: 730,
        updated_rows: 0,
        unchanged_rows: 0,
        rejected_rows: 0,
        provider_warnings: [],
        completion_timestamp: NOW,
        refresh_duration_seconds: 0.12,
      };
    },

    refresh_all_company_market_history: async (params: { cd_cvm: number }) => {
      const cdCvm = Number(params?.cd_cvm ?? 9512);
      const tickers = resolveMockCompanyTickers(cdCvm);
      const results = tickers.map((ticker) => ({
        ok: true,
        ticker,
        requested_start_date: null,
        requested_end_date: null,
        provider_date_range: "2024-06-08 to 2026-06-08",
        downloaded_rows: 730,
        inserted_rows: 730,
        updated_rows: 0,
        unchanged_rows: 0,
        rejected_rows: 0,
        provider_warnings: [],
        completion_timestamp: NOW,
        refresh_duration_seconds: 0.12,
      }));
      DOWNLOADED_MARKET_HISTORIES.add(cdCvm);
      return {
        ok: results.length > 0,
        cd_cvm: cdCvm,
        attempted_count: results.length,
        success_count: results.length,
        failure_count: 0,
        results,
        error: results.length ? null : "No ticker resolved",
      };
    },

    get_distribution_distributors: async (params) => {
      const search = (params?.search || "").toLowerCase();
      const items = [
        {
          distributor_id: "coelba",
          canonical_name: "Neoenergia Coelba",
          trade_name: "COELBA",
          normalized_cnpj: "15139629000194",
          agent_code: "48",
          concession_type: "concession",
          primary_uf: "BA",
          status: "active",
          economic_group_id: "neoenergia",
          group_name: "Neoenergia",
          cd_cvm: 15539,
          company_name: "NEOENERGIA S.A.",
          ticker_b3: "NEOE3.SA",
        },
        {
          distributor_id: "cpfl_paulista",
          canonical_name: "CPFL Paulista",
          trade_name: "CPFL PAULISTA",
          normalized_cnpj: "33050196000188",
          agent_code: "25",
          concession_type: "concession",
          primary_uf: "SP",
          status: "active",
          economic_group_id: "cpfl",
          group_name: "CPFL Energia",
          cd_cvm: 18660,
          company_name: "CPFL ENERGIA S.A.",
          ticker_b3: "CPFE3.SA",
        }
      ].filter(item => !search || item.canonical_name.toLowerCase().includes(search) || item.trade_name.toLowerCase().includes(search));
      return { items, count: items.length };
    },

    get_distribution_distributor_detail: async (params) => {
      const distributor_id = params?.distributor_id || "coelba";
      const isCoelba = distributor_id === "coelba";
      return {
        identity: {
          distributor_id: isCoelba ? "coelba" : "cpfl_paulista",
          canonical_name: isCoelba ? "Neoenergia Coelba" : "CPFL Paulista",
          legal_name: isCoelba ? "COELBA DISTRIBUIDORA DE ENERGIA" : "COMPANHIA PAULISTA DE FORÇA E LUZ",
          trade_name: isCoelba ? "COELBA" : "CPFL PAULISTA",
          normalized_cnpj: isCoelba ? "15139629000194" : "33050196000188",
          agent_code: isCoelba ? "48" : "25",
          distributor_code: isCoelba ? "48" : "25",
          concession_type: "concession",
          primary_uf: isCoelba ? "BA" : "SP",
          service_area: isCoelba ? "State of Bahia" : "Interior of São Paulo State",
          status: "active",
        },
        ownership_history: [
          {
            ownership_id: isCoelba ? "coelba_neo" : "cpfl_paulista_cpfl",
            valid_from: "2000-01-01",
            valid_to: "2099-12-31",
            control_status: "controlled",
            ownership_percentage: 1.0,
            operational_consolidation_flag: 1,
            economic_group_id: isCoelba ? "neoenergia" : "cpfl",
            group_name: isCoelba ? "Neoenergia" : "CPFL Energia",
            cd_cvm: isCoelba ? 15539 : 18660,
            company_name: isCoelba ? "NEOENERGIA S.A." : "CPFL ENERGIA S.A.",
            ticker_b3: isCoelba ? "NEOE3.SA" : "CPFE3.SA",
          }
        ],
        available_periods: ["2025-01", "2025-02", "2025-03"],
      };
    },

    get_distribution_series: async (_params) => {
      const series = [
        {
          period: "2025-01",
          billed_energy_mwh: 1200.5,
          revenue_brl: 450000.0,
          measured_energy_mwh: 1300.0,
          injected_energy_mwh: 1400.0,
          losses_mwh: 100.0,
          losses_pct: 0.0769,
          dec_actual: 7.2,
          fec_actual: 5.1,
          dec_limit: 8.0,
          fec_limit: 6.0,
          compensation_count: 150,
          compensation_value: 45000.0,
          delinquency_pct: 0.021,
          mmgd_projects_count: 1200,
          mmgd_capacity_kw: 4500.0,
          te_homologated: 120.40,
          tusd_homologated: 150.50,
        },
        {
          period: "2025-02",
          billed_energy_mwh: 1250.0,
          revenue_brl: 470000.0,
          measured_energy_mwh: 1350.0,
          injected_energy_mwh: 1450.0,
          losses_mwh: 100.0,
          losses_pct: 0.074,
          dec_actual: 7.1,
          fec_actual: 5.0,
          dec_limit: 8.0,
          fec_limit: 6.0,
          compensation_count: 140,
          compensation_value: 42000.0,
          delinquency_pct: 0.020,
          mmgd_projects_count: 1250,
          mmgd_capacity_kw: 4700.0,
          te_homologated: 122.10,
          tusd_homologated: 152.00,
        }
      ];
      return { series, count: series.length };
    },

    get_distribution_mmgd_projects: async (params) => {
      const rows = [
        {
          project_id: "GD-MOCK-1",
          distributor_id: params?.distributor_id || "cpfl_paulista",
          municipality: "Campinas",
          uf: "SP",
          consumer_class: "Residential",
          tariff_subgroup: "B1",
          project_modality: "Local generation",
          enabled_modality: "Self-consumption",
          generation_type: "Solar",
          generation_source: "Solar radiation",
          size_category: "Microgeneration",
          latitude: -22.9,
          longitude: -47.06,
          connection_date: "2025-01-15",
          reference_month: params?.reference_month || "2025-02",
          installed_capacity_kw: 10.5,
          beneficiary_units_count: 1,
          source_row_hash: "mock-hash-1",
          snapshot_id: "mock-snapshot",
        },
      ];
      return {
        source: "managed_parquet" as const,
        dataset_id: "distribution_mmgd_projects",
        distributor_id: params?.distributor_id || "cpfl_paulista",
        reference_month: params?.reference_month || "2025-02",
        rows,
        projects: rows,
        count: rows.length,
        total_matching_rows: rows.length,
        limit: params?.limit || 50,
        offset: params?.offset || 0,
        truncated: false,
      };
    },

    get_distribution_refresh_status: async () => ({
      status: "idle",
      error: null,
      stage: "done",
      message: "Mock refresh finished",
      progress_current: 3,
      progress_total: 3,
    }),

    refresh_distribution_data: async () => ({
      status: "started",
      error: null,
    }),

    get_distribution_groups: async (_params) => {
      const items = [
        {
          economic_group_id: "neoenergia",
          group_name: "Neoenergia",
          cd_cvm: 15539,
          company_name: "NEOENERGIA S.A.",
          ticker_b3: "NEOE3.SA",
          distributors_count: 5,
        },
        {
          economic_group_id: "cpfl",
          group_name: "CPFL Energia",
          cd_cvm: 18660,
          company_name: "CPFL ENERGIA S.A.",
          ticker_b3: "CPFE3.SA",
          distributors_count: 4,
        }
      ];
      return { items, count: items.length };
    },

    get_distribution_group_detail: async (params) => {
      const group_id = params?.group_id || "neoenergia";
      const isNeo = group_id === "neoenergia";
      return {
        identity: {
          economic_group_id: isNeo ? "neoenergia" : "cpfl",
          group_name: isNeo ? "Neoenergia" : "CPFL Energia",
          cd_cvm: isNeo ? 15539 : 18660,
          company_name: isNeo ? "NEOENERGIA S.A." : "CPFL ENERGIA S.A.",
          ticker_b3: isNeo ? "NEOE3.SA" : "CPFE3.SA",
        },
        portfolio: [
          {
            ownership_id: isNeo ? "coelba_neo" : "cpfl_paulista_cpfl",
            distributor_id: isNeo ? "coelba" : "cpfl_paulista",
            canonical_name: isNeo ? "Neoenergia Coelba" : "CPFL Paulista",
            trade_name: isNeo ? "COELBA" : "CPFL PAULISTA",
            valid_from: "2000-01-01",
            valid_to: "2099-12-31",
            control_status: "controlled",
            ownership_percentage: 1.0,
            operational_consolidation_flag: 1,
          }
        ],
        available_periods: ["2025-01", "2025-02", "2025-03"],
      };
    },

    export_distribution_excel: async (_params) => {
      return {
        path: "C:\\Users\\mock\\Documents\\CVMAnalytics\\reports\\mock_export.xlsx",
        error: null,
      };
    },

    get_distribution_health: async (_params) => {
      return {
        counts: {
          market: 0,
          balance: 0,
          continuity: 0,
          tariffs: 0,
          delinquency: 0,
          mmgd: 0,
        },
        snapshots: [],
      };
    },

    get_coverage_universes: async () => {
      return [
        {
          id: "63c536bd-c1d5-44d8-8275-3b03c498f36e",
          name: "Equity I",
          purpose: "Companhias com familiaridade",
          analysis_type: "Equity",
          benchmark: "IBOV",
          status: "active",
          company_count: 5,
          created_at: "2026-06-17T00:10:38Z",
          updated_at: "2026-06-17T00:34:26Z"
        },
        {
          id: "c59accae-996d-4d12-a67a-5424f3832787",
          name: "Equity II",
          purpose: "Novas teses de cobertura",
          analysis_type: "Equity",
          benchmark: "IBOV",
          status: "draft",
          company_count: 3,
          created_at: "2026-06-17T00:14:11Z",
          updated_at: "2026-06-17T00:34:18Z"
        }
      ];
    },

    get_coverage_universe: async (params: any) => {
      const id = params?.id || "63c536bd-c1d5-44d8-8275-3b03c498f36e";
      const name = id === "63c536bd-c1d5-44d8-8275-3b03c498f36e" ? "Equity I" : "Equity II";
      const status = id === "63c536bd-c1d5-44d8-8275-3b03c498f36e" ? "active" : "draft";
      return {
        id,
        name,
        purpose: id === "63c536bd-c1d5-44d8-8275-3b03c498f36e" ? "Companhias com familiaridade" : "Novas teses de cobertura",
        analysis_type: "Equity",
        benchmark: "IBOV",
        status,
        created_at: "2026-06-17T00:10:38Z",
        updated_at: "2026-06-17T00:34:26Z",
        assumptions: {
          weights: {
            market_cap_weight: 0.3,
            volume_weight: 0.3,
            holding_weight: 0.2,
            sector_weight: 0.2
          },
          tier_hours: {
            must_cover: 120,
            core: 80,
            watchlist: 30,
            opportunistic: 45,
            excluded: 5,
            inappropriate: 5
          },
          manager_decision: {
            status,
            decided_at: "2026-06-18T10:00:00Z",
            notes: "Initial universe setup approved by team"
          }
        }
      };
    },

    calculate_coverage_priority_scores: async (_params: any) => {
      const items = [
        {
          cd_cvm: 9512,
          company_name: "PETROBRAS PN",
          ticker_b3: "PETR4",
          gics_sector: "Energy",
          market_cap: 500000000000,
          market_cap_brl: 500000000000,
          volume_brl: 1500000000,
          holding_pct: 5.2,
          tier: "must_cover",
          final_score: 92.5,
          score_status: "normal",
          owner: "Thiago",
          rationale: "Fator estratégico nacional de relevância máxima",
          has_financial_data: true,
          completed_checklist_count: 5,
          total_checklist_count: 5
        },
        {
          cd_cvm: 14311,
          company_name: "VALE ON",
          ticker_b3: "VALE3",
          gics_sector: "Materials",
          market_cap: 320000000000,
          market_cap_brl: 320000000000,
          volume_brl: 1200000000,
          holding_pct: 8.5,
          tier: "must_cover",
          final_score: 88.0,
          score_status: "normal",
          owner: "Thiago",
          rationale: "Maior produtor global de minério de ferro",
          has_financial_data: true,
          completed_checklist_count: 4,
          total_checklist_count: 5
        },
        {
          cd_cvm: 14673,
          company_name: "AMBEV SA",
          ticker_b3: "ABEV3",
          gics_sector: "Consumer Staples",
          market_cap: 210000000000,
          market_cap_brl: 210000000000,
          volume_brl: 450000000,
          holding_pct: 2.1,
          tier: "core",
          final_score: 75.2,
          score_status: "normal",
          owner: "Felipe",
          rationale: "Geração de caixa resiliente e liderança de mercado",
          has_financial_data: true,
          completed_checklist_count: 3,
          total_checklist_count: 5
        },
        {
          cd_cvm: 4170,
          company_name: "OI SA",
          ticker_b3: "OIBR3",
          gics_sector: "Telecommunication Services",
          market_cap: 1200000000,
          market_cap_brl: 1200000000,
          volume_brl: 15000000,
          holding_pct: 0.0,
          tier: "watchlist",
          final_score: 18.5,
          score_status: "partial",
          owner: null,
          rationale: "Empresa em recuperação judicial",
          has_financial_data: true,
          completed_checklist_count: 1,
          total_checklist_count: 5
        },
        {
          cd_cvm: 5258,
          company_name: "XP INC",
          ticker_b3: "XPBR31",
          gics_sector: "Financials",
          market_cap: 85000000000,
          market_cap_brl: 85000000000,
          volume_brl: 180000000,
          holding_pct: 1.5,
          tier: "watchlist",
          final_score: 0.0,
          score_status: "blocked",
          owner: "Felipe",
          rationale: "Dados financeiros insuficientes para cálculo automatizado",
          has_financial_data: false,
          completed_checklist_count: 0,
          total_checklist_count: 5
        }
      ];
      return { items, _bridge_ms: 120 };
    },

    get_company_coverage_checklists: async (_params: any) => {
      const items = [
        { item_key: "annual_report_reviewed", is_completed: true, comments: "Annual report (DFP) 2025 read and checked.", rationale: "Mandatory" },
        { item_key: "earnings_call_listened", is_completed: true, comments: "4Q25 earnings call listened.", rationale: "Qualitative factor" },
        { item_key: "financial_model_updated", is_completed: false, comments: "Missing capex projection.", rationale: "Model V2" },
        { item_key: "competitor_benchmarking", is_completed: false, comments: "Awaiting peers benchmarking.", rationale: "Comparative" },
        { item_key: "investment_thesis_drafted", is_completed: false, comments: "", rationale: "Executive summary" }
      ];
      return { items };
    },

    get_coverage_work_queue: async (_params: any) => {
      const items = [
        {
          cd_cvm: 9512,
          company_name: "PETROBRAS PN",
          ticker_b3: "PETR4",
          tier: "must_cover",
          owner: "Thiago",
          reason: "Missing financial model update with refining assumptions.",
          severity: "high",
          task_type: "checklist_gap",
          suggested_action: "Complete 'financial_model_updated' checklist item."
        },
        {
          cd_cvm: 14311,
          company_name: "VALE ON",
          ticker_b3: "VALE3",
          tier: "must_cover",
          owner: "Thiago",
          reason: "Sector benchmarking is outdated.",
          severity: "high",
          task_type: "checklist_gap",
          suggested_action: "Complete 'competitor_benchmarking' checklist item."
        },
        {
          cd_cvm: 4170,
          company_name: "OI SA",
          ticker_b3: "OIBR3",
          tier: "watchlist",
          owner: null,
          reason: "No analyst assigned to cover this company.",
          severity: "low",
          task_type: "unassigned_owner",
          suggested_action: "Assign a coverage analyst for OI SA."
        },
        {
          cd_cvm: 5258,
          company_name: "XP INC",
          ticker_b3: "XPBR31",
          tier: "watchlist",
          owner: "Felipe",
          reason: "Missing market cap historical series (Score Blocked).",
          severity: "medium",
          task_type: "missing_market_cap",
          suggested_action: "Import market cap data or refresh XP INC manually."
        }
      ];
      return { items };
    },

    get_coverage_capacity_data: async (_params: any) => {
      return {
        available_hours: 1600,
        required_hours: 1040,
        capacity_utilization_pct: 65.0,
        warnings: [
          "XP INC (XPBR31) has missing or invalid GICS classification. Complexity marked as unknown."
        ],
        tier_counts: {
          must_cover: 2,
          core: 1,
          watchlist: 2,
          opportunistic: 0,
          excluded: 0,
          inappropriate: 0
        },
        tier_hours: {
          must_cover: 240,
          core: 80,
          watchlist: 60,
          opportunistic: 0,
          excluded: 0,
          inappropriate: 0
        },
        tier_hours_assumptions: {
          must_cover: 120,
          core: 80,
          watchlist: 30,
          opportunistic: 45,
          excluded: 5,
          inappropriate: 5
        },
        by_owner: {
          "Thiago": { company_count: 2, required_hours: 200.0, utilization_pct: 12.5 },
          "Felipe": { company_count: 2, required_hours: 140.0, utilization_pct: 8.75 },
          "Unassigned": { company_count: 1, required_hours: 30.0, utilization_pct: 1.88 }
        },
        gics_unknown_companies: [
          { cd_cvm: 5258, company_name: "XP INC", ticker_b3: "XPBR31", tier: "watchlist" }
        ]
      };
    },

    get_coverage_recommendation: async (_params: any) => {
      return {
        universe_id: _params?.universe_id || "63c536bd-c1d5-44d8-8275-3b03c498f36e",
        company_count: 5,
        keep: [
          { cd_cvm: 9512, company_name: "PETROBRAS PN", ticker_b3: "PETR4", tier: "must_cover", score_status: "normal", final_score: 92.5, owner: "Thiago" },
          { cd_cvm: 14311, company_name: "VALE ON", ticker_b3: "VALE3", tier: "must_cover", score_status: "normal", final_score: 88.0, owner: "Thiago" },
          { cd_cvm: 14673, company_name: "AMBEV SA", ticker_b3: "ABEV3", tier: "core", score_status: "normal", final_score: 75.2, owner: "Felipe" }
        ],
        review: [
          { cd_cvm: 4170, company_name: "OI SA", ticker_b3: "OIBR3", tier: "watchlist", score_status: "partial", final_score: 18.5, owner: null }
        ],
        blocked: [
          { cd_cvm: 5258, company_name: "XP INC", ticker_b3: "XPBR31", tier: "watchlist", score_status: "blocked", final_score: 0.0, owner: "Felipe" }
        ],
        excluded: [],
        missing_data_risks: {
          missing_market_cap_count: 1,
          missing_gics_count: 1,
          unassigned_owner_count: 1
        },
        proposed_actions: [
          "Import market cap or quotes data for XP INC.",
          "Assign coverage analyst for OI SA.",
          "Complete the qualitative checklist for Vale and Petrobras."
        ],
        risks: [
          "XP INC (XPBR31) is blocked due to missing basic financial data.",
          "Missing GICS classification for XP INC prevents accurate sector complexity estimation."
        ]
      };
    },

    get_coverage_decision_history: async (_params: any) => {
      return {
        items: [
          {
            id: 1,
            event_type: "manager_decision_change",
            previous_value: "draft",
            new_value: "approved",
            rationale: "Quarterly review finalized. Portfolio approved for execution.",
            timestamp: "2026-06-18T10:00:00Z",
            author: "Manager",
            company_name: "All",
            ticker_b3: null,
            cd_cvm: null
          },
          {
            id: 2,
            event_type: "owner_change",
            previous_value: null,
            new_value: "Thiago",
            rationale: "Thiago takes over major commodities producers.",
            timestamp: "2026-06-17T11:30:00Z",
            author: "Manager",
            company_name: "VALE ON",
            ticker_b3: "VALE3",
            cd_cvm: 14311
          },
          {
            id: 3,
            event_type: "override_change",
            previous_value: null,
            new_value: "95.0",
            rationale: "Strategic relevance of energy sector in the portfolio.",
            timestamp: "2026-06-17T11:25:00Z",
            author: "Manager",
            company_name: "PETROBRAS PN",
            ticker_b3: "PETR4",
            cd_cvm: 9512
          }
        ]
      };
    },

    save_manual_score_override: async () => ({ success: true }),
    update_company_owner_analyst: async () => ({ success: true }),
    save_coverage_capacity_scenario: async () => ({ success: true }),
    save_coverage_manager_decision: async () => ({ success: true, status: "approved", decided_at: new Date().toISOString() }),
    duplicate_coverage_universe: async () => ({ success: true, universe_id: "duplicate-mock-id" }),
    delete_coverage_universe: async () => ({ success: true }),
    create_coverage_universe: async () => ({ success: true, universe_id: "new-mock-id" }),
    update_coverage_universe: async () => ({ success: true }),
    bulk_update_companies_in_coverage_universe: async () => ({ success: true }),
    add_company_to_coverage_universe: async () => ({ success: true }),
    remove_company_from_coverage_universe: async () => ({ success: true }),
  };
}
