# Company-Level On-Demand Updates

Per-company refresh from the company pages, separate from the bulk Update Base
flow ([database-updates.md](database-updates.md)). Bridge contract:
`desktop/bridge.py`; typed mirror `apps/desktop-web/src/lib/bridge/types.ts`;
facade `apps/desktop-web/src/lib/api/companyRefresh.ts`.

## Companies search includes no-history companies

`get_companies` returns the full catalog, including companies with no local
financial data. Each `CompanyDirectoryItem` carries `data_status`
(`CompanyDataStatus`): `no_history` | `partial` | `complete` | `failed` |
`unmapped`. A company can be found and opened even before any data is downloaded.

## On-demand update from the company page

The company detail page (`/empresas/:cdCvm`) triggers `request_refresh` for a
single company. Use it to:

- download history for a company that currently shows `no_history`
- fetch new ITRs / newly published filings
- pull a specific year range (`start_year` / `end_year`)
- retry a company that previously failed

`cancel_refresh` stops an in-flight single-company job.

## Status and progress

`get_refresh_status` returns `CompanyRefreshStatus` per company:

- `tracking_state` — `idle` | `queued` | `running` | `stalled` | `success` |
  `no_data` | `error`
- progress: `progress_current` / `progress_total`, `estimated_progress_pct`,
  `estimated_eta_seconds`, `estimated_completion_at`
- outcome/freshness: `last_status`, `last_error`, `last_success_at`,
  `latest_attempt_outcome`, `freshness_summary_*`
- `is_retry_allowed`, `status_reason_code` — drive the retry affordance

## Status badges

UI badges map from `data_status` / `tracking_state`:

- **complete** — readable current data present
- **partial** — some years present, gaps remain
- **no_history** — in catalog, no local financial data yet
- **failed** / **error** — last attempt failed (`last_error`, retry if allowed)
- **unmapped** — ticker/CVM mapping missing (won't fetch until resolved)

## Write/lock safety

On-demand updates are destructive bridge calls: blocked in dev+release-data mode
without `CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES=1`, and blocked under a
concurrent lock. See [dev-runtime-and-data-paths.md](dev-runtime-and-data-paths.md).
