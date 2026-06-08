import type {
  CountryKPIValue,
  KPICatalogEntry,
  PlantParcelCatalogResponse,
  PlantParcelDetailResponse,
  PlantParcelSourceStatusResponse,
  SINKPIDashboardResponse,
  SINKPIObservation,
} from "./types";

const NOW = new Date().toISOString();
const YEAR = new Date().getFullYear();

export const COUNTRY_NS = "energy_utilities.country";
const COUNTRY_FIXTURES = [
  { iso: "BRA", name: "Brazil",         hydro: 58, solar: 6,  wind: 13, nuclear: 2,  gas: 9,  coal: 3,  demand: 620,  carbon: 96,  demandPc: 2800,  ghg: 70,   energyRen: 47, energyFos: 43, ren5y: 5  },
  { iso: "USA", name: "United States",  hydro: 6,  solar: 5,  wind: 11, nuclear: 18, gas: 39, coal: 19, demand: 4300, carbon: 360, demandPc: 12000, ghg: 1500, energyRen: 13, energyFos: 79, ren5y: 8  },
  { iso: "CHN", name: "China",          hydro: 15, solar: 6,  wind: 9,  nuclear: 5,  gas: 3,  coal: 58, demand: 8900, carbon: 560, demandPc: 5800,  ghg: 5000, energyRen: 16, energyFos: 80, ren5y: 12 },
  { iso: "OWEU", name: "EU 27",         hydro: 12, solar: 9,  wind: 17, nuclear: 22, gas: 18, coal: 13, demand: 2800, carbon: 250, demandPc: 5800,  ghg: 900,  energyRen: 23, energyFos: 69, ren5y: 11 },
  { iso: "CHL", name: "Chile",          hydro: 21, solar: 19, wind: 12, nuclear: 0,  gas: 18, coal: 24, demand: 86,   carbon: 310, demandPc: 4300,  ghg: 35,   energyRen: 38, energyFos: 57, ren5y: 18 },
  { iso: "ARG", name: "Argentina",      hydro: 25, solar: 2,  wind: 9,  nuclear: 7,  gas: 50, coal: 2,  demand: 145,  carbon: 330, demandPc: 3800,  ghg: 70,   energyRen: 13, energyFos: 83, ren5y: 7  },
] as const;

const COUNTRY_KPIS = [
  "elec_hydro_share",
  "elec_solar_share",
  "elec_wind_share",
  "elec_nuclear_share",
  "elec_gas_share",
  "elec_coal_share",
  "elec_renewables_share",
  "elec_fossil_share",
  "elec_low_carbon_share",
  "elec_carbon_intensity",
  "elec_demand_total",
  "elec_generation_total",
  "elec_demand_growth_yoy",
  "elec_net_imports_share",
  "elec_demand_per_capita",
  "elec_ghg_emissions",
  "elec_net_imports",
  "energy_renewables_share",
  "energy_fossil_share",
  "elec_renewables_share_5y_chg",
] as const;

