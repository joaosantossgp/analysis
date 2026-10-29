# AGENTS.md

Canonical operating rules for AI agents in this project. Rules live here;
domain contracts live in the docs this file points to. English-only.

## 1. Start here

- Read this file once per session.
- Read `docs/STATUS.md` for the current version, release state, active work,
  and recent decisions.
- Use `README.md` ("Canonical Documentation") as the doc index and
  `docs/reference/repository-map.md` for paths, folders, workflows, and what is
  historical.

Read before touching a specific area:

| Area | Read first |
|---|---|
| `src/` or `apps/api/` | `docs/CONTEXT.md` |
| Any Vite UI screen in `apps/desktop-web` | [`docs/skills/CVMANALYTICS_VITE_UI_SKILL.md`](docs/skills/CVMANALYTICS_VITE_UI_SKILL.md), `docs/PRODUCT.md`, `docs/DESIGN.md` |
| Data, sources, storage, financial logic | `docs/data-sources.md` (source classes, storage rules, interpretation distinctions) |
| New features or feature fit | `docs/PRODUCT_DIRECTION.md` (analyst workflow, workspace ownership, admission rules) |
| Indicators module | `docs/reference/indicators-module.md` |
| Energy/Utilities system drivers | `docs/decisions/energy-utilities-driver-pilot-contract.md`, then verify current source/readiness evidence in the repo |
| GICS classification | `docs/reference/gics-import.md` |
| Excel workbooks | `docs/excel-exports.md` |
| Build, release, updater | `docs/build-release.md`, `docs/release-process.md` |
| Dev modes and data paths | `docs/development.md`, `docs/dev-runtime-and-data-paths.md` |
| Long-running autonomous PRs | `docs/governance/autonomous-mode.md` |

Docs whose status says withdrawn, historical, or superseded, and everything
under `docs/archive/`, are reference only, not current contracts.

## 2. Active application

- Shipped product: `dist/CVMAnalytics/CVMAnalytics.exe`, built by
  `desktop/build_desktop.ps1`. Packaged users keep runtime data under
  `%USERPROFILE%\Documents\CVMAnalytics`.
- The only UI is the Vite app in `apps/desktop-web`. Runtime integration:
  `apps/desktop-web/src/lib/bridge/adapter.ts` -> `window.pywebview.api` ->
  `desktop/bridge.py` / `desktop/bridge_api/`.
- `apps/api` is an HTTP adapter for tests and dev/hosted access, not the
  desktop UI. Vercel/Railway are not the canonical runtime.
- Do not create, restore, or modify Next.js code. `apps/web` was removed.
- Inspect `apps/desktop-web`, `desktop/`, `src/`, and `apps/api` before
  changing behavior. Do not infer architecture from archived, migration,
  release, or legacy docs.
- If a file looks legacy, orphaned, or unused, report the evidence instead of
  modifying it.

## 3. Language

- All documentation and new user-facing UI strings must be English. Existing
  Portuguese docs and UI strings are cleanup debt: translate them when touching
  them, and never add new Portuguese text.
- The UI is still mixed Portuguese/English. Do not claim it is fully English.
- Do not translate source data: company names, tickers, CVM/B3 terms, raw
  filings, and financial statement line items stay as published.

## 4. Product guardrails

CVMAnalytics is a local-first analyst workbench for Brazilian companies, not
"CVM data plus charts". Every material feature must support a step in
`Coverage Universe -> Sector Work -> Company Work -> Critical Factors ->
Forecasts / Models -> Valuation -> Thesis / Recommendation -> Audit-ready
Export`, have an owning workspace, identify its source class, define what
persists locally, and show failure/offline behavior. Details and workspace
boundaries: `docs/PRODUCT_DIRECTION.md`.

- Do not place company-, plant-, parcel-specific, or unit-economic indicators
  in the general Indicator Library.
- A route, bridge/API method, table, source module, export path, or test is
  required before calling a workflow implemented.
- Never silently fall back from official to external data, never present mocks
  or planned data as real observations, and never turn missing values into
  zero. Keep missing, partial, stale, and failed data visible.
- Keep calculated values traceable: number -> formula -> source -> entity ->
  period -> unit -> timestamp.
- Already-downloaded data must stay readable offline. Normal views must not
  trigger hidden external calls; refreshes must be explicit and logged.
- When feature ownership is unclear, write a short product note before code.

## 5. Working principles

1. **Inspect before editing.** Read the file being changed and at least one
   caller or consumer. Never fabricate project state.
