# AGENTS.md

Canonical operating rules for AI agents in this project. English-only.

## 1. How to read this file

- This is the **default** contract. Read it once per session.
- For runtime architecture, data sources, Excel exports, development, build/release, troubleshooting, and product workflows, start with the canonical docs linked from `README.md`.
- For macro product direction and feature fit, read `docs/PRODUCT_DIRECTION.md`.
- For product principles, minimalism, and UI hierarchy standards, read `docs/PRODUCT.md` and `docs/DESIGN.md`.
- For a full map of every folder, workflow, and doc status, see `docs/reference/repository-map.md`.
- For long-running autonomous PRs, also read `docs/governance/autonomous-mode.md`.
- Before touching `src/` or `apps/api/`, also read `docs/CONTEXT.md`.
- Before implementing or reviewing any Vite UI screen in `apps/desktop-web`, read and follow [docs/skills/CVMANALYTICS_VITE_UI_SKILL.md](docs/skills/CVMANALYTICS_VITE_UI_SKILL.md).
- Before changing the Indicators module, read `docs/reference/indicators-module.md`.
- Before changing Energy/Utilities system-driver scope, read `docs/decisions/energy-utilities-driver-pilot-contract.md` and verify current source/readiness evidence in the active repo.
- Active reference docs live in `docs/` and `docs/reference/`. ADRs live in `docs/decisions/`. Migration history lives in `docs/archive/migration/` (all phases complete as of v0.17.0).
- `archive/` at the repository root is historical governance and experiment material. Do not treat it as a current contract.

## Active Application Source of Truth

- The active frontend is the Vite app in `apps/desktop-web`.
- The active runtime integration is the desktop pywebview/backend bridge:
  `apps/desktop-web/src/lib/bridge/adapter.ts` -> `window.pywebview.api` ->
  `desktop/bridge.py` / `desktop/bridge_api/`.
- Do not create or modify Next.js routes, pages, layouts, API routes, or components. The old `apps/web` Next.js app was removed from the active tree.
- Do not infer architecture from archived, migration, release, or legacy docs.
  Inspect `apps/desktop-web`, `desktop/`, `src/`, and `apps/api` before changing UI/runtime/backend behavior.
- If a file appears legacy, orphaned, or unused, report the evidence instead of modifying it.

## UI Language Policy

- **Target UI language: English-only.** New user-facing strings in `apps/desktop-web` must be English.
- The current app still contains **mixed Portuguese/English** labels and routes. Do not claim the UI is already fully English.
- Treat existing Portuguese UI strings as cleanup debt, not the desired convention. Migrate them to English when touching that surface; do not add new Portuguese user-facing strings.
- Do not blindly translate source data: company names, tickers, CVM/B3 terms, raw filings, and financial statement line items stay as published.

## Product Workflow and Workspace Ownership

CVMAnalytics is a local-first financial analyst workbench for Brazilian companies. It is not “CVM data plus charts.” The product should support this analyst path:

```text
Coverage Universe
-> Sector Work
-> Company Work
-> Critical Factors
-> Forecasts / Models
-> Valuation
-> Thesis / Recommendation
-> Audit-ready Export
```

- Every material feature must support a step in this path, have an owning workspace, identify its source class, define what persists locally, and show failure/offline behavior.
- Do not optimize the core product for generic dashboards, CRUD administration, casual browsing, decorative chart galleries, mobile-first use, or untraceable AI summaries.
- Separate verified implementation from product direction. A route, bridge/API method, database table, source module, export path, or test is required before claiming a workflow is implemented.
- When feature ownership is unclear, write a short product note before writing code.

Workspace boundaries:

- **Indicator Library:** macro, sector, system, market, and benchmark indicators that open without selecting a company, distributor, plant, asset, parcel, ticker, fuel product, state, or economic group.
- **Company Workspace:** issuer-level financial and operational metrics, company-specific KPIs, risks, peers, valuation, and evidence.
- **Asset / Plant workflows:** plant, parcel, operational asset metrics, and unit economics requiring entity selection.
- **Model Workspace:** assumptions, scenarios, forecast outputs, sensitivities, and explicit calculated values.
- Do not place company-specific, plant-specific, parcel-specific, or unit-economic indicators in the general Indicator Library.