function buildMockCountryKpiValues(): CountryKPIValue[] {
  const rows: CountryKPIValue[] = [];
  for (let year = YEAR - 11; year <= YEAR - 1; year += 1) {
    const yearOffset = year - (YEAR - 11);
    for (const [countryIdx, country] of COUNTRY_FIXTURES.entries()) {
      const shift = Math.sin((yearOffset + countryIdx) * 0.7);
      const hydro = clampShare(country.hydro + shift * 2.2 - yearOffset * 0.15);
      const solar = clampShare(country.solar + yearOffset * 0.75 + Math.max(0, shift));
      const wind = clampShare(country.wind + yearOffset * 0.45 + shift * 0.7);
      const nuclear = clampShare(country.nuclear);
      const gas = clampShare(country.gas - yearOffset * 0.18 + shift);
      const coal = clampShare(country.coal - yearOffset * 0.7 - shift);
      const renewables = hydro + solar + wind;
      const fossil = gas + coal;
      const lowCarbon = renewables + nuclear;
      const demand = country.demand * (1 + yearOffset * 0.018 + shift * 0.008);
      const generation = demand * (1 + ([0.01, -0.02, 0.03, -0.01, 0.02, -0.015][countryIdx] ?? 0));
      const growth = 1.2 + shift * 2.4 + countryIdx * 0.2;
      const imports = ((demand - generation) / demand) * 100;
      const carbon = Math.max(35, country.carbon - yearOffset * 8 + shift * 8);
      const demandPc = country.demandPc * (1 + yearOffset * 0.012 + shift * 0.006);
      const ghg = Math.max(10, country.ghg * (1 - yearOffset * 0.015 + shift * 0.01));
      const netImports = demand - generation; // TWh, negative = exporter
      const energyRen = clampShare(country.energyRen + yearOffset * 0.6 + shift * 0.8);
      const energyFos = clampShare(country.energyFos - yearOffset * 0.5 + shift * 0.4);
      const ren5y = country.ren5y + yearOffset * 0.3 + shift * 0.5;
      const valueMap: Record<(typeof COUNTRY_KPIS)[number], number> = {
        elec_hydro_share: hydro,
        elec_solar_share: solar,
        elec_wind_share: wind,
        elec_nuclear_share: nuclear,
        elec_gas_share: gas,
        elec_coal_share: coal,
        elec_renewables_share: renewables,
        elec_fossil_share: fossil,
        elec_low_carbon_share: lowCarbon,
        elec_carbon_intensity: carbon,
        elec_demand_total: demand,
        elec_generation_total: generation,
        elec_demand_growth_yoy: growth,
        elec_net_imports_share: imports,
        elec_demand_per_capita: demandPc,
        elec_ghg_emissions: ghg,
        elec_net_imports: netImports,
        energy_renewables_share: energyRen,
        energy_fossil_share: energyFos,
        elec_renewables_share_5y_chg: ren5y,
      };
      const UNIT_MAP: Record<string, string> = {
        elec_carbon_intensity: "gCO2/kWh",
        elec_demand_total: "TWh", elec_generation_total: "TWh", elec_net_imports: "TWh",
        elec_demand_per_capita: "kWh",
        elec_ghg_emissions: "MtCO2e",
        elec_renewables_share_5y_chg: "pp",
      };
      for (const kpi of COUNTRY_KPIS) {
        const value = Number(valueMap[kpi].toFixed(2));
        const kpiId = `${COUNTRY_NS}.${kpi}`;
        const unit = UNIT_MAP[kpi] ?? (
          kpi.includes("share") || kpi.endsWith("growth_yoy") ? "%" : "TWh"
        );
        rows.push({
          kpi_id: kpiId,
          iso_code: country.iso,
          country_name: country.name,
          period: year,
          value,
          unit,
          source: "mock",
          source_priority: 1,
          source_field: kpi,
          data_quality_status: "ok",
          source_conflict: false,
          fallback_used: false,
          snapshot_id: "mock-country-energy-snapshot",
          value_owid: value,
          value_ember: null,
        });
      }
    }
  }
  return rows;
}

function clampShare(value: number): number {
  return Math.max(0, Math.min(100, value));
}

export const MOCK_COUNTRY_KPI_VALUES = buildMockCountryKpiValues();

// ---------------------------------------------------------------------------
// SIN subsystem KPI fixtures
// ---------------------------------------------------------------------------

const SIN_NS = "energy_utilities.sin";
const SIN_SUBSYSTEMS = [
  { code: "S", name: "South / Sul", color: "#60A5FA" },
  { code: "SE_CO", name: "Southeast-Center West / Sudeste-Centro-Oeste", color: "#22D3EE" },
  { code: "NE", name: "Northeast / Nordeste", color: "#FBBF24" },
  { code: "N", name: "North / Norte", color: "#4ADE80" },
] as const;

