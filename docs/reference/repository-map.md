# Repository Map

CVMAnalytics · stable baseline v0.17.0 · updated 2026-05-23

Single-stop orientation for contributors and AI agents. Maps every top-level folder, classifies all GitHub Actions workflows, and distinguishes current docs from historical archive.

---

## Top-Level Folders

| Folder | Classification | Notes |
|---|---|---|
| `src/` | **Python core** | Pipeline, DB access, KPI engine, refresh worker, Excel export, standardizer, scraper. Start here for data/financial logic. |
| `desktop/` | **Desktop shell** | pywebview window, Python-JS bridge, auto-updater, PyInstaller spec, build script. Start here for packaging/updater changes. |
| `apps/desktop-web/` | **Packaged desktop UI** | Vite + React + TypeScript SPA. The only UI runtime bundled into `CVMAnalytics.exe`. Start here for desktop UI changes. |
| `apps/web/` | **Source-only hosted surface** | Next.js 16. Not packaged. Not part of the desktop runtime. Retained pending a hosted-surface retirement decision. |
| `apps/api/` | **Source-only hosted surface** | FastAPI hosted on Railway. Not packaged. Not part of the desktop runtime. `railway.toml` points here. |
| `tests/` | **Test suite** | pytest for Python core and desktop runtime. Run with `pytest tests/`. |
| `docs/` | **Documentation** | Active reference, completed migration history, ADRs, performance baselines. See doc status table below. |
| `scripts/` | **Utility / tooling** | Setup, diagnostics, validation, batch ops. Mix of active and historical scripts. |
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
| `.github/` | **CI/CD** | 10 workflow files. See workflow table below. |
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
| `railway.toml` | Railway deployment config for `apps/api/`. Retained pending hosted-surface retirement decision. |

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
| `perf-guardrails.yml` | **Obsolete / manual-only** | Manual | Legacy Next.js performance guardrails. Self-annotated as obsolete for desktop CI. Does not block the desktop release pipeline. Retained for optional hosted-web audits. |

---

## Documentation Status

### Current — active contracts and reference

| Path | What it covers |
|---|---|
| `docs/CONTEXT.md` | Data model, column conventions, financial statement structure. Read before touching `src/` or `apps/api/`. |
| `docs/decisions/` | Architecture Decision Records 0001–0006. Authoritative for architecture choices. |
| `docs/governance/autonomous-mode.md` | Operating rules for long-running autonomous AI sessions. |
| `docs/governance/on-demand-release-evidence.md` | Release evidence protocol for on-demand releases. |
| `docs/reference/repository-map.md` | This file. Repo orientation and folder/workflow/doc classification. |
| `docs/reference/perf-baseline.md` | Performance baselines for the Python core. |
| `docs/reference/gics-import.md` | GICS import reference. |
| `docs/reference/product-page-prompts.md` | Product page copy prompts. |
| `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md` | Rules for implementing Vite UI screens in `apps/desktop-web/`. Read before any desktop UI change. |
| `docs/perf/` | Performance benchmarks and guardrails. |
| `docs/releases/` | Release notes per version (v0.2.0 through v0.17.0). |
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

### Hosted-surface docs — describe `apps/web/` and `apps/api/`, not the desktop

These documents describe source-only hosted surfaces that are **not part of the packaged desktop runtime**. They remain in the repo pending a hosted-surface retirement decision.

| Path | What it covers |
|---|---|
| `docs/reference/sitemap.md` | Information architecture blueprint for the hosted web app (`apps/web/`). Not the desktop. |
| `docs/reference/interface-map.md` | Frontend route × API endpoint map for `apps/web/` and `apps/api/`. Not the desktop bridge. |
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
| `apps/web/`, `apps/api/`, `railway.toml` | Hosted surfaces. Deletion requires an explicit retirement decision. |
