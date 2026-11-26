# Settings Module

Settings keeps preferences and maintenance only: local data preferences, data
completeness, sources and imports, storage, app state, and diagnostics. It is
never a required step to see data; the app shell owns the local database state
and the data update ([ADR 0010](decisions/0010-shell-owned-data-updates.md),
[database-updates.md](database-updates.md)).

## Navigation

One list, `apps/desktop-web/src/lib/settingsNav.ts`, drives both the shell
sub-navigation and the Settings sidebar, so they cannot disagree.

| Route | Section |
|-------|---------|
| `/settings` | Overview |
| `/settings/data` | Data: History range and Data completeness |
| `/settings/sources` | Sources |
| `/settings/imports` | Sources > Manual imports |
| `/settings/indicator-sources` | Sources > Indicator sources |
| `/settings/storage` | Storage |
| `/settings/app` | App |
| `/settings/diagnostics` | Advanced |

Retired routes redirect: `/settings/updates`, `/settings/health`,
`/settings/coverage`, `/atualizar-base`, `/company-universe` and `/data-coverage`
go to `/settings/data`; `/status` goes to `/settings/diagnostics`.

## Information Architecture

Overview is a calm, action-first summary. It shows overall status, issue counts,
a capped Needs Attention list whose items link to where each issue is fixed (an
empty CVM registry or empty statements link to Home, where "Download CVM data"
lives), and cards for Data, Sources, Storage, and App. Overview uses only the
cached lightweight Settings health summary and cached storage summary; it does
not trigger coverage loads, storage scans, imports, refreshes, repair actions,
migrations, or network work.

Data holds the History range preference (Last 3 / 5 / 10 years or Since 2010; a
span of years that rolls forward each year) and the Data completeness table.
Data completeness is an audit surface, not an update launcher: failed rows offer
Retry, no-data rows offer Open and Ignore.

Sources is a source hub: B3 sectors, manual imports, indicator sources, and
"Fetch market caps", an explicit action labelled Yahoo Finance (unofficial)
with its last status.

Storage shows local footprint, file count, free space, largest category, last
measured time, an explicit Refresh inventory button, managed paths first, and
"Rebuild local database" (typed confirmation, backup first, keeps ignore flags,
starts nothing afterwards).
Technical inventory tables remain available under Storage > Advanced details.

App contains user-facing runtime state: version, runtime mode, bridge status,
write mode, data root mode, desktop shell, lock state, and common local file
paths. Software updater controls remain in Advanced diagnostics because the
existing updater UI is owned by the diagnostics/status workflow.

Advanced contains troubleshooting surfaces: runtime diagnostics, updater/log
details from `StatusPage`, metric provenance, and status definitions.

## Health Status Semantics

Settings uses one vocabulary:

- `healthy`: required checks pass with enough evidence.
- `degraded`: data is usable, but freshness, coverage, quality, source, or last
  refresh needs attention.
- `critical`: a required database or runtime dependency is unreadable, locked, or
  has a blocking error.
- `updating`: a valid refresh/import job is running.
- `empty`: the segment is configured but has no usable local data yet.
- `unavailable`: the bridge or optional contract could not report the segment.
- `unknown`: evidence is insufficient or intentionally deferred.

Overall status is categorical, not a numeric score. Required CVM segments drive
critical/empty status. Optional segments do not make the overall state critical
unless they report an active blocking error.

## Segment Taxonomy

Required:

- Companies and CVM Registry
- CVM Financial Statements

Optional:

- Market Data
- Energy Macro Indicators
- SIN / ONS
- Generation Assets and CCEE Plant Data
- Distribution / ANEEL
- Manual/user-managed source files

Optional missing data is shown as `unknown` or `unavailable`, not `healthy`.
Row counts are displayed only as evidence and are never treated as proof of
freshness, completeness, integrity, or usability.

## Metric Provenance

The overview calls `get_settings_health_summary`, an additive read-only bridge
method. It uses bounded checks only:

- runtime mode, write mode, and lock state from the desktop bridge/runtime;
- local paths from `src.platform.settings`;
- CVM table presence via SQLite table existence plus `SELECT 1 LIMIT 1`;
- active CVM refresh jobs from the light refresh status path;
- energy macro and SIN health from their existing compact health contracts;
- plant and distribution active refresh state only.

