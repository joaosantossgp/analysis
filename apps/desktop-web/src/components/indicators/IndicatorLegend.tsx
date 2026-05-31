import type { ReactNode } from "react";

import { formatValue } from "@/lib/indicators/format";
import type {
  AxisSide,
  ChartType,
  IndicatorSelection,
  ResolvedSeries,
} from "@/lib/indicators/types";

interface IndicatorLegendProps {
  series: ResolvedSeries[];
  selectionById: Map<string, IndicatorSelection>;
  indexMode: boolean;
  /** Hidden when every selected indicator shares one unit (dual axis adds nothing). */
  showAxisControls: boolean;
  onSetAxis: (id: string, axis: "auto" | AxisSide) => void;
  onSetType: (id: string, type: "auto" | ChartType) => void;
  onRemove: (id: string) => void;
}

const AXIS_CYCLE: Array<"auto" | AxisSide> = ["auto", "left", "right"];
const TYPE_CYCLE: Array<"auto" | ChartType> = ["auto", "line", "bar", "area"];
const AXIS_LABEL: Record<"auto" | AxisSide, string> = {
  auto: "axis: auto",
  left: "axis: L",
  right: "axis: R",
};
const TYPE_LABEL: Record<"auto" | ChartType, string> = {
  auto: "type: auto",
  line: "type: line",
  bar: "type: bar",
  area: "type: area",
};

function next<T>(cycle: T[], current: T): T {
  const i = cycle.indexOf(current);
  return cycle[(i + 1) % cycle.length];
}

/**
 * Interactive legend. Each series maps to its colour and latest value, and
 * exposes contextual per-series controls (axis assignment, type override,
 * remove) right where the series is shown — keeping the top control bar simple.
 */
export function IndicatorLegend({
  series,
  selectionById,
  indexMode,
  showAxisControls,
  onSetAxis,
  onSetType,
  onRemove,
}: IndicatorLegendProps) {
  if (series.length === 0) return null;
  return (
    <ul className="flex flex-wrap" style={{ gap: 8, listStyle: "none", margin: 0, padding: 0 }}>
      {series.map((s) => {
        const sel = selectionById.get(s.id);
        const axisValue = sel?.axis ?? "auto";
        const typeValue = sel?.type ?? "auto";
        return (
          <li
            key={s.id}
            className="flex items-center"
            style={{
              background: "var(--color-surface-1)",
              border: "1px solid var(--color-border-subtle)",
              borderRadius: "var(--radius-sm)",
              gap: 8,
              padding: "4px 6px",
            }}
          >
            <span
              aria-hidden="true"
              style={{ background: s.color, borderRadius: 1, flexShrink: 0, height: 10, width: 10 }}
            />
            <span style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)" }}>
              {s.label}
            </span>
            <span
              className="font-mono"
              style={{
                color: "var(--color-text-secondary)",
                fontSize: "var(--text-xs)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {formatValue(s.latest, s.unit, indexMode)}
            </span>

            <span
              aria-hidden="true"
              style={{ background: "var(--color-border-subtle)", height: 14, width: 1 }}
            />

            <MiniButton
              onClick={() => onSetType(s.id, next(TYPE_CYCLE, typeValue))}
              title="Cycle this series' chart type"
            >
              {TYPE_LABEL[typeValue]}
            </MiniButton>

            {showAxisControls && !indexMode ? (
              <MiniButton
                onClick={() => onSetAxis(s.id, next(AXIS_CYCLE, axisValue))}
                title="Cycle this series' axis (auto / left / right)"
              >
                {AXIS_LABEL[axisValue]}
              </MiniButton>
            ) : null}

            <MiniButton onClick={() => onRemove(s.id)} title="Remove from chart" danger>
              ×
            </MiniButton>
          </li>
        );
      })}
    </ul>
  );
}

function MiniButton({
  children,
  onClick,
  title,
  danger = false,
}: {
  children: ReactNode;
  onClick: () => void;
  title: string;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="font-mono focus-visible:outline focus-visible:outline-1"
      style={{
        background: "transparent",
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-sm)",
        color: danger ? "var(--color-text-tertiary)" : "var(--color-text-secondary)",
        cursor: "pointer",
        fontSize: "var(--text-2xs)",
        lineHeight: 1,
        outlineColor: "var(--color-border-focus)",
        padding: "3px 5px",
      }}
    >
      {children}
    </button>
  );
}