2. **Small, reviewable changes.** One concern per edit.
3. **Preserve architecture** unless asked to change it; propose alternatives
   before implementing.
4. **Ask only questions that change scope, correctness, architecture, quality,
   or destructive risk.**
5. **Validate what can be validated**, targeted first, then broader. Say
   plainly what was not validated.
6. **No speculative engineering:** no memoization without a measured win, no
   abstraction for hypothetical callers, no dependency or rewrite without
   evidence.
7. **Match the style of surrounding code and docs.**
8. **Be honest about findings.** Do not repeat subagent findings not verified
   against active files.
9. **Context efficiency:** use symbol/reference search and targeted reads
   before reading large files; avoid repo-wide grep/read loops.
10. **Final reports** include objective or root cause, files changed,
    decisions, tests and results, remaining risks, and anything not validated.

## 6. Risk-based planning

- **Low risk** (typo, copy fix, isolated function, single-component tweak):
  inspect, act, one-line summary.
- **Medium risk** (multi-file refactor, new component, non-trivial logic): state
  the plan in 2-4 lines, then act.
- **High risk** (architecture, data model, DB schema, financial calculations,
  auth/security, destructive operations, repo-wide changes, dependencies): plan
  in full and wait for approval unless that exact scope was already approved.
- "Plan only" / "draft": do not edit files. "Go" / "proceed": continue the
  agreed step without re-asking unless new risk appears.

## 7. Validation

- Desktop UI TS/TSX edits: `npm --prefix apps/desktop-web run typecheck`.
- Frontend behavior: targeted test, then `npm --prefix apps/desktop-web run
  test`, `typecheck`, and `build` when warranted.
- Indicators module: the targeted `CountryKpisPage` test.
- Python: `pytest tests/`; add `pytest apps/api/tests/` when editing the API or
  shared API contracts.
- UI-observable changes: run the real dev runtime when feasible and check
  loading, empty, error, partial, responsive, and laptop-width states.
- Data changes: validate against fixtures or real sandbox snapshots.
- Heavy ingestion/storage: run the guardrails in `docs/build-release.md`.
- Release-sensitive work: validate the packaged artifact as described in
  `docs/build-release.md`. "Works in dev" is not proof for packaged bugs.
- If validation is skipped, say why.

## 8. Task modes

- **Bugfix:** record symptom, expected vs actual, reproduction, and evidence.
  Isolate the failing layer, fix the root cause, and add a regression test for
  previously untested paths.
- **Feature:** confirm workflow step, owning workspace, source class,
  persistence, offline and failure behavior, and the smallest useful version.
  Prefer additive changes. Validate end to end.
- **Refactor:** no behavior change. Map imports, scripts, tests, docs, and
  packaging references before moving files. No aesthetic-only moves.
- **UI/UX:** follow the Vite UI skill and `docs/DESIGN.md` (Tailwind tokens,
  `@base-ui/react`, `getSectorColor`, OKLCH palette). Dense, minimal,
  analyst-grade. Detail panels must not make the main table unusable at laptop
  width and need an explicit close path. Offer 2-3 visual options when the brief
  is unconstrained.
- **Data/modeling:** read `docs/CONTEXT.md` and `docs/data-sources.md`. Never
  infer GICS from CVM/B3/ticker/name. Preserve lineage for calculated values.
- **Excel/export:** follow `docs/excel-exports.md` (no merged cells, traceable
  formulas, negatives in parentheses, files open without repair).
- **Release/updater:** `desktop/__version__.py` is the runtime version source.
  Never bundle or overwrite user data. Follow `docs/build-release.md`.
- **Docs/research:** do not edit application code. Cite active paths and
  lines. Mark gaps as "Needs validation". Update the canonical doc and archive
  contradictory ones. Update `docs/STATUS.md` when state or decisions change.
- **Autonomous (opt-in only):** route through
  `docs/governance/autonomous-mode.md`. Interactive sessions do not need
  issue-first, worktrees, lanes, risk labels, or draft PRs.

## 9. Do not

- Open PRs as draft just because they touch many files.
- Use `gh` or `scripts/release/pr_complete.ps1` for routine merges; `git push`
  plus manual or auto-merge is enough.
- Load stale planning docs as active context, or follow deleted `CLAUDE.md`,
  `CONTRIBUTING.md`, or `docs/GOVERNANCE_QUICK_REFERENCE.md`.
- Hide source failures, stale data, missing values, partial coverage, or bridge
  errors to make a screen look complete.
- Mix official, external, calculated, estimated, consolidated, individual,
  quarterly, accumulated, or differently scaled values without explicit labels.
