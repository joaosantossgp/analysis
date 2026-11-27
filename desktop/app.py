"""
CVM Analytics — entry point pywebview.

Uso:
  python -m desktop.app             # Vite SPA default (no Node process)
  python -m desktop.app --vite      # alias of default Vite mode
  python -m desktop.app --legacy    # unsupported; warns, then opens Vite
  python -m desktop.app --dev       # Vite dev server on :5173 (source mode)
  python -m desktop.app --debug     # opens DevTools in whichever mode is active
  python -m desktop.app --diagnose-runtime  # write diagnostics log and exit

Dev data path:
  By default, a source run uses the shared dev data of the main checkout
  (<main checkout>/data/dev-runtime), also when launched from a git worktree.
  A data-sensitive worktree uses isolated dev data (see desktop/dev_data.py).
  The packaged release continues to use Documents.
  Set CVM_DATA_DIR=<path> to use an arbitrary data directory.

Phase 5B (v0.15.0): the packaged desktop runtime is Vite only. The legacy
web runtime is no longer bundled. The updater, bundle layout, and user-data
contract remain unchanged.

When packaged via PyInstaller (sys.frozen=True):
  - Vite SPA loaded from sys._MEIPASS/desktop-web/index.html (default).
"""

from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

from datetime import datetime, timezone
from pathlib import Path

# Source mode starts with whatever Python the developer invoked. Provision and
# re-exec into the repository-local environment before importing pywebview or
# bridge modules. Frozen builds already contain their Python dependencies.
if __name__ == "__main__":
    from desktop.dev_bootstrap import BootstrapError, bootstrap_and_reexec_if_needed

    try:
        sys.argv = [sys.argv[0], *bootstrap_and_reexec_if_needed(sys.argv[1:])]
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    # Source `--dev` runs under the dev supervisor, which starts this module
    # again as its child. Decided before the runtime imports below so broken
    # app code cannot take the supervisor down. The packaged app never loads it.
    if not getattr(sys, "frozen", False):
        from desktop import dev_supervisor

        if dev_supervisor.should_supervise(sys.argv[1:], os.environ):
            raise SystemExit(dev_supervisor.run(sys.argv[1:]))

from desktop import lockfile
import webview

from desktop.bridge import CVMBridge

_USER_DATA_DIR_NAME = "CVMAnalytics"
_RECOVERY_LOG_NAME = "recovery.log"

_VITE_DEV_PORT = 5173
_VITE_DEV_URL = f"http://127.0.0.1:{_VITE_DEV_PORT}"
_VITE_DEV_PORT_MAX = 5199
_WIDTH, _HEIGHT = 1280, 820
_BG = "#0a0a0a"
_STARTUP_TIMEOUT = 15  # segundos — bundle pode demorar mais no primeiro boot
_LEGACY_REMOVED_MESSAGE = (
    "Legacy web runtime was removed. Please launch without --legacy.\n\n"
    "CVMAnalytics will continue with the Vite desktop UI."
)


def _bundled() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _bundle_dir() -> Path:
    return Path(sys._MEIPASS)  # type: ignore[attr-defined]


def _repo_root() -> Path:
    return Path(__file__).parent.parent


def _runtime_dir() -> Path:
    if _bundled():
        return Path(sys.executable).resolve().parent
    return _repo_root()


def _documents_data_root() -> Path | None:
    """Default Phase 3C user-visible data root: %USERPROFILE%\\Documents\\CVMAnalytics."""
    profile = os.environ.get("USERPROFILE")
    if not profile:
        return None
    return Path(profile) / "Documents" / _USER_DATA_DIR_NAME


def _legacy_localappdata_root() -> Path:
    """Pre-Phase-3C location of runtime data: %LOCALAPPDATA%\\CVMAnalytics.

    Still used by the updater (`desktop/updater.py`) and `update_helper.ps1`
    for staging/rollback. Kept as a migration source for the active runtime
    data root.
    """
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return Path(base) / _USER_DATA_DIR_NAME


def _user_data_root() -> Path:
    """Authoritative location for user-writable runtime data.

    Resolution order:
      1. ``CVMANALYTICS_DATA_DIR`` env var (operator override).
      2. ``%USERPROFILE%\\Documents\\CVMAnalytics`` (Phase 3C default).
      3. ``%LOCALAPPDATA%\\CVMAnalytics`` (pre-3C default; kept as fallback
         when USERPROFILE is missing, e.g. service accounts).
      4. ``<tempdir>/CVMAnalytics`` (non-Windows / test fallback).
    """
    override = os.environ.get("CVMANALYTICS_DATA_DIR")
    if override:
        return Path(override)
    docs = _documents_data_root()
    if docs is not None:
        return docs
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return Path(base) / _USER_DATA_DIR_NAME


def _legacy_install_data_root() -> Path | None:
    """Pre-Phase-0 location of the runtime DB: <exe-dir>/data."""
    if not _bundled():
        return None
    return _runtime_dir() / "data"


