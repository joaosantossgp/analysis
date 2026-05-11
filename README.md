# CVM Reports Capture

Captures historical financial statements from Brazilian publicly traded companies (CVM regulator), persists them locally in SQLite, and serves them through a Windows desktop app built on Next.js + pywebview, with an optional read-only FastAPI for local/dev HTTP.

## Canonical product

The shipped runtime is the Windows desktop app at **`dist/CVMAnalytics/CVMAnalytics.exe`**, built by **`desktop/build_desktop.ps1`**. The Next.js UI from `apps/web/` is bundled into the executable; the database is local SQLite at `data/db/cvm_financials.db`.

**Public download** (recommended for end users):

```
https://github.com/joaosantossgp/analisys/releases/latest/download/CVMAnalytics-windows.zip
```

Vercel/Railway deployment is no longer the assumed runtime. Troubleshoot product issues against the desktop app (`ANALISYS_DESKTOP_MODE=1`) or a local API + DB, not remote URLs.

## Repository layout

```
desktop/         pywebview wrapper + PyInstaller build script
apps/web/        Next.js 16 standalone UI (bundled into the .exe)
apps/api/        Optional FastAPI read-only service for dev/local HTTP
src/             Python core: scraper, KPI engine, refresh/read services
main.py          CLI entry point for headless refresh
scripts/         Setup, batches, diagnostics, validation helpers
landing/         Static landing page (deployed by GitHub Pages workflow)
data/            Local SQLite DB + raw inputs + caches (gitignored)
docs/            Active documentation; see docs/reference/ and docs/decisions/
tests/           Pytest suite
```

## Local development

```bash
# Python dependencies
pip install -r requirements.txt
pip install -r apps/api/requirements-dev.txt

# Web dependencies (only if running the dev UI)
cd apps/web && npm install && cd ../..

# Initialize the DB on a fresh machine
python scripts/setup_db.py
python scripts/setup_companies_table.py

# Validate environment
python scripts/runtime_doctor.py --require-canonical

# Run the desktop app in dev mode (uses local Next.js dev server)
python -m desktop.app --dev

# Build the Windows executable
.\desktop\build_desktop.ps1
.\dist\CVMAnalytics\CVMAnalytics.exe
```

**Headless / API alternatives:**

```bash
# CLI refresh for a single company
python main.py --companies PETROBRAS --start_year 2021 --end_year 2025

# Local FastAPI (optional)
uvicorn apps.api.app.main:app --reload
# → Swagger at http://127.0.0.1:8000/docs

# Web dev server only
cd apps/web && npm run dev
```

**Desktop build note:** `desktop/build_desktop.ps1` copies `node.exe` from your locally installed Node into `desktop/node_portable/` at build time. Node must be installed on the machine running the build; the portable copy is created automatically and is gitignored.

## Validation

```bash
# Python tests
pytest tests/ -q
pytest apps/api/tests -q

# Web typecheck + lint + build + tests
cd apps/web && npm run lint
cd apps/web && npm run typecheck
cd apps/web && npm run build
cd apps/web && npm run test:unit
cd apps/web && npm run test:e2e

# Database portability smoke
python scripts/db_portability_smoke.py --write-check
```

## Documentation

- **`AGENTS.md`** — operating rules for AI agents
- **`COMO_RODAR.md`** — operational how-to (Portuguese)
- **`docs/CONTEXT.md`** — domain rules and non-obvious decisions
- **`docs/decisions/`** — ADRs (historical architectural decisions; may cite archived planning docs)
- **`docs/reference/`** — active reference docs (sitemap, interface map, API contract, perf baseline, GICS import, product page prompts)
- **`docs/governance/`** — autonomous-mode contract + release evidence
- **`docs/releases/`** — release notes

## Key principles

- `apps/api` consumes `src/read_service.py` — no duplicated SQL/KPI logic
- The web UI consumes `apps/api`; do not reimplement queries in `apps/web`
- `apps/web/next.config.ts` keeps `output: "standalone"` because the desktop build depends on it
- Refresh logs land in `output/logs/`, including `refresh_runs.jsonl`
- Database conventions and non-obvious quirks live in [docs/CONTEXT.md](docs/CONTEXT.md)
