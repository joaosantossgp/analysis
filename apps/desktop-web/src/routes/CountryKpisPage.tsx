/**
 * CountryKpisPage — top-level stub route at /country-kpis.
 *
 * Shows Energy Utilities country KPIs for all v1 peer countries.
 * The registry is multi-sector by design; this route will serve as the
 * discovery entry point for all sector country KPIs in a future iteration.
 * TODO: multi-sector filter in v2
 */
import { PageHeader } from "@/components/PageHeader";
import { CountryKpiGrid } from "@/components/indicators/CountryKpiGrid";

export function CountryKpisPage() {
  const breadcrumbs = [{ label: "Country KPIs" }];

  return (
    <section className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg space-y-4">
      <PageHeader
        title="Country KPIs"
        subtitle="Energy Utilities · Country-level electricity matrix, carbon intensity, and demand indicators"
        breadcrumbs={breadcrumbs}
      />
      <CountryKpiGrid />
    </section>
  );
}
