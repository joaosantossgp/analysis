import test from "node:test";
import assert from "node:assert/strict";

import {
  fetchBaseHealth,
  fetchBatchRefresh,
  fetchBatchJobs,
  fetchBatchJobStatus,
  cancelBatchJob,
  resolveBatchRefreshCvmRange,
} from "../lib/api.ts";
import {
  buildBaseHealthSummary,
  buildHistoryRows,
  buildUpdateModeEstimates,
  computeRefreshProgress,
  getStageProgressFloor,
  getHistoryState,
} from "../lib/update-base-admin.ts";
import {
  bridgeRequestBatchRefresh,
  bridgeFetchBatchStatus,
  bridgeCancelRefresh,
} from "../lib/desktop-bridge.ts";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type FetchMock = typeof globalThis.fetch;

function withFetchMock(mock: FetchMock) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = mock;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

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
// base health / jobs loading
// ---------------------------------------------------------------------------

const baseHealthPayload = {
  generated_at: "2026-05-04T15:00:00",
  start_year: 2024,
  end_year: 2025,
  total_cells: 10,
  completed_cells: 7,
  missing_cells: 3,
  pct: 70,
  health_score: 78,
  health_status: "atencao",
  eta_hours: 1.5,
  throughput_per_hour: 2,
  throughput_confidence: "medium",
  per_year: [
    { year: 2024, total_companies: 5, completed: 4, missing: 1, pct: 80, eta_hours: 0.5 },
    { year: 2025, total_companies: 6, completed: 3, missing: 3, pct: 50, eta_hours: 1 },
  ],
  prioritized_companies: [],
  raw: {},
  total_companies: 6,
  companies_with_historical_data: 4,
  companies_without_historical_data: 2,
  companies_with_any_local_financial_report: 5,
  companies_partial_local: 1,
  companies_with_refresh_status_recorded: 5,
  companies_with_last_refresh_error: 0,
};

