type StatementLineLabelProps = {
  code?: string | null;
  label: string;
  standardName?: string | null;
  level?: number;
  emphasis?: boolean;
};

export function StatementLineLabel({
  code,
  label,
  standardName,
  level = 0,
  emphasis = false,
}: StatementLineLabelProps) {
  const shownCode = code?.trim() || null;
  const shownStandard =
    standardName && standardName.trim() && standardName !== label
      ? standardName
      : null;

  return (
    <div
      className="min-w-0"
      style={{ paddingLeft: Math.max(0, level) * 14 }}
    >
      <div className="flex min-w-0 items-baseline gap-2">
        {shownCode ? (
          <span
            className="shrink-0 font-mono"
            style={{
              color: "var(--color-id-ticker)",
              fontSize: "var(--text-xs)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {shownCode}
          </span>
        ) : null}
        <span
          className="truncate"
          style={{
            color: emphasis ? "var(--color-text-primary)" : "var(--color-text-secondary)",
            fontSize: "var(--text-sm)",
            fontWeight: emphasis ? 650 : 500,
          }}
        >
          {label}
        </span>
      </div>
      {shownStandard ? (
        <div
          className="truncate"
          style={{
            color: "var(--color-text-tertiary)",
            fontSize: "var(--text-2xs)",
            letterSpacing: "0.04em",
            marginTop: 2,
            textTransform: "uppercase",
          }}
        >
          {shownStandard}
        </div>
      ) : null}
    </div>
  );
}
