from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from apps.api.app.services.refresh_jobs import ApiRefreshJobManager
from desktop.bridge import CVMBridge
from desktop.services import DesktopRefreshJobManager
from src.companies.universe import (
    CompanyUniverseEntry,
    CompanyUniverseSelection,
    CompanyUniverseUnavailableError,
)
from src.platform.contracts import CompanyRefreshResult, RefreshResult
from src.platform.settings import build_settings


class FakeReadService:
    def __init__(self, items=None, statuses=None, complete_years=None):
        self.items = items or [SimpleNamespace(cd_cvm=9512)]
        self.statuses = statuses or []
        self.complete_years = complete_years or {}
        self.calls = []

    def list_companies(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(items=tuple(self.items))

    def list_refresh_status(self):
        return tuple(self.statuses)

    def _load_complete_annual_years_map(self, cd_cvms, *, start_year, end_year):
        return {
            int(cd_cvm): tuple(
                int(year)
                for year in self.complete_years.get(int(cd_cvm), ())
                if int(start_year) <= int(year) <= int(end_year)
            )
            for cd_cvm in cd_cvms
        }


class FakeRefreshService:
    def __init__(self):
        self.requests = []

    def execute(
        self,
        request,
        *,
        progress_callback=None,
        stage_callback=None,
        should_cancel=None,
        persist_refresh_status=True,
    ):
        self.requests.append(request)
        if stage_callback is not None:
            stage_callback(
                SimpleNamespace(
                    stage="planning",
                    current=1,
                    total=1,
                    message="Planejamento concluido.",
                )
            )
        if progress_callback is not None:
            progress_callback(1, len(request.companies), f"Processando {request.companies[0]}")
        result = CompanyRefreshResult(
            company_name="PETROBRAS",
            cvm_code=int(request.companies[0]),
            requested_years=(2024,),
            years_processed=(2024,),
            rows_inserted=10,
            status="success",
            attempts=1,
        )
        return RefreshResult(
            request=request,
            companies=(result,),
            planning_stats={"planned_company_years": 1},
            synced_companies=1,
            cancelled=bool(should_cancel and should_cancel()),
        )


def _make_manager(tmp_path: Path, *, read_service=None, refresh_service=None, autostart=True):
    settings = build_settings(project_root=tmp_path)
    return DesktopRefreshJobManager(
        settings=settings,
        read_service=read_service or FakeReadService(),
        refresh_service=refresh_service or FakeRefreshService(),
        jobs_path=tmp_path / "data" / "refresh_jobs.json",
        autostart=autostart,
    )


def _wait_for_terminal(manager: DesktopRefreshJobManager, job_id: str):
    deadline = time.time() + 3
    while time.time() < deadline:
        status = manager.get_refresh_status({"job_id": job_id})
        if status["state"] in DesktopRefreshJobManager.TERMINAL_STATES:
            return status
        time.sleep(0.02)
    raise AssertionError("refresh job did not finish")


def test_request_refresh_dispatches_background_job_and_persists_status(tmp_path: Path):
    refresh_service = FakeRefreshService()
    manager = _make_manager(tmp_path, refresh_service=refresh_service)

    dispatch = manager.request_refresh({"mode": "missing", "sector_slug": "energia", "end_year": 2024})

    assert dispatch["status"] == "running"
    assert dispatch["job_id"]
    assert dispatch["queued"] == 1

    status = _wait_for_terminal(manager, dispatch["job_id"])
    assert status["state"] == "success"
    assert status["processed"] == 1
    assert status["failures"] == 0
    assert status["log_lines"]
    assert refresh_service.requests[0].companies == ("9512",)

    saved = json.loads((tmp_path / "data" / "refresh_jobs.json").read_text(encoding="utf-8"))
    assert saved["jobs"][0]["job_id"] == dispatch["job_id"]
    assert saved["jobs"][0]["state"] == "success"


def test_request_refresh_applies_sector_status_and_cvm_range_filters(tmp_path: Path):
    read_service = FakeReadService(
        items=[
            SimpleNamespace(cd_cvm=99),
            SimpleNamespace(cd_cvm=150),
            SimpleNamespace(cd_cvm=180),
            SimpleNamespace(cd_cvm=250),
        ],
        statuses=[
            SimpleNamespace(cd_cvm=150, tracking_state="error", last_status="error", latest_attempt_outcome="error"),
            SimpleNamespace(cd_cvm=180, tracking_state="success", last_status="success", latest_attempt_outcome="success"),
        ],
    )
    manager = _make_manager(tmp_path, read_service=read_service, autostart=False)

    dispatch = manager.request_refresh(
        {
            "mode": "missing",
            "sector_slug": "varejo",
            "status_filter": "failed",
            "cvm_range": "100-200",
            "start_year": 2023,
            "end_year": 2024,
        }
    )

    assert dispatch["status"] == "queued"
    assert dispatch["queued"] == 1
    assert read_service.calls[0]["sector_slug"] == "varejo"

    saved = json.loads((tmp_path / "data" / "refresh_jobs.json").read_text(encoding="utf-8"))
    assert saved["jobs"][0]["request"] == {
        "companies": ["150"],
        "start_year": 2023,
        "end_year": 2024,
    }


def test_api_and_desktop_batch_refresh_resolve_same_companies(tmp_path: Path):
    items = [
        SimpleNamespace(cd_cvm=100),
        SimpleNamespace(cd_cvm=150),
        SimpleNamespace(cd_cvm=180),
        SimpleNamespace(cd_cvm=250),
    ]
    statuses = [
        SimpleNamespace(
            cd_cvm=100,
            tracking_state="success",
            last_status="success",
            latest_attempt_outcome="success",
            freshness_summary_code="refresh_completed_readable",
            freshness_summary_severity="success",
            has_readable_current_data=True,
            latest_readable_year=2024,
            last_end_year=2024,
        ),
        SimpleNamespace(
            cd_cvm=150,
            tracking_state="success",
            last_status="success",
            latest_attempt_outcome="success",
            freshness_summary_code="mixed_no_new_data_readable",
            freshness_summary_severity="warning",
            has_readable_current_data=True,
            latest_readable_year=2023,
            last_end_year=2023,
        ),
        SimpleNamespace(
            cd_cvm=180,
            tracking_state="error",
            last_status="error",
            latest_attempt_outcome="error",
            is_retry_allowed=True,
            has_readable_current_data=True,
        ),
    ]
    params = {
        "mode": "outdated",
        "sector": "energia",
        "cvm_from": 100,
        "cvm_to": 200,
        "start_year": 2023,
        "end_year": 2024,
    }
    settings = build_settings(project_root=tmp_path)
    api_manager = ApiRefreshJobManager(
        settings=settings,
        read_service=FakeReadService(items=items, statuses=statuses),
        autostart=False,
    )
    desktop_manager = _make_manager(
        tmp_path,
        read_service=FakeReadService(items=items, statuses=statuses),
        autostart=False,
    )

    api_dispatch = api_manager.request_refresh(params)
    desktop_dispatch = desktop_manager.request_refresh(params)

    api_job = api_manager._jobs[str(api_dispatch["job_id"])]
    saved = json.loads((tmp_path / "data" / "refresh_jobs.json").read_text(encoding="utf-8"))
    desktop_job = saved["jobs"][0]
    assert api_dispatch["queued"] == desktop_dispatch["queued"] == 1
    assert api_job["request"] == desktop_job["request"] == {
        "companies": ["150"],
        "start_year": 2023,
        "end_year": 2024,
    }


def test_desktop_refresh_rejects_invalid_batch_range(tmp_path: Path):
    manager = _make_manager(tmp_path, autostart=False)

    dispatch = manager.request_refresh(
        {
            "mode": "full",
            "cvm_range": {"start": 300, "end": 100},
        }
    )

    assert dispatch["status"] == "error"
    assert dispatch["status_reason_code"] == "invalid_request"
    assert "cvm_range.start" in dispatch["message"]


def test_running_jobs_are_marked_interrupted_after_restart(tmp_path: Path):
    jobs_path = tmp_path / "data" / "refresh_jobs.json"
    jobs_path.parent.mkdir(parents=True)
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "job_id": "job-1",
                        "state": "running",
                        "queued": 1,
                        "processed": 0,
                        "failures": 0,
                        "log_lines": [],
                        "created_at": "2026-05-03T12:00:00",
                        "updated_at": "2026-05-03T12:00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    manager = _make_manager(tmp_path, autostart=False)

    status = manager.get_refresh_status({"job_id": "job-1"})
    assert status["state"] == "interrupted"
    assert "app closed" in status["error"]


def test_bridge_refresh_methods_delegate_to_manager():
    calls = []

    class FakeManager:
        def request_refresh(self, params):
            calls.append(("request", params))
            return {"status": "running", "job_id": "abc"}

        def get_refresh_status(self, params):
            calls.append(("status", params))
            return {"state": "running", "job_id": "abc"}

        def cancel_job(self, params):
            calls.append(("cancel", params))
            return {"ok": True}

    bridge = CVMBridge()
    bridge._refresh_manager = FakeManager()

    assert bridge.request_refresh({"mode": "missing"})["job_id"] == "abc"
    assert bridge.get_refresh_status({"job_id": "abc"})["state"] == "running"
    assert bridge.cancel_refresh({"job_id": "abc"})["ok"] is True
    assert calls == [
        ("request", {"mode": "missing"}),
        ("status", {"job_id": "abc"}),
        ("cancel", {"job_id": "abc"}),
    ]


def test_start_data_update_returns_blocked_without_dispatching_when_universe_unavailable(
    tmp_path,
    monkeypatch,
):
    class FakeOnboarding:
        def get_company_universe_by_preset(self, preset, *, refresh_catalog=False):
            assert refresh_catalog is True
            raise CompanyUniverseUnavailableError("missing market-cap source")

    class FakeManager:
        def __init__(self):
            self.called = False

        def request_refresh(self, params):
            self.called = True
            raise AssertionError("request_refresh must not be called for blocked universe")

        def record_failed_start(self, *, scope, error):
            self.failed_start = (scope, error)

    bridge = CVMBridge()
    fake_manager = FakeManager()
    market_cap_fetches = []
    from src.companies.market_cap import MarketCapService

    monkeypatch.setattr(
        MarketCapService,
        "fetch_from_yahoo_finance",
        lambda *_args, **_kwargs: market_cap_fetches.append(True),
    )
    bridge._onboarding_service = FakeOnboarding()
    bridge._refresh_manager = fake_manager
    bridge._service = SimpleNamespace(
        settings=build_settings(project_root=tmp_path),
        invalidate_read_caches=lambda: None,
    )
    bridge._resolve_data_update_settings = lambda: {
        "universe_preset": "top_200",
        "batch_size": 100,
        "retry_failed": True,
        "recompute_coverage": True,
        "start_year": 2022,
        "end_year": 2026,
    }
    bridge._normalize_data_update_settings = lambda raw: {
        "universe_preset": raw["universe_preset"],
        "batch_size": int(raw["batch_size"]),
        "retry_failed": bool(raw["retry_failed"]),
        "recompute_coverage": bool(raw["recompute_coverage"]),
        "start_year": int(raw["start_year"]),
        "end_year": int(raw["end_year"]),
    }

    response = bridge.start_data_update({"universe_preset": "top_200"})

    assert response["status"] == "blocked"
    assert response["status_reason_code"] == "company_universe_unavailable"
    assert response["job_id"] is None
    assert "missing market-cap source" in response["message"]
    assert fake_manager.called is False
    assert fake_manager.failed_start == ("data_update", "missing market-cap source")
    assert market_cap_fetches == []


def test_start_data_update_blocked_writes_packaged_runtime_log(tmp_path, monkeypatch):
    monkeypatch.setenv("CVM_DATA_DIR", str(tmp_path))

    class FakeOnboarding:
        def get_company_universe_by_preset(self, preset, *, refresh_catalog=False):
            assert refresh_catalog is True
            raise CompanyUniverseUnavailableError("missing market-cap source")

    bridge = CVMBridge()
    bridge._onboarding_service = FakeOnboarding()
    bridge._resolve_data_update_settings = lambda: {
        "universe_preset": "top_200",
        "batch_size": 100,
        "retry_failed": True,
        "recompute_coverage": True,
        "start_year": 2022,
        "end_year": 2026,
    }
    bridge._normalize_data_update_settings = lambda raw: {
        "universe_preset": raw["universe_preset"],
        "batch_size": int(raw["batch_size"]),
        "retry_failed": bool(raw["retry_failed"]),
        "recompute_coverage": bool(raw["recompute_coverage"]),
        "start_year": int(raw["start_year"]),
        "end_year": int(raw["end_year"]),
    }

    bridge.start_data_update({"universe_preset": "top_200"})

    log_text = (tmp_path / "recovery.log").read_text(encoding="utf-8")
    assert "start_data_update blocked" in log_text
    assert "company_universe_unavailable" in log_text
    assert "missing market-cap source" in log_text


def test_refresh_all_company_market_history_invalidates_cached_reads(tmp_path, monkeypatch):
    class FakeMarketHistoryService:
        def __init__(self, *, settings, read_service):
            assert settings.paths.db_path.parent == tmp_path / "data" / "db"
            assert read_service is bridge._service

        def refresh_all_market_history(self, cd_cvm):
            assert cd_cvm == 9512
            return {
                "ok": True,
                "cd_cvm": 9512,
                "attempted_count": 2,
                "success_count": 2,
                "failure_count": 0,
                "results": [],
            }

    invalidations = []
    bridge = CVMBridge()
    bridge._service = SimpleNamespace(
        settings=build_settings(project_root=tmp_path),
        invalidate_read_caches=lambda: invalidations.append(True),
    )
    monkeypatch.setattr(
        "src.companies.market_history.MarketHistoryService",
        FakeMarketHistoryService,
    )

    response = bridge.refresh_all_company_market_history({"cd_cvm": 9512})

    assert response["ok"] is True
    assert response["success_count"] == 2
    assert invalidations == [True]


def test_fetch_market_cap_snapshot_runs_the_yahoo_refresh_explicitly(tmp_path, monkeypatch):
    calls = []

    class FakeMarketCapService:
        def __init__(self, *, settings, read_service):
            self.settings = settings

        def fetch_from_yahoo_finance(self):
            calls.append(True)
            return {"available": True, "row_count": 209, "as_of_date": "2026-11-24", "source": "yahoo_finance"}

    invalidations = []
    bridge = CVMBridge()
    bridge._service = SimpleNamespace(
        settings=build_settings(project_root=tmp_path),
        invalidate_read_caches=lambda: invalidations.append(True),
    )
    monkeypatch.setattr("src.companies.market_cap.MarketCapService", FakeMarketCapService)

    response = bridge.fetch_market_cap_snapshot({})

    assert response["ok"] is True and response["status"]["row_count"] == 209
    assert calls == [True] and invalidations == [True]


def test_fetch_market_cap_snapshot_reports_failure_without_raising(tmp_path, monkeypatch):
    class FailingMarketCapService:
        def __init__(self, *, settings, read_service):
            pass

        def fetch_from_yahoo_finance(self):
            raise RuntimeError("Yahoo Finance API request failed: offline")

    bridge = CVMBridge()
    bridge._service = SimpleNamespace(settings=build_settings(project_root=tmp_path), invalidate_read_caches=lambda: None)
    monkeypatch.setattr("src.companies.market_cap.MarketCapService", FailingMarketCapService)

    response = bridge.fetch_market_cap_snapshot({})

    assert response["ok"] is False and "offline" in response["error"]


def test_market_cap_unavailable_message_points_to_an_action_that_exists():
    from src.companies.universe import _market_cap_unavailable_message

    message = _market_cap_unavailable_message(snapshot_path=Path("snap.csv"), provider_errors=[])
    assert "Run database updates" not in message
    assert "Fetch market caps" in message
