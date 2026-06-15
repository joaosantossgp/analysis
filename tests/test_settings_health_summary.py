from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from desktop.bridge import CVMBridge
from src.platform.settings import build_settings


def _seed_minimal_cvm_db(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE companies (cd_cvm INTEGER PRIMARY KEY, company_name TEXT)")
        conn.execute(
            'CREATE TABLE financial_reports ("CD_CVM" INTEGER, "REPORT_YEAR" INTEGER, "PERIOD_LABEL" TEXT)'
        )
        conn.execute(
            """
            CREATE TABLE company_refresh_status (
                cd_cvm INTEGER PRIMARY KEY,
                last_success_at TEXT,
                last_attempt_at TEXT,
                last_error TEXT
            )
            """
        )
        conn.execute("INSERT INTO companies VALUES (9512, 'PETROBRAS')")
        conn.execute("INSERT INTO financial_reports VALUES (9512, 2025, '2025')")
        conn.execute(
            "INSERT INTO company_refresh_status VALUES (9512, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', NULL)"
        )


def test_settings_health_summary_uses_fast_summary_path(tmp_path, monkeypatch):
    settings = build_settings(project_root=tmp_path)
    _seed_minimal_cvm_db(settings.paths.db_path)
    bridge = CVMBridge()
    bridge._service = SimpleNamespace(settings=settings)

    bridge._get_refresh_status_light = lambda _params: {"items": []}
    bridge.get_energy_kpi_health = lambda _params: {
        "last_refresh_at": None,
        "last_refresh_status": None,
        "rows_ingested": 0,
        "rows_conflict": 0,
        "is_stale": False,
        "owid_snapshot_id": None,
        "owid_fetched_at": None,
        "dq_errors": 0,
        "dq_warnings": 0,
        "refresh_running": False,
        "refresh_error": None,
    }
    bridge.get_sin_kpi_health = lambda _params: {
        "last_refresh_at": None,
        "last_refresh_status": None,
        "rows_ingested": 0,
        "latest_reference_datetime": None,
        "is_stale": False,
        "dq_errors": 0,
        "dq_warnings": 0,
        "refresh_running": False,
        "refresh_error": None,
    }
    bridge._plant_parcel_refresh_status = lambda: {"status": "idle", "error": None}
    bridge._dist_refresh_status = lambda: {"status": "idle", "error": None}
    bridge.get_data_coverage = lambda _params=None: (_ for _ in ()).throw(
        AssertionError("get_data_coverage must not run on Settings overview")
    )
    bridge.get_distribution_health = lambda _params=None: (_ for _ in ()).throw(
        AssertionError("get_distribution_health must not run on Settings overview")
    )
    monkeypatch.delenv("CVMANALYTICS_USE_RELEASE_DATA", raising=False)
    monkeypatch.delenv("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", raising=False)

    payload = bridge.get_settings_health_summary({})

    assert payload["summary"]["initial_bridge_calls"] == 1
    assert payload["summary"]["full_table_scans"] is False
    assert "get_data_coverage" in payload["summary"]["deferred_detail_contracts"]
    assert "get_distribution_health" in payload["summary"]["deferred_detail_contracts"]
    assert payload["overall_status"] in {"healthy", "degraded", "unknown"}
    required = {row["id"]: row for row in payload["segments"] if row["required"]}
    assert required["cvm_registry"]["status"] == "healthy"
    assert required["cvm_financials"]["status"] == "healthy"
