import { useEffect, useRef, useState, type ReactNode } from "react";

import { Checkbox } from "@/components/ui/Checkbox";
import { PeriodSelect, type PeriodSelectOption } from "@/components/ui/PeriodSelect";
import type {
  ChartAesthetics,
  Frequency,
  IndicatorDef,
} from "@/lib/indicators/types";

import { IndicatorPicker } from "./IndicatorPicker";

interface IndicatorControlsProps {
  periodValue?: string;
  periodOptions?: ReadonlyArray<PeriodSelectOption<string>>;
  onPeriodChange?: (period: string) => void;
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
  optionsContent?: ReactNode;
  showLegendOption?: boolean;
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

export function IndicatorControls({
  periodValue,
  periodOptions,
  onPeriodChange,
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
  optionsContent,
  showLegendOption = true,
}: IndicatorControlsProps) {
  const [showOptions, setShowOptions] = useState(false);
  const optionsRef = useRef<HTMLDivElement>(null);
  const smoothDisabled = chart.type === "bar";

  useEffect(() => {
    if (!showOptions) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowOptions(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [showOptions]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="chart-toolbar company-chart-toolbar">
        {periodValue && periodOptions && onPeriodChange ? (
          <Field label="Period">
            <PeriodSelect
              ariaLabel="Financial indicator period"
              value={periodValue}
              options={periodOptions}
              onChange={onPeriodChange}
            />
          </Field>
        ) : null}

        {showFrequency ? (
          <Field label="Frequency">
            <PeriodSelect<Frequency>
              ariaLabel="Frequency"
              value={frequency}
              options={FREQUENCY_OPTIONS(quarterlyAvailable)}
              onChange={onFrequencyChange}
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

        <div ref={optionsRef} className="chart-toolbar__actions" style={{ position: "relative" }}>
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

          {showOptions ? (
            <>
              <button
                type="button"
                aria-label="Close chart options"
                tabIndex={-1}
                onClick={() => setShowOptions(false)}
                style={{
                  position: "fixed",
                  inset: 0,
                  zIndex: 40,
                  background: "transparent",
                  border: "none",
                  cursor: "default",
                }}
              />
              <div
                role="dialog"
                aria-label="Financial chart options"
                className="flex flex-wrap items-center gap-x-5 gap-y-2"
                style={{
                  position: "absolute",
                  top: "calc(100% + 6px)",
                  right: 0,
                  zIndex: 50,
                  width: "min(340px, calc(100vw - 32px))",
                  background: "var(--color-surface-2)",
                  border: "1px solid var(--color-border-default)",
                  borderRadius: "var(--radius-md)",
                  boxShadow: "var(--shadow-overlay)",
                  padding: "10px 12px",
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
                {showLegendOption ? (
                  <Checkbox
                    label="Legend"
                    checked={chart.legend}
                    onChange={(e) => onChartChange({ legend: e.currentTarget.checked })}
                  />
                ) : null}
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
                {optionsContent ? (
                  <div className="w-full" style={{ borderTop: "1px solid var(--color-border-subtle)", paddingTop: 8 }}>
                    {optionsContent}
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="chart-toolbar__field" style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
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