const SIN_KPI_META: Record<string, { unit: string; source: string; dataset: string; field: string }> = {
  [`${SIN_NS}.load_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_carga" },
  [`${SIN_NS}.generation_hydro_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gerhidraulica" },
  [`${SIN_NS}.generation_thermal_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gertermica" },
  [`${SIN_NS}.generation_wind_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gereolica" },
  [`${SIN_NS}.generation_solar_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gersolar" },
  [`${SIN_NS}.generation_total_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "derived_total_generation" },
  [`${SIN_NS}.mix_hydro_pct`]: { unit: "%", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gerhidraulica/total" },
  [`${SIN_NS}.mix_thermal_pct`]: { unit: "%", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gertermica/total" },
  [`${SIN_NS}.mix_wind_pct`]: { unit: "%", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gereolica/total" },
  [`${SIN_NS}.mix_solar_pct`]: { unit: "%", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_gersolar/total" },
  [`${SIN_NS}.ear_stored_pct`]: { unit: "%", source: "ONS", dataset: "ear_diario_subsistema", field: "ear_verif_subsistema_percentual" },
  [`${SIN_NS}.ear_stored_mwmes`]: { unit: "MWmes", source: "ONS", dataset: "ear_diario_subsistema", field: "ear_verif_subsistema_mwmes" },
  [`${SIN_NS}.ena_gross_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "ena_diario_subsistema", field: "ena_bruta_regiao_mwmed" },
  [`${SIN_NS}.ena_gross_pct_mlt`]: { unit: "% MLT", source: "ONS", dataset: "ena_diario_subsistema", field: "ena_bruta_regiao_percentualmlt" },
  [`${SIN_NS}.ena_storable_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "ena_diario_subsistema", field: "ena_armazenavel_regiao_mwmed" },
  [`${SIN_NS}.ena_storable_pct_mlt`]: { unit: "% MLT", source: "ONS", dataset: "ena_diario_subsistema", field: "ena_armazenavel_regiao_percentualmlt" },
  [`${SIN_NS}.cmo_brl_mwh`]: { unit: "R$/MWh", source: "ONS", dataset: "cmo_semihorario", field: "val_cmo" },
  [`${SIN_NS}.pld_brl_mwh`]: { unit: "R$/MWh", source: "CCEE", dataset: "pld_horario", field: "PLD_HORA" },
  [`${SIN_NS}.net_interchange_mwmed`]: { unit: "MWmed", source: "ONS", dataset: "balanco_energia_subsistema", field: "val_intercambio" },
};

function buildMockSINValues(): SINKPIObservation[] {
  const rows: SINKPIObservation[] = [];
  const baseBySubsystem: Record<string, number> = { S: 13500, SE_CO: 51500, NE: 13200, N: 7900 };
  for (let day = 13; day >= 0; day -= 1) {
    const date = new Date(Date.now() - day * 86_400_000).toISOString().slice(0, 10) + "T00:00:00";
    for (const [idx, sub] of SIN_SUBSYSTEMS.entries()) {
      const wave = Math.sin((13 - day + idx) * 0.55);
      const load = baseBySubsystem[sub.code] + wave * 900;
      const hydro = load * ([0.46, 0.48, 0.19, 0.68][idx] ?? 0.4);
      const thermal = load * ([0.18, 0.16, 0.07, 0.18][idx] ?? 0.12);
      const wind = load * ([0.10, 0.03, 0.63, 0.04][idx] ?? 0.1);
      const solar = load * ([0.04, 0.05, 0.08, 0.03][idx] ?? 0.04);
      const total = hydro + thermal + wind + solar;
      const valueMap: Record<string, number> = {
        [`${SIN_NS}.load_mwmed`]: load,
        [`${SIN_NS}.generation_hydro_mwmed`]: hydro,
        [`${SIN_NS}.generation_thermal_mwmed`]: thermal,
        [`${SIN_NS}.generation_wind_mwmed`]: wind,
        [`${SIN_NS}.generation_solar_mwmed`]: solar,
        [`${SIN_NS}.generation_total_mwmed`]: total,
        [`${SIN_NS}.mix_hydro_pct`]: hydro / total * 100,
        [`${SIN_NS}.mix_thermal_pct`]: thermal / total * 100,
        [`${SIN_NS}.mix_wind_pct`]: wind / total * 100,
        [`${SIN_NS}.mix_solar_pct`]: solar / total * 100,
        [`${SIN_NS}.ear_stored_pct`]: [72, 64, 48, 77][idx] + wave * 2.5,
        [`${SIN_NS}.ear_stored_mwmes`]: [14500, 128000, 24800, 11800][idx] + wave * 600,
        [`${SIN_NS}.ena_gross_mwmed`]: [8200, 41000, 6400, 9000][idx] + wave * 700,
        [`${SIN_NS}.ena_gross_pct_mlt`]: [92, 84, 57, 103][idx] + wave * 5,
        [`${SIN_NS}.ena_storable_mwmed`]: [6100, 30200, 4700, 6600][idx] + wave * 400,
        [`${SIN_NS}.ena_storable_pct_mlt`]: [72, 65, 44, 87][idx] + wave * 4,
        [`${SIN_NS}.cmo_brl_mwh`]: [148, 152, 144, 155][idx] + wave * 9,
        [`${SIN_NS}.pld_brl_mwh`]: [142, 151, 139, 152][idx] + wave * 7,
        [`${SIN_NS}.net_interchange_mwmed`]: [-850, -4200, 780, 5400][idx] + wave * 350,
      };
      for (const [kpiId, value] of Object.entries(valueMap)) {
        const meta = SIN_KPI_META[kpiId];
        rows.push({
          kpi_id: kpiId,
          subsystem_code: sub.code,
          subsystem_name: sub.name,
          reference_datetime: date,
          value: Number(value.toFixed(2)),
          unit: meta.unit,
          source: meta.source,
          source_dataset: meta.dataset,
          source_field: meta.field,
          data_quality_status: "ok",
          snapshot_id: "mock-sin-snapshot",
        });
      }
    }
  }
  return rows;
}

export const MOCK_SIN_VALUES = buildMockSINValues();

export const MOCK_SIN_DASHBOARD: SINKPIDashboardResponse = {
  last_successful_update: new Date(Date.now() - 3_600_000).toISOString(),
  latest_reference_datetime: MOCK_SIN_VALUES.at(-1)?.reference_datetime ?? null,
  is_empty: false,
  is_stale: false,
  observations: MOCK_SIN_VALUES.filter((row) => row.reference_datetime === MOCK_SIN_VALUES.at(-1)?.reference_datetime),
  source_statuses: [
    { source: "ONS", dataset: "balanco_energia_subsistema", frequency: "hourly", last_snapshot_at: NOW, local_records_count: 6160, last_status: "partial", last_error: null },
    { source: "ONS", dataset: "ear_diario_subsistema", frequency: "daily", last_snapshot_at: NOW, local_records_count: 112, last_status: "partial", last_error: null },
    { source: "ONS", dataset: "ena_diario_subsistema", frequency: "daily", last_snapshot_at: NOW, local_records_count: 224, last_status: "partial", last_error: null },
    { source: "ONS", dataset: "cmo_semihorario", frequency: "semi-hourly", last_snapshot_at: NOW, local_records_count: 1344, last_status: "partial", last_error: null },
    { source: "CCEE", dataset: "pld_horario", frequency: "hourly", last_snapshot_at: NOW, local_records_count: 1344, last_status: "partial", last_error: "Mock partial source note: CCEE can return 403 in some environments." },
  ],
  refresh_running: false,
  refresh_error: null,
};

export const MOCK_PLANT_SOURCES: PlantParcelSourceStatusResponse = {
  source_statuses: [
    {
      source_id: "aneel_siga_plants",
      source_name: "ANEEL SIGA Plants",
      dataset_name: "siga-empreendimentos-geracao.csv",
      provider: "ANEEL",
      official_url: "https://dadosabertos.aneel.gov.br/dataset/siga-sistema-de-informacoes-de-geracao-da-aneel",
      refresh_frequency: "monthly/daily",
      granularity: "CEG plant",
      description: "ANEEL SIGA plant registry and regulatory capacity data.",
      known_caveats: "CEG may map to multiple CCEE plant parcels.",
      local_records_count: 2,
      latest_reference: "2026-06-01",
      last_refresh_at: NOW,
      last_status: "success",
      last_error: null,
      last_import_mode: "automatic_refresh",
      refresh_id: "mock-aneel-refresh",
      cache_status: "fresh",
    },
    {
      source_id: "ccee_plant_parcel_monthly",
      source_name: "CCEE Plant Parcel Monthly",
      dataset_name: "PARCELA_USINA_MONTANTE_MENSAL",
      provider: "CCEE",
      official_url: "https://dadosabertos.ccee.org.br/dataset/parcela_usina_montante_mensal",
      refresh_frequency: "monthly",
      granularity: "plant parcel / month",
      description: "CCEE plant parcel attributes and monthly accounting amounts.",
      known_caveats: "Plant parcels are CCEE accounting entities and are not guaranteed to map 1:1 to ANEEL or ONS plants.",
      local_records_count: 2,
      latest_reference: "2026-05",
      last_refresh_at: NOW,
      last_status: "success",
      last_error: null,
      last_import_mode: "manual_file",
      last_original_file_name: "parcela_usina_montante_mensal_2026.csv",
      last_file_type: "csv",
      last_detected_period: "2026-01..2026-05",
      last_manual_import_at: NOW,
      last_manual_status: "success",
      last_manual_file_name: "parcela_usina_montante_mensal_2026.csv",
      last_manual_file_size_bytes: 4096,
      last_manual_file_hash: "mock-sha256",
      last_manual_file_type: "csv",
      last_manual_detected_period: "2026-01..2026-05",
      last_manual_rows_inserted: 2,
      last_manual_rows_skipped: 0,
      refresh_id: "mock-ccee-monthly-refresh",
      cache_status: "fresh",
    },
    {
      source_id: "ccee_plant_generation_hourly",
      source_name: "CCEE Plant Hourly Generation",
      dataset_name: "GERACAO_HORARIA_USINA",
      provider: "CCEE",
      official_url: "https://dadosabertos.ccee.org.br/dataset/geracao_horaria_usina",
      refresh_frequency: "monthly",
      granularity: "plant parcel / commercialization period",
      description: "CCEE hourly generation by plant parcel and commercialization period.",
      known_caveats: "Hourly files can be large and must be refreshed by selected month.",
      local_records_count: 96,
      latest_reference: "2026-05-02T23:00:00",
      last_refresh_at: NOW,
      last_status: "success",
      last_error: null,
      last_import_mode: "manual_file",
      last_original_file_name: "geracao_horaria_usina_202605.csv.gz",
      last_file_type: "gzip",
      last_detected_period: "2026-05",
      last_manual_import_at: NOW,
      last_manual_status: "success",
      last_manual_file_name: "geracao_horaria_usina_202605.csv.gz",
      last_manual_file_size_bytes: 1_048_576,
      last_manual_file_hash: "mock-sha256",
      last_manual_file_type: "gzip",
      last_manual_detected_period: "2026-05",
      last_manual_rows_inserted: 96,
      last_manual_rows_skipped: 0,
      refresh_id: "mock-ccee-hourly-refresh",
      cache_status: "fresh",
    },
  ],
  count: 3,
  database_path: "[mock] /dev/mock/data/db/energy_kpis.db",
  raw_data_dir: "[mock] /dev/mock/data/raw/energy",
  refresh_running: false,
  refresh_error: null,
  refresh_source_id: null,
};

export const MOCK_PLANT_RECORDS = [
  {
    entity_type: "ccee_plant_parcel",
    entity_id: "1001",
    plant_parcel_code: "1001",
    plant_parcel_acronym: "UHE-TST-1",
    ceg: "CEG123",
    plant_name: "Test Hydro Plant",
    agent_name: "Utility SA",
    generation_source: "Hydraulic",
    submarket: "SE/CO",
    uf: "SP",
    phase: "Operation",
    capacity_mw: 100,
    authorized_capacity_mw: 120,
    inspected_capacity_mw: 110,
    physical_guarantee_mwmed: 55,
    physical_guarantee_mw: 50,
    latest_reference_month: "2026-05",
    latest_generation_mwmed: 48,
    data_status: "cached",
  },
  {
    entity_type: "ccee_plant_parcel",
    entity_id: "2002",
    plant_parcel_code: "2002",
    plant_parcel_acronym: "EOL-TST-2",
    ceg: "CEG456",
    plant_name: "Test Wind Plant",
    agent_name: "WindCo SA",
    generation_source: "Wind",
    submarket: "NE",
    uf: "BA",
    phase: "Operation",
    capacity_mw: 80,
    authorized_capacity_mw: 90,
    inspected_capacity_mw: 82,
    physical_guarantee_mwmed: 30,
    physical_guarantee_mw: 28,
    latest_reference_month: "2026-05",
    latest_generation_mwmed: 32,
    data_status: "cached",
  },
] satisfies PlantParcelCatalogResponse["records"];

export const MOCK_PLANT_DETAIL: PlantParcelDetailResponse = {
  entity_type: "ccee_plant_parcel",
  entity_id: "1001",
  parcel: {
    plant_parcel_code: "1001",
    plant_parcel_acronym: "UHE-TST-1",
    ceg: "CEG123",
    plant_name: "Test Hydro Plant",
    agent_name: "Utility SA",
    submarket: "SE/CO",
    generation_source: "Hydraulic",
    capacity_mw: 100,
    physical_guarantee_mwmed: 55,
    source_reference_month: "2026-05",
  },
  aneel_plant: {
    ceg: "CEG123",
    plant_name: "Test Hydro Plant",
    uf: "SP",
    phase: "Operation",
    authorized_capacity_kw: 120000,
    inspected_capacity_kw: 110000,
  },
  related_parcels: [MOCK_PLANT_RECORDS[0]],
  metrics: [
    {
      metric_id: "capacity_mw",
      label: "Capacity",
      value: 100,
      unit: "MW",
      source_id: "ccee_plant_parcel_monthly",
      source: "CCEE",
      dataset: "CCEE:PARCELA_USINA_MONTANTE_MENSAL",
      reference_period: "2026-05",
      local_refresh_timestamp: NOW,
      raw_or_derived: "raw",
      methodology: "Direct CCEE CAP_T field.",
    },
    {
      metric_id: "generation_center_of_gravity_gwh",
      label: "Generation at Center of Gravity",
      value: 35.7,
      unit: "GWh",
      source_id: "ccee_plant_parcel_monthly",
      source: "CCEE",
      dataset: "CCEE:PARCELA_USINA_MONTANTE_MENSAL",
      reference_period: "2026-05",
      local_refresh_timestamp: NOW,
      raw_or_derived: "derived",
      methodology: "GWh = MWmed * hours_in_month / 1000.",
    },
    {
      metric_id: "capacity_factor_pct",
      label: "Capacity Factor",
      value: 48,
      unit: "%",
      source_id: "ccee_plant_parcel_monthly",
      source: "CCEE",
      dataset: "CCEE:PARCELA_USINA_MONTANTE_MENSAL",
      reference_period: "2026-05",
      local_refresh_timestamp: NOW,
      raw_or_derived: "derived",
      methodology: "Capacity factor = generated MWh / (capacity MW * hours_in_month).",
    },
  ],
  monthly_series: [
    { reference_month: "2026-04", generation_center_of_gravity_mwmed: 45, capacity_mw: 100 },
    { reference_month: "2026-05", generation_center_of_gravity_mwmed: 48, capacity_mw: 100 },
  ],
  hourly_preview: [
    { reference_datetime: "2026-05-02T22:00:00", commercialization_period: 23, generation_center_of_gravity_mwh: 49, verified_generation_ons_mwh: 48 },
    { reference_datetime: "2026-05-02T23:00:00", commercialization_period: 24, generation_center_of_gravity_mwh: 47, verified_generation_ons_mwh: 46 },
  ],
  metadata: {
    caveats: [
      "CCEE plant parcel is not always equivalent to an ANEEL CEG plant or an ONS plant/group.",
      "A CEG can map to multiple CCEE plant parcels.",
    ],
    latest_refresh_by_source: {},
  },
};

// ---------------------------------------------------------------------------
// KPI catalog fixture (dev-only)
//
// Mirrors the backend `kpi_catalog` so the Indicator Explorer renders a
// realistic, fully metadata-tagged catalog under `npm run dev:mock`. This is
// NOT shipped data — the mock module is excluded from production builds by Vite
// dead-code elimination (see adapter.ts).
// ---------------------------------------------------------------------------

const COUNTRY_CAT_META: Record<
  string,
  { name: string; macro: string; unit: string; calc: string; hib: boolean | null; caveat?: string }
> = {
  elec_hydro_share: { name: "Hydro Share of Electricity", macro: "hydro", unit: "%", calc: "direct", hib: null, caveat: "High hydro share = hydrology/drought risk for Brazilian utilities" },
  elec_solar_share: { name: "Solar Share of Electricity", macro: "renewables", unit: "%", calc: "direct", hib: true },
  elec_wind_share: { name: "Wind Share of Electricity", macro: "renewables", unit: "%", calc: "direct", hib: true },
  elec_nuclear_share: { name: "Nuclear Share of Electricity", macro: "nuclear", unit: "%", calc: "direct", hib: null },
  elec_gas_share: { name: "Gas Share of Electricity", macro: "thermal", unit: "%", calc: "direct", hib: false },
  elec_coal_share: { name: "Coal Share of Electricity", macro: "thermal", unit: "%", calc: "direct", hib: false },
  elec_renewables_share: { name: "Renewable Share of Electricity", macro: "renewables", unit: "%", calc: "direct", hib: true, caveat: "OWID uses substitution method; shares comparable across sources" },
  elec_fossil_share: { name: "Fossil Share of Electricity", macro: "fossil_dependence", unit: "%", calc: "direct", hib: false },
  elec_low_carbon_share: { name: "Low-Carbon Share of Electricity", macro: "renewables", unit: "%", calc: "direct", hib: true },
  elec_carbon_intensity: { name: "Carbon Intensity of Electricity", macro: "carbon_intensity", unit: "gCO₂/kWh", calc: "direct", hib: false },
  elec_demand_total: { name: "Total Electricity Demand", macro: "demand", unit: "TWh", calc: "direct", hib: null },
  elec_generation_total: { name: "Total Electricity Generation", macro: "generation", unit: "TWh", calc: "direct", hib: null },
  elec_demand_growth_yoy: { name: "Electricity Demand Growth (YoY)", macro: "demand", unit: "%", calc: "derived_yoy", hib: null, caveat: "Derived locally; OWID revisions shift YoY figures retrospectively" },
  elec_net_imports_share: { name: "Net Imports as % of Demand", macro: "trade", unit: "%", calc: "direct", hib: false },
  elec_demand_per_capita: { name: "Electricity Demand per Capita", macro: "demand", unit: "kWh", calc: "direct", hib: null },
  elec_ghg_emissions: { name: "Power-Sector GHG Emissions", macro: "emissions", unit: "MtCO₂e", calc: "direct", hib: false },
  elec_net_imports: { name: "Net Electricity Imports", macro: "trade", unit: "TWh", calc: "direct", hib: null, caveat: "Negative = net exporter" },
  energy_renewables_share: { name: "Renewable Share of Primary Energy", macro: "energy_mix", unit: "%", calc: "direct", hib: true, caveat: "Energy Institute Statistical Review origin; broader than electricity share" },
  energy_fossil_share: { name: "Fossil Share of Primary Energy", macro: "energy_mix", unit: "%", calc: "direct", hib: false, caveat: "Energy Institute Statistical Review origin" },
  elec_renewables_share_5y_chg: { name: "Renewable Share Δ5y", macro: "transition", unit: "pp", calc: "derived_trend", hib: true, caveat: "Derived; requires ≥5 years of coverage" },
};

const SIN_CAT_META: Record<string, { name: string; macro: string; calc: string }> = {
  load_mwmed: { name: "Load", macro: "load", calc: "direct" },
  generation_hydro_mwmed: { name: "Hydro Generation", macro: "generation", calc: "direct" },
  generation_thermal_mwmed: { name: "Thermal Generation", macro: "generation", calc: "direct" },
  generation_wind_mwmed: { name: "Wind Generation", macro: "generation", calc: "direct" },
  generation_solar_mwmed: { name: "Solar Generation", macro: "generation", calc: "direct" },
  generation_total_mwmed: { name: "Total Generation", macro: "generation", calc: "direct" },
  mix_hydro_pct: { name: "Hydro Mix", macro: "generation_mix", calc: "derived_share" },
  mix_thermal_pct: { name: "Thermal Mix", macro: "generation_mix", calc: "derived_share" },
  mix_wind_pct: { name: "Wind Mix", macro: "generation_mix", calc: "derived_share" },
  mix_solar_pct: { name: "Solar Mix", macro: "generation_mix", calc: "derived_share" },
  ear_stored_pct: { name: "Stored Energy (%)", macro: "reservoirs", calc: "direct" },
  ear_stored_mwmes: { name: "Stored Energy (MWmes)", macro: "reservoirs", calc: "direct" },
  ena_gross_mwmed: { name: "Gross ENA", macro: "hydrology", calc: "direct" },
  ena_gross_pct_mlt: { name: "Gross ENA % MLT", macro: "hydrology", calc: "direct" },
  ena_storable_mwmed: { name: "Storable ENA", macro: "hydrology", calc: "direct" },
  ena_storable_pct_mlt: { name: "Storable ENA % MLT", macro: "hydrology", calc: "direct" },
  cmo_brl_mwh: { name: "CMO", macro: "price", calc: "direct" },
  pld_brl_mwh: { name: "PLD", macro: "price", calc: "direct" },
  net_interchange_mwmed: { name: "Net Interchange", macro: "interchange", calc: "direct" },
};

function buildMockKpiCatalog(): KPICatalogEntry[] {
  const entries: KPICatalogEntry[] = [];
  for (const kpi of COUNTRY_KPIS) {
    const m = COUNTRY_CAT_META[kpi];
    if (!m) continue;
    entries.push({
      kpi_id: `${COUNTRY_NS}.${kpi}`,
      display_name: m.name,
      description: `${m.name} — mock fixture entry.`,
      kpi_type: m.calc === "derived_yoy" ? "growth" : "mix_share",
      macro_category: m.macro,
      subsector: "Electricity Market",
      unit: m.unit,
      primary_source: "OWID",
      calculation_method: m.calc,
      v1_status: "v1_required",
      dashboard_priority: "lead",
      excel_export_priority: "required",
      source_verification_status: "verified",
      higher_is_better: m.hib,
      source_caveats: m.caveat ?? "",
      audit_notes: "",
    });
  }
  for (const [kpiId, meta] of Object.entries(SIN_KPI_META)) {
    const suffix = kpiId.slice(SIN_NS.length + 1);
    const m = SIN_CAT_META[suffix];
    if (!m) continue;
    entries.push({
      kpi_id: kpiId,
      display_name: m.name,
      description: `${m.name} by SIN subsystem — mock fixture entry.`,
      kpi_type: m.macro === "generation_mix" ? "mix_share" : m.macro === "price" ? "price" : "volume",
      macro_category: m.macro,
      subsector: "SIN Subsystems",
      unit: meta.unit,
      primary_source: meta.source,
      calculation_method: m.calc,
      v1_status: "v1_optional",
      dashboard_priority: "lead",
      excel_export_priority: "required",
      source_verification_status: meta.source === "CCEE" ? "pending" : "verified",
      higher_is_better: null,
      source_caveats:
        meta.source === "CCEE" ? "CCEE access may reject direct downloads in some environments." : "",
      audit_notes:
        suffix === "generation_total_mwmed" ? "Derived locally from ONS generation source columns." : "",
    });
  }
  // One blocked entry so the Explorer demonstrates the "blocked" status + filter.
  entries.push({
    kpi_id: `${COUNTRY_NS}.capacity_installed_total`,
    display_name: "Total Installed Capacity",
    description: "Total installed electricity generation capacity (GW).",
    kpi_type: "capacity",
    macro_category: "capacity",
    subsector: "Power Generation",
    unit: "GW",
    primary_source: "EMBER",
    calculation_method: "direct",
    v1_status: "blocked_by_source_verification",
    dashboard_priority: "not_in_v1_dashboard",
    excel_export_priority: "optional",
    source_verification_status: "blocked",
    higher_is_better: null,
    source_caveats: "OWID has no capacity data; Ember field names unverified (key-gated).",
    audit_notes: "Blocked until Ember API key obtained.",
  });
  return entries;
}

export const MOCK_KPI_CATALOG = buildMockKpiCatalog();

// ---------------------------------------------------------------------------
// Onboarding state
// ---------------------------------------------------------------------------
