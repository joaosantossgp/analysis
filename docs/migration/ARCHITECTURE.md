# Current Architecture Map

Snapshot updated after Phase 5B / `v0.15.0`: the packaged desktop runtime is
Vite-only. Older Next/Node sections below are historical context for Phase 2-4
and no longer describe the current package.

## Current packaged process tree

```
CVMAnalytics.exe (PyInstaller bootstrap)
└─ python (frozen) running desktop/app.py main()
   ├─ pywebview window  (WebView2 / Edge Chromium)
   │   └─ HTML/JS from http://127.0.0.1:<random>
   ├─ thread: http.server.ThreadingHTTPServer
   │   └─ serves _internal/desktop-web/ (Vite SPA dist)
   ├─ thread: desktop-update-check
   └─ thread: desktop-refresh-worker
```

No `node.exe`. No `web_standalone/`. `--legacy` warns and continues into Vite.

---

## Historical Phase 2 Snapshot

## Process tree

### Default mode (Next standalone) — what users get on v0.3.4
```
CVMAnalytics.exe (PyInstaller bootstrap)
└─ python (frozen) running desktop/app.py main()
   ├─ pywebview window  (WebView2 / Edge Chromium)
   │   └─ HTML/JS from http://127.0.0.1:<random>
   ├─ subprocess: _internal/node.exe _internal/web_standalone/server.js
   │   └─ Next.js standalone server (HOSTNAME=127.0.0.1, PORT=<random>)
   ├─ thread: desktop-update-check  (GitHub releases poll)
   └─ thread: desktop-refresh-worker  (drains refresh_jobs table)
```

### `--vite` mode (Phase 2 opt-in)
```
CVMAnalytics.exe (PyInstaller bootstrap)
└─ python (frozen) running desktop/app.py main()
   ├─ pywebview window  (WebView2 / Edge Chromium)
   │   └─ HTML/JS from http://127.0.0.1:<random>
   ├─ thread: http.server.ThreadingHTTPServer
   │   └─ serves _internal/desktop-web/ (Vite SPA dist)
   ├─ thread: desktop-update-check
   └─ thread: desktop-refresh-worker
```

No `node.exe`. No Next standalone server. Same CVMBridge / WebView2 stack.

### `--dev` mode (source Vite dev server)
```
python -m desktop.app --dev
├─ pywebview window
└─ subprocess: npm.cmd run dev  (apps/desktop-web)
    └─ Vite dev server on 127.0.0.1:5173
```

### `--diagnose-runtime` mode
No window. Writes diagnostic log to `%USERPROFILE%\Documents\CVMAnalytics\diagnostics-<utc>.log`, opens in Notepad, exits.

---

## Current file layout in the packaged exe

```
dist/CVMAnalytics/
├── CVMAnalytics.exe
└── _internal/
    ├── desktop-web/
    │   ├── index.html
    │   └── assets/
    ├── data/import/gics_mapping.csv
    ├── pythonnet/runtime/
    ├── update_helper.ps1
    └── (Python stdlib + site-packages)
```

The package must not contain `_internal/node.exe` or `_internal/web_standalone/`.

---

## Historical Phase 2 file layout in the packaged exe

```
dist/CVMAnalytics/
├── CVMAnalytics.exe                       (PyInstaller bootloader, 20 MB)
└── _internal/                              (PyInstaller _MEIPASS contents)
    ├── desktop-web/                        ← Phase 2: Vite SPA static dist (1.8 MB)
    │   ├── index.html
    │   └── assets/
    │       ├── index-<hash>.js
    │       └── index-<hash>.css
    ├── web_standalone/                     ← Next.js standalone server (26 MB)
    │   ├── server.js
    │   ├── node_modules/
    │   ├── public/
    │   └── .next/
    ├── node.exe                            ← Bundled Node runtime (88 MB)
    ├── pythonnet/runtime/                  ← .NET Framework loader assets
    │   ├── Python.Runtime.dll              (450 KB)
    │   ├── Python.Runtime.deps.json        (9.8 KB) ← MUST be present
    │   ├── Python.Runtime.xml
    │   └── Python.Runtime.pdb
    ├── clr_loader/ffi/dlls/amd64/          ← Native bridge for pythonnet
    ├── update_helper.ps1                   ← Updater swap script
    ├── (Python stdlib + site-packages)
    ├── (sqlalchemy, sqlite3.pyd, pandas, ...)
    └── (numpy, msvcp140.dll, ...)
```

Total ~202 MB packaged, ~78-87 MB compressed.

---

## File layout in `%USERPROFILE%\Documents\CVMAnalytics\`

