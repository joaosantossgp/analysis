/**
 * Indicator Explorer registry.
 *
 * The canonical indicator catalog is owned by the Python backend `kpi_catalog`
 * table (country `energy_utilities.country.*` + SIN `energy_utilities.sin.*`),
 * surfaced verbatim through the `get_kpi_catalog` bridge method as
 * `KPICatalogEntry[]`. This module does NOT redefine that catalog — it only
 * normalises each entry into the presentation-oriented `IndicatorRecord` shape
 * the Explorer renders, deriving analytical theme, source group, frequency,
 * value type and cache status from fields that already exist on the catalog
 * entry, the time-series rows, and the health snapshots.
 *
 * Reproducibility note: every metadata field shown in the Explorer maps back to
 * a real backend field. Nothing is invented; missing values render as "—".
 */
import type {
  CountryKPIValue,
  EnergyKPIHealthResponse,
  KPICatalogEntry,
  SINKPIDashboardResponse,
  SINKPIObservation,
} from "@/lib/bridge/types";
import type { IndicatorUnit } from "./types";

// ── Namespaces (mirror the backend kpi_id prefixes) ─────────────────────────────
export const COUNTRY_NS = "energy_utilities.country";
export const SIN_NS = "energy_utilities.sin";

export type IndicatorSourceGroup = "energy_country" | "sin";
export type IndicatorValueType = "raw" | "derived";
/** Local-first cache state for one indicator. */
export type IndicatorStatus = "cached" | "stale" | "missing" | "failed" | "blocked";

/**
 * Presentation model for one indicator in the Explorer. Derived from a
 * `KPICatalogEntry` plus cached series + health context.
 */
export interface IndicatorRecord {
  id: string;
  name: string;
  description: string;

  /** Analytical theme (what the metric measures), distinct from its source. */
  theme: string;
  themeKey: string;

  /** Where the data comes from (API / dataset). */
  sourceGroup: IndicatorSourceGroup;
  sourceLabel: string;
  primarySource: string;

  geography: string;
  geographyKey: string;

  frequency: string;
  frequencyKey: string;

  /** Raw unit string from the catalog ("%", "TWh", "MWmed", "R$/MWh"…). */
  unit: string;
  /** Coarse unit family used by the preview chart. */
  chartUnit: IndicatorUnit;

  valueType: IndicatorValueType;
  calculationMethod: string;

  status: IndicatorStatus;
  lastRefreshAt: string | null;

  /** Latest cached value for a representative geography (see `latestValueLabel`). */
  latestValue: number | null;
  latestValueLabel: string | null;
  latestReferenceDate: string | null;

  coverageStart: string | null;
  coverageEnd: string | null;

  methodology: string;
  caveats: string;
  auditNotes: string;
  verificationStatus: string;
  higherIsBetter: boolean | null;
  dashboardPriority: string;

  /** Latest data_quality_status seen for the representative value. */
  dataQuality: string | null;

  relatedIds: string[];
}

// ── Theme mapping (macro_category → analytical theme) ───────────────────────────

const THEME_LABELS: Record<string, string> = {
  // Country
  renewables: "Renewables",
  fossil_dependence: "Fossil dependence",
  hydro: "Hydro",
  thermal: "Thermal",
  nuclear: "Nuclear",
  generation: "Generation",
  demand: "Demand",
  carbon_intensity: "Carbon intensity",
  emissions: "Emissions",
  trade: "Trade",
  energy_mix: "Primary energy mix",
  transition: "Energy transition",
  capacity: "Capacity",
  // SIN
  load: "Load",
  generation_mix: "Generation mix",
  reservoirs: "Reservoirs",
  hydrology: "Hydrology",
  price: "Prices",
  interchange: "Trade",
};

