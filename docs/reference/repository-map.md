# Repository Map

The single map of the CVMAnalytics repository: active app paths, routes,
folders, commands, and what is historical. Last verified from local files on
2026-10-29. For the canonical documentation index, see the "Canonical
Documentation" table in [`README.md`](../../README.md). For the current project
state, see [`docs/STATUS.md`](../STATUS.md).

If another document conflicts with this file, inspect the active code paths
below before changing anything.

## Active App

| Area | Active path |
|---|---|
| Packaged product | `dist/CVMAnalytics/CVMAnalytics.exe`, built by `desktop/build_desktop.ps1` |
| Frontend | `apps/desktop-web` (Vite + React + TypeScript); the only UI bundled into the executable |
| Desktop shell | `desktop/app.py` |
| Bridge | `desktop/bridge.py` and `desktop/bridge_api/` |
| Bridge services | `desktop/services.py` |
| Python core/data | `src/` |
| HTTP API adapter | `apps/api` (FastAPI tests/dev-hosted access, not the desktop UI) |
| Landing page | `apps/landing` (GitHub Pages download surface, not the product runtime) |

Runtime integration: `apps/desktop-web/src/lib/bridge/adapter.ts` ->
`window.pywebview.api` -> `desktop/bridge.py` / `desktop/bridge_api/` ->
`desktop/services.py` / `src/`. See [`docs/architecture.md`](../architecture.md).

## Active Routes

See "Active Routes" in [`docs/architecture.md`](../architecture.md). The
route source is `apps/desktop-web/src/App.tsx`.

## Top-Level Folders

| Folder | Classification | Notes |
|---|---|---|
| `src/` | Active Python core | Settings, CVM ingestion, SQLite schema, read services, companies, financials, Excel, refresh jobs, energy/news modules |
| `desktop/` | Active desktop runtime | pywebview entrypoint, bridge/mixins, services, updater, PyInstaller spec, build script |
| `apps/desktop-web/` | Active packaged UI | Vite + React + TypeScript |
| `apps/api/` | Active HTTP adapter | FastAPI adapter and API tests; not the packaged desktop UI |
| `apps/landing/` | Static public surface | GitHub Pages download surface |
| `tests/` | Active tests | Python core/desktop tests |
| `scripts/` | Active tooling | See Scripts below |
| `docs/` | Documentation | Canonical docs, reference docs, ADRs, release notes, archive |
| `data/` | Data assets/dev data | Import CSVs and schema files are active; local DB/raw/cache outputs are runtime/dev artifacts |
| `build/`, `dist/`, `output/`, `tmp/`, `scratch/` | Generated/local artifacts | Not source of truth |
| `.github/` | CI/CD and guardrails | Workflows, PR template, guardrail policy |
| `.claude/` | AI tooling | Agent/session tooling, not product runtime |

## Root Files

| File | Purpose |
|---|---|
| `README.md` | Project overview and canonical documentation index |
| `AGENTS.md` | AI agent operating contract |
| `requirements.txt` | Root Python dependencies |
| `main.py` | Headless CLI refresh entrypoint |
| `pytest.ini`, `conftest.py` | pytest discovery/config |
| `railway.toml` | Deployment config for `apps/api`, not the desktop UI |

There is no root `package.json`. The active Node package is
`apps/desktop-web/package.json`.

## Scripts

| Folder | Purpose |
|---|---|
| `scripts/data/` | Refresh, backfill, catalog seed, identity/GICS import, canonical dictionaries, energy stores and marts, storage budget and managed-ingestion checks |
| `scripts/setup/` | Database/table setup and Windows/worktree bootstrap |
| `scripts/diagnostics/` | Runtime doctor, smoke validation, read-path benchmarks, bridge method inventory, packaged candidate validation |
| `scripts/qa/` | Consolidation, line-id, and workbook verification |
| `scripts/release/` | Desktop dev launchers, MOTW tests, PR helper |
| `scripts/governance/` | Repository contract tests and worktree helpers |

`pytest.ini` includes `tests` and `scripts`, so `test_*.py` files under
`scripts/` are pytest-discovered.

## GitHub Workflows

| Workflow | Purpose |
|---|---|
| `ci.yml` | Governance contracts, Python compile/tests, coverage, Vite typecheck/build |
| `release-desktop.yml` | Windows desktop build and GitHub Release publication (candidate/attest/publish phases) |
| `deploy-landing.yml` | GitHub Pages deploy for `apps/landing` |
| `refresh.yml` | Manual CVM refresh into the external PostgreSQL (schedule disabled) |
| `backfill_historico.yml` | Manual historical backfill (quarterly gap-fill schedule disabled) |
| `ingest.yml` | Manual CVM ingestion |
| `on_demand_ingest.yml` | Manual per-company ingestion |
| `seed_catalog.yml` | Manual catalog seed |
| `pr-issue-guardrails.yml` | PR issue-link governance |

## Active Commands

See [`docs/development.md`](../development.md) for the full command map.

```powershell
# real desktop dev
python -m desktop.app --dev

# Vite checks
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build

# Python checks
python -m py_compile desktop/app.py desktop/bridge.py
pytest tests -q
pytest apps/api/tests -q

# desktop package build
.\desktop\build_desktop.ps1
```

## Historical / Non-Canonical

| Area | Status |
|---|---|
| `docs/archive/migration/` | Completed Next/Node to Vite migration history |
| `docs/archive/planning-2026/` | Point-in-time audits, plans, specs, and planning prompts |
| `docs/decisions/` | ADRs; point-in-time decisions, not daily instructions. Check each status. |
| `docs/releases/` | Partial local release notes; GitHub Releases are the published source |
| `docs/reference/v2-api-contract.md` | HTTP API adapter contract for `apps/api`; not the desktop bridge |
| `docs/perf/`, `docs/diagnostics/` | Dated benchmark/audit evidence; context, not current state |
| `docs/vendor/` | Vendor/source reference material |
| `apps/web` | Old Next.js app, removed from the active tree. Do not recreate it. |

## Do Not Touch Without A Plan

| Entry | Why |
|---|---|
| `desktop/app.spec` | Wrong bundle path can produce a broken executable |
| `desktop/build_desktop.ps1` | Build/version/provenance pipeline |
| `desktop/updater.py`, `desktop/update_helper.ps1` | Installed-user update safety and rollback contract |
| `.github/workflows/release-desktop.yml` | Published artifact creation |
| `src/platform/settings.py` | User data path resolution |
| `data/import/canonical_accounts.csv`, `data/import/gics_mapping.csv` | Bundled/imported data contracts |
| `src/financials/excel_exporter.py` | Financial workbook auditability |
| `apps/api/`, `railway.toml` | HTTP API/deploy surface; still active |
