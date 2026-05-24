/**
 * Number formatting helpers — CVMAnalytics Terminal UI.
 *
 * All helpers are null-safe and return an em-dash ("—") on null / undefined /
 * non-finite input. Locale is fixed to pt-BR (Brazilian convention: comma
 * decimal, dot thousand separator).
 *
 * Existing `lib/formatters.ts` keeps `formatKpiCell` / `formatUnit` for
 * KPI-row table cells driven by a format-type field. These helpers below are
 * the explicit-named variants used by new Terminal UI components (MetricTape,
 * NumberCell, DeltaBadge).
 */

const EM_DASH = "—";

const BRL_FORMATTER = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});

const isMissing = (n: number | null | undefined): boolean =>
  n === null || n === undefined || !Number.isFinite(n);

/**
 * Format an absolute monetary value in BRL with no decimal places.
 * Example: 12_345_678 → "R$ 12.345.678".
 */
export function formatBRL(n: number | null | undefined): string {
  if (isMissing(n)) return EM_DASH;
  return BRL_FORMATTER.format(n as number);
}

/**
 * Format a percentage. Input is the raw ratio (0.123 → "12,3%") OR a
 * pre-scaled percentage value (12.3 → "12,3%") — caller controls.
 *
 * Default digits = 1.
 */
export function formatPct(
  n: number | null | undefined,
  digits = 1,
): string {
  if (isMissing(n)) return EM_DASH;
  return `${(n as number).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

/**
 * Format a multiple / ratio with the × suffix.
 * Example: 2.3 → "2,30×". Default digits = 2.
 */
export function formatMultiple(
  n: number | null | undefined,
  digits = 2,
): string {
  if (isMissing(n)) return EM_DASH;
  return `${(n as number).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}×`;
}

/**
 * Format a compact monetary value with Brazilian magnitude suffix:
 *   k (mil), mi (milhões), bi (bilhões), tri (trilhões).
 * Example: 1_234_567_890 → "R$ 1,23 bi".
 */
export function formatCompact(n: number | null | undefined): string {
  if (isMissing(n)) return EM_DASH;
  const abs = Math.abs(n as number);
  const sign = (n as number) < 0 ? "-" : "";
  let value: number;
  let suffix: string;
  if (abs >= 1e12) {
    value = abs / 1e12;
    suffix = " tri";
  } else if (abs >= 1e9) {
    value = abs / 1e9;
    suffix = " bi";
  } else if (abs >= 1e6) {
    value = abs / 1e6;
    suffix = " mi";
  } else if (abs >= 1e3) {
    value = abs / 1e3;
    suffix = " k";
  } else {
    return `${sign}R$ ${abs.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`;
  }
  return `${sign}R$ ${value.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}${suffix}`;
}

/**
 * Format a signed delta for display in a DeltaBadge. Returns the raw
 * formatted string without the glyph — DeltaBadge supplies the ▲/▼/—
 * separately so the caller controls the icon column width.
 */
export function formatSignedPct(
  n: number | null | undefined,
  digits = 1,
): string {
  if (isMissing(n)) return EM_DASH;
  const sign = (n as number) > 0 ? "+" : "";
  return `${sign}${formatPct(n, digits)}`;
}
