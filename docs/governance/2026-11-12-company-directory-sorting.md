# Companies directory ordering validation

Date: 2026-11-12. Issue #452, parent #486. Base: `116644168ca6eb90641be647f51c82fc7294701b`.

## Behavior and scope

The desktop bridge previously discarded the requested sort; the UI sorted only
its current page. It now validates and forwards the selected column/direction.
The service reuses its lightweight raw-SQL/ready-mart directory and local
catalog/snapshot assembly, sorts enriched metadata, and only then slices a page.
This deliberately avoids dynamic SQL and loading financial statement rows.
Years uses the existing annual-year map before ordering; other columns only fetch
years for the returned page. No query-layer schema or financial logic changed.

Text is case-insensitive; missing values stay last in both directions, ties use
ascending CVM codes. Page-cache keys include ordering. Existing service/API
callers without sorting keep their defaults. The frontend renders bridge order;
explicit mock mode also sorts its entire fixture list before slicing.

## Evidence

- Regression RED: 18 Python failures and two separate frontend failures exposed
  ignored sort parameters, page-local missing-first ordering and unsorted mocks.
- Focused Python: 23 passing cases, including all eight columns, both directions,
  ties, missing values, one-row pages, cache direction changes, catalog search,
  GICS filtering, raw and ready-mart paths, network denial and page-only year reads.
- Full Python/API: 1,093 passed, 1 skipped; two existing dependency deprecations.
  Process-local database/path overrides were removed and USERPROFILE redirected
  to a temporary validation profile. All regression databases are temporary.
- Frontend tests, typecheck and production build passed. Existing empty vendor
  chunk warning remains. No dependency or lockfile change.
- Independent Ponytail review identified the mock-ordering regression; fixed
  with its own failing-then-passing adapter test.

## Limits

The automatic permission review rejected launching the isolated desktop fixture,
reporting only `blocked by policy`. Real-window inspection was not performed.
This is automated behavior validation, not packaged acceptance or release
certification. No ingestion, original user-data repair, migration or release was
performed. Exact integrated desktop/Excel/offline acceptance remains in #487.