## 2. Principles

1. **Inspect before editing.** Read the file being changed and at least one caller or consumer. Never fabricate project state.
2. **Prefer small, reviewable changes.** One concern per edit. If a task spans multiple concerns, finish one cleanly, then start the next.
3. **Preserve architecture unless asked to change it.** If architecture must change, say so explicitly and propose the alternative before implementation.
4. **Ask only questions that change scope, correctness, architecture, quality, or destructive risk.** Do not ask permission for reversible decisions inside an already granted scope.
5. **Validate what can be validated.** Run targeted tests first, then the required broader checks. If validation is not possible, state that plainly.
6. **Surface assumptions and risks at the end.** State what could go wrong, what was not verified, and what should be watched.
7. **Do not speculate-engineer.** No memoization without a measured win, no abstraction for hypothetical callers, no dependency or rewrite without evidence.
8. **Match the language of surrounding code and docs.** This does not override the English-only policy for new user-facing Vite UI strings.
9. **Be honest about audit and finding quality.** Do not repeat subagent findings that were not verified against active files.
10. **Data, financial, and modeling work:** prioritize auditability and correctness over speed. Honor `docs/CONTEXT.md`, `docs/data-sources.md`, and the relevant source contract.
11. **UI/design work:** keep output professional, dense, minimal, analyst-grade, responsive, and consistent with the existing design system. Preserve source visibility and avoid decorative dashboard patterns.
12. **Performance work:** measure before and after when practical. Protect startup time, local read latency, memory, CPU, IO, chart/table responsiveness, and packaged behavior.
13. **Autonomous long-running work:** route through `docs/governance/autonomous-mode.md`. Interactive sessions use this file only.
14. **Final reports:** include root cause or objective, files changed, decisions, tests and results, remaining risks, and anything not validated.

## Financial Data and Source Contract

Preserve these distinctions whenever they affect interpretation:

- official CVM/B3 vs official external dataset vs external/unofficial vs user import;
- consolidated vs individual statements;
- DFP annual vs ITR quarterly;
- quarterly isolated vs accumulated;
- reported vs transformed vs calculated;
- actual vs estimated or forecast;
- original filing vs restatement;
- recurring vs non-recurring;
- BRL vs thousand BRL vs million BRL and other currencies/scales;
- point-in-time vs period flow;
- source timestamp vs generated timestamp vs as-of date;
- missing value vs zero;
- unavailable vs unsupported vs failed.

- Never silently fallback from official data to external data.
- Never present mocks, placeholders, static definitions, or planned data as real observations.
- Yahoo Finance/yfinance, Google News, and other aggregators are not equivalent to CVM or B3 official data.
- Calculated values must remain traceable through:

```text
number -> formula/transformation -> source -> company/entity -> period -> unit -> timestamp
```

- EBITDA is not cash. Do not substitute it for operating cash flow or free cash flow.
- Financial analysis must preserve the relevant lens: Equity, Credit, IB, DCF, multiples, SOTP, project finance, utilities/concessions, or operational analysis.
- Missing, partial, stale, invalid, or failed data must remain visible. Do not convert missing values to zero to simplify UI logic.

## Storage, Offline, and Performance Contract

- Already-downloaded data must remain readable offline. Opening normal analytical views must not trigger hidden external calls.
- Refresh, import, update, and rebuild operations must be explicit, scoped, observable, and logged.
- Preserve downloaded files, source snapshots, import metadata, and prior valid local state when refreshes fail.
- Prefer bounded UI read models, indexes proven by query plans, caches, and rebuildable marts over repeated scans of high-cardinality raw tables.
- Do not add high-cardinality sector detail directly to the main app databases when a managed analytical store and compact marts are required.
- New heavy ingestion must define raw snapshot retention, lineage, managed storage, bounded read paths, manifests/registration where required, telemetry, failure recovery, and release validation.
- Benchmark destructive storage/index/schema changes on a copied database first. Keep rollback commands and do not replace a live database without an explicit backup-and-swap plan with the app stopped.
- Do not delete raw files or `source_snapshots` merely because a mart or cache exists.
- Avoid repeated external calls when local snapshots or caches should serve the request.

