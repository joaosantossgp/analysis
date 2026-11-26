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
| Curated | Assigned by CVMAnalytics with recorded basis, confidence and evidence; not an official classification | GICS sub-industry per company (`data/curation/gics_curated.csv`, see `reference/gics-import.md`) |
| Estimated/planned | Not implemented or not fully validated | Product workflow ideas, coverage-plan prompts, future methodology templates |

External and unofficial sources must never be described as equivalent to CVM or
B3 official data.

## B3 Sector Classification

Class: official external dataset (source metadata). `src/companies/b3_classification.py`
stores B3's setor / subsetor / segmento for each local company, exactly as B3's
listed-companies service publishes it (by CVM code), with the source URL and
fetch timestamp, in `company_b3_classification`. It is collected only by an
explicit refresh (Settings -> Sources -> "Refresh B3 sectors", bridge method
`refresh_b3_classification`), one request per company. Every run is logged in
`b3_classification_refresh_log` with counts and per-company errors; a failed
company keeps its previous labels. Company reads are offline. Data older than
90 days is marked stale. B3 labels are shown next to the CVM sector as labelled
metadata and are never used as the canonical (GICS) classification.

## CVM Financial Statements

### Company catalog reads and refresh

Company lookups, search, universe previews and coverage reads use local evidence.
They never refresh the CVM company catalog implicitly. The official catalog
snapshot is stored at `metadata/cvm_company_catalog.json` under the configured
data root, preserving the source URL, UTC download timestamp and source CSV.
Cache expiry only re-reads that local file; it does not authorize network access.

A data update ("Download CVM data" / "Update data") refreshes the catalog once
before selecting companies, and the scraper reads the company registry from that
snapshot. An explicit single-company refresh can download a missing
catalog to bootstrap that company. A failed download or invalid response reports
an error and preserves the previous snapshot. Missing local catalog evidence is
reported where needed; existing database rows remain readable. Startup CNPJ
enrichment uses only the downloaded snapshot.

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