function titleCase(raw: string): string {
  return raw
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function themeFor(macroCategory: string): { label: string; key: string } {
  const key = (macroCategory || "other").toLowerCase();
  return { label: THEME_LABELS[key] ?? (titleCase(key) || "Other"), key };
}

// ── Source / geography / frequency derivations ──────────────────────────────────

function isSin(kpiId: string): boolean {
  return kpiId.startsWith(SIN_NS);
}

function sourceFor(entry: KPICatalogEntry): {
  group: IndicatorSourceGroup;
  label: string;
} {
  if (isSin(entry.kpi_id)) {
    const src = (entry.primary_source || "").toUpperCase();
    return { group: "sin", label: src === "CCEE" ? "CCEE" : "ONS" };
  }
  return { group: "energy_country", label: "OWID / Ember" };
}

function geographyFor(group: IndicatorSourceGroup): { label: string; key: string } {
  return group === "sin"
    ? { label: "Brazil — SIN subsystems", key: "sin" }
    : { label: "Country (cross-country)", key: "country" };
}

function frequencyFor(group: IndicatorSourceGroup): { label: string; key: string } {
  // The catalog does not carry a frequency column; derive by source group.
  // Country energy is annual; SIN operating data is sub-daily, cached daily.
  return group === "sin"
    ? { label: "Daily / intraday", key: "daily" }
    : { label: "Annual", key: "annual" };
}

/** "%" / "% MLT" → pct; everything else renders as a plain number with its unit. */
export function toChartUnit(unit: string): IndicatorUnit {
  const u = (unit || "").trim().toLowerCase();
  if (u === "%" || u.startsWith("% ") || u === "pp") return "pct";
  return "number";
}

function valueTypeFor(calculationMethod: string): IndicatorValueType {
  return calculationMethod && calculationMethod !== "direct" ? "derived" : "raw";
}

// ── Value formatting ────────────────────────────────────────────────────────────

/**
 * Format a latest value with its raw unit. Catalog/series percentage values are
 * stored on a 0–100 scale (not fractions), so we append the unit verbatim
 * rather than routing through the fraction-based KPI formatter.
 */
export function formatLatestValue(value: number | null, unit: string): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  const digits = abs >= 1000 ? 0 : abs >= 100 ? 1 : 2;
  const num = value.toLocaleString("en-US", { maximumFractionDigits: digits });
  const u = (unit || "").trim();
  if (!u || u === "—") return num;
  if (u === "%") return `${num}%`;
  return `${num} ${u}`;
}

// ── Record builder ──────────────────────────────────────────────────────────────

interface BuildContext {
  countrySeries: CountryKPIValue[];
  sinObservations: SINKPIObservation[];
  energyHealth: EnergyKPIHealthResponse | null;
  sinDashboard: SINKPIDashboardResponse | null;
}

/** Preferred representative geographies for the table's "latest value" column. */
const REF_ISO = "BRA";
const REF_SUBSYSTEM = "SE_CO";

function buildCountryMeta(
  kpiId: string,
  series: CountryKPIValue[],
): {
  latestValue: number | null;
  latestValueLabel: string | null;
  latestReferenceDate: string | null;
  coverageStart: string | null;
  coverageEnd: string | null;
  hasSeries: boolean;
  dataQuality: string | null;
} {
  const rows = series.filter((v) => v.kpi_id === kpiId && v.value !== null);
  if (rows.length === 0) {
    return {
      latestValue: null,
      latestValueLabel: null,
      latestReferenceDate: null,
      coverageStart: null,
      coverageEnd: null,
      hasSeries: false,
      dataQuality: null,
    };
  }
  const periods = rows.map((r) => r.period);
  const coverageStart = String(Math.min(...periods));
  const coverageEnd = String(Math.max(...periods));

  const refIso = rows.some((r) => r.iso_code === REF_ISO) ? REF_ISO : rows[0].iso_code;
  const refRows = rows
    .filter((r) => r.iso_code === refIso)
    .sort((a, b) => a.period - b.period);
  const latest = refRows.at(-1) ?? null;

  return {
    latestValue: latest?.value ?? null,
    latestValueLabel: latest ? (latest.country_name || refIso) : null,
    latestReferenceDate: latest ? String(latest.period) : null,
    coverageStart,
    coverageEnd,
    hasSeries: true,
    dataQuality: latest?.data_quality_status ?? null,
  };
}

function buildSinMeta(
  kpiId: string,
  observations: SINKPIObservation[],
): {
  latestValue: number | null;
  latestValueLabel: string | null;
  latestReferenceDate: string | null;
  coverageStart: string | null;
  coverageEnd: string | null;
  hasSeries: boolean;
  dataQuality: string | null;
} {
  const rows = observations.filter((o) => o.kpi_id === kpiId && o.value !== null);
  if (rows.length === 0) {
    return {
      latestValue: null,
      latestValueLabel: null,
      latestReferenceDate: null,
      coverageStart: null,
      coverageEnd: null,
      hasSeries: false,
      dataQuality: null,
    };
  }
  const ref =
    rows.find((r) => r.subsystem_code === REF_SUBSYSTEM) ?? rows[0];
  return {
    latestValue: ref.value,
    latestValueLabel: ref.subsystem_name || ref.subsystem_code,
    latestReferenceDate: ref.reference_datetime,
    // The dashboard snapshot only carries the latest reference; full coverage
    // start is not available without the full SIN series.
    coverageStart: null,
    coverageEnd: ref.reference_datetime,
    hasSeries: true,
    dataQuality: ref.data_quality_status ?? null,
  };
}

