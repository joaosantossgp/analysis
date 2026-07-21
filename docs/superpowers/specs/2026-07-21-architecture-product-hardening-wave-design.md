# Architecture & Product Hardening Wave — Design

**Status:** Approved by João on 2026-07-21
**Evidence source commit:** `9ecd2db246668452262624ea7ad4f370eb7a67d9` (`origin/main`)
**Repository:** `joaosantossgp/analisys`
**Selected approach:** Evidence-first guardrails
**Planning branch:** `codex/architecture-hardening-wave-design`

## 1. Objective

Increase confidence in the active CVMAnalytics desktop architecture through
small, evidence-backed guardrails and reproducible validation. Preserve the
existing Vite -> pywebview -> Python architecture, local-first/offline reads,
downloaded user data, raw snapshots, source lineage, active routes, bridge
behavior, Excel exports, package/update behavior, and observed performance.

This wave is not a feature program and is not an architecture rewrite. It may
repair proven operational metadata drift, strengthen CI, remove redundant type
declarations without changing the method surface, characterize risks, and
validate a disposable current-head package. It must not publish a release.

## 2. Binding approval boundaries

The following require a new explicit approval before implementation:

- changing or removing the automatic startup metadata refresh;
- changing release-publication behavior;
- any database or public-contract change;
- any financial-calculation change;
- any updater-channel change;
- any destructive action;
- any architectural change; and
- any user-visible behavior change.

Characterization, tests of existing behavior, inventory, issue creation, and
design proposals may proceed without crossing these gates. A task that
discovers one of these changes is required stops at evidence and recommendation.

## 3. Active architecture

The verified runtime path is:

```text
apps/desktop-web Vite SPA
  -> apps/desktop-web/src/lib/api/*
  -> apps/desktop-web/src/lib/bridge/adapter.ts
  -> window.pywebview.api
  -> desktop/bridge.py + desktop/bridge_api/*
  -> desktop services and src/* domain/read modules
  -> local SQLite/databases and retained source snapshots
```

`desktop/app.py` serves the built SPA in the frozen application and owns
startup, the runtime lock, background workers, pywebview, and data-root setup.
`apps/api` remains an HTTP/development adapter and is not the shipped UI.
`apps/desktop-web` is the only active frontend. No Next.js source is active.

This boundary matches `README.md`, `docs/architecture.md`,
`docs/active-project-map.md`, and `docs/reference/repository-map.md` at the
evidence source commit.

## 4. Evidence method and baseline provenance

All commands in this section ran from the isolated worktree:

```text
C:\Users\jadaojoao\Documents\Projects\analisys\.claude\worktrees\ops-quality\architecture-hardening-wave-design
```

Common environment:

```text
Windows Microsoft Windows NT 10.0.26200.0
PowerShell 7.6.3
Python 3.11.9
Node v24.14.1
Vite 6.4.2
```

Local logs are under
`scratch/architecture-hardening-wave/baselines/` in the planning worktree.
The directory is ignored scratch evidence and is not a durable substitute for
the committed design, issue records, PR checks, or final audit.

