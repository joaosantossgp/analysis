import { describe, expect, it } from "vitest";

import type { CompanyFinancialReadiness } from "../../lib/bridge/types";
import * as companyDetailPage from "../CompanyDetailPage";

type DisplayState =
  | "ready"
  | "partial"
  | "stale"
  | "failed"
  | "missing"
  | "unknown";
type StateResolver = (readiness: CompanyFinancialReadiness) => DisplayState;

function getStateResolver(): StateResolver {
  const resolver = Reflect.get(
    companyDetailPage,
    "getCompanyFinancialReadinessState",
  );
  expect(resolver).toBeTypeOf("function");
  return resolver as StateResolver;
}

const BASE_READINESS: CompanyFinancialReadiness = {
  cd_cvm: 9512,
  source_class: "official_reported",
  source_label: "CVM DFP/ITR filings",
  availability_state: "ready",
  freshness_state: "fresh",
  refresh_state: "successful",
  has_local_financial_reports: true,
  available_periods: [],
  local_read_model_updated_at: "2025-03-01T12:00:00Z",
  last_successful_refresh_at: "2025-03-01T12:00:00Z",
  latest_local_evidence_at: "2025-03-01T12:00:00Z",
  last_refresh_error: null,
  financial_export_eligible: true,
  exportable_years: [2024],
  refresh_available: true,
};

describe("Company Overview financial-readiness states", () => {
  it("keeps ready, partial, stale, failed, missing, and unknown evidence distinct", () => {
    const resolve = getStateResolver();

    expect(resolve(BASE_READINESS)).toBe("ready");
    expect(
      resolve({
        ...BASE_READINESS,
        availability_state: "partial",
        freshness_state: "unknown",
        financial_export_eligible: false,
      }),
    ).toBe("partial");
    expect(
      resolve({ ...BASE_READINESS, freshness_state: "stale", refresh_state: "no_data" }),
    ).toBe("stale");
    expect(
      resolve({
        ...BASE_READINESS,
        availability_state: "missing",
        freshness_state: "unknown",
        refresh_state: "failed",
        last_refresh_error: "CVM import failed",
      }),
    ).toBe("failed");
    expect(
      resolve({
        ...BASE_READINESS,
        availability_state: "missing",
        freshness_state: "unknown",
        refresh_state: "not_recorded",
        has_local_financial_reports: false,
      }),
    ).toBe("missing");
    expect(
      resolve({
        ...BASE_READINESS,
        freshness_state: "unknown",
        refresh_state: "provider_pending_review",
      }),
    ).toBe("unknown");
  });
});