def _configure_bundled_data_paths() -> None:
    if not _bundled():
        if not os.environ.get("CVM_DATA_DIR"):
            use_release_data = os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {"1", "true", "yes"}
            if use_release_data:
                user_root = _user_data_root()
            else:
                from desktop import dev_data  # noqa: PLC0415 - source-mode dev tooling

                dev = dev_data.resolve(_repo_root())
                user_root = dev.data_root
                if dev.mode == dev_data.ISOLATED:
                    # Isolated dev data owns its databases; downloaded CVM files stay shared.
                    os.environ.setdefault("CVM_INPUT_DIR", str(dev.shared_root / "input"))
            db_dir = user_root / "db"
            output_dir = user_root / "output"
            logs_dir = user_root / "logs"
            cache_dir = user_root / "cache"

            for path in (user_root, db_dir, output_dir, logs_dir, cache_dir):
                path.mkdir(parents=True, exist_ok=True)

            if not use_release_data:
                os.environ.pop("CVMANALYTICS_USE_RELEASE_DATA", None)
            os.environ["CVM_DATA_DIR"] = str(user_root)
            os.environ.setdefault("CVM_DB_DIR", str(db_dir))
            os.environ.setdefault("SQLITE_PATH", str(db_dir / "cvm_financials.db"))
            os.environ.setdefault("CVM_NEWS_DB", str(db_dir / "news.db"))
            os.environ.setdefault("CVM_OUTPUT_DIR", str(output_dir))
            os.environ.setdefault("CVM_LOG_DIR", str(logs_dir))
            os.environ.setdefault("CVM_CACHE_DIR", str(cache_dir))
        return

    user_root = _user_data_root()
    db_dir = user_root / "db"
    output_dir = user_root / "output"
    logs_dir = user_root / "logs"
    cache_dir = user_root / "cache"

    for path in (user_root, db_dir, output_dir, logs_dir, cache_dir):
        path.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("CVM_DATA_DIR", str(user_root))
    os.environ.setdefault("CVM_DB_DIR", str(db_dir))
    os.environ.setdefault("SQLITE_PATH", str(db_dir / "cvm_financials.db"))
    os.environ.setdefault("CVM_NEWS_DB", str(db_dir / "news.db"))
    os.environ.setdefault("CVM_OUTPUT_DIR", str(output_dir))
    os.environ.setdefault("CVM_LOG_DIR", str(logs_dir))
    os.environ.setdefault("CVM_CACHE_DIR", str(cache_dir))


def _runtime_lock_dir() -> Path:
    """The runtime lock lives in the effective data root, not the launching checkout.

    Must run after _configure_bundled_data_paths. Two source runs on shared dev
    data therefore meet at the same lock file.
    """
    if "CVM_DATA_DIR" in os.environ:
        return Path(os.environ["CVM_DATA_DIR"])
    return _user_data_root() if _bundled() else _repo_root() / "data"


def _migrate_legacy_db_once() -> None:
    """Migrate any pre-Phase-3C runtime DB into the active user data root.

    The active runtime data root is resolved by `_user_data_root()` and now
    defaults to ``%USERPROFILE%\\Documents\\CVMAnalytics`` (Phase 3C). This
    function copies (never moves, never deletes) a legacy DB from older
    locations into the active root when, and only when, the active root has
    no DB of its own.

    Source priority (first existing wins):
      1. ``%LOCALAPPDATA%\\CVMAnalytics\\db\\cvm_financials.db`` (Phase 0
         through 3B).
      2. ``<install-dir>\\data\\db\\cvm_financials.db`` (pre-Phase-0).

    Idempotency comes from the target-existence check, not a sentinel file.
    If the user's runtime DB already exists at the active root, we never
    touch it.

    WAL safety: we use sqlite3.Connection.backup() on a read-only handle of
    the source. The Backup API captures a consistent snapshot including any
    uncheckpointed pages in -wal, so the target file is self-contained and
    safe to open in any journal mode without the original sidecars.

    Recovery: if the active target is missing AND no legacy DB is found,
    we log the situation and return — downstream code initializes a fresh
    DB via migrations.

    Must run after _configure_bundled_data_paths so paths are provisioned.
    """
    if not _bundled():
        return

    user_root = _user_data_root()
    target_db = user_root / "db" / "cvm_financials.db"

    if target_db.exists():
        return  # user already has a runtime DB; never overwrite

    candidates: list[tuple[str, Path]] = []
    localappdata_root = _legacy_localappdata_root()
    # Avoid recursive copy if the active root resolves to the same
    # LOCALAPPDATA path (e.g. operator override on a service account).
    if localappdata_root.resolve() != user_root.resolve():
        candidates.append(("localappdata", localappdata_root / "db" / "cvm_financials.db"))
    install_root = _legacy_install_data_root()
    if install_root is not None:
        candidates.append(("install_dir", install_root / "db" / "cvm_financials.db"))

    legacy_label: str | None = None
    legacy_db: Path | None = None
    for label, candidate in candidates:
        if candidate.exists():
            legacy_label = label
            legacy_db = candidate
            break

    if legacy_db is None:
        _log_recovery(
            user_root,
            "no target DB and no legacy DB found; downstream will init fresh",
        )
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = user_root / "backup" / f"legacy-db-{legacy_label}-{timestamp}"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        # Informational raw-file snapshot. May be WAL-inconsistent without
        # sidecars; sidecars are preserved alongside for forensic recovery.
        shutil.copy2(legacy_db, backup_dir / legacy_db.name)
        for suffix in ("-wal", "-shm"):
            sidecar = legacy_db.with_name(legacy_db.name + suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, backup_dir / sidecar.name)
    except Exception as exc:
        _log_recovery(user_root, f"backup failed: {exc!r}; aborting migration")
        return

    try:
        target_db.parent.mkdir(parents=True, exist_ok=True)
        _wal_safe_copy_sqlite(legacy_db, target_db)
    except Exception as exc:
        _log_recovery(
            user_root,
            f"WAL-safe copy failed: {exc!r}; target left empty for fresh init",
        )
        # Clean up any partial file the Backup API may have created.
        try:
            target_db.unlink(missing_ok=True)
        except Exception:
            pass
        return

    _log_recovery(
        user_root,
        f"migrated legacy DB from {legacy_db} (source={legacy_label}); "
        "original kept in place",
    )


