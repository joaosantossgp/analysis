# Phase 5 Legacy Deletion Audit

> Status: **Phase 5B implemented for v0.15.0.** This document started as the
> Phase 5A audit and now records the final desktop-bundle deletion decisions.
> Phase 5B touched only the desktop bundle/runtime path. Phase 5C records the
> separate source-only / hosted-surface decision in
> `PHASE_5C_SOURCE_LEGACY_CLEANUP.md`.

## Phase 5B Final Deletion Decisions

Accepted implementation path:

```
CVMAnalytics.exe              -> Vite UI only
CVMAnalytics.exe --vite       -> Vite alias
CVMAnalytics.exe --legacy     -> unsupported warning, then Vite UI
CVMAnalytics.exe --dev        -> source mode starts/uses Vite dev server on :5173;
                                 packaged build ignores dev and opens Vite
CVMAnalytics.exe --debug      -> opens DevTools in the active Vite mode
CVMAnalytics.exe --diagnose-runtime   -> write diagnostics log and exit
```

Removed from the packaged desktop app:

```
Next.js standalone server   (_internal/web_standalone/)
bundled node.exe            (_internal/node.exe)
desktop/node_portable/      (build artifact source for node.exe)
Next build/copy steps       (desktop/build_desktop.ps1)
Next/Node data entries      (desktop/app.spec)
```

Kept in source tree:

```
apps/web/        source-only legacy / hosted Next.js app, not packaged
apps/api/        Railway-hosted FastAPI + API tests, not packaged
railway.toml     hosted API deployment config
landing/         marketing site
```

No persistent user-data path, database migration, updater allowlist, ZIP root
contract, Python data pipeline, or Vite bridge contract was changed.

## Current Runtime Model

Phase 5A baseline release: **`v0.14.1`** (manually accepted after the `v0.14.0`
Phase 4 default flip + GICS-backfill hotfix).

```
CVMAnalytics.exe              -> Vite default (no Node process)
CVMAnalytics.exe --vite       -> alias of default Vite mode
CVMAnalytics.exe --legacy     -> Next/Node fallback (spawns bundled node.exe)
CVMAnalytics.exe --dev        -> Next.js dev server (developer only)
CVMAnalytics.exe --debug      -> open DevTools in the active mode
CVMAnalytics.exe --diagnose-runtime   -> write diagnostics log and exit
```

Bundle layout under `_internal/` (measured against `dist/CVMAnalytics/_internal/`):

| Asset | Size | Used by |
|---|---|---|
| `desktop-web/` | 2.2 MB | Vite default |
| `web_standalone/` | 22.7 MB | `--legacy` only |
| `node.exe` | 87.2 MB | `--legacy` only |
| `update_helper.ps1` | < 1 KB | updater (all modes) |
| `data/import/gics_mapping.csv` | 0.24 MB | startup GICS backfill |
| `pythonnet/runtime/` | (small) | all modes |
| Python core (`base_library.zip`, `*.pyd`, deps) | ~90 MB | all modes |
| **Total** | **~203 MB** | |

`--legacy` accounts for ~110 MB (about 54%) of the bundle.

## Target Runtime Model

Stated direction from `docs/migration/README.md`:

```
Python core
+ SQLite local DB
+ pywebview / WebView2
+ static Vite frontend
+ PyInstaller
```

After Phase 5B the bundle does NOT contain:

```
Next.js standalone server   (web_standalone/)
Bundled Node runtime        (node.exe)
desktop/node_portable/      (build artifact dir)
--legacy startup branch in desktop/app.py
--dev branch (Next dev) in desktop/app.py
```

The bundle still contains:

```
desktop-web/ (Vite SPA)
update_helper.ps1
data/import/gics_mapping.csv
pythonnet/runtime/
desktop/bridge.py + src/ + Python deps
```

## Runtime Dependency Audit

