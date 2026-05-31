import { useEffect, useMemo, type ReactNode } from "react";

import { StateBanner } from "@/components/feedback/StateBanner";
import { Panel } from "@/components/surface/Panel";
import type { KPIBundle } from "@/lib/bridge/types";
import { buildIndicatorDefs, defaultSelectedIds } from "@/lib/indicators/catalog";
import { resolveSeries, selectPeriods } from "@/lib/indicators/series";
import type {
  AxisSide,
  ChartType,
  IndicatorSelection,
} from "@/lib/indicators/types";
import { useIndicatorConfig } from "@/lib/indicators/useIndicatorConfig";

import { IndicatorChart } from "./IndicatorChart";
import { IndicatorControls } from "./IndicatorControls";
import { IndicatorLegend } from "./IndicatorLegend";
import { IndicatorTable } from "./IndicatorTable";

const MAX_SELECTED = 6;

interface IndicatorWorkspaceProps {
  bundle: KPIBundle;
  selectedYears: number[];
}

/**
 * Container for the configurable Indicators tab. Owns the chart configuration,
 * derives the available indicators and chart-ready series from the KPI bundle,
 * and keeps the chart and the detail table driven by one shared selection +
 * frequency. All financial computation already happened in the Python KPI
 * engine; this layer only selects, orders and shapes data for rendering.
 */
export function IndicatorWorkspace({ bundle, selectedYears }: IndicatorWorkspaceProps) {
  const { config, setFrequency, setSelected, setChart } = useIndicatorConfig();
  const { frequency, chart } = config;

  const activeTable = frequency === "annual" ? bundle.annual : bundle.quarterly;

  // Defaults are seeded from the annual table (most complete catalog coverage).
  const annualDefs = useMemo(() => buildIndicatorDefs(bundle.annual), [bundle.annual]);
  const defs = useMemo(() => buildIndicatorDefs(activeTable), [activeTable]);
  const defsById = useMemo(() => new Map(defs.map((d) => [d.id, d])), [defs]);

  const quarterlyPeriods = useMemo(
    () => selectPeriods(bundle.quarterly, "quarterly", selectedYears),
    [bundle.quarterly, selectedYears],
  );
  const quarterlyAvailable = quarterlyPeriods.length > 0;

  const periods = useMemo(
    () => selectPeriods(activeTable, frequency, selectedYears),
    [activeTable, frequency, selectedYears],
  );

  // Seed a sensible default selection on first use.
  useEffect(() => {
    if (config.selected.length === 0 && annualDefs.length > 0) {
      const seeded: IndicatorSelection[] = defaultSelectedIds(annualDefs).map((id) => ({
        id,
        axis: "auto",
        type: "auto",
      }));
      if (seeded.length > 0) setSelected(seeded);
    }
  }, [annualDefs, config.selected.length, setSelected]);

  // If the user picked quarterly but there is no quarterly data, fall back.
  useEffect(() => {
    if (frequency === "quarterly" && !quarterlyAvailable) setFrequency("annual");
  }, [frequency, quarterlyAvailable, setFrequency]);

  const selectionById = useMemo(
    () => new Map(config.selected.map((s) => [s.id, s] as const)),
    [config.selected],
  );

  // Only indicators that are actually computable for the active frequency get plotted.
  const plottable = useMemo(
    () => config.selected.filter((s) => defsById.get(s.id)?.available),
    [config.selected, defsById],
  );
  const plottableIds = useMemo(() => plottable.map((s) => s.id), [plottable]);

  const series = useMemo(
    () => resolveSeries(activeTable, periods, plottable, chart.type, chart.indexMode),
    [activeTable, periods, plottable, chart.type, chart.indexMode],
  );

  const showAxisControls = useMemo(
    () => new Set(series.map((s) => s.unit)).size > 1,
    [series],
  );

  const selectedExistingCount = config.selected.filter((s) => defsById.has(s.id)).length;
  const droppedCount = selectedExistingCount - plottable.length;

  function toggleIndicator(id: string) {
    const exists = config.selected.some((s) => s.id === id);
    if (exists) {
      setSelected(config.selected.filter((s) => s.id !== id));
    } else if (config.selected.length < MAX_SELECTED) {
      setSelected([...config.selected, { id, axis: "auto", type: "auto" }]);
    }
  }

  function setAxis(id: string, axis: "auto" | AxisSide) {
    setSelected(config.selected.map((s) => (s.id === id ? { ...s, axis } : s)));
  }

  function setType(id: string, type: "auto" | ChartType) {
    setSelected(config.selected.map((s) => (s.id === id ? { ...s, type } : s)));
  }

  const noIndicatorsAtAll = annualDefs.filter((d) => d.available).length === 0;

  const methodology =
    frequency === "annual"
      ? "Annual KPIs at fiscal-year close."
      : "Quarterly KPIs — flow metrics annualised on an LTM (trailing 4Q) basis; balance-sheet items at quarter-end.";

  return (
    <div className="space-y-4">
      <Panel
        title="Indicator chart"
        subtitle={methodology}
        actions={
          <span
            className="font-mono"
            style={{ color: "var(--color-text-tertiary)", fontSize: "var(--text-xs)" }}
          >
            {series.length}/{config.selected.length} plotted
          </span>
        }
      >
        <div className="space-y-3">
          <IndicatorControls
            frequency={frequency}
            quarterlyAvailable={quarterlyAvailable}
            onFrequencyChange={setFrequency}
            defs={defs}
            selectedIds={config.selected.map((s) => s.id)}
            onToggleIndicator={toggleIndicator}
            maxSelected={MAX_SELECTED}
            chart={chart}
            onChartChange={setChart}
          />

          <ChartArea
            noIndicatorsAtAll={noIndicatorsAtAll}
            frequency={frequency}
            quarterlyAvailable={quarterlyAvailable}
            periodsCount={periods.length}
            selectedCount={config.selected.length}
            plottedCount={series.length}
          >
            <IndicatorChart series={series} periods={periods} config={chart} />
          </ChartArea>

          {droppedCount > 0 ? (
            <p
              style={{
                color: "var(--color-state-warn)",
                fontSize: "var(--text-xs)",
                margin: 0,
              }}
            >
              {droppedCount} selected indicator{droppedCount > 1 ? "s are" : " is"} unavailable for{" "}
              {frequency} view and {droppedCount > 1 ? "were" : "was"} hidden.
            </p>
          ) : null}

          {chart.legend && series.length > 0 ? (
            <IndicatorLegend
              series={series}
              selectionById={selectionById}
              indexMode={chart.indexMode}
              showAxisControls={showAxisControls}
              onSetAxis={setAxis}
              onSetType={setType}
              onRemove={(id) => toggleIndicator(id)}
            />
          ) : null}
        </div>
      </Panel>

      <Panel
        title="Indicator detail"
        subtitle={`${series.length} indicator${series.length === 1 ? "" : "s"} · ${periods.length} period${periods.length === 1 ? "" : "s"}`}
      >
        {series.length > 0 && periods.length > 0 ? (
          <IndicatorTable table={activeTable} periods={periods} selectedIds={plottableIds} />
        ) : (
          <StateBanner
            variant="empty"
            title="Nothing to show"
            message="Select one or more available indicators to populate the table."
          />
        )}
      </Panel>
    </div>
  );
}

