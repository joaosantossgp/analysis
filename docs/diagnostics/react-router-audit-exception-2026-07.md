# React Router Audit Exception - 2026-07

Audit date: 2026-07-28

## Status

This is an accepted temporary exception, not a clean audit.

The partial npm audit remediation keeps these resolved package versions in
`apps/desktop-web/package-lock.json`:

- `vite` 6.4.3
- `postcss` 8.5.24
- `@babel/core` 7.29.7
- `react-router-dom` 7.18.2
- `react-router` 7.18.2

After `npm --prefix apps/desktop-web ci`, `npm --prefix apps/desktop-web audit --json`
reports two remaining high severity records:

- `react-router`: GHSA-qwww-vcr4-c8h2, "React Router: RSC Mode CSRF Bypass
  Allows Action Execution Before 400 Response", range `>=7.12.0 <8.3.0`.
- `react-router-dom`: direct dependency affected via `react-router`.

The remaining records arise from direct `react-router-dom@7.18.2` pinning
`react-router@7.18.2`.

## Registry Facts

Confirmed from the npm registry on 2026-07-28:

- `react-router@8.3.0` is the fixed package version for GHSA-qwww-vcr4-c8h2,
  but declares Node engine `>=22.22.0`.
- `react-router-dom@latest` is `7.18.2`.
- `react-router-dom@latest` depends on `react-router` 7.18.2.

## Frontend Routing Evidence

The active frontend uses the Vite desktop app under `apps/desktop-web`.
Inspection on 2026-07-28 found:

- `apps/desktop-web/src/App.tsx` imports `HashRouter`, `Routes`, `Route`, and
  `Navigate` from `react-router-dom`.
- `apps/desktop-web/src/App.tsx` wraps the app in `<HashRouter>` and defines
  client-side `<Routes>`.
- `apps/desktop-web/vite.config.ts` builds a static SPA with Vite, with
  `base: "./"` and no SSR or RSC plugin configuration.
- Targeted search found no confirmed React Server Components routing setup
  (`RSC`, `react-server`, `HydratedRouter`, `RouterProvider`, or
  `createBrowserRouter`) in the active frontend files inspected.

This evidence only describes the current configuration. It does not claim that
GHSA-qwww-vcr4-c8h2 is inapplicable to this application.

## Exception Handling

Re-evaluate this exception on every dependency refresh and every release.

Remove this exception when either condition is met:

- a compatible fixed `react-router-dom` release is available and validated in
  this app; or
- a routing migration is validated and removes the affected dependency path.

Until then, audit output is expected to remain non-zero with the two high
React Router records above.
