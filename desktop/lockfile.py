"""
CVMAnalytics runtime lock file.

Prevents concurrent access by two CVMAnalytics processes to the same data
directory. The lock is a JSON file at {data_dir}/runtime.lock, written at
startup and deleted on graceful shutdown.

Lock file schema:
  {
    "pid": int,
    "runtime_mode": str,  # "release" | "dev-isolated" | "dev-release-data" | "dev-static"
    "started_at": str,    # ISO 8601 UTC
    "data_dir": str,
    "db_path": str,
    "app_version": str | "unknown"
  }

Stale locks (PID no longer alive) are automatically recovered.
Non-fatal: if the lock file cannot be written, the app continues without one.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_LOCK_FILENAME = "runtime.lock"

# Module-level state — set by acquire(), cleared by release()
_lock_path: Path | None = None
_lock_owned: bool = False
_conflict_info: dict | None = None
_stale_recovered: bool = False


def _pid_alive(pid: int) -> bool:
    """Return True if the process with the given PID is alive."""
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
            return True
        # ERROR_ACCESS_DENIED (5): process exists but we lack permission
        return ctypes.windll.kernel32.GetLastError() == 5  # type: ignore[attr-defined]
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False


def _runtime_mode_label() -> str:
    if getattr(sys, "frozen", False):
        return "release"
    argv = {str(arg).lower() for arg in sys.argv}
    use_release = os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {
        "1", "true", "yes",
    }
    if use_release:
        return "dev-release-data"
    if "--dev" in argv:
        return "dev-isolated"
    return "dev-static"


def _read_lock_file(lock_path: Path) -> dict | None:
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def acquire(data_dir: Path, app_version: str | None = None) -> dict:
    """
    Acquire the runtime lock for data_dir.

    Returns one of:
      {"owned": True, "conflict": None, "stale": False}
        — lock acquired cleanly.
      {"owned": True, "conflict": {...}, "stale": True}
        — stale lock from a dead process recovered; lock acquired.
      {"owned": False, "conflict": {...}, "stale": False}
        — a live process already holds the lock for this directory.
    """
    global _lock_path, _lock_owned, _conflict_info, _stale_recovered

    lock_path = data_dir / _LOCK_FILENAME
    _lock_path = lock_path

    existing = _read_lock_file(lock_path)
    conflict: dict | None = None
    stale = False

    if existing is not None:
        other_pid = existing.get("pid")
        if other_pid is not None and int(other_pid) != os.getpid():
            if _pid_alive(int(other_pid)):
                # Another live process holds this data directory.
                _conflict_info = existing
                _lock_owned = False
                return {"owned": False, "conflict": existing, "stale": False}
            else:
                # PID is dead — stale lock; we can take over.
                stale = True
                conflict = existing
                _stale_recovered = True

    lock_data = {
        "pid": os.getpid(),
        "runtime_mode": _runtime_mode_label(),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_dir": str(data_dir),
        "db_path": str(data_dir / "db" / "cvm_financials.db"),
        "app_version": app_version or "unknown",
    }
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")
    except Exception:
        pass  # Best-effort; non-fatal.

    _lock_owned = True
    _conflict_info = conflict if stale else None
    return {"owned": True, "conflict": conflict, "stale": stale}


def release() -> None:
    """Delete the lock file if this process owns it."""
    global _lock_owned
    if _lock_path is not None and _lock_owned:
        try:
            _lock_path.unlink(missing_ok=True)
        except Exception:
            pass
    _lock_owned = False


def get_status() -> dict:
    """Return a serialisable snapshot of the current lock state."""
    if _lock_owned:
        return {
            "status": "locked_by_self",
            "stale_recovered": _stale_recovered,
            "stale_pid": (
                _conflict_info.get("pid") if _stale_recovered and _conflict_info else None
            ),
        }
    if _conflict_info:
        other_pid = _conflict_info.get("pid")
        if other_pid and _pid_alive(int(other_pid)):
            return {
                "status": "locked_by_other",
                "pid": other_pid,
                "runtime_mode": _conflict_info.get("runtime_mode"),
                "started_at": _conflict_info.get("started_at"),
            }
        return {
            "status": "stale_recovered",
            "pid": other_pid,
            "runtime_mode": _conflict_info.get("runtime_mode"),
        }
    return {"status": "no_lock"}
