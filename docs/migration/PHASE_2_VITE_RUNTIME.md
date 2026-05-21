# Phase 2 — Opt-in `--vite` Runtime in Packaged Exe

Commit `8291613` `feat(desktop): Phase 2 — opt-in --vite runtime alongside Next default`.

Status: **implemented on `main`, not yet tagged / released.** Released `v0.3.4` does not have this flag.

---

## Goal

Wire the Phase 1 Vite SPA into the packaged desktop runtime as an experimental, opt-in launch mode without breaking the default Next-based path.

After this phase, the packaged exe contains both UIs:
- Default (no flag) → Next standalone + bundled Node (unchanged).
- `--vite` → Vite static SPA via Python's `http.server`, zero Node processes.

---

## Files modified

| File | Change |
|---|---|
| `desktop/app.py` | New `_vite_dist_path`, `_start_vite_static_server`, `--vite` branch in `main()`, try/finally cleanup |
| `desktop/app.spec` | Conditional bundle of `apps/desktop-web/dist/` → `_internal/desktop-web/` |
| `desktop/build_desktop.ps1` | New step 1.5 `vite build`, `-SkipViteBuild` flag |
| `apps/desktop-web/README.md` | Phase 2 docs |
| `docs/migration/README.md` | Phase table |
| `docs/migration/NEXT_AGENT_HANDOFF.md` | Updated status |

No changes to `desktop/bridge.py`, `src/**`, `apps/web/`, `apps/api/`, `desktop/node_portable/`, `desktop/update_helper.ps1`, `desktop/updater.py`, or any Phase 0 user-data contract.

---

## Static asset path resolution

```python
def _vite_dist_path() -> Path:
    if _bundled():
        return _bundle_dir() / "desktop-web"          # _MEIPASS/desktop-web/
    return _repo_root() / "apps" / "desktop-web" / "dist"
```

Bundled exe: `_internal/desktop-web/{index.html, assets/...}`.
Dev: `apps/desktop-web/dist/` (build with `npm --prefix apps/desktop-web run build`).

---

## Local static HTTP server

`desktop/app.py::_start_vite_static_server(dist)`:

```python
class _QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(dist), **kwargs)
    def log_message(self, *_args): return
server = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
```

Why HTTP over `file://`:
- WebView2 blocks several Web Platform features (fetch, importmaps, cross-origin isolation) when content is loaded from `file://`.
- The local HTTP server gives the SPA real origin semantics.
- Bound to a random free loopback port so multiple instances do not collide.
- Daemon-thread `serve_forever`; shut down via try/finally on webview exit.

Why subclass instead of `partial`:
- The stdlib docs example uses `functools.partial(SimpleHTTPRequestHandler, directory=...)`. That object is not a class and cannot be subclassed (`TypeError: the first argument must be callable`).
- Subclassing and setting `directory` in `__init__` is the supported pattern in Python 3.7+.

---

## `--vite` branch in `main()`

```python
vite_mode = "--vite" in args

if vite_mode:
    dist = _vite_dist_path()
    index_html = dist / "index.html"
    if not index_html.exists():
        sys.exit("[desktop] Vite build nao encontrado em ...")
    static_server, port = _start_vite_static_server(dist)
    url = f"http://127.0.0.1:{port}/"
elif dev_mode:
    # ... existing Next dev branch
else:
    # ... existing Next standalone branch (default, unchanged)
```

All Phase 0 safety preflights still run (`_configure_bundled_data_paths`, `_strip_motw_from_bundle`, `_migrate_legacy_db_once`, `_ensure_db_initialized`, `_preflight_pywebview_backend`).

Window title gets a `(Vite)` suffix in Vite mode to make it visually distinguishable during testing.

---

## PyInstaller spec change

```python
VITE_DIST_DIR = ROOT / "apps" / "desktop-web" / "dist"
if VITE_DIST_DIR.exists():
    datas.append((str(VITE_DIST_DIR), "desktop-web"))
```

Conditional: if `apps/desktop-web/dist/` is absent (e.g. `-SkipViteBuild` and never built), the entry is silently omitted. `desktop/app.py` then refuses `--vite` with an actionable error. Existing Next path still works.

---

## Build script change