| Evidence | Exact command | UTC start | Duration | Result | Observed output | Local log |
|---|---|---:|---:|---|---|---|
| Worktree bootstrap | `.\scripts\setup\bootstrap_worktree.ps1` | `2026-07-21T19:41:44.3321170Z` | 7.242 s | PASS | Node/Python floors and local Vite verified | `bootstrap.log` |
| Core tests | `python -m pytest tests -q` | `2026-07-21T19:42:14.5804557Z` | 275.895 s | PASS | 688 passed; pytest reported 273.59 s | `pytest-core.log` |
| API tests | `python -m pytest apps/api/tests -q` | `2026-07-21T19:42:14.5976660Z` | 34.295 s | PASS | 122 passed; pytest reported 23.42 s, followed by Sentry shutdown wait | `pytest-api.log` |
| Vite tests | `npm --prefix apps/desktop-web run test` | `2026-07-21T19:42:14.5804579Z` | 6.556 s | PASS | 14 files, 75 tests | `vite-test.log` |
| Vite typecheck | `npm --prefix apps/desktop-web run typecheck` | `2026-07-21T19:42:14.6323392Z` | 18.594 s | PASS | `tsc --noEmit` | `vite-typecheck.log` |
| Vite build | `npm --prefix apps/desktop-web run build` | `2026-07-21T19:42:14.7353942Z` | 22.904 s | PASS | Vite build completed in 3.05 s; largest JS chunk 207.51 kB / 65.14 kB gzip | `vite-build.log` |
| Runtime doctor | `python scripts/diagnostics/runtime_doctor.py --require-canonical` | `2026-07-21T19:47:50.7119357Z` | 0.698 s | PASS | `Ambiente validado.` | `runtime-doctor.log` |
| Real read paths | `python scripts/diagnostics/benchmark_real_read_paths.py --runs 3` | `2026-07-21T19:47:50.6883922Z` | 3.887 s | PASS | See Section 7 | `real-read-benchmark.log` |
| Local storage profile | `python scripts/data/profile_local_storage.py --no-write` | `2026-07-21T19:47:50.6883930Z` | 10.714 s | PASS | See Section 6 | `storage-profile.log` |
| Stale package fingerprint | `Get-Content C:\Users\jadaojoao\Documents\Projects\analisys\desktop\_build_info.py; Get-FileHash C:\Users\jadaojoao\Documents\Projects\analisys\dist\CVMAnalytics\CVMAnalytics.exe -Algorithm SHA256; Get-Item C:\Users\jadaojoao\Documents\Projects\analisys\dist\CVMAnalytics\CVMAnalytics.exe` | `2026-07-21T19:54:00.1463732Z` | 1.207 s | PASS | See Section 5.7 | `stale-package-fingerprint.log` |
| Stale package isolated diagnostic | `C:\Users\jadaojoao\Documents\Projects\analisys\dist\CVMAnalytics\CVMAnalytics.exe --diagnose-runtime --non-interactive` with `CVMANALYTICS_DATA_DIR=C:\Users\jadaojoao\Documents\Projects\analisys\.claude\worktrees\ops-quality\architecture-hardening-wave-design\scratch\architecture-hardening-wave\package-diagnostic-isolated` | `2026-07-21T19:51:28.5242250Z` | 3.474 s | PASS | Frozen runtime diagnostic completed in the isolated operator root | `stale-package-isolated.log` |

Every row above ran at source commit
`9ecd2db246668452262624ea7ad4f370eb7a67d9`. The previously observed 84 Vite
tests came from the primary dirty checkout, which contains uncommitted user UI
tests. It is retained only as a session observation. The clean authoritative
commit baseline is 75 Vite tests.

`npm ci` reported two dependency-audit findings (one low, one high). This wave
does not change dependencies, and the audit output alone does not justify an
unscoped upgrade.

## 5. Architecture health findings

### 5.1 Healthy and preserved

- The documented Vite/pywebview/Python boundary matches active imports and
  runtime startup.
- The packaged build spec bundles the active Vite output and required Python
  resources without bundling the user's databases.
- The updater stages outside the install directory, checks checksums, swaps
  only `CVMAnalytics.exe` and `_internal`, and retains a rollback snapshot.
- Existing data is resolved under `%USERPROFILE%\Documents\CVMAnalytics`, with
  explicit operator overrides and local SQLite reads.
- Source, unit, frequency, missing-value, official/external/calculated, and
  actual/forecast distinctions are present in canonical contracts and must not
  be weakened.
- All clean-commit automated baselines passed.

### 5.2 Proven operational-contract drift

Three operational files contain stale assumptions:

1. `.github/workflows/seed_catalog.yml:49-50` imports removed
   `src.db` and `src.settings` modules. The active modules are
   `src.platform.db` and `src.platform.settings`. The workflow reaches this
   smoke step only after remote seed work, so the stale import can turn a
   successful mutation into a final workflow failure.
2. `.github/guardrails/path-policy.json:98-104` lists removed top-level
   runtime modules instead of active `src/platform`, `src/financials`, and
   `src/refresh` paths. The policy therefore does not accurately describe the
   critical runtime write surface.
3. `scripts/governance/worktree_create.ps1` defaults to `main`, while
   `scripts/governance/worktree_remove.ps1:12` defaults to `master`. The
   repository has `main` and no local `master` branch.

