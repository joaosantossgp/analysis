from __future__ import annotations

import sys

import pytest

from desktop.bridge import CVMBridge
from src.contracts import HealthSnapshot


def _make_bridge(fake_svc) -> CVMBridge:
    bridge = CVMBridge()
    bridge._service = fake_svc
    return bridge


def _make_health_snapshot() -> HealthSnapshot:
    return HealthSnapshot(
        generated_at=None,
        start_year=2020,
        end_year=2024,
        total_cells=100,
        completed_cells=70,
        missing_cells=30,
        pct=70.0,
        health_score=70.0,
        health_status="partial",
        eta_hours=None,
        throughput_per_hour=None,
        throughput_confidence="low",
        per_year=(),
        prioritized_companies=(),
        raw={},
    )


class FakeReadService:
    def __init__(self, health_snapshot: HealthSnapshot | None = None):
        self.view_calls: list[int] = []
        self._health_snapshot = health_snapshot
        self.force_refresh_received: bool | None = None

    def record_company_view(self, cd_cvm: int) -> None:
        self.view_calls.append(cd_cvm)

    def get_health_snapshot(self, *, start_year: int, end_year: int, force_refresh: bool = False) -> HealthSnapshot:
        self.force_refresh_received = force_refresh
        assert self._health_snapshot is not None
        return self._health_snapshot


# ---------------------------------------------------------------------------
# track_company_view
# ---------------------------------------------------------------------------

def test_track_view_writes_in_normal_dev(monkeypatch):
    monkeypatch.delenv("CVMANALYTICS_USE_RELEASE_DATA", raising=False)
    svc = FakeReadService()
    bridge = _make_bridge(svc)

    result = bridge.track_company_view({"cd_cvm": 9512})

    assert result == {"ok": True}
    assert svc.view_calls == [9512]


def test_track_view_skips_in_readonly_release_data(monkeypatch):
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.delenv("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", raising=False)
    monkeypatch.delenv("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", raising=False)
    svc = FakeReadService()
    bridge = _make_bridge(svc)

    result = bridge.track_company_view({"cd_cvm": 9512})

    assert result["ok"] is True
    assert result.get("skipped") is True
    assert result.get("reason") == "read_only"
    assert svc.view_calls == []


def test_track_view_writes_when_release_data_writes_allowed(monkeypatch):
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.setenv("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", "1")
    monkeypatch.delenv("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", raising=False)
    svc = FakeReadService()
    bridge = _make_bridge(svc)

    result = bridge.track_company_view({"cd_cvm": 9512})

    assert result == {"ok": True}
    assert svc.view_calls == [9512]


def test_track_view_skips_when_concurrent_lock(monkeypatch):
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.setenv("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", "1")
    monkeypatch.setenv("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", "1")
    svc = FakeReadService()
    bridge = _make_bridge(svc)

    result = bridge.track_company_view({"cd_cvm": 9512})

    assert result["ok"] is True
    assert result.get("skipped") is True
    assert svc.view_calls == []


def test_track_view_zero_cdcvm_is_noop(monkeypatch):
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.delenv("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", raising=False)
    svc = FakeReadService()
    bridge = _make_bridge(svc)

    result = bridge.track_company_view({"cd_cvm": 0})

    assert result == {"ok": True}
    assert svc.view_calls == []


def test_track_view_writes_in_release_build(monkeypatch):
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.delenv("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    svc = FakeReadService()
    bridge = _make_bridge(svc)

    result = bridge.track_company_view({"cd_cvm": 9512})

    assert result == {"ok": True}
    assert svc.view_calls == [9512]


# ---------------------------------------------------------------------------
# get_base_health — force_refresh=True must not be blocked in read-only mode
# (get_health_snapshot is purely in-memory; no disk writes occur)
# ---------------------------------------------------------------------------

def test_get_base_health_force_refresh_not_blocked_in_readonly(monkeypatch):
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.delenv("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", raising=False)
    monkeypatch.delenv("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", raising=False)
    svc = FakeReadService(health_snapshot=_make_health_snapshot())
    bridge = _make_bridge(svc)

    result = bridge.get_base_health({"start_year": 2020, "end_year": 2024, "force_refresh": True})

    assert "error" not in result
    assert result.get("pct") == pytest.approx(70.0)
    assert svc.force_refresh_received is True


def test_get_base_health_force_refresh_works_in_normal_dev(monkeypatch):
    monkeypatch.delenv("CVMANALYTICS_USE_RELEASE_DATA", raising=False)
    svc = FakeReadService(health_snapshot=_make_health_snapshot())
    bridge = _make_bridge(svc)

    result = bridge.get_base_health({"start_year": 2020, "end_year": 2024, "force_refresh": True})

    assert "error" not in result
    assert result.get("pct") == pytest.approx(70.0)
    assert svc.force_refresh_received is True
