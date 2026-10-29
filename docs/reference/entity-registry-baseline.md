# Entity Registry Baseline

> **Withdrawn (2026-10-29).** The Canonical Entity Registry epic (#413) and its
> v0.31.0 release plan were closed as not planned during a backlog reset. This
> record is kept for reference only. It is not an active contract and does not
> authorize or require any work. See `docs/STATUS.md`.

Source-bound dossier for issue #414. Verified at commit
`e41855e6fac3f69aa2443752364537870c67cf53` on 2026-07-29 (local worktree
and `origin/main` both resolved to that SHA). This is a current-state record,
not a data-model proposal. Any later implementation must diff its target SHA
against this one.

## Executive boundary

The packaged product is the Vite SPA in `apps/desktop-web`, served by the
pywebview runtime (`desktop/app.py`), which exposes `CVMBridge` through
`window.pywebview.api`. `desktop/bridge.py:20-29` composes the public bridge
from domain mixins; the typed UI mirror is
`apps/desktop-web/src/lib/bridge/types.ts` (see `docs/architecture.md:33-47`).
`apps/api` is an active FastAPI HTTP adapter for development/hosted access, not
the packaged UI.

Runtime data is local to `%USERPROFILE%\\Documents\\CVMAnalytics` unless
overridden; it remains readable offline after download. This baseline does not
prove clean-machine packaged behavior, which `docs/architecture.md:101-104`
requires release validation to establish.

## Main company identity and persistence

### Verified implementation

| Concern | Evidence at recorded SHA | Consequence for a registry change |
|---|---|---|
| Main database initialization | `src/financials/database.py::init_db_tables` (`:24-139`) is called by `CVMDatabase._init_db` (`:277-279`) and FastAPI lifespan (`apps/api/app/main.py:60-66`). It branches for SQLite (WAL, SQLite PK/REAL) versus PostgreSQL (SERIAL/DOUBLE PRECISION and concurrent index DDL at `database.py:31-40,127-136`), creates base DDL, and delegates supplementary table setup. | There is no verified general migration runner/version table. Existing upgrades are idempotent `CREATE TABLE IF NOT EXISTS` plus targeted `ALTER TABLE` helpers. Any compatibility/rollback plan must validate both SQLite and PostgreSQL. |
| Canonical company row today | `companies` is created at `src/financials/database.py:76-94`: `cd_cvm` primary key; name, commercial name, CNPJ, CVM/analytical sector, four GICS levels plus `gics_sector_slug`, type, B3 ticker, coverage rank, active flag, and timestamp. | `cd_cvm` is the primary persisted company key. The table already carries GICS fields but does not, from this DDL alone, establish four-level taxonomy governance, provenance, confidence, or manual-override audit fields. |
| Existing metadata repair | `init_db_tables` invokes `_ensure_company_columns` at `database.py:102-108` and `_backfill_companies_metadata` at `:138-139`; their definitions are `:142-208` and `:210-240`. `_ensure_company_columns` adds absent columns dynamically. | Schema evolution is distributed code, not a centrally audited sequence; a registry proposal needs an explicit compatibility/rollback plan. |
| Resolver | `src/companies/identity.py::CompanyIdentityResolver` (`:79-316`) resolves `cd_cvm` through an in-process cache, DB, synchronous CVM catalog fallback, and CSV ticker hints; it also offers ticker/CNPJ/batch methods. `_resolve_uncached` performs DB lookup at `:123-180`, then `CompanyCatalogService.lookup_company` at `:182-188`. | Resolver behavior and persisted company rows are related but not one declared authoritative entity-registry interface. Changes must inventory all resolver consumers and cannot assume offline-only resolution. |
| GICS overlap | The main DDL includes GICS columns, and `data/import/gics_mapping*.csv` exists. GitHub issue #397 remains open and requires canonical taxonomy, deterministic mapping, source/confidence, explicit unknowns, and auditable local overrides. | #397 owns classification-policy implementation. #414 records the baseline only; it must not make CVM labels appear as GICS or introduce a second mapping path. |
| Public read DTOs | `src/platform/contracts.py` defines `CompanyInfoDTO` (`:254`), directory/filter DTOs (`:330-402`), sector DTOs (`:417-491`), and refresh DTOs (`:56-205`, `:303-318`). | A new canonical entity record needs explicit DTO and bridge compatibility review; fields cannot be assumed private simply because they are SQLite columns. |

### Current bridge/read surface

`desktop/bridge_api/companies.py::CompanyBridgeMixin` publishes company reads:
`get_companies` (`:24-42`), filters, suggestions, info (`:92-108`), years,
KPIs, readiness, market-history, and exports. `get_company_info` first calls
the read service with `allow_catalog_lookup=True` (`:92-106`). The read service
first queries local state, then synchronously calls
`self.company_catalog.lookup_company` if the local payload is absent
(`src/financials/read_service_query.py:224-252`). The catalog snapshot loader
uses `requests.get(CVM_MASTER_URL, timeout=self.timeout)`
(`src/companies/catalog.py:127-160`); the resolver configures that service with
a three-second timeout (`identity.py:96`). Errors in the resolver catalog
fallback are logged, after which the resolver can still use its local CSV
ticker-map fallback (`identity.py:182-252`). Only after
that synchronous bridge/read-service lookup returns no company does the bridge
return `catalog_lookup_pending` and queue its background lookup (`companies.py:100-152`).
This is a current local-first tension: a registry contract must expose offline,
timeout, error, and pending behavior instead of implying every read is local.

### Active FastAPI/HTTP surface

`apps/api/app/main.py::create_app` is the active HTTP entrypoint (`:50-151`).
Its lifespan calls the shared `init_db_tables` on the read-service engine and
logs failure while starting degraded (`:60-66`). It registers health,
companies, sectors, status, analytics, and refresh routers (`:142-147`). The
companies router (`apps/api/app/routes/companies.py:50-310`) exposes directory,
filter, suggestion, refresh, company-info, export, years, statement, KPI, and
summary routes over the shared `CVMReadService`; bridge and API are therefore
separate transports with overlapping core/service DTO use, not interchangeable
contracts. Test coverage exists under `apps/api/tests/`, notably
`test_api_contract.py` (uses `create_app` and TestClient at `:11-15`) and
`test_refresh_api.py` (API refresh manager/contract tests at `:8-12`). Exact
bridge/API response parity beyond these source-bound surfaces is **Needs
validation** before adding entity fields.

PR #412 is the merge commit at the recorded base SHA (`e41855e`); its
first-parent delta changed frontend/docs only. `desktop/bridge_api/distribution.py::get_company_connections`
exists at `:1054-1124`, but the #412 commit itself did not add backend code at
this SHA. Treat it as contextual Company Workspace linkage, not a general
identity registry or an Energy/company causality model.

## Refresh and migration behavior

### Verified implementation

`src/refresh/jobs.py::ensure_refresh_runtime_tables_for_connection` is defined
at `:183-185`; its wrapper `ensure_refresh_runtime_tables` calls it at
`:178-181`, and `RefreshJobRepository.ensure_schema` calls the wrapper at
`:383-385` (the constructor at `:379-381` only assigns the engine). Repository
operations can instead call the connection-level helper directly; for example,
`get_active_job_for_company` does so at `:386-388`. It creates/extends
`company_refresh_status`, `refresh_jobs`, and
`refresh_job_enqueue_counter`, including indexes and the active-company unique
index. Refresh transport and result shapes are defined in
`src/platform/contracts.py`.

At startup `desktop/app.py:1209-1227` starts update checking, refresh-worker,
and `_background_remote_metadata_refresh` daemon threads. The latter is an
explicitly blocked decision in issue #402: source evidence says it can inspect
missing CNPJs/TTL and write company CNPJ and
`app_settings.metadata_last_successful_refresh`; frozen execution remains
**Needs validation**. Do not fold this implicit behavior into a registry
guarantee or change it without the #402 decision/João approval.

### Migration conclusion

No repository-wide schema-migration runner was verified in the inspected active
paths. Main and refresh schema evolution is initializer/helper based; Energy
has separate initialization plus an automatic data migration below. This
contradicts any plan that assumes a single versioned migration pipeline. For
desktop SQLite, validate on a copied database with backup-and-swap/rollback
before replacing a live file. For PostgreSQL, separately validate DDL/index
compatibility and rollback; a copied SQLite procedure is not a PostgreSQL
migration strategy. Never initialize or migrate the live Documents data root
merely to test a proposal.

## Energy identity and boundary

`src/energy_kpi/schema.py::get_energy_kpi_engine` (`:1194-1204`) uses the
separate Energy database; `init_energy_kpi_db` (`src/financials/database.py:581-586`)
states the separation permits independent refresh. Its schema initializer
`ensure_energy_kpi_tables_for_connection` (`energy_kpi/schema.py:65-1106`)
owns country/subsystem facts, source/snapshot/quality evidence, plant/parcel
and distribution identities, raw/fact tables, and rebuildable marts. Relevant
identity groups include `aneel_siga_plants` (`:360`), `ccee_plant_parcels`
(`:389`), `distribution_economic_groups` (`:655`),
`distribution_listed_companies` (`:664`), `distribution_distributors` (`:675`),
and `distribution_ownership_history` (`:717`).

Energy initialization is not DDL-only. `migrate_unmapped_distributors`
(`energy_kpi/schema.py:1108-1178`) seeds/reclassifies distributor rows, maps
unmapped IDs to canonical IDs, updates eight fact/project tables with
`UPDATE OR IGNORE`, deletes remaining old fact rows, then deletes the unmapped
distributor record. `ensure_energy_kpi_tables` invokes it automatically after
schema setup (`:1181-1184`), and cached engine construction invokes that wrapper
on first access (`:1187-1203`). This update/delete behavior is a material
Energy migration: use a copied Energy database plus a tested rollback/backup
plan before exercising it. Its real-data outcomes remain **Needs validation**;
this dossier did not initialize an Energy database.

The migration is not verified as atomic on partial table failure. Each of the
eight table moves catches and suppresses exceptions (`:1161-1172`), but the
outer `engine.begin()` can then commit (`:1181-1184`) and, once a target mapping
is selected, the old distributor row is deleted regardless of per-table errors
after the loop (`:1174-1177`). A
failed table can therefore leave facts keyed to the old ID after its identity
row is removed. `UPDATE OR IGNORE` also permits a conflict to leave old rows
unchanged before the following delete removes them (`:1163-1169`), creating
data-loss risk. Before any production use, require copied-database testing,
atomic failure/rollback behavior, and post-migration counts plus referential
reconciliation for all eight tables; do not accept a backup alone as proof of
integrity.

This is a separate Energy/asset model, not proof that a company master is
shared or that a listed issuer has a causal relation to a system indicator.
Issues #385 and #376 remain open/blocked: no PLD source expansion, capacity
headroom contract, or company-exposure conclusion is authorized by this
dossier. The Energy driver contract still prohibits direct MW/MWmed comparison
without an approved aggregate contract.

## Exports

The financial workbook path is `src/financials/read_service_export.py`
(`ReadServiceExportMixin.build_company_excel_export`, `:909`) ->
`src/financials/excel_exporter.py::ExcelExporter` (`:688-786`) ->
`desktop/bridge_api/companies.py::export_company_excel` (`:352-412`). The
bridge writes a collision-safe file under the configured runtime `output/`
directory and returns its path/size. Other verified export paths are company
market history (`companies.py:414-459`), coverage universe
(`src/companies/coverage.py:1835`), country KPIs
(`src/energy_kpi/excel.py::export_country_kpis`), and distribution export
(`src/energy_kpi/distribution/excel.py::export_distribution_excel`).

`docs/excel-exports.md` requires source/audit distinctions and manual
Excel-open validation for releases. Registry additions therefore need an
explicit export-field/source/override decision; no existing export is evidence
that every identity field is available or source-qualified.

## CI, release, updater, and storage

| Area | Verified evidence | Boundary |
|---|---|---|
| CI | `.github/workflows/ci.yml:3-111` runs on main/task pushes, PRs, and merge groups; it executes governance checks, py-compile, `pytest tests -q`, and Vite test/typecheck/build (`:101-111`). | CI validates source paths, not packaged/offline user-data behavior. The brief’s main CI run `30414910882` success is **Needs validation** here because the available read-only connector did not expose that run by ID. |
| Release | `.github/workflows/release-desktop.yml:3-120` triggers tag/dispatch, builds with the explicit version, verifies `desktop/__version__.py`, validates flat ZIP roots, hashes artifacts, and publishes a GitHub release. `docs/build-release.md:64-115` sets evidence hierarchy and updater/user-data guardrails. | #403 remains open/blocked and owns the decision about an enforceable release-publication gate. This dossier does not claim documented preflight is fully automated. |
| Updater | `docs/build-release.md:93-115` records checksum validation, versioned extraction, allowlisted swap, rollback snapshot, allowed semantic/RC tags, and prohibition on overwriting Documents data. | Latest stable `v0.29.2` and prerelease `v0.30.0-rc.1` supplied by the issue brief are **Needs validation** against current Releases API. |
| Storage | `scripts/data/check_storage_budget.py::_load_inventory` (`:131-140`) reads cached inventory by default; `parse_args` (`:143-152`) defines 12 GiB per main DB, 16 GiB database category, and 32 GiB active local storage excluding rollback backups. `docs/data-sources.md:162-182` defines the local data-root categories and offline distinction. | These are existing guardrails, not a justified entity-registry budget. No storage threshold is introduced here. |

## Read/performance baseline

`scripts/diagnostics/benchmark_real_read_paths.py` is not safe to classify as
read-only for the configured runtime data root. It measures a cold
`CVMReadService.list_companies` call plus caller-configurable median/min/max
for directory/search/filter/sector/health/suggestions and bridge
directory/base-health reads (`:23-105`). Its health calls can miss the
persistent cache: `get_health_snapshot` then writes it
(`src/financials/read_service_coverage.py:101-138`) under
`settings.paths.cache_dir` (`:2509-2512,2558-2581`). It was therefore **not
executed** in this worktree.

Before rerunning it, use an isolated settings/data/cache root and an isolated
copied database, never the live Documents root. Record the database size,
environment, command, run count, and separate cold-cache and warm-cache phases;
clear/verify the isolated persistent base-health cache before cold runs and
preserve/verify it before warm runs. This prevents both user-data writes and
cache-state ambiguity in the timings.

The inherited issue baseline is recorded as supplied evidence, not a repeatable
measurement in this worktree: cold directory **873.48 ms**, warm bridge company
list **0.54 ms**, and base health **1.30 ms**. Environment, DB size, individual
runs, and min/max are absent from the brief; all are **Needs validation** before
using these figures as a regression comparison. The e41855e change was
frontend/docs only (`git show --stat`), so it did not alter those measured
Python paths.

## GitHub overlap and non-duplication map

| Item | Reverified state | Relationship to this dossier | Child-action rule |
|---|---|---|---|
| #397 GICS taxonomy | Open. | Dependency. | Registry work consumes its canonical output; no duplicate mapping dictionary or override policy. |
| #402 startup metadata refresh | Open, `status:blocked`. | Narrowing: records a potential local-first/identity write, but no behavior change. | Wait for explicit decision; preserve pending/error/offline visibility. |
| #403 release-publication gate | Open, `status:blocked`. | Independence. | Do not modify workflow/release channel; a registry release must consume its accepted evidence gate when approved. |
| #385 official CCEE hourly PLD | Open, `status:blocked`. | Independence. | No PLD/provider/energy ingestion scope in an entity registry. |
| #376 next Energy expansion | Open, `status:blocked`. | Independence. | Do not assert issuer exposure or expand energy scope. |
| #412 Company connections | Merged at base SHA. | Incorporation boundary: contextual links only. | Keep Company Workspace links distinct from canonical entity identity. |

## Likely subsequent write sets and conflict lanes

These are planning signals, not authorization:

| Concern | Likely paths | Lane/conflict |
|---|---|---|
| Main entity schema and resolver | `src/financials/database.py`, `src/companies/identity.py`, `src/platform/contracts.py`, focused tests | backend; serial with #397 and any migration work |
| Bridge/read contract | `desktop/bridge_api/companies.py`, `desktop/services.py`, `apps/desktop-web/src/lib/bridge/types.ts`, consumer tests | backend + frontend child tasks; public contract-sensitive review |
| GICS input/policy | `data/import/gics_mapping.csv`, GICS scripts/docs | #397 ownership; do not overlap |
| Export consumption | financial/coverage/export modules and `docs/excel-exports.md` | backend + ops-quality; source/audit contract review |
| Release/package verification | `.github/workflows/`, build/updater docs/scripts | ops-quality; #403 ownership |
| Energy linkage | `src/energy_kpi/**`, Energy bridge/UI/docs | backend/frontend as a separate approved task; no implicit registry scope |

## Open evidence and validation handoff

- **Needs validation:** exact recent CI run result/details, current Releases API
  state, packaged frozen runtime, clean install/update-over-prior behavior,
  current Documents database sizes, and repeatable performance environment.
- **Needs validation:** whether all company identity consumers use
  `CompanyIdentityResolver`; targeted repository searches show consumers in
  read service, scraper, coverage, market history/cap, universe, bridge, and
  desktop services, but this dossier does not claim exhaustive runtime tracing.
- **Required before implementation:** agree the authoritative company entity
  boundary and migration plan, preserve source/override/audit metadata, test
  SQLite on a copied database and PostgreSQL compatibility/rollback separately,
  prove offline and explicit failure states, and benchmark before/after only
  with isolated settings/data/cache roots and the cold/warm protocol above.