These are one bounded operational-contract repair because they are all stale
repository automation/navigation metadata. The implementation must add static
regression checks before changing the files.

### 5.3 Frontend CI omission

`.github/workflows/ci.yml` installs the Vite dependencies, runs typecheck, and
builds, but does not run Vitest. The clean suite is fast (75 tests in 6.556 s
including command startup) and already exists. Adding the existing test command
to CI changes no product behavior.

### 5.4 BridgeApi duplication and inventory gap

`apps/desktop-web/src/lib/bridge/types.ts` contains a repeated block of method
declarations beginning around line 1654. TypeScript accepts compatible duplicate
interface members, so typecheck does not expose this drift. There is no static
duplicate-name regression check and no durable Python-versus-TypeScript method
inventory.

The smallest authorized repair is:

1. add a static test that fails on duplicate `BridgeApi` method names;
2. observe the test fail against the current interface;
3. remove only duplicate declarations, preserving the unique TypeScript method
   surface and all types;
4. produce a verified inventory of Python public bridge methods versus the
   TypeScript interface; and
5. document mismatches and classify them as active, legacy, intentionally
   Python-only, or needing a separately approved follow-up.

This task must not add code generation, a schema framework, or a dependency
unless the verified inventory first proves that the static guardrail is
insufficient. It must not add, remove, rename, or change a runtime bridge method.

### 5.5 Automatic startup metadata refresh: potential local-first violation

`desktop/app.py:1223-1227` always starts
`desktop-remote-metadata-refresh` after window creation. The thread is started
in both development and frozen execution because it is outside the `dev_mode`
branch.

Current behavior:

- It waits two seconds, requires the process-wide runtime lock to report
  `locked_by_self`, and opens
  `_user_data_root()/db/cvm_financials.db` directly.
- `_user_data_root()` resolves `CVMANALYTICS_DATA_DIR`, then
  `%USERPROFILE%\Documents\CVMAnalytics`, then LocalAppData/temp fallbacks. It
  does not use `CVM_DATA_DIR` as its source of truth.
- Development startup preserves an explicit `CVM_DATA_DIR`, while the refresh
  still uses `_user_data_root()`. Therefore a developer using only
  `CVM_DATA_DIR` can lock and read an isolated database while the refresh thread
  inspects or writes the Documents database. Existing tests patch
  `_user_data_root()` and do not characterize this mismatch.
- Frozen startup normally aligns both values by deriving them from
  `_user_data_root()`. An explicit `CVMANALYTICS_DATA_DIR` is the correct
  packaged isolation override. `CVM_DATA_DIR` alone is insufficient for code
  that directly calls `_user_data_root()`.
- If a companies table contains missing CNPJs and the seven-day timestamp is
  absent or expired, `CompanyCatalogService` performs a CVM catalog fetch with
  a ten-second timeout.
- On success it directly updates `companies.cnpj` and writes
  `app_settings.metadata_last_successful_refresh`, even when zero valid CNPJs
  were found. Per-company lookup errors are swallowed and partial updates are
  committed.
- Network, validation, and persistence failures are caught and printed. The
  success timestamp is not written when the initial catalog load fails.
- Observability is stdout-only. `desktop/app.spec` uses `console=False`, and no
  bridge status, UI state, refresh log, or explicit setting exposes this work to
  a packaged user.
- No opt-out flag or user setting was found for this thread. The seven-day TTL,
  no-missing-CNPJ case, missing database/table, lock ownership, and in-process
  mutex are the only gates.
- Persisted CNPJ values are consumed by company identity resolution, company
  detail display, sector/company search and panels, market-cap matching,
  distribution/company linking, and Excel exports. The refresh therefore has
  real consumers, but that does not authorize a hidden external call.

Existing tests in `tests/test_metadata_fixes.py` cover lock, TTL, success,
failure timestamp, and in-process concurrency behavior. They do not establish
that implicit startup network access is compatible with the local-first
contract, nor do they cover data-root alignment or packaged observability.

This is a potential contract violation, not a neutral enhancement. The child
issue may add characterization evidence and propose options, but changing or
removing the behavior remains behind explicit approval.

### 5.6 Release evidence enforcement gap

