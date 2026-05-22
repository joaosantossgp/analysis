# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para CVM Analytics Desktop (Opção A — pasta distribuível).
#
# Pré-requisitos antes de rodar este spec:
#   1. npm --prefix apps/web run build   (gera .next/standalone/)
#   2. Copiar public/ e .next/static/ para dentro de standalone/ (feito pelo build_desktop.ps1)
#   3. Ter desktop/node_portable/node.exe disponível (copiado pelo build_desktop.ps1)
#
# Uso: pyinstaller desktop/app.spec --noconfirm
# Saída: dist/CVMAnalytics/CVMAnalytics.exe

import pythonnet
from pathlib import Path

ROOT = Path(SPECPATH).parent  # repo root (spec está em desktop/, ROOT é um nível acima)
STANDALONE_DIR = ROOT / "apps" / "web" / ".next" / "standalone"
VITE_DIST_DIR = ROOT / "apps" / "desktop-web" / "dist"
NODE_EXE = ROOT / "desktop" / "node_portable" / "node.exe"
UPDATE_HELPER = ROOT / "desktop" / "update_helper.ps1"
GICS_MAPPING_CSV = ROOT / "data" / "import" / "gics_mapping.csv"

datas = []

if STANDALONE_DIR.exists():
    datas.append((str(STANDALONE_DIR), "web_standalone"))

# Phase 2: ship the Vite static SPA alongside the Next standalone. The
# runtime decides which one to load via the `--vite` flag in desktop/app.py.
# Bundling both keeps the default Next path intact while enabling the
# experimental Vite mode on the same executable.
if VITE_DIST_DIR.exists():
    datas.append((str(VITE_DIST_DIR), "desktop-web"))

if NODE_EXE.exists():
    datas.append((str(NODE_EXE), "."))

# Bundled PowerShell helper used by the auto-updater to swap files after exit.
datas.append((str(UPDATE_HELPER), "."))

# v0.14.1 hotfix: ship the canonical GICS mapping CSV so the startup
# backfill in desktop/app.py::_ensure_gics_backfilled can populate
# companies.gics_* on user DBs that were seeded before GICS columns were
# filled. Without this asset, the Vite sectors / sector-filter screens
# render only "Sem classificacao GICS".
if GICS_MAPPING_CSV.exists():
    datas.append((str(GICS_MAPPING_CSV), "data/import"))

# v0.3.1: pythonnet's .NET assembly cannot bind its dependencies without
# Python.Runtime.deps.json sitting next to Python.Runtime.dll. PyInstaller's
# default collector only ships the .dll, which causes:
#
#   RuntimeError: Failed to resolve Python.Runtime.Loader.Initialize from
#   <bundle>\_internal\pythonnet\runtime\Python.Runtime.dll
#
# Ship the full runtime/ directory verbatim. .deps.json is mandatory; .xml
# and .pdb are small and harmless to ship.
PYTHONNET_RUNTIME = Path(pythonnet.__file__).parent / "runtime"
if PYTHONNET_RUNTIME.is_dir():
    for runtime_file in PYTHONNET_RUNTIME.iterdir():
        if runtime_file.is_file():
            datas.append((str(runtime_file), "pythonnet/runtime"))

a = Analysis(
    [str(ROOT / "desktop" / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # pywebview backends (Windows usa EdgeChromium / WinForms)
        "webview",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        # bridge e deps lazy-importadas
        "desktop.bridge",
        "src.read_service",
        "src.db",
        # clr/pythonnet necessário para pywebview no Windows
        "clr",
        "clr_loader",
        "clr_loader.netfx",
        "clr_loader.hostfxr",
        "pythonnet",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # excluir tooling que não vai ao runtime
        "pytest",
        "IPython",
        "matplotlib",
        "tkinter",
        "streamlit",
        "plotly",
        "altair",
        "pyarrow",
        "polars",
        "_polars_runtime_32",
        "PIL",
        "lxml",
        "psycopg2",
        "yfinance",
        "curl_cffi",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# v0.3.1: UPX disabled entirely. UPX-compressed .NET assemblies are a
# well-known source of "Failed to resolve" loader errors and AV false
# positives on Windows SmartScreen. The size win is not worth the
# reliability hit for a release-grade build.
USE_UPX = False

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # --onedir: binários ficam na pasta, não embutidos no exe
    name="CVMAnalytics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=USE_UPX,
    console=False,  # sem janela de console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: adicionar ícone .ico em Fase 5
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=USE_UPX,
    upx_exclude=[
        # Belt-and-suspenders: even if UPX is re-enabled later, never
        # compress .NET / native loader assets or WebView2 helpers.
        "Python.Runtime.dll",
        "ClrLoader.dll",
        "WebView2Loader.dll",
    ],
    name="CVMAnalytics",
)
