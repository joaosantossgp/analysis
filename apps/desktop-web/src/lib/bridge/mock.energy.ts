import type {
  BridgeApi,
  CountryKPICompareResponse,
  CountryKPISeriesResponse,
  EnergyKPICatalogResponse,
  EnergyKPIHealthResponse,
  EnergyMartRebuildState,
  EnergyMartStatusResponse,
  FuelDistributionDetailResponse,
  FuelDistributionProductYearSummaryResponse,
  FuelDistributionStateMonthSeriesResponse,
  EnergyKPIRefreshResult,
  PlantParcelCatalogResponse,
  PlantParcelRefreshResult,
  SINKPIHealthResponse,
  SINKPIDailyChartSeriesResponse,
  SINKPISeriesResponse,
} from "./types";
import {
  COUNTRY_NS,
  MOCK_COUNTRY_KPI_VALUES,
  MOCK_KPI_CATALOG,
  MOCK_PLANT_DETAIL,
  MOCK_PLANT_RECORDS,
  MOCK_PLANT_SOURCES,
  MOCK_SIN_DASHBOARD,
  MOCK_SIN_VALUES,
} from "./mockEnergyFixtures";
import { NOW, YEAR } from "./mock.fixtures";

const MOCK_SIN_FREQUENCY_BY_DATASET: Record<string, string> = {
  balanco_energia_subsistema: "hourly",
  ear_diario_subsistema: "daily",
  ena_diario_subsistema: "daily",
  cmo_semihorario: "semi-hourly",
  pld_horario: "hourly",
};

