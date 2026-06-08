from __future__ import annotations

from os import environ
from pathlib import Path
from unittest.mock import patch

from desktop import app


def test_configure_dev_data_paths_defaults_to_documents_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(app.sys, "frozen", False, raising=False)

    with patch.dict(environ, {"USERPROFILE": str(tmp_path)}, clear=True):
        app._configure_bundled_data_paths()

        data_root = tmp_path / "Documents" / "CVMAnalytics"
        assert Path(app.os.environ["CVM_DATA_DIR"]) == data_root
        assert Path(app.os.environ["CVM_DB_DIR"]) == data_root / "db"
        assert Path(app.os.environ["SQLITE_PATH"]) == data_root / "db" / "cvm_financials.db"
        assert app.os.environ["CVMANALYTICS_USE_RELEASE_DATA"] == "1"


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
