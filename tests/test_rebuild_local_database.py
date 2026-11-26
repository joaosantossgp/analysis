from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.financials.read_service as read_service_module
from desktop.bridge import CVMBridge
from src.companies.universe import CompanyUniverseEntry, CompanyUniverseSelection
from src.platform.settings import build_settings


@pytest.fixture
def sandbox_bridge(tmp_path, monkeypatch):
    """Bridge on a real SQLite file inside tmp_path; never the analyst's runtime folder."""
    monkeypatch.delenv("CVMANALYTICS_USE_RELEASE_DATA", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = build_settings(project_root=tmp_path)
    assert Path(settings.paths.db_path).is_relative_to(tmp_path)
    Path(settings.paths.db_path).parent.mkdir(parents=True, exist_ok=True)
    real_service = read_service_module.CVMReadService
    # The rebuild drops the bridge's service; the next one must stay in the sandbox.
    monkeypatch.setattr(read_service_module, "CVMReadService", lambda: real_service(settings=settings))
    bridge = CVMBridge()
    bridge._service = real_service(settings=settings)
    bridge._refresh_manager = SimpleNamespace(get_refresh_status=lambda _params: {"items": []})
    return bridge, settings


def _ignored_rows(db_path):
    with sqlite3.connect(str(db_path)) as conn:
        return conn.execute(
            "SELECT cd_cvm, ignored, ignored_reason FROM company_refresh_status WHERE ignored = 1 ORDER BY cd_cvm"
        ).fetchall()


def test_rebuild_backs_up_and_keeps_ignore_flags(sandbox_bridge):
    bridge, settings = sandbox_bridge
    assert bridge.set_company_ignored({"cd_cvm": 9512, "ignored": True, "reason": "Delisted"})["ok"]
    assert bridge.set_company_ignored({"cd_cvm": 4170, "ignored": True})["ok"]
    assert bridge.set_company_ignored({"cd_cvm": 1023, "ignored": False})["ok"]

    result = bridge.reset_local_database({"action": "recreate_local", "confirm": "REBUILD"})

    assert result["ok"], result
    backup_dir = Path(result["backup_path"])
    assert backup_dir.is_relative_to(Path(settings.paths.data_dir))
    backup_db = backup_dir / Path(settings.paths.db_path).name
    assert backup_db.exists()
    assert _ignored_rows(backup_db) == [(4170, 1, None), (9512, 1, "Delisted")]
    assert _ignored_rows(settings.paths.db_path) == [(4170, 1, None), (9512, 1, "Delisted")]
    with sqlite3.connect(str(settings.paths.db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM company_refresh_status").fetchone()[0] == 2


def test_rebuild_requires_typed_confirmation(sandbox_bridge):
    bridge, settings = sandbox_bridge
    bridge.set_company_ignored({"cd_cvm": 9512, "ignored": True})

    result = bridge.reset_local_database({"action": "recreate_local", "confirm": "rebuild"})

    assert result["ok"] is False
    assert "REBUILD" in result["error"]
    assert not (Path(settings.paths.data_dir) / "backup").exists()


def test_restart_current_reset_is_no_longer_offered(sandbox_bridge):
    bridge, _settings = sandbox_bridge

    result = bridge.reset_local_database({"action": "restart_current", "confirm": "RESET"})

    assert result["ok"] is False
    assert result["error"] == "Invalid reset action."


class _Onboarding:
    def get_company_universe_by_preset(self, preset, *, refresh_catalog=False):
        entry = CompanyUniverseEntry(
            cd_cvm=9512, ticker="PETR4", company_name="PETROBRAS", market_cap=None,
            market_cap_rank=None, source="cvm_company_catalog", source_date=None,
        )
        return CompanyUniverseSelection(preset=preset, entries=(entry,), source="cvm_company_catalog", source_date=None)


class _Manager:
    params = None

    def request_refresh(self, params):
        self.params = params
        return {"status": "running", "job_id": "job-1"}


def test_history_range_preference_drives_the_data_update_and_survives_rebuild(sandbox_bridge):
    bridge, _settings = sandbox_bridge
    end_year = datetime.now(timezone.utc).year
    current = bridge.get_data_update_settings({})
    saved = bridge.save_data_update_settings({**current, "start_year": end_year - 9, "end_year": end_year})
    assert "error" not in saved, saved

    assert bridge.reset_local_database({"action": "recreate_local", "confirm": "REBUILD"})["ok"]
    assert bridge.get_data_update_settings({})["start_year"] == end_year - 9

    manager = _Manager()
    bridge._onboarding_service = _Onboarding()
    bridge._refresh_manager = manager
    bridge.start_data_update({})

    assert (manager.params["start_year"], manager.params["end_year"]) == (end_year - 9, end_year)


def test_history_range_rolls_forward_into_a_new_year(sandbox_bridge):
    bridge, _settings = sandbox_bridge
    year = datetime.now(timezone.utc).year
    # A "last 5 years" range saved last year must cover this year now.
    bridge._write_app_settings({**bridge.get_data_update_settings({}), "start_year": year - 5, "end_year": year - 1})
    resolved = bridge.get_data_update_settings({})
    assert (resolved["start_year"], resolved["end_year"]) == (year - 4, year)


def test_since_2010_history_stays_anchored_at_2010(sandbox_bridge):
    bridge, _settings = sandbox_bridge
    year = datetime.now(timezone.utc).year
    bridge._write_app_settings({**bridge.get_data_update_settings({}), "start_year": 2010, "end_year": year - 1})
    resolved = bridge.get_data_update_settings({})
    assert (resolved["start_year"], resolved["end_year"]) == (2010, year)
