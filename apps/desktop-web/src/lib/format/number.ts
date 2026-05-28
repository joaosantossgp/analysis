/**
 * Number formatting helpers — CVMAnalytics Terminal UI.
 *
 * All helpers are null-safe and return an em-dash ("—") on null / undefined /
 * non-finite input. Locale is en-US (comma thousand, dot decimal separator).
 *
 * Existing `lib/formatters.ts` keeps `formatKpiCell` / `formatUnit` for
 * KPI-row table cells driven by a format-type field. These helpers below are
 * the explicit-named variants used by new Terminal UI components (MetricTape,
 * NumberCell, DeltaBadge).
 */

const EM_DASH = "—";

const BRL_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
  currencyDisplay: "narrowSymbol",
});

const isMissing = (n: number | null | undefined): boolean =>
  n === null || n === undefined || !Number.isFinite(n);

/**
 * Format an absolute monetary value in BRL with no decimal places.
 * Example: 12_345_678 → "R$12,345,678".
 */
export function formatBRL(n: number | null | undefined): string {
  if (isMissing(n)) return EM_DASH;
  return BRL_FORMATTER.format(n as number);
}

/**
 * Format a percentage. Default digits = 1.
 */
export function formatPct(
  n: number | null | undefined,
  digits = 1,
): string {
  if (isMissing(n)) return EM_DASH;
  return `${(n as number).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

/**
 * Format a multiple / ratio with the × suffix.
 * Example: 2.3 → "2.30×". Default digits = 2.
 */
export function formatMultiple(
  n: number | null | undefined,
  digits = 2,
): string {
  if (isMissing(n)) return EM_DASH;
  return `${(n as number).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}×`;
}

/**
 * Format a compact monetary value with magnitude suffix:
 *   K (thousands), M (millions), B (billions), T (trillions).
 * Example: 1_234_567_890 → "R$ 1.23B".
 */
export function formatCompact(n: number | null | undefined): string {
  if (isMissing(n)) return EM_DASH;
  const abs = Math.abs(n as number);
  const sign = (n as number) < 0 ? "-" : "";
  let value: number;
  let suffix: string;
  if (abs >= 1e12) {
    value = abs / 1e12;
    suffix = "T";
  } else if (abs >= 1e9) {
    value = abs / 1e9;
    suffix = "B";
  } else if (abs >= 1e6) {
    value = abs / 1e6;
    suffix = "M";
  } else if (abs >= 1e3) {
    value = abs / 1e3;
    suffix = "K";
  } else {
    return `${sign}R$ ${abs.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  }
  return `${sign}R$ ${value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}${suffix}`;
}

/**
 * Format a signed delta for display in a DeltaBadge.
 */
export function formatSignedPct(
  n: number | null | undefined,
  digits = 1,
): string {
  if (isMissing(n)) return EM_DASH;
  const sign = (n as number) > 0 ? "+" : "";
  return `${sign}${formatPct(n, digits)}`;
}
