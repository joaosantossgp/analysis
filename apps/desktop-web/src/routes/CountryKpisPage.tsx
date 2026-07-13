/**
 * Indicators module at /indicators.
 *
 * Analyst module with:
 *   - Sectors                → Energy as the first deep sector
 *   - Companies & Assets     → CVM registry, sectoral assets, mapping hub
 *   - Indicator Library      → catalog/search surface for KPIs
 *   - Data Health & Sources  → local source coverage and refresh audit
 *   - Exports & Verification → real export paths and pre-export checks
 *
 * URL shape: ?section=<section>&sub=<sub>
 */
import { lazy, Suspense, useEffect, useState, useTransition } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { StateBanner } from "@/components/feedback/StateBanner";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import { fetchDistributionHealth } from "@/lib/api/distribution";
import type { DistributionHealthResponse } from "@/lib/bridge/types";

// ── Lazy-loaded panels ────────────────────────────────────────────────────────
const IndicatorExplorer = lazy(() =>
  import("@/components/indicators/explorer/IndicatorExplorer").then((m) => ({
    default: m.IndicatorExplorer,
  })),
);
const PlantParcelExplorer = lazy(() =>
  import("@/components/indicators/PlantParcelExplorer").then((m) => ({
    default: m.PlantParcelExplorer,
  })),
);
const SectorCompanyPanel = lazy(() =>
  import("@/components/indicators/SectorCompanyPanel").then((m) => ({
    default: m.SectorCompanyPanel,
  })),
);
const DistributorExplorer = lazy(() =>
  import("@/components/indicators/distribution/DistributorExplorer").then(
    (m) => ({ default: m.DistributorExplorer }),
  ),
);
const FuelDistributionExplorer = lazy(() =>
  import("@/components/indicators/FuelDistributionExplorer").then((m) => ({
    default: m.FuelDistributionExplorer,
  })),
);

// ── Types ─────────────────────────────────────────────────────────────────────
type TopSection = "energy" | "entities" | "library" | "health" | "exports";
type EnergySub = "distribution" | "generation" | "fuel" | "sin" | "matrix";

type TopNavItem = {
  id: TopSection;
  label: string;
  description: string;
  marker: string;
};

type ExportWorkflowStatus = "available" | "source-review" | "in-workflow";

type ExportVerificationWorkflow = {
  id: string;
  title: string;
  domain: string;
  status: ExportWorkflowStatus;
  exportScope: string;
  whereToRun: string;
  verificationSignals: string[];
  currentLimit: string;
  actionLabel: string;
  targetSection: TopSection;
  targetSub?: EnergySub;
};

// ── Nav config ────────────────────────────────────────────────────────────────
export const TOP_NAV: TopNavItem[] = [
  {
    id: "library",
    label: "Indicator Library",
    description: "Searchable KPI catalog",
    marker: "01",
  },
  {
    id: "energy",
    label: "Sectors",
    description: "Energy is the first deep sector",
    marker: "02",
  },
  {
    id: "entities",
    label: "Companies & Assets",
    description: "CVM registry and sector links",
    marker: "03",
  },
  {
    id: "health",
    label: "Data Health & Sources",
    description: "Coverage, snapshots, refresh logs",
    marker: "04",
  },
  {
    id: "exports",
    label: "Exports & Verification",
    description: "Download paths and audit checks",
    marker: "05",
  },
];

export const ENERGY_SUB_NAV: Array<{ id: EnergySub; label: string }> = [
  { id: "distribution", label: "Distribution" },
  { id: "generation", label: "Generation" },
  { id: "fuel", label: "Fuel" },
  { id: "sin", label: "Power System" },
  { id: "matrix", label: "Matrix & Trends" },
];

const HEALTH_SCOPE_ITEMS = [
  {
    label: "ANEEL Distribution",
    status: "Covered here",
    description: "Row counts, ingest snapshots, reconciliation logs and refresh status.",
  },
  {
    label: "CCEE Generation",
    status: "Specialist view",
    description: "Source status and manual imports are shown inside Generation.",
  },
  {
    label: "ONS / CCEE SIN",
    status: "Specialist view",
    description: "Source status remains inside Power System until centralized health expands.",
  },
  {
    label: "ANP Fuel",
    status: "Partial",
    description: "Fuel marts are readable today; centralized health is not available yet.",
  },
];

