# AGENTS.md

Canonical operating rules for AI agents. Rules live here; domain contracts live
in the linked docs. English-only.

## 1. Start here

- Read this file once per session, `docs/STATUS.md` for current version/state/active
  work, `README.md` ("Canonical Documentation") as doc index, and
  `docs/reference/repository-map.md` for paths and what is historical.
- Docs marked withdrawn, historical, or superseded, and `docs/archive/`, are
  reference only, not active contracts.

Read before touching a specific area:

| Area | Read first |
|---|---|
| `src/` or `apps/api/` | `docs/CONTEXT.md` |
| Any Vite UI screen in `apps/desktop-web` | [`docs/skills/CVMANALYTICS_VITE_UI_SKILL.md`](docs/skills/CVMANALYTICS_VITE_UI_SKILL.md), `docs/PRODUCT.md`, `docs/DESIGN.md` |
| Data, sources, storage, financial logic | `docs/data-sources.md` |
| New features or feature fit | `docs/PRODUCT_DIRECTION.md` |
| Indicators module | `docs/reference/indicators-module.md` |
| Energy/Utilities system drivers | `docs/decisions/energy-utilities-driver-pilot-contract.md` (then verify current repo evidence) |
| GICS classification | `docs/reference/gics-import.md` |
| Excel workbooks | `docs/excel-exports.md` |
| Build, release, updater | `docs/build-release.md`, `docs/release-process.md` |
| Dev modes and data paths | `docs/development.md`, `docs/dev-runtime-and-data-paths.md` |
| Issues, triage, skills, domain vocab | `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, `docs/agents/skills.md`, `docs/agents/domain.md` |

## 2. Active application

- Shipped product: `dist/CVMAnalytics/CVMAnalytics.exe` (`desktop/build_desktop.ps1`);
  packaged user data lives in `%USERPROFILE%\Documents\CVMAnalytics`.
- Only UI: Vite app in `apps/desktop-web`. Integration:
  `apps/desktop-web/src/lib/bridge/adapter.ts` -> `window.pywebview.api` ->
  `desktop/bridge.py` / `desktop/bridge_api/`.
- `apps/api` is an HTTP adapter for tests/dev-hosted access, not the desktop UI.
  Vercel/Railway are not canonical runtimes.
- Do not create, restore, or modify Next.js code (`apps/web` was removed).
- Inspect active code (`apps/desktop-web`, `desktop/`, `src/`, `apps/api`) before
  changing behavior; never infer architecture from archived or legacy docs.
- Report evidence for legacy/orphaned files instead of modifying them unasked.

## 3. Language

- All docs and new UI strings must be English. Translate existing Portuguese
  when touching it; never add new Portuguese text. UI is still mixed PT/EN — do
  not claim it is fully English.
- Keep source data as published (company names, tickers, CVM/B3 terms, filings,
  and statement line items).

## 4. Product guardrails

CVMAnalytics is a local-first analyst workbench for Brazilian companies. Every
material feature must support `Coverage Universe -> Sector Work -> Company Work
-> Critical Factors -> Forecasts / Models -> Valuation -> Thesis / Recommendation
-> Audit-ready Export`, name its owning workspace and source class, define local
persistence, and expose offline/failure behavior (`docs/PRODUCT_DIRECTION.md`).

- Never put company-, plant-, parcel-specific, or unit-economic metrics in the
  general Indicator Library.
- Cite an active route, bridge/API method, table, source module, export path, or
  test before calling a workflow implemented.
- Never silently fall back from official to external data, present mocks/planned
  data as real observations, or turn missing values into zero. Keep missing,
  partial, stale, and failed states visible.
- Keep calculated values traceable: `number -> formula -> source -> entity ->
  period -> unit -> timestamp`.
- Downloaded data must stay readable offline. Normal views must not trigger
  hidden external calls; refreshes must be explicit and logged.
- Write a short product note before code when feature ownership is unclear.

## 5. Workflow

GitHub (`joaosantossgp/analysis`, via `gh`) is the source of truth: issues track
work, PRs deliver it.

- **Issues:** `goal` (parent outcome with sub-issues), task (`enhancement`), or
  `bug`. Start at `needs-triage`; `/triage` moves to `ready-for-agent`,
  `ready-for-human`, `needs-info`, or `wontfix` (`docs/agents/triage-labels.md`).
- **Shipping class (ADR 0011):** triage gives every task and bug one of
  `ships:none` (docs, CI, tests, dev tooling: publishes nothing), `ships:pre`
  (small/medium change: pre-release), `ships:release` (large implementation:
  release), or `ships:hotfix` (breaks the current release: immediate release);
  the owner can change it before merge. Only the ticket that makes a large
  implementation reachable carries `ships:release`; earlier parts carry
  `ships:none` and stay unreachable in the app. Goals get no class. The PR check
  takes the highest class of the closed issues and fails when none has one.
- **Branches & PRs:** `<type>/<issue>-<slug>` from `main` (e.g.
  `feat/452-companies-backend-sort`). One PR per issue by default, or batch
  related small issues into one PR. Use `Closes #n` for tasks/bugs and `Refs #n`
  for goals (close goals by hand when sub-issues are done). CI enforces this.