export function buildIndicatorRecords(
  entries: KPICatalogEntry[],
  ctx: BuildContext,
): IndicatorRecord[] {
  // Index country series by KPI for O(1) presence checks.
  const countryByKpi = new Map<string, CountryKPIValue[]>();
  for (const v of ctx.countrySeries) {
    const bucket = countryByKpi.get(v.kpi_id);
    if (bucket) bucket.push(v);
    else countryByKpi.set(v.kpi_id, [v]);
  }
  const sinObs = ctx.sinObservations;

  const energyStale = ctx.energyHealth?.is_stale ?? false;
  const energyFailed =
    !!ctx.energyHealth?.refresh_error ||
    (ctx.energyHealth?.last_refresh_status != null &&
      ctx.energyHealth.last_refresh_status !== "success");
  const sinStale = ctx.sinDashboard?.is_stale ?? false;
  const sinFailed = !!ctx.sinDashboard?.refresh_error;

  // Group entries by theme so we can link related indicators.
  const byTheme = new Map<string, string[]>();
  for (const e of entries) {
    const { key } = themeFor(e.macro_category);
    const arr = byTheme.get(key);
    if (arr) arr.push(e.kpi_id);
    else byTheme.set(key, [e.kpi_id]);
  }

  return entries.map((entry) => {
    const { group, label: sourceLabel } = sourceFor(entry);
    const theme = themeFor(entry.macro_category);
    const geo = geographyFor(group);
    const freq = frequencyFor(group);

    const meta =
      group === "sin"
        ? buildSinMeta(entry.kpi_id, sinObs)
        : buildCountryMeta(entry.kpi_id, countryByKpi.get(entry.kpi_id) ?? []);

    const blocked =
      entry.source_verification_status === "blocked" ||
      entry.v1_status === "blocked_by_source_verification";
    const stale = group === "sin" ? sinStale : energyStale;
    const failed = group === "sin" ? sinFailed : energyFailed;

    let status: IndicatorStatus;
    if (blocked) status = "blocked";
    else if (!meta.hasSeries) status = failed ? "failed" : "missing";
    else if (stale) status = "stale";
    else status = "cached";

    const lastRefreshAt =
      group === "sin"
        ? ctx.sinDashboard?.last_successful_update ?? null
        : ctx.energyHealth?.owid_fetched_at ??
          ctx.energyHealth?.last_refresh_at ??
          null;

    const related = (byTheme.get(theme.key) ?? [])
      .filter((id) => id !== entry.kpi_id)
      .slice(0, 6);

    return {
      id: entry.kpi_id,
      name: entry.display_name || entry.kpi_id,
      description: entry.description || "",
      theme: theme.label,
      themeKey: theme.key,
      sourceGroup: group,
      sourceLabel,
      primarySource: entry.primary_source || sourceLabel,
      geography: geo.label,
      geographyKey: geo.key,
      frequency: freq.label,
      frequencyKey: freq.key,
      unit: entry.unit || "",
      chartUnit: toChartUnit(entry.unit || ""),
      valueType: valueTypeFor(entry.calculation_method),
      calculationMethod: entry.calculation_method || "direct",
      status,
      lastRefreshAt,
      latestValue: meta.latestValue,
      latestValueLabel: meta.latestValueLabel,
      latestReferenceDate: meta.latestReferenceDate,
      coverageStart: meta.coverageStart,
      coverageEnd: meta.coverageEnd,
      methodology: entry.calculation_method || "direct",
      caveats: entry.source_caveats || "",
      auditNotes: entry.audit_notes || "",
      verificationStatus: entry.source_verification_status || "",
      higherIsBetter: entry.higher_is_better,
      dashboardPriority: entry.dashboard_priority || "",
      dataQuality: meta.dataQuality,
      relatedIds: related,
    };
  });
}

// ── Faceting / filtering / sorting ──────────────────────────────────────────────

export interface FacetOption {
  key: string;
  label: string;
  count: number;
}

export interface Facets {
  themes: FacetOption[];
  sources: FacetOption[];
  frequencies: FacetOption[];
  geographies: FacetOption[];
  statuses: FacetOption[];
  valueTypes: FacetOption[];
}

export interface ExplorerFilters {
  themes: string[];
  sources: string[];
  frequencies: string[];
  geographies: string[];
  statuses: string[];
  valueTypes: string[];
}

export const EMPTY_FILTERS: ExplorerFilters = {
  themes: [],
  sources: [],
  frequencies: [],
  geographies: [],
  statuses: [],
  valueTypes: [],
};

export function hasActiveFilters(f: ExplorerFilters): boolean {
  return (
    f.themes.length > 0 ||
    f.sources.length > 0 ||
    f.frequencies.length > 0 ||
    f.geographies.length > 0 ||
    f.statuses.length > 0 ||
    f.valueTypes.length > 0
  );
}

