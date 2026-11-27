import type {
  BridgeApi,
  BaseHealthSnapshot,
  DataUpdateSettings,
  RefreshJobListResponse,
  RefreshJobStatus,
} from "./types";
import { NOW, YEAR, FIXTURE_COMPANIES } from "./mock.fixtures";

export const MOCK_JOB_RUNNING: RefreshJobStatus = {
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

export function createMockRefreshMethods(): Partial<BridgeApi> {
  return {
    get_base_health: async () => MOCK_BASE_HEALTH,

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
      action: "recreate_local",
      message: "[mock] Local database rebuilt after a backup. Ignore flags were kept.",
      backup_path: "[mock] /dev/mock/backup",
      backup_items: ["[mock] cvm_financials.db.bak"],
      removed: ["refresh_jobs.json"],
      active_job_id: null,
    }),

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
  };
}
