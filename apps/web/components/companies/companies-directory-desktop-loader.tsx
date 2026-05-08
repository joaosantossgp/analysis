"use client";

import { useEffect, useState } from "react";

import {
  CompaniesDirectoryLoadingState,
  CompaniesDirectoryPageContent,
} from "@/components/companies/companies-directory-client";
import { useDesktopBridgeReady } from "@/components/shared/use-desktop-bridge-ready";
import type { CompaniesDirectoryQueryState } from "@/lib/companies-directory-query";
import type { CompaniesPageData } from "@/lib/companies-page-data";
import {
  bridgeFetchCompanies,
  bridgeFetchCompanyFilters,
  bridgeFetchCompanySuggestions,
} from "@/lib/desktop-bridge";

type CompaniesDirectoryDesktopLoaderProps = Pick<
  CompaniesDirectoryQueryState,
  "page" | "pageSize" | "search" | "sector" | "viewMode"
>;

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

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Nao foi possivel carregar os dados locais agora.";
}

export function CompaniesDirectoryDesktopLoader({
  page,
  pageSize,
  search,
  sector,
  viewMode,
}: CompaniesDirectoryDesktopLoaderProps) {
  const loadKey = `${search}|${sector ?? ""}|${page}|${pageSize}`;
  const bridgeReady = useDesktopBridgeReady(loadKey);
  const [loadState, setLoadState] = useState<{
    key: string;
    data: CompaniesPageData;
  } | null>(null);

  useEffect(() => {
    if (bridgeReady !== "ready") return;

    let cancelled = false;

    async function loadFromBridge() {
      if (cancelled) return;

      const shouldFetchFallbackSuggestions =
        search.trim().length >= 2 && !sector;
      const [directoryResult, filtersResult, fallbackSuggestionsResult] =
        await Promise.allSettled([
          bridgeFetchCompanies({ search, sector, page, pageSize }),
          bridgeFetchCompanyFilters(),
          shouldFetchFallbackSuggestions
            ? bridgeFetchCompanySuggestions(search, 6)
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
              ? errorMessage(directoryResult.reason)
              : null,
          filtersError:
            filtersResult.status === "rejected"
              ? errorMessage(filtersResult.reason)
              : null,
          fallbackSuggestionsError:
            fallbackSuggestionsResult.status === "rejected"
              ? errorMessage(fallbackSuggestionsResult.reason)
              : null,
        },
      });
    }

    void loadFromBridge();

    return () => {
      cancelled = true;
    };
  }, [bridgeReady, loadKey, page, pageSize, search, sector]);

  const timeoutState =
    bridgeReady === "timeout"
      ? {
          key: loadKey,
          data: emptyDesktopData(
            "Bridge local do desktop indisponivel. Reabra o aplicativo para carregar os dados locais.",
          ),
        }
      : null;
  const resolvedState =
    loadState?.key === loadKey ? loadState : timeoutState;

  if (!resolvedState) {
    return <CompaniesDirectoryLoadingState />;
  }

  return (
    <CompaniesDirectoryPageContent
      data={resolvedState.data}
      page={page}
      pageSize={pageSize}
      search={search}
      sector={sector}
      viewMode={viewMode}
    />
  );
}
