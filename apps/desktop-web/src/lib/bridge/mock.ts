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
  CountryKPIValue,
  DataCoverageResponse,
  DataCoverageRow,
  DatabaseDiagnostics,
  DataUpdateSettings,
  EnergyKPIHealthResponse,
  EnergyKPIRefreshResult,
  KPIBundle,
  OnboardingState,
  RefreshJobListResponse,
  RefreshJobStatus,
  SectorDirectoryResponse,
  SectorDetailResponse,
  SINKPIDashboardResponse,
  SINKPIHealthResponse,
  SINKPIObservation,
  SINKPISeriesResponse,
  StatementMatrix,
  TabularData,
  TabularRow,
} from "./types";

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
 * KPI fixtures mirror the real engine output shape (src/kpi_engine.py):
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
    version: "0.25.1-mock",
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
    current_version: "0.25.1",
    latest_version: "0.25.1",
    update_available: false,
    status: "up_to_date",
    apply_supported: false,
  },
  diagnostics: {
    ok: true,
    version: "0.25.1-mock",
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

// ---------------------------------------------------------------------------
// Country Energy KPI fixtures
// ---------------------------------------------------------------------------

const COUNTRY_NS = "energy_utilities.country";
const COUNTRY_FIXTURES = [
  { iso: "BRA", name: "Brazil", hydro: 58, solar: 6, wind: 13, nuclear: 2, gas: 9, coal: 3, demand: 620, carbon: 96 },
  { iso: "USA", name: "United States", hydro: 6, solar: 5, wind: 11, nuclear: 18, gas: 39, coal: 19, demand: 4300, carbon: 360 },
  { iso: "CHN", name: "China", hydro: 15, solar: 6, wind: 9, nuclear: 5, gas: 3, coal: 58, demand: 8900, carbon: 560 },
  { iso: "OWEU", name: "EU 27", hydro: 12, solar: 9, wind: 17, nuclear: 22, gas: 18, coal: 13, demand: 2800, carbon: 250 },
  { iso: "CHL", name: "Chile", hydro: 21, solar: 19, wind: 12, nuclear: 0, gas: 18, coal: 24, demand: 86, carbon: 310 },
  { iso: "ARG", name: "Argentina", hydro: 25, solar: 2, wind: 9, nuclear: 7, gas: 50, coal: 2, demand: 145, carbon: 330 },
] as const;

const COUNTRY_KPIS = [
  "elec_hydro_share",
  "elec_solar_share",
  "elec_wind_share",
  "elec_nuclear_share",
  "elec_gas_share",
  "elec_coal_share",
  "elec_renewables_share",
  "elec_fossil_share",
  "elec_low_carbon_share",
  "elec_carbon_intensity",
  "elec_demand_total",
  "elec_generation_total",
  "elec_demand_growth_yoy",
  "elec_net_imports_share",
] as const;

function buildMockCountryKpiValues(): CountryKPIValue[] {
  const rows: CountryKPIValue[] = [];
  for (let year = YEAR - 11; year <= YEAR - 1; year += 1) {
    const yearOffset = year - (YEAR - 11);
    for (const [countryIdx, country] of COUNTRY_FIXTURES.entries()) {
      const shift = Math.sin((yearOffset + countryIdx) * 0.7);
      const hydro = clampShare(country.hydro + shift * 2.2 - yearOffset * 0.15);
      const solar = clampShare(country.solar + yearOffset * 0.75 + Math.max(0, shift));
      const wind = clampShare(country.wind + yearOffset * 0.45 + shift * 0.7);
      const nuclear = clampShare(country.nuclear);
      const gas = clampShare(country.gas - yearOffset * 0.18 + shift);
      const coal = clampShare(country.coal - yearOffset * 0.7 - shift);
      const renewables = hydro + solar + wind;
      const fossil = gas + coal;
      const lowCarbon = renewables + nuclear;
      const demand = country.demand * (1 + yearOffset * 0.018 + shift * 0.008);
      const generation = demand * (1 + ([0.01, -0.02, 0.03, -0.01, 0.02, -0.015][countryIdx] ?? 0));
      const growth = 1.2 + shift * 2.4 + countryIdx * 0.2;
      const imports = ((demand - generation) / demand) * 100;
      const carbon = Math.max(35, country.carbon - yearOffset * 8 + shift * 8);
      const valueMap: Record<(typeof COUNTRY_KPIS)[number], number> = {
        elec_hydro_share: hydro,
        elec_solar_share: solar,
        elec_wind_share: wind,
        elec_nuclear_share: nuclear,
        elec_gas_share: gas,
        elec_coal_share: coal,
        elec_renewables_share: renewables,
        elec_fossil_share: fossil,
        elec_low_carbon_share: lowCarbon,
        elec_carbon_intensity: carbon,
        elec_demand_total: demand,
        elec_generation_total: generation,
        elec_demand_growth_yoy: growth,
        elec_net_imports_share: imports,
      };
      for (const kpi of COUNTRY_KPIS) {
        const value = Number(valueMap[kpi].toFixed(2));
        const kpiId = `${COUNTRY_NS}.${kpi}`;
        rows.push({
          kpi_id: kpiId,
          iso_code: country.iso,
          country_name: country.name,
          period: year,
          value,
          unit: kpi.includes("share") || kpi.endsWith("growth_yoy") ? "%" : kpi.endsWith("intensity") ? "gCO2/kWh" : "TWh",
          source: "mock",
          source_priority: 1,
          source_field: kpi,
          data_quality_status: "ok",
          source_conflict: false,
          fallback_used: false,
          snapshot_id: "mock-country-energy-snapshot",
          value_owid: value,
          value_ember: null,
        });
      }
    }
  }
  return rows;
}

function clampShare(value: number): number {
  return Math.max(0, Math.min(100, value));
}

const MOCK_COUNTRY_KPI_VALUES = buildMockCountryKpiValues();

// ---------------------------------------------------------------------------
// SIN subsystem KPI fixtures
// ---------------------------------------------------------------------------

const SIN_NS = "energy_utilities.sin";
const SIN_SUBSYSTEMS = [
  { code: "S", name: "South / Sul", color: "#60A5FA" },
  { code: "SE_CO", name: "Southeast-Center West / Sudeste-Centro-Oeste", color: "#22D3EE" },
  { code: "NE", name: "Northeast / Nordeste", color: "#FBBF24" },
  { code: "N", name: "North / Norte", color: "#4ADE80" },
] as const;

const SIN_KPI_META: Record<string, { unit: string; source: string; dataset: string; field: string }> = {
  [`${SIN_NS}.load_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_carga" },
  [`${SIN_NS}.generation_hydro_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gerhidraulica" },
  [`${SIN_NS}.generation_thermal_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gertermica" },
  [`${SIN_NS}.generation_wind_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gereolica" },
  [`${SIN_NS}.generation_solar_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gersolar" },
  [`${SIN_NS}.generation_total_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "derived_total_generation" },
  [`${SIN_NS}.mix_hydro_pct`]: { unit: "%", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gerhidraulica/total" },
  [`${SIN_NS}.mix_thermal_pct`]: { unit: "%", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gertermica/total" },
  [`${SIN_NS}.mix_wind_pct`]: { unit: "%", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gereolica/total" },
  [`${SIN_NS}.mix_solar_pct`]: { unit: "%", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gersolar/total" },
  [`${SIN_NS}.ear_stored_pct`]: { unit: "%", source: "ONS", dataset: "ear_diario_subsistema", field: "ear_verif_subsistema_percentual" },
  [`${SIN_NS}.ear_stored_mwmes`]: { unit: "MWmes", source: "ONS", dataset: "ear_diario_subsistema", field: "ear_verif_subsistema_mwmes" },
  [`${SIN_NS}.ena_gross_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "ena_diario_subsistema", field: "ena_bruta_regiao_mwmed" },
  [`${SIN_NS}.ena_gross_pct_mlt`]: { unit: "% MLT", source: "ONS", dataset: "ena_diario_subsistema", field: "ena_bruta_regiao_percentualmlt" },
  [`${SIN_NS}.cmo_brl_mwh`]: { unit: "R$/MWh", source: "ONS", dataset: "cmo_semihorario", field: "val_cmo" },
  [`${SIN_NS}.pld_brl_mwh`]: { unit: "R$/MWh", source: "CCEE", dataset: "pld_horario", field: "PLD_HORA" },
  [`${SIN_NS}.net_interchange_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_intercambio" },
};

function buildMockSINValues(): SINKPIObservation[] {
  const rows: SINKPIObservation[] = [];
  const baseBySubsystem: Record<string, number> = { S: 13500, SE_CO: 51500, NE: 13200, N: 7900 };
  for (let day = 13; day >= 0; day -= 1) {
    const date = new Date(Date.now() - day * 86_400_000).toISOString().slice(0, 10) + "T00:00:00";
    for (const [idx, sub] of SIN_SUBSYSTEMS.entries()) {
      const wave = Math.sin((13 - day + idx) * 0.55);
      const load = baseBySubsystem[sub.code] + wave * 900;
      const hydro = load * ([0.46, 0.48, 0.19, 0.68][idx] ?? 0.4);
      const thermal = load * ([0.18, 0.16, 0.07, 0.18][idx] ?? 0.12);
      const wind = load * ([0.10, 0.03, 0.63, 0.04][idx] ?? 0.1);
      const solar = load * ([0.04, 0.05, 0.08, 0.03][idx] ?? 0.04);
      const total = hydro + thermal + wind + solar;
      const valueMap: Record<string, number> = {
        [`${SIN_NS}.load_mwmed`]: load,
        [`${SIN_NS}.generation_hydro_mwmed`]: hydro,
        [`${SIN_NS}.generation_thermal_mwmed`]: thermal,
        [`${SIN_NS}.generation_wind_mwmed`]: wind,
        [`${SIN_NS}.generation_solar_mwmed`]: solar,
        [`${SIN_NS}.generation_total_mwmed`]: total,
        [`${SIN_NS}.mix_hydro_pct`]: hydro / total * 100,
        [`${SIN_NS}.mix_thermal_pct`]: thermal / total * 100,
        [`${SIN_NS}.mix_wind_pct`]: wind / total * 100,
        [`${SIN_NS}.mix_solar_pct`]: solar / total * 100,
        [`${SIN_NS}.ear_stored_pct`]: [72, 64, 48, 77][idx] + wave * 2.5,
        [`${SIN_NS}.ear_stored_mwmes`]: [14500, 128000, 24800, 11800][idx] + wave * 600,
        [`${SIN_NS}.ena_gross_mwmed`]: [8200, 41000, 6400, 9000][idx] + wave * 700,
        [`${SIN_NS}.ena_gross_pct_mlt`]: [92, 84, 57, 103][idx] + wave * 5,
        [`${SIN_NS}.cmo_brl_mwh`]: [148, 152, 144, 155][idx] + wave * 9,
        [`${SIN_NS}.pld_brl_mwh`]: [142, 151, 139, 152][idx] + wave * 7,
        [`${SIN_NS}.net_interchange_mwmed`]: [-850, -4200, 780, 5400][idx] + wave * 350,
      };
      for (const [kpiId, value] of Object.entries(valueMap)) {
        const meta = SIN_KPI_META[kpiId];
        rows.push({
          kpi_id: kpiId,
          subsystem_code: sub.code,
          subsystem_name: sub.name,
          reference_datetime: date,
          value: Number(value.toFixed(2)),
          unit: meta.unit,
          source: meta.source,
          source_dataset: meta.dataset,
          source_field: meta.field,
          data_quality_status: "ok",
          snapshot_id: "mock-sin-snapshot",
        });
      }
    }
  }
  return rows;
}

const MOCK_SIN_VALUES = buildMockSINValues();

const MOCK_SIN_DASHBOARD: SINKPIDashboardResponse = {
  last_successful_update: new Date(Date.now() - 3_600_000).toISOString(),
  latest_reference_datetime: MOCK_SIN_VALUES.at(-1)?.reference_datetime ?? null,
  is_empty: false,
  is_stale: false,
  observations: MOCK_SIN_VALUES.filter((row) => row.reference_datetime === MOCK_SIN_VALUES.at(-1)?.reference_datetime),
  source_statuses: [
    { source: "ONS", dataset: "balanco_energia_subsistema", frequency: "hourly", last_snapshot_at: NOW, local_records_count: 6160, last_status: "partial", last_error: null },
    { source: "ONS", dataset: "ear_diario_subsistema", frequency: "daily", last_snapshot_at: NOW, local_records_count: 112, last_status: "partial", last_error: null },
    { source: "ONS", dataset: "ena_diario_subsistema", frequency: "daily", last_snapshot_at: NOW, local_records_count: 224, last_status: "partial", last_error: null },
    { source: "ONS", dataset: "cmo_semihorario", frequency: "semi-hourly", last_snapshot_at: NOW, local_records_count: 1344, last_status: "partial", last_error: null },
    { source: "CCEE", dataset: "pld_horario", frequency: "hourly", last_snapshot_at: NOW, local_records_count: 1344, last_status: "partial", last_error: "Mock partial source note: CCEE can return 403 in some environments." },
  ],
  refresh_running: false,
  refresh_error: null,
};

// ---------------------------------------------------------------------------
// Onboarding state
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

const MOCK_SECTORS: SectorDirectoryResponse = {
  items: SECTOR_SLUGS.map((s) => ({
    sector_name: s.name,
    sector_slug: s.slug,
    company_count: s.count,
    latest_year: YEAR - 1,
    snapshot: { roe: 12, mg_ebit: 18, mg_liq: 8 },
    sub_industries: [],
    sub_industry_breakdown: [],
    group_type: "sector",
    parent_sector_name: null,
    parent_sector_slug: null,
    companies: [],
  })),
};

// ---------------------------------------------------------------------------
// Company directory item helpers
// ---------------------------------------------------------------------------

function toDirectoryItem(c: FixtureCompany): CompanyDirectoryItem {
  return {
    cd_cvm: c.cd_cvm,
    company_name: c.company_name,
    ticker_b3: c.ticker_b3,
    setor_analitico: c.sector_name,
    setor_cvm: c.sector_name,
    sector_name: c.sector_name,
    sector_slug: c.sector_slug,
    anos_disponiveis: c.anos_disponiveis,
    total_rows: c.total_rows,
    has_financial_data: c.has_financial_data,
    coverage_rank: c.has_financial_data ? 1 : null,
    data_status: c.data_status,
    gics_sector: null,
    gics_sector_slug: null,
    gics_industry_group: null,
    gics_industry: null,
    gics_sub_industry: null,
  };
}

// ---------------------------------------------------------------------------
// createMockBridge — exported factory
// ---------------------------------------------------------------------------

export function createMockBridge(): Partial<BridgeApi> {
  return {
    ping: async () => ({ pong: true, ts: Date.now() / 1000 }),

    get_health: async () => ({
      status: "ok",
      version: "0.25.1-mock",
      database_dialect: "sqlite",
      required_tables: ["financial_reports", "companies", "refresh_jobs"],
      warnings: [],
      errors: [],
    }),

    get_app_status: async () => MOCK_APP_STATUS,

    get_database_diagnostics: async () => MOCK_DB_DIAGNOSTICS,

    get_base_health: async () => MOCK_BASE_HEALTH,

    get_kpi_catalog: async () => ({
      entries: [],
      count: 0,
    }),

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

    get_companies: async (params) => {
      const p = params as Record<string, unknown>;
      const search = String(p?.search ?? "").toLowerCase();
      const sectorSlug = String(p?.sector_slug ?? "");
      const page = Number(p?.page ?? 1);
      const pageSize = Number(p?.page_size ?? 50);

      let items = FIXTURE_COMPANIES;
      if (search) items = items.filter((c) => c.company_name.toLowerCase().includes(search) || (c.ticker_b3 ?? "").toLowerCase().includes(search));
      if (sectorSlug) items = items.filter((c) => c.sector_slug === sectorSlug);

      const totalItems = items.length;
      const totalPages = Math.ceil(totalItems / pageSize) || 1;
      const start = (page - 1) * pageSize;
      const pageItems = items.slice(start, start + pageSize);

      const result: CompanyDirectoryPage = {
        items: pageItems.map(toDirectoryItem),
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
          nome_comercial: null,
          cnpj: null,
          ticker_b3: null,
          company_type: null,
          setor_cvm: null,
          setor_analitico: null,
          has_local_financial_reports: false,
          has_readable_current_data: false,
          readable_years_count: 0,
          latest_readable_year: null,
          read_model_updated_at: null,
          read_availability_code: null,
          read_availability_message: null,
          not_found: true,
        } satisfies CompanyInfo;
      }
      return {
        cd_cvm: c.cd_cvm,
        company_name: c.company_name,
        nome_comercial: c.company_name,
        cnpj: c.cnpj,
        ticker_b3: c.ticker_b3,
        company_type: "SA",
        setor_cvm: c.sector_name,
        setor_analitico: c.sector_name,
        sector_name: c.sector_name,
        sector_slug: c.sector_slug,
        has_local_financial_reports: c.has_financial_data,
        has_readable_current_data: c.has_financial_data,
        readable_years_count: c.anos_disponiveis.length,
        latest_readable_year: c.anos_disponiveis.at(-1) ?? null,
        read_model_updated_at: c.has_financial_data
          ? new Date(Date.now() - 86_400_000).toISOString()
          : null,
        read_availability_code: c.has_financial_data ? "readable" : "no_data",
        read_availability_message: c.has_financial_data ? "Data available" : "No financial data",
      } satisfies CompanyInfo;
    },

    get_company_years: async (params) => {
      const p = params as Record<string, unknown>;
      const cdCvm = Number(p?.cd_cvm ?? 0);
      const c = FIXTURE_COMPANIES.find((x) => x.cd_cvm === cdCvm);
      return { years: c?.anos_disponiveis ?? [] } satisfies CompanyYearsResult;
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
      const statementType = String(p?.statement_type ?? "DRE");
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

    get_sectors: async () => MOCK_SECTORS,

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

    check_update: async () => ({ available: false, version: "0.25.1" }),

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

    get_excel_mapping_workspace: async () => ({
      ok: true,
      company: {
        cd_cvm: 9512,
        company_name: "PETROBRAS PN",
        nome_comercial: "PETROBRAS PN",
        cnpj: "33.000.167/0001-01",
        ticker_b3: "PETR4",
        company_type: "SA",
        setor_cvm: "Petróleo e Gás",
        setor_analitico: "Petróleo e Gás",
        sector_name: "Petróleo e Gás",
        sector_slug: "petroleo-e-gas",
        has_local_financial_reports: true,
        has_readable_current_data: true,
        readable_years_count: 5,
        latest_readable_year: YEAR - 1,
        read_model_updated_at: NOW,
        read_availability_code: "readable",
        read_availability_message: "Data available",
      },
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

    fetch_latest_market_cap: async () => ({
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
  };
}