| Dependency | Classification | Evidence |
|---|---|---|
| `apps/desktop-web/` | runtime-required | [desktop/app.py:850-858](desktop/app.py:850) loads `_vite_dist_path()` for default startup. |
| `desktop/bridge.py` + `src/` | runtime-required | Bridge exposed to both UIs; Vite default path imports it identically to `--legacy`. |
| `_internal/web_standalone/` | legacy-fallback-only | [desktop/app.py:809](desktop/app.py:809) only resolves it inside `if legacy_mode:`. |
| `_internal/node.exe` | legacy-fallback-only | [desktop/app.py:813-820](desktop/app.py:813) `_node_exe()` only called from `_start_standalone_server`. |
| `desktop/node_portable/node.exe` | legacy-fallback-only | Build-time source for the bundled `node.exe`. No other consumer. |
| `apps/web/` (Next 16 project) | **dual-use, NOT pure legacy** | Source for the legacy `--legacy` desktop bundle (via `next build`), **and** also deployed to Vercel (`.github/workflows/ci.yml` has a `Trigger Vercel deploy` step gated on the `VERCEL_DEPLOY_HOOK` secret). `apps/web/public/vercel.svg` corroborates the Vercel target. |
| `apps/api/` (FastAPI) | **dual-use, NOT pure legacy** | Hosted on Railway as `https://analisys-production.up.railway.app`. Called by `.github/workflows/on_demand_ingest.yml:71`, `.github/workflows/backfill_historico.yml:95`, `.github/workflows/ingest.yml:102`, and probed by `.github/workflows/ci.yml` for tests. `railway.toml` builds `apps/api/Dockerfile`. Phase 4's bundle does not consume FastAPI but the hosted product does. |
| FastAPI / Uvicorn / `sentry-sdk` in `requirements.txt` | dev-only / hosted-only | NOT in top-level `requirements.txt`. Only in `apps/api/requirements-prod.txt` and `apps/api/requirements-dev.txt`. The packaged desktop runtime never installs FastAPI. |
| `NotFoundError` (from `apps.api.app.dependencies`) | runtime-required cross-module import | [src/read_service.py:2221](src/read_service.py:2221) and [src/read_service.py:2742](src/read_service.py:2742) `from apps.api.app.dependencies import NotFoundError`. Hit when the bridge dispatches an on-demand refresh and the company is missing. Imported lazily — desktop has not crashed because the path is rare. |
| `railway.toml` | runtime-required for hosted API | Drives Railway's auto-deploy of the hosted FastAPI. Has no relation to the desktop bundle. |
| `landing/` | runtime-required for marketing | Static GitHub Pages site. Built by `.github/workflows/deploy-landing.yml`. Independent of both UIs. |

## Packaging Audit

[desktop/app.spec](desktop/app.spec) — three entries are dedicated to `--legacy`:

```python
STANDALONE_DIR = ROOT / "apps" / "web" / ".next" / "standalone"   # → web_standalone/  (--legacy only)
NODE_EXE       = ROOT / "desktop" / "node_portable" / "node.exe" # → node.exe         (--legacy only)
```

The Vite SPA, `update_helper.ps1`, `gics_mapping.csv`, and `pythonnet/runtime/`
all serve the default Vite runtime and must stay.

[desktop/build_desktop.ps1](desktop/build_desktop.ps1):
- **Step 1** (`next build`) — only feeds `--legacy`.
- **Step 3** (copy `public/` + `.next/static/` into standalone) — only feeds `--legacy`.
- **Step 4** (prepare `desktop/node_portable/node.exe`) — only feeds `--legacy`.
- **Step 1.5** (`vite build` in `apps/desktop-web`) — feeds the default.
- **Step 2** (inject `__version__.py`) — runtime-required.
- **Step 5** (`pyinstaller desktop/app.spec`) — runtime-required.

[.github/workflows/release-desktop.yml](.github/workflows/release-desktop.yml):
- `actions/setup-node@v4` (line 28-32) and `npm ci --prefix apps/web` (line 38) only feed `--legacy`.
- The rest of the workflow (Python setup, build_desktop, flat-root verify, ZIP, SHA-256, publish) is runtime-required.

