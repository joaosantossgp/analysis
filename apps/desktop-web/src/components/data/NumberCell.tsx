import type { CSSProperties } from "react";

import { formatKpiCell } from "@/lib/formatters";

export type NumberTone = "neutral" | "positive" | "negative" | "muted" | "auto";

type NumberCellProps = {
  value: unknown;
  formatType?: unknown;
  tone?: NumberTone;
  signed?: boolean;
  size?: "sm" | "md" | "lg";
  align?: "left" | "right";
  className?: string;
  title?: string;
};

function toneColor(tone: NumberTone, value: unknown): string {
  const resolved =
    tone === "auto" && typeof value === "number" && Number.isFinite(value)
      ? value > 0
        ? "positive"
        : value < 0
          ? "negative"
          : "neutral"
      : tone;

  if (resolved === "positive") return "var(--color-num-pos)";
  if (resolved === "negative") return "var(--color-num-neg)";
  if (resolved === "muted") return "var(--color-text-tertiary)";
  return "var(--color-text-primary)";
}

function fontSize(size: NonNullable<NumberCellProps["size"]>): string {
  if (size === "lg") return "var(--text-xl)";
  if (size === "md") return "var(--text-base)";
  return "var(--text-sm)";
}

function formatValue(value: unknown, formatType: unknown, signed: boolean): string {
  const formatted = formatKpiCell(value, formatType);
  if (!signed || typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return formatted;
  }
  return `+${formatted}`;
}

export function NumberCell({
  value,
  formatType,
  tone = "neutral",
  signed = false,
  size = "sm",
  align = "right",
  className,
  title,
}: NumberCellProps) {
  const style: CSSProperties = {
    color: toneColor(tone, value),
    display: "inline-block",
    fontFamily: "var(--font-mono)",
    fontSize: fontSize(size),
    fontVariantNumeric: "tabular-nums",
    fontWeight: size === "lg" ? 600 : 500,
    lineHeight: 1.2,
    minWidth: align === "right" ? "5ch" : undefined,
    textAlign: align,
    whiteSpace: "nowrap",
  };

  return (
    <span className={className} style={style} title={title}>
      {formatValue(value, formatType, signed)}
    </span>
  );
}
