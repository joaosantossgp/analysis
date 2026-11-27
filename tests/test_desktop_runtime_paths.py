from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from os import environ
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from desktop import app, dev_data, lockfile


def test_stop_vite_dev_server_uses_taskkill_for_the_windows_process_tree(
) -> None:
    proc = Mock(pid=4242)

    with patch.object(app.subprocess, "run") as run:
        with patch.object(app.os, "name", "nt"):
            app._stop_vite_dev_server(proc)

    run.assert_called_once_with(
        ["taskkill", "/PID", "4242", "/T", "/F"],
        check=False,
        stdout=app.subprocess.DEVNULL,
        stderr=app.subprocess.DEVNULL,
    )
    proc.terminate.assert_not_called()


def test_stop_vite_dev_server_terminates_and_waits_on_non_windows(
) -> None:
    proc = Mock()

    with patch.object(app.os, "name", "posix"):
        app._stop_vite_dev_server(proc)

    proc.terminate.assert_called_once_with()
    proc.wait.assert_called_once_with(timeout=5)
    proc.kill.assert_not_called()


def test_stop_vite_dev_server_kills_after_non_windows_wait_timeout(
) -> None:
    proc = Mock()
    proc.wait.side_effect = app.subprocess.TimeoutExpired("vite", 5)

    with patch.object(app.os, "name", "posix"):
        app._stop_vite_dev_server(proc)

    proc.terminate.assert_called_once_with()
    proc.wait.assert_called_once_with(timeout=5)
    proc.kill.assert_called_once_with()


def test_configure_dev_data_paths_defaults_to_the_checkout_dev_data_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(app.sys, "frozen", False, raising=False)
    monkeypatch.setattr(app, "_repo_root", lambda: tmp_path / "repo")

    with patch.dict(environ, {"USERPROFILE": str(tmp_path)}, clear=True):
        app._configure_bundled_data_paths()

        data_root = tmp_path / "repo" / "data" / "dev-runtime"
        assert Path(app.os.environ["CVM_DATA_DIR"]) == data_root
        assert Path(app.os.environ["CVM_DB_DIR"]) == data_root / "db"
        assert Path(app.os.environ["SQLITE_PATH"]) == data_root / "db" / "cvm_financials.db"
        assert Path(app.os.environ["CVM_NEWS_DB"]) == data_root / "db" / "news.db"
        assert "CVMANALYTICS_USE_RELEASE_DATA" not in app.os.environ


def test_configure_dev_data_paths_provisions_sqlite_parent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(app.sys, "frozen", False, raising=False)
    monkeypatch.setattr(app, "_repo_root", lambda: tmp_path / "repo")

    with patch.dict(environ, {"USERPROFILE": str(tmp_path)}, clear=True):
        app._configure_bundled_data_paths()
        app._ensure_db_initialized()

        db_path = Path(app.os.environ["SQLITE_PATH"])
        with sqlite3.connect(str(db_path)) as conn:
            assert conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'companies'"
            ).fetchone() == ("companies",)


def test_ensure_db_initialized_creates_db_in_an_empty_explicit_data_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    # A fresh CVM_DATA_DIR has no db/ folder, and SQLite cannot create a file there.
    explicit_data = tmp_path / "fresh"
    explicit_data.mkdir()
    monkeypatch.setattr(app.sys, "frozen", False, raising=False)

    with patch.dict(environ, {"USERPROFILE": str(tmp_path), "CVM_DATA_DIR": str(explicit_data)}, clear=True):
        app._configure_bundled_data_paths()
        app._ensure_db_initialized()

    with sqlite3.connect(str(explicit_data / "db" / "cvm_financials.db")) as conn:
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'companies'"
        ).fetchone() == ("companies",)
    assert not (explicit_data / "recovery.log").exists()


def test_configure_dev_data_paths_preserves_explicit_data_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    explicit_data = tmp_path / "isolated"
    monkeypatch.setattr(app.sys, "frozen", False, raising=False)

    with patch.dict(environ, {"USERPROFILE": str(tmp_path), "CVM_DATA_DIR": str(explicit_data)}, clear=True):
        app._configure_bundled_data_paths()

        assert Path(app.os.environ["CVM_DATA_DIR"]) == explicit_data
        assert "CVMANALYTICS_USE_RELEASE_DATA" not in app.os.environ


def test_configure_bundled_data_paths_points_sqlite_to_documents_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exe_path = tmp_path / "CVMAnalytics.exe"
    exe_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    monkeypatch.setattr(app.sys, "executable", str(exe_path))

    with patch.dict(environ, {"USERPROFILE": str(tmp_path)}, clear=True):
        app._configure_bundled_data_paths()

        data_root = tmp_path / "Documents" / "CVMAnalytics"
        assert Path(app.os.environ["CVM_DATA_DIR"]) == data_root
        assert Path(app.os.environ["CVM_DB_DIR"]) == data_root / "db"
        assert (
            Path(app.os.environ["SQLITE_PATH"])
            == data_root / "db" / "cvm_financials.db"
        )
        assert Path(app.os.environ["CVM_NEWS_DB"]) == data_root / "db" / "news.db"
        assert Path(app.os.environ["CVM_OUTPUT_DIR"]) == data_root / "output"
        assert Path(app.os.environ["CVM_LOG_DIR"]) == data_root / "logs"