Expected impact of Phase 5B (remove `--legacy` from the bundle):

| Metric | Estimate |
|---|---|
| Bundle size | ~203 MB → ~93 MB (−54%, −110 MB) |
| Release ZIP size | ~79 MB → ~30 MB (estimated) |
| CI build time | −Node setup (~30 s) and −`next build` step (≥1 minute) → saves ≥1 min per release |
| Process count at runtime | unchanged for default (already 0 `node.exe`); −1 `node.exe` for any user previously on `--legacy` |
| Cold-start time | unchanged for default (already Vite); `--legacy` cold-start no longer offered |
| Risk | Low for the bundle change; **medium-high if `apps/web/` / `apps/api/` were touched** because of the Vercel / Railway products |

## Source Tree Audit

| Path | Action | Reason |
|---|---|---|
| `apps/desktop-web/` | keep | Default Vite UI source. |
| `apps/web/` | **keep — needs user decision** | Source of legacy `--legacy` bundle **and** Vercel-deployed web app. Phase 5B does NOT delete it: it stops bundling `.next/standalone` into the desktop ZIP. Removing the directory is a separate user decision tied to retiring the Vercel deploy. |
| `apps/api/` | **keep — needs user decision** | Hosted Railway product called by data-pipeline CI workflows. Independent of desktop runtime. Phase 5B does NOT delete it. |
| `desktop/node_portable/` | delete in Phase 5B | Only feeds `--legacy`. |
| `railway.toml` | keep | Drives the hosted FastAPI deploy. Independent of desktop runtime. |
| `landing/` | keep | Static marketing site on GitHub Pages. |
| `next.config.ts` (inside `apps/web/`) | keep | Owned by `apps/web/`. |
| `apps/web/start-web.cmd` | keep | Owned by `apps/web/`. |
| `_internal/web_standalone/` | not in repo; stops being produced in Phase 5B once `STANDALONE_DIR` data entry is removed | |
| `data/import/gics_mapping.csv` | keep | Used by startup backfill. |

## Backend/API Audit

The Vite UI talks only through `window.pywebview.api`. The adapter at
[apps/desktop-web/src/lib/bridge/adapter.ts:32-41](apps/desktop-web/src/lib/bridge/adapter.ts:32) never reaches HTTP — there is no fallback to FastAPI.

The Python desktop runtime needs:

```
desktop/bridge.py
src/**  (read_service, refresh_job_*, settings, db, sector_taxonomy,
         gics_manual_mapping, contracts, ...)
SQLite via standard library + SQLAlchemy
local filesystem under Documents/CVMAnalytics
```

FastAPI / Uvicorn / `sentry-sdk` are **not** in the desktop runtime stack. They
live only in `apps/api/requirements-prod.txt` / `requirements-dev.txt` and run
inside Railway (and inside `apps/api/tests` on CI). The top-level
`requirements.txt` does not include them — `pip install -r requirements.txt` on
a clean machine produces a desktop-ready environment without FastAPI.

The one cross-cutting coupling between `src/` and `apps/api/` is the lazy
import of `NotFoundError`:

```
src/read_service.py:2221     from apps.api.app.dependencies import NotFoundError
src/read_service.py:2742     from apps.api.app.dependencies import NotFoundError
```

This is **not a Phase 5B blocker for the desktop bundle change** — the desktop
bundle still ships `apps/api/` via its source tree under `src/` imports because
PyInstaller follows the import graph. Since Phase 5B does NOT delete
`apps/api/`, the import still resolves. If a future phase removes `apps/api/`
entirely, those two imports must be relocated: define `NotFoundError` in
`src/contracts.py` (or a new `src/errors.py`) and re-export from
`apps.api.app.dependencies` for backwards compatibility with the hosted API.

## Build/CI Audit