def _wal_safe_copy_sqlite(source: Path, destination: Path) -> None:
    """Copy a SQLite DB via the Backup API, capturing any uncheckpointed WAL.

    Opens source as read-only (URI form) so we never write to the legacy
    file and never need to take a write lock. The Backup API streams pages
    into the destination, producing a consistent snapshot independent of
    the source's -wal/-shm files.
    """
    src_uri = f"file:{source.as_posix()}?mode=ro"
    src = sqlite3.connect(src_uri, uri=True)
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


_NET_FRAMEWORK_48_RELEASE_KEY = 528040  # Windows registry release value for 4.8

# File extensions that need Mark-of-the-Web stripped on first launch so .NET
# Framework's "loadFromRemoteSources" policy does not refuse to execute them.
_MOTW_STRIP_EXTENSIONS = (".dll", ".exe", ".pyd", ".node", ".ps1")


def _strip_motw_from_bundle() -> int:
    """Remove the Zone.Identifier ADS from every DLL/EXE/PYD in the bundle.

    Why this exists:
        When a user downloads the release ZIP from GitHub and extracts it
        with Windows Explorer's "Extract All" (the default on Windows 11),
        Windows applies Mark-of-the-Web (Zone.Identifier ADS, ZoneId=3) to
        every extracted file. .NET Framework's default loader policy
        refuses to execute managed assemblies whose source is the Internet
        zone, so `Assembly.LoadFile("...\\Python.Runtime.dll")` silently
        returns null and clr_loader raises:

            RuntimeError: Failed to resolve Python.Runtime.Loader.Initialize

        Note that PowerShell's `Expand-Archive` does NOT preserve MOTW,
        which is why this bug is invisible on developer machines that
        extract via the PowerShell helper.

    What it does:
        Walks the bundle directory and calls Win32 `DeleteFileW` on the
        `<file>:Zone.Identifier` alternate data stream of every .dll,
        .exe, .pyd, .node, and .ps1 file. Returns the number of streams
        successfully removed. Failures are silently tolerated — the
        worst case is we fall through to the precise MessageBox in
        `_preflight_pywebview_backend`.

    Idempotent: removing an ADS that does not exist is a no-op.
    Safe: only touches the Zone.Identifier stream, never the file body.
    """
    if not _bundled():
        return 0
    try:
        import ctypes  # noqa: PLC0415
    except Exception:
        return 0

    bundle = _bundle_dir()
    removed = 0
    delete_file = ctypes.windll.kernel32.DeleteFileW
    for f in bundle.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in _MOTW_STRIP_EXTENSIONS:
            continue
        ads_path = str(f) + ":Zone.Identifier"
        try:
            if delete_file(ads_path):
                removed += 1
        except Exception:
            pass
    return removed



def _detect_net_framework_release() -> int | None:
    """Read the NDP\\v4\\Full Release value from the Windows registry.

    Returns None if the key is missing (no .NET Framework 4.x installed)
    or if we cannot read it. Otherwise returns the integer Release value,
    where >= 528040 means .NET Framework 4.8 or later.
    """
    try:
        import winreg  # noqa: PLC0415
    except ImportError:
        return None
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full",
        )
    except OSError:
        return None
    try:
        value, _ = winreg.QueryValueEx(key, "Release")
        return int(value)
    except OSError:
        return None
    finally:
        winreg.CloseKey(key)


def _detect_webview2_runtime() -> str | None:
    """Return the installed Microsoft Edge WebView2 Runtime version or None.

    Checks the per-machine registry locations used by the Evergreen Runtime
    installer for both 64-bit and 32-bit hosts.
    """
    try:
        import winreg  # noqa: PLC0415
    except ImportError:
        return None
    candidates = (
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        ),
    )
    for root, sub in candidates:
        try:
            key = winreg.OpenKey(root, sub)
        except OSError:
            continue
        try:
            value, _ = winreg.QueryValueEx(key, "pv")
            value = str(value)
            if value and value != "0.0.0.0":
                return value
        except OSError:
            continue
        finally:
            winreg.CloseKey(key)
    return None


