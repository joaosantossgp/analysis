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
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { Segmented } from "@/components/indicators/Segmented";
import { IndicatorExplorer } from "@/components/indicators/explorer/IndicatorExplorer";
import { SectorCompanyPanel } from "@/components/indicators/SectorCompanyPanel";
import { whenBridgeReady } from "@/lib/bridge/adapter";

type View = "explorer" | "sector";

export function CountryKpisPage() {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [view, setView] = useState<View>("explorer");

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
            : "Microeconomic context: sector snapshots and company-level KPI coverage from the local CVM database."
        }
        breadcrumbs={[{ label: "Indicators" }]}
        actions={
          <Segmented
            ariaLabel="Indicators view"
            value={view}
            options={[
              { value: "explorer", label: "Explorer" },
              { value: "sector", label: "Sector & Company" },
            ]}
            onChange={setView}
          />
        }
      />

      {view === "explorer" ? (
        <IndicatorExplorer bridgeReady={bridgeReady} />
      ) : (
        <SectorCompanyPanel bridgeReady={bridgeReady} />
      )}
    </section>
  );
}