export function createMockEnergyMethods(): Partial<BridgeApi> {
  return {
    get_kpi_catalog: async () => ({
      entries: MOCK_KPI_CATALOG,
      count: MOCK_KPI_CATALOG.length,
    } satisfies EnergyKPICatalogResponse),

    get_country_kpi_series: async (params) => {
      const kpiIds = Array.isArray(params?.kpi_ids) ? new Set(params.kpi_ids) : null;
      const isoCodes = Array.isArray(params?.iso_codes) ? new Set(params.iso_codes) : null;
      const years = Array.isArray(params?.years) ? new Set(params.years.map(Number)) : null;
      const values = MOCK_COUNTRY_KPI_VALUES.filter((row) => {
        if (kpiIds && !kpiIds.has(row.kpi_id)) return false;
        if (isoCodes && !isoCodes.has(row.iso_code)) return false;
        if (years && !years.has(row.period)) return false;
        return true;
      });
      return { values, count: values.length } satisfies CountryKPISeriesResponse;
    },

    get_country_kpi_compare: async (params) => {
      const kpiId = params?.kpi_id ?? `${COUNTRY_NS}.elec_renewables_share`;
      const year = Number(params?.year ?? YEAR - 1);
      const values = MOCK_COUNTRY_KPI_VALUES.filter((row) => row.kpi_id === kpiId && row.period === year);
      return { kpi_id: kpiId, year, values } satisfies CountryKPICompareResponse;
    },

    get_energy_kpi_health: async () => ({
      last_refresh_at: new Date(Date.now() - 3_600_000).toISOString(),
      last_refresh_status: "success",
      rows_ingested: MOCK_COUNTRY_KPI_VALUES.length,
      rows_conflict: 0,
      is_stale: false,
      owid_snapshot_id: "mock-country-energy-snapshot",
      owid_fetched_at: NOW,
      dq_errors: 0,
      dq_warnings: 0,
      refresh_running: false,
      refresh_error: null,
    } satisfies EnergyKPIHealthResponse),

    refresh_energy_kpis: async () => ({
      status: "success",
      error: null,
      run_id: "mock-country-energy-refresh",
      rows_ingested: MOCK_COUNTRY_KPI_VALUES.length,
    } satisfies EnergyKPIRefreshResult),

    export_country_kpis_excel: async () => ({
      path: null,
      error: "Mock bridge does not write Excel exports.",
    }),

    get_sin_kpi_dashboard: async () => MOCK_SIN_DASHBOARD,

    get_sin_kpi_series: async (params) => {
      const p = params as Record<string, unknown> | undefined;
      const kpiIds = Array.isArray(p?.kpi_ids) ? new Set(p?.kpi_ids as string[]) : null;
      const subsystemCodes = Array.isArray(p?.subsystem_codes) ? new Set(p?.subsystem_codes as string[]) : null;
      const values = MOCK_SIN_VALUES.filter((row) => {
        if (kpiIds && !kpiIds.has(row.kpi_id)) return false;
        if (subsystemCodes && !subsystemCodes.has(row.subsystem_code)) return false;
        if (typeof p?.start_datetime === "string" && row.reference_datetime < p.start_datetime) return false;
        if (typeof p?.end_datetime === "string" && row.reference_datetime > p.end_datetime) return false;
        return true;
      });
      return { values, count: values.length } satisfies SINKPISeriesResponse;
    },

    get_sin_kpi_daily_chart_series: async (params) => {
      const p = params as Record<string, unknown> | undefined;
      const kpiIds = Array.isArray(p?.kpi_ids) ? new Set(p?.kpi_ids as string[]) : null;
      const subsystemCodes = Array.isArray(p?.subsystem_codes) ? new Set(p?.subsystem_codes as string[]) : null;
      const startDatetime = typeof p?.start_datetime === "string" ? p.start_datetime : null;
      const endDatetime = typeof p?.end_datetime === "string" ? p.end_datetime : null;
      const request = {
        kpi_ids: kpiIds ? [...kpiIds] : [],
        subsystem_codes: subsystemCodes ? [...subsystemCodes] : [],
        start_datetime: startDatetime,
        end_datetime: endDatetime,
      };
      if (p && Object.prototype.hasOwnProperty.call(p, "limit")) {
        return {
          values: [],
          count: 0,
          raw_row_count: 0,
          request,
          coverage: { start_date: null, end_date: null },
          generated_at: NOW,
          error: "get_sin_kpi_daily_chart_series does not accept limit",
        } satisfies SINKPIDailyChartSeriesResponse;
      }
      const rawValues = MOCK_SIN_VALUES.filter((row) => {
        if (kpiIds && !kpiIds.has(row.kpi_id)) return false;
        if (subsystemCodes && !subsystemCodes.has(row.subsystem_code)) return false;
        if (startDatetime && row.reference_datetime < startDatetime) return false;
        if (endDatetime && row.reference_datetime > endDatetime) return false;
        return true;
      });
      const groups = new Map<string, typeof rawValues>();
      const rawReaderRowCounts = new Map<string, number>();
      for (const row of rawValues) {
        const referenceDate = row.reference_datetime.slice(0, 10);
        const frequency = MOCK_SIN_FREQUENCY_BY_DATASET[row.source_dataset] ?? "unknown";
        const key = [
          row.kpi_id,
          row.subsystem_code,
          referenceDate,
          row.unit,
          frequency,
          row.source,
          row.source_dataset,
          row.source_field,
          row.snapshot_id,
        ].join("|");
        const rawReaderKey = [row.kpi_id, row.subsystem_code, referenceDate].join("|");
        rawReaderRowCounts.set(rawReaderKey, (rawReaderRowCounts.get(rawReaderKey) ?? 0) + 1);
        groups.set(key, [...(groups.get(key) ?? []), row]);
      }
      const values = [...groups.values()].map((rows) => {
        const first = rows[0];
        const usable = rows.filter((row) => row.value !== null);
        const referenceDate = first.reference_datetime.slice(0, 10);
        const dayStart = `${referenceDate}T00:00:00`;
        const dayEnd = `${referenceDate}T23:59:59.999999`;
        const rawReaderKey = [first.kpi_id, first.subsystem_code, referenceDate].join("|");
        return {
          kpi_id: first.kpi_id,
          subsystem_code: first.subsystem_code,
          subsystem_name: first.subsystem_name,
          reference_date: referenceDate,
          value: usable.length > 0
            ? usable.reduce((sum, row) => sum + (row.value ?? 0), 0) / usable.length
            : null,
          unit: first.unit,
          frequency: MOCK_SIN_FREQUENCY_BY_DATASET[first.source_dataset] ?? "unknown",
          raw_row_count: rows.length,
          contributing_observation_count: usable.length,
          sources: [...new Set(rows.map((row) => row.source))],
          source_datasets: [...new Set(rows.map((row) => row.source_dataset))],
          source_fields: [...new Set(rows.map((row) => row.source_field))],
          data_quality_statuses: [...new Set(rows.map((row) => row.data_quality_status))],
          snapshot_ids: [...new Set(rows.map((row) => row.snapshot_id))],
          aggregation: "daily_mean_non_null",
          formula: "mean(normalized_value where normalized_value is not null)",
          calculated_at: NOW,
          raw_drilldown: {
            method: "get_sin_kpi_series",
            kpi_ids: [first.kpi_id],
            subsystem_codes: [first.subsystem_code],
            start_datetime: startDatetime && startDatetime > dayStart ? startDatetime : dayStart,
            end_datetime: endDatetime && endDatetime < dayEnd ? endDatetime : dayEnd,
            unit_context: first.unit,
            raw_reader_row_count: rawReaderRowCounts.get(rawReaderKey) ?? 0,
          },
        };
      });
      return {
        values,
        count: values.length,
        raw_row_count: rawValues.length,
        request,
        coverage: {
          start_date: values.at(0)?.reference_date ?? null,
          end_date: values.at(-1)?.reference_date ?? null,
        },
        generated_at: NOW,
      } satisfies SINKPIDailyChartSeriesResponse;
    },

    get_sin_kpi_health: async () => ({
      last_refresh_at: new Date(Date.now() - 3_600_000).toISOString(),
      last_refresh_status: "partial",
      rows_ingested: MOCK_SIN_VALUES.length,
      latest_reference_datetime: MOCK_SIN_DASHBOARD.latest_reference_datetime,
      is_stale: false,
      dq_errors: 0,
      dq_warnings: 1,
      refresh_running: false,
      refresh_error: null,
    } satisfies SINKPIHealthResponse),

    refresh_sin_kpis: async () => ({
      status: "partial",
      error: null,
      rows_inserted: MOCK_SIN_VALUES.length,
      rows_read: MOCK_SIN_VALUES.length,
      snapshots: 5,
    }),

    get_energy_mart_status: async () => ({
      db_path: "mock://energy_kpis.db",
      db_size_bytes: 36_493_611_008,
      source: {
        table: "ccee_plant_parcel_hourly",
        row_estimate: 75_832_752,
        max_rowid: 75_832_752,
        latest_reference: `${YEAR}-04-30T23:00:00`,
        latest_reference_month: `${YEAR}-04`,
        count_method: "MAX(rowid)",
      },
      marts: {
        plant_parcel_daily_generation_mart: {
          mart_name: "plant_parcel_daily_generation_mart",
          status: "success",
          rebuilt_at: NOW,
          row_count_current: 2_779_986,
          period_start_current: `${YEAR - 2}-03`,
          period_end_current: `${YEAR}-04`,
          period_count_current: 26,
          parcel_count_current: 3991,
          source_observations_current: 66_719_664,
          is_current_for_latest_source_month: true,
        },
        plant_parcel_hourly_preview_mart: {
          mart_name: "plant_parcel_hourly_preview_mart",
          status: "success",
          rebuilt_at: NOW,
          row_count_current: 188_496,
          period_start_current: `${YEAR}-04`,
          period_end_current: `${YEAR}-04`,
          parcel_count_current: 3927,
        },
        plant_parcel_source_submarket_monthly_mart: {
          mart_name: "plant_parcel_source_submarket_monthly_mart",
          status: "success",
          rebuilt_at: NOW,
          row_count_current: 180,
          period_start_current: `${YEAR - 2}-03`,
          period_end_current: `${YEAR}-04`,
          period_count_current: 26,
          generation_source_count_current: 8,
          submarket_count_current: 4,
          grouped_parcel_count_current: 19_200,
          source_observations_current: 66_719_664,
        },
      },
      recommended_daily_rebuild_month: `${YEAR}-04`,
      notes: ["Mock mart status. No local database is modified."],
      rebuild: { status: "idle", error: null },
      write_mode: "read-write",
    } satisfies EnergyMartStatusResponse),

    start_energy_mart_rebuild: async (params) => ({
      status: "success",
      error: null,
      rebuild_id: "mock-energy-mart-rebuild",
      started_at: NOW,
      finished_at: new Date(Date.now() + 250).toISOString(),
      reference_months: params?.reference_month ? [params.reference_month] : null,
      rebuild_daily: params?.rebuild_daily ?? true,
      rebuild_preview: params?.rebuild_preview ?? false,
      rebuild_source_submarket: params?.rebuild_source_submarket ?? true,
      result: {
        build_version: "plant_hourly_marts_v1",
        daily_rows: 117_810,
        preview_rows: params?.rebuild_preview ? 188_496 : null,
        source_submarket_rows: 8,
        elapsed_ms: 250,
      },
    } satisfies EnergyMartRebuildState),

    get_plant_parcel_source_statuses: async () => MOCK_PLANT_SOURCES,

    get_plant_parcel_catalog: async (params) => {
      const p = params as Record<string, unknown> | undefined;
      const search = String(p?.search ?? "").toLowerCase();
      const entityType = String(p?.entity_type ?? "");
      const generationSource = String(p?.generation_source ?? "");
      const submarket = String(p?.submarket ?? "");
      const uf = String(p?.uf ?? "");
      const limit = Number(p?.limit ?? 100);
      const offset = Number(p?.offset ?? 0);
      const records = MOCK_PLANT_RECORDS.filter((row) => {
        if (search) {
          const haystack = [
            row.entity_id,
            row.plant_parcel_code,
            row.plant_parcel_acronym,
            row.ceg,
            row.plant_name,
            row.agent_name,
          ].join(" ").toLowerCase();
          if (!haystack.includes(search)) return false;
        }
        if (entityType && row.entity_type !== entityType) return false;
        if (generationSource && row.generation_source !== generationSource) return false;
        if (submarket && row.submarket !== submarket) return false;
        if (uf && row.uf !== uf) return false;
        return true;
      });
      return {
        records: records.slice(offset, offset + limit),
        count: records.slice(offset, offset + limit).length,
        total: records.length,
        limit,
        offset,
        facets: {
          entity_type: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.entity_type))],
          generation_source: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.generation_source).filter(Boolean))],
          submarket: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.submarket).filter(Boolean))],
          uf: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.uf).filter(Boolean))],
          data_status: [...new Set(MOCK_PLANT_RECORDS.map((r) => r.data_status))],
        },
      } satisfies PlantParcelCatalogResponse;
    },

    get_plant_parcel_detail: async (params) => ({
      ...MOCK_PLANT_DETAIL,
      entity_id: params?.entity_id ?? MOCK_PLANT_DETAIL.entity_id,
    }),

    get_fuel_distribution_product_year_summary: async (params) => {
      const product = String(params?.product ?? "").trim().toUpperCase();
      const startYear = params?.start_year == null ? null : Number(params.start_year);
      const endYear = params?.end_year == null ? null : Number(params.end_year);
      const rows = [
        { source_dataset_id: "anp_fuel_sales_state_month", product: "GASOLINA C", year: YEAR - 1, unit: "m3", total_value: 44_821_000, source_row_count: 324 },
        { source_dataset_id: "anp_fuel_sales_state_month", product: "GASOLINA C", year: YEAR, unit: "m3", total_value: 21_654_000, source_row_count: 162 },
        { source_dataset_id: "anp_diesel_type_state_month", product: "ÓLEO DIESEL", year: YEAR - 1, unit: "m3", total_value: 63_210_000, source_row_count: 324 },
        { source_dataset_id: "anp_ethanol_municipality_year", product: "ETANOL HIDRATADO", year: YEAR - 1, unit: "liters", total_value: 18_940_000_000, source_row_count: 5_102 },
      ].filter((row) => {
        if (product && row.product !== product) return false;
        if (startYear != null && row.year < startYear) return false;
        if (endYear != null && row.year > endYear) return false;
        return true;
      });
      return { source: "sqlite_mart", items: rows, count: rows.length } satisfies FuelDistributionProductYearSummaryResponse;
    },

    get_fuel_distribution_state_month_series: async (params) => {
      const product = String(params?.product ?? "GASOLINA C").trim().toUpperCase() || "GASOLINA C";
      const state = String(params?.state ?? "SÃO PAULO").trim().toUpperCase() || "SÃO PAULO";
      const rows = ["01", "02", "03", "04", "05", "06"].map((month, index) => ({
        source_dataset_id: String(params?.source_dataset_id ?? "anp_fuel_sales_state_month"),
        product,
        reference_period: `${YEAR}-${month}`,
        year: YEAR,
        month: index + 1,
        region: "REGIÃO SUDESTE",
        state,
        unit: "m3",
        total_value: 760_000 + index * 22_500,
        source_row_count: 1,
      }));
      return { source: "sqlite_mart", items: rows, count: rows.length } satisfies FuelDistributionStateMonthSeriesResponse;
    },

    get_fuel_distribution_detail: async (params) => {
      const rows = [
        { reference_period: `${params?.year ?? YEAR}-01`, region: "REGIÃO SUDESTE", state: "SÃO PAULO", municipality: null, product: params?.product ?? "GASOLINA C", unit: "m3", value: 799_343.74, source_dataset_id: params?.source_dataset_id },
        { reference_period: `${params?.year ?? YEAR}-02`, region: "REGIÃO SUDESTE", state: "SÃO PAULO", municipality: null, product: params?.product ?? "GASOLINA C", unit: "m3", value: 812_904.12, source_dataset_id: params?.source_dataset_id },
        { reference_period: `${params?.year ?? YEAR}-03`, region: "REGIÃO SUDESTE", state: "SÃO PAULO", municipality: null, product: params?.product ?? "GASOLINA C", unit: "m3", value: 844_010.52, source_dataset_id: params?.source_dataset_id },
      ];
      return {
        source: "managed_parquet",
        dataset_id: "fuel_distribution_sector_intake",
        source_dataset_id: params?.source_dataset_id,
        product: params?.product,
        year: params?.year,
        rows,
        count: rows.length,
        total_matching_rows: rows.length,
        limit: params?.limit ?? 500,
        offset: params?.offset ?? 0,
        truncated: false,
      } satisfies FuelDistributionDetailResponse;
    },

    get_plant_parcel_chart_data: async (params) => {
      const freq = params.frequency || "monthly";
      if (freq === "monthly") {
        const periods = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"];
        return {
          series: [
            { id: "generation_mwmed", label: "Generation (MWmed)", unit: "number", axis: "left", type: "line", points: [42, 45, 40, 45, 48], latest: 48 },
            { id: "generation_gwh", label: "Generation (GWh)", unit: "number", axis: "left", type: "line", points: [31.2, 30.2, 29.8, 32.4, 35.7], latest: 35.7 },
            { id: "capacity_mw", label: "Capacity (MW)", unit: "number", axis: "right", type: "line", points: [100, 100, 100, 100, 100], latest: 100 },
            { id: "physical_guarantee_mwmed", label: "Physical Guarantee (MWmed)", unit: "number", axis: "right", type: "line", points: [50, 50, 50, 50, 50], latest: 50 },
            { id: "capacity_factor_pct", label: "Capacity Factor (%)", unit: "pct", axis: "left", type: "line", points: [42, 45, 40, 45, 48], latest: 48 }
          ],
          periods,
          frequency: freq,
          entity_type: params.entity_type || "ccee_plant_parcel",
          entity_id: params.entity_id,
        };
      } else if (freq === "daily") {
        const periods = Array.from({ length: 30 }, (_, i) => `2026-05-${String(i + 1).padStart(2, "0")}`);
        const pointsGen = Array.from({ length: 30 }, () => Math.round(40 + Math.random() * 20));
        return {
          series: [
            { id: "generation_mwh", label: "Generation (MWh)", unit: "number", axis: "left", type: "line", points: pointsGen, latest: pointsGen[29] },
            { id: "verified_generation_mwh", label: "Verified Generation ONS (MWh)", unit: "number", axis: "left", type: "line", points: pointsGen.map(p => p - 1), latest: pointsGen[29] - 1 },
            { id: "verified_availability_mwh", label: "Verified Availability (MWh)", unit: "number", axis: "right", type: "line", points: pointsGen.map(() => 98), latest: 98 },
            { id: "unavailability_mwh", label: "Unavailability (MWh)", unit: "number", axis: "right", type: "line", points: pointsGen.map(() => 2), latest: 2 },
            { id: "capacity_factor_pct", label: "Capacity Factor (%)", unit: "pct", axis: "left", type: "line", points: pointsGen.map(p => Math.round((p / 2400) * 100)), latest: Math.round((pointsGen[29] / 2400) * 100) }
          ],
          periods,
          frequency: freq,
          entity_type: params.entity_type || "ccee_plant_parcel",
          entity_id: params.entity_id,
        };
      } else { // hourly
        const periods = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, "0")}h`);
        const pointsGen = Array.from({ length: 24 }, () => Math.round(30 + Math.random() * 40));
        return {
          series: [
            { id: "generation_mwh", label: "Generation (MWh)", unit: "number", axis: "left", type: "line", points: pointsGen, latest: pointsGen[23] },
            { id: "verified_generation_mwh", label: "Verified Generation ONS (MWh)", unit: "number", axis: "left", type: "line", points: pointsGen.map(p => p - 1), latest: pointsGen[23] - 1 },
            { id: "verified_availability_mwh", label: "Verified Availability (MWh)", unit: "number", axis: "right", type: "line", points: pointsGen.map(() => 98), latest: 98 },
            { id: "unavailability_mwh", label: "Unavailability (MWh)", unit: "number", axis: "right", type: "line", points: pointsGen.map(() => 2), latest: 2 },
            { id: "capacity_factor_pct", label: "Capacity Factor (%)", unit: "pct", axis: "left", type: "line", points: pointsGen.map(p => Math.round((p / 100) * 100)), latest: Math.round((pointsGen[23] / 100) * 100) }
          ],
          periods,
          frequency: freq,
          entity_type: params.entity_type || "ccee_plant_parcel",
          entity_id: params.entity_id,
        };
      }
    },

    refresh_plant_parcel_source: async (params) => ({
      status: "success",
      error: null,
      source_id: params?.source_id,
      refresh_id: "mock-plant-refresh",
      rows_inserted: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      rows_read: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      period_start: params?.year_month ?? (params?.year ? `${params.year}-01` : null),
      period_end: params?.year_month ?? (params?.year ? `${params.year}-12` : null),
    } satisfies PlantParcelRefreshResult),

    select_plant_parcel_import_file: async (params) => ({
      ok: true,
      canceled: false,
      file_path: params?.source_id === "ccee_plant_generation_hourly"
        ? "C:\\mock\\geracao_horaria_usina_202605.csv.gz"
        : "C:\\mock\\parcela_usina_montante_mensal_2026.csv",
      file_name: params?.source_id === "ccee_plant_generation_hourly"
        ? "geracao_horaria_usina_202605.csv.gz"
        : "parcela_usina_montante_mensal_2026.csv",
      file_paths: params?.source_id === "ccee_plant_generation_hourly"
        ? ["C:\\mock\\geracao_horaria_usina_202605.csv.gz"]
        : ["C:\\mock\\parcela_usina_montante_mensal_2025.csv", "C:\\mock\\parcela_usina_montante_mensal_2026.csv"],
      file_names: params?.source_id === "ccee_plant_generation_hourly"
        ? ["geracao_horaria_usina_202605.csv.gz"]
        : ["parcela_usina_montante_mensal_2025.csv", "parcela_usina_montante_mensal_2026.csv"],
    }),

    import_plant_parcel_source_file: async (params: any) => ({
      status: "success",
      error: null,
      warning: null,
      source_id: params?.source_id,
      refresh_id: "mock-manual-import",
      import_id: "mock-manual-import",
      import_mode: "manual_file",
      rows_inserted: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      rows_read: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      source_rows: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      parsed_rows: params?.source_id === "ccee_plant_generation_hourly" ? 96 : 2,
      rows_skipped: 0,
      file_size_bytes: params?.source_id === "ccee_plant_generation_hourly" ? 1_048_576 : 4096,
      file_hash: "mock-sha256",
      file_type: params?.source_id === "ccee_plant_generation_hourly" ? "gzip" : "csv",
      original_file_name: params?.original_file_name ?? null,
      requested_period: params?.expected_period ?? null,
      detected_period: params?.source_id === "ccee_plant_generation_hourly" ? "2026-05" : "2026-01..2026-05",
      period_start: params?.expected_period ?? null,
      period_end: params?.expected_period ?? null,
    }),
  };
}