- **PR body:** `.github/PULL_REQUEST_TEMPLATE.md` is the canonical default
  (`Summary`, `Closes/Refs`, `Documentation impact`, `Test plan`, `Notes`). Use
  the vendored `pr` skill's visuals / `Merge Danger` only as optional add-ons
  for complex or high-risk PRs.
- **Merge:** after CI passes, `gh pr merge <n> --merge --delete-branch`. Merge
  base first on stacked PRs.
- **Parallelism (`strict: true` on `main`):** run medium/long independent issues
  in parallel sessions and git worktrees; issues touching the same files must
  block each other (list paths under "Files and areas"). For small quick wins,
  batch related tasks into one PR or serialize merges to avoid `update-branch` +
  re-CI cascades. `dispatching-parallel-agents` is for independent sub-tasks
  within one session, not separate issues.
- **Dev data in worktrees:** dev mode in any worktree uses the shared dev data
  of the main checkout (`<main checkout>/data/dev-runtime`). Before running dev
  mode or data scripts in a worktree whose issue touches database schema,
  migrations, ingestion, refresh or reset, isolate it:
  `.\.venv\Scripts\python.exe scripts/dev/isolate_dev_data.py` (own database
  copy, shared downloads). Add `--full-copy` when the work changes the format,
  location or content of downloaded CVM files. Never isolate the main checkout
  (`docs/dev-runtime-and-data-paths.md`).
- **Plans & status:** `docs/superpowers/` working files are git-ignored; the
  GitHub issue is the spec of record. Update `docs/STATUS.md` when version,
  release state, active work, or a major decision changes.

### Skill tracks (choose the smallest track that fits)

This file's rules override upstream skills. Eleven Ponytail and Matt Pocock
skills live in `.agents/skills/` (`docs/agents/skills.md`); external Superpowers
skills are used when installed (fallback equivalents in `docs/agents/skills.md`).
Where Superpowers and Matt Pocock overlap (TDD, review, debugging), prefer
Superpowers — except `/ponytail-review` is always the single pre-PR review gate.
For a part of a larger implementation, that review checks the PR template line
that unfinished parts are unreachable in the app until the `ships:release`
ticket lands.

- **Fast Track** (`ready-for-agent` Low/Medium issue with closed scope):
  `using-git-worktrees` -> `ponytail` + `test-driven-development` ->
  `pre_pr_check.py` -> `/ponytail-review` -> PR (template) -> CI -> merge.
  *Skip `brainstorming`, `writing-plans`, `pr`, and `finishing-a-development-branch`.*
- **Full Track** (new idea/goal, High risk, or open design):
  `/grill-me` or `/grill-with-docs` -> `/to-spec` -> `/to-tickets` (or
  `/wayfinder` if multi-session) -> `brainstorming` / `writing-plans` -> Fast
  Track execution.
- **Targeted skills:** Bug -> `systematic-debugging` + regression test +
  `verification-before-completion`; unclear domain/tech -> `research`,
  `prototype`, or `domain-modeling`; issue queue -> `/triage`.
- **Ponytail in this repo:** Section 8 validation overrides Ponytail's test rule.
  Never cut loading/empty/error/partial/stale/failed states, source/unit labels,
  or lineage. Mark deliberate shortcuts with `shortcut: <limit>, <when to revisit>`.

## 6. Working principles

1. **Inspect before editing:** read the target file and at least one caller.
   Never fabricate state or repeat unverified subagent claims.
