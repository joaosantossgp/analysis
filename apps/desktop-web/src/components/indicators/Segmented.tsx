/**
 * Compact segmented control — a labelled radio group styled as a button strip.
 * Used for frequency and chart-type pickers in the indicator workspace.
 */
export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
  title?: string;
}

interface SegmentedProps<T extends string> {
  value: T;
  options: ReadonlyArray<SegmentedOption<T>>;
  onChange: (value: T) => void;
  ariaLabel: string;
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: SegmentedProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      style={{
        display: "inline-flex",
        flexShrink: 0,
        background: "var(--color-surface-1)",
        border: "1px solid var(--color-border-default)",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
      }}
    >
      {options.map((opt, i) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={opt.disabled}
            title={opt.title}
            onClick={() => !opt.disabled && onChange(opt.value)}
            className="font-mono focus-visible:outline focus-visible:outline-1"
            style={{
              background: active ? "var(--color-surface-3)" : "transparent",
              borderLeft: i === 0 ? "none" : "1px solid var(--color-border-default)",
              color: opt.disabled
                ? "var(--color-text-disabled)"
                : active
                  ? "var(--color-action-primary)"
                  : "var(--color-text-secondary)",
              cursor: opt.disabled ? "not-allowed" : "pointer",
              flexShrink: 0,
              fontSize: "var(--text-xs)",
              height: 26,
              minWidth: opt.label.length >= 8 ? 76 : 0,
              outlineColor: "var(--color-border-focus)",
              padding: "0 10px",
              whiteSpace: "nowrap",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