def _diagnose_runtime_to_file() -> Path:
    """Collect runtime diagnostics into a file under the user data root.

    Designed to run BEFORE any clr / pywebview import so that a broken
    .NET environment cannot prevent diagnostic collection. The resulting
    log path is returned so the caller can open it in Notepad and exit.
    """
    import hashlib  # noqa: PLC0415
    import platform  # noqa: PLC0415
    import traceback  # noqa: PLC0415

    user_root = _user_data_root()
    user_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = user_root / f"diagnostics-{stamp}.log"

    lines: list[str] = []

    def section(title: str) -> None:
        lines.append("")
        lines.append(f"=== {title} ===")

    def kv(key: str, value: object) -> None:
        lines.append(f"{key}: {value}")

    try:
        from desktop.__version__ import __version__ as app_version  # noqa: PLC0415
    except Exception:
        app_version = "unknown"

    section("App")
    kv("version", app_version)
    kv("frozen", _bundled())
    kv("executable", sys.executable)
    kv("python", sys.version.replace("\n", " "))
    kv("argv", sys.argv)

    section("Platform")
    kv("system", platform.system())
    kv("release", platform.release())
    kv("version", platform.version())
    kv("machine", platform.machine())
    kv("processor", platform.processor())
    kv("architecture", platform.architecture())

    section("Paths")
    kv("_MEIPASS", getattr(sys, "_MEIPASS", "n/a"))
    kv("_runtime_dir", _runtime_dir())
    kv("_user_data_root", user_root)
    kv("LOCALAPPDATA", os.environ.get("LOCALAPPDATA", "n/a"))

    section("Bundled pythonnet runtime/")
    if _bundled():
        runtime_dir = _bundle_dir() / "pythonnet" / "runtime"
        kv("path", runtime_dir)
        kv("exists", runtime_dir.is_dir())
        if runtime_dir.is_dir():
            for f in sorted(runtime_dir.iterdir()):
                if f.is_file():
                    h = hashlib.sha256()
                    with f.open("rb") as fh:
                        for chunk in iter(lambda: fh.read(65536), b""):
                            h.update(chunk)
                    kv(f"  {f.name}", f"size={f.stat().st_size} sha256={h.hexdigest()[:16]}")
    else:
        kv("note", "not a frozen build; skipped")

    section(".NET Framework")
    release = _detect_net_framework_release()
    kv("registry Release value", release)
    if release is None:
        kv("status", "NOT INSTALLED (no NDP\\v4\\Full\\Release key)")
    elif release < _NET_FRAMEWORK_48_RELEASE_KEY:
        kv("status", f"PRE-4.8 (Release {release} < {_NET_FRAMEWORK_48_RELEASE_KEY})")
    else:
        kv("status", f"OK (Release {release} >= {_NET_FRAMEWORK_48_RELEASE_KEY})")

    section("WebView2 Runtime")
    wv2 = _detect_webview2_runtime()
    kv("version", wv2 or "NOT INSTALLED")

    section("Environment overrides")
    for name in ("PYTHONNET_RUNTIME", "PYTHONNET_PYDLL", "DOTNET_ROOT", "PATH"):
        kv(name, os.environ.get(name, "n/a") if name != "PATH" else "(omitted; long)")

    section("Mark-of-the-Web stripping")
    removed = _strip_motw_from_bundle()
    kv("zone_identifier streams removed", removed)
    # After stripping, count any remaining
    remaining = 0
    if _bundled():
        for f in _bundle_dir().rglob("*"):
            if not f.is_file() or f.suffix.lower() not in _MOTW_STRIP_EXTENSIONS:
                continue
            ads = str(f) + ":Zone.Identifier"
            try:
                with open(ads, "rb"):
                    remaining += 1
            except (OSError, FileNotFoundError):
                pass
    kv("zone_identifier streams remaining", remaining)

    section("import clr")
    try:
        import clr  # noqa: F401, PLC0415
        kv("status", "OK")
    except Exception as exc:
        kv("status", f"FAILED: {type(exc).__name__}: {exc}")
        lines.append("---traceback---")
        lines.append(traceback.format_exc())

    section("import sqlite3 + Documents DB")
    try:
        import sqlite3 as _sql  # noqa: PLC0415
        db_path = user_root / "db" / "cvm_financials.db"
        kv("db_path", db_path)
        kv("exists_before", db_path.exists())
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = _sql.connect(str(db_path))
        rows = conn.execute("SELECT sqlite_version()").fetchone()
        conn.close()
        kv("sqlite_version", rows[0] if rows else "n/a")
        kv("status", "OK")
    except Exception as exc:
        kv("status", f"FAILED: {type(exc).__name__}: {exc}")

    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def _run_diagnostic_mode() -> None:
    """`--diagnose-runtime` entrypoint. Writes report + opens it in Notepad."""
    _configure_bundled_data_paths()
    log_path = _diagnose_runtime_to_file()
    is_headless = "--non-interactive" in sys.argv or "--headless" in sys.argv
    is_redirected = sys.stdout is None or not sys.stdout.isatty()
    non_interactive = is_headless or is_redirected
    summary = (
        f"Diagnostico salvo em:\n{log_path}\n\n"
        "Clique em OK para abrir o arquivo no Notepad."
    )
    if non_interactive:
        try:
            print("CVM Analytics - Diagnostico de runtime concluido.")
            print(f"Diagnostico salvo em: {log_path}")
        except Exception:
            pass
    else:
        _show_fatal_messagebox(title="CVM Analytics — diagnostico de runtime", body=summary)
        try:
            os.startfile(str(log_path))  # type: ignore[attr-defined]
        except Exception:
            pass
    sys.exit(0)


