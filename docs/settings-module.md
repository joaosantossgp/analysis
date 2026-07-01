# Settings Module

The Vite desktop app uses Settings as the canonical place for application
configuration, local data health, storage paths, sources/imports, database
updates, and diagnostics.

## Navigation

| Route | Section |
|-------|---------|
| `/settings` | Overview |
| `/settings/health` | Data Health |
| `/settings/storage` | Storage and Local Data |
| `/settings/sources` | Sources and Imports |
| `/settings/imports` | Backward-compatible Sources and Imports entry |
| `/settings/updates` | Updates |
| `/settings/coverage` | Backward-compatible CVM Coverage detail entry |
| `/settings/diagnostics` | Application / Advanced Diagnostics |
| `/status` | Redirects to `/settings/diagnostics` |
| `/data-coverage` | Redirects to `/settings/coverage` |
| `/atualizar-base` | Redirects to `/settings/updates` |

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
user opens the relevant Settings section or indicator workflow.

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
footprint, main volume free space, largest category, growth when history exists,
and last measured time. Opening `/settings/storage` displays detailed category,
segment, database, largest-item, warning, and measurement-note tables.

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