function tally(
  records: IndicatorRecord[],
  keyOf: (r: IndicatorRecord) => string,
  labelOf: (r: IndicatorRecord) => string,
): FacetOption[] {
  const counts = new Map<string, { label: string; count: number }>();
  for (const r of records) {
    const key = keyOf(r);
    const existing = counts.get(key);
    if (existing) existing.count += 1;
    else counts.set(key, { label: labelOf(r), count: 1 });
  }
  return [...counts.entries()]
    .map(([key, { label, count }]) => ({ key, label, count }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

const STATUS_LABELS: Record<IndicatorStatus, string> = {
  cached: "Cached",
  stale: "Stale",
  missing: "Not cached",
  failed: "Failed",
  blocked: "Blocked",
};

const VALUE_TYPE_LABELS: Record<IndicatorValueType, string> = {
  raw: "Raw",
  derived: "Derived",
};

export function collectFacets(records: IndicatorRecord[]): Facets {
  return {
    themes: tally(records, (r) => r.themeKey, (r) => r.theme),
    sources: tally(records, (r) => r.sourceLabel, (r) => r.sourceLabel),
    frequencies: tally(records, (r) => r.frequencyKey, (r) => r.frequency),
    geographies: tally(records, (r) => r.geographyKey, (r) => r.geography),
    statuses: tally(records, (r) => r.status, (r) => STATUS_LABELS[r.status]),
    valueTypes: tally(records, (r) => r.valueType, (r) => VALUE_TYPE_LABELS[r.valueType]),
  };
}

export function statusLabel(status: IndicatorStatus): string {
  return STATUS_LABELS[status];
}

export function valueTypeLabel(valueType: IndicatorValueType): string {
  return VALUE_TYPE_LABELS[valueType];
}

function matchesSearch(record: IndicatorRecord, q: string): boolean {
  if (!q) return true;
  const hay = [
    record.name,
    record.id,
    record.description,
    record.theme,
    record.sourceLabel,
    record.primarySource,
    record.geography,
    record.unit,
  ]
    .join(" ")
    .toLowerCase();
  return q
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => hay.includes(term));
}

export function filterRecords(
  records: IndicatorRecord[],
  opts: {
    search: string;
    filters: ExplorerFilters;
    favoritesOnly: boolean;
    isFavorite: (id: string) => boolean;
  },
): IndicatorRecord[] {
  const { search, filters, favoritesOnly, isFavorite } = opts;
  return records.filter((r) => {
    if (favoritesOnly && !isFavorite(r.id)) return false;
    if (filters.themes.length && !filters.themes.includes(r.themeKey)) return false;
    if (filters.sources.length && !filters.sources.includes(r.sourceLabel)) return false;
    if (filters.frequencies.length && !filters.frequencies.includes(r.frequencyKey)) return false;
    if (filters.geographies.length && !filters.geographies.includes(r.geographyKey)) return false;
    if (filters.statuses.length && !filters.statuses.includes(r.status)) return false;
    if (filters.valueTypes.length && !filters.valueTypes.includes(r.valueType)) return false;
    return matchesSearch(r, search);
  });
}

export type SortKey = "name" | "recent" | "source" | "theme" | "status" | "coverage";

export const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: "name", label: "Name (A–Z)" },
  { key: "recent", label: "Most recently updated" },
  { key: "source", label: "Source" },
  { key: "theme", label: "Theme" },
  { key: "status", label: "Cache status" },
  { key: "coverage", label: "Coverage end" },
];

const STATUS_ORDER: Record<IndicatorStatus, number> = {
  cached: 0,
  stale: 1,
  missing: 2,
  failed: 3,
  blocked: 4,
};

export function sortRecords(records: IndicatorRecord[], key: SortKey): IndicatorRecord[] {
  const sorted = [...records];
  switch (key) {
    case "recent":
      sorted.sort((a, b) => (b.lastRefreshAt ?? "").localeCompare(a.lastRefreshAt ?? ""));
      break;
    case "source":
      sorted.sort(
        (a, b) => a.sourceLabel.localeCompare(b.sourceLabel) || a.name.localeCompare(b.name),
      );
      break;
    case "theme":
      sorted.sort((a, b) => a.theme.localeCompare(b.theme) || a.name.localeCompare(b.name));
      break;
    case "status":
      sorted.sort(
        (a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.name.localeCompare(b.name),
      );
      break;
    case "coverage":
      sorted.sort((a, b) => (b.coverageEnd ?? "").localeCompare(a.coverageEnd ?? ""));
      break;
    case "name":
    default:
      sorted.sort((a, b) => a.name.localeCompare(b.name));
      break;
  }
  return sorted;
}
