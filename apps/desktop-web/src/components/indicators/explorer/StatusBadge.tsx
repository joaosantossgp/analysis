import type { CSSProperties, ReactNode } from "react";

import type { IndicatorStatus } from "@/lib/indicators/registry";
import { statusLabel } from "@/lib/indicators/registry";

/**
 * Cache-status badge. Signal is carried by BOTH a glyph and a colour so it is
 * never colour-only (UI accessibility rule). Neutral statuses stay grey to
 * respect the "scarcity of colour" guideline.
 */
const STATUS_STYLE: Record<
  IndicatorStatus,
  { color: string; glyph: string }
> = {
  cached: { color: "var(--color-state-ok)", glyph: "●" },
  stale: { color: "var(--color-state-warn)", glyph: "▲" },
  missing: { color: "var(--color-text-tertiary)", glyph: "○" },
  failed: { color: "var(--color-state-err)", glyph: "✕" },
  blocked: { color: "var(--color-text-disabled)", glyph: "⊘" },
};

export function StatusBadge({ status }: { status: IndicatorStatus }) {
  const s = STATUS_STYLE[status];
  return (
    <span
      className="font-mono"
      style={{
        alignItems: "center",
        border: `1px solid ${s.color}`,
        borderRadius: "var(--radius-sm)",
        color: s.color,
        display: "inline-flex",
        fontSize: "var(--text-2xs)",
        gap: 4,
        lineHeight: 1,
        padding: "2px 5px",
        whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden="true">{s.glyph}</span>
      {statusLabel(status)}
    </span>
  );
}

/** Neutral, low-emphasis tag for source / theme / unit / value-type labels. */
export function Tag({
  children,
  title,
  tone = "neutral",
  style,
}: {
  children: ReactNode;
  title?: string;
  tone?: "neutral" | "info";
  style?: CSSProperties;
}) {
  const color =
    tone === "info" ? "var(--color-state-info)" : "var(--color-text-secondary)";
  return (
    <span
      className="font-mono"
      title={title}
      style={{
        background: "var(--color-surface-1)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-sm)",
        color,
        fontSize: "var(--text-2xs)",
        lineHeight: 1,
        padding: "2px 6px",
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {children}
    </span>
  );
}
