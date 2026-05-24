import type { CSSProperties, ReactNode } from "react";

type IdentifierBadgeProps = {
  label?: string;
  children: ReactNode;
  muted?: boolean;
  className?: string;
};

export function IdentifierBadge({
  label,
  children,
  muted = false,
  className,
}: IdentifierBadgeProps) {
  const style: CSSProperties = {
    alignItems: "center",
    background: muted ? "transparent" : "var(--color-surface-1)",
    border: `1px solid ${muted ? "var(--color-border-default)" : "var(--color-id-ticker)"}`,
    borderRadius: "var(--radius-sm)",
    color: muted ? "var(--color-text-secondary)" : "var(--color-id-link)",
    display: "inline-flex",
    fontFamily: "var(--font-mono)",
    fontSize: "var(--text-xs)",
    fontVariantNumeric: "tabular-nums",
    gap: 6,
    minHeight: 22,
    padding: "2px 7px",
    whiteSpace: "nowrap",
  };

  return (
    <span className={className} style={style}>
      {label ? (
        <span style={{ color: "var(--color-text-tertiary)" }}>{label}</span>
      ) : null}
      <span>{children}</span>
    </span>
  );
}
