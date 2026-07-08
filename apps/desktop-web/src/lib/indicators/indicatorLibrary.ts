import type { IndicatorRecord } from "./registry";

export type IndicatorLibrarySection = "energy" | "entities" | "health" | "exports";
export type IndicatorLibraryEnergySub = "distribution" | "generation" | "fuel" | "sin" | "matrix";

export type IndicatorLibraryAction =
  | { type: "energy"; sub: IndicatorLibraryEnergySub; label: string }
  | { type: "section"; section: IndicatorLibrarySection; label: string }
  | { type: "hash"; href: string; label: string };

export type IndicatorLibraryPreviewKind =
  | "country-kpi"
  | "sin-kpi"
  | "none";

export type IndicatorLibraryScopeLevel = "global" | "system" | "sector";

export type IndicatorLibraryRow = {
  id: string;
  name: string;
  domain: string;
  scope: string;
  source: string;
  unit: string;
  period: string;
  valueType: string;
  status: string;
  description: string;
  scopeLevel: IndicatorLibraryScopeLevel;
  requiresEntityContext: false;
  catalogBacked: boolean;
  action: IndicatorLibraryAction;
  sourceRecordId?: string;
  sourceGroup?: IndicatorRecord["sourceGroup"];
  previewKind: IndicatorLibraryPreviewKind;
  exportKind: "country-kpi-excel" | "none";
  exportUnavailableReason?: string;
  lastRefreshAt?: string | null;
  coverageStart?: string | null;
  coverageEnd?: string | null;
  dataQuality?: string | null;
  latestValue?: number | null;
  latestReferenceDate?: string | null;
  latestValueLabel?: string | null;
};

export type IndicatorLibraryFilterKey = "domains" | "sources" | "units" | "valueTypes" | "statuses";

export type IndicatorLibraryFilters = Record<IndicatorLibraryFilterKey, string[]>;

export type IndicatorLibraryFacetOption = {
  key: string;
  label: string;
  count: number;
};

export type IndicatorLibraryFacets = Record<IndicatorLibraryFilterKey, IndicatorLibraryFacetOption[]>;

export const EMPTY_INDICATOR_LIBRARY_FILTERS: IndicatorLibraryFilters = {
  domains: [],
  sources: [],
  units: [],
  valueTypes: [],
  statuses: [],
};

function catalogStatusLabel(status: IndicatorRecord["status"]): string {
  if (status === "cached") return "Cached";
  if (status === "stale") return "Stale";
  if (status === "missing") return "Missing data";
  if (status === "failed") return "Source issue";
  if (status === "blocked") return "Blocked";
  return "Available";
}

const openPowerSystem: IndicatorLibraryAction = { type: "energy", sub: "sin", label: "Open Power System" };
const openMatrix: IndicatorLibraryAction = { type: "energy", sub: "matrix", label: "Open Matrix & Trends" };

const SIN_FALLBACK_INDICATORS: Array<{
  id: string;
  name: string;
  unit: string;
  category: string;
}> = [
  { id: "energy_utilities.sin.load_mwmed", name: "Load", unit: "MWmed", category: "Load" },
  { id: "energy_utilities.sin.generation_hydro_mwmed", name: "Hydro generation", unit: "MWmed", category: "Generation" },
  { id: "energy_utilities.sin.generation_thermal_mwmed", name: "Thermal generation", unit: "MWmed", category: "Generation" },
  { id: "energy_utilities.sin.generation_wind_mwmed", name: "Wind generation", unit: "MWmed", category: "Generation" },
  { id: "energy_utilities.sin.generation_solar_mwmed", name: "Solar generation", unit: "MWmed", category: "Generation" },
  { id: "energy_utilities.sin.generation_total_mwmed", name: "Total generation", unit: "MWmed", category: "Generation" },
  { id: "energy_utilities.sin.mix_hydro_pct", name: "Hydro mix", unit: "%", category: "Generation mix" },
  { id: "energy_utilities.sin.mix_thermal_pct", name: "Thermal mix", unit: "%", category: "Generation mix" },
  { id: "energy_utilities.sin.mix_wind_pct", name: "Wind mix", unit: "%", category: "Generation mix" },
  { id: "energy_utilities.sin.mix_solar_pct", name: "Solar mix", unit: "%", category: "Generation mix" },
  { id: "energy_utilities.sin.ear_stored_mwmes", name: "Stored energy", unit: "MWmes", category: "Reservoirs" },
  { id: "energy_utilities.sin.ear_stored_pct", name: "Stored energy", unit: "%", category: "Reservoirs" },
  { id: "energy_utilities.sin.ena_gross_mwmed", name: "Gross ENA", unit: "MWmed", category: "Hydrology" },
  { id: "energy_utilities.sin.ena_gross_pct_mlt", name: "Gross ENA % MLT", unit: "%", category: "Hydrology" },
  { id: "energy_utilities.sin.ena_storable_mwmed", name: "Storable ENA", unit: "MWmed", category: "Hydrology" },
  { id: "energy_utilities.sin.ena_storable_pct_mlt", name: "Storable ENA % MLT", unit: "%", category: "Hydrology" },
  { id: "energy_utilities.sin.cmo_brl_mwh", name: "CMO", unit: "R$/MWh", category: "Prices" },
  { id: "energy_utilities.sin.pld_brl_mwh", name: "PLD", unit: "R$/MWh", category: "Prices" },
  { id: "energy_utilities.sin.net_interchange_mwmed", name: "Net interchange", unit: "MWmed", category: "Trade" },
];

