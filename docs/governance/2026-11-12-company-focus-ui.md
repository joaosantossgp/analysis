# Company-focused UI candidate

Date: 2026-11-12. Issue #487, parent #486, owner decisions #500.
Base: `4de7fe4581d0622d45323e58a476d4e14c45ba3b`.

## Approved revision

- Home remains customizable; empty and saved v4 layouts/configurations survive.
  Optional recommended layout contains Watchlist and Market Price.
- News leaves navigation, palette, routes, widget picker and Settings controls.
  Old routes explain retirement. Saved `top-news` widgets remain registered as
  non-loading retirement placeholders with an explicit remove action. Queue
  evidence remains visible but retired News handoffs are disabled.
- Companies owns Coverage at `/empresas/coverage/*`, plus Assets & Mapping at
  `/empresas/assets`. Old Coverage bookmarks retain query/hash parameters.
  Company-specific Coverage and all universe/queue/capacity/export services remain.
- Coverage waits for bridge readiness and a successful catalog before clearing
  an invalid selection. Loading, errors and unavailable bridge preserve selection.
- Sectors keeps GICS/CVM distinctions, year-based analysis and Macro / Country
  (not equivalent to the indicator explorer). CVM moves to an alternate selector;
  names replace redundant Actions links; technical/tutorial copy is removed.
- Indicators keeps Library plus all five Energy views. The actual entity panel
  moves to Companies and the full health/audit panel to Settings. Legacy section
  links redirect; compact export help links actual actions. Favorites remain.

## Validation

- Regression tests first failed for navigation, retirement and selected-universe
  loss. Focused tests now cover saved layouts, retired widgets without queries,
  queue handoffs, sector links, indicator compatibility and catalog loading/error/
  successful resolution, plus shared catalog bridge readiness. All 147 frontend
  tests, typecheck and production build pass. Existing empty vendor chunk warning remains.
- Headless Edge against real Vite browser fallback checks old Coverage/News links,
  query preservation, saved News widget configuration, selected-universe survival,
  new asset/health destinations, Energy navigation, CVM selector, empty Home and
  optional preset. Navigation fits 1280x800 and 1024x768.
- Independent Ponytail review found no blocking code findings. Backend data,
  schemas, downloads, financial logic and settings storage were not changed.
- Local raw browser evidence: `tmp/487-validation/revised-browser.json` and PNGs.
  Browser fallback does not validate populated database results or real exports.

## Acceptance status before the follow-ups below

At the initial browser-only checkpoint, real desktop and exact packaged
company/history/Excel/offline acceptance had not run. The preceding isolated desktop launch was rejected by automatic permission
review with only `blocked by policy`. This revision does not bypass that denial.
Keep PR #499 and #487/#486 open until exact-candidate acceptance is recorded.
No release, ingestion, repair or user-data migration is implied.
## Desktop preview and Excel follow-up — 2026-11-12

Candidate `f30fc15c0a77c2786607f6f6248dd7bc7b07df9e` passed all five GitHub CI
checks. The owner requested a visible dev preview before further acceptance.

- Real `python -m desktop.app --dev` opened from this worktree with WebView2,
  `runtime_mode=vite-dev`, `frozen=false`, bridge ready and a healthy refresh
  worker. The visible preview uses `tmp/487-desktop/populated-data`, verified
  through `get_app_status`; release-data mode is false.
- SQLite online backup copied the two-company financial/energy databases from
  the retained #485 run-03 fixture into a new isolated root. These are existing
  2022–2024 observations, not a fresh import or a claim of current coverage.
  Source database hashes were unchanged after validation.
- Home and Companies were inspected in the native window. The populated
  directory displayed Petrobras and Vale with partial coverage; Directory,
  Coverage and Assets & Mapping were visible. The preview remains open for the
  owner. This does not claim full populated UI coverage of every moved panel.
- Real bridge reads returned company details, DRE and historical-indicator
  payloads for CVM 9512 and 4170. Both full-history Excel exports succeeded in
  the isolated output directory. No source refresh was requested by these reads.
- Each workbook has 12 sheets, including Model, source_observations,
  value_lineage and financial_qa. Petrobras has 1,367 formulas; Vale 1,319.
  Structural checks found zero merged cells and zero stored Excel error cells.
  Excel 16.0 opened both read-only, recalculated them without formula error
  cells, then closed without saving. Export hashes remained unchanged.
- A new package was built from this source commit using the already validated
  Vite bundle: version `0.30.0-rc.1`, 2,649 files, no bundled `.db` files.
  EXE SHA-256: `94174b26b6eede3b69c5c914edf7e4ba05b494f80f6f6ecdccb0b7f9a96b4184`.
  Build-generated version-file formatting was restored to the committed bytes.
- **Unvalidated at this checkpoint:** launching this package and offline/restart acceptance.
  Automatic review rejected the command preparing and launching the isolated
  offline package with proxy settings: `blocked by policy`, no detailed reason.
  The command did not execute, and no alternate launch was attempted.
  Dev/Excel evidence above must not be promoted to packaged/offline acceptance.

The initial empty dev launch had a missing scratch database directory and a
worker startup error; it was closed gracefully. The populated preview used for
acceptance has a healthy worker. Its startup updater check returned a GitHub 404;
no updater success or absence-of-network claim is made.

Local evidence: `tmp/487-desktop/copied-data.json`, `dev-bridge.json`,
`excel-structure.json`, `excel-native.json`, `bundle-manifest.json` and build logs.
No prototype was created: the existing implementation answered the preview
question directly. A disposable prototype remains an option for comparing new
layout alternatives, not a substitute for runtime validation.

## Owner-confirmed dev offline validation — 2026-11-13

The owner confirmed that the application surfaces were visible and that local
consultation and Excel export worked without internet in the isolated dev-mode
preview. This is operator-reported evidence, following the manual close/reopen
procedure supplied in this chat; it is not an independently captured offline run.
The existing desktop/Excel checks above and this confirmation complete the
bounded dev-mode check. Exact packaged executable/offline acceptance remains
pending; no merge, release or packaged acceptance is implied.

## Final owner acceptance and scope decision — 2026-11-13

The owner manually tested the packaged executable using the supplied isolated
fixture procedure and confirmed successful consultation, Excel export and normal
opening of the exported files in Excel. This is owner-reported packaged evidence,
not an automated reproduction. The source candidate and package identity remain
those recorded above; subsequent commits change documentation only.

The owner explicitly waived the disconnected-network/restart test for the
packaged executable and authorized completion of PR #499 and merge into main
after CI passes. This supersedes the earlier acceptance holds in this record.
The packaged offline test is waived, not passed; local data storage alone is not
proof of offline behavior. The owner-confirmed dev-mode offline result remains
separate. No release publication or broad offline certification is implied.