| Workflow | References to delete-targets | Phase 5B action |
|---|---|---|
| `release-desktop.yml` | `setup-node@v4`, `npm ci --prefix apps/web`, plus `build_desktop.ps1` step 1 | Remove the Node setup step and the npm install step. Phase 5B also rewrites `build_desktop.ps1` so step 1 / 3 / 4 disappear; the workflow no longer needs Node. |
| `ci.yml` | builds `apps/web`, tests `apps/api`, deploys Vercel | **No Phase 5B change.** Both products stay. |
| `perf-guardrails.yml` | path triggers on `apps/web/**` and `apps/api/**` | **No Phase 5B change.** Both products stay. |
| `ingest.yml`, `on_demand_ingest.yml`, `backfill_historico.yml` | curl `analisys-production.up.railway.app/...` | **No Phase 5B change.** The Railway-hosted FastAPI is alive. |
| `refresh.yml` | runs Python ingestion only; no hosted-API call in the section reviewed | No change. |
| `deploy-landing.yml` | only deploys `landing/` to GitHub Pages | No change. |
| `seed_catalog.yml`, `pr-issue-guardrails.yml` | not touched in audit | No change. |

## Updater / Release Contract Audit

Removing `--legacy` does not break any of the Phase 0 invariants:

| Invariant | Status after Phase 5B |
|---|---|
| Release artifact naming (`CVMAnalytics-windows-v<version>.zip` + `.sha256` + latest alias) | Unchanged. |
| Flat ZIP root contract (`CVMAnalytics.exe` + `_internal/`) | Unchanged. The `Compress-Archive -Path dist\CVMAnalytics\*` and the post-archive verification step still apply. |
| `update_helper.ps1` allowlist `(CVMAnalytics.exe, _internal)` | Unchanged. Allowlist is by top-level entry name, not by contents — fewer files inside `_internal/` does not break the swap. |
| Updater rollback snapshot under `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-ts>\` | Unchanged. |
| User-data deny-list (`data`, `output`, `logs`, `cache`, `tmp`, `backup`, `versions`, `update_rollback`) | Unchanged. |
| Persistent data root `%USERPROFILE%\Documents\CVMAnalytics\` | Unchanged. Migrator, WAL-safe copy, schema init, GICS backfill all run independently of which UI is loaded. |
| `_strip_motw_from_bundle()` | Unchanged. |
| `_preflight_pywebview_backend()` (NET 4.8 + WebView2 + pythonnet) | Unchanged. |
| `--diagnose-runtime` | Unchanged. |
| `desktop/updater.py` GitHub Releases polling, SHA-256 verify, staging | Unchanged. |

Risk: a `v0.14.1` user who applies an update to `v0.15.0` (the post-Phase-5B
release) will lose the `--legacy` escape hatch on the next launch. The release
notes must call this out.

## Historical Fallback Strategy

Three options were considered during Phase 5A:

- **A. Remove `--legacy` immediately in Phase 5B.** Lowest cost, but the user
  has only had one accepted release (`v0.14.1`) on the Vite default. If a
  Vite-only regression surfaces post-update, the user cannot fall back.
- **B. Keep `--legacy` for one more release, remove in Phase 5C.** Ship
  `v0.15.0` as another Vite-default-with-`--legacy` release after the Phase 5B
  audit so a soak interval passes between user acceptance of `v0.14.1` and the
  permanent removal. Lowest risk, defers savings by one release cycle.
- **C. Do not remove `--legacy` yet.** Only if a specific Vite-default blocker
  is open. None is open today.

The user explicitly approved Phase 5A as an audit, not the deletion. The Phase
4 prompt and the `PHASE_3_PLAN.md` pre-conditions both ask for a soak window
between the default flip and any deletion. `v0.14.1` was accepted **once**,
manually, on a single machine.

Final Phase 5B decision: the user explicitly approved immediate removal after
manually accepting `v0.14.1`. The implementation keeps the flag only as an
unsupported warning + Vite fallback so old shortcuts still open the app.

## Executed Phase 5B Deletion List

Only paths whose sole consumer was the desktop `--legacy` runtime:

```
desktop/node_portable/                      (entire directory, 87 MB)
desktop/node_portable/node.exe              (specifically — the only file in the dir)
```

**Not deleted** (independent products / dual-use):

```
apps/web/        — Vercel-deployed web app; Phase 5B only stops bundling its build output.
apps/api/        — Railway-hosted FastAPI; Phase 5B does not touch it.
railway.toml     — Drives the hosted API deploy.
landing/         — Static GitHub Pages site, independent.
src/read_service.py NotFoundError import — keep; apps/api remains.
```

## Executed Phase 5B Modification List

```
desktop/app.py
  - Remove _DEV_PORT, _DEV_URL constants.
  - Remove _web_dir(), _standalone_path(), _node_exe(), _npm_cmd().
  - Remove _start_dev_server(), _start_standalone_server().
  - Remove legacy_mode + dev_mode parsing and branches in main().
  - Keep `--vite` accepted as a no-op alias.
  - Keep `--legacy` accepted only as an unsupported warning + Vite fallback.
  - Update window title (drop the "(Legacy)" suffix branch).
  - Update module docstring.

