# Energy Database Profile

- Generated: `2026-06-15T22:14:12Z`
- Database: `C:\Users\jadaojoao\Documents\CVMAnalytics\db\energy_kpis.db`
- Read-only: `True`
- dbstat available: `False`
- File size: `36483608576` bytes

## Top Tables

| Table | Kind | Rows | Table bytes | Index bytes | Total bytes |
|---|---:|---:|---:|---:|---:|
| `ccee_plant_parcel_hourly` | historical_fact | 66719664 | None | None | None |
| `distribution_mmgd_project_snapshots` | snapshot | 3923184 | None | None | None |
| `distribution_mmgd_projects` | metadata | 3923184 | None | None | None |
| `distribution_market_facts` | historical_fact | 1602847 | None | None | None |
| `distribution_continuity_facts` | historical_fact | 1200360 | None | None | None |
| `distribution_delinquency_facts` | historical_fact | 1112622 | None | None | None |
| `distribution_energy_balance_facts` | historical_fact | 982166 | None | None | None |
| `subsystem_kpi_values` | historical_fact | 656184 | None | None | None |
| `distribution_continuity_compensations` | metadata | 544725 | None | None | None |
| `distribution_continuity_limits` | metadata | 435859 | None | None | None |
| `distribution_tariff_facts` | historical_fact | 317309 | None | None | None |
| `ccee_plant_parcel_monthly` | historical_fact | 82458 | None | None | None |
| `distribution_monthly_aggregates` | aggregate | 29466 | None | None | None |
| `aneel_siga_plants` | current_state | 25250 | None | None | None |
| `country_kpi_values` | historical_fact | 11645 | None | None | None |
| `ccee_plant_parcels` | current_state | 4036 | None | None | None |
| `distribution_annual_aggregates` | aggregate | 2583 | None | None | None |
| `distribution_tariff_conflicts` | quality | 2056 | None | None | None |
| `distribution_distributors` | metadata | 179 | None | None | None |
| `distribution_delinquency_indicators` | metadata | 80 | None | None | None |

## Top Indexes

| Index | Table | Columns | Bytes | Overlap candidates |
|---|---|---|---:|---|
| `idx_aneel_siga_source` | `aneel_siga_plants` | generation_source | None |  |
| `idx_aneel_siga_uf` | `aneel_siga_plants` | uf | None |  |
| `idx_cdr_dataset_period` | `ccee_discovered_resources` | dataset_id, year, month | None |  |
| `idx_cppe_parcel_ref` | `ccee_plant_parcel_hourly` | plant_parcel_code, reference_datetime | None |  |
| `idx_cppe_ref` | `ccee_plant_parcel_hourly` | reference_datetime | None |  |
| `idx_cppe_ref_month` | `ccee_plant_parcel_hourly` | reference_month | None |  |
| `idx_cppe_source` | `ccee_plant_parcel_hourly` | generation_source | None |  |
| `idx_cppe_submarket` | `ccee_plant_parcel_hourly` | submarket | None |  |
| `idx_cppm_ceg` | `ccee_plant_parcel_monthly` | ceg | None |  |
| `idx_cppm_parcel_ref` | `ccee_plant_parcel_monthly` | plant_parcel_code, reference_month | None |  |
| `idx_cppm_ref` | `ccee_plant_parcel_monthly` | reference_month | None |  |
| `idx_cppm_source` | `ccee_plant_parcel_monthly` | generation_source | None |  |
| `idx_cppm_submarket` | `ccee_plant_parcel_monthly` | submarket | None |  |
| `idx_cpp_ceg` | `ccee_plant_parcels` | ceg | None |  |
| `idx_cpp_ref_month` | `ccee_plant_parcels` | source_reference_month | None |  |
| `idx_cpp_source` | `ccee_plant_parcels` | generation_source | None |  |
| `idx_cpp_submarket` | `ccee_plant_parcels` | submarket | None |  |
| `idx_ckv_iso_period` | `country_kpi_values` | iso_code, period | None |  |
| `idx_ckv_kpi_iso` | `country_kpi_values` | kpi_id, iso_code | None |  |
| `idx_ckv_snapshot` | `country_kpi_values` | snapshot_id | None |  |
| `idx_dqc_run` | `data_quality_checks` | run_id | None |  |
| `idx_dist_annual_agg` | `distribution_annual_aggregates` | distributor_id, reference_year | None |  |
| `idx_dist_cont_indicator_ref` | `distribution_continuity_facts` | indicator_code, distributor_id, reference_month | None |  |
| `idx_dist_cont_ref` | `distribution_continuity_facts` | distributor_id, set_id, reference_month | None |  |
| `idx_dist_bal_ref` | `distribution_energy_balance_facts` | distributor_id, reference_month | None |  |
| `idx_dist_market_ref` | `distribution_market_facts` | distributor_id, reference_month | None |  |
| `idx_dist_mmgd_snap` | `distribution_mmgd_project_snapshots` | project_id, reference_month | None |  |
| `idx_dist_mmgd_proj` | `distribution_mmgd_projects` | distributor_id | None |  |
| `idx_dist_monthly_agg` | `distribution_monthly_aggregates` | distributor_id, reference_month | None |  |
| `idx_dist_tariff_series_lookup` | `distribution_tariff_facts` | distributor_id, subgroup, consumer_class, unit, valid_from, valid_to | None |  |

## Query Profiles

| Query | Owner | Rows | Elapsed ms | Plan |
|---|---|---:|---:|---|
| `plant_parcel_detail_latest` | EnergyKPIReadService.get_plant_parcel_detail | 1 | 0.69 | SEARCH ccee_plant_parcels USING INDEX sqlite_autoindex_ccee_plant_parcels_1 (plant_parcel_code=?)<br>SCALAR SUBQUERY 1<br>SCAN ccee_plant_parcels USING COVERING INDEX sqlite_autoindex_ccee_plant_parcels_1 |
| `plant_monthly_series_by_parcel` | EnergyKPIReadService.get_plant_parcel_chart_data monthly | 16 | 5.76 | SEARCH ccee_plant_parcel_monthly USING INDEX idx_cppm_parcel_ref (plant_parcel_code=?)<br>SCALAR SUBQUERY 1<br>SCAN ccee_plant_parcel_monthly USING COVERING INDEX idx_cppm_parcel_ref |
| `plant_hourly_series_by_parcel_month` | EnergyKPIReadService.get_plant_parcel_chart_data hourly | 0 | 3187.29 | SEARCH ccee_plant_parcel_hourly USING INDEX idx_cppe_parcel_ref (plant_parcel_code=?)<br>SCALAR SUBQUERY 1<br>SCAN ccee_plant_parcel_hourly USING COVERING INDEX idx_cppe_parcel_ref<br>SCALAR SUBQUERY 2<br>SCAN ccee_plant_parcel_hourly USING COVERING INDEX idx_cppe_ref_month<br>USE TEMP B-TREE FOR RIGHT PART OF ORDER BY |
| `sin_latest_reference` | EnergyKPIReadService.get_sin_kpi_health | 1 | 60.02 | SEARCH subsystem_kpi_values USING COVERING INDEX idx_skv_dataset_ref |
| `distribution_distributor_series` | DistributionReadService.get_series | 42456 | 1202.88 | SEARCH distribution_market_facts USING INDEX idx_dist_market_ref (distributor_id=?)<br>SCALAR SUBQUERY 1<br>SCAN distribution_market_facts USING COVERING INDEX idx_dist_market_ref |
