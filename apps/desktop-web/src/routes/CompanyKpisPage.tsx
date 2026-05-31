import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { MetricTape, type MetricTapeItem } from "@/components/data/MetricTape";
import { EntityHeader } from "@/components/EntityHeader";
import { StateBanner } from "@/components/feedback/StateBanner";
import { IndicatorWorkspace } from "@/components/indicators/IndicatorWorkspace";
import { Panel } from "@/components/surface/Panel";
import { Button } from "@/components/ui/Button";
import {
  fetchCompanyKpis,
  fetchCompanyYears,
  type CompanyKpisResult,
  type CompanyYearsResultUI,
} from "@/lib/api/companyDetail";
import { whenBridgeReady } from "@/lib/bridge/adapter";
import type { KPIBundle, TabularRow } from "@/lib/bridge/types";

const DEFAULT_RECENT_YEARS = 5;
const SUMMARY_KPI_IDS = ["MG_EBITDA", "MG_LIQ", "ROE", "DIV_EBITDA"] as const;

export function CompanyKpisPage() {
  const params = useParams<{ cdCvm: string }>();
  const cdCvm = Number.parseInt(params.cdCvm ?? "", 10);
  const [bridgeReady, setBridgeReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    whenBridgeReady().then(() => {
      if (!cancelled) setBridgeReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!Number.isFinite(cdCvm) || cdCvm <= 0) {
    return <StateBanner variant="error" message={`CVM inválido: "${params.cdCvm}"`} />;
  }

  return (
    <section className="space-y-4">
      <EntityHeader cdCvm={cdCvm} activeTab="kpis" />
      <KpiBody cdCvm={cdCvm} bridgeReady={bridgeReady} />
    </section>
  );
}

function KpiBody({ cdCvm, bridgeReady }: { cdCvm: number; bridgeReady: boolean }) {
  const yearsQuery = useQuery<CompanyYearsResultUI>({
    queryKey: ["company-years", cdCvm],
    queryFn: () => fetchCompanyYears(cdCvm),
    enabled: bridgeReady,
  });

  const availableYears = useMemo(
    () => (yearsQuery.data?.mode === "desktop" ? [...yearsQuery.data.years] : []),
    [yearsQuery.data],
  );
  const sortedYears = useMemo(
    () => [...availableYears].sort((a, b) => a - b),
    [availableYears],
  );

  const [selectedYears, setSelectedYears] = useState<number[]>([]);
  useEffect(() => {
    if (selectedYears.length === 0 && sortedYears.length > 0) {
      const desc = [...sortedYears].sort((a, b) => b - a);
      setSelectedYears(desc.slice(0, DEFAULT_RECENT_YEARS).sort((a, b) => a - b));
    }
  }, [sortedYears, selectedYears.length]);

  const kpiQuery = useQuery<CompanyKpisResult>({
    queryKey: ["company-kpis", cdCvm, selectedYears.join(",")],
    queryFn: () => fetchCompanyKpis(cdCvm, selectedYears),
    enabled: bridgeReady && selectedYears.length > 0,
  });

  const bundle = kpiQuery.data?.mode === "desktop" ? kpiQuery.data.bundle : null;
  const metricItems = useMemo(
    () => buildMetricTapeItems(bundle, selectedYears),
    [bundle, selectedYears],
  );

  if (!bridgeReady || yearsQuery.isLoading) {
    return <StateBanner variant="loading" title="Loading available years…" />;
  }
  if (yearsQuery.isError) {
    return (
      <StateBanner
        variant="error"
        onRetry={() => yearsQuery.refetch()}
        message={
          yearsQuery.error instanceof Error
            ? yearsQuery.error.message
            : String(yearsQuery.error)
        }
      />
    );
  }
  if (yearsQuery.data?.mode === "browser") {
    return <StateBanner variant="browser-only" message={yearsQuery.data.reason} />;
  }
  if (sortedYears.length === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No annual data"
        message="No annual rows in the local database. Run Database Updates to populate and try again."
      />
    );
  }

  return (
    <div className="space-y-4">
      <YearSelector
        available={sortedYears}
        selected={selectedYears}
        onChange={setSelectedYears}
      />

      <MetricTape items={metricItems} ariaLabel="Indicator summary" />

      {kpiQuery.isLoading ? (
        <StateBanner variant="loading" title="Loading indicators…" />
      ) : kpiQuery.isError ? (
        <StateBanner
          variant="error"
          onRetry={() => kpiQuery.refetch()}
          message={
            kpiQuery.error instanceof Error ? kpiQuery.error.message : String(kpiQuery.error)
          }
        />
      ) : kpiQuery.data?.mode === "browser" ? (
        <StateBanner variant="browser-only" message={kpiQuery.data.reason} />
      ) : bundle ? (
        <IndicatorWorkspace bundle={bundle} selectedYears={selectedYears} />
      ) : (
        <StateBanner
          variant="empty"
          title="No indicators"
          message="Bridge returned an empty payload for the selected years."
        />
      )}
    </div>
  );
}

function YearSelector({
  available,
  selected,
  onChange,
}: {
  available: number[];
  selected: number[];
  onChange: (years: number[]) => void;
}) {
  const selectedSet = new Set(selected);
  function toggle(year: number) {
    if (selectedSet.has(year)) {
      onChange(selected.filter((y) => y !== year));
    } else {
      onChange([...selected, year].sort((a, b) => a - b));
    }
  }
  function selectAll() {
    onChange([...available].sort((a, b) => a - b));
  }
  function selectRecent() {
    const desc = [...available].sort((a, b) => b - a);
    onChange(desc.slice(0, DEFAULT_RECENT_YEARS).sort((a, b) => a - b));
  }
  return (
    <Panel
      dense
      title="Years"
      subtitle="Pick which periods feed the indicator engine."
      actions={
        <div className="flex gap-2">
          <Button size="xs" onClick={selectRecent}>
            Last {DEFAULT_RECENT_YEARS}
          </Button>
          <Button size="xs" onClick={selectAll}>
            All
          </Button>
        </div>
      }
    >
      <div className="flex flex-wrap gap-2">
        {available.map((year) => {
          const active = selectedSet.has(year);
          return (
            <button
              key={year}
              type="button"
              onClick={() => toggle(year)}
              className="font-mono focus-visible:outline focus-visible:outline-1"
              style={{
                background: active ? "var(--color-surface-3)" : "transparent",
                border: `1px solid ${
                  active ? "var(--color-action-primary)" : "var(--color-border-default)"
                }`,
                borderRadius: "var(--radius-sm)",
                color: active ? "var(--color-action-primary)" : "var(--color-text-secondary)",
                fontSize: "var(--text-xs)",
                height: 24,
                outlineColor: "var(--color-border-focus)",
                padding: "2px 9px",
              }}
            >
              {year}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}

function buildMetricTapeItems(
  bundle: KPIBundle | null,
  selectedYears: number[],
): MetricTapeItem[] {
  const latestYear = selectedYears.length ? Math.max(...selectedYears) : null;
  const rowsById = new Map<string, TabularRow>();
  for (const row of bundle?.annual.rows ?? []) {
    const id = String(row.KPI_ID ?? "").trim();
    if (id) rowsById.set(id, row);
  }

  return SUMMARY_KPI_IDS.map((id) => {
    const row = rowsById.get(id);
    return {
      id,
      label: row ? String(row.KPI_NOME ?? humanizeKpiId(id)) : humanizeKpiId(id),
      value: latestYear && row ? row[String(latestYear)] : null,
      formatType: row?.FORMAT_TYPE,
      sublabel: latestYear ? `latest ${latestYear}` : "no year",
      delta: row?.DELTA_YOY_PCT ?? null,
      sparkline: selectedYears.map((year) => numericOrNull(row?.[String(year)])),
    };
  });
}

function numericOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function humanizeKpiId(id: string): string {
  return id
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
