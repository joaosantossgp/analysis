import type { CSSProperties } from "react";

import { formatKpiCell } from "@/lib/formatters";

type DeltaBadgeProps = {
  value: unknown;
  label?: string;
  className?: string;
};

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function formatDelta(value: number): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatKpiCell(value, "pct")}`;
}

export function DeltaBadge({ value, label = "YoY", className }: DeltaBadgeProps) {
  const hasValue = isFiniteNumber(value);
  const direction = hasValue ? (value > 0 ? "up" : value < 0 ? "down" : "flat") : "none";
  const glyph = direction === "up" ? "▲" : direction === "down" ? "▼" : "—";
  const color =
    direction === "up"
      ? "var(--color-num-pos)"
      : direction === "down"
        ? "var(--color-num-neg)"
        : "var(--color-text-tertiary)";

  const style: CSSProperties = {
    alignItems: "center",
    border: `1px solid ${hasValue ? "var(--color-border-default)" : "var(--color-border-subtle)"}`,
    borderRadius: "var(--radius-sm)",
    color,
    display: "inline-flex",
    fontFamily: "var(--font-mono)",
    fontSize: "var(--text-xs)",
    fontVariantNumeric: "tabular-nums",
    gap: 4,
    height: 22,
    justifyContent: "center",
    minWidth: 68,
    padding: "0 6px",
    whiteSpace: "nowrap",
  };

  return (
    <span
      className={className}
      style={style}
      aria-label={
        hasValue
          ? `${label} ${direction === "up" ? "up" : direction === "down" ? "down" : "flat"} ${formatDelta(value)}`
          : `${label} unavailable`
      }
      title={hasValue ? `${label}: ${formatDelta(value)}` : `${label}: sem dado`}
    >
      <span aria-hidden="true">{glyph}</span>
      <span>{hasValue ? formatDelta(value) : "—"}</span>
    </span>
  );
}
