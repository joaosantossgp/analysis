# Repository Profile

Recommended values for the GitHub "About" panel of `joaosantossgp/analisys`. Applied via `gh` when possible; this file is the canonical reference if manual update is required.

## Description

Local-first desktop financial data tool for Brazilian companies, built with Python, SQLite, pywebview, and a packaged web UI.

## Website / Homepage

`https://analisys-nine.vercel.app` — keep. It is the existing marketing landing page (sourced from `apps/landing/`). It is not the product runtime; the product is the packaged Windows desktop executable distributed via GitHub Releases.

If at any point the landing page is taken down, blank the homepage field instead of pointing it at a non-existent URL.

## Topics

```
python
sqlite
financial-data
brazilian-market
cvm
desktop-app
pywebview
equity-research
data-pipeline
windows
```

## Releases

Public download:
`https://github.com/joaosantossgp/analisys/releases/latest/download/CVMAnalytics-windows-v<version>.zip`

The release artifact contains `CVMAnalytics.exe` and `_internal/` at the top level. This layout is the contract enforced by `desktop/update_helper.ps1`. Do not change it without updating the helper allowlist.

## Update commands

```bash
gh repo edit joaosantossgp/analisys \
  --description "Local-first desktop financial data tool for Brazilian companies, built with Python, SQLite, pywebview, and a packaged web UI." \
  --homepage "https://analisys-nine.vercel.app" \
  --add-topic python \
  --add-topic sqlite \
  --add-topic financial-data \
  --add-topic brazilian-market \
  --add-topic cvm \
  --add-topic desktop-app \
  --add-topic pywebview \
  --add-topic equity-research \
  --add-topic data-pipeline \
  --add-topic windows
```
