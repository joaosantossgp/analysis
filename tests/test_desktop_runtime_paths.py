from __future__ import annotations

from os import environ
from pathlib import Path
from unittest.mock import patch

from desktop import app


def test_configure_bundled_data_paths_points_sqlite_to_runtime_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exe_path = tmp_path / "CVMAnalytics.exe"
    exe_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app.sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
    monkeypatch.setattr(app.sys, "executable", str(exe_path))

    with patch.dict(environ, {}, clear=True):
        app._configure_bundled_data_paths()

        assert Path(app.os.environ["CVM_DATA_DIR"]) == tmp_path / "data"
        assert Path(app.os.environ["CVM_DB_DIR"]) == tmp_path / "data" / "db"
        assert (
            Path(app.os.environ["SQLITE_PATH"])
            == tmp_path / "data" / "db" / "cvm_financials.db"
        )
        assert Path(app.os.environ["CVM_OUTPUT_DIR"]) == tmp_path / "output"
        assert Path(app.os.environ["CVM_LOG_DIR"]) == tmp_path / "output" / "logs"


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
