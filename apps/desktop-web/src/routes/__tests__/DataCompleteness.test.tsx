import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import type { DataCoverageResponse, DataCoverageRow } from "@/lib/bridge/types";

const bridge = vi.hoisted(() => ({
  callBridge: vi.fn(async () => ({ status: "accepted", job_id: "job-1" })),
}));

vi.mock("@/lib/bridge/adapter", () => ({
  callBridge: bridge.callBridge,
  getBridgeMode: () => "desktop",
  whenBridgeReady: () => new Promise(() => {}),
}));

import { retryFailedCompanies } from "@/lib/api/updateBase";
import { DataCoveragePage } from "../DataCoveragePage";

function row(overrides: Partial<DataCoverageRow>): DataCoverageRow {
  return {
    cd_cvm: 9512,
    company_name: "PETROBRAS",
    ticker: "PETR4",
    status: "failed",
    has_registry: true,
    has_dfp: false,
    has_itr: false,
    ticker_mapped: true,
    is_stale: false,
    update_failed: true,
    ignored: false,
    latest_dfp_year: null,
    latest_itr_period: null,
    last_success_at: null,
    last_attempt_at: "2026-11-24T10:00:00Z",
    last_error: "DFP 2024 download failed",
    ...overrides,
  } as DataCoverageRow;
}

function renderPage(rows: DataCoverageRow[]) {
  const client = new QueryClient();
  const data = {
    rows,
    summary: { total: rows.length, complete: 0, partial: 0, no_financial: 1, failed: 1, stale: 0, unmapped: 0, ignored: 0 },
    filter_counts: { all: rows.length },
  } as unknown as DataCoverageResponse;
  client.setQueryData(["data-coverage"], { mode: "desktop", data });
  return renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DataCoveragePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Data completeness", () => {
  it("offers Retry only on failed rows and never links to an update page", () => {
    const html = renderPage([
      row({}),
      row({ cd_cvm: 4170, company_name: "VALE", status: "no_financial", update_failed: false, last_error: null }),
    ]);
    expect(html).toContain("Data completeness");
    expect(html).not.toContain("Database Updates");
    expect(html).not.toContain("/settings/updates");
    expect(html.match(/>Retry</g)).toHaveLength(1);
    expect(html.match(/>Open</g)).toHaveLength(2);
    expect(html.match(/>Ignore</g)).toHaveLength(2);
  });

  it("retries failed companies through the shared retry contract", async () => {
    await retryFailedCompanies([9512]);
    expect(bridge.callBridge).toHaveBeenCalledWith("request_refresh", {
      mode: "failed",
      scope: "retry",
      company_ids: [9512],
    });
  });
});
