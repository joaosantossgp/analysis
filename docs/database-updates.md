# Database Updates

How the desktop app refreshes the local financial database, and how the Update
Base page relates to Data Coverage. Active routes live in
`apps/desktop-web/src/App.tsx`; the bridge contract is `desktop/bridge.py`
(typed mirror in `apps/desktop-web/src/lib/bridge/types.ts`).

## Page map

| Route | Page | Role |
|-------|------|------|
| `/` | Home | Summary only — base health snapshot, KPIs, CTA into updates |
| `/atualizar-base` | UpdateBasePage | Primary "update the database" flow |
| `/data-coverage` | DataCoveragePage | Audit page — per-company coverage gaps |
| `/company-universe` | CompanyUniversePage | Which companies are in scope (presets) |
| `/status` | StatusPage | Diagnostics, runtime, data paths, write mode, lock |

Home is read-only summary. The Update Base page is the one place that starts a
full database update. Data Coverage is an audit/triage surface, not an update
launcher (per-company updates are triggered from the company pages — see
[company-on-demand-updates.md](company-on-demand-updates.md)).

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

Progress is polled via `get_refresh_status` (job-level) and surfaced on the
Status page and the Update Base page.

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