## Energy / Utilities Driver Contract

The approved pilot question is:

> Is the Brazilian power system becoming structurally tighter or looser, which observable drivers explain the change, and which types of electricity companies are most exposed?

The approved analytical families are:

1. SIN load and demand pressure.
2. Generation supply and mix.
3. Hydro buffer and inflow.
4. System price confirmation.
5. Capacity and firm-supply headroom.

Rules:

- Analyze sector/system evidence before company conclusions.
- Load, generation mix, and hydrology are explanatory drivers. Price is confirmatory and must not be used circularly as both cause and proof.
- Company exposure is a hypothesis until ownership, contracts, regulatory context, and financial modeling establish a link. Do not claim company financial causality from system indicators alone.
- Capacity and firm-supply headroom remain blocked until an approved aggregate contract exists. Do not add or directly compare MW and MWmed.
- Do not assume PLD, CMO, capacity, or any provider is currently ready. Verify local rows, source status, bridge/read methods, and the latest decision/reference docs before implementation claims.
- Company-specific, plant, parcel, and asset analysis remain outside the general system-driver library.

## Token and Context Efficiency Protocol

Use context-efficient tools before reading large files.

### Serena MCP

When Serena is available, use it first for code navigation, symbol search, reference lookup, and refactoring analysis.

Prefer Serena for:

- finding symbols, components, functions, classes, and references;
- understanding cross-file dependencies;
- inspecting file outlines before reading full files;
- planning refactors across multiple files;
- checking where a function/component is used before editing it.

Avoid reading full files unless:

- the exact implementation is required;
- Serena's symbolic overview is insufficient;
- debugging requires full local context.

At the beginning of a new session, activate the current project with Serena and read Serena's initial instructions if they are not already loaded.

### Repomix

Use Repomix outputs only for broad repository understanding, onboarding, architecture review, or high-level planning.
Do not rely on compressed Repomix output for precise implementation changes. Inspect real source files or use Serena for exact edits.

### Cost Discipline

- Before large changes, inspect the relevant subsystem first.
- Avoid broad grep/read loops across the whole repository.
- When the task changes substantially, start a fresh session or compact/clear the context.
- Prefer targeted plans, small diffs, and focused validation commands.

## 3. Plan-mode rule (risk-based, not ceremony-based)

- **Low risk** (typo, copy fix, isolated function, formatter swap, single-component prop tweak): inspect, act, and provide a one-line summary.
- **Medium risk** (multi-file refactor, new component, non-trivial logic change, new hook): state the plan in 2–4 lines, then act.
- **High risk** (architecture, data model, DB schema, financial calculations, auth/security, destructive operations, repo-wide changes, dependency changes): plan in full and wait for approval unless the user already explicitly approved that exact implementation scope.
- **“Only plan” / “plan only” / “draft”:** plan; do not edit files.
- **“Do next” / “go” / “proceed”:** proceed with the agreed step without re-asking unless new risk appears.

## 4. Validation expectations

- Desktop UI TypeScript: run `npm --prefix apps/desktop-web run typecheck` after any desktop UI TS/TSX edit.
- Frontend behavior: run the relevant targeted test, then `npm --prefix apps/desktop-web run test`, `typecheck`, and `build` when the change warrants the broader pass.
- Indicators module: use the targeted `CountryKpisPage` test and follow `docs/reference/indicators-module.md`.
- Python: run `pytest tests/` for desktop/core paths and `pytest apps/api/tests/` when intentionally editing the hosted API or shared API contracts.
- UI-observable changes: start the real dev runtime when feasible and verify loading, empty, error, partial data, responsiveness, and normal laptop-width behavior.
- Data changes: validate against known fixtures or real sandbox snapshots, not only type signatures.
- Heavy ingestion/storage changes: run the managed-ingestion and storage-budget guardrails documented in `docs/build-release.md`.
- Release-sensitive work: validate the packaged desktop artifact, Documents data root, offline reads, clean install, update over a prior version, included files, updater/checksum behavior, relaunch, logs, permissions, and Excel-open behavior.
- If validation is skipped, say why explicitly in the wrap-up.

## 5. Task modes