2. **Small, reviewable edits:** one concern per edit; preserve architecture
   unless asked to change it (propose alternatives first).
3. **Ask only high-leverage questions:** scope, correctness, architecture,
   quality, or destructive risk.
4. **No speculative engineering:** no memoization, abstraction, dependency, or
   rewrite without measured evidence. Match surrounding style.
5. **Context efficiency:** use symbol/reference search and targeted reads before
   large files; avoid repo-wide read loops.
6. **Evidence & reporting:** validate targeted then broader; final reports state
   objective/root cause, files changed, decisions, tests/results, remaining
   risks, and anything not validated.

## 7. Risk-based planning

- **Low risk** (typo, copy, isolated function/tweak): inspect, act, 1-line summary.
- **Medium risk** (multi-file refactor, new component, non-trivial logic): state
  plan in 2-4 lines, then act.
- **High risk** (architecture, data model/DB schema, financial calculations,
  auth/security, destructive ops, repo-wide changes, dependencies): full plan
  and wait for approval unless already approved.
- `"Plan only"`/`"draft"`: no edits. `"Go"`/`"proceed"`: continue without re-asking
  unless new risk appears.

## 8. Validation

- **Pre-PR mirror (always before push/PR):**
  `.\.venv\Scripts\python.exe scripts/diagnostics/pre_pr_check.py` (add
  `--full-python` or `--all` for full local parity).
- **Frontend (`apps/desktop-web`):** targeted test, `typecheck`, and `test` /
  `build` when warranted. Indicators module: targeted `CountryKpisPage` test.
- **Python:** run `tests/` (and `apps/api/tests/` when touching API or shared
  contracts) using `.venv` per `docs/development.md`.
- **UI-observable / Data / Release:** check loading, empty, error, partial,
  responsive, and laptop-width states in the real dev runtime when feasible;
  validate data against fixtures/sandboxes; run `docs/build-release.md`
  guardrails for heavy ingestion/storage and packaged validation for
  release-sensitive work ("works in dev" is not proof for packaged bugs).
- State plainly if any validation was skipped and why.

## 9. Task modes

- **Bugfix:** record symptom, expected vs actual, repro, and evidence; fix root
  cause; add regression test.
- **Feature:** confirm workflow step, owning workspace, source class, persistence,
  offline/failure behavior, and smallest useful version; prefer additive changes.
- **Refactor:** no behavior change; map imports, scripts, tests, docs, and
  packaging refs before moving files; no aesthetic-only moves.
- **UI/UX:** follow `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md` and
  `docs/DESIGN.md` (Tailwind, CSS tokens, existing components, `getSectorColor`).
  Dense, minimal, analyst-grade; detail panels must keep the main table usable
  at laptop width and have an explicit close path. Offer 2-3 options when open.
- **Data/modeling:** read `docs/CONTEXT.md` and `docs/data-sources.md`. GICS is
  curated by CVMAnalytics (never official MSCI/S&P, never copied from CVM/B3;
  `docs/reference/gics-import.md`). Preserve calculation lineage.
- **Excel/export:** follow `docs/excel-exports.md` (no merged cells, traceable
  formulas, negatives in parentheses, opens without repair).
- **Release/updater:** `desktop/__version__.py` is the runtime version source;
  publications stamp it at build time, with no version-bump commits. Merges
  publish through `release-desktop.yml` by shipping class, and
  `promote-release.yml` promotes a pre-release; never tag, create or promote a
  release by hand. Approve a waiting publication or promotion for the owner only
  after their explicit OK in chat for that exact version
  (`docs/release-process.md`).
  Never bundle or overwrite user data (`docs/build-release.md`).
- **Docs/research:** no app code edits; cite active paths/lines; mark gaps
  "Needs validation"; update canonical doc, archive contradictory ones, and
  update `docs/STATUS.md` on state/decision changes.

## 10. Do not

- Open PRs as draft just because they touch many files.
- Merge before CI passes, or squash a PR that another PR is stacked on.
- Load stale planning docs as active context, or follow deleted `CLAUDE.md`,
  `CONTRIBUTING.md`, or `docs/GOVERNANCE_QUICK_REFERENCE.md`.
- Hide source failures, stale data, missing values, partial coverage, or bridge
  errors to make a screen look complete.
- Mix official, external, calculated, estimated, consolidated, individual,
  quarterly, accumulated, or differently scaled values without explicit labels.