Eligible explicit persistent refresh jobs retain only their admitted companies'
annual source rows in the [bounded worker cohort](architecture.md#service-and-coverage-boundaries),
including when only one job is queued. A compatible already-queued second job can
reuse successful annual preparation; unrelated later jobs get a fresh context.
Standalone completion releases the context immediately. Retry and forced-refresh
exclusions remain unchanged.
Existing ZIP freshness checks still run. Reuse requires the same resolved raw
and processed paths, report type and source URL, plus matching ZIP/extracted-file
signatures (file identity, size, modification and change times). Changed or
missing files invalidate the affected entries; failed preparation or parsing
discards the context. Cached company subsets are copied before normalization,
preserving raw value text, versions, periods, units and all existing file families.
This is an in-memory optimization of explicit refresh only: no persistent cache,
read-time network request or change to financial/QA rules is introduced.

Financial statement docs must preserve these distinctions:

- consolidated vs individual;
- DFP annual vs ITR quarterly;
- reported CVM account code and account description vs standardized model
  labels;
- raw reported values vs transformed values;
- units, currency, scale, period labels, and timestamps;
- missing values vs zero values;
- reported values vs calculated KPIs/checks.

### Financial period evidence and conservative QA

`src/financials/periodization.py` selects source durations before creating the
analytical matrix. It retains reported YTD and standalone values separately.
Only compatible additive monetary inputs may be subtracted, using the exact
adjacent cumulative predecessor. Missing inputs, ambiguous versions, reused
account identities and unsupported units produce unavailable cells with QA.
No description-based economic mapping or missing-to-zero substitution is used.
Unit validation also applies to BPA/BPP stocks: absent currency or unknown
scale keeps the raw observation but makes the analytical value unavailable.
DRE `3.99` per-share accounts use reported durations and BRL/share for REAL
filings; annual EPS is neither subtracted nor reconciled by quarterly summation.

The additive persistence contract is:

- `financial_source_observations`: company-scoped observations, original value
  text, filing version, source file, account identity, duration, currency/scale,
  normalized unit and import timestamp. These are retained across refreshes;
  the entire annual CVM corpus is not duplicated in the company database.
- `financial_value_lineage`: analytical cell status, unit, formula and source
  observation IDs, replaced only for explicitly imported statement-years.
- `qa_logs.REPORT_YEAR` and `DETAILS_JSON`: full account/period/source inputs,
  missing inputs, expected/actual/difference where applicable, units and action.
  Existing scalar QA columns remain compatible with older readers.

All three are written with the financial rows in one transaction. Failed writes
roll back; repeated imports preserve source identity and other years' QA.
Source import timestamps describe local ingestion, not a claimed download time.
Previously imported databases have unknown or partial evidence until an explicit
refresh. Normal reads do not repair data or download filings. A successful
refresh and complete statement-package coverage do not certify financial QA.

The statement screen exposes QA even when all analytical cells are excluded.
Its year discovery includes partial ITR and dated QA evidence independently
of annual KPI years and complete-period coverage. An explicit refresh also
invalidates this evidence-year query.
Analytical and ingestion workbooks retain `financial_qa`, `source_observations`
and `value_lineage` audit sheets when evidence is present. See
[`excel-exports.md`](excel-exports.md). The 78-row Vale 2024 regression fixture
in `tests/fixtures/vale_2024_financial_qa.json` records exact offline source rows,
CSV line numbers and source-file hashes; it is not an exhaustive issuer audit.

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

News is retired from the active interface. Existing `/news/*` URLs show a
[retirement notice](../apps/desktop-web/src/App.tsx#L154); the former
`NewsPage.tsx` is not mounted. Saved settings and downloaded data remain, as do
[`src/news/`](../src/news/) and the [News bridge](../desktop/bridge.py#L26).
See [retired News UI](architecture.md#retired-news-ui) for compatibility behavior.

The retained backend collects metadata and, when allowed, readable content from
registered sources. Google News feeds remain aggregator sources, not official
company or regulatory sources. Source reliability and content-storage policy
remain explicit in the [source registry](../src/news/sources.py#L75) and
[collection service](../src/news/service.py#L474). Paywalls must not be bypassed;
the [article fetcher](../src/news/fetcher.py#L258) preserves paywalled/unavailable
states instead of presenting protected content as available.

Coverage still reads [local News workload](../src/companies/coverage.py#L706)
without network calls. Its news-gap evidence remains visible, but the
[News handoffs are unsupported](../apps/desktop-web/src/components/coverage/workQueueHandoffs.ts#L130).
Retaining that data does not restore a News workspace.

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

Storage rules:

- Opening normal analytical views must not trigger hidden external calls.
- Refresh, import, update, and rebuild operations must be explicit, scoped,
  observable, and logged.
- Preserve downloaded files, source snapshots, import metadata, and prior valid
  local state when refreshes fail.
- Prefer bounded UI read models, indexes proven by query plans, caches, and
  rebuildable marts over repeated scans of high-cardinality raw tables.
- Do not add high-cardinality sector detail directly to the main app databases
  when a managed analytical store and compact marts are required.
- New heavy ingestion must define raw snapshot retention, lineage, managed
  storage, bounded read paths, manifests/registration where required,
  telemetry, failure recovery, and release validation.
- Benchmark destructive storage/index/schema changes on a copied database
  first. Keep rollback commands and do not replace a live database without an
  explicit backup-and-swap plan with the app stopped.
- Do not delete raw files or `source_snapshots` merely because a mart or cache
  exists.
- Avoid repeated external calls when local snapshots or caches should serve the
  request.

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

## Interpretation Distinctions

Preserve these distinctions whenever they affect interpretation:

- official CVM/B3 vs official external dataset vs external/unofficial vs user
  import;
- consolidated vs individual statements;
- DFP annual vs ITR quarterly;
- quarterly isolated vs accumulated;
- reported vs transformed vs calculated;
- actual vs estimated or forecast;
- original filing vs restatement;
- recurring vs non-recurring;
- BRL vs thousand BRL vs million BRL and other currencies/scales;
- point-in-time vs period flow;
- source timestamp vs generated timestamp vs as-of date;
- missing value vs zero;
- unavailable vs unsupported vs failed.

Rules:

- Never silently fall back from official data to external data.
- Never present mocks, placeholders, static definitions, or planned data as
  real observations.
- Yahoo Finance/yfinance, Google News, and other aggregators are not equivalent
  to CVM or B3 official data.
- Calculated values must remain traceable through
  `number -> formula/transformation -> source -> company/entity -> period -> unit -> timestamp`.
- EBITDA is not cash. Do not substitute it for operating cash flow or free cash
  flow.
- Financial analysis must preserve the relevant lens: Equity, Credit, IB, DCF,
  multiples, SOTP, project finance, utilities/concessions, or operational
  analysis.
- Missing, partial, stale, invalid, or failed data must remain visible. Do not
  convert missing values to zero to simplify UI logic.
