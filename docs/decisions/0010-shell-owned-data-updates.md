# 0010: Shell-owned data updates

Status: Accepted (2026-11-24)

## Context

On a fresh install the analyst needs 9 clicks across 7 screens to see a
statement. The only bulk download lives at Settings -> Data -> Database Updates,
and its default preset (Top 200) is blocked on first use because it needs an
unofficial Yahoo Finance market-cap snapshot that the build does not ship.
Empty states point to "Database Updates" without a link, and nothing on Home
says the local database is empty. `docs/settings-module.md` and
`docs/database-updates.md` name Settings as the one place that starts a full
update, while `docs/PRODUCT.md` treats Settings as a utility.

## Decision

- The local database state and the data update are owned by the app shell, not
  by Settings. A persistent indicator shows the local database state on every
  screen and opens a compact Data panel (run, cancel, progress, failures).
- Home and every data-dependent empty state offer the same single action. When
  the local database is empty, Home leads with it. Home keeps its customizable
  layouts (owner decision in #500).
- The single action downloads all active CVM companies for the last 5 years,
  from official CVM sources only. It needs no unofficial ranking and no
  configuration. The company list appears first and statements fill in as they
  are processed.
- Settings keeps preferences and maintenance only. It is never a required step
  to see data.
- Data updates stay explicit and logged. The indicator and panel only read local
  state; they never start network work on their own.

## Considered options

- A full-screen first-run gate before Home (removed in `6dbd29f`): rejected
  because it blocks Home and only helps on the first launch.
- A new top-level Data workspace: rejected because it adds a module for what is
  one action plus status.
- Top N by market cap as the default scope: rejected because it depends on an
  unofficial source with 236 hand-mapped tickers and fails on first use.

## Consequences

- `/settings/updates` is retired; `docs/settings-module.md` and
  `docs/database-updates.md` must be revised to match.
- First-run duration for all active companies is unmeasured. If it is still too
  slow after the efficiency fixes, the default scope is revisited (company list
  first, statements on demand per company).
