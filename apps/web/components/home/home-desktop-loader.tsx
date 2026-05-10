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
import {
  bridgeFetchCompanies,
  bridgeFetchEmDestaque,
  bridgeFetchSectors,
} from "@/lib/desktop-bridge";

export function HomeDesktopLoader() {
  const bridgeReady = useDesktopBridgeReady("home");
  const [destaqueCompanies, setDestaqueCompanies] = useState<
    Awaited<ReturnType<typeof bridgeFetchEmDestaque>>["items"]
  >([]);
  const [totalCompanies, setTotalCompanies] = useState<number | null>(null);
  const [gicsSectors, setGicsSectors] = useState<
    Array<{
      sector_name: string;
      sector_slug: string;
      company_count: number;
      gics_sector: string;
      gics_sector_slug: string;
    }>
  >([]);

  useEffect(() => {
    if (bridgeReady !== "ready") return;

    let cancelled = false;

    async function load() {
      if (cancelled) return;

      const [destaqueResult, statsResult, sectorsResult] = await Promise.allSettled([
        bridgeFetchEmDestaque(),
        bridgeFetchCompanies({ page: 1, pageSize: 1 }),
        bridgeFetchSectors("sector"),
      ]);

      if (cancelled) return;

      setDestaqueCompanies(
        destaqueResult.status === "fulfilled" ? destaqueResult.value.items : [],
      );
      setTotalCompanies(
        statsResult.status === "fulfilled"
          ? (statsResult.value.pagination.total_items ?? null)
          : null,
      );
      setGicsSectors(
        sectorsResult.status === "fulfilled"
          ? sectorsResult.value.items
              .filter((item) => (item.group_type ?? "sector") === "sector")
              .map((item) => ({
                sector_name: item.sector_name,
                sector_slug: item.sector_slug,
                company_count: item.company_count,
                gics_sector: item.sector_name,
                gics_sector_slug: item.sector_slug,
              }))
          : [],
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
      <HomeTrustStrip totalCompanies={totalCompanies} disableHealthCheck />
      <BentoFeatures />
      <DiscoverySectionLazy
        destaqueCompanies={destaqueCompanies}
        gicsSectors={gicsSectors}
      />
      <CtaSection />
    </PageShell>
  );
}