`.github/workflows/release-desktop.yml` builds the package, validates version
metadata and ZIP layout, and publishes release assets. The broader documented
preflight in `docs/build-release.md` includes core/API/UI tests, managed
ingestion and storage checks, and packaged smoke/offline/update evidence. Those
checks are not all enforced in the publication workflow. The main CI workflow
does not run on release tags, so a tag can enter the release job without a tag
specific CI run.

Prior work already validated prerelease classification and updater SemVer
handling. This finding is narrower: define the evidence/preflight relationship
for publication. Any workflow change that modifies publication behavior
requires explicit approval. The issue remains characterization/proposal-only
until that approval is granted.

### 5.7 Local package is not current-head evidence

The existing local executable is associated with generated build provenance:

```text
version = 0.30.0-rc.1
build_commit = ad7e9af
build_time = 2026-07-16T02:40:19Z
SHA-256 = B11889269FAF9027E9D120FA88AA6499A2DAB27FD86CAE3013209B377DBAE779
```

The source evidence commit is `9ecd2db`, so this package cannot prove current
head. A non-interactive diagnostic of the stale package passed on 2026-07-21
at `2026-07-21T19:51:28.5242250Z`, took 3.474 s, and used the explicit
`CVMANALYTICS_DATA_DIR` operator override. Its logs are
`stale-package-isolated.log` and
`scratch/architecture-hardening-wave/package-diagnostic-isolated/diagnostics-20260721T195129Z.log`.

An earlier probe used `CVM_DATA_DIR` alone and showed why that variable is not
enough for `_user_data_root()` diagnostics: one diagnostic log was created in
the Documents root. That exact generated log was immediately moved, without
deletion, into the worktree evidence directory. No downloaded data, database,
or source snapshot was altered.

Issue #372 remains valid evidence for the published RC at its documented older
commit. This wave needs a new disposable current-head package validation after
the authorized guardrails merge, without publishing a tag or release.

## 6. Data safety evidence

The read-only storage profile found:

| Item | Observed value |
|---|---:|
| Canonical root | `C:\Users\jadaojoao\Documents\CVMAnalytics` |
| Files | 219 |
| Total size | 7,153,422,052 bytes |
| `input/` | 4,230,605,643 bytes |
| `db/` | 2,090,016,768 bytes |
| `raw/` | 819,731,209 bytes |
| Largest database | `db/energy_kpis.db`, 2,076,139,520 bytes |

The profile used `--no-write`. The wave will not delete, compact, migrate,
reindex, copy over, or replace these stores. Current-head packaged validation
must use a disposable data root or a copy made with SQLite/WAL-safe handling.
Downloaded files and source snapshots remain authoritative retained evidence.

## 7. Performance evidence

The real read-path benchmark used the canonical
`db/cvm_financials.db`, sample company `9512`, and years 2021–2025:

| Read | Result |
|---|---:|
| First `list_companies` read | 690.45 ms |
| Warm `list_companies` median | 0.00 ms |
| Warm `search_petro` median | 0.01 ms |
| Warm bridge `get_companies` median | 0.56 ms |
| Warm bridge `get_base_health` median | 1.56 ms |

This proves a measurable cold/warm difference but does not isolate a production
bottleneck or justify optimization. Existing issues #134 and #239 cover general
read/startup benchmarking, and #374 covers the SIN series bottleneck that led to
the approved daily chart contract. This wave will rerun the existing benchmark
as a regression check and will not create a duplicate performance issue.

## 8. Program alternatives

### A. Evidence-first guardrails — selected

Repair only proven automation/contract drift, make existing tests visible to
CI, protect the bridge interface from duplicate declarations, characterize the
two gated risks, and validate a disposable package. This has the best ratio of
confidence gain to behavioral risk.

### B. Boundary extraction — rejected

`desktop/services.py` is large, but current evidence shows two coherent active
responsibilities plus an uncertain/orphaned ranked-selection path. File size
alone is not a coupling, failure, or testability result. Broad extraction stays
rejected unless new call-graph, coupling, testing, or failure evidence justifies
a separately scoped task.

### C. Immediate runtime/release behavior hardening — deferred

Removing the startup refresh or changing release workflow gates could improve
contract enforcement, but both cross explicit approval boundaries. They remain
evidence and decision tasks in this wave.