```
%USERPROFILE%\Documents\CVMAnalytics\
├── db/
│   ├── cvm_financials.db                  ← authoritative runtime DB
│   ├── cvm_financials.db-shm              (SQLite WAL shared memory)
│   └── cvm_financials.db-wal              (SQLite write-ahead log)
├── output/                                 ← Excel exports
├── logs/                                   ← refresh / app logs
├── cache/                                  ← refresh planner cache, etc.
├── backup/                                 ← created when legacy DB migrated
│   └── legacy-db-<utc-ts>/
│       ├── cvm_financials.db              (raw copy)
│       ├── cvm_financials.db-wal          (raw copy)
│       └── cvm_financials.db-shm          (raw copy)
├── recovery.log                            ← migrator + init events
└── diagnostics-<utc-ts>.log                ← from --diagnose-runtime or preflight failures
```

Updater staging remains under `%LOCALAPPDATA%\CVMAnalytics\` and does not
contain user financial data:

```
%LOCALAPPDATA%\CVMAnalytics\
├── update_rollback/                        ← created on every update
│   └── <utc-ts>/
│       ├── CVMAnalytics.exe               (pre-swap copy)
│       └── _internal/                      (pre-swap copy)
├── versions/                               ← staged updates before swap
│   └── <version>/                          (extracted new bundle)
├── snooze.json                             ← updater snooze state
└── update_error.log                        ← helper script errors
```

---

## Module/dependency map

| Concern | Files / paths |
|---|---|
| **Python core (untouchable bridge surface)** | `src/read_service.py`, `src/refresh_service.py`, `src/refresh_job_worker.py`, `src/refresh_jobs.py`, `src/db.py`, `src/database.py`, `src/settings.py`, `src/contracts.py`, `src/scraper.py`, `src/standardizer.py`, `src/kpi_engine.py`, `src/excel_exporter.py` |
| **Desktop shell** | `desktop/app.py`, `desktop/bridge.py`, `desktop/updater.py`, `desktop/update_helper.ps1`, `desktop/__version__.py`, `desktop/services.py` |
| **Packaging** | `desktop/app.spec`, `desktop/build_desktop.ps1`, `.github/workflows/release-desktop.yml` |
| **Source-only / hosted Next UI** | `apps/web/app/**`, `apps/web/components/**`, `apps/web/lib/**`, `apps/web/next.config.ts`, `apps/web/package.json` |
| **Hosted/development FastAPI** | `apps/api/app/**`, `apps/api/worker.py`, `apps/api/Dockerfile`, `railway.toml` |
| **Packaged Vite SPA** | `apps/desktop-web/**` |
| **Smoke / harness scripts** | `scripts/phase1_pywebview_smoke.py`, `scripts/test_motw_strip.py`, `scripts/test_motw_explorer.ps1`, `scripts/test_motw_launch.ps1`, `scripts/test_ci_v034_full.ps1`, `scripts/test_ci_v033_motw.ps1` |
| **Migration docs** | `docs/migration/*.md` |

---

## Bridge surface (Python → JavaScript contract)

`desktop/bridge.py::CVMBridge` exposes the following methods as `window.pywebview.api.<method>`:

| Method | Returns | Used by Vite SPA? |
|---|---|---|
| `ping` | `{pong, ts}` | Yes (BridgeStatus) |
| `get_companies` | `CompanyDirectoryPage` | Yes |
| `get_company_filters` | `{sectors: [...]}` | No (yet) |
| `get_company_suggestions` | `{items: [...]}` | No |
| `get_populares` | `CompanyDirectoryPage` | No |
| `get_em_destaque` | `CompanyDirectoryPage` | No |
| `track_company_view` | `{ok}` | No |
| `get_company_info` | `CompanyInfo` | Yes |
| `get_company_years` | `{years}` | Yes |
| `get_company_kpis` | `KPIBundle` | Yes |
| `get_company_statement` | `StatementMatrix` | No (yet) |
| `download_company_excel` | base64 payload | No (yet) |
| `save_company_excel` | file path | No (yet) |
| `get_sectors` | `SectorDirectory` | No (yet) |
| `get_sector_detail` | `SectorDetail` | No (yet) |
| `get_sub_sector_detail` | `SectorDetail` | No (yet) |
| `get_refresh_status` | refresh status payload | No (yet) |
| `request_refresh` | dispatch response | No (yet) |
| `cancel_refresh` | `{ok}` | No (yet) |
| `get_base_health` | `BaseHealthSnapshot` | No (yet) |
| `get_health` | `HealthPayload` | Yes |
| `check_update` | update info | No (yet) |
| `apply_update` | `{started}` | No (yet) |
| `get_update_progress` | progress payload | No (yet) |
| `snooze_update` | `{ok}` | No (yet) |

The packaged desktop UI now lives in `apps/desktop-web`. Source-only hosted
surfaces in `apps/web` / `apps/api` are documented separately and are not part
of the desktop package.

---

## Vite SPA layout (`apps/desktop-web/`)

```
apps/desktop-web/
├── index.html                              (Vite entry HTML)
├── package.json                            (Vite 6, React 19, TS 5, TanStack Query 5, react-router-dom 7)
├── vite.config.ts                          (base "./", alias @ → src)
├── tsconfig.json                           (strict mode, bundler resolution)
├── public/                                 (static assets served as-is)
└── src/
    ├── main.tsx                            (root render + QueryClientProvider)
    ├── App.tsx                             (HashRouter + NavLink + Routes)
    ├── index.css                           (Tailwind v4 import)
    ├── components/
    │   ├── BridgeStatus.tsx                (footer indicator chip)
    │   ├── CompaniesTable.tsx              (directory list + search + pagination)
    │   └── HealthCard.tsx                  (runtime health)
    ├── lib/
    │   ├── query.ts                        (shared QueryClient)
    │   ├── bridge/
    │   │   ├── adapter.ts                  ← SINGLE chokepoint for window.pywebview.api
    │   │   └── types.ts                    ← typed mirror of CVMBridge
    │   └── api/
    │       ├── companies.ts                (fetchCompanies)
    │       ├── companyDetail.ts            (fetchCompanyInfo, fetchCompanyYears, fetchCompanyKpis)
    │       └── health.ts                   (fetchHealth)
    └── routes/
        ├── CompaniesPage.tsx               (/)
        ├── CompanyDetailPage.tsx           (/empresas/:cdCvm)
        └── HealthPage.tsx                  (/health)
```

### Architecture rules
1. **Components never call `window.pywebview.api` directly.** Always go through `lib/bridge/adapter.ts::callBridge`.
2. **Adding a new bridge method** = 2 steps:
   - Add signature to `BridgeApi` interface in `lib/bridge/types.ts`.
   - Add facade in `lib/api/<area>.ts` that wraps `callBridge` with the typed query/result shape.
3. **TanStack Query**: use `useQuery` with `enabled: bridgeReady` (from `whenBridgeReady()`). Keep `staleTime: 60_000`, `gcTime: 300_000`, `refetchOnWindowFocus: false` (set globally in `lib/query.ts`).
4. **Routing**: HashRouter. Use `<Link to={...}>` from `react-router-dom`. Use `useParams()` to read dynamic segments.
5. **Browser-mode fallback**: every facade must distinguish `mode: "desktop"` vs `mode: "browser"` so the SPA renders a clear banner in dev without pywebview.

---

## CI / release flow

```
git push tag vX.Y.Z
  ↓
.github/workflows/release-desktop.yml on windows-latest
  ├─ checkout
  ├─ setup-python 3.11 + setup-node 22
  ├─ pip install -r requirements.txt
  ├─ npm ci --prefix apps/desktop-web
  ├─ desktop/build_desktop.ps1 -Version X.Y.Z
  │     ├─ vite build (apps/desktop-web)
  │     ├─ inject version into desktop/__version__.py
  │     └─ pyinstaller desktop/app.spec
  ├─ Compress-Archive -Path dist\CVMAnalytics\*  ← FLAT root, post-verify
  ├─ verify zip root contains CVMAnalytics.exe + _internal (workflow fails if not)
  ├─ SHA-256 sidecar
  └─ softprops/action-gh-release@v2 publish
        ↓
GitHub Release vX.Y.Z with:
  - CVMAnalytics-windows-vX.Y.Z.zip
  - CVMAnalytics-windows-vX.Y.Z.zip.sha256
  - CVMAnalytics-windows.zip (latest alias)
  - CVMAnalytics-windows.zip.sha256
        ↓
Auto-updater in running vX.Y.Z-1 clients
  ├─ desktop/updater.py polls api.github.com/.../releases/latest
  ├─ Downloads zip, validates SHA-256, extracts to LOCALAPPDATA/versions/X.Y.Z/
  └─ Spawns update_helper.ps1 staged current → swap allowlist entries → relaunch
```

---

## Known broken / fragile items

| Item | Status | Owner |
|---|---|---|
| `desktop/__version__.py` is build-time overwritten | Working as-is; documented hygiene issue | Future cleanup |
| HashRouter chosen over BrowserRouter | Working; can switch if Phase 3 enforces http_server | Future cleanup |
| Vite SPA does not cover all Next screens | Expected mid-migration state | Phase 1.7 / 2.5 |
| `whenBridgeReady` relies on `pywebviewready` event | Works in pywebview ≥ 4.4 | Verified empirically |
| `slow_query` warning for `get_companies_directory_page` (~400 ms) | Pre-existing in Python service | Out of migration scope |
| No code signing | SmartScreen warns on download | Phase 4 |
| UPX disabled | Larger bundle but no .NET load issues | Locked-in tradeoff |
