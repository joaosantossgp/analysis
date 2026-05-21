/**
 * Companies API facade.
 *
 * Calls CVMBridge.get_companies via the bridge adapter. Phase 1.5 only —
 * Phase 2 will route through the same facade once we drop the
 * embedded Next.js server.
 */
import { callBridge, getBridgeMode, type BridgeMode } from "../bridge/adapter";
import type {
  CompaniesQuery,
  CompanyDirectoryPage,
} from "../bridge/types";

export type CompaniesResult =
  | { mode: "desktop"; page: CompanyDirectoryPage }
  | { mode: "browser"; page: null; reason: string };

const BROWSER_REASON =
  "Running in browser mode — pywebview bridge is unavailable. Launch via the pywebview smoke (scripts/phase1_pywebview_smoke.py) or the packaged exe to see real company data.";

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
