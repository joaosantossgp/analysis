# Data Sources

## Source Classes

CVMAnalytics must distinguish source reliability and data type explicitly.

| Class | Meaning | Examples |
|---|---|---|
| Official reported | Published by the legal/regulatory source | CVM DFP/ITR statement CSVs from `dados.cvm.gov.br`; B3/CVM identifiers when sourced from official registries |
| Official external dataset | Official source outside CVM statements | ANEEL open data, ONS/CCEE datasets where the module records source metadata |
| External/unofficial | Useful market or context data, not equivalent to CVM/B3 | Yahoo Finance/yfinance market cap and price history, Google News RSS |
| User import | Operator-provided files | Manual source/import workflows and market-cap snapshots |
| Calculated | Derived by CVMAnalytics | KPIs, model formulas, checks, coverage scores, transformed quarterly values |
| Estimated/planned | Not implemented or not fully validated | Product workflow ideas, coverage-plan prompts, future methodology templates |

External and unofficial sources must never be described as equivalent to CVM or
B3 official data.

## CVM Financial Statements

Primary financial statement source:

```text
https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC
```

Verified implementation:

- `src/financials/scraper.py` downloads DFP and ITR yearly ZIPs into the raw
  source directory, extracts CSVs into the processed directory, filters
  `ORDEM_EXERC == "ULTIMO"`, and supports consolidated or individual report
  type.
- `src/refresh/service.py` plans company/year work, runs the scraper, syncs
  refresh status, and persists refresh logs.
- `src/financials/database.py` stores long-form rows in `financial_reports`,
  QA events in `qa_logs`, and company metadata in `companies`.
- `src/financials/read_service.py` is the read-side source of truth for desktop
  and API consumers.

Financial statement docs must preserve these distinctions:

- consolidated vs individual;
- DFP annual vs ITR quarterly;
- reported CVM account code and account description vs standardized model
  labels;
- raw reported values vs transformed values;
- units, currency, scale, period labels, and timestamps;
- missing values vs zero values;
- reported values vs calculated KPIs/checks.

## Market Data

Market cap and price history can use Yahoo Finance/yfinance-backed code paths
or local snapshots. These are external/unofficial sources in this repository.

Verified implementation points:

- `src/platform/settings.py` defaults `CVM_MARKET_CAP_PROVIDER` to
  `yahoo_finance` and accepts deprecated `yfinance` aliases.
- `src/companies/market_cap.py` imports or refreshes market-cap snapshots with
  provider status, source URL/method, as-of date, downloaded timestamp, mapping
  metadata, and warnings.
- `src/companies/market_history.py` stores local market-history observations
  with source/provider status and downloaded timestamps.

Docs and UI must label these as market context, not official financial
statements.

## News Data

The News module collects metadata and, when allowed, readable content from
registered sources. Google News company feeds are aggregator sources, not
official company or regulatory sources.

Verified UI language in `apps/desktop-web/src/routes/NewsPage.tsx` already
states that Google News RSS is treated as aggregator/lower-priority and that
the app does not bypass paywalls.

## Energy And Utility Sources

Energy KPI modules use separate local-first databases and raw-source folders.
Relevant code/docs include:

- `src/energy_kpi/`;
- `src/energy_kpi/distribution/`;
- `docs/reference/energy-utilities-sin-kpis.md`;
- `docs/reference/energy-utilities-distribution.md`;
- `docs/reference/fuel-distribution-source-intake.md`;
- `docs/reference/indicators-module.md`.

These sources are optional segments in Settings health. Missing optional
evidence should be `unknown` or `unavailable`, not `critical`, unless a blocking
error is reported by the module.

CCEE hourly plant-parcel data is kept as auditable local source-derived facts in
`ccee_plant_parcel_hourly`, but default plant chart reads should not aggregate
that large table on demand. The energy schema includes rebuildable marts for the
hot UI path:

- `plant_parcel_daily_generation_mart` serves daily plant/parcel charts.
- `plant_parcel_hourly_preview_mart` serves compact detail previews.
- `plant_ceg_hourly_generation_mart` serves CEG-level hourly drill-downs.
- `plant_parcel_source_submarket_monthly_mart` serves compact diagnostics and
  future filters at source/submarket/month grain.
