"""
CVM Analytics — entry point pywebview.

Uso:
  python -m desktop.app --dev    # inicia/reusa Next.js dev server em :3000
  python -m desktop.app          # standalone server em .next/standalone/server.js
  python -m desktop.app --debug  # abre DevTools no modo que estiver ativo

Quando empacotado via PyInstaller (sys.frozen=True):
  - server.js lido de sys._MEIPASS/web_standalone/server.js
  - node.exe lido de sys._MEIPASS/node.exe (copiado pelo build_desktop.ps1)
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

import webview

from desktop.bridge import CVMBridge

_USER_DATA_DIR_NAME = "CVMAnalytics"
_RECOVERY_LOG_NAME = "recovery.log"

_DEV_PORT = 3000
_DEV_URL = f"http://127.0.0.1:{_DEV_PORT}"
_WIDTH, _HEIGHT = 1280, 820
_BG = "#0a0a0a"
_STARTUP_TIMEOUT = 15  # segundos — bundle pode demorar mais no primeiro boot


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


def _user_data_root() -> Path:
    """Authoritative location for user-writable runtime data on Windows.

    Resolves to %LOCALAPPDATA%\\CVMAnalytics, or falls back to the system temp
    directory if LOCALAPPDATA is unset (non-Windows test environments).
    """
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return Path(base) / _USER_DATA_DIR_NAME


def _legacy_install_data_root() -> Path | None:
    """Pre-Phase-0 location of the runtime DB: <exe-dir>/data."""
    if not _bundled():
        return None
    return _runtime_dir() / "data"


def _configure_bundled_data_paths() -> None:
    if not _bundled():
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
    os.environ.setdefault("CVM_OUTPUT_DIR", str(output_dir))
    os.environ.setdefault("CVM_LOG_DIR", str(logs_dir))
    os.environ.setdefault("CVM_CACHE_DIR", str(cache_dir))


def _migrate_legacy_db_once() -> None:
    """Migrate any pre-Phase-0 install-dir DB into LOCALAPPDATA.

    Idempotency comes from target-existence check, not a sentinel file.
    If the user's runtime DB already exists at the target location, we
    never touch it.

    WAL safety: we use sqlite3.Connection.backup() on a read-only handle of
    the source. The Backup API captures a consistent snapshot including any
    uncheckpointed pages in -wal, so the target file is self-contained and
    safe to open in any journal mode without the original sidecars.

    Recovery: if the target is missing AND no legacy DB is found, we log
    the situation and return — downstream code initializes a fresh DB via
    migrations.

    Must run after _configure_bundled_data_paths so paths are provisioned.
    """
    if not _bundled():
        return

    user_root = _user_data_root()
    target_db = user_root / "db" / "cvm_financials.db"

    if target_db.exists():
        return  # user already has a runtime DB; never overwrite

    legacy_root = _legacy_install_data_root()
    legacy_db = (
        legacy_root / "db" / "cvm_financials.db" if legacy_root else None
    )

    if legacy_db is None or not legacy_db.exists():
        _log_recovery(
            user_root,
            "no target DB and no legacy DB found; downstream will init fresh",
        )
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = user_root / "backup" / f"legacy-db-{timestamp}"
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

    _log_recovery(user_root, f"migrated legacy DB from {legacy_db}")


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
    """Collect runtime diagnostics into a file under LOCALAPPDATA.

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

    section("import clr")
    try:
        import clr  # noqa: F401, PLC0415
        kv("status", "OK")
    except Exception as exc:
        kv("status", f"FAILED: {type(exc).__name__}: {exc}")
        lines.append("---traceback---")
        lines.append(traceback.format_exc())

    section("import sqlite3 + LOCALAPPDATA DB")
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
    summary = (
        f"Diagnostico salvo em:\n{log_path}\n\n"
        "Clique em OK para abrir o arquivo no Notepad."
    )
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