desktop/bridge.py
  - _runtime_mode(): drop the "--legacy" branch; treat frozen builds
    unconditionally as "vite".

desktop/app.spec
  - Remove STANDALONE_DIR + the `if STANDALONE_DIR.exists():` data entry.
  - Remove NODE_EXE + the `if NODE_EXE.exists():` data entry.
  - Update the file-level comment that lists pre-build requirements.

desktop/build_desktop.ps1
  - Remove step 1 (`next build`) and its $SkipNextBuild parameter.
  - Remove step 3 (copy `public/` + `.next/static/` into standalone).
  - Remove step 4 (prepare `desktop/node_portable/node.exe`).
  - Renumber remaining steps; rewrite the file-level docstring.

.github/workflows/release-desktop.yml
  - Keep `actions/setup-node@v4`, scoped to `apps/desktop-web`, because Vite
    still needs Node to build.
  - Remove the `npm ci --prefix apps/web` step.
  - Install only `apps/desktop-web` dependencies.
  - Leave flat-root verify, SHA-256 sidecars, and publish step untouched.

apps/desktop-web/src/routes/StatusPage.tsx
  - Drop the "--legacy" fallback hint added in v0.14.0 (or rewrite to point at
    `v0.14.x` for users who need the previous UI before update).

README.md, apps/desktop-web/README.md,
docs/migration/README.md,
docs/migration/NEXT_AGENT_HANDOFF.md,
docs/migration/PHASE_3_PARITY_MATRIX.md
  - Update the launch-mode tables to drop `--legacy`.
  - Update the bundle-architecture block to drop Next/Node references.
  - Add a Phase 5B release note (docs/releases/v0.15.0.md).
