import { coercePositiveInt, getFirstParam } from "./search-params.ts";

export const COMPANIES_DIRECTORY_PAGE_SIZE = 20;

export type CompaniesDirectoryViewMode = "rows" | "cards";

type SearchParamsReader = {
  get(name: string): string | null;
};

export type CompaniesDirectoryQueryState = {
  search: string;
  sector: string | null;
  page: number;
  pageSize: number;
  viewMode: CompaniesDirectoryViewMode;
};

export function readCompaniesDirectoryQuery(
  searchParams: SearchParamsReader,
  pageSize = COMPANIES_DIRECTORY_PAGE_SIZE,
): CompaniesDirectoryQueryState {
  const search = searchParams.get("busca")?.trim() ?? "";
  const rawSector = searchParams.get("setor")?.trim() ?? "";

  return {
    search,
    sector: rawSector ? rawSector : null,
    page: coercePositiveInt(searchParams.get("pagina") ?? undefined, 1),
    pageSize,
    viewMode: searchParams.get("view") === "cards" ? "cards" : "rows",
  };
}

export function readCompaniesDirectoryQueryFromRecord(
  searchParamsRecord: Record<string, string | string[] | undefined>,
  pageSize = COMPANIES_DIRECTORY_PAGE_SIZE,
): CompaniesDirectoryQueryState {
  const searchParams = new URLSearchParams();

  Object.entries(searchParamsRecord).forEach(([key, value]) => {
    const firstValue = getFirstParam(value);
    if (firstValue !== undefined) {
      searchParams.set(key, firstValue);
    }
  });

  return readCompaniesDirectoryQuery(searchParams, pageSize);
}

