import { BentoFeatures } from "@/components/home/bento-features";
import { CompanySearchHero } from "@/components/home/company-search-hero";
import { HomeDesktopLoader } from "@/components/home/home-desktop-loader";
import { HomeTrustStrip } from "@/components/home/home-trust-strip";
import { PageShell } from "@/components/shared/design-system-recipes";
import { fetchCompanies } from "@/lib/api";
import { isDesktopServerMode } from "@/lib/desktop-mode";
import { settledOr } from "@/lib/promise-helpers";

// Keep at 300 to match the perf baseline.
export const revalidate = 300;

export default async function HomePage() {

  if (isDesktopServerMode()) {
    return <HomeDesktopLoader />;
  }

  const [statsResult] = await Promise.allSettled([
    // Minimal fetch only for the total company count used by HomeTrustStrip
    fetchCompanies({ page: 1, pageSize: 1 }),
  ]);

  const totalCompanies =
    settledOr(statsResult, null)?.pagination.total_items ?? null;

  return (
    <PageShell density="relaxed" className="flex flex-col items-center gap-20 pb-24">
      {/* Hero with Search */}
      <CompanySearchHero />

      {/* Trust and live health */}
      <HomeTrustStrip totalCompanies={totalCompanies} />

      {/* Bento Features Grid */}
      <BentoFeatures />
    </PageShell>
  );
}
