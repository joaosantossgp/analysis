export interface PeriodSelectOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
  title?: string;
}

interface PeriodSelectProps<T extends string> {
  ariaLabel: string;
  value: T;
  options: ReadonlyArray<PeriodSelectOption<T>>;
  onChange: (value: T) => void;
}

export function PeriodSelect<T extends string>({
  ariaLabel,
  value,
  options,
  onChange,
}: PeriodSelectProps<T>) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      onChange={(event) => onChange(event.target.value as T)}
      className="period-select font-mono focus-visible:outline focus-visible:outline-1"
    >
      {options.map((option) => (
        <option
          key={option.value}
          value={option.value}
          disabled={option.disabled}
          title={option.title}
          className="bg-[var(--color-surface-3)] text-[var(--color-text-primary)]"
        >
          {option.label}
        </option>
      ))}
    </select>
  );
}