`desktop/build_desktop.ps1` step 1.5:

```powershell
if (-not $SkipViteBuild) {
    if (Test-Path (Join-Path $ViteDir "package.json")) {
        Push-Location $ViteDir
        try {
            if (-not (Test-Path "node_modules")) {
                & npm install
            }
            & npm run build
        } finally { Pop-Location }
    }
}
```

`-SkipViteBuild` skips the Vite build (useful when iterating on `desktop/app.py` only).

---

## Validation

### Local dev
| Test | Result |
|---|---|
| `_start_vite_static_server` direct HTTP probe | `index_html` 200, `nonexistent.js` 404 |
| `python -m desktop.app --vite` (dev mode) | alive 15 s, **0 node.exe**, 6 WebView2 children over baseline |

### Default mode regression (packaged)
| Check | Result |
|---|---|
| Alive 20 s | yes |
| `node.exe` count | 1 (Next standalone) |
| `msedgewebview2.exe` over baseline | +14 |
| LOCALAPPDATA DB | created |

### `--vite` mode (packaged)
| Check | Result |
|---|---|
| Alive 20 s | yes |
| `node.exe` count | **0** |
| `msedgewebview2.exe` over baseline | +12 |
| LOCALAPPDATA DB | created |
| Local HTTP listening port | yes (ephemeral 127.0.0.1) |

### Bundle layout
```
_internal/
  desktop-web/          1.8 MB  (Vite SPA, NEW)
  web_standalone/       26 MB   (Next, unchanged)
  node.exe              88 MB   (unchanged)
  pythonnet/runtime/    (unchanged)
  update_helper.ps1     (unchanged)
```

Total package: 200 → 202 MB (Vite added 1.8 MB).

---

## Known unknowns

- Packaged `--vite` interactive click-through (companies → search → company detail → back) not yet manually verified. Liveness + process count verified.
- `HashRouter` is the safe choice across `file://`, `http://127.0.0.1:<port>`, and pywebview's `http_server`. If Phase 3 standardises on the local HTTP server, switching to `BrowserRouter` becomes possible (nicer URLs, but requires a tiny SPA-fallback in the static server to redirect unknown paths to `index.html`).
- Vite SPA does not yet cover sectors, update-base admin, Excel export, or auto-updater UI — covered by the Phase 1.7 / 2.5 backlog in `NEXT_AGENT_HANDOFF.md`.

---

## What was intentionally NOT done

- Not switched default to Vite. `--vite` is opt-in.
- Not removed Node from the bundle.
- Not removed `_internal/web_standalone/`.
- Not deleted `apps/web/` or `apps/api/`.
- Not tagged a release. The next tag (e.g. `v0.3.5`) will automatically include both UIs because both `app.spec` data entries are conditional on disk presence.

---

## Process count comparison

| Mode | `CVMAnalytics.exe` | `node.exe` | `msedgewebview2.exe` (delta) |
|---|---|---|---|
| Default | 1 | 1 | +14 |
| `--vite` | 1 | **0** | +12 |

Eliminating `node.exe` in `--vite` mode is the headline Phase 2 deliverable.

---

## Package size impact

| Stage | Total | Notes |
|---|---|---|
| Pre-Phase-2 (v0.3.4) | ~200 MB | Next + Node only |
| Post-Phase-2 (main) | ~202 MB | + Vite dist 1.8 MB |
| Post-Phase-3 (planned) | ~88 MB | drops `node.exe` (88 MB) + `web_standalone/` (26 MB) |

Phase 3 reclaims ~114 MB once Vite reaches parity.

---

## How to ship Phase 2

If/when the user approves shipping Phase 2:

1. Build locally: `.\desktop\build_desktop.ps1` (rebuilds Next + Vite + PyInstaller).
2. Smoke: `python scripts/test_ci_v034_full.ps1` against the local build to confirm Phase 0 regressions pass.
3. Smoke: launch packaged exe with and without `--vite`; verify process count and LOCALAPPDATA DB.
4. Tag `v0.3.5` with release notes saying `--vite` is opt-in / experimental, default is unchanged Next runtime.
5. Push tag — CI publishes the bundle automatically.
6. Real-asset MOTW + updater contract test against the published v0.3.5 (as for v0.3.4).
