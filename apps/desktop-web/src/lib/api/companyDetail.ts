/**
 * Company detail API facade. Wraps three bridge methods:
 *   - get_company_info   — header card data
 *   - get_company_years  — available year list
 *   - get_company_kpis   — KPI matrix for selected years
 *
 * All calls are read-only. No new Python service code is required.
 */
import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type {
  CompanyFinancialReadiness,
  CompanyInfo,
  CompanyYearsResult,
  KPIBundle,
} from "../bridge/types";

const BROWSER_REASON =
  "Running in browser mode — pywebview bridge is unavailable. Launch via scripts/diagnostics/phase1_pywebview_smoke.py or the packaged exe.";

export type CompanyInfoResult =
  | { mode: "desktop"; info: CompanyInfo }
  | { mode: "desktop-not-found"; cd_cvm: number; catalog_lookup_pending: boolean }
  | { mode: "browser"; reason: string };

export async function fetchCompanyInfo(
  cdCvm: number,
): Promise<CompanyInfoResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", reason: BROWSER_REASON };
  }
  const info = await callBridge("get_company_info", { cd_cvm: cdCvm });
  if (info.not_found) {
    return {
      mode: "desktop-not-found",
      cd_cvm: cdCvm,
      catalog_lookup_pending: Boolean(info.catalog_lookup_pending),
    };
  }
  return { mode: "desktop", info };
}

export type CompanyFinancialReadinessResult =
  | { mode: "desktop"; readiness: CompanyFinancialReadiness }
  | { mode: "browser"; readiness: null; reason: string };

/**
 * Reads the bounded local financial-evidence contract for a company.
 *
 * This facade performs no refresh, export, or network activity. Those actions
 * remain owned by their existing Company Command Bar surfaces.
 */
export async function fetchCompanyFinancialReadiness(
  cdCvm: number,
): Promise<CompanyFinancialReadinessResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", readiness: null, reason: BROWSER_REASON };
  }
  const readiness = await callBridge("get_company_financial_readiness", {
    cd_cvm: cdCvm,
  });
  if (readiness.error) {
    throw new Error(readiness.error);
  }
  return { mode: "desktop", readiness };
}

export type CompanyYearsResultUI =
  | { mode: "desktop"; years: number[] }
  | { mode: "browser"; years: number[]; reason: string };

export async function fetchCompanyYears(
  cdCvm: number,
): Promise<CompanyYearsResultUI> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", years: [], reason: BROWSER_REASON };
  }
  const result: CompanyYearsResult = await callBridge("get_company_years", {
    cd_cvm: cdCvm,
  });
  if (result.error) {
    throw new Error(result.error);
  }
  return { mode: "desktop", years: result.years ?? [] };
}

export type CompanyKpisResult =
  | { mode: "desktop"; bundle: KPIBundle }
  | { mode: "browser"; bundle: null; reason: string };

export async function fetchCompanyKpis(
  cdCvm: number,
  years: number[],
): Promise<CompanyKpisResult> {
  if (getBridgeMode() === "browser") {
    return { mode: "browser", bundle: null, reason: BROWSER_REASON };
  }
  if (years.length === 0) {
    return {
      mode: "desktop",
      bundle: {
        cd_cvm: cdCvm,
        years: [],
        annual: { columns: [], rows: [] },
        quarterly: { columns: [], rows: [] },
      },
    };
  }
  const bundle: KPIBundle = await callBridge("get_company_kpis", {
    cd_cvm: cdCvm,
    years,
  });
  if (bundle.error) {
    throw new Error(bundle.error);
  }
  return { mode: "desktop", bundle };
}

export interface CompanyConnections {
  has_financials: boolean;
  mapped_distributors: number;
  mapped_plants: number;
  total_capacity_mw: number;
}

export type CompanyConnectionsResult =
  | { mode: "desktop"; connections: CompanyConnections }
  | { mode: "browser"; reason: string };

export async function fetchCompanyConnections(
  cdCvm: number,
): Promise<CompanyConnectionsResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", reason: BROWSER_REASON };
  }
  const payload = await callBridge("get_company_connections", { cd_cvm: cdCvm });
  if (payload.error) throw new Error(payload.error);
  return {
    mode: "desktop",
    connections: {
      has_financials: Boolean(payload.has_financials),
      mapped_distributors: payload.mapped_distributors ?? 0,
      mapped_plants: payload.mapped_plants ?? 0,
      total_capacity_mw: payload.total_capacity_mw ?? 0,
    },
  };
}
