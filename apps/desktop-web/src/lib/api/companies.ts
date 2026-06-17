/**
 * Companies API facade.
 *
 * Calls CVMBridge.get_companies via the bridge adapter. The packaged desktop
 * app uses this bridge as the production data path.
 */
import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type {
  CompaniesQuery,
  CompanyDirectoryPage,
  CompanyFiltersResponse,
  CompanyHistoricalIndicatorsResult,
  CompanySectorFilterOption,
} from "../bridge/types";

export type { CompanyHistoricalIndicatorsResult } from "../bridge/types";

export type CompaniesResult =
  | { mode: "desktop"; page: CompanyDirectoryPage }
  | { mode: "browser"; page: null; reason: string };

export type CompanyFiltersResult =
  | { mode: "desktop"; sectors: CompanySectorFilterOption[] }
  | { mode: "browser"; sectors: []; reason: string };

const BROWSER_REASON =
  "Running in browser mode — pywebview bridge is unavailable. Launch via the pywebview smoke (scripts/diagnostics/phase1_pywebview_smoke.py) or the packaged exe to see real company data.";

/**
 * Fetch a paginated company directory page.
 *
 * Bridge contract (mirrors `desktop/bridge.py::CVMBridge.get_companies`):
 *   - `search` is a substring matched on company_name/ticker by the
 *     service layer; empty string returns the full directory.
 *   - `sector_slug` filters to a single sector. null/undefined = all sectors.
 *   - `page` is 1-indexed. `page_size` is clamped server-side to [1, 100].
 */
export async function fetchCompanies(
  query: CompaniesQuery = {},
): Promise<CompaniesResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", page: null, reason: BROWSER_REASON };
  }
  const params = {
    search: query.search ?? "",
    sector_slug: query.sector_slug ?? null,
    page: query.page ?? 1,
    page_size: query.page_size ?? 20,
  };
  const page = await callBridge("get_companies", params);
  if (page.error) {
    throw new Error(page.error);
  }
  return { mode: "desktop", page };
}

/**
 * Fetch the static directory filter options (sectors). Backed by
 * `CVMBridge.get_company_filters`, which reads from the GICS catalog and
 * counts companies per hub sector. Used by the directory sector dropdown.
 */
export async function fetchCompanyFilters(): Promise<CompanyFiltersResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", sectors: [], reason: BROWSER_REASON };
  }
  const payload: CompanyFiltersResponse = await callBridge(
    "get_company_filters",
    {},
  );
  if (payload.error) {
    throw new Error(payload.error);
  }
  return { mode: "desktop", sectors: payload.sectors ?? [] };
}

export type FetchCompanyHistoricalIndicatorsResult =
  | { mode: "desktop"; data: CompanyHistoricalIndicatorsResult }
  | { mode: "browser"; data: null; reason: string };

/**
 * Fetch historical metrics (ROE, EBIT margin, net margin, and stock price) for a company.
 */
export async function fetchCompanyHistoricalIndicators(
  cdCvm: number,
): Promise<FetchCompanyHistoricalIndicatorsResult> {
  const mode: BridgeMode = getBridgeMode();
  if (mode === "browser") {
    return { mode: "browser", data: null, reason: BROWSER_REASON };
  }
  const data = await callBridge("get_company_historical_indicators", { cd_cvm: cdCvm });
  if (data.error) {
    throw new Error(data.error);
  }
  return { mode: "desktop", data };
}

export interface ResolvedIdentity {
  input: string;
  cd_cvm: number;
  ticker_b3: string | null;
  company_name: string;
  cnpj: string | null;
  gics_sector: string | null;
}

export async function resolveCompanyIdentities(inputs: string[]): Promise<{
  resolved: ResolvedIdentity[];
  unmapped: string[];
}> {
  const mode = getBridgeMode();
  if (mode === "browser") {
    return { resolved: [], unmapped: inputs };
  }
  const res = await callBridge("resolve_company_identities", { inputs });
  if (res.error) throw new Error(res.error);
  return res;
}


