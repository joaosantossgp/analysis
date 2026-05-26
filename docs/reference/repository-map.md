# Repository Map

CVMAnalytics · active Vite desktop baseline · updated 2026-05-26

Single-stop orientation for contributors and AI agents. Maps every top-level folder, classifies all GitHub Actions workflows, and distinguishes current docs from historical archive.

---

## Top-Level Folders

| Folder | Classification | Notes |
|---|---|---|
| `src/` | **Python core** | Pipeline, DB access, KPI engine, refresh worker, Excel export, standardizer, scraper. Start here for data/financial logic. |
| `desktop/` | **Desktop shell** | pywebview window, Python-JS bridge, auto-updater, PyInstaller spec, build script. Start here for packaging/updater changes. |
| `apps/desktop-web/` | **Packaged desktop UI** | Vite + React + TypeScript SPA. The only UI runtime bundled into `CVMAnalytics.exe`. Start here for desktop UI changes. |
| `apps/api/` | **HTTP API adapter** | FastAPI API/test surface. Not the desktop frontend and not packaged as UI. `railway.toml` points here. |
| `tests/` | **Test suite** | pytest for Python core and desktop runtime. Run with `pytest tests/`. |
| `docs/` | **Documentation** | Active reference, completed migration history, ADRs, performance baselines. See doc status table below. |
| `scripts/` | **Utility / tooling** | Setup, diagnostics, validation, batch ops. See the `scripts/` cluster table below. |
| `landing/` | **Marketing surface** | Static HTML deployed to GitHub Pages. Not the product runtime. |
| `config/` | **Reference data** | `canonical_accounts.csv` — CVM account mapping used by the financial standardizer. Referenced by `src/settings.py` and 8+ scripts. Do not move without updating all callers and re-verifying the packaged build. |
| `migrations/` | **DB schema** | SQLite migration SQL files. |
| `data/` | **Local dev data** | Dev-mode SQLite DB, raw CVM inputs, cache. Content is gitignored. |
| `archive/` | **Historical archive** | Governance snapshots, old experiments, old local-ops evidence. Excluded from AI context via `.claudeignore`. Do not treat as current. |
| `build/` | **Generated artifact** | PyInstaller build intermediates. Gitignored. Do not commit. |
| `dist/` | **Generated artifact** | PyInstaller final output (`CVMAnalytics.exe`). Gitignored. |
| `output/` | **Generated artifact** | Dev-mode Excel exports and test output. Content is gitignored. |
| `release/` | **Historical artifact** | Old release ZIPs (v0.3.x–v0.13.x). GitHub Releases is the authoritative download source. |
| `release_validation_v0.12.0/` | **Historical artifact** | Old validation artifacts from pre-v0.17.0 releases. |
| `release_validation_v0.13.0/` | **Historical artifact** | Old validation artifacts from pre-v0.17.0 releases. |
| `skills/` | **AI agent tooling** | Agent skill definitions (`doc-architect`, `review-code`, `ui-review`). Not source code. |
| `.github/` | **CI/CD** | 9 workflow files. See workflow table below. |
| `.claude/` | **AI tooling** | Claude Code session memory. |

---

## Root-Level Files

| File | Purpose |
|---|---|
| `README.md` | Main project overview. Start here. |
| `AGENTS.md` | AI agent operating contract. AI agents read this first. |
| `COMO_RODAR.md` | Dev run guide (Portuguese). Practical startup steps. |
| `DESIGN.md` | Design system tokens + visual principles. |
| `PRODUCT.md` | Product brief: users, purpose, brand, design principles. |
| `main.py` | Headless CLI refresh entry point. |
| `conftest.py` | pytest shared fixtures. Must stay at root for test discovery. |
| `pytest.ini` | pytest discovery config. Must stay at root. |
| `requirements.txt` | Python dependencies. Installed by CI and dev setup. |
| `railway.toml` | Railway deployment config for `apps/api/`. Not part of the desktop UI runtime. |

---

## `scripts/` Cluster Overview

