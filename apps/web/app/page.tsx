import { BentoFeatures } from "@/components/home/bento-features";
import { CompanySearchHero } from "@/components/home/company-search-hero";
import { CtaSection } from "@/components/home/cta-section";
import { DiscoverySectionLazy } from "@/components/home/discovery-section-lazy";
import { HomeDesktopLoader } from "@/components/home/home-desktop-loader";
import { HomeTrustStrip } from "@/components/home/home-trust-strip";
import { StatsStrip } from "@/components/home/stats-strip";
import { PageShell } from "@/components/shared/design-system-recipes";
import {
  fetchCompanies,
  fetchCompanyFilters,
  fetchEmDestaqueCompanies,
  fetchSectorDirectory,
  SECTOR_DIRECTORY_NO_STORE_READ,
} from "@/lib/api";
import { isDesktopServerMode } from "@/lib/desktop-mode";

// Keep at 300 to match the perf baseline.
export const revalidate = 300;

export default async function HomePage() {

  if (isDesktopServerMode()) {
    return <HomeDesktopLoader />;
  }

  const [destaqueResult, statsResult, filtersResult, sectorsResult] = await Promise.allSettled([
    fetchEmDestaqueCompanies(),
    // Minimal fetch only for the total company count used by StatsStrip / HomeTrustStrip
    fetchCompanies({ page: 1, pageSize: 1 }),
    fetchCompanyFilters(),
    // Same source as /setores — fresh fetch avoids stale ISR hiding deploy/backfill
    fetchSectorDirectory({ request: SECTOR_DIRECTORY_NO_STORE_READ }),
  ]);

  const destaqueCompanies =
    destaqueResult.status === "fulfilled" ? destaqueResult.value.items : [];

  const totalCompanies =
    statsResult.status === "fulfilled"
      ? (statsResult.value?.pagination.total_items ?? null)
      : null;

  const directoryItems =
    sectorsResult.status === "fulfilled"
      ? sectorsResult.value.items.filter((item) => (item.group_type ?? "sector") === "sector")
      : [];

  const gicsSectors =
    directoryItems.length > 0
      ? directoryItems.map((item) => ({
          sector_name: item.sector_name,
          sector_slug: item.sector_slug,
          company_count: item.company_count,
          gics_sector: item.sector_name,
          gics_sector_slug: item.sector_slug,
        }))
      : filtersResult.status === "fulfilled"
        ? filtersResult.value.sectors
        : [];

  return (
    <PageShell density="relaxed" className="flex flex-col items-center gap-20 pb-24">
      {/* Hero with Search */}
      <CompanySearchHero />

      {/* Stats Strip */}
      <StatsStrip totalCompanies={totalCompanies} />

      {/* Trust and live health */}
      <HomeTrustStrip totalCompanies={totalCompanies} />

      {/* Bento Features Grid */}
      <BentoFeatures />

      {/* Discovery Section */}
      <DiscoverySectionLazy
        destaqueCompanies={destaqueCompanies}
        gicsSectors={gicsSectors}
      />

      <CtaSection />
    </PageShell>
  );
}
