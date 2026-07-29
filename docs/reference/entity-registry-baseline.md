# Entity Registry Baseline

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
`apps/api` is an active HTTP adapter for development/hosted access, not the
packaged UI.

Runtime data is local to `%USERPROFILE%\\Documents\\CVMAnalytics` unless
overridden; it remains readable offline after download. This baseline does not
prove clean-machine packaged behavior, which `docs/architecture.md:101-104`
requires release validation to establish.

## Main company identity and persistence

### Verified implementation

| Concern | Evidence at recorded SHA | Consequence for a registry change |
|---|---|---|
| Main database initialization | `src/financials/database.py::init_db_tables` is called by `CVMDatabase.__init__` (`:24-138`, `:246-279`). It enables SQLite WAL, creates base DDL, and delegates supplementary table setup. | There is no verified general migration runner/version table. Existing upgrades are idempotent `CREATE TABLE IF NOT EXISTS` plus targeted `ALTER TABLE` helpers. |
| Canonical company row today | `companies` is created at `src/financials/database.py:76-94`: `cd_cvm` primary key; name, commercial name, CNPJ, CVM/analytical sector, four GICS columns, type, B3 ticker, coverage rank, active flag, and timestamp. | `cd_cvm` is the primary persisted company key. The table already carries GICS fields but does not, from this DDL alone, establish four-level taxonomy governance, provenance, confidence, or manual-override audit fields. |
| Existing metadata repair | `_backfill_companies_metadata` and `_ensure_company_columns` are invoked from initialization (`database.py:142-244`). `_ensure_company_columns` explicitly adds absent columns dynamically. | Schema evolution is distributed code, not a centrally audited sequence; a registry proposal needs an explicit compatibility/rollback plan. |
| Resolver | `src/companies/identity.py::CompanyIdentityResolver` is the single `cd_cvm -> CompanyIdentity` entry point (`:79-316`), with `resolve`, `resolve_by_ticker`, `resolve_by_cnpj`, and batch resolution. Its sources include DB data and CSV ticker mapping (`:56-76`, `:123-254`). | Resolver behavior and persisted company rows are related but not one declared authoritative entity-registry interface. Changes must inventory all resolver consumers. |
| GICS overlap | The main DDL includes GICS columns, and `data/import/gics_mapping*.csv` exists. GitHub issue #397 remains open and requires canonical taxonomy, deterministic mapping, source/confidence, explicit unknowns, and auditable local overrides. | #397 owns classification-policy implementation. #414 records the baseline only; it must not make CVM labels appear as GICS or introduce a second mapping path. |
| Public read DTOs | `src/platform/contracts.py` defines `CompanyInfoDTO` (`:254`), directory/filter DTOs (`:330-402`), sector DTOs (`:417-491`), and refresh DTOs (`:56-205`, `:303-318`). | A new canonical entity record needs explicit DTO and bridge compatibility review; fields cannot be assumed private simply because they are SQLite columns. |

### Current bridge/read surface

`desktop/bridge_api/companies.py::CompanyBridgeMixin` publishes company reads:
`get_companies` (`:24-42`), filters, suggestions, info (`:92-108`), years,
KPIs, readiness, market-history, and exports. `get_company_info` calls the
read service with `allow_catalog_lookup=True`; absent info can enqueue a
background lookup (`:92-152`). This is an explicit place where entity reads can
cross from cached data into a lookup workflow, so a future registry contract
must specify offline/error/pending semantics rather than hide them.

PR #412 is merged at the recorded SHA; its parent commit is the base and it
changed frontend/docs only. `desktop/bridge_api/distribution.py::get_company_connections`
exists at `:1054-1124`, but the #412 commit itself did not add backend code at
this SHA. Treat it as contextual Company Workspace linkage, not a general
identity registry or an Energy/company causality model.

## Refresh and migration behavior

### Verified implementation

`src/refresh/jobs.py::ensure_refresh_runtime_tables_for_connection` (`:178-356`)
creates/extends `company_refresh_status`, `refresh_jobs`, and
`refresh_job_enqueue_counter`, including indexes and the active-company unique
index. `RefreshJobRepository` calls this setup (`:379-385`). Refresh transport
and result shapes are defined in `src/platform/contracts.py`.

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
uses its own initializer. This is a documented contradiction with any plan that
assumes a single versioned migration pipeline. A future issue should first
choose a migration/compatibility strategy, then use a copied database and
backup-and-swap procedure; it must never initialize or migrate the live
Documents data root merely to test a proposal.

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
| CI | `.github/workflows/ci.yml:3-110` runs on main/task pushes, PRs, and merge groups; it executes governance checks, py-compile, `pytest tests -q`, and Vite test/typecheck/build. | CI validates source paths, not packaged/offline user-data behavior. The brief’s main CI run `30414910882` success is **Needs validation** here because the available read-only connector did not expose that run by ID. |
| Release | `.github/workflows/release-desktop.yml:3-120` triggers tag/dispatch, builds with the explicit version, verifies `desktop/__version__.py`, validates flat ZIP roots, hashes artifacts, and publishes a GitHub release. `docs/build-release.md:64-115` sets evidence hierarchy and updater/user-data guardrails. | #403 remains open/blocked and owns the decision about an enforceable release-publication gate. This dossier does not claim documented preflight is fully automated. |
| Updater | `docs/build-release.md:93-115` records checksum validation, versioned extraction, allowlisted swap, rollback snapshot, allowed semantic/RC tags, and prohibition on overwriting Documents data. | Latest stable `v0.29.2` and prerelease `v0.30.0-rc.1` supplied by the issue brief are **Needs validation** against current Releases API. |
| Storage | `scripts/data/check_storage_budget.py:143-178` checks cached inventory by default; defaults are 12 GiB per main DB, 16 GiB database category, and 32 GiB active local storage excluding rollback backups. `docs/data-sources.md:162-182` defines the local data-root categories and offline distinction. | These are existing guardrails, not a justified entity-registry budget. No storage threshold is introduced here. |

## Read/performance baseline

The safe diagnostic implementation is
`scripts/diagnostics/benchmark_real_read_paths.py`: it declares no database
modification and measures a cold `CVMReadService.list_companies` call plus
five-run (caller-configurable) median/min/max for directory/search/filter/
sector/health/suggestions and bridge directory/base-health reads (`:1-114`).
It resolves the normal runtime settings, so it was **not executed** in this
worktree: safety was not proven for the live Documents data root and the task
forbids that mutation risk.

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
| #397 GICS taxonomy | Open. | Dependency/incorporation boundary: it owns taxonomy, mapping precedence, confidence, and overrides. | Registry work consumes its canonical output; no duplicate mapping dictionary. |
| #402 startup metadata refresh | Open, `status:blocked`. | Narrowing: records a potential local-first/identity write, but no behavior change. | Wait for explicit decision; preserve pending/error/offline visibility. |
| #403 release-publication gate | Open, `status:blocked`. | Independence with release-evidence dependency. | Do not modify workflow/release channel; use its accepted evidence gate when approved. |
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
  boundary and migration plan, preserve source/override/audit metadata, test on
  a copied database, prove offline and explicit failure states, and benchmark
  before/after with the diagnostic’s full method/DB-size output.
