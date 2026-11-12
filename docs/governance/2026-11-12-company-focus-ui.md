# Company-focused UI candidate

Date: 2026-11-12. Issue #487, parent #486. Base commit:
`4de7fe4581d0622d45323e58a476d4e14c45ba3b` (includes #452 and external deliveries).

## Changes

- Home, Companies, Sectors and Indicators are primary. Settings is always visible.
- Coverage and News live under a native More disclosure, with their active module
  named on deep links. Pointer selection, Enter/Tab, Escape/focus return, focus
  leaving the disclosure and outside pointer dismissal are supported.
- Coverage gains a command-palette entry; existing commands and routes remain.
- Empty Home offers Open Companies. The existing explicit recommended action
  adds only Watchlist and Market Price. No automatic preset or storage migration.
- Database Monitor, News and Priority Queue stay registered/configurable. The
  compact status/job summary, data-source distinctions and failure states remain.

## Validation

- Five focused RED assertions exposed missing behavior; six focused tests pass.
- Frontend suite: 135 passed. Typecheck and production build passed. Existing
  empty vendor chunk warning remains. No dependency/lockfile changes.
- Headless Edge against the actual Vite browser preview: Enter/Tab opens and
  reaches Coverage; Escape closes and restores summary focus; selecting Coverage
  closes the disclosure and identifies the active route; Open Companies works.
- Explicit preset and reload preserve the two selected widgets. Saved v4 News
  and Priority Queue layouts/configs survive reload. Explicitly empty layouts
  remain empty. Native disclosure and Home screenshots inspected at 1280x800
  and 1024x768; primary navigation and Settings fit both widths.
- Browser preview is explicitly labeled browser fallback; no fake bridge or
  source observations were injected. Local-only raw evidence is retained in
  `tmp/487-validation/` in the issue worktree.

## Pending acceptance

Real desktop and packaged company/history/Excel/offline acceptance has not run.
The preceding isolated desktop launch attempt was rejected by automatic
permission review with only `blocked by policy`. Browser checks do not replace
that gate. Keep this PR and issues #487/#486 open until exact-candidate acceptance
is recorded. No release, ingestion, repair, schema or user-data change is implied.
