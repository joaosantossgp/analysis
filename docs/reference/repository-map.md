# Repository Map

CVMAnalytics repository orientation, last verified from local files on
2026-06-19.

This map classifies active code, generated artifacts, historical material, and
canonical documentation. For the short app map, see
[`../active-project-map.md`](../active-project-map.md).

## Top-Level Folders

| Folder | Classification | Notes |
|---|---|---|
| `src/` | Active Python core | Data settings, CVM ingestion, SQLite/database schema, read services, companies, financials, Excel, refresh jobs, energy/news modules |
| `desktop/` | Active desktop runtime | pywebview entrypoint, bridge/mixins, services, updater, PyInstaller spec, build script |
| `apps/desktop-web/` | Active packaged UI | Vite + React + TypeScript; only UI bundled into `CVMAnalytics.exe` |
| `apps/api/` | Active HTTP adapter | FastAPI adapter and API tests/dev-hosted HTTP access; not the packaged desktop UI |
| `apps/landing/` | Static public surface | GitHub Pages/download surface; not product runtime |
| `tests/` | Active tests | Python core/desktop tests; run `pytest tests -q` |
| `scripts/` | Active tooling | Setup, data maintenance, diagnostics, QA, release helpers, governance scripts |
| `docs/` | Documentation | Canonical docs, reference docs, ADRs, release notes, archived migration history |
| `data/` | Data assets/dev data | Import CSVs and schema files are active; local DB/raw/cache outputs are runtime/dev artifacts |
| `archive/` | Historical archive | Old governance snapshots/experiments; not active guidance |
| `build/`, `dist/`, `output/`, `tmp/`, `scratch/` | Generated/local artifacts | Do not treat as source-of-truth docs or code |
| `.github/` | CI/CD and guardrails | Workflows, PR template, guardrail policy |
| `.claude/`, `skills/` | AI tooling | Agent/session tooling, not product runtime |

## Root Files

| File | Purpose |
|---|---|
| `README.md` | Minimal project overview and canonical doc index |
| `AGENTS.md` | AI agent operating contract |
| `requirements.txt` | Root Python dependencies |
| `main.py` | Headless CLI refresh entrypoint |
| `pytest.ini`, `conftest.py` | pytest discovery/config |
| `railway.toml` | Deployment config for `apps/api`, not desktop UI |
| `CVMAnalytics-windows*.zip` | Local generated release artifacts, not source |

There is no root `package.json` or workspace package manager config. The active
Node package is `apps/desktop-web/package.json`.

## Scripts

| Area | Active files |
|---|---|
| `scripts/data/` | `atualizar_todos.py`, `batch_completo.py`, `restaurar_historico.py`, `seed_catalog.py`, `sync_identity.py`, `expand_tickers.py`, `import_company_gics.py`, `backfill_company_gics.py`, `build_canonical_dict.py`, `canonicalize_data_layout.py`, `atualizar_dados.ps1`, `test_seed_catalog.py` |
| `scripts/setup/` | `setup_db.py`, `setup_companies_table.py`, `bootstrap_windows.ps1` |
| `scripts/diagnostics/` | `runtime_doctor.py`, `smoke_validate.py`, `db_portability_smoke.py`, `update_base_smoke.py`, `test_update_base_smoke.py`, `phase1_pywebview_smoke.py`, `benchmark_read_paths.py`, `benchmark_real_read_paths.py`, `calibrate_mappings.py` |
| `scripts/qa/` | `quick_verify.py`, `verify_consolidation.py`, `verify_line_id_base.py`, `final_verification.py`, `workbook_paths.py` |
| `scripts/release/` | `dev-desktop.ps1`, `dev-desktop-release-data.ps1`, `test_motw_explorer.ps1`, `test_motw_launch.ps1`, `test_motw_strip.py`, `pr_complete.ps1` |
| `scripts/governance/` | `worktree_create.ps1`, `worktree_remove.ps1`, `worktree_status.ps1`, `fix-git-config.ps1` |

`pytest.ini` includes `tests` and `scripts`, so `test_*.py` files under scripts
are pytest-discovered.

## GitHub Workflows

Workflow files under `.github/workflows/` are active unless explicitly removed:

| Workflow | Purpose |
|---|---|
| `ci.yml` | Python compile/tests, coverage, and Vite typecheck/build |
| `release-desktop.yml` | Windows desktop build and GitHub Release publication |
| `deploy-landing.yml` | GitHub Pages deploy for `apps/landing` |
| `refresh.yml` | Scheduled CVM refresh workflow |
| `ingest.yml` | Manual CVM ingestion |
| `on_demand_ingest.yml` | Manual per-company ingest |
| `backfill_historico.yml` | Manual historical backfill |
| `seed_catalog.yml` | Manual catalog seed |
| `pr-issue-guardrails.yml` | PR issue-link governance |

## Canonical Documentation

| Topic | Path |
|---|---|
| Project overview | `README.md` |
| Agent rules | `AGENTS.md` |
| Active project map | `docs/active-project-map.md` |
| Runtime architecture | `docs/architecture.md` |
| Data sources and auditability | `docs/data-sources.md` |
| Excel export standards | `docs/excel-exports.md` |
| Development commands | `docs/development.md` |
| Build/release/updater | `docs/build-release.md` |
| Troubleshooting | `docs/troubleshooting.md` |
| Product workflows | `docs/product-workflows.md` |
| Data/modeling context | `docs/CONTEXT.md` |
| Settings/update flow | `docs/settings-module.md`, `docs/database-updates.md` |
| On-demand company refresh | `docs/company-on-demand-updates.md` |
| UI implementation rules | `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md` |
| GICS import | `docs/reference/gics-import.md` |
| Indicators | `docs/reference/indicators-module.md` |
| Energy references | `docs/reference/energy-utilities-sin-kpis.md`, `docs/reference/energy-utilities-distribution.md`, `docs/reference/fuel-distribution-source-intake.md` |

`docs/COMO_RODAR.md` remains a Portuguese operational guide. The canonical
English command map is `docs/development.md`.

## Historical / Non-Canonical Docs

| Area | Status |
|---|---|
| `docs/archive/migration/` | Completed Next/Node to Vite migration history; not current operating guidance |
| `docs/decisions/` | ADRs; point-in-time decisions, not daily instructions |
| `docs/releases/` | Partial local release notes; GitHub Releases are the published source |
| `docs/reference/v2-api-contract.md` | HTTP API adapter contract for `apps/api`; not the desktop bridge |
| `docs/reference/coverage_*`, `docs/plans/` | Product/workflow planning context; not proof of implemented features |
| `docs/perf/` and `docs/diagnostics/` | Dated benchmark/audit evidence; useful context, not universal current state |
| `docs/vendor/` | Vendor/source reference material, not operating guidance |

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
| `apps/api/`, `railway.toml` | HTTP API/deploy surface; not desktop UI but still active |

## Legacy Warning

The old `apps/web` Next.js app has been removed. Do not infer current runtime
architecture from archive docs, old ADRs, release notes, or deleted path names.