def _preflight_pywebview_backend() -> None:
    """Verify the pythonnet / .NET CLR backend can load on Windows.

    Performs three checks in order, before attempting `import clr`:

    1. Confirm `Python.Runtime.dll` and `Python.Runtime.deps.json` are
       present in the bundle. Missing files indicate a packaging
       regression (the v0.3.0 root cause).
    2. Confirm .NET Framework 4.8 or later is installed via the standard
       Windows registry probe. pywebview's WinForms backend depends on
       pythonnet's netfx loader, which requires .NET Framework on the
       target machine.
    3. Confirm Microsoft Edge WebView2 Runtime is installed. Without it
       pywebview can still create a window, but content rendering fails.

    On failure: shows a precise, user-actionable MessageBox naming the
    missing prerequisite, points the user at `--diagnose-runtime`, and
    exits non-zero.
    """
    if not _bundled():
        return

    runtime_dir = _bundle_dir() / "pythonnet" / "runtime"
    dll = runtime_dir / "Python.Runtime.dll"
    deps = runtime_dir / "Python.Runtime.deps.json"
    if not dll.exists() or not deps.exists():
        missing = []
        if not dll.exists():
            missing.append("Python.Runtime.dll")
        if not deps.exists():
            missing.append("Python.Runtime.deps.json")
        _show_fatal_messagebox(
            title="CVM Analytics — instalacao corrompida",
            body=(
                "O bundle do CVM Analytics esta incompleto.\n\n"
                f"Arquivo(s) ausente(s): {', '.join(missing)}\n"
                f"Local esperado: {runtime_dir}\n\n"
                "Acoes sugeridas:\n"
                " 1) Reextrair o ZIP da release em uma pasta nova.\n"
                " 2) Baixar novamente a release oficial do GitHub.\n"
                " 3) Verificar o SHA-256 do arquivo baixado.\n\n"
                f"Diagnostico detalhado: rode\n  {sys.executable} --diagnose-runtime"
            ),
        )
        _log_recovery(_user_data_root(), f"preflight missing bundle files: {missing}")
        sys.exit(1)

    release = _detect_net_framework_release()
    if release is None or release < _NET_FRAMEWORK_48_RELEASE_KEY:
        observed = "nao instalado" if release is None else f"Release={release}"
        _show_fatal_messagebox(
            title="CVM Analytics — pre-requisito ausente",
            body=(
                "O CVM Analytics requer Microsoft .NET Framework 4.8 ou superior.\n\n"
                f"Detectado: {observed}\n"
                f"Requerido: Release >= {_NET_FRAMEWORK_48_RELEASE_KEY} (.NET Framework 4.8)\n\n"
                "Como resolver:\n"
                " 1) Instalar o '.NET Framework 4.8 Runtime' a partir de:\n"
                "    https://dotnet.microsoft.com/download/dotnet-framework/net48\n"
                " 2) Reiniciar o computador.\n"
                " 3) Abrir o CVM Analytics novamente.\n\n"
                f"Diagnostico detalhado: rode\n  {sys.executable} --diagnose-runtime"
            ),
        )
        _log_recovery(_user_data_root(), f"preflight .NET Framework missing: release={release}")
        sys.exit(1)

    wv2 = _detect_webview2_runtime()
    if wv2 is None:
        _show_fatal_messagebox(
            title="CVM Analytics — pre-requisito ausente",
            body=(
                "O CVM Analytics requer o Microsoft Edge WebView2 Runtime.\n\n"
                "Detectado: nao instalado\n\n"
                "Como resolver:\n"
                " 1) Baixar e instalar o 'Evergreen Standalone Installer' em:\n"
                "    https://developer.microsoft.com/microsoft-edge/webview2/\n"
                " 2) Abrir o CVM Analytics novamente.\n\n"
                f"Diagnostico detalhado: rode\n  {sys.executable} --diagnose-runtime"
            ),
        )
        _log_recovery(_user_data_root(), "preflight WebView2 missing")
        sys.exit(1)

    try:
        import clr  # noqa: F401, PLC0415
    except Exception as exc:
        log_path = _diagnose_runtime_to_file()
        _show_fatal_messagebox(
            title="CVM Analytics — falha ao carregar runtime .NET",
            body=(
                "Pre-requisitos detectados, mas o componente .NET do pywebview "
                "ainda nao carregou.\n\n"
                f"Detalhe tecnico:\n{type(exc).__name__}: {exc}\n\n"
                f"Um diagnostico completo foi salvo em:\n{log_path}\n\n"
                "Por favor anexe esse arquivo ao reportar o problema."
            ),
        )
        _log_recovery(_user_data_root(), f"preflight clr import failed: {exc!r}")
        sys.exit(1)


def _show_fatal_messagebox(*, title: str, body: str) -> None:
    """Show a native Windows MessageBox without requiring any GUI toolkit."""
    try:
        import ctypes  # noqa: PLC0415
        # MB_OK | MB_ICONERROR | MB_TOPMOST = 0x00010000 | 0x00000010 = 0x00010010
        ctypes.windll.user32.MessageBoxW(0, body, title, 0x00010010)
    except Exception:
        # If even MessageBoxW fails, fall back to stderr.
        try:
            sys.stderr.write(f"[{title}] {body}\n")
        except Exception:
            pass


def _show_warning_messagebox(*, title: str, body: str, timeout_ms: int = 5000) -> None:
    """Show a short native warning without blocking startup indefinitely."""
    try:
        import ctypes  # noqa: PLC0415
        # MB_OK | MB_ICONWARNING | MB_TOPMOST = 0x00010000 | 0x00000030
        flags = 0x00010030
        timeout = getattr(ctypes.windll.user32, "MessageBoxTimeoutW", None)
        if timeout is not None:
            timeout(0, body, title, flags, 0, timeout_ms)
        else:
            ctypes.windll.user32.MessageBoxW(0, body, title, flags)
    except Exception:
        try:
            sys.stderr.write(f"[{title}] {body}\n")
        except Exception:
            pass


