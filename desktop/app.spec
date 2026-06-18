# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para CVM Analytics Desktop (Opção A — pasta distribuível).
#
# Pré-requisitos antes de rodar este spec:
#   1. npm --prefix apps/desktop-web run build   (gera dist/)
#
# Uso: pyinstaller desktop/app.spec --noconfirm
# Saída: dist/CVMAnalytics/CVMAnalytics.exe

import pythonnet
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # repo root (spec está em desktop/, ROOT é um nível acima)
VITE_DIST_DIR = ROOT / "apps" / "desktop-web" / "dist"
UPDATE_HELPER = ROOT / "desktop" / "update_helper.ps1"
GICS_MAPPING_CSV = ROOT / "data" / "import" / "gics_mapping.csv"
CANONICAL_ACCOUNTS_CSV = ROOT / "data" / "import" / "canonical_accounts.csv"

datas = []

# Phase 5B: desktop package ships only the static Vite SPA. The legacy
# standalone web runtime is intentionally not included.
if VITE_DIST_DIR.exists():
    datas.append((str(VITE_DIST_DIR), "desktop-web"))

# Bundled PowerShell helper used by the auto-updater to swap files after exit.
datas.append((str(UPDATE_HELPER), "."))

# v0.14.1 hotfix: ship the canonical GICS mapping CSV so the startup
# backfill in desktop/app.py::_ensure_gics_backfilled can populate
# companies.gics_* on user DBs that were seeded before GICS columns were
# filled. Without this asset, the Vite sectors / sector-filter screens
# render only "Sem classificacao GICS".
if GICS_MAPPING_CSV.exists():
    datas.append((str(GICS_MAPPING_CSV), "data/import"))

# Ship the canonical CVM account dictionary used by scraper/Excel paths that
# can run from the packaged desktop bridge.
if CANONICAL_ACCOUNTS_CSV.exists():
    datas.append((str(CANONICAL_ACCOUNTS_CSV), "data/import"))

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
        # provenance gerado por build_desktop.ps1 (import condicional em bridge.py)
        "desktop._build_info",
        "desktop.bridge_api.base",
        "desktop.bridge_api.companies",
        "desktop.bridge_api.energy",
        "desktop.bridge_api.refresh",
        "desktop.bridge_api.status",
        "desktop.bridge_api.distribution",
        "src.companies.gics_manual_mapping",
        "src.companies.market_cap",
        "src.companies.market_history",
        "src.companies.sector_taxonomy",
        "src.companies.ticker_map",
        "src.companies.universe",
        "yfinance",
        "yfinance.data",
        "yfinance.scrapers",
        "yfinance.scrapers.history",
        "yfinance.scrapers.quote",
        "frozendict",
        "peewee",
        "curl_cffi",
        "curl_cffi.requests",
        "platformdirs",
        "multitasking",
        "google.protobuf",
        "src.energy_kpi.excel",
        "src.energy_kpi.plant_parcel_refresh",
        "src.energy_kpi.read",
        "src.energy_kpi.refresh",
        "src.energy_kpi.sin_refresh",
        "src.energy_kpi.distribution.aggregates",
        "src.energy_kpi.distribution.catalog",
        "src.energy_kpi.distribution.excel",
        "src.energy_kpi.distribution.ingest",
        "src.energy_kpi.distribution.quality",
        "src.energy_kpi.distribution.read",
        "src.financials.database",
        "src.financials.read_service",
        "src.financials.read_service_coverage",
        "src.financials.read_service_export",
        "src.financials.read_service_query",
        "src.financials.read_service_refresh_selection",
        "src.platform.settings",
        "src.platform.db",
        "src.refresh.github_dispatch",
        "src.refresh.job_worker",
        "src.refresh.jobs",
        "src.refresh.service",
        # clr/pythonnet necessário para pywebview no Windows
        "clr",
        "clr_loader",
        "clr_loader.netfx",
        "clr_loader.hostfxr",
        "pythonnet",
    ] + collect_submodules("trafilatura"),
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
        "PIL",
        "psycopg2",
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
