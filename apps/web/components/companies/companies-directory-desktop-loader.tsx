"use client";

import { useEffect, useState } from "react";

import {
  CompaniesDirectoryLoadingState,
  CompaniesDirectoryPageContent,
} from "@/components/companies/companies-directory-client";
import type { CompaniesDirectoryQueryState } from "@/lib/companies-directory-query";
import type { CompaniesPageData } from "@/lib/companies-page-data";
import {
  fetchCompanies,
  fetchCompanyFilters,
  fetchCompanySuggestions,
  getUserFacingErrorMessage,
  isDesktopMode,
} from "@/lib/api";

type CompaniesDirectoryDesktopLoaderProps = Pick<
  CompaniesDirectoryQueryState,
  "page" | "pageSize" | "search" | "sector" | "viewMode"
>;

const BRIDGE_READY_MAX_ATTEMPTS = 60;
const BRIDGE_READY_RETRY_MS = 100;

function emptyDesktopData(error: string): CompaniesPageData {
  return {
    directory: null,
    filters: null,
    fallbackSuggestions: null,
    directoryError: error,
    filtersError: null,
    fallbackSuggestionsError: null,
  };
}

export function CompaniesDirectoryDesktopLoader({
  page,
  pageSize,
  search,
  sector,
  viewMode,
}: CompaniesDirectoryDesktopLoaderProps) {
  const loadKey = `${search}|${sector ?? ""}|${page}|${pageSize}`;
  const [loadState, setLoadState] = useState<{
    key: string;
    data: CompaniesPageData;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;

    async function loadFromBridge() {
      if (cancelled) return;

      if (!isDesktopMode()) {
        attempts += 1;
        if (attempts <= BRIDGE_READY_MAX_ATTEMPTS) {
          timeoutId = setTimeout(loadFromBridge, BRIDGE_READY_RETRY_MS);
          return;
        }

        setLoadState({
          key: loadKey,
          data: emptyDesktopData(
            "Bridge local do desktop indisponivel. Reabra o aplicativo para carregar os dados locais.",
          ),
        });
        return;
      }

      const shouldFetchFallbackSuggestions =
        search.trim().length >= 2 && !sector;
      const [directoryResult, filtersResult, fallbackSuggestionsResult] =
        await Promise.allSettled([
          fetchCompanies({ search, sector, page, pageSize }),
          fetchCompanyFilters(),
          shouldFetchFallbackSuggestions
            ? fetchCompanySuggestions(search, 6)
            : Promise.resolve({ items: [] }),
        ]);

      if (cancelled) return;

      setLoadState({
        key: loadKey,
        data: {
          directory:
            directoryResult.status === "fulfilled" ? directoryResult.value : null,
          filters:
            filtersResult.status === "fulfilled" ? filtersResult.value : null,
          fallbackSuggestions:
            fallbackSuggestionsResult.status === "fulfilled"
              ? fallbackSuggestionsResult.value
              : null,
          directoryError:
            directoryResult.status === "rejected"
              ? getUserFacingErrorMessage(directoryResult.reason)
              : null,
          filtersError:
            filtersResult.status === "rejected"
              ? getUserFacingErrorMessage(filtersResult.reason)
              : null,
          fallbackSuggestionsError:
            fallbackSuggestionsResult.status === "rejected"
              ? getUserFacingErrorMessage(fallbackSuggestionsResult.reason)
              : null,
        },
      });
    }

    void loadFromBridge();

    return () => {
      cancelled = true;
      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
      }
    };
  }, [loadKey, page, pageSize, search, sector]);

  if (!loadState || loadState.key !== loadKey) {
    return <CompaniesDirectoryLoadingState />;
  }

  return (
    <CompaniesDirectoryPageContent
      data={loadState.data}
      page={page}
      pageSize={pageSize}
      search={search}
      sector={sector}
      viewMode={viewMode}
    />
  );
}
