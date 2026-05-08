"use client";

import { useEffect, useState } from "react";

import { BentoFeatures } from "@/components/home/bento-features";
import { CompanySearchHero } from "@/components/home/company-search-hero";
import { CtaSection } from "@/components/home/cta-section";
import { DiscoverySectionLazy } from "@/components/home/discovery-section-lazy";
import { HomeTrustStrip } from "@/components/home/home-trust-strip";
import { StatsStrip } from "@/components/home/stats-strip";
import { PageShell } from "@/components/shared/design-system-recipes";
import { useDesktopBridgeReady } from "@/components/shared/use-desktop-bridge-ready";
import type { CompanyDirectoryItem } from "@/lib/api";
import {
  bridgeFetchCompanies,
  bridgeFetchEmDestaque,
  bridgeFetchPopulares,
} from "@/lib/desktop-bridge";

type PopularesState = "loading" | "empty" | "error" | "ready";

export function HomeDesktopLoader() {
  const bridgeReady = useDesktopBridgeReady("home");
  const [popularesCompanies, setPopularesCompanies] = useState<
    CompanyDirectoryItem[]
  >([]);
  const [popularesState, setPopularesState] = useState<PopularesState>("loading");
  const [destaqueCompanies, setDestaqueCompanies] = useState<
    CompanyDirectoryItem[]
  >([]);
  const [totalCompanies, setTotalCompanies] = useState<number | null>(null);

  useEffect(() => {
    if (bridgeReady !== "ready") return;

    let cancelled = false;

    async function load() {
      if (cancelled) return;

      const [popularesResult, destaqueResult, statsResult] =
        await Promise.allSettled([
          bridgeFetchPopulares(),
          bridgeFetchEmDestaque(),
          bridgeFetchCompanies({ page: 1, pageSize: 1 }),
        ]);

      if (cancelled) return;

      setPopularesCompanies(
        popularesResult.status === "fulfilled" ? popularesResult.value.items : [],
      );
      if (popularesResult.status === "rejected") {
        setPopularesState("error");
      } else if (popularesResult.value.items.length === 0) {
        setPopularesState("empty");
      } else {
        setPopularesState("ready");
      }
      setDestaqueCompanies(
        destaqueResult.status === "fulfilled" ? destaqueResult.value.items : [],
      );
      setTotalCompanies(
        statsResult.status === "fulfilled"
          ? (statsResult.value.pagination.total_items ?? null)
          : null,
      );
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [bridgeReady]);

  return (
    <PageShell density="relaxed" className="flex flex-col items-center gap-20 pb-24">
      <CompanySearchHero />
      <StatsStrip totalCompanies={totalCompanies} />
      <HomeTrustStrip totalCompanies={totalCompanies} />
      <BentoFeatures />
      <DiscoverySectionLazy
        popularesCompanies={popularesCompanies}
        popularesState={popularesState}
        destaqueCompanies={destaqueCompanies}
      />
      <CtaSection />
    </PageShell>
  );
}
