"use client";

import { useEffect, useState } from "react";

import { ComparePageView } from "@/components/compare/compare-page-view";
import {
  PageShell,
  SectionHeading,
  SurfaceCard,
} from "@/components/shared/design-system-recipes";
import { useDesktopBridgeReady } from "@/components/shared/use-desktop-bridge-ready";
import type { CompanySuggestionItem } from "@/lib/api";
import {
  EMPTY_COMPARE_PAGE_DATA,
  loadComparePageData,
  type CompareCompanyOption,
} from "@/lib/compare-page-data";
import {
  bridgeFetchCompanyInfo,
  bridgeFetchCompanyKpis,
  bridgeFetchCompanySuggestions,
  bridgeFetchCompanyYears,
} from "@/lib/desktop-bridge";
import { getSectorNameFromSlug } from "@/lib/constants";

type CompareDesktopLoaderProps = {
  ids: string | undefined;
  years: string | undefined;
};

function toQuickOption(item: CompanySuggestionItem): CompareCompanyOption {
  return {
    cd_cvm: item.cd_cvm,
    company_name: item.company_name,
    ticker_b3: item.ticker_b3,
    sector_name: getSectorNameFromSlug(item.sector_slug) ?? "Setor nao informado",
  };
}

const EMPTY_QUICK: CompareCompanyOption[] = [];

export function CompareDesktopLoader({ ids, years }: CompareDesktopLoaderProps) {
  const loadKey = `${ids ?? ""}|${years ?? ""}`;
  const bridgeReady = useDesktopBridgeReady(loadKey);
  const [state, setState] = useState<{
    key: string;
    ready: boolean;
    compareData: Awaited<ReturnType<typeof loadComparePageData>> | null;
    quickCompanies: CompareCompanyOption[];
    bridgeTimeout: boolean;
  } | null>(null);

  useEffect(() => {
    if (bridgeReady !== "ready") return;

    let cancelled = false;

    async function run() {
      if (cancelled) return;

      try {
        const [compareData, quickPayload] = await Promise.all([
          loadComparePageData(ids, years, {
            fetchCompanyInfo: (cd) => bridgeFetchCompanyInfo(cd),
            fetchCompanyYears: (cd) => bridgeFetchCompanyYears(cd),
            fetchCompanyKpis: (cd, yrs) => bridgeFetchCompanyKpis(cd, yrs),
          }),
          bridgeFetchCompanySuggestions("", 8, { readyOnly: true }).catch(() => ({
            items: [] as CompanySuggestionItem[],
          })),
        ]);

        if (cancelled) return;

        const quickCompanies = (quickPayload?.items ?? []).map(toQuickOption).filter(
          (company) =>
            Number.isFinite(company.cd_cvm) &&
            company.cd_cvm > 0 &&
            company.company_name.trim() !== "--",
        );

        setState({
          key: loadKey,
          ready: true,
          compareData,
          quickCompanies,
          bridgeTimeout: false,
        });
      } catch (error) {
        if (cancelled) return;
        setState({
          key: loadKey,
          ready: true,
          compareData: {
            ...EMPTY_COMPARE_PAGE_DATA,
            dataError:
              error instanceof Error
                ? error.message
                : "Nao foi possivel carregar a comparacao local agora.",
          },
          quickCompanies: EMPTY_QUICK,
          bridgeTimeout: false,
        });
      }
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [bridgeReady, loadKey, ids, years]);

  const resolvedState =
    state?.key === loadKey
      ? state
      : bridgeReady === "timeout"
        ? {
            key: loadKey,
            ready: true,
            compareData: null,
            quickCompanies: EMPTY_QUICK,
            bridgeTimeout: true,
          }
        : null;

  if (!resolvedState || !resolvedState.ready) {
    return (
      <PageShell density="default">
        <SurfaceCard tone="muted" padding="hero" className="animate-pulse space-y-4">
          <div className="h-10 w-64 rounded-full bg-muted/70" />
          <div className="h-32 rounded-2xl bg-muted/50" />
        </SurfaceCard>
      </PageShell>
    );
  }

  if (resolvedState.bridgeTimeout) {
    return (
      <PageShell density="default">
        <SectionHeading
          eyebrow="PG-04 - Comparar"
          title="Modo desktop indisponivel"
          titleAs="h1"
          description="Bridge local do desktop indisponivel. Reabra o aplicativo para carregar os dados locais."
        />
      </PageShell>
    );
  }

  if (!resolvedState.compareData) {
    return (
      <PageShell density="default">
        <SurfaceCard tone="muted" padding="hero" className="animate-pulse space-y-4">
          <div className="h-10 w-64 rounded-full bg-muted/70" />
          <div className="h-32 rounded-2xl bg-muted/50" />
        </SurfaceCard>
      </PageShell>
    );
  }

  return (
    <ComparePageView
      compareData={resolvedState.compareData}
      quickCompanies={resolvedState.quickCompanies}
    />
  );
}
