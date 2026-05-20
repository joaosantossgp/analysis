"use client";

import { useEffect, useState } from "react";

import { BentoFeatures } from "@/components/home/bento-features";
import { CompanySearchHero } from "@/components/home/company-search-hero";
import { HomeTrustStrip } from "@/components/home/home-trust-strip";
import { PageShell } from "@/components/shared/design-system-recipes";
import { useDesktopBridgeReady } from "@/components/shared/use-desktop-bridge-ready";
import { bridgeFetchCompanies } from "@/lib/desktop-bridge";

export function HomeDesktopLoader() {
  const bridgeReady = useDesktopBridgeReady("home");
  const [totalCompanies, setTotalCompanies] = useState<number | null>(null);

  useEffect(() => {
    if (bridgeReady !== "ready") return;

    let cancelled = false;

    async function load() {
      if (cancelled) return;

      const statsResult = await bridgeFetchCompanies({ page: 1, pageSize: 1 }).catch(
        () => null,
      );

      if (cancelled) return;

      setTotalCompanies(statsResult?.pagination.total_items ?? null);
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [bridgeReady]);

  return (
    <PageShell density="relaxed" className="flex flex-col items-center gap-20 pb-24">
      <CompanySearchHero />
      <HomeTrustStrip totalCompanies={totalCompanies} disableHealthCheck />
      <BentoFeatures />
    </PageShell>
  );
}
