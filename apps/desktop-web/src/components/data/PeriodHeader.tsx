type PeriodHeaderProps = {
  label: string;
  latest?: boolean;
  sublabel?: string;
};

export function PeriodHeader({ label, latest = false, sublabel }: PeriodHeaderProps) {
  return (
    <span className="inline-flex flex-col items-end gap-0.5">
      <span
        className="font-mono"
        style={{
          color: latest ? "var(--color-action-primary)" : "var(--color-text-secondary)",
          fontSize: "var(--text-xs)",
          fontVariantNumeric: "tabular-nums",
          fontWeight: latest ? 600 : 500,
          lineHeight: 1.1,
        }}
      >
        {label}
      </span>
      {latest || sublabel ? (
        <span
          style={{
            color: latest ? "var(--color-action-primary)" : "var(--color-text-tertiary)",
            fontSize: "var(--text-2xs)",
            fontWeight: 500,
            letterSpacing: "0.04em",
            lineHeight: 1,
            textTransform: "uppercase",
          }}
        >
          {sublabel ?? "latest"}
        </span>
      ) : null}
    </span>
  );
}
