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

## Pending acceptance

Real desktop and exact packaged company/history/Excel/offline acceptance has not
run. The preceding isolated desktop launch was rejected by automatic permission
review with only `blocked by policy`. This revision does not bypass that denial.
Keep PR #499 and #487/#486 open until exact-candidate acceptance is recorded.
No release, ingestion, repair or user-data migration is implied.