| Cluster | Files | Status | Notes |
|---|---|---|---|
| **CI data pipeline** | `atualizar_todos.py`, `atualizar_dados.ps1`, `batch_completo.py`, `restaurar_historico.py`, `setup_db.py`, `setup_companies_table.py`, `seed_catalog.py` | Active | Referenced from `.github/workflows/*.yml`. High-risk — breaking these breaks CI. |
| **Desktop diagnostics / dev** | `runtime_doctor.py`, `bootstrap_windows.ps1`, `smoke_validate.py`, `update_base_smoke.py`, `phase1_pywebview_smoke.py`, `db_portability_smoke.py`, `canonicalize_data_layout.py` | Active | Referenced from `README.md`, `COMO_RODAR.md`, `docs/migration/`. |
| **Data utilities** | `import_company_gics.py`, `backfill_company_gics.py`, `build_canonical_dict.py`, `expand_tickers.py` | Active | Manual maintenance tools. `build_canonical_dict.py` is wired into `src/standardizer.py` error path. |
| **Excel-export manual QA** | `quick_verify.py`, `verify_consolidation.py`, `verify_line_id_base.py`, `final_verification.py`, `workbook_paths.py` | Active manual QA | Documented in `COMO_RODAR.md` §8. Never CI. `final_verification.py` is a historical bug-fix regression check. |
| **MOTW / release validation (reusable)** | `test_motw_explorer.ps1`, `test_motw_launch.ps1`, `test_motw_strip.py` | Active | Generic harness, parameterized by ZIP path. Use for any current release. |
| **Performance benchmarks** | `benchmark_read_paths.py`, `benchmark_real_read_paths.py` | Active manual QA | Query/read-path benchmarks. No Next.js route guardrail remains active. |
| **pytest-discovered tests in `scripts/`** | `test_motw_strip.py`, `test_seed_catalog.py`, `test_update_base_smoke.py` | Active | Discovered via `pytest.ini` `testpaths = tests scripts`. Moving these requires updating `pytest.ini`. |
| **Dev tooling** | `pr_complete.ps1`, `fix-git-config.ps1`, `worktree_create.ps1`, `worktree_remove.ps1`, `worktree_status.ps1` | Active | Git / worktree helpers. Referenced from `AGENTS.md`, `docs/reference/autonomous-mode.md`. |
| **Archived (moved out of `scripts/`)** | `docs/migration/legacy-release-validation/test_ci_v033_motw.ps1`, `.../test_ci_v034_full.ps1` | Historical | Version-pinned to v0.3.3 / v0.3.4. Cannot be re-run against current releases. Kept under `docs/migration/` for historical reference. |
| **Removed (obsolete)** | `calc_financial_kpis.py`, `patch_database_sectors_v2.py`, `gerar_base_analitica.py`, `perf_guardrail.py`, `seed_web_smoke_db.py` | Deleted | Superseded by active core logic or removed with the legacy Next.js app. |

---

## GitHub Actions Workflows

| Workflow file | Status | Trigger | Purpose |
|---|---|---|---|
| `ci.yml` | **Active** | Push / PR | Python core tests + compile checks |
| `release-desktop.yml` | **Active** | Tag push / manual | Builds Windows EXE, publishes GitHub Release |
| `deploy-landing.yml` | **Active** | Push to `landing/**` / manual | Deploys `landing/` to GitHub Pages |
| `refresh.yml` | **Active** | Scheduled (1st of each month) | Monthly CVM data refresh on Railway |
| `ingest.yml` | **Active** | Manual | Full CVM ingestion with configurable year range |
| `on_demand_ingest.yml` | **Active** | Manual | Per-company on-demand CVM refresh |
| `backfill_historico.yml` | **Active** | Manual | Historical CVM backfill from a given start year |
| `seed_catalog.yml` | **Active** | Manual | Seed companies catalog |
| `pr-issue-guardrails.yml` | **Active** | PR events | Governance: PR must link a GitHub issue |

---

## Documentation Status

### Current — active contracts and reference