export const EXPORT_VERIFICATION_WORKFLOWS: ExportVerificationWorkflow[] = [
  {
    id: "distribution-excel",
    title: "Distribution Excel report",
    domain: "ANEEL Distribution",
    status: "available",
    exportScope: "Selected distributor or economic group.",
    whereToRun: "Energy -> Distribution detail panel.",
    verificationSignals: [
      "Distribution health counts",
      "Ingest snapshots",
      "Refresh logs, rejected rows and unresolved identities",
    ],
    currentLimit: "The export still runs inside the Distribution view after an entity is selected.",
    actionLabel: "Open Distribution",
    targetSection: "energy",
    targetSub: "distribution",
  },
  {
    id: "country-kpi-excel",
    title: "Country energy KPI Excel",
    domain: "Country Matrix & Trends",
    status: "available",
    exportScope: "Country-level energy KPI catalog and cached series.",
    whereToRun: "Indicator Library or Energy -> Matrix & Trends detail panel.",
    verificationSignals: [
      "Source label and primary source",
      "Coverage range",
      "Last refresh, data quality and audit notes",
    ],
    currentLimit: "SIN indicators do not use this Excel export path.",
    actionLabel: "Open Indicator Library",
    targetSection: "library",
  },
  {
    id: "generation-source-review",
    title: "Generation asset source review",
    domain: "CCEE Generation",
    status: "source-review",
    exportScope: "Plant-parcel catalog and selected asset detail are reviewable in-app.",
    whereToRun: "Energy -> Generation.",
    verificationSignals: [
      "Source status",
      "Manual import metadata",
      "Plant detail and owner mapping",
    ],
    currentLimit: "No centralized generation export is exposed in Indicators yet.",
    actionLabel: "Open Generation",
    targetSection: "energy",
    targetSub: "generation",
  },
  {
    id: "sin-source-review",
    title: "SIN subsystem source review",
    domain: "ONS / CCEE Power System",
    status: "source-review",
    exportScope: "Subsystem dashboard, cached observations and source status.",
    whereToRun: "Energy -> Power System.",
    verificationSignals: [
      "Source status cards",
      "Local records count",
      "Snapshot timestamp and refresh error text",
    ],
    currentLimit: "No Excel export is currently shown for SIN indicators.",
    actionLabel: "Open Power System",
    targetSection: "energy",
    targetSub: "sin",
  },
  {
    id: "fuel-detail-review",
    title: "Fuel mart detail review",
    domain: "ANP Fuel",
    status: "source-review",
    exportScope: "Product/year summaries, state/month trends and bounded detail rows.",
    whereToRun: "Energy -> Fuel.",
    verificationSignals: [
      "Source dataset id",
      "Product, state, year and unit filters",
      "Source row counts",
    ],
    currentLimit: "No centralized fuel export is exposed in Indicators yet.",
    actionLabel: "Open Fuel",
    targetSection: "energy",
    targetSub: "fuel",
  },
  {
    id: "mapping-review-notes",
    title: "Mapping review notes",
    domain: "Companies & Assets",
    status: "in-workflow",
    exportScope: "Latest asset-to-company manual mapping note is visible in Mapping Review.",
    whereToRun: "Companies & Assets -> Mapping Review.",
    verificationSignals: [
      "Manual override status",
      "Custom owner or CVM company target",
      "Review note stored on the mapping row",
    ],
    currentLimit: "There is no separate mapping history export table yet.",
    actionLabel: "Open Companies & Assets",
    targetSection: "entities",
  },
];

