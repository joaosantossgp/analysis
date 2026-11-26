# Data Updates

How the desktop app fills and refreshes the **local database** with official
CVM filings. Decision of record: [ADR 0010](decisions/0010-shell-owned-data-updates.md).
Terms follow [GLOSSARY.md](../GLOSSARY.md). Bridge contract: `desktop/bridge.py`
and `desktop/bridge_api/`; typed mirror in `apps/desktop-web/src/lib/bridge/`.

## Ownership

The app shell owns the local database state and the data update. Settings keeps
preferences and maintenance only and is never a required step to see data.

| Surface | Role |
|---|---|
| Top-bar pill (`components/shell/DataIndicator.tsx`) | Local database state on every screen; opens the Data panel |
| Data panel | State, progress with ETA, the shared action, failures with retry, link to Data completeness |
| Home (`components/home/EmptyDatabaseHero.tsx`, `LocalDatabaseNotice.tsx`) | Leads with "Download CVM data" while the database has no statements; slim notice when Stale or Completed with failures |
| Empty states (`components/shell/LocalDataEmptyState.tsx`) | Companies, Sectors and sector detail offer the same action when the cause is an empty local database |
| Companies directory | Row status (Downloading, Queued, Failed) and the run phase during a data update |
| Company pages | "Update company" (one company); "Download now" when the company waits in a running data update; "Update market prices (external)" |
| `/settings/data` | History range preference and the Data completeness table |
| `/settings/storage` | Rebuild local database |
| `/settings/sources` | B3 sectors, manual imports, indicator sources, market caps (Yahoo Finance, unofficial) |

Every label and behavior of the action comes from one component,
`components/shell/DataAction.tsx`: "Download CVM data" when the database has no
statements, "Update data" afterwards, "Try again" after a failed first run,
"View progress" (or "Cancel update" inside the panel) while a run is active,
disabled with a visible reason when offline.

## Local database state

`get_local_database_state` (bridge) and `GET /local-database-state` (HTTP
adapter) return one derived answer, computed by
`src/refresh/local_database_state.py` from local files only (no network, no
writes):

| Field | Meaning |
|---|---|
| `state` | `empty`, `files`, `updating`, `current`, `stale`, `partial`, `failed` (`unknown` when local files cannot be read) |
| `has_statements` | Whether `financial_reports` has any row (cheap existence check) |
| `last_full_update_at` | Finish time of the last successful or partial data update covering all active companies |
| `stale_reason` | `{label, due}` of the latest CVM deadline passed since then; label null when no full data update was ever recorded |
| `run` | Active run: scope, phase (`starting`, `files`, `companies`, `finalizing`), file and company counts, pace-based ETA (time since the company phase began ÷ companies processed × companies left), company ids, current company |
| `last_run` | Last finished data update or retry, with failures and error |
| `failures` | Companies whose last refresh failed, with company name and error |

**Stale** follows the CVM filing calendar: ITR deadlines on May 15, Aug 14 and
Nov 14, DFP on Mar 31. Company updates and retries never move
`last_full_update_at`. Offline comes from the browser connectivity flag and is
shown as a suffix that never hides another state.

## The data update

`start_data_update` has a fixed scope: every active company in the CVM catalog,
companies with a B3 ticker first, over the History range, official CVM sources
only. Presets, batch sizes and the market-cap ranking are not inputs. The
catalog is refreshed once before dispatch and the scraper reads the company
registry from that snapshot. Data updates honor the full History range (the
"missing" fast lane applies to other batches only).

The History range is stored through `get_data_update_settings` /
`save_data_update_settings` as a span of years and rolls forward each year
("Last 5 years", "Since 2010", ...).

Runs are explicit and logged. Nothing starts a data update automatically, on
launch or when the database is Stale.

### Completion

- A CVM file that cannot be downloaded or read fails the affected companies
  ("CVM files could not be downloaded: DFP 2024"). A 404 means the file is not
  published yet (for example the current year's DFP) and is not a failure.
- Failed companies are retried once inside the job.
- The job ends `success`, `partial` (some companies failed, "Completed with N
  failures"), `error` (all failed), or `cancelled`.
- When a job finishes, the job manager invalidates read caches and the Data
  completeness cache; the shell refreshes every data screen.
- Retries use `request_refresh` with `mode: "failed"` and `scope: "retry"`.

### Concurrency and job store

A data update and a company update may run in the same process; one writer per
yearly CVM ZIP prevents conflicting downloads. `refresh_jobs.json` keeps the 50
most recent finished jobs and writes progress at most every 2 seconds; readers
never rewrite it.

## Company updates

A company update covers one company ("Update company"). See
[company-on-demand-updates.md](company-on-demand-updates.md).

## Rebuild

`reset_local_database` with `action: "recreate_local"` and the typed `REBUILD`
confirmation backs up and recreates the local database, keeps the analyst's
ignore flags, and starts nothing afterwards. It is blocked in dev+release-data
mode unless `CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES=1`, and under a concurrent
lock (see [dev-runtime-and-data-paths.md](dev-runtime-and-data-paths.md)).

## Data completeness

`get_data_coverage` returns per-company rows with a status (`complete`,
`partial`, `no_financial`, `failed`, `unmapped`, `ignored`) and filter buckets.
The table lives at `/settings/data`. Failed rows offer Retry; no-data rows offer
Open and Ignore. `set_company_ignored` excludes a company from completeness.

## Settings health summary

`get_settings_health_summary` is read-only and cheap: it never calls
`get_data_coverage`, never triggers updates, imports, integrity checks or
network calls. Each "Needs attention" item links to where it is fixed; an empty
CVM registry or statements link to Home.

## Development

In mock mode, pick a local database scenario with
`localStorage.setItem("cvm_mock_local_database", "<state>")` and reload
(`empty`, `files`, `updating`, `current`, `stale`, `partial`, `failed`).