The overview does not call:

- `get_data_coverage`;
- `get_distribution_health`;
- destructive update/import/reset methods;
- network-backed source refreshes;
- integrity, migration, vacuum, or repair operations.

Full CVM coverage and distribution source/count details are loaded only after the
user opens the relevant Settings section or indicator workflow. Metric
provenance is shown in Advanced > Evidence, not on the default Data view.

## Storage Inventory

Settings also exposes the local data footprint through a separate storage
inventory contract. This is intentionally not part of the expensive work done by
`get_settings_health_summary`.

Bridge methods:

- `get_storage_inventory`: returns the latest cached inventory snapshot.
- `start_storage_inventory_scan`: starts one background scan when explicitly
  requested by the user.
- `get_storage_inventory_scan_status`: returns the active or last scan state.

Snapshot location:

- `${CVM_METADATA_DIR}/storage_inventory_v1.json`, normally
  `%USERPROFILE%/Documents/CVMAnalytics/metadata/storage_inventory_v1.json`.

Measurement semantics:

- `logical_bytes` is the sum of filesystem file lengths.
- `allocated_bytes_total` is `null` unless a platform-specific reliable
  allocated-size measurement is added later.
- SQLite internal free-page bytes are estimated from `page_size *
  freelist_count`; this is reusable internal database capacity, not a cleanup
  amount.
- The scan does not read file contents, hash files, run `VACUUM`, checkpoint WAL
  files, mutate SQLite pragmas, or follow symlinks/junctions.

Storage roots come from resolved `AppPaths` values, including data, input/raw,
processed, output/reports, logs, cache, metadata, database directory, CVM
financial database, Energy KPI database, analytical stores, rollback backups,
and Energy raw source directory.
Physical roots are canonicalized and nested duplicates are excluded from
scanning to prevent double counting. Files are still classified using the most
specific known path owner, so scanning the data root can attribute nested files
to databases, analytical stores, rollback backups, raw sources, processed data,
cache, logs, exports, metadata, or uncategorized managed data.

Storage health uses categorical thresholds:

- critical free disk: less than 1 GiB free or less than 3% free on a managed
  volume;
- degraded free disk: less than 5 GiB free or less than 10% free;
- stale inventory: older than 7 days;
- large WAL warning: WAL file larger than 50% of its main SQLite database;
- skipped paths or scan errors: degraded or partial, depending on severity.

The Settings Overview shows only compact cached storage fields: total logical
footprint, main volume free space, largest category, and last measured time.
Opening `/settings/storage` displays the default storage summary and managed
paths first. Detailed category, segment, database, largest-item, warning,
rollback-backup, managed-snapshot, and measurement-note tables are kept behind
Storage > Advanced details.

`/settings/storage` also shows a tiered local storage summary:

- main SQLite databases;
- managed analytical stores;
- raw sources;
- retained rollback backups.

When rollback backups exist, the inventory includes
`backup_candidates?: StorageBackupCandidate[]`. Each candidate reports the path,
logical bytes, file count, modified time, reclaimable bytes, and destructive
confirmation flags. The Settings UI shows these in the Rollback Backup Plan
panel so users can see reclaimable storage after migration validation. This is
diagnostic only: Settings does not expose a delete or move action in the current
contract.

Managed analytical stores can also report
`managed_snapshot_history?: StorageManagedSnapshotHistory[]`. Each row describes
a raw source batch under a managed dataset, whether the current manifest points
to it, its logical bytes, file count, modified time, and audit reason. The
Settings UI shows these in the Managed Source Snapshots panel so operators can
see retained source evidence before any future retention policy is designed.
This is also diagnostic only: no delete or move action is exposed in this phase.

## Known Limits

- Market data health is currently conservative and reports `unknown` in the
  overview unless a workflow-specific contract is opened.
- Distribution detail health can include full fact-table counts and source logs,
  so it remains deferred.
- Browser preview cannot inspect local data and reports an explicit unavailable
  state.
- Mock mode uses fixture data and should not be used to validate local database
  behavior.
- Storage inventory does not estimate deduplication or compression. It reports
  measured rollback backup candidates as reclaimable only after explicit
  validation; it does not clean them up automatically.
