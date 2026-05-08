import test from "node:test";
import assert from "node:assert/strict";

import {
  isDesktopMode,
  bridgeFetchCompanies,
  bridgeFetchCompanyFilters,
  bridgeFetchCompanySuggestions,
  bridgeFetchCompanyInfo,
  bridgeFetchCompanyYears,
  bridgeFetchHealth,
  bridgeFetchBaseHealth,
  bridgeTrackCompanyView,
  bridgeFetchRefreshStatus,
  bridgeFetchCompanyFreshness,
  bridgeFetchBatchJobs,
  bridgeRequestRefresh,
} from "../lib/desktop-bridge.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type PyApi = NonNullable<NonNullable<typeof globalThis.window>["pywebview"]>["api"];

function withPywebview(api: Partial<PyApi>) {
  const win = globalThis as unknown as {
    window?: { pywebview?: { api: Partial<PyApi> } };
  };
  const prev = win.window;
  win.window = { pywebview: { api } };
  return () => {
    win.window = prev;
  };
}

// ---------------------------------------------------------------------------
// isDesktopMode
// ---------------------------------------------------------------------------

test("isDesktopMode returns false when window is undefined", () => {
  assert.equal(isDesktopMode(), false);
});

test("isDesktopMode returns true when window.pywebview is present", () => {
  const restore = withPywebview({ ping: async () => ({ pong: true, ts: 0 }) } as PyApi);
  try {
    assert.equal(isDesktopMode(), true);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeFetchCompanies — error envelope triggers BridgeError
// ---------------------------------------------------------------------------

test("bridgeFetchCompanies throws when bridge returns error envelope", async () => {
  const restore = withPywebview({
    get_companies: async () => ({ error: "db unavailable" }),
  } as unknown as PyApi);

  try {
    await assert.rejects(
      () => bridgeFetchCompanies({ page: 1, pageSize: 10 }),
      (err: unknown) => {
        assert.ok(err instanceof Error);
        assert.match((err as Error).message, /db unavailable/);
        return true;
      },
    );
  } finally {
    restore();
  }
});

test("bridgeFetchCompanies returns data on success", async () => {
  const fakeResult = {
    items: [{ cd_cvm: 1, name: "Petro" }],
    pagination: { page: 1, page_size: 10, total: 1, total_pages: 1 },
  };
  const restore = withPywebview({
    get_companies: async () => fakeResult,
  } as unknown as PyApi);

  try {
    const result = await bridgeFetchCompanies({ page: 1 });
    assert.deepEqual(result, fakeResult);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeFetchCompanyFilters
// ---------------------------------------------------------------------------

test("bridgeFetchCompanyFilters returns sectors list", async () => {
  const fake = { sectors: [{ slug: "energia", label: "Energia" }] };
  const restore = withPywebview({
    get_company_filters: async () => fake,
  } as unknown as PyApi);

  try {
    const result = await bridgeFetchCompanyFilters();
    assert.deepEqual(result, fake);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeFetchCompanySuggestions
// ---------------------------------------------------------------------------

test("bridgeFetchCompanySuggestions passes ready_only flag", async () => {
  let captured: Record<string, unknown> = {};
  const restore = withPywebview({
    get_company_suggestions: async (p: Record<string, unknown>) => {
      captured = p;
      return { items: [] };
    },
  } as unknown as PyApi);

  try {
    await bridgeFetchCompanySuggestions("petro", 5, { readyOnly: true });
    assert.equal(captured.q, "petro");
    assert.equal(captured.limit, 5);
    assert.equal(captured.ready_only, true);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeFetchCompanyInfo — not_found returns null
// ---------------------------------------------------------------------------

test("bridgeFetchCompanyInfo returns null when not_found", async () => {
  const restore = withPywebview({
    get_company_info: async () => ({ not_found: true }),
  } as unknown as PyApi);

  try {
    const result = await bridgeFetchCompanyInfo(12345);
    assert.equal(result, null);
  } finally {
    restore();
  }
});

test("bridgeFetchCompanyInfo returns company data on success", async () => {
  const fake = { cd_cvm: 9512, name: "Vale" };
  const restore = withPywebview({
    get_company_info: async () => fake,
  } as unknown as PyApi);

  try {
    const result = await bridgeFetchCompanyInfo(9512);
    assert.deepEqual(result, fake);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeFetchCompanyYears
// ---------------------------------------------------------------------------

test("bridgeFetchCompanyYears returns years array", async () => {
  const restore = withPywebview({
    get_company_years: async () => ({ years: [2021, 2022, 2023] }),
  } as unknown as PyApi);

  try {
    const years = await bridgeFetchCompanyYears(9512);
    assert.deepEqual(years, [2021, 2022, 2023]);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeFetchHealth
// ---------------------------------------------------------------------------

test("bridgeFetchHealth returns ok status", async () => {
  const fake = {
    status: "ok",
    version: "desktop",
    database_dialect: "sqlite",
    required_tables: [],
    warnings: [],
    errors: [],
  };
  const restore = withPywebview({
    get_health: async () => fake,
  } as unknown as PyApi);

  try {
    const result = await bridgeFetchHealth();
    assert.equal(result.status, "ok");
  } finally {
    restore();
  }
});

test("bridgeFetchBaseHealth calls the desktop base-health bridge with years", async () => {
  let captured: Record<string, unknown> = {};
  const fake = {
    generated_at: "2026-05-04T15:00:00",
    start_year: 2024,
    end_year: 2025,
    total_cells: 10,
    completed_cells: 7,
    missing_cells: 3,
    pct: 70,
    health_score: 78,
    health_status: "atencao",
    eta_hours: null,
    throughput_per_hour: null,
    throughput_confidence: "low",
    per_year: [],
    prioritized_companies: [],
    raw: {},
  };
  const restore = withPywebview({
    get_base_health: async (params: Record<string, unknown>) => {
      captured = params;
      return fake;
    },
  } as unknown as PyApi);

  try {
    const result = await bridgeFetchBaseHealth({ startYear: 2024, endYear: 2025 });
    assert.equal(captured.start_year, 2024);
    assert.equal(captured.end_year, 2025);
    assert.equal(result.missing_cells, 3);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeTrackCompanyView — fire-and-forget, no throw
// ---------------------------------------------------------------------------

test("bridgeTrackCompanyView is a no-op when not in desktop mode", () => {
  assert.doesNotThrow(() => bridgeTrackCompanyView(9512));
});

// ---------------------------------------------------------------------------
// bridgeFetchRefreshStatus — retorna lista vazia no desktop
// ---------------------------------------------------------------------------

test("bridgeFetchRefreshStatus returns empty array in desktop mode", async () => {
  const restore = withPywebview({
    get_refresh_status: async () => ({ items: [] }),
  } as unknown as PyApi);

  try {
    const items = await bridgeFetchRefreshStatus(9512);
    assert.deepEqual(items, []);
  } finally {
    restore();
  }
});

test("bridgeFetchCompanyFreshness returns first refresh item", async () => {
  const restore = withPywebview({
    get_refresh_status: async () => ({
      items: [
        { cd_cvm: 9512, company_name: "VALE", source_scope: "on_demand" },
        { cd_cvm: 9512, company_name: "VALE", source_scope: "cached" },
      ],
    }),
  } as unknown as PyApi);

  try {
    const item = await bridgeFetchCompanyFreshness(9512);
    assert.equal(item?.source_scope, "on_demand");
  } finally {
    restore();
  }
});

test("bridgeFetchBatchJobs returns the desktop refresh job list", async () => {
  const restore = withPywebview({
    get_refresh_status: async () => ({
      items: [
        {
          job_id: "job-1",
          state: "running",
          queued: 2,
          processed: 1,
          failures: 0,
          log_lines: [],
        },
      ],
    }),
  } as unknown as PyApi);

  try {
    const result = await bridgeFetchBatchJobs();
    assert.equal(result.items.length, 1);
    assert.equal(result.items[0]?.job_id, "job-1");
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeRequestRefresh — retorna already_current, não inicia polling
// ---------------------------------------------------------------------------

test("bridgeRequestRefresh returns already_current status", async () => {
  const restore = withPywebview({
    request_refresh: async () => ({
      status: "already_current",
      cd_cvm: 9512,
      job_id: null,
      accepted_at: "",
      message: "Atualizacao nao disponivel no modo desktop.",
      status_reason_code: "desktop_viewer",
      status_reason_message: null,
      is_retry_allowed: false,
    }),
  } as unknown as PyApi);

  try {
    const result = await bridgeRequestRefresh(9512);
    assert.equal(result.status, "already_current");
    assert.equal(result.is_retry_allowed, false);
  } finally {
    restore();
  }
});
