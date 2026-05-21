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
    dev_mode = "--dev" in args
    debug_mode = "--debug" in args

    _configure_bundled_data_paths()
    _migrate_legacy_db_once()
    _ensure_db_initialized()
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
