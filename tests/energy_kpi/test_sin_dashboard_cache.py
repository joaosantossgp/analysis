"""Bridge cache tests for the SIN dashboard payload contract."""
from __future__ import annotations

import json
from types import SimpleNamespace

from desktop.bridge import CVMBridge


class _Dashboard:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def to_dict(self) -> dict:
        return self._payload


class _EnergyService:
    def __init__(self, payload: dict) -> None:
        self.calls = 0
        self._payload = payload

    def get_sin_kpi_dashboard(self):
        self.calls += 1
        return _Dashboard(self._payload)


def test_sin_dashboard_cache_schema_rebuilds_old_payload_shape(tmp_path, monkeypatch):
    bridge = CVMBridge()
    assert bridge.SIN_DASHBOARD_CACHE_SCHEMA_VERSION == 2

    settings = SimpleNamespace(
        paths=SimpleNamespace(
            cache_dir=tmp_path,
            energy_kpi_db_path=tmp_path / "energy_kpis.db",
        )
    )
    old_signature = [
        "sin_dashboard",
        1,
        bridge._sin_dashboard_cache_signature(settings)[2],
        bridge._sqlite_signature(settings.paths.energy_kpi_db_path),
    ]
    (tmp_path / "sin_kpi_dashboard_v1.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "signature": old_signature,
                "payload": {
                    "last_successful_update": None,
                    "latest_reference_datetime": None,
                    "is_empty": True,
                    "is_stale": False,
                    "observations": [],
                    "source_statuses": [
                        {
                            "source": "CCEE",
                            "dataset": "pld_horario",
                            "frequency": "hourly",
                            "last_snapshot_at": None,
                            "local_records_count": 0,
                            "last_status": "partial",
                            "last_error": None,
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    new_payload = {
        "last_successful_update": None,
        "latest_reference_datetime": None,
        "is_empty": True,
        "is_stale": False,
        "observations": [],
        "source_statuses": [
            {
                "source": "CCEE",
                "dataset": "pld_horario",
                "frequency": "hourly",
                "last_snapshot_at": None,
                "local_records_count": 0,
                "last_status": "failed",
                "last_error": "HTTP 403 Forbidden",
                "latest_reference_datetime": None,
                "latest_successful_snapshot_at": None,
                "latest_attempt_at": "2026-07-10T01:05:00+00:00",
                "latest_attempt_status": "failed",
                "latest_failure_at": "2026-07-10T01:05:00+00:00",
                "health_state": "failed",
                "is_missing": False,
                "is_stale": False,
            }
        ],
    }
    service = _EnergyService(new_payload)
    bridge._energy_read_service = service
    monkeypatch.setattr("src.platform.settings.get_settings", lambda: settings)

    result = bridge.get_sin_kpi_dashboard()

    assert service.calls == 1
    assert result["source_statuses"][0]["health_state"] == "failed"
    assert result["source_statuses"][0]["latest_attempt_status"] == "failed"
    assert result["source_statuses"][0]["last_error"] == "HTTP 403 Forbidden"
    assert (tmp_path / "sin_kpi_dashboard_v2.json").exists()