| Path | What it covers |
|---|---|
| `docs/CONTEXT.md` | Data model, column conventions, financial statement structure. Read before touching `src/` or `apps/api/`. |
| `docs/decisions/` | Architecture Decision Records 0001–0006. Authoritative for architecture choices. |
| `docs/governance/autonomous-mode.md` | Operating rules for long-running autonomous AI sessions. |
| `docs/governance/on-demand-release-evidence.md` | Release evidence protocol for on-demand releases. |
| `docs/active-project-map.md` | Concise source-of-truth map for active paths, commands, and AI-agent warnings. |
| `docs/reference/repository-map.md` | This file. Repo orientation and folder/workflow/doc classification. |
| `docs/REPOSITORY_PROFILE.md` | Canonical GitHub "About" panel values (description, homepage, topics). Apply via `gh` or manually. |
| `docs/reference/gics-import.md` | GICS import reference. |
| `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md` | Rules for implementing Vite UI screens in `apps/desktop-web/`. Read before any desktop UI change. |
| `docs/perf/benchmark_read_paths.md` | **Benchmark report.** Issue #134 — read-path benchmark on the CVM query layer (synthetic SQLite). |
| `docs/perf/polars-benchmark.md` | **Benchmark report.** Issue #110 — Polars vs Pandas comparison on the CVM ingestion pipeline. |
| `docs/releases/` | Release notes per version. See `docs/releases/README.md` for the index and known coverage gaps. |
| `AGENTS.md` | AI agent operating contract. |
| `COMO_RODAR.md` | Practical dev/run guide. |
| `DESIGN.md` | Design system tokens + brand principles. |
| `PRODUCT.md` | Product brief. |

### Historical — completed migration phases

These documents record the completed multi-phase migration from Next/Node to Vite-only runtime (through v0.17.0). They are **not current instructions** — they are engineering history.

| Path | What it covers |
|---|---|
| `docs/migration/README.md` | Phase tracker overview. All phases released. |
| `docs/migration/NEXT_AGENT_HANDOFF.md` | Primary handoff doc for the migration. Migration is complete as of v0.17.0. |
| `docs/migration/ARCHITECTURE.md` | Current architecture map + historical Phase 2 snapshot. The "Current" section is still accurate. |
| `docs/migration/PHASE_0_*.md` | Phase 0 release checkpoint and user data safety spec. |
| `docs/migration/PHASE_1_VITE_SHELL.md` | Phase 1 Vite SPA shell implementation. |
| `docs/migration/PHASE_2_VITE_RUNTIME.md` | Phase 2 opt-in Vite runtime. |
| `docs/migration/PHASE_3_*.md` | Phase 3 parity matrix and incremental slice plans. |
| `docs/migration/PHASE_5_LEGACY_DELETION_AUDIT.md` | Phase 5A deletion audit. |
| `docs/migration/PHASE_5C_SOURCE_LEGACY_CLEANUP.md` | Phase 5C source cleanup decision. |
| `docs/migration/PHASE_6C_STABLE_RELEASE_PASS.md` | Phase 6C stable release pass. |
| `docs/migration/PHASE_6_FINAL_HARDENING_AUDIT.md` | Phase 6 final hardening audit. |
| `docs/migration/SMOKE_RECIPES.md` | Smoke test recipes used during migration. Still useful for ad-hoc validation. |

### API docs — describe `apps/api/`, not the desktop UI

These documents describe the HTTP API adapter. The active desktop app communicates
through `window.pywebview.api`, not through these HTTP routes.

| Path | What it covers |
|---|---|
| `docs/reference/v2-api-contract.md` | HTTP API contract for `apps/api/` V2. Not the desktop `window.pywebview.api` bridge. |

---

## What Not to Touch Without a Plan

| Entry | Why |
|---|---|
| `desktop/app.spec` | PyInstaller spec. A wrong path produces a broken EXE with no obvious error at build time. |
| `desktop/build_desktop.ps1` | Build pipeline. Test end-to-end on Windows before merging. |
| `desktop/update_helper.ps1` | Updater swap script. The allowlist entries are a contract with already-deployed app versions. |
| `.github/workflows/release-desktop.yml` | Release CI. Changes affect artifacts downloaded by real users. |
| `src/settings.py` | User data paths. Wrong changes break the DB location for users running the packaged app. |
| `config/canonical_accounts.csv` | Referenced by `src/settings.py` and 8 scripts. Moving requires coordinated multi-file update + build verification. |
| `apps/api/`, `railway.toml` | HTTP API/deploy surface. Not part of the desktop UI, but still active for API tests/dev-hosted access. |
