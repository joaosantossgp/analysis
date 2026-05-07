"use client";

import { useEffect, useState } from "react";

import { BentoFeatures } from "@/components/home/bento-features";
import { CompanySearchHero } from "@/components/home/company-search-hero";
import { CtaSection } from "@/components/home/cta-section";
import { DiscoverySectionLazy } from "@/components/home/discovery-section-lazy";
import { HomeTrustStrip } from "@/components/home/home-trust-strip";
import { StatsStrip } from "@/components/home/stats-strip";
import { PageShell } from "@/components/shared/design-system-recipes";
import type { CompanyDirectoryItem } from "@/lib/api";
import {
  bridgeFetchCompanies,
  bridgeFetchEmDestaque,
  bridgeFetchPopulares,
  isDesktopMode,
} from "@/lib/desktop-bridge";

const BRIDGE_READY_MAX_ATTEMPTS = 60;
const BRIDGE_READY_RETRY_MS = 100;

export function HomeDesktopLoader() {
  const [popularesCompanies, setPopularesCompanies] = useState<
    CompanyDirectoryItem[]
  >([]);
  const [destaqueCompanies, setDestaqueCompanies] = useState<
    CompanyDirectoryItem[]
  >([]);
  const [totalCompanies, setTotalCompanies] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;

    async function load() {
      if (cancelled) return;

      if (!isDesktopMode()) {
        attempts += 1;
        if (attempts <= BRIDGE_READY_MAX_ATTEMPTS) {
          timeoutId = setTimeout(load, BRIDGE_READY_RETRY_MS);
          return;
        }
        return;
      }

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
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    };
  }, []);

  return (
    <PageShell density="relaxed" className="flex flex-col items-center gap-20 pb-24">
      <CompanySearchHero />
      <StatsStrip totalCompanies={totalCompanies} />
      <HomeTrustStrip totalCompanies={totalCompanies} />
      <BentoFeatures />
      <DiscoverySectionLazy
        popularesCompanies={popularesCompanies}
        destaqueCompanies={destaqueCompanies}
      />
      <CtaSection />
    </PageShell>
  );
}
