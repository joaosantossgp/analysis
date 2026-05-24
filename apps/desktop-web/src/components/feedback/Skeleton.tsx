import type { CSSProperties } from "react";

/**
 * Static skeleton placeholder. No shimmer animation — the terminal
 * aesthetic prefers calm grey blocks over marketing-style pulse.
 *
 * Variants:
 *   line  — single text line, defaults to full width / 12px tall
 *   block — solid block, caller supplies width/height via style
 *   row   — multi-line row stack, count via `lines` prop
 */

type CommonProps = {
  className?: string;
  style?: CSSProperties;
};

export function SkeletonLine({
  width = "100%",
  height = 12,
  className,
  style,
}: CommonProps & { width?: number | string; height?: number | string }) {
  return (
    <div
      aria-hidden="true"
      className={className}
      style={{
        width,
        height,
        background: "var(--color-surface-3)",
        borderRadius: "var(--radius-sm)",
        ...style,
      }}
    />
  );
}

export function SkeletonBlock({
  width = "100%",
  height = 64,
  className,
  style,
}: CommonProps & { width?: number | string; height?: number | string }) {
  return (
    <div
      aria-hidden="true"
      className={className}
      style={{
        width,
        height,
        background: "var(--color-surface-2)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "var(--radius-md)",
        ...style,
      }}
    />
  );
}

export function SkeletonRow({
  lines = 3,
  className,
  style,
}: CommonProps & { lines?: number }) {
  return (
    <div
      aria-hidden="true"
      className={className}
      style={{ display: "flex", flexDirection: "column", gap: 8, ...style }}
    >
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonLine
          key={i}
          width={i === lines - 1 ? "60%" : "100%"}
          height={10}
        />
      ))}
    </div>
  );
}