/** Chart-area state machine: distinct, explicit empty states before the chart. */
function ChartArea({
  noIndicatorsAtAll,
  frequency,
  quarterlyAvailable,
  periodsCount,
  selectedCount,
  plottedCount,
  children,
}: {
  noIndicatorsAtAll: boolean;
  frequency: "annual" | "quarterly";
  quarterlyAvailable: boolean;
  periodsCount: number;
  selectedCount: number;
  plottedCount: number;
  children: ReactNode;
}) {
  if (noIndicatorsAtAll) {
    return (
      <StateBanner
        variant="empty"
        title="No indicators available"
        message="The KPI engine returned no computable indicators for this company. Update this company's data and try again."
      />
    );
  }
  if (frequency === "quarterly" && (!quarterlyAvailable || periodsCount === 0)) {
    return (
      <StateBanner
        variant="empty"
        title="No quarterly data"
        message="This company has no quarterly (LTM) indicator series for the selected years. Switch to Annual or widen the year range."
      />
    );
  }
  if (selectedCount === 0) {
    return (
      <StateBanner
        variant="empty"
        title="No indicators selected"
        message="Use the Indicators picker to choose what to plot."
      />
    );
  }
  if (plottedCount === 0) {
    return (
      <StateBanner
        variant="empty"
        title="Selected indicators unavailable"
        message={`None of the selected indicators can be computed for the ${frequency} view. Pick different indicators or switch frequency.`}
      />
    );
  }
  return <>{children}</>;
}
