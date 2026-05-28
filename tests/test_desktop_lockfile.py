from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from desktop import lockfile


@pytest.fixture(autouse=True)
def reset_lockfile_state():
    """Reset module-level state between tests."""
    yield
    lockfile._lock_path = None
    lockfile._lock_owned = False
    lockfile._conflict_info = None
    lockfile._stale_recovered = False


def test_acquire_clean(tmp_path: Path) -> None:
    result = lockfile.acquire(tmp_path, app_version="1.0.0")

    assert result["owned"] is True
    assert result["stale"] is False
    assert result["conflict"] is None

    lock_file = tmp_path / "runtime.lock"
    assert lock_file.exists()
    data = json.loads(lock_file.read_text())
    assert data["pid"] == os.getpid()
    assert data["app_version"] == "1.0.0"


def test_acquire_stale_lock_recovered(tmp_path: Path) -> None:
    dead_pid = 999_999_999
    stale_data = {
        "pid": dead_pid,
        "runtime_mode": "dev-isolated",
        "started_at": "2024-01-01T00:00:00+00:00",
        "data_dir": str(tmp_path),
        "db_path": str(tmp_path / "db" / "cvm_financials.db"),
        "app_version": "0.99.0",
    }
    (tmp_path / "runtime.lock").write_text(json.dumps(stale_data), encoding="utf-8")

    with patch.object(lockfile, "_pid_alive", return_value=False):
        result = lockfile.acquire(tmp_path)

    assert result["owned"] is True
    assert result["stale"] is True
    assert result["conflict"]["pid"] == dead_pid

    lock_file = tmp_path / "runtime.lock"
    assert lock_file.exists()
    current = json.loads(lock_file.read_text())
    assert current["pid"] == os.getpid()


def test_acquire_live_conflict(tmp_path: Path) -> None:
    other_pid = 12345
    live_data = {
        "pid": other_pid,
        "runtime_mode": "release",
        "started_at": "2024-01-01T00:00:00+00:00",
        "data_dir": str(tmp_path),
        "db_path": str(tmp_path / "db" / "cvm_financials.db"),
        "app_version": "0.23.0",
    }
    (tmp_path / "runtime.lock").write_text(json.dumps(live_data), encoding="utf-8")

    with patch.object(lockfile, "_pid_alive", return_value=True):
        result = lockfile.acquire(tmp_path)

    assert result["owned"] is False
    assert result["stale"] is False
    assert result["conflict"]["pid"] == other_pid


def test_release_removes_lock_file(tmp_path: Path) -> None:
    lockfile.acquire(tmp_path)
    lock_file = tmp_path / "runtime.lock"
    assert lock_file.exists()

    lockfile.release()

    assert not lock_file.exists()
    assert lockfile._lock_owned is False


def test_release_noop_when_not_owned(tmp_path: Path) -> None:
    # Should not raise even if no lock was acquired
    lockfile.release()


def test_get_status_locked_by_self(tmp_path: Path) -> None:
    lockfile.acquire(tmp_path)
    status = lockfile.get_status()

    assert status["status"] == "locked_by_self"
    assert status["stale_recovered"] is False


def test_get_status_stale_recovered(tmp_path: Path) -> None:
    dead_pid = 999_999_999
    stale_data = {"pid": dead_pid, "runtime_mode": "dev-isolated"}
    (tmp_path / "runtime.lock").write_text(json.dumps(stale_data), encoding="utf-8")

    with patch.object(lockfile, "_pid_alive", return_value=False):
        lockfile.acquire(tmp_path)

    status = lockfile.get_status()
    assert status["status"] == "locked_by_self"
    assert status["stale_recovered"] is True
    assert status["stale_pid"] == dead_pid


def test_get_status_no_lock() -> None:
    status = lockfile.get_status()
    assert status["status"] == "no_lock"


def test_acquire_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested"
    result = lockfile.acquire(nested)

    assert result["owned"] is True
    assert (nested / "runtime.lock").exists()