```

## Files To Keep

```
apps/web/        (Vercel-deployed)
apps/api/        (Railway-hosted)
railway.toml
landing/
data/import/gics_mapping.csv
desktop/bridge.py
desktop/app.py (with --legacy/Next code paths removed)
desktop/app.spec (without web_standalone / node.exe data entries)
desktop/update_helper.ps1   (unchanged)
desktop/updater.py          (unchanged)
desktop/__version__.py      (bump only)
desktop/build_desktop.ps1 (with Next/Node steps removed)
.github/workflows/release-desktop.yml (with Node setup steps removed)
src/                        (unchanged including the NotFoundError import)
apps/desktop-web/           (default UI)
data/                       (unchanged)
```

## Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | A Vite-only regression surfaces post-Phase-5B and the user cannot fall back. | Low–Medium | High | Pick option B (one more `--legacy` release before deletion). Document `v0.14.x` as the last image that ships `--legacy`. |
| 2 | A user with a custom shortcut passes `--legacy` to the new build. | Low | Low | Phase 5B should either silently ignore unknown flags or print a one-line MessageBox pointing at the release notes. |
| 3 | Accidentally deleting `apps/web/` or `apps/api/` along with the desktop cleanup. | Low | Critical | Phase 5B prompt + branch protection: limit the deletion commit to `desktop/node_portable/` only. Run `git status --short` before commit. |
| 4 | The `src/read_service.py::NotFoundError` import breaks because someone removes `apps/api/` later. | Low | High (would break the bridge on missing-company refresh) | Out of Phase 5B scope. If a future phase removes `apps/api/`, move `NotFoundError` into `src/contracts.py` (or `src/errors.py`) and re-export from `apps.api.app.dependencies` first. |
| 5 | CI workflow `release-desktop.yml` breaks because the Node setup steps are removed but `apps/web/package-lock.json` still has cache entries elsewhere. | Low | Low | The Node setup is only used by `npm ci --prefix apps/web`. Removing both steps is internally consistent. |
| 6 | Updater applies the post-Phase-5B build over a `v0.14.1` install. The user's `_internal/web_standalone/` and `_internal/node.exe` survive inside `_internal/` only as orphaned files until the next swap. | Low | Negligible (orphaned files harm nothing) | The helper allowlist swap removes the entire `_internal/` before writing the new one. Orphans not possible. |
| 7 | The Phase 5B bundle is markedly smaller; SmartScreen reputation may dip on a brand-new artifact size signature. | Low | Low | UPX still disabled; preflight + MOTW strip still apply. Monitor first reports. |
| 8 | Removing `--dev` breaks a developer workflow somewhere. | Low | Low | Replace with `python scripts/phase1_pywebview_smoke.py --manual` in the developer docs. |

## Validation Plan For Phase 5B

Pre-merge:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build

.\desktop\build_desktop.ps1 -Version 0.15.0

# Inspect dist for the absence of --legacy assets
Test-Path "dist\CVMAnalytics\_internal\web_standalone"      # expect: False
Test-Path "dist\CVMAnalytics\_internal\node.exe"            # expect: False
Test-Path "dist\CVMAnalytics\_internal\desktop-web\index.html"  # expect: True
Test-Path "dist\CVMAnalytics\_internal\update_helper.ps1"       # expect: True
Test-Path "dist\CVMAnalytics\_internal\data\import\gics_mapping.csv"  # expect: True

# Bundle size sanity
(Get-ChildItem dist\CVMAnalytics -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
# expect: ~93 MB (-54% vs v0.14.1)
```

Runtime:

```powershell
.\dist\CVMAnalytics\CVMAnalytics.exe
# expect: Vite UI; no node.exe process spawned.

.\dist\CVMAnalytics\CVMAnalytics.exe --legacy
# expect: graceful fallthrough to Vite default OR a one-line notice that --legacy was removed.

.\dist\CVMAnalytics\CVMAnalytics.exe --diagnose-runtime
# expect: diagnostics log written; bundled pythonnet/runtime/ + sqlite3 OK.
```

UI smoke (must all pass):

```
companies directory
company detail
financial statements
KPIs + KPI trend charts
sectors directory (11 GICS hubs)
sector detail
sub-sector detail
Update Base
single-company refresh panel
Excel export (full workbook + per-statement)
status / diagnostics
software updater check
```

Persistence + updater:

```
Documents/CVMAnalytics/db/cvm_financials.db preserved across launches
Documents/CVMAnalytics/output/ preserved across launches
Documents/CVMAnalytics/logs/ + cache/ untouched by the helper swap
Helper sandbox swap test: see docs/migration/PHASE_3_PARITY_MATRIX.md
GitHub Release flat-root ZIP test against the published v0.15.0 asset
v0.14.1 → v0.15.0 update applied end-to-end at least once
```

## Recommendation

**Phase 5B package/runtime removal is complete.**

Recommended next step: keep soaking the Vite-only desktop runtime. Phase 5C
kept `apps/web/` and `apps/api/` as documented source-only / hosted surfaces
outside the desktop package and default desktop CI. Delete them only after a
separate hosted-surface retirement approval.