- `energy_mart_builds` records rebuild version, timestamp, source high-water
  marks, period coverage, row count, and status.

Hourly drill-down remains available only for explicit entity + reference-month +
date-window requests. CEG hourly drill-downs use the CEG mart when rebuilt and
fall back to canonical raw SQLite when needed. Broader daily/monthly views
should use marts or the existing monthly CCEE table. Rebuild existing local
hourly marts with:

```powershell
python scripts/data/rebuild_energy_marts.py --reference-month 2026-04
```

Settings -> Diagnostics also exposes Energy KPI mart status and a scoped action
to rebuild the latest source month's daily mart. This action is write-policy
gated and does not run a full historical rebuild.

Use `--all` only for planned maintenance because it scans the full local hourly
table. The daily mart full rebuild is processed month by month for progress
visibility, but large databases should still be benchmarked on a copy first.
Raw files and `source_snapshots` are not deleted by mart rebuilds.

Fuel Distribution is an implemented Energy managed-ingestion pilot for ANP fuel
sales data. Its current source dossier is
`docs/reference/fuel-distribution-source-intake.md`, and the refresh command is
`python scripts/data/import_fuel_distribution_sources.py`. New fuel-sector
ingestion must use raw snapshots, managed analytical detail storage, explicit
lineage, and compact SQLite marts; it must not add high-cardinality detail rows
directly to the main app databases. Current app-facing reads use
`fuel_distribution_product_year_mart` for overview summaries,
`fuel_distribution_state_month_mart` for bounded trends, and cold Parquet detail
only after the caller supplies source/product/year filters.

The standalone `idx_cppe_ref(reference_datetime)` index is intentionally not
created by the current schema. The raw table primary key already starts with
`reference_datetime`, while guarded hourly drill-down uses
`idx_cppe_parcel_ref(plant_parcel_code, reference_datetime)`. On the June 2026
copy benchmark, removing only `idx_cppe_ref` freed about 2.22 GB of SQLite
pages without regressing representative hot reads. Keep the source and
submarket indexes until their broad diagnostic/filter uses have replacement
marts or directory tables. Rollback is to recreate the index with
`CREATE INDEX idx_cppe_ref ON ccee_plant_parcel_hourly(reference_datetime);`.

Use `scripts/data/compact_energy_db.py` to create a validated compact copy after
index/cache maintenance. The script writes a separate database with SQLite
`VACUUM INTO`, preserves raw/source tables, and does not replace the live
database. Live replacement requires a separate backup-and-swap maintenance step
with the app stopped.

Do not remove `idx_cppe_source` or `idx_cppe_submarket` only because the
source/submarket mart exists. First cut every broad diagnostic/filter read over
to the mart, benchmark on a copied database, and keep a rollback command for the
indexes. The June 2026 copied-DB benchmark showed representative app reads no
longer use those raw-hourly indexes and dropping both would free about 2.67 GB
of SQLite pages before compaction. Raw ad hoc filters by `generation_source` or
`submarket` would become full table scans after removal.

## Storage And Offline Behavior

Default runtime data root:

```text
%USERPROFILE%\Documents\CVMAnalytics
```

Key local artifacts:

- `db/cvm_financials.db`: CVM statements and app tables;
- `db/energy_kpis.db`: energy KPI data;
- `db/news.db`: local news metadata/content database;
- `input/raw` and `input/processed`: CVM source ZIPs and extracted files;
- `cache`: health snapshots, active universe cache, processed presence index;
- `metadata`: source/import metadata and storage inventory;
- `output`: Excel exports and generated outputs;
- `logs`: refresh/update/runtime logs depending on mode.

Offline access means the app can read already-downloaded local data. It does
not mean refresh/update/news/market-data operations work without network access.

## Auditability Requirements

Every significant financial datum should be traceable to:

- source class and provider;
- source URL/file/snapshot when available;
- company identifier (`cd_cvm`, ticker/CNPJ when applicable);
- statement/account/period;
- report type, period type, unit/currency/scale;
- transformation or formula if calculated;
- generated/downloaded/imported timestamp;
- warnings, conflicts, or data-quality status.

Open gaps should be documented as "Needs validation" rather than presented as
implemented guarantees.