const COUNTRY_FALLBACK_INDICATORS: Array<{
  id: string;
  name: string;
  unit: string;
  category: string;
}> = [
  { id: "energy_utilities.country.elec_renewables_share", name: "Renewable share", unit: "%", category: "Electricity mix" },
  { id: "energy_utilities.country.elec_fossil_share", name: "Fossil share", unit: "%", category: "Electricity mix" },
  { id: "energy_utilities.country.elec_low_carbon_share", name: "Low-carbon share", unit: "%", category: "Electricity mix" },
  { id: "energy_utilities.country.elec_hydro_share", name: "Hydro share", unit: "%", category: "Electricity mix" },
  { id: "energy_utilities.country.elec_solar_share", name: "Solar share", unit: "%", category: "Electricity mix" },
  { id: "energy_utilities.country.elec_wind_share", name: "Wind share", unit: "%", category: "Electricity mix" },
  { id: "energy_utilities.country.elec_nuclear_share", name: "Nuclear share", unit: "%", category: "Electricity mix" },
  { id: "energy_utilities.country.elec_gas_share", name: "Gas share", unit: "%", category: "Electricity mix" },
  { id: "energy_utilities.country.elec_coal_share", name: "Coal share", unit: "%", category: "Electricity mix" },
  { id: "energy_utilities.country.elec_carbon_intensity", name: "Carbon intensity", unit: "gCO2/kWh", category: "Emissions" },
  { id: "energy_utilities.country.elec_demand_total", name: "Electricity demand", unit: "TWh", category: "Demand" },
  { id: "energy_utilities.country.elec_generation_total", name: "Electricity generation", unit: "TWh", category: "Generation" },
  { id: "energy_utilities.country.elec_demand_growth_yoy", name: "Demand growth YoY", unit: "%", category: "Demand" },
  { id: "energy_utilities.country.elec_net_imports_share", name: "Net imports share", unit: "%", category: "Trade" },
];

export const INDICATOR_LIBRARY_STATIC_ROWS: IndicatorLibraryRow[] = [
  ...SIN_FALLBACK_INDICATORS.map((indicator) => ({
    id: `catalog.${indicator.id}`,
    name: indicator.name,
    domain: "Energy / Power System",
    scope: "System / subsystem",
    source: "ONS / CCEE",
    unit: indicator.unit,
    period: "Daily / intraday",
    valueType: "Reported / imported",
    status: "Definition",
    description: `${indicator.category}: system or subsystem operating series.`,
    scopeLevel: "system" as const,
    requiresEntityContext: false as const,
    catalogBacked: false,
    action: openPowerSystem,
    previewKind: "none" as const,
    exportKind: "none" as const,
    exportUnavailableReason: "No Indicator Library export is exposed for SIN indicators yet.",
  })),
  ...COUNTRY_FALLBACK_INDICATORS.map((indicator) => ({
    id: `catalog.${indicator.id}`,
    name: indicator.name,
    domain: "Energy / Matrix & Trends",
    scope: "Country",
    source: "OWID / Ember",
    unit: indicator.unit,
    period: "Annual",
    valueType: "Reported / calculated",
    status: "Definition",
    description: `${indicator.category}: country-level annual energy or electricity series.`,
    scopeLevel: "global" as const,
    requiresEntityContext: false as const,
    catalogBacked: false,
    action: openMatrix,
    previewKind: "none" as const,
    exportKind: "none" as const,
    exportUnavailableReason: "No cached catalog record is available for this indicator in the library.",
  })),
];