// ── Main Page ─────────────────────────────────────────────────────────────────
export function CountryKpisPage() {
  const [bridgeReady, setBridgeReady] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const [, startTransition] = useTransition();

  const section = parseSection(searchParams.get("section"));
  const energySub = parseEnergySub(searchParams.get("sub"));
  const energyOpen = section === "energy";

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const setSection = (next: TopSection) => {
    startTransition(() => {
      const params = new URLSearchParams(searchParams);
      if (next === "library") {
        params.delete("section");
      } else {
        params.set("section", next);
      }
      params.delete("sub");
      setSearchParams(params);
    });
  };

  const setEnergySub = (next: EnergySub) => {
    startTransition(() => {
      const params = new URLSearchParams(searchParams);
      params.set("section", "energy");
      if (next === "distribution") params.delete("sub");
      else params.set("sub", next);
      setSearchParams(params);
    });
  };

  return (
    <div className="flex min-h-0 gap-0 rounded-lg border border-zinc-800 bg-zinc-900/60 shadow-lg overflow-hidden">
      {/* ── Sidebar ─────────────────────────────────────────────────────── */}
      <nav
        aria-label="Indicators navigation"
        className="w-60 shrink-0 border-r border-zinc-800 bg-zinc-950/70 flex flex-col py-3 gap-0.5"
      >
        <div className="px-3 pb-3">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
            Indicators
          </div>
          <div className="mt-1 text-[10px] leading-snug text-zinc-600">
            Sector / company / asset / indicator
          </div>
        </div>

        {TOP_NAV.map((item) => {
          const isActive = section === item.id;
          return (
            <div key={item.id}>
              <button
                id={`indicators-nav-${item.id}`}
                onClick={() => setSection(item.id)}
                aria-current={isActive ? "page" : undefined}
                className={`w-full flex items-start gap-2 px-3 py-2 text-xs font-medium rounded-none transition-colors text-left ${
                  isActive
                    ? "bg-amber-500/10 text-amber-400 border-l-2 border-amber-500"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50 border-l-2 border-transparent"
                }`}
              >
                <span className="mt-0.5 w-5 shrink-0 font-mono text-[10px] text-zinc-600">
                  {item.marker}
                </span>
                <span className="min-w-0">
                  <span className="block truncate">{item.label}</span>
                  <span
                    className={`block truncate text-[10px] font-normal ${
                      isActive ? "text-amber-200/70" : "text-zinc-600"
                    }`}
                  >
                    {item.description}
                  </span>
                </span>
              </button>

              {/* Energy sub-nav — collapsible */}
              {item.id === "energy" && energyOpen && (
                <div className="ml-5 mt-0.5 mb-1 flex flex-col gap-0.5 border-l border-zinc-800 pl-2">
                  <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">
                    Energy
                  </div>
                  {ENERGY_SUB_NAV.map((sub) => {
                    const subActive = energySub === sub.id;
                    return (
                      <button
                        key={sub.id}
                        id={`indicators-energy-${sub.id}`}
                        onClick={() => setEnergySub(sub.id)}
                        aria-current={subActive ? "page" : undefined}
                        className={`w-full text-left px-2 py-1 text-[11px] rounded transition-colors ${
                          subActive
                            ? "text-amber-400 bg-amber-500/10 font-semibold"
                            : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40"
                        }`}
                      >
                        {sub.label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        <div className="flex-1" />
        <div className="px-3 pt-2 border-t border-zinc-800">
          <span className="text-[9px] text-zinc-600 leading-none">
            Local-first · Offline reads
          </span>
        </div>
      </nav>

      {/* ── Main content ────────────────────────────────────────────────── */}
      <div className="flex-1 min-w-0 p-5 overflow-auto">
        <Suspense fallback={<StateBanner variant="loading" title="Loading view…" />}>
          {section === "entities" && (
            <SectorCompanyPanel bridgeReady={bridgeReady} />
          )}

          {section === "energy" && energySub === "distribution" && (
            <DistributorExplorer bridgeReady={bridgeReady} />
          )}

          {section === "energy" && energySub === "generation" && (
            <PlantParcelExplorer bridgeReady={bridgeReady} />
          )}

          {section === "energy" && energySub === "fuel" && (
            <FuelDistributionExplorer bridgeReady={bridgeReady} />
          )}

          {section === "energy" && energySub === "sin" && (
            <SINPanelWrapper bridgeReady={bridgeReady} />
          )}

          {section === "energy" && energySub === "matrix" && (
            <IndicatorExplorer bridgeReady={bridgeReady} mode="catalog" />
          )}

          {section === "library" && (
            <IndicatorExplorer
              bridgeReady={bridgeReady}
              mode="library"
              onOpenSection={setSection}
              onOpenEnergySub={setEnergySub}
            />
          )}

          {section === "health" && (
            <DistributionHealthPanel bridgeReady={bridgeReady} />
          )}

          {section === "exports" && (
            <ExportVerificationPanel
              onOpenSection={setSection}
              onOpenEnergySub={setEnergySub}
            />
          )}
        </Suspense>
      </div>
    </div>
  );
}

// ── SIN panel wrapper (lazy-loaded on demand) ─────────────────────────────────
const SINKpiPanel = lazy(() =>
  import("@/components/indicators/SINKpiPanel").then((m) => ({
    default: m.SINKpiPanel,
  })),
);

function SINPanelWrapper({ bridgeReady }: { bridgeReady: boolean }) {
  const [viewMode, setViewMode] = useState<"matrix" | "trend">("matrix");
  return (
    <Suspense fallback={<StateBanner variant="loading" title="Loading power system data…" />}>
      <SINKpiPanel bridgeReady={bridgeReady} viewMode={viewMode} onViewModeChange={setViewMode} />
    </Suspense>
  );
}

// ── Exports & Verification ──────────────────────────────────────────────────
function ExportVerificationPanel({
  onOpenSection,
  onOpenEnergySub,
}: {
  onOpenSection: (section: TopSection) => void;
  onOpenEnergySub: (sub: EnergySub) => void;
}) {
  const openWorkflow = (workflow: ExportVerificationWorkflow) => {
    if (workflow.targetSub) {
      onOpenEnergySub(workflow.targetSub);
      return;
    }
    onOpenSection(workflow.targetSection);
  };

  const availableExports = EXPORT_VERIFICATION_WORKFLOWS.filter(
    (workflow) => workflow.status === "available",
  ).length;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100 mb-1">
            Exports & Verification
          </h2>
          <p className="max-w-3xl text-sm text-zinc-400">
            Review what can be downloaded today, where each export is generated,
            and which source signals should be checked before using the data in a model.
          </p>
        </div>
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 px-3 py-2 text-[11px] text-zinc-500">
          <div className="font-mono text-zinc-400">
            {availableExports} direct export paths
          </div>
          <div>No unified export manifest is generated in this phase.</div>
        </div>
      </div>

      <section className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-4">
          <h3 className="text-sm font-semibold text-zinc-200">
            Pre-export verification checklist
          </h3>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {[
              "Confirm source and primary dataset.",
              "Check latest refresh or snapshot timestamp.",
              "Review missing, rejected or unresolved rows where available.",
              "Confirm units, frequency, geography and selected filters.",
              "Verify company-to-asset mappings before portfolio exports.",
              "Record limitations when the export is still handled inside a specialist view.",
            ].map((item, index) => (
              <div
                key={item}
                className="flex gap-2 rounded border border-zinc-800 bg-zinc-950/70 px-3 py-2"
              >
                <span className="mt-0.5 font-mono text-[10px] text-zinc-600">
                  {(index + 1).toString().padStart(2, "0")}
                </span>
                <span className="text-xs leading-snug text-zinc-400">{item}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
          <h3 className="text-sm font-semibold text-amber-300">
            Current boundary
          </h3>
          <p className="mt-2 text-xs leading-relaxed text-zinc-400">
            Phase 4 does not create new datasets or a synthetic export manifest.
            It organizes existing export actions and points to the source evidence
            already available in the app.
          </p>
          <button
            type="button"
            onClick={() => onOpenSection("health")}
            className="mt-3 rounded border border-amber-500/30 px-2 py-1 text-[11px] font-semibold text-amber-300 hover:border-amber-400"
          >
            Open source health
          </button>
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-zinc-300">
            Export and review paths
          </h3>
          <span className="text-[11px] text-zinc-600">
            Direct downloads stay inside the source panels that already own them.
          </span>
        </div>
        <div className="grid gap-3 xl:grid-cols-2">
          {EXPORT_VERIFICATION_WORKFLOWS.map((workflow) => (
            <div
              key={workflow.id}
              className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4"
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-zinc-200">
                    {workflow.title}
                  </div>
                  <div className="mt-0.5 font-mono text-[10.5px] text-zinc-600">
                    {workflow.domain}
                  </div>
                </div>
                <ExportWorkflowStatusBadge status={workflow.status} />
              </div>

              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                <ExportMeta label="Export scope" value={workflow.exportScope} />
                <ExportMeta label="Where to run" value={workflow.whereToRun} />
              </div>

              <div className="mt-3">
                <div className="text-[10px] uppercase tracking-wider text-zinc-600">
                  Verification signals
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {workflow.verificationSignals.map((signal) => (
                    <span
                      key={signal}
                      className="rounded border border-zinc-800 bg-zinc-900/50 px-1.5 py-0.5 text-[10px] text-zinc-400"
                    >
                      {signal}
                    </span>
                  ))}
                </div>
              </div>

              <div className="mt-3 rounded border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-[11px] leading-snug text-zinc-500">
                {workflow.currentLimit}
              </div>

              <button
                type="button"
                onClick={() => openWorkflow(workflow)}
                className="mt-3 rounded border border-zinc-700 px-2 py-1 text-[11px] font-semibold text-zinc-300 hover:border-amber-500/60 hover:text-amber-300"
              >
                {workflow.actionLabel}
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function ExportMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950/70 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-zinc-600">
        {label}
      </div>
      <div className="mt-1 text-xs leading-snug text-zinc-300">{value}</div>
    </div>
  );
}

function ExportWorkflowStatusBadge({ status }: { status: ExportWorkflowStatus }) {
  const label =
    status === "available"
      ? "Export available"
      : status === "source-review"
        ? "Review only"
        : "In workflow";
  const classes =
    status === "available"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
      : status === "source-review"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
        : "border-sky-500/30 bg-sky-500/10 text-sky-400";

  return (
    <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold ${classes}`}>
      {label}
    </span>
  );
}

// ── Distribution Health Panel ─────────────────────────────────────────────────
function DistributionHealthPanel({ bridgeReady }: { bridgeReady: boolean }) {
  const healthQuery = useQuery({
    queryKey: ["distribution-health"],
    queryFn: () => fetchDistributionHealth(),
    enabled: bridgeReady,
    staleTime: 60_000,
  });

  if (!bridgeReady || healthQuery.isLoading) {
    return (
      <div className="space-y-6">
        <DataHealthIntro />
        <StateBanner variant="loading" title="Loading data health…" />
      </div>
    );
  }
  if (healthQuery.isError) {
    return (
      <div className="space-y-6">
        <DataHealthIntro />
        <StateBanner
          variant="error"
          title="Could not load health data"
          message={
            healthQuery.error instanceof Error
              ? healthQuery.error.message
              : String(healthQuery.error)
          }
          onRetry={() => void healthQuery.refetch()}
        />
      </div>
    );
  }

  const result = healthQuery.data;
  if (!result || result.mode === "browser") {
    return (
      <div className="space-y-6">
        <DataHealthIntro />
        <StateBanner
          variant="browser-only"
          message="Centralized health rows require the desktop bridge and local databases."
        />
      </div>
    );
  }

  const health = result.health as DistributionHealthResponse;
  const counts = health.counts;

  const countCards: Array<{ label: string; key: keyof typeof counts; desc: string }> = [
    { label: "Market Facts", key: "market", desc: "Billed energy & revenue rows" },
    { label: "Energy Balance", key: "balance", desc: "Injected / losses rows" },
    { label: "Quality (DEC/FEC)", key: "continuity", desc: "Continuity indicator rows" },
    { label: "Tariff Facts", key: "tariffs", desc: "TE/TUSD tariff rows" },
    { label: "Delinquency", key: "delinquency", desc: "Indqual delinquency rows" },
    { label: "MMGD Projects", key: "mmgd", desc: "Microgeneration project rows" },
  ];

  return (
    <div className="space-y-6">
      <DataHealthIntro />

      {/* Count cards */}
      <div>
        <h3 className="mb-2 text-sm font-semibold text-zinc-300">
          ANEEL Distribution Coverage
        </h3>
        <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
          {countCards.map((card) => {
            const n = counts[card.key];
            const hasData = n > 0;
            return (
              <div
                key={card.key}
                className={`rounded-lg border p-4 space-y-2 ${
                  hasData
                    ? "border-zinc-700 bg-zinc-900/60"
                    : "border-zinc-800 bg-zinc-950/50"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-zinc-300">{card.label}</span>
                  <span
                    className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                      hasData ? "bg-emerald-500" : "bg-zinc-600"
                    }`}
                    title={hasData ? "Data present" : "No data"}
                  />
                </div>
                <div className="font-mono text-xl font-bold text-zinc-100 tabular-nums">
                  {n.toLocaleString()}
                </div>
                <div className="text-[11px] text-zinc-500">{card.desc}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Snapshots audit trail */}
      <div>
        <h3 className="text-sm font-semibold text-zinc-300 mb-2">
          Ingest Snapshots ({health.snapshots.length})
        </h3>
        {health.snapshots.length === 0 ? (
          <div className="text-sm text-zinc-500 italic px-1">
            No snapshots recorded — data has not been ingested yet.
            Use the Refresh button in the Distribution view to import ANEEL datasets.
          </div>
        ) : (
          <div className="rounded-md border border-zinc-800 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800 bg-zinc-900/80">
                  {["Source", "Fetched At", "Rows", "Status", "SHA-256 (prefix)"].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-left px-3 py-2 font-semibold text-zinc-400 uppercase tracking-wider"
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {health.snapshots.map((snap, i) => {
                  const isOk = snap.status === "ok";
                  return (
                    <tr
                      key={snap.snapshot_id}
                      className={`border-b border-zinc-800/50 ${
                        i % 2 === 0 ? "bg-zinc-950/30" : "bg-zinc-900/20"
                      }`}
                    >
                      <td className="px-3 py-1.5 font-medium text-zinc-300">
                        {snap.source}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-zinc-400">
                        {snap.fetched_at?.slice(0, 16).replace("T", " ") ?? "—"}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-zinc-300 text-right tabular-nums">
                        {snap.row_count != null
                          ? snap.row_count.toLocaleString()
                          : "—"}
                      </td>
                      <td className="px-3 py-1.5">
                        <span
                          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                            isOk
                              ? "bg-emerald-500/10 text-emerald-400"
                              : "bg-red-500/10 text-red-400"
                          }`}
                        >
                          {snap.status}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 font-mono text-zinc-600 text-[10px]">
                        {snap.sha256 ? snap.sha256.slice(0, 16) + "…" : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Reconciliation Logs */}
      <div>
        <h3 className="text-sm font-semibold text-zinc-300 mb-2">
          Reconciliation & Refresh Logs ({health.refresh_logs?.length ?? 0})
        </h3>
        {!health.refresh_logs || health.refresh_logs.length === 0 ? (
          <div className="text-sm text-zinc-500 italic px-1">
            No refresh execution logs recorded — data has not been ingested yet.
          </div>
        ) : (
          <div className="rounded-md border border-zinc-800 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-zinc-800 bg-zinc-900/80">
                    {["Source / Dataset", "Refreshed At", "Status", "Source Rows", "Published", "Conflicts", "Unresolved", "Rejected", "Duration", "RSS / CPU"].map(
                      (h, idx) => (
                        <th
                          key={h}
                          className={`px-3 py-2 font-semibold text-zinc-400 uppercase tracking-wider ${
                            idx >= 3 ? "text-right" : "text-left"
                          }`}
                        >
                          {h}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody>
                  {health.refresh_logs.map((log, i) => {
                    const isSuccess = log.status === "success" || log.status === "ok" || log.status === "done";
                    const hasConflicts = (log.conflict_rows ?? 0) > 0;
                    const hasUnresolved = (log.unresolved_identity_rows ?? 0) > 0;
                    const hasRejected = (log.rejected_rows ?? 0) > 0;
                    
                    const durationMs = (log.elapsed_download_ms ?? 0) + (log.elapsed_parse_ms ?? 0) + (log.elapsed_publish_ms ?? 0);
                    const durationSec = durationMs > 0 ? `${(durationMs / 1000).toFixed(1)}s` : "—";
                    const lockWaitSec = log.elapsed_lock_wait_ms != null ? `${(log.elapsed_lock_wait_ms / 1000).toFixed(2)}s lock` : null;

                    return (
                      <tr
                        key={log.refresh_id}
                        className={`border-b border-zinc-800/50 hover:bg-zinc-900/10 ${
                          i % 2 === 0 ? "bg-zinc-950/30" : "bg-zinc-900/20"
                        }`}
                      >
                        <td className="px-3 py-2 font-medium text-zinc-300">
                          <div>{log.dataset_name || log.source_id}</div>
                          {log.warning_message && (
                            <div className="text-[10px] text-amber-400/85 truncate max-w-[200px] mt-0.5" title={log.warning_message}>
                              Warning: {log.warning_message}
                            </div>
                          )}
                          {log.error_message && (
                            <div className="text-[10px] text-red-400/85 truncate max-w-[200px] mt-0.5" title={log.error_message}>
                              Error: {log.error_message}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 font-mono text-zinc-400">
                          {log.started_at?.slice(0, 16).replace("T", " ") ?? "—"}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              isSuccess
                                ? "bg-emerald-500/10 text-emerald-400"
                                : log.status === "running"
                                ? "bg-amber-500/10 text-amber-400"
                                : "bg-red-500/10 text-red-400"
                            }`}
                          >
                            {log.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 font-mono text-zinc-300 text-right tabular-nums">
                          {log.source_rows != null ? log.source_rows.toLocaleString() : "—"}
                        </td>
                        <td className="px-3 py-2 font-mono text-zinc-300 text-right tabular-nums">
                          {log.final_published_rows != null ? log.final_published_rows.toLocaleString() : "—"}
                        </td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${hasConflicts ? "text-amber-400 font-semibold" : "text-zinc-500"}`}>
                          {log.conflict_rows != null ? log.conflict_rows.toLocaleString() : "0"}
                        </td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${hasUnresolved ? "text-amber-400 font-semibold" : "text-zinc-500"}`}>
                          {log.unresolved_identity_rows != null ? log.unresolved_identity_rows.toLocaleString() : "0"}
                        </td>
                        <td className={`px-3 py-2 font-mono text-right tabular-nums ${hasRejected ? "text-red-400 font-semibold" : "text-zinc-500"}`}>
                          {log.rejected_rows != null ? log.rejected_rows.toLocaleString() : "0"}
                        </td>
                        <td className="px-3 py-2 font-mono text-zinc-400 text-right tabular-nums">
                          {durationSec}
                          {lockWaitSec && <div className="text-[10px] text-zinc-500">{lockWaitSec}</div>}
                        </td>
                        <td className="px-3 py-2 font-mono text-zinc-400 text-right tabular-nums">
                          {log.peak_rss_mb != null ? `${log.peak_rss_mb.toFixed(0)} MB` : "—"}
                          {log.cpu_time_ms != null ? ` / ${(log.cpu_time_ms / 1000).toFixed(1)}s` : ""}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DataHealthIntro() {
  return (
    <>
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">
          Data Health & Sources
        </h2>
        <p className="max-w-3xl text-sm text-zinc-400">
          Centralized local health is available for the ANEEL distribution analytics
          domain. Other Energy sources keep their source status inside their specialist
          views until the module has centralized source health for them.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {HEALTH_SCOPE_ITEMS.map((item) => (
          <div
            key={item.label}
            className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="text-sm font-semibold text-zinc-200">{item.label}</div>
              <span className="rounded border border-zinc-800 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-500">
                {item.status}
              </span>
            </div>
            <div className="mt-2 text-xs leading-snug text-zinc-500">
              {item.description}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

// ── URL parsing helpers ───────────────────────────────────────────────────────
export function parseSection(raw: string | null): TopSection {
  if (
    raw === "energy" ||
    raw === "entities" ||
    raw === "library" ||
    raw === "health" ||
    raw === "exports"
  )
    return raw;
  if (raw === "overview") return "library";
  if (raw === "discover") return "entities";
  if (raw === "favorites") return "library";
  return "library";
}

export function parseEnergySub(raw: string | null): EnergySub {
  if (
    raw === "distribution" ||
    raw === "generation" ||
    raw === "fuel" ||
    raw === "sin" ||
    raw === "matrix"
  )
    return raw;
  return "distribution";
}