Each task type has a minimal extra rule on top of the principles. Match the mode to the work; do not blend unrelated work.

### Bugfix

- Record symptom, expected behavior, actual behavior, reproduction, and evidence.
- Isolate the failing layer: external source, download, parsing, validation, database, cache, backend, IPC/bridge, frontend state, filters, rendering, build, release, or updater.
- Reproduce or read the error trace before proposing a fix.
- Prioritize hypotheses and fix the root cause, not the symptom.
- Add a regression test when the bug came from a previously untested path.
- “Works in dev” is not proof for packaged/release bugs.

### Feature

- Confirm the workflow step and owning workspace before designing.
- Confirm source class, local persistence, offline behavior, failure state, and smallest useful first version.
- Prefer additive changes over rewrites.
- Do not describe planned data or workflows as implemented.
- Validate end-to-end before declaring done.

### Refactor

- **No behavior change.** State what is preserved and what is moving.
- Map active imports, scripts, tests, docs, and packaging references before moving files.
- Do not reorganize only for aesthetics.
- Verify with typecheck and tests; do not add new features in the same pass.
- If a refactor requires a behavior change, stop and re-scope.

### UI / UX / design

- Honor the existing design system: Tailwind tokens, `@base-ui/react`, sector colors through `getSectorColor`, and the OKLCH palette.
- Keep the app serious, minimal, dense, and analyst-oriented rather than CRUD-like or SaaS-template-like.
- Prefer summary before detail, clear filters, predictable navigation, responsive tables, and detail on demand.
- For large tables or many assets, consider search, filters, grouping, drill-down, virtualized rendering, and charts on demand.
- Do not allow detail drawers/panels to make the main table unusable at normal laptop widths. Provide an explicit close path when a panel is user-opened.
- Verify loading, empty, error, partial, responsive, keyboard, and performance-perception states.
- Preserve creative latitude: propose 2–3 visual options when the brief is genuinely unconstrained.

### Data / modeling / financial logic

- Read `docs/CONTEXT.md` and `docs/data-sources.md` first.
- Prioritize auditability and correctness over speed.
- Validate against known fixtures or source-backed sandbox data.
- Never infer GICS classifications from CVM/B3/ticker/name. Follow `docs/reference/gics-import.md`.
- Keep company master data converging toward one source of truth for name, ticker, CNPJ, CVM id, CVM sector, GICS sector/subindustry, conglomerate/subsidiary relationships, source, and timestamp.
- Preserve formula, source, company/entity, account, period, unit, transformation, and timestamp lineage for calculated values.

### Excel / export

- Read `docs/excel-exports.md` before changing workbook generation.
- Never use merged cells. Use Center Across Selection when visual spanning is required.
- Freeze panes logically.
- Separate inputs, calculations, and outputs.
- Keep formulas simple and traceable.
- Standardize dates, units, currencies, and scales.
- Separate historical and forecast periods.
- Preserve hierarchy and subtotals.
- Include relevant balance sheet, cash flow, debt, source, and data-quality checks.
- Show negatives in parentheses and zeros as `-`.
- Generated files must open without repair.

### Release / updater

- Read `docs/build-release.md` first.
- `desktop/__version__.py` is the runtime version source. Frontend package metadata is not the shipped product version source.
- Verify release tag/commit, bundled runtime version, generated build provenance, and packaged validation evidence in that order.
- Accepted update tags are stable semantic versions or the documented `-rc.N` prerelease form; malformed tags must not be offered.
- Never bundle or overwrite user data under `%USERPROFILE%\Documents\CVMAnalytics`.
- Verify the flat ZIP root contract, checksum, allowlisted swap, rollback snapshot, and update-over-previous-version behavior.

### Docs / research

- Do not edit application code in this mode.
- Output documentation, findings, decisions, or recommendations.
- Cite active file paths and line numbers when referencing code.
- Mark gaps as “Needs validation” rather than presenting them as implemented guarantees.
- Update the canonical document and remove or archive contradictory instructions when the evidence is sufficient.

### Autonomous (opt-in only)

- Route through `docs/governance/autonomous-mode.md`.
- Default interactive workflow does not require issue-first, worktrees, risk labels, or draft PRs.

