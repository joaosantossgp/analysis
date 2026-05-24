import type { ReactNode } from "react";

type Tone = "scope" | "format" | "path" | "muted";

type Props = {
  children: ReactNode;
  tone?: Tone;
  label?: string;
};

const TONE_COLOR: Record<Tone, string> = {
  scope: "var(--color-id-ticker)",
  format: "var(--color-action-primary)",
  path: "var(--color-state-ok)",
  muted: "var(--color-text-tertiary)",
};

export function ExportScopeBadge({ children, tone = "scope", label }: Props) {
  return (
    <span
      className="inline-flex min-w-0 items-center gap-1 font-mono"
      style={{
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-sm)",
        color: TONE_COLOR[tone],
        fontSize: "var(--text-2xs)",
        lineHeight: 1,
        maxWidth: "100%",
        padding: "4px 6px",
        textTransform: "uppercase",
      }}
      title={typeof children === "string" ? children : undefined}
    >
      {label ? (
        <span style={{ color: "var(--color-text-tertiary)" }}>{label}</span>
      ) : null}
      <span className="truncate">{children}</span>
    </span>
  );
}