test("fetchBaseHealth tolerates legacy payloads without extended inventory counters", async () => {
  const legacy = { ...baseHealthPayload } as Record<string, unknown>;
  delete legacy.companies_with_any_local_financial_report;
  delete legacy.companies_partial_local;
  delete legacy.companies_with_refresh_status_recorded;
  delete legacy.companies_with_last_refresh_error;

  const restore = withFetchMock((async (request: RequestInfo | URL): Promise<Response> => {
    void request;
    return new Response(JSON.stringify(legacy), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as FetchMock);

  try {
    const result = await fetchBaseHealth({ startYear: 2024, endYear: 2025 });
    assert.equal(result.companies_with_any_local_financial_report, 0);
    assert.equal(result.companies_partial_local, 0);
    assert.equal(result.companies_with_refresh_status_recorded, 0);
    assert.equal(result.companies_with_last_refresh_error, 0);
    assert.equal(result.total_companies, 6);
  } finally {
    restore();
  }
});

test("fetchBaseHealth (web) loads the same-origin base-health route with the real window", async () => {
  let capturedUrl = "";
  const restore = withFetchMock((async (input: RequestInfo | URL) => {
    capturedUrl = String(input);
    return new Response(JSON.stringify(baseHealthPayload), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as FetchMock);

  try {
    const result = await fetchBaseHealth({ startYear: 2024, endYear: 2025 });
    assert.ok(
      capturedUrl.endsWith("/api/base-health?start_year=2024&end_year=2025"),
      `unexpected url: ${capturedUrl}`,
    );
    assert.equal(result.missing_cells, 3);
  } finally {
    restore();
  }
});

test("fetchBatchJobs (web) distinguishes no active job with an empty real list", async () => {
  let capturedUrl = "";
  const restore = withFetchMock((async (input: RequestInfo | URL) => {
    capturedUrl = String(input);
    return new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as FetchMock);

  try {
    const result = await fetchBatchJobs();
    assert.ok(capturedUrl.endsWith("/api/refresh-jobs"), `unexpected url: ${capturedUrl}`);
    assert.deepEqual(result.items, []);
  } finally {
    restore();
  }
});

test("update-base summaries derive cards and mode estimates from health and filters", () => {
  const sectors = [
    { sector_name: "Energia", sector_slug: "energia", company_count: 2 },
    { sector_name: "Financeiro", sector_slug: "financeiro", company_count: 4 },
  ];

  const summary = buildBaseHealthSummary(baseHealthPayload);
  const estimates = buildUpdateModeEstimates({
    health: baseHealthPayload,
    sectors,
    selectedSectorSlug: "energia",
  });

  assert.equal(summary.totalCompanies, 6);
  assert.equal(summary.companiesWithHistoricalData, 4);
  assert.equal(summary.companiesWithoutHistoricalData, 2);
  assert.equal(summary.completedCells, 7);
  assert.equal(summary.missingCells, 3);
  assert.equal(estimates.full.affected, 2);
  assert.match(estimates.full.description, /2 empresas no setor Energia/);
  assert.equal(estimates.missing.affected, 3);
  assert.match(estimates.missing.description, /3 lacunas na janela 2024-2025/);
  assert.equal(estimates.outdated.affected, null);
});

test("update-base history exposes explicit empty and terminal states", () => {
  assert.deepEqual(buildHistoryRows([]), []);
  assert.equal(
    getHistoryState({ jobsState: "available", activeJobCount: 0, historyCount: 0 }),
    "no_history_no_active_job",
  );

  const rows = buildHistoryRows([
    {
      job_id: "job-1",
      state: "success",
      mode: "missing",
      queued: 3,
      processed: 3,
      failures: 0,
      started_at: "2026-05-04T15:00:00",
      finished_at: "2026-05-04T15:02:05",
      log_lines: [],
    },
  ]);

  assert.equal(rows.length, 1);
  assert.equal(rows[0]?.typeLabel, "Faltantes");
  assert.equal(rows[0]?.status, "success");
  assert.equal(rows[0]?.duration, "2m 5s");
  assert.equal(
    getHistoryState({ jobsState: "available", activeJobCount: 1, historyCount: 0 }),
    "active_jobs_no_history",
  );
});

test("progress fallback uses stage floor when numeric progress stalls", () => {
  assert.equal(getStageProgressFloor("planning"), 8);
  assert.equal(getStageProgressFloor("persist_reports"), 82);
  assert.equal(getStageProgressFloor("unknown"), 0);

  assert.equal(
    computeRefreshProgress({ numericPct: 0, stageFloor: 35, isStalled: true }),
    35,
  );
  assert.equal(
    computeRefreshProgress({ numericPct: 42, stageFloor: 35, isStalled: false }),
    42,
  );
});

// ---------------------------------------------------------------------------
// fetchBatchRefresh — web mode
// ---------------------------------------------------------------------------

test("fetchBatchRefresh (web) posts to /api/refresh-batch and returns dispatch response", async () => {
  const dispatch = {
    status: "running",
    job_id: "abc123",
    queued: 5,
    message: "Refresh iniciado em background.",
    is_retry_allowed: false,
  };

  let capturedUrl = "";
  let capturedMethod = "";
  let capturedBody: unknown = null;

  const restore = withFetchMock((async (input: RequestInfo | URL, init?: RequestInit) => {
    capturedUrl = typeof input === "string" ? input : String(input);
    capturedMethod = init?.method ?? "GET";
    capturedBody = init?.body ? JSON.parse(String(init.body)) : null;
    return new Response(JSON.stringify(dispatch), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as FetchMock);

  try {
    const result = await fetchBatchRefresh({ mode: "missing" });
    assert.ok(capturedUrl.endsWith("/api/refresh-batch"), `unexpected url: ${capturedUrl}`);
    assert.equal(capturedMethod, "POST");
    assert.equal((capturedBody as { mode: string }).mode, "missing");
    assert.equal(result.status, "running");
    assert.equal(result.job_id, "abc123");
    assert.equal(result.queued, 5);
  } finally {
    restore();
  }
});

test("fetchBatchRefresh (web) passes canonical filters in the request body", async () => {
  let capturedBody: Record<string, unknown> = {};

  const restore = withFetchMock((async (_: RequestInfo | URL, init?: RequestInit) => {
    capturedBody = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    return new Response(
      JSON.stringify({ status: "queued", job_id: "x", queued: 2, message: "ok", is_retry_allowed: false }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }) as FetchMock);

  try {
    await fetchBatchRefresh({
      mode: "outdated",
      sectorSlug: "financeiro",
      statusFilter: "failed",
      cvmRange: { start: 100, end: 999 },
    });
    assert.equal(capturedBody.mode, "outdated");
    assert.equal(capturedBody.sector_slug, "financeiro");
    assert.equal(capturedBody.status_filter, "failed");
    assert.deepEqual(capturedBody.cvm_range, { start: 100, end: 999 });
    assert.equal("sector" in capturedBody, false);
    assert.equal("cvm_from" in capturedBody, false);
    assert.equal("cvm_to" in capturedBody, false);
  } finally {
    restore();
  }
});

test("fetchBatchRefresh (web) throws on network failure", async () => {
  const restore = withFetchMock((async () => {
    throw new TypeError("fetch failed");
  }) as FetchMock);

  try {
    await assert.rejects(() => fetchBatchRefresh({ mode: "full" }));
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// fetchBatchJobStatus — web mode
// ---------------------------------------------------------------------------

test("fetchBatchJobStatus (web) fetches from /api/refresh-jobs/:id", async () => {
  const jobStatus = {
    job_id: "abc123",
    state: "running",
    queued: 10,
    processed: 3,
    failures: 0,
    current_cvm: 9512,
    log_lines: ["Baixando PETROBRAS", "Processando PETROBRAS"],
  };

  let capturedUrl = "";
  const restore = withFetchMock((async (input: RequestInfo | URL) => {
    capturedUrl = typeof input === "string" ? input : String(input);
    return new Response(JSON.stringify(jobStatus), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as FetchMock);

  try {
    const result = await fetchBatchJobStatus("abc123");
    assert.ok(capturedUrl.includes("/api/refresh-jobs/abc123"), `unexpected url: ${capturedUrl}`);
    assert.equal(result.state, "running");
    assert.equal(result.processed, 3);
    assert.equal(result.current_cvm, 9512);
    assert.deepEqual(result.log_lines, jobStatus.log_lines);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// cancelBatchJob — web mode
// ---------------------------------------------------------------------------

test("cancelBatchJob (web) posts to the real cancel route", async () => {
  let capturedUrl = "";
  let capturedMethod = "";
  const restore = withFetchMock((async (input: RequestInfo | URL, init?: RequestInit) => {
    capturedUrl = String(input);
    capturedMethod = init?.method ?? "GET";
    return new Response(JSON.stringify({ ok: true, message: "Cancelamento solicitado." }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as FetchMock);

  try {
    const result = await cancelBatchJob("job 123");
    assert.ok(capturedUrl.endsWith("/api/refresh-jobs/job%20123/cancel"), `unexpected url: ${capturedUrl}`);
    assert.equal(capturedMethod, "POST");
    assert.equal(result.ok, true);
    assert.equal(result.message, "Cancelamento solicitado.");
  } finally {
    restore();
  }
});

test("cancelBatchJob (web) throws when cancel route rejects the request", async () => {
  const restore = withFetchMock((async () => {
    return new Response(JSON.stringify({ error: { code: "cancel_failed", message: "Job ja finalizado." } }), {
      status: 409,
      headers: { "content-type": "application/json" },
    });
  }) as FetchMock);

  try {
    await assert.rejects(
      () => cancelBatchJob("finished-job"),
      (err: unknown) => {
        assert.ok(err instanceof Error);
        assert.match(err.message, /Job ja finalizado/);
        return true;
      },
    );
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeRequestBatchRefresh — desktop mode
// ---------------------------------------------------------------------------

test("bridgeRequestBatchRefresh calls request_refresh with mode param", async () => {
  let capturedParams: Record<string, unknown> = {};
  const dispatchResponse = {
    status: "running",
    job_id: "bridge-job-1",
    queued: 449,
    message: "ok",
    is_retry_allowed: false,
  };

  const restore = withPywebview({
    request_refresh: async (params: Record<string, unknown>) => {
      capturedParams = params;
      return dispatchResponse;
    },
  } as unknown as PyApi);

  try {
    const result = await bridgeRequestBatchRefresh({ mode: "full" });
    assert.equal(capturedParams.mode, "full");
    assert.equal(result.status, "running");
    assert.equal(result.job_id, "bridge-job-1");
  } finally {
    restore();
  }
});

test("bridgeRequestBatchRefresh passes canonical optional filters", async () => {
  let capturedParams: Record<string, unknown> = {};

  const restore = withPywebview({
    request_refresh: async (params: Record<string, unknown>) => {
      capturedParams = params;
      return { status: "queued", job_id: "j", queued: 1, message: "ok", is_retry_allowed: false };
    },
  } as unknown as PyApi);

  try {
    await bridgeRequestBatchRefresh({
      mode: "missing",
      sectorSlug: "energia",
      statusFilter: "failed",
      cvmRange: { start: 200 },
    });
    assert.equal(capturedParams.sector_slug, "energia");
    assert.equal(capturedParams.status_filter, "failed");
    assert.deepEqual(capturedParams.cvm_range, { start: 200 });
    assert.equal("sector" in capturedParams, false);
    assert.equal("cvm_from" in capturedParams, false);
    assert.equal("cvm_to" in capturedParams, false);
  } finally {
    restore();
  }
});

test("resolveBatchRefreshCvmRange blocks invalid client ranges before dispatch", () => {
  assert.deepEqual(resolveBatchRefreshCvmRange("4000", "12000"), {
    cvmRange: { start: 4000, end: 12000 },
    error: null,
  });
  assert.deepEqual(resolveBatchRefreshCvmRange("4000", ""), {
    cvmRange: { start: 4000 },
    error: null,
  });
  assert.equal(resolveBatchRefreshCvmRange("abc", "12000").cvmRange, null);
  assert.match(
    resolveBatchRefreshCvmRange("12000", "4000").error ?? "",
    /inicial nao pode ser maior/i,
  );
});

// ---------------------------------------------------------------------------
// bridgeFetchBatchStatus — desktop mode
// ---------------------------------------------------------------------------

test("bridgeFetchBatchStatus calls get_refresh_status with job_id", async () => {
  let capturedParams: Record<string, unknown> = {};
  const statusResponse = {
    job_id: "bridge-job-1",
    state: "success",
    queued: 10,
    processed: 10,
    failures: 1,
    log_lines: ["Done"],
  };

  const restore = withPywebview({
    get_refresh_status: async (params?: Record<string, unknown>) => {
      capturedParams = params ?? {};
      return statusResponse;
    },
  } as unknown as PyApi);

  try {
    const result = await bridgeFetchBatchStatus("bridge-job-1");
    assert.equal(capturedParams.job_id, "bridge-job-1");
    assert.equal(result.state, "success");
    assert.equal(result.processed, 10);
  } finally {
    restore();
  }
});

// ---------------------------------------------------------------------------
// bridgeCancelRefresh — desktop mode
// ---------------------------------------------------------------------------

test("bridgeCancelRefresh calls cancel_refresh with job_id", async () => {
  let capturedParams: Record<string, unknown> = {};

  const restore = withPywebview({
    cancel_refresh: async (params: Record<string, unknown>) => {
      capturedParams = params;
      return { ok: true, message: "Cancelamento solicitado." };
    },
  } as unknown as PyApi);

  try {
    const result = await bridgeCancelRefresh("bridge-job-1");
    assert.equal(capturedParams.job_id, "bridge-job-1");
    assert.equal(result.ok, true);
  } finally {
    restore();
  }
});

test("bridgeCancelRefresh throws on bridge error envelope", async () => {
  const restore = withPywebview({
    cancel_refresh: async () => ({ error: "job not found" }),
  } as unknown as PyApi);

  try {
    await assert.rejects(
      () => bridgeCancelRefresh("no-such-job"),
      (err: unknown) => {
        assert.ok(err instanceof Error);
        assert.match((err as Error).message, /job not found/);
        return true;
      },
    );
  } finally {
    restore();
  }
});