## 6. Source-of-truth pointers

- `README.md` — project overview and canonical documentation map.
- `docs/architecture.md` — active runtime architecture and boundaries.
- `docs/data-sources.md` — source classes, caveats, managed storage, and auditability rules.
- `docs/excel-exports.md` — Excel workbook standards and validation.
- `docs/development.md` — development setup and command map.
- `docs/build-release.md` — build, storage guardrails, release, updater, and packaged validation contract.
- `docs/troubleshooting.md` — runtime, data, updater, and export troubleshooting.
- `docs/product-workflows.md` — implemented vs planned analyst workflows.
- `docs/PRODUCT_DIRECTION.md` — analyst workflow, workspace ownership, and feature-fit rules.
- `docs/PRODUCT_DEVELOPMENT_CHECKLIST.md` — next-step product development checklist.
- `docs/PRODUCT.md` — product principles, minimalism, and target users.
- `docs/DESIGN.md` — design system and UI review rules.
- `docs/COMO_RODAR.md` — how to run locally in Portuguese.
- `docs/CONTEXT.md` — domain rules for `src/` and `apps/api/`.
- `docs/active-project-map.md` — concise active path and command map.
- `docs/dev-runtime-and-data-paths.md` — dev modes, data paths, read/write policy, and lockfile.
- `docs/database-updates.md` — Update Base flow, settings, reset, and Data Coverage relationship.
- `docs/company-on-demand-updates.md` — per-company refresh, no-history companies, and status badges.
- `docs/release-process.md` — versioning, build, and what does not require a release.
- `docs/reference/indicators-module.md` — Indicator Library boundary, active module shape, and validation.
- `docs/decisions/energy-utilities-driver-pilot-contract.md` — approved Energy/Utilities driver question, families, boundaries, and caveats.
- `docs/reference/` — active reference docs, including repository map, GICS import, and API contracts.
- `docs/decisions/` — durable architectural and product decisions.
- `docs/governance/autonomous-mode.md` — opt-in heavy contract for autonomous PRs.

## 7. What NOT to do

- Do not create, restore, or modify Next.js source. The legacy `apps/web` app was removed.
- Do not open PRs as draft merely because a change touches multiple files. Draft only when the work itself is incomplete.
- Do not use the GitHub CLI (`gh`) or `scripts/release/pr_complete.ps1` for routine merges. Standard `git push` plus manual or auto-merge is sufficient.
- Do not insist on issue-first, worktrees, lanes, or risk labels for interactive sessions. These belong to autonomous mode only.
- Do not load stale planning docs as active context. If references point to deleted plans such as `STUDENT_PACK_PLAN`, `WEBAPP_TRANSFORMATION_PLAN`, or `V2_PHASE1_BACKEND`, treat them as stale.
- Do not follow deleted `CLAUDE.md`, `CONTRIBUTING.md`, or `docs/GOVERNANCE_QUICK_REFERENCE.md`; their durable rules were consolidated here.
- Do not assume Vercel or Railway is the canonical product runtime. The canonical product is the Windows `CVMAnalytics.exe` desktop app built by `desktop/build_desktop.ps1`.
- Do not hide source failures, stale data, missing values, partial coverage, or bridge errors to make a screen appear complete.
- Do not mix official, external, calculated, estimated, consolidated, individual, quarterly, accumulated, or differently scaled values without explicit labels.

## 8. Canonical product

- **Shipped runtime:** `dist/CVMAnalytics/CVMAnalytics.exe`, built through `desktop/build_desktop.ps1`.
- **Architecture:** pywebview serves the static Vite SPA from `apps/desktop-web` / `_internal/desktop-web` and talks to Python through `desktop/bridge.py` and `desktop/bridge_api/`.
- **Data root:** packaged users store runtime data under `%USERPROFILE%\Documents\CVMAnalytics`.
- **`apps/desktop-web`** is the only UI source compiled into the desktop bundle.
- **`apps/api`** is an HTTP API/development backend adapter. It is not a frontend and is not packaged as the desktop UI.
- Validate product bugs against the packaged desktop app and the Documents data root when packaging, installation, updater, permissions, paths, offline behavior, or bundled files may be involved.
