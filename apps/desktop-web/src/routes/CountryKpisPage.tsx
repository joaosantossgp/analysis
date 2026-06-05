/**
 * Indicators module at /indicators.
 *
 * Thin host for the Indicator Explorer — a scalable, metadata-driven catalog of
 * local-first macro/energy KPIs (country + SIN) with full reproducibility
 * provenance. The former nested Macro/SIN/Matrix/Trend tab tree is superseded:
 * single-KPI trends, the electricity matrix, and the SIN generation mix are now
 * launched from each indicator's detail panel inside the Explorer.
 *
 * "Sector & Company" remains as a secondary view (microeconomic CVM coverage),
 * since it is owned by a different data layer (read-service / KPI engine) and is
 * not part of the energy `kpi_catalog`.
 */
import { lazy, Suspense, useEffect, useState, useTransition } from "react";

import { PageHeader } from "@/components/PageHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { Segmented } from "@/components/indicators/Segmented";
import { whenBridgeReady } from "@/lib/bridge/adapter";

type View = "explorer" | "plants" | "sector";

const IndicatorExplorer = lazy(() =>
  import("@/components/indicators/explorer/IndicatorExplorer").then((m) => ({ default: m.IndicatorExplorer })),
);
const PlantParcelExplorer = lazy(() =>
  import("@/components/indicators/PlantParcelExplorer").then((m) => ({ default: m.PlantParcelExplorer })),
);
const SectorCompanyPanel = lazy(() =>
  import("@/components/indicators/SectorCompanyPanel").then((m) => ({ default: m.SectorCompanyPanel })),
);

export function CountryKpisPage() {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [view, setView] = useState<View>("explorer");
  const [, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="min-w-0 max-w-full rounded-lg border border-zinc-800 bg-zinc-900/60 p-6 shadow-lg space-y-5">
      <PageHeader
        title="Indicators"
        subtitle={
          view === "explorer"
            ? "Local-first indicator explorer — macro and energy KPIs with full source, methodology, and cache provenance."
            : view === "plants"
              ? "Energy Utilities plant and CCEE plant-parcel explorer with source refresh, cache status, and audit metadata."
            : "Microeconomic context: sector snapshots and company-level KPI coverage from the local CVM database."
        }
        breadcrumbs={[{ label: "Indicators" }]}
        actions={
          <Segmented
            ariaLabel="Indicators view"
            value={view}
            options={[
              { value: "explorer", label: "Explorer" },
              { value: "plants", label: "Plant Parcels" },
              { value: "sector", label: "Sector & Company" },
            ]}
            onChange={(next) => startTransition(() => setView(next))}
          />
        }
      />

      <Suspense fallback={<StateBanner variant="loading" title="Loading indicator view…" />}>
        {view === "explorer" ? (
          <IndicatorExplorer bridgeReady={bridgeReady} />
        ) : view === "plants" ? (
          <PlantParcelExplorer bridgeReady={bridgeReady} />
        ) : (
          <SectorCompanyPanel bridgeReady={bridgeReady} />
        )}
      </Suspense>
    </section>
  );
}