## 9. Bounded Epic and child design

Create one Epic with six non-duplicative children:

### Child 1 — Repair repository operational-contract drift

**Risk:** low/medium, shared ops-quality
**Authorized:** yes

- Add static failing checks for seed workflow import resolution, active
  critical-runtime path policy entries, and the default worktree base.
- Repair the stale imports/paths/default while preserving workflow purpose and
  lane semantics.
- Do not run the remote seed workflow or mutate a remote database.

### Child 2 — Run Vite tests in CI

**Risk:** low, ops-quality
**Authorized:** yes

- Add `npm run test` to the existing Vite CI job before typecheck/build.
- Reuse the lockfile and current Node setup; add no dependency.
- Validate workflow syntax and the local 75-test clean baseline.

### Child 3 — Guard BridgeApi integrity

**Risk:** low/medium, frontend contract guardrail
**Authorized:** yes, within the smallest guardrail scope

- Add and observe a failing duplicate-name static test.
- Remove duplicate declarations only.
- Produce a verified Python-versus-TypeScript method inventory and document
  every mismatch.
- Preserve the runtime surface and avoid generation/framework/dependency work.

### Child 4 — Characterize automatic startup metadata refresh

**Risk:** contract-sensitive investigation
**Authorized:** characterization only

- Record dev and frozen target-path behavior, observability, failure semantics,
  writes, opt-out status, and active consumers.
- Add characterization tests only if they preserve current behavior.
- Present options and a recommendation.
- Do not change, disable, or remove the refresh without explicit approval.

### Child 5 — Define release-publication evidence gate

**Risk:** release-sensitive investigation
**Authorized:** characterization/proposal only

- Map documented preflights to current CI and release workflow enforcement.
- Define a minimal proposal and rollback/failure behavior.
- Do not modify publication behavior without explicit approval.

### Child 6 — Validate a current-head packaged candidate

**Risk:** medium, isolated verification
**Authorized:** yes

- Run only after authorized code/CI guardrails are integrated into the
  candidate commit.
- Build without a stable tag or release.
- Verify provenance, ZIP roots, clean launch, copied-data preservation,
  offline cached reads, source/missing/error visibility, Excel-open behavior,
  updater helper allowlist/rollback boundary, and normal laptop width where
  observable.
- Use disposable roots and retain logs/checksums/screenshots as audit evidence.

## 10. Overlap decisions

- GICS consistency remains owned by open issue #397; no duplicate child.
- Deferred CCEE PLD work remains #385; no duplicate child.
- Prior packaged RC validation remains #372; the new child covers a later
  current-head candidate only.
- Bridge startup readiness was fixed in #369; the new child covers static
  interface declaration integrity, not injection timing.
- Performance issues #134, #239, and #374 already own their respective
  baselines/findings; no generic performance child.
- Prerelease publication and updater ordering were handled in #380/#382/#383;
  the release child is limited to preflight evidence enforcement.

## 11. Execution model

- Design and plan are committed on the isolated planning branch.
- The Epic and children are created only after the detailed plan passes
  self-review and a final overlap search.
- Each authorized implementation child uses its own clean worktree, branch,
  test-first cycle, focused commit(s), PR, task review, CI verification, and
  audit record.
- Implementation tasks execute serially under subagent-driven development;
  task review covers both specification compliance and code quality.
- Gated investigations may create evidence and recommendations but do not merge
  prohibited behavior changes.
- No stable release is created.

## 12. Completion criteria

The wave is complete only when:

1. this design and the detailed plan are committed;
2. the Epic and six children contain source evidence, acceptance criteria,
   dependencies, risks, write sets, and approval boundaries;
3. every authorized low/medium implementation issue has a reviewed, verified,
   focused PR outcome;
4. gated issues clearly record the unresolved decision without changing
   behavior;
5. a disposable current-head package has auditable provenance and validation
   evidence, or an honestly documented blocker after exhausting safe checks;
6. the final audit maps every original requirement to authoritative evidence;
7. user data, source snapshots, bridge behavior, Excel behavior, updater
   channel, and release state remain preserved; and
8. broad `desktop/services.py` extraction remains out of scope absent new
   evidence.
