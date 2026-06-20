# Database Updates

How the desktop app refreshes the local financial database, and how the Update
Base page relates to Data Coverage. Active routes live in
`apps/desktop-web/src/App.tsx`; the bridge contract is `desktop/bridge.py`
(typed mirror in `apps/desktop-web/src/lib/bridge/types.ts`).

## Page map

| Route | Page | Role |
|-------|------|------|
| `/` | Home | Summary only — base health snapshot, KPIs, CTA into updates |
| `/settings` | Settings Overview | Canonical local runtime and data-health summary |
| `/settings/health` | Settings Data Health | Segment-level health summary |
| `/settings/coverage` | DataCoveragePage inside Settings | Audit page — per-company coverage gaps |
| `/settings/updates` | UpdateBasePage inside Settings | Primary "update the database" flow |
| `/settings/sources` | UserImportsPage inside Settings | Source status and manual imports |
| `/settings/storage` | Settings Storage | Local paths, database files, cache, logs, and outputs |
| `/settings/diagnostics` | StatusPage inside Settings | Advanced runtime, updater, path, and diagnostic details |
| `/atualizar-base` | Redirect | Backward-compatible redirect to `/settings/updates` |
| `/data-coverage` | Redirect | Backward-compatible redirect to `/settings/coverage` |
| `/status` | Redirect | Backward-compatible redirect to `/settings/diagnostics` |
| `/company-universe` | CompanyUniversePage | Which companies are in scope (presets) |

Home is a product summary. Settings is the canonical application configuration,
local storage, data-health, source/import, update, and diagnostic module. The
Update Base section is the one place that starts a full database update. Data
Coverage is an audit/triage surface, not a bulk update launcher (per-company
updates are triggered from the company pages — see
[company-on-demand-updates.md](company-on-demand-updates.md)).

## Settings health summary

`get_settings_health_summary` is an additive, read-only bridge method used by
the initial Settings overview. It returns:

- `overall_status`: `healthy`, `degraded`, `critical`, `updating`, `empty`,
  `unavailable`, or `unknown`;
- `segments`: required and optional data domains with status, reason, owner,
  provider, latest reference, update timestamps, and action route;
- runtime write mode and lock status;
- local storage paths;
- active update/import jobs;
- metric provenance and performance notes.

Initial Settings load intentionally avoids expensive detail contracts:

- it does not call `get_data_coverage`;
- it does not call `get_distribution_health`;
- it does not trigger updates, imports, integrity checks, or network calls;
- distribution row counts and CVM coverage rows are loaded only after opening
  their detail sections.

Required segments are the CVM company registry and CVM financial statements.
Optional segments include market data, energy macro KPIs, SIN, plant/CCEE
sources, distribution/ANEEL, and manual imports. Missing optional evidence is
shown as `unknown` or `unavailable`, not as `critical`.

## Update flow

The Update Base page calls `start_data_update` through the
`lib/api/updateBase.ts` facade. Settings are loaded/saved via
`get_data_update_settings` / `save_data_update_settings`.

`DataUpdateSettings` (see `types.ts`):

- `universe_preset` — `top_100` | `top_200` | `top_500` | `all`
- `batch_size` — `50` | `100` | `200` | `500`
- `start_year`, `end_year` — year range to fetch
- `retry_failed` — re-attempt previously failed companies
- `recompute_coverage` — rebuild coverage stats after the run

`RefreshMode` selects what gets fetched: `missing` | `full` | `outdated` |
`failed`.

Progress is polled via `get_refresh_status` (job-level) and surfaced in
Settings -> Diagnostics and the Update Base page.

## Top N universe configuration

`top_100`, `top_200`, and `top_500` require a market-cap ranking source before
the backend starts a refresh job. Provider order/settings:

1. Yahoo Finance bulk updater (`CVM_MARKET_CAP_PROVIDER=yahoo_finance`, default, unofficial free source)
2. Local CSV snapshot (`CVM_COMPANY_UNIVERSE_SNAPSHOT_PATH`, default
   `data/metadata/b3_market_cap_universe_snapshot.csv`, used if provider is `local_snapshot` or yahoo_finance fails)

Note: `CVM_MARKET_CAP_PROVIDER=yfinance` is accepted as a deprecated alias for `yahoo_finance`.

If no ranking source is available (e.g. yahoo_finance fails and no local snapshot exists), `start_data_update` returns
`status: "blocked"` with `status_reason_code:
"company_universe_unavailable"`. No refresh job is dispatched. The Update Base
page shows a configuration notice instead of a completed summary from a
previous run. Choosing `all` uses the local CVM company catalog and does not
need market-cap ranking.

## Reset / rebuild

`reset_local_database` (bridge) backs up and recreates the local DB. Response
`action` is `restart_current` or `recreate_local`; it returns `backup_path` and
`removed[]`. This is destructive — it is blocked in dev+release-data mode unless
`CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES=1`, and blocked entirely under a
concurrent lock (see [dev-runtime-and-data-paths.md](dev-runtime-and-data-paths.md)).

## Data Coverage relationship

`get_data_coverage` returns per-company rows with a `DataCoverageStatus`:
`complete` | `partial` | `no_financial` | `failed` | `unmapped` | `ignored`,
plus filter buckets (`no_dfp`, `no_itr`, `stale`, `ticker_unmapped`, etc.).
Use it to find what to update; then run an update from Update Base (bulk) or a
company page (single). `set_company_ignored` excludes a company from coverage
math.
