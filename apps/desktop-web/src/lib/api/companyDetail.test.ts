import { beforeEach, describe, expect, it, vi } from "vitest";

import * as adapter from "../bridge/adapter";
import * as companyDetail from "./companyDetail";

vi.mock("../bridge/adapter", () => ({
  callBridge: vi.fn(),
  getBridgeMode: vi.fn(),
}));

type FinancialReadinessFetcher = (cdCvm: number) => Promise<unknown>;

function getFinancialReadinessFetcher(): FinancialReadinessFetcher {
  const fetcher = Reflect.get(
    companyDetail,
    "fetchCompanyFinancialReadiness",
  );
  expect(fetcher).toBeTypeOf("function");
  return fetcher as FinancialReadinessFetcher;
}

describe("company financial-readiness facade", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps browser mode local and does not call the bridge", async () => {
    vi.mocked(adapter.getBridgeMode).mockReturnValue("browser");

    const result = await getFinancialReadinessFetcher()(9512);

    expect(result).toMatchObject({ mode: "browser", readiness: null });
    expect(adapter.callBridge).not.toHaveBeenCalled();
  });

  it("forwards the bounded readiness request and preserves the typed payload", async () => {
    const readiness = {
      cd_cvm: 9512,
      source_class: "official_reported",
      source_label: "CVM DFP/ITR filings",
      availability_state: "ready",
      freshness_state: "fresh",
      refresh_state: "successful",
      has_local_financial_reports: true,
      available_periods: [
        {
          period_label: "FY2024",
          period_display: "FY 2024",
          period_type: "annual",
          period_year: 2024,
          period_quarter: null,
        },
      ],
      local_read_model_updated_at: "2025-03-01T12:00:00Z",
      last_successful_refresh_at: "2025-03-01T12:00:00Z",
      latest_local_evidence_at: "2025-03-01T12:00:00Z",
      last_refresh_error: null,
      financial_export_eligible: true,
      exportable_years: [2024],
      refresh_available: true,
    };
    vi.mocked(adapter.getBridgeMode).mockReturnValue("desktop");
    vi.mocked(adapter.callBridge).mockResolvedValue(readiness as never);

    const result = await getFinancialReadinessFetcher()(9512);

    expect(adapter.callBridge).toHaveBeenCalledWith(
      "get_company_financial_readiness",
      { cd_cvm: 9512 },
    );
    expect(result).toEqual({ mode: "desktop", readiness });
  });
});
