# Active Project Map

Short source-of-truth map for CVMAnalytics. If another document conflicts with
this file, inspect the active code paths below before changing anything.

## Active App

| Area | Active path |
|---|---|
| Packaged product | `dist/CVMAnalytics/CVMAnalytics.exe` |
| Frontend | `apps/desktop-web` (Vite + React + TypeScript) |
| Desktop shell | `desktop/app.py` |
| Bridge | `desktop/bridge.py` and `desktop/bridge_api/` |
| Python core/data | `src/` |
| Bridge services | `desktop/services.py` |
| HTTP API adapter | `apps/api` (FastAPI tests/dev-hosted access, not desktop UI) |
| Landing page | `apps/landing` (GitHub Pages/download surface, not product runtime) |

## Active Routes

Route source: `apps/desktop-web/src/App.tsx`.

- `/`, `/empresas`, `/empresas/:cdCvm`, company statements, model mapping, and
  company coverage status.
- `/setores`, sector details, and subsector details.
- `/coverage`, `/coverage/prioritization`, `/coverage/work-queue`.
- `/news`, `/news/latest`.
- `/indicators`.
- `/settings` with health, storage, sources/imports, updates, coverage, and
  diagnostics.
- `/dev/data-ops`.

Compatibility redirects:

- `/atualizar-base` -> `/settings/updates`;
- `/data-coverage` -> `/settings/coverage`;
- `/status` -> `/settings/diagnostics`;
- `/country-kpis` -> `/indicators`;
- `/empresas/:cdCvm/indicadores` -> `/empresas/:cdCvm`.

## Canonical Docs

| Topic | Doc |
|---|---|
| Architecture | `docs/architecture.md` |
| Data sources | `docs/data-sources.md` |
| Excel exports | `docs/excel-exports.md` |
| Development | `docs/development.md` |
| Build/release/updater | `docs/build-release.md` |
| Troubleshooting | `docs/troubleshooting.md` |
| Product workflows | `docs/product-workflows.md` |
| Full repository map | `docs/reference/repository-map.md` |
| Agent rules | `AGENTS.md` |

## Active Commands

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

## Legacy / Historical

- `apps/web` was the old Next.js app and has been removed from the active tree.
- `docs/archive/migration/` is completed migration history, not current
  operating guidance.
- ADRs under `docs/decisions/` are point-in-time decision records.
- Release notes under `docs/releases/` are historical per-version notes; GitHub
  Releases are the published release source.

## Agent Warning

- Verify active runtime from scripts/config before documenting it as fact.
- Do not create or modify Next.js routes, pages, layouts, API routes, or
  components.
- Do not infer current architecture from `archive/`, `docs/archive/migration/`,
  release notes, or old ADR context.
- Inspect `apps/desktop-web`, `desktop/`, `src/`, and `apps/api` before changing
  UI/runtime/backend behavior.
- If a file appears legacy or unused, report it instead of modifying it.