export function buildIndicatorLibraryRows(records: IndicatorRecord[]): IndicatorLibraryRow[] {
  const catalogRows = records.map((record) => {
    const isSin = record.sourceGroup === "sin";
    return {
      id: `catalog.${record.id}`,
      name: record.name,
      domain: isSin ? "Energy / Power System" : "Energy / Matrix & Trends",
      scope: record.geography || "Catalog geography",
      source: record.primarySource || record.sourceLabel || "Catalog source",
      unit: record.unit || "Unavailable",
      period: record.frequency || "Unavailable",
      valueType: record.valueType === "derived" ? "Calculated" : "Reported / imported",
      status: catalogStatusLabel(record.status),
      description: record.description || record.methodology || "Catalog metadata record.",
      scopeLevel: isSin ? "system" : "global",
      requiresEntityContext: false,
      catalogBacked: true,
      action: isSin ? openPowerSystem : openMatrix,
      sourceRecordId: record.id,
      sourceGroup: record.sourceGroup,
      previewKind: isSin ? "sin-kpi" : "country-kpi",
      exportKind: isSin ? "none" : "country-kpi-excel",
      exportUnavailableReason: isSin ? "No Indicator Library export is exposed for SIN indicators yet." : undefined,
      lastRefreshAt: record.lastRefreshAt,
      coverageStart: record.coverageStart,
      coverageEnd: record.coverageEnd,
      dataQuality: record.dataQuality,
      latestValue: record.latestValue,
      latestReferenceDate: record.latestReferenceDate,
      latestValueLabel: record.latestValueLabel,
    } satisfies IndicatorLibraryRow;
  });

  const byId = new Map<string, IndicatorLibraryRow>();
  for (const row of INDICATOR_LIBRARY_STATIC_ROWS) byId.set(row.id, row);
  for (const row of catalogRows) byId.set(row.id, row);

  return [...byId.values()].filter(isIndicatorLibraryEligible).sort((a, b) => {
    const domainCompare = a.domain.localeCompare(b.domain);
    if (domainCompare !== 0) return domainCompare;
    return a.name.localeCompare(b.name);
  });
}

export function isIndicatorLibraryEligible(row: IndicatorLibraryRow): boolean {
  return row.requiresEntityContext === false;
}

export function indicatorLibraryFavoriteKey(row: IndicatorLibraryRow): string {
  return row.sourceRecordId ?? row.id;
}

export function resolveIndicatorLibrarySelection(currentId: string | null, clickedId: string): string | null {
  return currentId === clickedId ? null : clickedId;
}

export function isCountryKpiLibraryRow(row: IndicatorLibraryRow): boolean {
  return row.exportKind === "country-kpi-excel" && Boolean(row.sourceRecordId);
}

export function hasActiveIndicatorLibraryFilters(filters: IndicatorLibraryFilters): boolean {
  return Object.values(filters).some((items) => items.length > 0);
}

export function collectIndicatorLibraryFacets(rows: IndicatorLibraryRow[]): IndicatorLibraryFacets {
  return {
    domains: tallyFacet(rows, (row) => row.domain),
    sources: tallyFacet(rows, (row) => row.source),
    units: tallyFacet(rows, (row) => row.unit),
    valueTypes: tallyFacet(rows, (row) => row.valueType),
    statuses: tallyFacet(rows, (row) => row.status),
  };
}

export function filterIndicatorLibraryRows(
  rows: IndicatorLibraryRow[],
  opts: {
    search: string;
    filters: IndicatorLibraryFilters;
    favoritesOnly: boolean;
    isFavorite: (id: string) => boolean;
  },
): IndicatorLibraryRow[] {
  const needle = opts.search.trim().toLowerCase();
  return rows.filter((row) => {
    if (opts.favoritesOnly && !opts.isFavorite(indicatorLibraryFavoriteKey(row))) return false;
    if (opts.filters.domains.length > 0 && !opts.filters.domains.includes(row.domain)) return false;
    if (opts.filters.sources.length > 0 && !opts.filters.sources.includes(row.source)) return false;
    if (opts.filters.units.length > 0 && !opts.filters.units.includes(row.unit)) return false;
    if (opts.filters.valueTypes.length > 0 && !opts.filters.valueTypes.includes(row.valueType)) return false;
    if (opts.filters.statuses.length > 0 && !opts.filters.statuses.includes(row.status)) return false;
    if (!needle) return true;
    return [
      row.id,
      row.name,
      row.description,
      row.domain,
      row.scope,
      row.source,
      row.unit,
      row.period,
      row.valueType,
      row.status,
    ]
      .join(" ")
      .toLowerCase()
      .includes(needle);
  });
}

function tallyFacet(
  rows: IndicatorLibraryRow[],
  getValue: (row: IndicatorLibraryRow) => string,
): IndicatorLibraryFacetOption[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const value = getValue(row) || "Unavailable";
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ key: label, label, count }))
    .sort((a, b) => a.label.localeCompare(b.label));
}
