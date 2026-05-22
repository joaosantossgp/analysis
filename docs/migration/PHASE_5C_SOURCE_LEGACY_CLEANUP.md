# Phase 5C Source-only Legacy Cleanup

## Current Desktop Runtime

Accepted baseline: `v0.15.0`.

The packaged desktop runtime is:

```text
Python core
+ SQLite local DB under %USERPROFILE%\Documents\CVMAnalytics
+ pywebview / WebView2
+ static Vite frontend from _internal/desktop-web/
+ PyInstaller
```

The package does not include `_internal/node.exe`, `_internal/web_standalone/`,
the Next standalone server, or `desktop/node_portable/`.

## Source-only Legacy Inventory

| Item | Classification | Decision | Rationale |
|---|---|---|---|
| `apps/desktop-web/` | keep | Keep | Only packaged desktop UI source. Required by `desktop/build_desktop.ps1`, `desktop/app.spec`, and release CI. |
| `apps/web/` | keep as hosted/portfolio surface | Keep, document, do not run in default desktop CI | Full Next.js app with product routes, tests, docs, and Vercel deploy-hook evidence in historical CI. It is not packaged, but deletion would retire a hosted/source-only surface, not just dead desktop code. |
| `apps/api/` | keep as hosted/development API | Keep, document | Railway Docker config points at `apps/api/Dockerfile`; ingestion workflows call `https://analisys-production.up.railway.app`; `src/read_service.py` still lazily imports API error types. |
| `railway.toml` | keep as hosted API config | Keep | Drives hosted FastAPI deployment; unrelated to packaged desktop. |
| `.github/workflows/ci.yml` web jobs | delete now | Remove from default CI | `apps/web` is no longer desktop runtime. Its lint/build/e2e failures should not block desktop CI. |
| `.github/workflows/perf-guardrails.yml` | archive/manual | Keep manual-only | Existing budgets target legacy Next/web/API route performance. Keep for manual hosted-web audits, but stop running on desktop pushes/PRs. |
| `.github/workflows/release-desktop.yml` | keep | Keep | Already builds only Python/PyInstaller and `apps/desktop-web`. |
| Data ingestion workflows | keep as hosted/data workflows | Keep | `ingest.yml`, `on_demand_ingest.yml`, `backfill_historico.yml`, `refresh.yml`, and `seed_catalog.yml` operate the data pipeline and hosted API verification. |
| `docs/perf/**` | archive/document | Keep as historical/reference | Primarily describes legacy Next/API guardrails. Not current desktop CI policy. |
| `docs/decisions/0004-*` | archive/document | Keep as ADR history | Records old Railway/Vercel decision. It remains useful migration history, not current desktop contract. |

## apps/web Decision

Decision: **keep as source-only hosted/portfolio surface**.

Evidence:

- `apps/web/package.json` is a full Next.js 16 app with lint, typecheck, build,
  unit, and Playwright scripts.
- `apps/web/app/**`, `apps/web/components/**`, and `apps/web/lib/**` contain
  product routes, design-system artifacts, desktop compatibility shims, and API
  proxy code.
- Historical CI included a `VERCEL_DEPLOY_HOOK` deploy job.
- `apps/web/README.md` already states the app is no longer compiled into the
  Windows desktop package.

It is not safe to delete now because deletion would be a hosted-surface
retirement, not a package cleanup. Phase 5C removes it from default desktop CI
instead.

## apps/api Decision

Decision: **keep as hosted/development API**.

Evidence:

- `railway.toml` points Railway at `apps/api/Dockerfile`.
- `apps/api/app/main.py` defines the FastAPI app, route registration, Sentry
  integration, and health surface.
- Data workflows call `https://analisys-production.up.railway.app`.
- `src/read_service.py` still imports `NotFoundError` from
  `apps.api.app.dependencies` in two lazy paths.
- Tests under `tests/` and `apps/api/tests/` still import API service helpers.

It is not safe to delete now. A later deletion phase should first move shared
error types from `apps/api` into `src/` and explicitly retire Railway.

## CI/Workflow Decision

Default CI now targets the desktop product:

- Python core tests under `tests/`.
- `desktop/app.py` and `desktop/bridge.py` compile check.
- Vite desktop UI typecheck/build under `apps/desktop-web`.
- Python coverage for `src` and `desktop`.

Default CI no longer runs `apps/web` lint/typecheck/build/unit/e2e. The legacy
web perf guardrail workflow is manual-only. Release CI remains unchanged in
substance: it builds `apps/desktop-web`, runs PyInstaller, validates flat ZIP
root, and publishes ZIP + SHA.

## Root Metadata Decision

- `requirements.txt` remains desktop/core oriented and does not include FastAPI.
- `apps/api/requirements*.txt` remain scoped to the hosted/development API.
- Root `AGENTS.md` now identifies `apps/desktop-web` as the packaged desktop UI
  and `apps/web` / `apps/api` as source-only surfaces.
- No root package manager was introduced.

## Documentation Updates

Updated current docs to state:

- `CVMAnalytics.exe` is Vite-only.
- Node/Next are not packaged.
- Persistent user data remains under `Documents/CVMAnalytics`.
- `apps/web` and `apps/api` are source-only / hosted surfaces.
- Legacy Next/API performance docs are historical/manual, not desktop CI policy.

## Files Deleted

No source folders were deleted in Phase 5C.

## Files Kept

- `apps/web/`
- `apps/api/`
- `railway.toml`
- hosted/data workflows
- historical release and migration docs

## Files Modified

- `.github/workflows/ci.yml`
- `.github/workflows/perf-guardrails.yml`
- `AGENTS.md`
- `README.md`
- `apps/web/AGENTS.md`
- `apps/web/README.md`
- `docs/CONTEXT.md`
- `docs/migration/README.md`
- `docs/migration/NEXT_AGENT_HANDOFF.md`
- `docs/migration/ARCHITECTURE.md`
- `docs/migration/PHASE_3_PARITY_MATRIX.md`
- `docs/migration/PHASE_3_PLAN.md`
- `docs/migration/PHASE_5_LEGACY_DELETION_AUDIT.md`
- `docs/perf/performance_guardrails.md`
- `docs/reference/perf-baseline.md`
- `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md`
- `docs/releases/v0.16.0.md`
- `apps/desktop-web/src/lib/api/companies.ts`
- `apps/desktop-web/src/lib/api/sectors.ts`
- `apps/desktop-web/src/routes/CompanyStatementsPage.tsx`
- `desktop/bridge.py`
- `tests/test_desktop_runtime_paths.py`

## Validation Plan

Minimum local validation:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
python -m py_compile desktop/app.py desktop/bridge.py
pytest tests/test_desktop_runtime_paths.py -q
.\desktop\build_desktop.ps1 -Version 0.16.0
.\dist\CVMAnalytics\CVMAnalytics.exe
.\dist\CVMAnalytics\CVMAnalytics.exe --diagnose-runtime
```

Inspect `dist/CVMAnalytics/_internal/` and confirm:

- `_internal/desktop-web/` exists.
- `_internal/node.exe` is absent.
- `_internal/web_standalone/` is absent.
- `update_helper.ps1` remains present.

## Release Decision

Phase 5C changes default CI and source documentation, and it validates the
desktop package with version `0.16.0`. Publish `v0.16.0` if the local package
and launch checks pass.

## Recommendation

**Keep hosted surfaces documented.**

Repository cleanup for the packaged desktop product is complete. Deleting
`apps/web/`, `apps/api/`, or `railway.toml` needs a separate hosted-surface
retirement approval.
