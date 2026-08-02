# Interview Dev Reliability Design

## Goal

Make the shared-Documents desktop development flow predictable for an interview without altering downloaded financial data.

## Scope

Two focused fixes:

1. Close the complete Vite process tree when desktop development mode exits or Vite startup times out on Windows.
2. Resolve a placeholder local company name such as `CVM_25658` to its verified catalog identity for presentation in active company surfaces.

## Design

### Vite lifecycle

`desktop/app.py` launches `npm.cmd run dev`. On Windows, that command creates a child Node/Vite process. Terminating only the `Popen` parent leaves the child listening on port 5173. Add one private, platform-aware cleanup helper and use it for both the startup-timeout path and normal shutdown. On Windows it terminates the process tree rooted at the recorded Vite parent PID; elsewhere it retains the existing parent-process termination behavior. Cleanup remains limited to the process started by this desktop instance.

### Company display identity

The local financial database may retain a provisional `CVM_<id>` name. The active catalog and local market-cap snapshot have an authoritative display identity for the same CVM ID. The company read service will use that verified identity only when the stored name is a placeholder. Financial data, CVM ID, ticker, source values and stored rows remain unchanged. The result applies consistently to directory search, command search and company detail payloads that consume the shared result model.

## Constraints

- Keep `python -m desktop.app --dev` on `%USERPROFILE%\Documents\CVMAnalytics` by default.
- Do not modify Documents databases, snapshots, caches, financial rows or source lineage.
- Do not use mock bridge data.
- Preserve existing real names when they are not placeholders.
- Add regression tests before implementation and observe each fail before its matching code change.
- Commit directly to `main`; no pull request.

## Validation

- Targeted Python tests for Vite process cleanup and placeholder identity display.
- `pytest tests -q`.
- `npm --prefix apps/desktop-web run typecheck`.
- `npm --prefix apps/desktop-web run test`.
- `npm --prefix apps/desktop-web run build`.
- Manual Windows lifecycle check: start desktop dev, close it, verify ports 5173/5174 are free, then start it again.
- Shared-data smoke check: directory and company detail show AgroGalaxy instead of `CVM_25658`; Petrobras remains readable with annual and quarterly data.

## Out of scope

- Increasing downloaded-company coverage.
- Rebuilding financial marts.
- Changing market-cap provider or treating Yahoo Finance as an official source.
- Packaged release changes.
