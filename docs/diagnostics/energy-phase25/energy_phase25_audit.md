# Energy Database Phase 2.5 Audit

- Generated: `2026-06-15T23:34:46Z`
- Production database: `C:\Users\jadaojoao\Documents\CVMAnalytics\db\energy_kpis.db`
- Production unchanged: `False`
- SQLite dbstat tool: `C:\Users\jadaojoao\AppData\Local\Temp\cvma_sqlite_tools_3530200\sqlite3.exe`

## Exact Hourly Attribution

- Table bytes: `19384414208`
- Index bytes: `12111360000`
- Total bytes: `31495774208`
- Rows: `66719664`
- Table bytes per row: `290.5352492182814`
- Total bytes per row: `472.06134323458224`

## Top Tables

| Table | Rows | Table bytes | Index bytes | Total bytes |
|---|---:|---:|---:|---:|
| `ccee_plant_parcel_hourly` | 66719664 | 19384414208 | 12111360000 | 31495774208 |
| `distribution_market_facts` | 1602847 | 831692800 | 165064704 | 996757504 |
| `distribution_mmgd_project_snapshots` | 3923184 | 621105152 | 352116736 | 973221888 |
| `distribution_mmgd_projects` | 3923184 | 678322176 | 211353600 | 889675776 |
| `distribution_delinquency_facts` | 1112622 | 303476736 | 121868288 | 425345024 |
| `distribution_continuity_facts` | 1200360 | 260747264 | 157351936 | 418099200 |
| `subsystem_kpi_values` | 656184 | 221843456 | 146866176 | 368709632 |
| `distribution_energy_balance_facts` | 982166 | 268144640 | 92884992 | 361029632 |
| `distribution_tariff_facts` | 317309 | 148381696 | 57487360 | 205869056 |
| `distribution_continuity_compensations` | 544725 | 121786368 | 28749824 | 150536192 |
| `distribution_continuity_limits` | 435859 | 92450816 | 23150592 | 115601408 |
| `ccee_plant_parcel_monthly` | 82458 | 43757568 | 12066816 | 55824384 |

## Top Indexes

| Index | Table | Columns | Bytes |
|---|---|---|---:|
| `sqlite_autoindex_ccee_plant_parcel_hourly_1` | `ccee_plant_parcel_hourly` | reference_datetime, commercialization_period, plant_parcel_code | 2938433536 |
| `idx_cppe_parcel_ref` | `ccee_plant_parcel_hourly` | plant_parcel_code, reference_datetime | 2650116096 |
| `idx_cppe_ref` | `ccee_plant_parcel_hourly` | reference_datetime | 2221072384 |
| `idx_cppe_source` | `ccee_plant_parcel_hourly` | generation_source | 1740898304 |
| `idx_cppe_ref_month` | `ccee_plant_parcel_hourly` | reference_month | 1299099648 |
| `idx_cppe_submarket` | `ccee_plant_parcel_hourly` | submarket | 1261740032 |
| `sqlite_autoindex_distribution_mmgd_project_snapshots_1` | `distribution_mmgd_project_snapshots` | snapshot_row_id | 203587584 |
| `idx_dist_mmgd_snap` | `distribution_mmgd_project_snapshots` | project_id, reference_month | 148529152 |
| `sqlite_autoindex_distribution_delinquency_facts_1` | `distribution_delinquency_facts` | fact_id | 121868288 |
| `sqlite_autoindex_distribution_mmgd_projects_1` | `distribution_mmgd_projects` | project_id | 113209344 |
| `idx_dist_mmgd_proj` | `distribution_mmgd_projects` | distributor_id | 98144256 |
| `sqlite_autoindex_distribution_market_facts_1` | `distribution_market_facts` | fact_id | 88428544 |

## SQLite Experiments
- `current`: size `53440512`, index build `0.00` ms
  - `one_parcel_one_month`: median `7.80` ms, p95 `26.05` ms, rows `720`
  - `one_parcel_multi_month`: median `7.60` ms, p95 `7.96` ms, rows `2184`
  - `several_parcels_one_month`: median `26.62` ms, p95 `49.08` ms, rows `7200`
  - `aggregate_by_month`: median `108.72` ms, p95 `113.21` ms, rows `43`
  - `latest_reference`: median `0.03` ms, p95 `0.12` ms, rows `1`
  - `available_periods`: median `4.75` ms, p95 `5.89` ms, rows `3`
- `candidate_composite`: size `58728448`, index build `990.99` ms
  - `one_parcel_one_month`: median `3.68` ms, p95 `4.03` ms, rows `720`
  - `one_parcel_multi_month`: median `8.18` ms, p95 `11.57` ms, rows `2184`
  - `several_parcels_one_month`: median `34.64` ms, p95 `37.97` ms, rows `7200`
  - `aggregate_by_month`: median `106.77` ms, p95 `108.05` ms, rows `43`
  - `latest_reference`: median `0.03` ms, p95 `0.10` ms, rows `1`
  - `available_periods`: median `4.80` ms, p95 `6.44` ms, rows `3`
- `candidate_drop_overlap`: size `54747136`, index build `698.15` ms
  - `one_parcel_one_month`: median `3.43` ms, p95 `3.84` ms, rows `720`
  - `one_parcel_multi_month`: median `7.43` ms, p95 `8.06` ms, rows `2184`
  - `several_parcels_one_month`: median `35.36` ms, p95 `35.47` ms, rows `7200`
  - `aggregate_by_month`: median `115.49` ms, p95 `128.21` ms, rows `43`
  - `latest_reference`: median `0.03` ms, p95 `0.10` ms, rows `1`
  - `available_periods`: median `4.80` ms, p95 `5.93` ms, rows `3`

## Parquet Experiments
- `year_month` / `snappy`: `8857455` bytes, files `3`, write `96.24` ms
- `year_month` / `zstd`: `4958731` bytes, files `3`, write `71.86` ms
- `reference_month` / `snappy`: `8858568` bytes, files `3`, write `59.25` ms
- `reference_month` / `zstd`: `4959945` bytes, files `3`, write `72.12` ms
- `reference_month_source_dataset` / `snappy`: `8856440` bytes, files `3`, write `58.48` ms
- `reference_month_source_dataset` / `zstd`: `4957714` bytes, files `3`, write `65.75` ms
