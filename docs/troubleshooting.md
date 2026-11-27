# Troubleshooting

## Where To Look First

Use Settings -> Diagnostics in the desktop app for runtime mode, bridge state,
data paths, database counts, updater state, logs, and local dependency probes.

Key local paths:

```text
%USERPROFILE%\Documents\CVMAnalytics\db
%USERPROFILE%\Documents\CVMAnalytics\output
%USERPROFILE%\Documents\CVMAnalytics\logs
%USERPROFILE%\Documents\CVMAnalytics\cache
%LOCALAPPDATA%\CVMAnalytics\versions
%LOCALAPPDATA%\CVMAnalytics\update_rollback
%LOCALAPPDATA%\CVMAnalytics\update_error.log
%LOCALAPPDATA%\CVMAnalytics\update_channel.json
```

## Common Problems

| Symptom | Check |
|---|---|
| App opens but has no financial data | Choose **Download CVM data** on Home (or in the top-bar Data panel); the pill shows progress |
| Browser preview shows no data | `npm run dev` has no pywebview bridge; use `python -m desktop.app --dev` or `npm run dev:mock` |
| `ModuleNotFoundError: webview` or another declared package | Run `python -m desktop.app --repair-dev-environment --dev`; do not install the missing package globally. |
| Bootstrap fails before the app opens | Read the printed command, exit code, and output; confirm Python 3.11+, Node.js 22+, permissions, and network access, then run the repair command. |
| Writes are blocked in dev | Dev mode is using release Documents data; set isolated `CVM_DATA_DIR` or explicitly allow writes |
| Another instance warning | A live process owns `{data_dir}/runtime.lock`; close the other process before writes |
| Data update ends "Completed with N failures" | Open the Data panel: failed companies are listed with their error and a Retry |
| Company has no history | It may exist in the catalog but have no local CVM statement rows; use **Update company** on its page |
| Market widgets empty | Ticker mapping or unofficial market-data provider may be unavailable |
| News content unavailable | Only metadata/feed summary may be stored; the app does not bypass paywalls |
| Excel export fails | Check output directory permissions, open-file locks, and exporter tests |
| Packaged app launches old version | Check Settings -> Diagnostics build provenance and release ZIP layout |
| Updater fails | The top-bar Update pill reads "Update failed" and its panel shows the error; the installed version keeps running. Inspect `%LOCALAPPDATA%\CVMAnalytics\update_error.log` and rollback directory |
| No Update pill although a newer publication exists | The pill shows only an offer from the last check: check Settings -> App (failed, offline or postponed checks show nothing in the top bar; "Later" postpones that version for 7 days), then Check now |
| A pre-release is not offered | Settings -> App -> Update channel must be "Pre-releases and releases"; then Check now |

## Safe Diagnostics

```powershell
python scripts/diagnostics/runtime_doctor.py --require-canonical
python -m py_compile desktop/app.py desktop/bridge.py
npm --prefix apps/desktop-web run typecheck
pytest tests -q
```

For data-specific issues, inspect the relevant bridge method and read-service
path before changing code. Avoid deleting user databases as a first response.

## Packaged vs Dev Differences

- Packaged app runs from `dist/CVMAnalytics/CVMAnalytics.exe` and serves bundled
  Vite assets from `_internal/desktop-web`.
- `python -m desktop.app --dev` uses the Vite dev server but the real bridge.
- Source-mode startup provisions `.venv` from `requirements.txt`; frozen builds
  bypass this bootstrap because PyInstaller bundles their Python runtime and
  dependencies.
- Browser-only Vite preview does not have a real bridge.
- Packaged app writes to Documents by default; dev mode also points there unless
  `CVM_DATA_DIR` is set.
- Dev shared-data mode blocks destructive writes by default. Packaged mode does
  not.

## Escalation Checklist

Before documenting a bug as fixed, record:

- exact mode: packaged, source, dev, browser, mock;
- active data root and database path;
- app version/build provenance;
- bridge method or route involved;
- source class involved: CVM, external market data, news, energy, user import,
  calculated;
- minimal reproduction;
- command/test or manual check used to validate the fix.
