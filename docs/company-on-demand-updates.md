# Company Updates

A **company update** is a data update limited to one company
([GLOSSARY.md](../GLOSSARY.md)), started from the company pages. The data update
for all active companies is described in [database-updates.md](database-updates.md).
Bridge contract: `desktop/bridge.py`; typed mirror under
`apps/desktop-web/src/lib/bridge/`; facade `apps/desktop-web/src/lib/api/companyRefresh.ts`.

## Companies directory lists the catalog

`get_companies` merges the active CVM catalog with local rows until the local
rows cover every active company, so a company can be found and opened before it
is downloaded. Each `CompanyDirectoryItem` carries `data_status`: `no_history` |
`partial` | `complete` | `failed` | `unmapped`. During a data update, rows of that
run show Downloading or Queued, and companies that failed in the last partial
run show Failed.

## Actions on the company page

The company command bar (`components/CompanyCommandBar.tsx`) offers:

- **Update company**: CVM statements for this company over the chosen history
  range (`request_refresh` with `cd_cvm`). While the company waits in a running
  data update the label is **Download now**, which pulls it ahead.
- **Update market prices (external)**: market price history, external data kept
  apart from CVM statements.
- **History range…**: a custom CVM year range.

A company update never moves the "last full data update" used for Stale.

## Status and progress

`get_refresh_status` returns `CompanyRefreshStatus` per company:

- `tracking_state` — `idle` | `queued` | `running` | `stalled` | `success` |
  `no_data` | `error`
- progress: `progress_current` / `progress_total`, `estimated_progress_pct`,
  `estimated_eta_seconds`, `estimated_completion_at`
- outcome/freshness: `last_status`, `last_error`, `last_success_at`,
  `latest_attempt_outcome`, `freshness_summary_*`
- `is_retry_allowed`, `status_reason_code` — drive the retry affordance

## Write/lock safety

Company updates are write operations: blocked in dev+release-data mode without
`CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES=1`, and blocked under a concurrent lock.
See [dev-runtime-and-data-paths.md](dev-runtime-and-data-paths.md).
