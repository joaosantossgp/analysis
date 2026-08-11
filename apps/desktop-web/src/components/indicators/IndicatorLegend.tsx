import { useState, type ReactNode } from "react";

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

const COLOR_PALETTE = ["#22D3EE", "#FBBF24", "#4ADE80", "#F472B6", "#A78BFA", "#FB923C"];
const CHART_TYPE_CYCLE: ChartType[] = ["line", "bar", "area"];

function nextChartType(current: ChartType): ChartType {
  return CHART_TYPE_CYCLE[(CHART_TYPE_CYCLE.indexOf(current) + 1) % CHART_TYPE_CYCLE.length];
}

function ChartTypeIcon({ type }: { type: ChartType }) {
  if (type === "bar") return <svg viewBox="0 0 28 16" width="22" height="14" aria-hidden="true"><path d="M4 14V8M11 14V3M18 14V6M25 14V1" stroke="currentColor" strokeWidth="3" /></svg>;
  if (type === "area") return <svg viewBox="0 0 28 16" width="22" height="14" aria-hidden="true"><path d="M2 13L10 7L18 10L26 3V14H2Z" fill="currentColor" opacity=".3" /><path d="M2 13L10 7L18 10L26 3" fill="none" stroke="currentColor" strokeWidth="2" /></svg>;
  return <svg viewBox="0 0 28 16" width="22" height="14" aria-hidden="true"><path d="M2 9L10 6L18 10L26 4" fill="none" stroke="currentColor" strokeWidth="2" /><circle cx="10" cy="6" r="2" fill="currentColor" /></svg>;
}

/** Compact per-series chart controls used directly below the plot. */
export function EditableSeriesLegend({
  series,
  stylesById,
  onSetColor,
  onSetType,
}: {
  series: ResolvedSeries[];
  stylesById: Map<string, { color?: string; type?: ChartType }>;
  onSetColor: (id: string, color: string) => void;
  onSetType: (id: string, type: ChartType) => void;
}) {
  const [openColorId, setOpenColorId] = useState<string | null>(null);
  if (series.length < 2) return null;
  return (
    <ul className="flex flex-wrap" style={{ gap: 10, listStyle: "none", margin: 0, minWidth: 0, padding: 0 }}>
      {series.map((seriesItem) => {
        const current = stylesById.get(seriesItem.id);
        return (
        <li
          key={seriesItem.id}
          className="flex items-center"
          style={{ color: "var(--color-text-secondary)", fontSize: "var(--text-xs)", gap: 6, minWidth: 0, position: "relative" }}
          title={seriesItem.label}
        >
          <button type="button" aria-label={`Change ${seriesItem.label} color`} onClick={() => setOpenColorId((id) => id === seriesItem.id ? null : seriesItem.id)} style={{ background: seriesItem.color, border: 0, borderRadius: 1, cursor: "pointer", flexShrink: 0, height: 11, padding: 0, width: 11 }} />
          <span className="truncate">{seriesItem.label}</span>
          <button type="button" aria-label={`Change ${seriesItem.label} chart type`} onClick={() => onSetType(seriesItem.id, nextChartType(current?.type ?? seriesItem.type))} className="focus-visible:outline focus-visible:outline-1" style={{ alignItems: "center", background: "var(--color-surface-1)", border: "1px solid var(--color-border-default)", borderRadius: "var(--radius-sm)", color: "var(--color-text-secondary)", cursor: "pointer", display: "flex", height: 24, justifyContent: "center", outlineColor: "var(--color-border-focus)", padding: 0, width: 30 }}>
            <ChartTypeIcon type={current?.type ?? seriesItem.type} />
          </button>
          {openColorId === seriesItem.id ? <span className="flex" role="group" aria-label={`${seriesItem.label} color palette`} style={{ background: "var(--color-surface-3)", border: "1px solid var(--color-border-default)", borderRadius: "var(--radius-sm)", gap: 4, padding: 4, position: "absolute", zIndex: 2, top: "calc(100% + 4px)" }}>{COLOR_PALETTE.map((color) => <button key={color} type="button" aria-label={`Use ${color}`} onClick={() => { onSetColor(seriesItem.id, color); setOpenColorId(null); }} style={{ background: color, border: 0, borderRadius: 1, cursor: "pointer", height: 14, padding: 0, width: 14 }} />)}</span> : null}
        </li>
        );
      })}
    </ul>
  );
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
  const [expandedId, setExpandedId] = useState<string | null>(null);
  if (series.length === 0) return null;
  return (
    <ul className="flex flex-wrap" style={{ gap: 8, listStyle: "none", margin: 0, minWidth: 0, padding: 0 }}>
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
              maxWidth: "100%",
              minWidth: 0,
              padding: "4px 6px",
            }}
          >
            <span
              aria-hidden="true"
              style={{ background: s.color, borderRadius: 1, flexShrink: 0, height: 10, width: 10 }}
            />
            <span
              className="truncate"
              style={{ color: "var(--color-text-primary)", fontSize: "var(--text-xs)", minWidth: 0 }}
              title={s.label}
            >
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

            <MiniButton
              onClick={() => setExpandedId((current) => (current === s.id ? null : s.id))}
              title="Edit this series"
            >
              Edit
            </MiniButton>

            <MiniButton onClick={() => onRemove(s.id)} title="Remove from chart" danger>
              ×
            </MiniButton>

            {expandedId === s.id ? (
              <>
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
              </>
            ) : null}
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
