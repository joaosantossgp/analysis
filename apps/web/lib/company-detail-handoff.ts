import type { CompanyInfo, RefreshStatusItem } from "@/lib/api";

function normalizeStatus(value: string | null | undefined): string {
  return String(value || "").trim().toLowerCase();
}

/** Reject bogus fractional fiscal years (e.g. 2023.6); accept tiny float noise only. */
const YEAR_INTEGER_TOLERANCE = 1e-6;

function normalizeReadableYear(year: number): number | null {
  if (!Number.isFinite(year)) {
    return null;
  }
  const rounded = Math.round(year);
  if (!Number.isSafeInteger(rounded)) {
    return null;
  }
  if (Math.abs(year - rounded) > YEAR_INTEGER_TOLERANCE) {
    return null;
  }
  return rounded;
}

/**
 * Local DB has `financial_reports` rows but none qualify as annual KPI-ready history
 * (`read_availability_code` from API/read_model). Use for UX copy, not as a data-quality score.
 */
export function companyHasNonAnnualLocalOnly(company: CompanyInfo): boolean {
  return (
    company.has_local_financial_reports &&
    company.read_availability_code === "no_readable_annual_history"
  );
}

function hasReadableYearSignal(item: RefreshStatusItem): boolean {
  return (
    item.readable_years_count > 0 ||
    typeof item.latest_readable_year === "number"
  );
}

export function getReadableCompanyYears(
  company: CompanyInfo,
  availableYears: number[],
): number[] {
  const normalizedYears = Array.from(
    new Set(
      availableYears
        .map((year) => normalizeReadableYear(year))
        .filter((year): year is number => year !== null),
    ),
  ).sort((a, b) => a - b);

  if (normalizedYears.length > 0) {
    return normalizedYears;
  }

  const latestYear =
    company.latest_readable_year != null
      ? normalizeReadableYear(company.latest_readable_year)
      : null;

  const count =
    typeof company.readable_years_count === "number"
      ? company.readable_years_count
      : 0;

  const hasReadSignal =
    company.has_readable_current_data ||
    (Number.isFinite(count) && count > 0);

  if (hasReadSignal && latestYear !== null) {
    return [latestYear];
  }

  return [];
}

export function isReadableRefreshSuccess(
  item: RefreshStatusItem | null | undefined,
): boolean {
  if (!item?.has_readable_current_data || !hasReadableYearSignal(item)) {
    return false;
  }

  const trackingState = normalizeStatus(item.tracking_state);
  const latestOutcome = normalizeStatus(item.latest_attempt_outcome);
  const lastStatus = normalizeStatus(item.last_status);

  return (
    trackingState === "success" ||
    latestOutcome === "success" ||
    lastStatus === "success"
  );
}

export function getReadableRefreshSuccessKey(
  item: RefreshStatusItem | null | undefined,
): string | null {
  if (!item || !isReadableRefreshSuccess(item)) {
    return null;
  }

  return [
    item.cd_cvm,
    item.read_model_updated_at ??
      item.last_success_at ??
      item.finished_at ??
      item.updated_at ??
      "readable",
    item.latest_readable_year ?? "yearless",
    item.job_id ?? "no-job",
  ].join(":");
}