def _ensure_db_initialized() -> None:
    """Ensure the runtime DB has the required schema.

    Idempotent: SQLAlchemy's metadata.create_all is a no-op when the tables
    already exist. Guarantees that a fresh bundled install — where the
    migrator found neither a target nor a legacy DB — still ends with a
    usable schema before the bridge serves its first request.
    """
    if not _bundled():
        return
    try:
        from src.database import init_db_tables  # noqa: PLC0415
        from src.db import build_engine  # noqa: PLC0415

        engine = build_engine()
        try:
            init_db_tables(engine)
        finally:
            engine.dispose()
    except Exception as exc:
        _log_recovery(_user_data_root(), f"init_db_tables failed: {exc!r}")


def _log_recovery(user_root: Path, message: str) -> None:
    try:
        user_root.mkdir(parents=True, exist_ok=True)
        log_path = user_root / _RECOVERY_LOG_NAME
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def _web_dir() -> Path:
    return _repo_root() / "apps" / "web"


def _standalone_path() -> Path:
    if _bundled():
        return _bundle_dir() / "web_standalone" / "server.js"
    return _web_dir() / ".next" / "standalone" / "server.js"


def _node_exe() -> str:
    """Retorna o caminho do node a usar: bundled primeiro, depois PATH."""
    if _bundled():
        node = _bundle_dir() / "node.exe"
        if node.exists():
            return str(node)
    return "node"


def _npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


def _start_dev_server() -> tuple[subprocess.Popen[bytes], int]:
    web_dir = _web_dir()
    if not (web_dir / "package.json").exists():
        sys.exit(f"[desktop] Web app nao encontrado em {web_dir}.")

    env = {**os.environ, "BROWSER": "none", "ANALISYS_DESKTOP_MODE": "1"}
    proc = subprocess.Popen(
        [
            _npm_cmd(),
            "run",
            "dev",
            "--",
            "--hostname",
            "127.0.0.1",
            "--port",
            str(_DEV_PORT),
        ],
        cwd=str(web_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc, _DEV_PORT


def _start_standalone_server(standalone: Path) -> tuple[subprocess.Popen[bytes], int]:
    port = _free_port()
    env = {
        **os.environ,
        "PORT": str(port),
        "HOSTNAME": "127.0.0.1",
        "ANALISYS_DESKTOP_MODE": "1",
    }
    proc = subprocess.Popen(
        [_node_exe(), str(standalone)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc, port


def main() -> None:
    args = sys.argv[1:]
    if "--diagnose-runtime" in args:
        _run_diagnostic_mode()
        return  # _run_diagnostic_mode calls sys.exit; defensive
    dev_mode = "--dev" in args
    debug_mode = "--debug" in args

    _configure_bundled_data_paths()
    _migrate_legacy_db_once()
    _ensure_db_initialized()
    _preflight_pywebview_backend()
    bridge = CVMBridge()
    server_proc: subprocess.Popen[bytes] | None = None

    if dev_mode:
        if _port_open(_DEV_PORT):
            url = _DEV_URL
        else:
            server_proc, port = _start_dev_server()
            if not _wait_for_port(port, timeout=30):
                server_proc.terminate()
                sys.exit(
                    f"[desktop] Next.js dev server nao respondeu na porta {port} "
                    "apos 30s."
                )
            url = _DEV_URL
    else:
        standalone = _standalone_path()
        if not standalone.exists():
            sys.exit(
                f"[desktop] Standalone server não encontrado em {standalone}.\n"
                "Execute primeiro:\n"
                "  .\\desktop\\build_desktop.ps1\n"
                "(ou: npm --prefix apps/web run build)"
            )
        server_proc, port = _start_standalone_server(standalone)
        if not _wait_for_port(port):
            server_proc.terminate()
            sys.exit(
                f"[desktop] Servidor standalone não respondeu na porta {port} "
                f"após {_STARTUP_TIMEOUT}s."
            )
        url = f"http://127.0.0.1:{port}"

    webview.create_window(
        "CVM Analytics",
        url=url,
        js_api=bridge,
        width=_WIDTH,
        height=_HEIGHT,
        background_color=_BG,
        min_size=(800, 600),
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

    webview.start(debug=debug_mode)

    if server_proc is not None:
        server_proc.terminate()


if __name__ == "__main__":
    main()
