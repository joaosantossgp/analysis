import { useState, type ReactNode } from "react";

import { Checkbox } from "@/components/ui/Checkbox";
import type {
  ChartAesthetics,
  ChartType,
  Frequency,
  IndicatorDef,
} from "@/lib/indicators/types";

import { IndicatorPicker } from "./IndicatorPicker";
import { Segmented } from "./Segmented";

interface IndicatorControlsProps {
  frequency: Frequency;
  quarterlyAvailable: boolean;
  onFrequencyChange: (frequency: Frequency) => void;
  /** Hide the Annual/Quarterly toggle when frequency is not a meaningful axis
   *  (e.g. country energy or SIN subsystems, where it is permanently disabled). */
  showFrequency?: boolean;
  /** What the picker selects. "Indicators" for company KPIs, "Countries" /
   *  "Subsystems" for the macro views that reuse this control. */
  itemNoun?: string;

  defs: IndicatorDef[];
  selectedIds: string[];
  onToggleIndicator: (id: string) => void;
  maxSelected: number;

  chart: ChartAesthetics;
  onChartChange: (patch: Partial<ChartAesthetics>) => void;
}

const FREQUENCY_OPTIONS = (quarterlyAvailable: boolean) =>
  [
    { value: "annual" as const, label: "Annual" },
    {
      value: "quarterly" as const,
      label: "Quarterly",
      disabled: !quarterlyAvailable,
      title: quarterlyAvailable ? undefined : "No quarterly (LTM) data for this company",
    },
  ];

const CHART_TYPE_OPTIONS = [
  { value: "line" as const, label: "Line" },
  { value: "bar" as const, label: "Bar" },
  { value: "area" as const, label: "Area" },
];

export function IndicatorControls({
  frequency,
  quarterlyAvailable,
  onFrequencyChange,
  showFrequency = true,
  itemNoun = "Indicators",
  defs,
  selectedIds,
  onToggleIndicator,
  maxSelected,
  chart,
  onChartChange,
}: IndicatorControlsProps) {
  const [showOptions, setShowOptions] = useState(false);
  const smoothDisabled = chart.type === "bar";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {showFrequency ? (
          <Field label="Frequency">
            <Segmented
              ariaLabel="Frequency"
              value={frequency}
              options={FREQUENCY_OPTIONS(quarterlyAvailable)}
              onChange={(v) => onFrequencyChange(v as Frequency)}
            />
          </Field>
        ) : null}

        <Field label={itemNoun}>
          <IndicatorPicker
            label={itemNoun}
            defs={defs}
            selectedIds={selectedIds}
            onToggle={onToggleIndicator}
            maxSelected={maxSelected}
          />
        </Field>

        <Field label="Chart">
          <Segmented
            ariaLabel="Chart type"
            value={chart.type}
            options={CHART_TYPE_OPTIONS}
            onChange={(v) => onChartChange({ type: v as ChartType })}
          />
        </Field>

        <div style={{ marginLeft: "auto" }}>
          <button
            type="button"
            aria-expanded={showOptions}
            onClick={() => setShowOptions((o) => !o)}
            className="font-mono focus-visible:outline focus-visible:outline-1"
            style={{
              background: showOptions ? "var(--color-surface-3)" : "var(--color-surface-1)",
              border: "1px solid var(--color-border-default)",
              borderRadius: "var(--radius-md)",
              color: "var(--color-text-secondary)",
              cursor: "pointer",
              fontSize: "var(--text-xs)",
              height: 26,
              outlineColor: "var(--color-border-focus)",
              padding: "0 10px",
            }}
          >
            Options
            <span aria-hidden="true" style={{ marginLeft: 6, color: "var(--color-text-tertiary)" }}>
              {showOptions ? "▴" : "▾"}
            </span>
          </button>
        </div>
      </div>

      {showOptions ? (
        <div
          className="flex flex-wrap items-center gap-x-5 gap-y-2"
          style={{
            background: "var(--color-surface-1)",
            border: "1px solid var(--color-border-subtle)",
            borderRadius: "var(--radius-sm)",
            padding: "8px 12px",
          }}
        >
          <Checkbox
            label="Smooth lines"
            checked={chart.smooth}
            disabled={smoothDisabled}
            onChange={(e) => onChartChange({ smooth: e.currentTarget.checked })}
          />
          <Checkbox
            label="Markers"
            checked={chart.markers}
            onChange={(e) => onChartChange({ markers: e.currentTarget.checked })}
          />
          <Checkbox
            label="Legend"
            checked={chart.legend}
            onChange={(e) => onChartChange({ legend: e.currentTarget.checked })}
          />
          <Checkbox
            label="Grid"
            checked={chart.grid}
            onChange={(e) => onChartChange({ grid: e.currentTarget.checked })}
          />
          <Checkbox
            label="Data labels"
            checked={chart.dataLabels}
            onChange={(e) => onChartChange({ dataLabels: e.currentTarget.checked })}
          />
          <Checkbox
            label="Index (base 100)"
            checked={chart.indexMode}
            onChange={(e) => onChartChange({ indexMode: e.currentTarget.checked })}
          />
        </div>
      ) : null}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span
        style={{
          color: "var(--color-text-tertiary)",
          fontSize: "var(--text-2xs)",
          letterSpacing: "0.04em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
      {children}
    </div>
  );
}
