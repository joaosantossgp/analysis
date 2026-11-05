# CVMAnalytics

## Overview

CVMAnalytics is a local-first Windows desktop app for financial analysis of
Brazilian public companies. It collects CVM financial statements, stores them
in local SQLite databases, exposes them through a pywebview desktop UI, and
exports analyst-oriented Excel workbooks.

The product is a serious financial analysis tool, not a generic dashboard. It
prioritizes offline access to already-downloaded data, auditable source
tracking, reproducible refreshes, predictable packaging, and Excel files that
open cleanly.

## Download

[Download the latest Windows build](https://github.com/joaosantossgp/analisys/releases/latest/download/CVMAnalytics-windows.zip)

- Checksum: [CVMAnalytics-windows.zip.sha256](https://github.com/joaosantossgp/analisys/releases/latest/download/CVMAnalytics-windows.zip.sha256)
- Distribution channel: [GitHub Releases](https://github.com/joaosantossgp/analisys/releases)
- Public site: `apps/landing/` on GitHub Pages. It is a download/marketing
  surface only, not the product runtime.

## Active App

The active product runtime is the packaged Windows desktop app:

```text
dist/CVMAnalytics/CVMAnalytics.exe
```

Verified active paths:

| Area | Active path |
|---|---|
| Desktop shell | `desktop/app.py` |
| Build script | `desktop/build_desktop.ps1` |
| PyInstaller spec | `desktop/app.spec` |
| Frontend | `apps/desktop-web` |
| Frontend build output | `apps/desktop-web/dist` bundled as `_internal/desktop-web` |
| Python bridge | `desktop/bridge.py` and `desktop/bridge_api/` |
| Python data/core | `src/` |
| HTTP API adapter | `apps/api` for tests/dev-hosted HTTP access; not the desktop UI |

`apps/desktop-web` is the only UI bundled into the desktop executable. The old
Next.js `apps/web` app was removed from the active tree. Do not recreate or
modify Next.js routes for product work.

## Quick Start

For end users:

1. Download `CVMAnalytics-windows.zip`.
2. Extract it to a folder you control, for example
   `Documents\Apps\CVMAnalytics`.
3. Keep `CVMAnalytics.exe` and `_internal\` together.
4. Run `CVMAnalytics.exe`.
5. Use Settings -> Updates to download CVM data for the companies you follow.

Runtime data is stored outside the install folder:

```text
%USERPROFILE%\Documents\CVMAnalytics\
```

This folder holds local databases, caches, logs, source files, and Excel
outputs. Already-downloaded data remains usable offline. Refreshes and updater
checks need network access.

## Developer Commands

For desktop development, install Python 3.11+ and Node.js 22+ once, then run
the normal command. It creates the repository-local `.venv`, installs the
declared Python dependencies, and synchronizes the Vite dependencies when
needed; no manual `pip install` or virtual-environment activation is required.

Run the desktop app with the real Python bridge and Vite dev server:

```powershell
python -m desktop.app --dev
```

To re-synchronize declared dependencies, run:

```powershell
python -m desktop.app --repair-dev-environment --dev
```

To recreate the isolated environment completely, run:

```powershell
python -m desktop.app --rebuild-dev-environment --dev
```

Run frontend checks:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

Run Python checks:

```powershell
python -m py_compile desktop/app.py desktop/bridge.py
pytest tests -q
```

Build the packaged desktop app:

```powershell
.\desktop\build_desktop.ps1
```

See [docs/development.md](docs/development.md) and
[docs/build-release.md](docs/build-release.md) for the full validated command
map.

## Financial Data Caveats

CVM DFP/ITR filings from `dados.cvm.gov.br` are the primary official source for
financial statements. B3/CVM identifiers, GICS mappings, Yahoo Finance market
data, Google News RSS, ONS/CCEE/ANEEL/OWID energy datasets, and user imports
are separate sources with different reliability levels.

Do not treat Yahoo Finance, yfinance, Google News, or other external/aggregator
sources as equivalent to CVM or B3 official data. Documentation and UI should
distinguish official, external, reported, calculated, estimated, and imported
data. Calculated values must remain traceable to source, company, period,
account, transformation/formula, and timestamp.

See [docs/data-sources.md](docs/data-sources.md).

## Canonical Documentation

| Topic | Canonical doc |
|---|---|
| Current project status | [docs/STATUS.md](docs/STATUS.md) |
| Product direction | [docs/PRODUCT_DIRECTION.md](docs/PRODUCT_DIRECTION.md) |
| Product development checklist | [docs/PRODUCT_DEVELOPMENT_CHECKLIST.md](docs/PRODUCT_DEVELOPMENT_CHECKLIST.md) |
| Product principles | [docs/PRODUCT.md](docs/PRODUCT.md) |
| Design system and UI principles | [docs/DESIGN.md](docs/DESIGN.md) |
| Runtime architecture | [docs/architecture.md](docs/architecture.md) |
| Data sources and auditability | [docs/data-sources.md](docs/data-sources.md) |
| Excel export standards | [docs/excel-exports.md](docs/excel-exports.md) |
| Development setup and commands | [docs/development.md](docs/development.md) |
| Build, release, updater | [docs/build-release.md](docs/build-release.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Product workflows | [docs/product-workflows.md](docs/product-workflows.md) |
| Repository map | [docs/reference/repository-map.md](docs/reference/repository-map.md) |
| Agent rules | [AGENTS.md](AGENTS.md) |
| Vendored agent skills and automatic maintenance | [docs/agents/skills.md](docs/agents/skills.md) |
| Multi-window research (proposal) | [Workbench](docs/research/2026-11-04-multi-window-workbench.md), [local storage](docs/research/local-multi-window-storage.md) |

Historical migration docs live under `docs/archive/migration/`. ADRs under
`docs/decisions/` preserve point-in-time decisions. Release notes under
`docs/releases/` are a partial local index; GitHub Releases are the published
release source.

## Known Limits

- Browser-only Vite preview has no `window.pywebview.api` bridge unless mock
  mode is used.
- Dev mode uses the same Documents data root by default and blocks destructive
  writes unless explicitly allowed.
- The packaged app is Vite-only. `--legacy` is unsupported and continues into
  Vite after logging a warning.
- Packaged-app smoke, clean install, update-over-previous-version, and manual
  Excel-open validation remain required before publishing a release.
