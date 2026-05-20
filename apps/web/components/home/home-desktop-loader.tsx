"use client";

import { useState } from "react";

import { BentoFeatures } from "@/components/home/bento-features";
import { CompanySearchHero } from "@/components/home/company-search-hero";
import { HomeTrustStrip } from "@/components/home/home-trust-strip";
import { PageShell } from "@/components/shared/design-system-recipes";
import { useDesktopLoader } from "@/components/shared/use-desktop-loader";
import { bridgeFetchCompanies } from "@/lib/desktop-bridge";

export function HomeDesktopLoader() {
  const [totalCompanies, setTotalCompanies] = useState<number | null>(null);

  useDesktopLoader("home", async (isCancelled) => {
    const statsResult = await bridgeFetchCompanies({ page: 1, pageSize: 1 }).catch(
      () => null,
    );
    if (isCancelled()) return;
    setTotalCompanies(statsResult?.pagination.total_items ?? null);
  });

  return (
    <PageShell density="relaxed" className="flex flex-col items-center gap-20 pb-24">
      <CompanySearchHero />
      <HomeTrustStrip totalCompanies={totalCompanies} disableHealthCheck />
      <BentoFeatures />
    </PageShell>
  );
}