def test_configure_bundled_data_paths_does_not_override_explicit_sqlite_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    explicit_db = tmp_path / "custom.db"
    exe_path = tmp_path / "CVMAnalytics.exe"
    exe_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    monkeypatch.setattr(app.sys, "executable", str(exe_path))

    with patch.dict(environ, {"SQLITE_PATH": str(explicit_db)}, clear=True):
        app._configure_bundled_data_paths()

        assert Path(app.os.environ["SQLITE_PATH"]) == explicit_db


@pytest.fixture
def worktree_of_main(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    """Source dev mode launched from a git worktree of `tmp_path / "main"`."""
    main = tmp_path / "main"
    worktree = main / ".claude" / "worktrees" / "feature"
    worktree.mkdir(parents=True)
    monkeypatch.setattr(app.sys, "frozen", False, raising=False)
    monkeypatch.setattr(app, "_repo_root", lambda: worktree)
    monkeypatch.setattr(dev_data, "main_checkout", lambda _repo_root: main)
    return main, worktree


def test_worktree_dev_mode_uses_shared_dev_data(worktree_of_main, tmp_path: Path) -> None:
    main, _ = worktree_of_main
    shared_root = main / "data" / "dev-runtime"

    with patch.dict(environ, {"USERPROFILE": str(tmp_path)}, clear=True):
        app._configure_bundled_data_paths()

        assert Path(app.os.environ["CVM_DATA_DIR"]) == shared_root
        assert Path(app.os.environ["SQLITE_PATH"]) == shared_root / "db" / "cvm_financials.db"
        assert "CVM_INPUT_DIR" not in app.os.environ


def test_data_sensitive_worktree_uses_isolated_dev_data_and_shared_downloads(
    worktree_of_main,
    tmp_path: Path,
) -> None:
    main, worktree = worktree_of_main
    (worktree / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")
    own_root = worktree / "data" / "dev-runtime"

    with patch.dict(environ, {"USERPROFILE": str(tmp_path)}, clear=True):
        app._configure_bundled_data_paths()

        assert Path(app.os.environ["CVM_DATA_DIR"]) == own_root
        assert Path(app.os.environ["SQLITE_PATH"]) == own_root / "db" / "cvm_financials.db"
        assert Path(app.os.environ["CVM_INPUT_DIR"]) == main / "data" / "dev-runtime" / "input"


def test_full_copy_worktree_shares_nothing(worktree_of_main, tmp_path: Path) -> None:
    _, worktree = worktree_of_main
    (worktree / dev_data.MARKER_NAME).write_text("full-copy\n", encoding="utf-8")

    with patch.dict(environ, {"USERPROFILE": str(tmp_path)}, clear=True):
        app._configure_bundled_data_paths()

        assert Path(app.os.environ["CVM_DATA_DIR"]) == worktree / "data" / "dev-runtime"
        assert "CVM_INPUT_DIR" not in app.os.environ


def test_explicit_path_overrides_win_over_worktree_dev_data(worktree_of_main, tmp_path: Path) -> None:
    _, worktree = worktree_of_main
    (worktree / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")
    explicit_data = tmp_path / "explicit"
    explicit_db = tmp_path / "custom.db"

    with patch.dict(environ, {"USERPROFILE": str(tmp_path), "CVM_DATA_DIR": str(explicit_data)}, clear=True):
        app._configure_bundled_data_paths()

        assert Path(app.os.environ["CVM_DATA_DIR"]) == explicit_data
        assert "CVM_INPUT_DIR" not in app.os.environ

    with patch.dict(
        environ,
        {"USERPROFILE": str(tmp_path), "SQLITE_PATH": str(explicit_db), "CVM_INPUT_DIR": str(tmp_path / "in")},
        clear=True,
    ):
        app._configure_bundled_data_paths()

        assert Path(app.os.environ["SQLITE_PATH"]) == explicit_db
        assert Path(app.os.environ["CVM_INPUT_DIR"]) == tmp_path / "in"


def test_installed_app_data_mode_wins_over_worktree_dev_data(worktree_of_main, tmp_path: Path) -> None:
    _, worktree = worktree_of_main
    (worktree / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")

    with patch.dict(
        environ,
        {"USERPROFILE": str(tmp_path), "CVMANALYTICS_USE_RELEASE_DATA": "1"},
        clear=True,
    ):
        app._configure_bundled_data_paths()

        assert Path(app.os.environ["CVM_DATA_DIR"]) == tmp_path / "Documents" / "CVMAnalytics"
        assert app.os.environ["CVMANALYTICS_USE_RELEASE_DATA"] == "1"
        assert "CVM_INPUT_DIR" not in app.os.environ


def test_runtime_lock_follows_shared_dev_data(worktree_of_main, monkeypatch, tmp_path: Path) -> None:
    main, _ = worktree_of_main
    shared_root = main / "data" / "dev-runtime"
    monkeypatch.setattr(lockfile, "_lock_path", None)
    monkeypatch.setattr(lockfile, "_lock_owned", False)
    monkeypatch.setattr(lockfile, "_conflict_info", None)
    monkeypatch.setattr(lockfile, "_stale_recovered", False)

    with patch.dict(environ, {"USERPROFILE": str(tmp_path)}, clear=True):
        app._configure_bundled_data_paths()
        assert app._runtime_lock_dir() == shared_root

        # Dev mode already running from the main checkout holds the same lock.
        (shared_root / "runtime.lock").write_text('{"pid": 1, "runtime_mode": "dev"}', encoding="utf-8")
        with patch.object(lockfile, "_pid_alive", return_value=True):
            result = lockfile.acquire(app._runtime_lock_dir())

    assert result["owned"] is False
    assert result["conflict"]["pid"] == 1


def test_runtime_lock_of_a_data_sensitive_worktree_is_its_own(worktree_of_main, tmp_path: Path) -> None:
    _, worktree = worktree_of_main
    (worktree / dev_data.MARKER_NAME).write_text("isolated\n", encoding="utf-8")

    with patch.dict(environ, {"USERPROFILE": str(tmp_path)}, clear=True):
        app._configure_bundled_data_paths()

        assert app._runtime_lock_dir() == worktree / "data" / "dev-runtime"


_CATALOG_CSV = (
    "CD_CVM;DENOM_SOCIAL;DENOM_COMERC;CNPJ_CIA;SETOR_ATIV;SIT\n"
    "9512;PETROBRAS;PETROBRAS;33.000.167/0001-01;Petroleo;ATIVO\n"
)


def _seed_enrichment_data(data_root: Path) -> Path:
    """A company missing its CNPJ plus local catalog evidence that has it."""
    db_path = data_root / "db" / "cvm_financials.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("CREATE TABLE companies (cd_cvm INTEGER PRIMARY KEY, cnpj TEXT)")
        conn.execute("INSERT INTO companies VALUES (9512, NULL)")
    snapshot = data_root / "metadata" / "cvm_company_catalog.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "source_url": "fixture", "downloaded_at": "2026-01-01T00:00:00+00:00", "csv": _CATALOG_CSV}
    snapshot.write_text(json.dumps(payload), encoding="utf-8")
    return db_path


def _enriched_cnpj(db_path: Path) -> str | None:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute("SELECT cnpj FROM companies WHERE cd_cvm = 9512").fetchone()[0]


def _run_local_metadata_enrichment() -> None:
    with patch.object(lockfile, "get_status", return_value={"status": "locked_by_self"}), patch("time.sleep"):
        app._background_local_metadata_enrichment()


@pytest.mark.parametrize("explicit_data_dir", [False, True], ids=["shared-dev-data", "cvm-data-dir"])
def test_local_metadata_enrichment_in_source_mode_uses_the_active_dev_database(
    worktree_of_main, tmp_path: Path, explicit_data_dir: bool
) -> None:
    # #664: a dev run must never write the installed app's Documents\CVMAnalytics database.
    profile = tmp_path / "profile"
    installed_root = profile / "Documents" / "CVMAnalytics"
    installed_db = _seed_enrichment_data(installed_root)
    installed_bytes = installed_db.read_bytes()
    env = {"USERPROFILE": str(profile)}
    if explicit_data_dir:
        env["CVM_DATA_DIR"] = str(tmp_path / "explicit-data")

    with patch.dict(environ, env, clear=True):
        app._configure_bundled_data_paths()
        active_root = Path(app.os.environ["CVM_DATA_DIR"])
        assert installed_root not in (active_root, *active_root.parents)
        active_db = _seed_enrichment_data(active_root)
        _run_local_metadata_enrichment()

    assert _enriched_cnpj(active_db) == "33000167000101"
    assert installed_db.read_bytes() == installed_bytes


def test_local_metadata_enrichment_in_the_packaged_app_uses_the_documents_database(
    monkeypatch, tmp_path: Path
) -> None:
    exe_path = tmp_path / "CVMAnalytics.exe"
    exe_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    monkeypatch.setattr(app.sys, "executable", str(exe_path))
    profile = tmp_path / "profile"
    installed_db = _seed_enrichment_data(profile / "Documents" / "CVMAnalytics")

    with patch.dict(environ, {"USERPROFILE": str(profile)}, clear=True):
        app._configure_bundled_data_paths()
        _run_local_metadata_enrichment()

    assert _enriched_cnpj(installed_db) == "33000167000101"