def _warn_legacy_removed() -> None:
    message = _LEGACY_REMOVED_MESSAGE
    _log_recovery(_user_data_root(), "unsupported --legacy flag used; continuing in Vite mode")
    try:
        print(f"[desktop] {message.replace(chr(10), ' ')}")
    except Exception:
        pass
    _show_warning_messagebox(
        title="CVM Analytics — legacy runtime removed",
        body=message,
    )


def _ensure_db_initialized() -> None:
    """Ensure the runtime DB has the required schema.

    Idempotent: SQLAlchemy's metadata.create_all is a no-op when the tables
    already exist. Guarantees that a fresh bundled install — where the
    migrator found neither a target nor a legacy DB — still ends with a
    usable schema before the bridge serves its first request. This applies to
    the isolated development data directory as well.
    """
    try:
        from src.financials.database import init_db_tables  # noqa: PLC0415
        from src.platform.db import build_engine  # noqa: PLC0415
        from src.platform.settings import build_settings  # noqa: PLC0415

        settings = build_settings()
        # An explicit CVM_DATA_DIR gets no folders from _configure_bundled_data_paths.
        settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = build_engine(settings)
        try:
            init_db_tables(engine)
        finally:
            engine.dispose()
    except Exception as exc:
        _log_recovery(Path(os.environ.get("CVM_DATA_DIR", _user_data_root())), f"init_db_tables failed: {exc!r}")


def _ensure_classification_synced() -> None:
    """Load the shipped curated GICS classification and materialize it into companies.

    Runs in packaged and development modes. An invalid dataset is rejected before any
    write, so the previous classification stays in place; the outcome goes to recovery.log.
    """
    log_root = Path(os.environ.get("CVM_DATA_DIR", _user_data_root()))
    try:
        from src.companies.classification import sync_curated_classification  # noqa: PLC0415
        from src.platform.db import build_engine  # noqa: PLC0415
        from src.platform.settings import build_settings  # noqa: PLC0415

        engine = build_engine(build_settings())
        try:
            result = sync_curated_classification(engine)
        finally:
            engine.dispose()
        _log_recovery(log_root, f"classification sync: {result}")
    except Exception as exc:
        _log_recovery(log_root, f"classification sync failed: {exc!r}")


