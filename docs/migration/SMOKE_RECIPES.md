# Smoke Recipes

> [!NOTE]
> **Historical migration document.** Recipes were collected during the desktop migration, complete as of `v0.17.0`. Some commands (MOTW reproduction, updater contract) still apply to current releases; others were one-time validations for specific phases. Use `scripts/test_motw_launch.ps1` and `scripts/test_motw_explorer.ps1` for current release validation. For current product state, see `README.md` and `docs/reference/repository-map.md`.

All the validation commands used during this migration, in one place. Copy/paste-ready.

---

## Phase 0 — User data + updater contract

### Full Phase 0 contract against a published release asset
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File docs/migration/legacy-release-validation/test_ci_v034_full.ps1
```
Downloads the latest `v0.3.4` zip from GitHub via `gh`, applies MOTW to 155 binaries, launches the bundled exe, simulates an updater swap with planted user data, and reports:
- Fresh install: alive, WebView2 children, Documents data root preserved/created.
- Updater contract: exe + `_internal/` swapped, user data preserved byte-for-byte, rollback snapshot.

### Mark-of-the-Web reproduction (no updater path)
```powershell
# Against a local zip
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_motw_launch.ps1 "C:\path\to\CVMAnalytics-windows-vX.Y.Z.zip"
```
Sets `Zone.Identifier:ZoneId=3` on the zip, extracts via `Expand-Archive`, launches, reports liveness.

```powershell
# Heavier variant: stamps MOTW on every extracted binary (Explorer "Extract All" reproduction)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_motw_explorer.ps1 "C:\path\to\zip"
```

### MOTW strip unit test
```bash
python scripts/test_motw_strip.py
```
Verifies `_strip_motw_from_bundle` removes Zone.Identifier ADS from DLLs only (txt files untouched) and is idempotent.

### WAL-safe migrator sandbox test
```bash
python -c "
import os, sys, tempfile, sqlite3
from pathlib import Path
sandbox = Path(tempfile.mkdtemp(prefix='cvm_wal_'))
fake_appdata = sandbox / 'LocalAppData'
fake_exe = sandbox / 'install'
db = fake_exe / 'data/db/cvm_financials.db'
db.parent.mkdir(parents=True)
c = sqlite3.connect(str(db))
c.execute('PRAGMA journal_mode=WAL')
c.execute('PRAGMA wal_autocheckpoint=0')
c.execute('CREATE TABLE t(v TEXT)')
c.execute(\"INSERT INTO t VALUES ('committed-row')\")
c.commit()
os.environ['LOCALAPPDATA'] = str(fake_appdata)
sys.path.insert(0, '.')
import desktop.app as A
A._bundled = lambda: True
A._runtime_dir = lambda: fake_exe
A._configure_bundled_data_paths()
A._migrate_legacy_db_once()
target = fake_appdata / 'CVMAnalytics/db/cvm_financials.db'
print('migrated:', sqlite3.connect(str(target)).execute('SELECT v FROM t').fetchall())
"
```

---

## Phase 1.x — Vite SPA dev + bridge

### Interactive (stays open until you close it)
```bash
python scripts/phase1_pywebview_smoke.py --manual
```
Spawns Vite dev on `127.0.0.1:5173` + pywebview window with real `CVMBridge()` attached. Bridge tap prints `ping` / `get_health` / `get_companies` / `get_company_info` / `get_company_years` / `get_company_kpis` at startup. Manual mode = no auto-close.

### Automated (auto-closes after N seconds)
```bash
python scripts/phase1_pywebview_smoke.py            # default 12s
python scripts/phase1_pywebview_smoke.py --timeout 30
```

### Vite-only checks (no Python)
```bash
npm --prefix apps/desktop-web install
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
npm --prefix apps/desktop-web run dev      # http://127.0.0.1:5173, browser-mode banner active
```

### Bridge contract probe (Python only)
```bash
python -c "
import sys; sys.path.insert(0, '.')
from desktop.bridge import CVMBridge
b = CVMBridge()
print('ping:', b.ping())
print('health:', b.get_health()['status'])
page = b.get_companies({'page': 1, 'page_size': 3})
print('total companies:', page['pagination']['total_items'])
info = b.get_company_info({'cd_cvm': page['items'][0]['cd_cvm']})
print('first company:', info['company_name'])
"
```

---

## Phase 5B — Packaged Vite-only mode

### Build packaged exe
```powershell
.\desktop\build_desktop.ps1                     # builds Vite + PyInstaller (fresh)
.\desktop\build_desktop.ps1 -SkipViteBuild      # PyInstaller only if Vite dist still good
.\desktop\build_desktop.ps1 -Version 0.3.5      # explicit version
```

### Default mode (Vite)
```powershell
.\dist\CVMAnalytics\CVMAnalytics.exe
```
Expect: no `node.exe`; WebView2 children spawn; window opens; Documents data root is preserved.

### `--vite` mode (alias)
```powershell
.\dist\CVMAnalytics\CVMAnalytics.exe --vite
```
Expect: no `node.exe`; pywebview window; Documents data root is preserved.

### `--legacy` mode (unsupported)
```powershell
.\dist\CVMAnalytics\CVMAnalytics.exe --legacy
```
Expect: native warning that the legacy Next/Node runtime was removed, then the Vite UI opens. No `node.exe`.

### Process count comparison (run all supported aliases, measure)
```bash
python <<'PYEOF'
import subprocess, time
def count(name):
    r = subprocess.run(['tasklist.exe','/FI',f'IMAGENAME eq {name}'], capture_output=True, text=True)
    return sum(1 for line in r.stdout.splitlines() if name.lower() in line.lower())
for n in ('CVMAnalytics.exe','node.exe','msedgewebview2.exe'):
    subprocess.run(['taskkill.exe','/F','/IM',n,'/T'], capture_output=True)
time.sleep(2)
baseline = {'node': count('node.exe'), 'wv2': count('msedgewebview2.exe')}
for flag in ([], ['--vite'], ['--legacy']):
    p = subprocess.Popen([r'dist\CVMAnalytics\CVMAnalytics.exe', *flag],
        creationflags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
    time.sleep(20)
    label = ' '.join(flag) if flag else 'default'
    print(f'{label}: alive={p.poll() is None} node={count(\"node.exe\")-baseline[\"node\"]} wv2_delta={count(\"msedgewebview2.exe\")-baseline[\"wv2\"]}')
    subprocess.run(['taskkill.exe','/F','/PID',str(p.pid),'/T'], capture_output=True)
    subprocess.run(['taskkill.exe','/F','/IM','msedgewebview2.exe','/T'], capture_output=True)
    subprocess.run(['taskkill.exe','/F','/IM','node.exe','/T'], capture_output=True)
    time.sleep(2)
PYEOF
```

### Vite mode dev (uses `apps/desktop-web/dist/`, not the dev server)
```bash
npm --prefix apps/desktop-web run build
python -m desktop.app --vite
```

### Vite dev server (source checkout only)
```bash
python -m desktop.app --dev
```
Expect: starts or reuses Vite dev server on `127.0.0.1:5173`.

---

## Diagnostics (any phase)

### Generate a runtime diagnostic log
```powershell
.\dist\CVMAnalytics\CVMAnalytics.exe --diagnose-runtime
```
Writes `%USERPROFILE%\Documents\CVMAnalytics\diagnostics-<utc>.log` and opens it in Notepad. Use for user bug reports.

### Inspect bundle layout
```bash
ls dist/CVMAnalytics/
ls dist/CVMAnalytics/_internal/
test -d dist/CVMAnalytics/_internal/desktop-web
test ! -e dist/CVMAnalytics/_internal/web_standalone
test ! -e dist/CVMAnalytics/_internal/node.exe
```

### Verify zip layout pre-release
```bash
python -c "
import zipfile
with zipfile.ZipFile('release/CVMAnalytics-windows-vX.Y.Z.zip') as z:
    roots = sorted({n.split('/')[0] for n in z.namelist()})
    print('roots:', roots)
    assert set(roots) == {'CVMAnalytics.exe', '_internal'}, f'BAD layout: {roots}'
    print('LAYOUT OK (flat root)')
"
```

### Release pipeline check
```bash
gh release view vX.Y.Z --json assets,name,url,isPrerelease,publishedAt
```

---

## Cleanup helpers

### Kill all CVMAnalytics processes
```bash
python -c "
import subprocess
for n in ('CVMAnalytics.exe','node.exe','msedgewebview2.exe','pythonw.exe'):
    subprocess.run(['taskkill.exe','/F','/IM',n,'/T'], capture_output=True)
"
```

### Wipe Documents runtime data (use with caution — destroys user DB)
```bash
rm -rf "$USERPROFILE/Documents/CVMAnalytics"
```

### Wipe test sandboxes
```bash
rm -rf /tmp/cvm_* "$TEMP"/cvm_*
```

### Reset Phase 0 install-dir state (no-op since v0.3.4)
```bash
rm -rf dist/CVMAnalytics/data
```
