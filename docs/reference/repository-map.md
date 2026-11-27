# Repository Map

The single map of the CVMAnalytics repository: active app paths, routes,
folders, commands, and what is historical. Route/navigation entries and the
folder classifications below were checked on 2026-11-16; this is not validation
that every tool or externally dependent workflow currently executes successfully.
For the canonical documentation index, see the "Canonical
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

## Maintenance entry points

- Financial queries/exports: `src/financials/read_service.py` is the compatibility
  facade; explicit writes are in `refresh_commands.py` and `mapping_commands.py`
  in the same directory. See [service boundaries](../architecture.md#service-and-coverage-boundaries).
- Companies Coverage: `apps/desktop-web/src/routes/CoveragePage.tsx` composes the
  workflow modules under `apps/desktop-web/src/components/coverage/`, mounted at
  `/empresas/coverage` and its prioritization, work-queue and capacity routes.
- Assets & Mapping and Indicator Sources: exports in
  `apps/desktop-web/src/routes/CountryKpisPage.tsx` serve Companies and Settings;
  their file location does not make them Indicator Library screens.

## Active Routes

The [architecture route table](../architecture.md#active-routes) owns the full
inventory, compatibility redirects and developer gates. Route definitions are in
[App.tsx:108](../../apps/desktop-web/src/App.tsx#L108); primary navigation is in
[ModuleNav.tsx:16](../../apps/desktop-web/src/components/shell/ModuleNav.tsx#L16),
with contextual tabs in
[SubNav.tsx:16](../../apps/desktop-web/src/components/shell/SubNav.tsx#L16).

| Primary entry | Route | Ownership |
|---|---|---|
| Home | `/` | Analyst Home and optional widgets |
| Companies | `/empresas` | Directory, company analysis, Coverage (`/empresas/coverage`) and Assets & Mapping (`/empresas/assets`) |
| Sectors | `/setores` | Sector/subsector directory and analysis |
| Indicators | `/indicators` | Indicator Library and Energy |
| Settings | `/settings` | Data, sources, Indicator Sources (`/settings/indicator-sources`), storage and app diagnostics |

Coverage is inside Companies; old `/coverage/*` URLs redirect there. Settings'
Data completeness (`/settings/data`) reports local-data completeness and is a
separate surface.
Company Excel mapping retains its route and dedicated window.

News is retired from primary navigation. Old `/news/*` URLs show
[RetiredNewsPage](../../apps/desktop-web/src/routes/RetiredNewsPage.tsx#L4), and
saved Home news widgets show
[RetiredNewsCard](../../apps/desktop-web/src/components/home/widgets/RetiredNewsCard.tsx#L5)
without querying news. The former `NewsPage.tsx` route file was removed;
`src/news/`, the News bridge and downloaded data/settings remain preserved.

## Top-Level Folders

| Folder | Classification | Notes |
|---|---|---|
| `src/` | Active Python core | Settings, CVM ingestion, SQLite schema, read services, companies, financials, Excel, refresh jobs, energy modules and retained News backend |
| `desktop/` | Active desktop runtime | pywebview entrypoint, bridge/mixins, services, updater, PyInstaller spec, build script |
| `apps/desktop-web/` | Active packaged UI | Vite + React + TypeScript |
| `apps/api/` | Active HTTP adapter | FastAPI adapter and API tests; not the packaged desktop UI |
| `apps/landing/` | Static public surface | GitHub Pages download surface |
| `tests/` | Active tests | Python core/desktop tests |
| `scripts/` | Active tooling | See Scripts below |
| `tools/` | Investigation tooling | Energy database profiling and phase-2.5 experiments; inspect scope and output paths before manual use |
| `docs/` | Documentation | Canonical docs, reference docs, ADRs, release notes, archive |
| `docs/research/` | Research and validation records | Proposals, diagnostics and evidence for delivered work; each record's date, baseline, status and scope determine its authority |
| `docs/governance/` | Delivery/validation evidence | Dated owner decisions and scoped checks; active operating rules remain in `AGENTS.md` |
| `docs/testing/` | Manual validation references | Check individual status; the earlier Home checklist is historical |
| `data/` | Data assets/dev data | Import CSVs and schema files are active; local DB/raw/cache outputs are runtime/dev artifacts |
| `build/`, `dist/`, `output/`, `tmp/`, `scratch/` | Generated/local artifacts | Not source of truth |
| `.github/` | CI/CD | Workflows, issue and PR templates |
| `.claude/` | AI tooling | Agent/session tooling, not product runtime |
| `.agents/skills/` | Vendored agent skills | Upstream skills and pinned integrity manifest; see `docs/agents/skills.md` |
| `.superpowers/` | Tracked investigation history | Point-in-time identity, interview-scope and shutdown notes; not active plans or runtime code |

`docs/superpowers/` is a separate, ignored location for working plans/specs.
GitHub issues remain the spec of record. Do not infer current implementation or
approval from a folder name; use the document's status and owning code.

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
| `scripts/governance/` | Repository contract tests and legacy worktree helpers |
| `scripts/curation/` | Development-only GICS curation tools (structure extraction, Claude batch proposals); not app runtime, SDK installed separately |

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
| `pr-issue-guardrails.yml` | Requires issue references (`Closes`/`Refs`), non-empty `## Documentation impact`, validates existence and non-PR identity, and rejects closing goals |
| `update-agent-skills.yml` | Offline skill integrity and regression checks on PRs or manual dispatch; updates are manual |

## Active Commands

[Development](../development.md) is the canonical command map for setup,
project-interpreter tests, desktop/browser/mock modes, API and diagnostics.
[Build and release](../build-release.md) owns packaging and release validation.
Do not copy commands from historical plans.

## Historical / Non-Canonical

| Area | Status |
|---|---|
| `docs/archive/migration/` | Completed Next/Node to Vite migration history |
| `docs/archive/planning-2026/` | Point-in-time audits, plans, specs, and planning prompts |
| `docs/archive/governance/` | Retired lane-based autonomous mode |
| `docs/decisions/` | ADRs; point-in-time decisions, not daily instructions. Check each status. |
| `docs/releases/` | Partial local release notes; GitHub Releases are the published source |
| `docs/reference/v2-api-contract.md` | HTTP API adapter contract for `apps/api`; not the desktop bridge |
| `docs/perf/`, `docs/diagnostics/` | Dated benchmark/audit evidence; context, not current state |
| `docs/research/`, `docs/governance/` | Dated proposals or validation evidence; inspect status, baseline and limits rather than treating every record as a proposal or current contract |
| `.superpowers/` | Earlier investigations; preserve as evidence and revalidate claims before acting |
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
| `data/import/canonical_accounts.csv` | Bundled/imported data contract |
| `data/reference/gics_structure.csv` | Current GICS codes and names (no definitions) used by curation |
| `data/curation/gics_curated.csv` | Curated GICS sub-industry per active CVM company (to be loaded by the app, #518); review evidence and cost reports live beside it |
| `src/financials/excel_exporter.py` | Financial workbook auditability |
| `apps/api/`, `railway.toml` | HTTP API/deploy surface; still active |