def _log_recovery(user_root: Path, message: str) -> None:
    try:
        user_root.mkdir(parents=True, exist_ok=True)
        log_path = user_root / _RECOVERY_LOG_NAME
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def _npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_for_port(port: int, timeout: float = _STARTUP_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(port):
            return True
        time.sleep(0.2)
    return False


def _first_free_vite_dev_port() -> int:
    for port in range(_VITE_DEV_PORT, _VITE_DEV_PORT_MAX + 1):
        if not _port_open(port):
            return port
    sys.exit(
        f"[desktop] Nenhuma porta Vite livre encontrada entre "
        f"{_VITE_DEV_PORT} e {_VITE_DEV_PORT_MAX}."
    )


def _vite_dist_path() -> Path:
    """Locate the Vite static build.

    Bundled (`_bundled() == True`)  -> `<_MEIPASS>/desktop-web/`
    Dev mode                         -> `<repo>/apps/desktop-web/dist/`
    """
    if _bundled():
        return _bundle_dir() / "desktop-web"
    return _repo_root() / "apps" / "desktop-web" / "dist"


def _vite_app_dir() -> Path:
    return _repo_root() / "apps" / "desktop-web"


def _start_vite_static_server(dist: Path) -> tuple[object, int]:
    """Serve `dist/` over a loopback HTTP server.

    Returns the server instance plus the bound port. The caller is
    responsible for shutting the server down before the process exits.

    Rationale for HTTP over `file://`: WebView2 blocks several Web Platform
    features (fetch, importmaps, cross-origin isolation) when content is
    loaded from `file://`. A local HTTP server avoids that class of
    problems and gives the SPA normal same-origin HTTP behavior. The server
    binds to a random free loopback port so multiple
    instances do not collide.
    """
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer  # noqa: PLC0415

    dist_str = str(dist)

    class _QuietHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            # Pin the served directory at construction time — the partial-
            # based pattern from the docs does not survive subclassing.
            super().__init__(*args, directory=dist_str, **kwargs)  # type: ignore[arg-type]

        def log_message(self, *_args: object) -> None:
            # Silence per-request log lines on stderr. PyInstaller windowed
            # builds have no console; this is just noise in dev too.
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    port = server.server_address[1]
    threading.Thread(
        target=server.serve_forever,
        name="desktop-vite-static",
        daemon=True,
    ).start()
    return server, port


def _stop_vite_dev_server(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None:
        return

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    except (OSError, subprocess.SubprocessError):
        return


def _start_vite_dev_server() -> tuple[subprocess.Popen[bytes] | None, str]:
    vite_dir = _vite_app_dir()
    if not (vite_dir / "package.json").exists():
        sys.exit(f"[desktop] Vite app nao encontrado em {vite_dir}.")

    env = {**os.environ, "BROWSER": "none", "ANALISYS_DESKTOP_MODE": "1"}
    # Desktop dev must use the real pywebview bridge. If a parent shell was
    # used for `npm run dev:mock`, this inherited variable would make the Vite
    # bundle prefer fixture data over window.pywebview.api.
    env.pop("VITE_MOCK_BRIDGE", None)

    port = _first_free_vite_dev_port()
    if port != _VITE_DEV_PORT:
        print(
            f"[desktop] porta {_VITE_DEV_PORT} ocupada; iniciando Vite dev "
            f"sem mock em {port}."
        )

    proc = subprocess.Popen(
        [
            _npm_cmd(),
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--strictPort",
        ],
        cwd=str(vite_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _wait_for_port(port, timeout=30):
        _stop_vite_dev_server(proc)
        sys.exit(
            f"[desktop] Vite dev server nao respondeu na porta {port} "
            "apos 30s."
        )
    return proc, f"http://127.0.0.1:{port}"


_refresh_lock = threading.Lock()
_refresh_in_progress = False


def _background_local_metadata_enrichment() -> None:
    """Enrich missing CNPJs from local catalog evidence without network access."""
    global _refresh_in_progress
    import json
    
    # 1. Instance protection: verify this process owns the cross-process runtime lock
    from desktop import lockfile
    if lockfile.get_status().get("status") != "locked_by_self":
        print("[desktop] Local catalog enrichment: process does not own the runtime lock. Skipping.")
        return
        
    with _refresh_lock:
        if _refresh_in_progress:
            return
        _refresh_in_progress = True
        
    try:
        # Wait for UI to initialize
        time.sleep(2.0)
        
        db_path = _user_data_root() / "db" / "cvm_financials.db"
        if not db_path.exists():
            return
            
        now_ts = int(time.time())
        ttl_seconds = 604800  # 7 days TTL
        
        # 2. Check last successful refresh timestamp in app_settings
        last_refresh = 0
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)")
            cur.execute("SELECT value FROM app_settings WHERE key = 'metadata_last_successful_refresh'")
            row = cur.fetchone()
            if row:
                try:
                    last_refresh = int(json.loads(row[0]))
                except Exception:
                    pass
            
            # Check if companies table exists
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='companies'")
            if not cur.fetchone():
                return
            
            # Find companies with missing CNPJs
            cur.execute("SELECT cd_cvm FROM companies WHERE cnpj IS NULL")
            missing_companies = cur.fetchall()
        except sqlite3.OperationalError as e:
            print(f"[desktop] Warning: DB access during remote refresh check failed: {e}")
            return
        finally:
            conn.close()
            
        # If no companies are missing CNPJs, we don't need to refresh
        if not missing_companies:
            return
            
        # 3. Check TTL
        if now_ts - last_refresh < ttl_seconds:
            last_date = datetime.fromtimestamp(last_refresh, tz=timezone.utc).isoformat()
            print(f"[desktop] Local catalog enrichment: TTL not expired. Last refreshed at {last_date}. Skipping.")
            return
            
        print(f"[desktop] Local catalog enrichment: reading local evidence for {len(missing_companies)} companies...")
        
        from src.companies.catalog import CompanyCatalogService
        from src.companies.cnpj import validate_cnpj
        
        # Explicit 10s timeout
        catalog = CompanyCatalogService(timeout=10, snapshot_path=_user_data_root() / "metadata" / "cvm_company_catalog.json")
        # Read local evidence only; missing evidence leaves the success timestamp unchanged.
        catalog.list_entries()
        
        updates = []
        
        for (cd_cvm,) in missing_companies:
            try:
                entry = catalog.lookup_company(int(cd_cvm))
                if entry and entry.cnpj:
                    cleaned_cnpj = "".join(c for c in str(entry.cnpj) if c.isdigit())
                    if validate_cnpj(cleaned_cnpj):
                        updates.append((cleaned_cnpj, int(cd_cvm)))
            except Exception:
                pass
                
        # 4. Short transaction update & update last_successful_refresh
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            cur = conn.cursor()
            if updates:
                cur.executemany("UPDATE companies SET cnpj = ? WHERE cd_cvm = ?", updates)
            
            # Save successful refresh timestamp
            cur.execute(
                "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('metadata_last_successful_refresh', ?, ?)",
                (json.dumps(now_ts), datetime.now(timezone.utc).isoformat())
            )
            conn.commit()
            print(f"[desktop] Local catalog enrichment completed. Saved {len(updates)} CNPJs. Last success timestamp persisted.")
        except sqlite3.OperationalError as e:
            print(f"[desktop] Warning: Failed to persist remote refresh updates: {e}")
        finally:
            conn.close()
            
    except Exception as exc:
        print(f"[desktop] Warning: local metadata enrichment skipped: {exc}")
    finally:
        with _refresh_lock:
            _refresh_in_progress = False


def main() -> None:
    args = sys.argv[1:]
    if "--diagnose-runtime" in args:
        _run_diagnostic_mode()
        return  # _run_diagnostic_mode calls sys.exit; defensive
    dev_mode = "--dev" in args
    debug_mode = "--debug" in args
    legacy_requested = "--legacy" in args

    _configure_bundled_data_paths()

    # Acquire the runtime lock. Detects concurrent access to the same data
    # directory (e.g. release app and dev using release data simultaneously).
    try:
        from desktop.__version__ import __version__ as _lock_ver  # noqa: PLC0415
    except Exception:
        _lock_ver = None
    _lock_data_dir = _runtime_lock_dir()
    _lock_result = lockfile.acquire(_lock_data_dir, app_version=_lock_ver)
    if not _lock_result.get("owned"):
        _conflict = _lock_result.get("conflict") or {}
        _log_recovery(
            _lock_data_dir,
            f"concurrent access detected: PID {_conflict.get('pid')}, "
            f"mode={_conflict.get('runtime_mode')} — starting in restricted mode",
        )
        os.environ["CVMANALYTICS_CONCURRENT_LOCK_DETECTED"] = "1"
    elif _lock_result.get("stale"):
        _stale = _lock_result.get("conflict") or {}
        _log_recovery(
            _lock_data_dir,
            f"stale lock recovered from dead PID {_stale.get('pid')} "
            f"(mode={_stale.get('runtime_mode')})",
        )

    # Strip Mark-of-the-Web from bundle DLLs BEFORE any .NET load attempt.
    # Without this, Python.Runtime.dll fails to execute on machines where
    # Windows Explorer's "Extract All" preserved MOTW on extracted files.
    _strip_motw_from_bundle()
    _migrate_legacy_db_once()
    _ensure_db_initialized()
    _ensure_classification_synced()
    _preflight_pywebview_backend()
    if legacy_requested:
        _warn_legacy_removed()
    bridge = CVMBridge()
    server_proc: subprocess.Popen[bytes] | None = None
    static_server: object | None = None

    if dev_mode and not _bundled():
        server_proc, url = _start_vite_dev_server()
    else:
        # Default mode (and explicit --vite / legacy-flag fallback): serve the
        # static Vite SPA over a loopback HTTP server.
        if dev_mode and _bundled():
            _log_recovery(
                _user_data_root(),
                "unsupported --dev flag in packaged build; continuing in Vite mode",
            )
        dist = _vite_dist_path()
        index_html = dist / "index.html"
        if not index_html.exists():
            sys.exit(
                f"[desktop] Vite build nao encontrado em {dist}.\n"
                "Para gerar localmente:\n"
                "  npm --prefix apps/desktop-web run build\n"
                "Para empacotar:\n"
                "  .\\desktop\\build_desktop.ps1\n"
                "(verifique se o passo do Vite ficou habilitado)."
            )
        static_server, port = _start_vite_static_server(dist)
        url = f"http://127.0.0.1:{port}/"
        print(f"[desktop] vite mode: serving {dist} on {url}")

    excel_mapping_windows: dict[int, object] = {}
    excel_mapping_windows_lock = threading.RLock()

    def open_excel_mapping_window(cd_cvm: int) -> dict[str, object]:
        with excel_mapping_windows_lock:
            existing = excel_mapping_windows.get(cd_cvm)
            if existing is not None:
                try:
                    existing.restore()  # type: ignore[attr-defined]
                    existing.show()  # type: ignore[attr-defined]
                    return {"ok": True, "reused": True}
                except Exception:
                    excel_mapping_windows.pop(cd_cvm, None)

            window = webview.create_window(
                f"Excel Mapping — CVM {cd_cvm}",
                url=f"{url}?window=excel-mapping#/empresas/{cd_cvm}/model-mapping",
                js_api=bridge,
                width=1180,
                height=780,
                min_size=(900, 600),
                background_color=_BG,
            )
            if window is None:
                return {"ok": False, "error": "Could not create the Excel Mapping window."}

            excel_mapping_windows[cd_cvm] = window

            def forget_window(*_args: object) -> None:
                with excel_mapping_windows_lock:
                    excel_mapping_windows.pop(cd_cvm, None)

            window.events.closed += forget_window
            return {"ok": True, "reused": False}

    bridge.set_excel_mapping_window_opener(open_excel_mapping_window)

    # Under the dev supervisor, reopen on the route and geometry the previous
    # child saved. Every other launch keeps the fixed defaults.
    dev_state_file, dev_route, dev_geometry = None, "", {}
    if dev_mode and not _bundled():
        from desktop import dev_supervisor  # noqa: PLC0415

        dev_state_file = os.environ.get(dev_supervisor.STATE_FILE_ENV)
    if dev_state_file:
        dev_route, dev_geometry = dev_supervisor.load_window_state(Path(dev_state_file))

    main_window = webview.create_window(
        "CVM Analytics",
        url=url + dev_route,
        js_api=bridge,
        background_color=_BG,
        min_size=(800, 600),
        **{"width": _WIDTH, "height": _HEIGHT, **dev_geometry},
    )
    if dev_state_file:
        dev_supervisor.watch_for_stop(
            Path(dev_state_file),
            main_window,
            lambda: [window.destroy() for window in list(webview.windows)],
        )

    threading.Thread(
        target=bridge._start_update_check,
        name="desktop-update-check",
        daemon=True,
    ).start()

    # Drena jobs enfileirados em refresh_jobs (criados por
    # request_company_refresh no caminho single-company com período).
    threading.Thread(
        target=bridge._start_refresh_worker,
        name="desktop-refresh-worker",
        daemon=True,
    ).start()

    threading.Thread(
        target=_background_local_metadata_enrichment,
        name="desktop-local-metadata-enrichment",
        daemon=True,
    ).start()

    try:
        webview.start(debug=debug_mode)
    finally:
        lockfile.release()
        _stop_vite_dev_server(server_proc)
        if static_server is not None:
            try:
                static_server.shutdown()  # type: ignore[attr-defined]
            except Exception:
                pass


if __name__ == "__main__":
    main()
