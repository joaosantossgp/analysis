import {
  fetchCompanies,
  fetchCompanyFilters,
  fetchCompanySuggestions,
  getUserFacingErrorMessage,
  type CompanyDirectoryPage,
  type CompanyFiltersResponse,
  type CompanySuggestionsResponse,
} from "./api.ts";
import { settledOr, settledReason } from "./promise-helpers.ts";

type CompaniesPageLoaders = {
  fetchDirectory?: () => Promise<CompanyDirectoryPage>;
  fetchFilters?: () => Promise<CompanyFiltersResponse>;
  fetchFallbackSuggestions?: () => Promise<CompanySuggestionsResponse>;
};

export type CompaniesPageData = {
  directory: CompanyDirectoryPage | null;
  filters: CompanyFiltersResponse | null;
  fallbackSuggestions: CompanySuggestionsResponse | null;
  directoryError: string | null;
  filtersError: string | null;
  fallbackSuggestionsError: string | null;
};

export async function loadCompaniesPageData(
  params: {
    search: string;
    sector: string | null;
    page: number;
    pageSize: number;
  },
  loaders: CompaniesPageLoaders = {},
): Promise<CompaniesPageData> {
  const fetchDirectory =
    loaders.fetchDirectory ??
    (() =>
      fetchCompanies({
        search: params.search,
        sector: params.sector,
        page: params.page,
        pageSize: params.pageSize,
      }));
  const fetchFilters = loaders.fetchFilters ?? (() => fetchCompanyFilters());
  const shouldFetchFallbackSuggestions =
    params.search.trim().length >= 2 && !params.sector;
  const fetchFallbackSuggestions =
    loaders.fetchFallbackSuggestions ??
    (() => fetchCompanySuggestions(params.search, 6));

  const [directoryResult, filtersResult, fallbackSuggestionsResult] = await Promise.allSettled([
    fetchDirectory(),
    fetchFilters(),
    shouldFetchFallbackSuggestions
      ? fetchFallbackSuggestions()
      : Promise.resolve({ items: [] }),
  ]);

  return {
    directory: settledOr(directoryResult, null),
    filters: settledOr(filtersResult, null),
    fallbackSuggestions: settledOr(fallbackSuggestionsResult, null),
    directoryError: settledReason(directoryResult, getUserFacingErrorMessage),
    filtersError: settledReason(filtersResult, getUserFacingErrorMessage),
    fallbackSuggestionsError: settledReason(
      fallbackSuggestionsResult,
      getUserFacingErrorMessage,
    ),
  };
}
