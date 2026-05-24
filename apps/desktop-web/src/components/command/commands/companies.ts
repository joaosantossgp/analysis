import { useQuery } from "@tanstack/react-query";
import type { NavigateFunction } from "react-router-dom";

import { fetchCompanies } from "@/lib/api/companies";
import type { CompanyDirectoryItem } from "@/lib/bridge/types";

import type { Command } from "../CommandRegistry";

/**
 * Companies index for the command palette.
 *
 * Loaded lazily on first palette open via TanStack Query, cached 5 min.
 * Walks the paginated bridge endpoint (page_size=100) until exhausted.
 *
 * In browser mode the query short-circuits to an empty array so the palette
 * still works with routes + actions.
 */

const QUERY_KEY = ["command-palette", "companies-index"] as const;
const PAGE_SIZE = 100;
const MAX_PAGES = 20; // safety cap — covers >2k companies

async function loadAllCompanies(): Promise<CompanyDirectoryItem[]> {
  const all: CompanyDirectoryItem[] = [];
  let page = 1;
  while (page <= MAX_PAGES) {
    const result = await fetchCompanies({
      search: "",
      sector_slug: null,
      page,
      page_size: PAGE_SIZE,
    });
    if (result.mode !== "desktop" || !result.page) return all;
    const items = result.page.items;
    all.push(...items);
    if (!result.page.pagination.has_next) break;
    page += 1;
  }
  return all;
}

/**
 * React hook: returns the cached companies index. Only fires the request
 * when `enabled` is true (i.e. palette has been opened at least once).
 */
export function useCompaniesIndex(enabled: boolean) {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: loadAllCompanies,
    enabled,
    staleTime: 5 * 60 * 1000, // 5 min
    gcTime: 10 * 60 * 1000,
  });
}

/**
 * Convert companies-index rows into commands. Memoize at call site.
 */
export function buildCompanyCommands(
  companies: CompanyDirectoryItem[] | undefined,
  navigate: NavigateFunction,
): Command[] {
  if (!companies) return [];
  return companies.map((c) => {
    const ticker = c.ticker_b3 ? ` · ${c.ticker_b3}` : "";
    return {
      id: `company:${c.cd_cvm}`,
      group: "companies",
      glyph: "company",
      label: c.company_name,
      secondary: `#${c.cd_cvm}${ticker}`,
      keywords: [
        c.company_name,
        String(c.cd_cvm),
        ...(c.ticker_b3 ? [c.ticker_b3] : []),
        c.sector_name,
      ],
      run: () => navigate(`/empresas/${c.cd_cvm}`),
    } as Command;
  });
}
