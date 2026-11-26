from __future__ import annotations

import threading
from types import SimpleNamespace

from desktop.bridge import CVMBridge
from desktop.services import DesktopRefreshJobManager
from src.companies.universe import CompanyUniverseEntry, CompanyUniverseSelection
from src.financials.read_service import resolve_refresh_batch_selection
from src.platform.contracts import RefreshResult
from src.platform.settings import build_settings


def _entry(cd_cvm, name, ticker):
    return CompanyUniverseEntry(
        cd_cvm=cd_cvm, ticker=ticker, company_name=name, market_cap=None,
        market_cap_rank=None, source="cvm_company_catalog", source_date=None,
    )


class _Onboarding:
    def __init__(self, entries):
        self.entries = entries
        self.calls = []

    def get_company_universe_by_preset(self, preset, *, refresh_catalog=False):
        self.calls.append((preset, refresh_catalog))
        return CompanyUniverseSelection(preset=preset, entries=tuple(self.entries), source="cvm_company_catalog", source_date=None)


class _Manager:
    def __init__(self):
        self.params = None

    def request_refresh(self, params):
        self.params = params
        return {"status": "running", "job_id": "job-1", "queued": len(params["company_ids"])}


def _bridge(tmp_path, entries):
    bridge = CVMBridge()
    bridge._onboarding_service = _Onboarding(entries)
    bridge._refresh_manager = _Manager()
    bridge._service = SimpleNamespace(settings=build_settings(project_root=tmp_path), invalidate_read_caches=lambda: None)
    bridge._resolve_data_update_settings = lambda: {
        "universe_preset": "top_200", "batch_size": 100, "retry_failed": True,
        "recompute_coverage": True, "start_year": 2022, "end_year": 2026,
    }
    return bridge


def test_data_update_targets_all_active_companies_with_tickers_first(tmp_path):
    entries = [_entry(1, "ZETA SA", "ZETA3"), _entry(2, "ALFA SA", None), _entry(3, "BETA SA", "BETA3"), _entry(4, "AURA SA", None)]
    bridge = _bridge(tmp_path, entries)

    response = bridge.start_data_update({})

    assert bridge._onboarding_service.calls == [("all", True)]
    params = bridge._refresh_manager.params
    assert params["company_ids"] == [3, 1, 2, 4]
    assert "limit" not in params
    assert params["scope"] == "data_update"
    assert (params["start_year"], params["end_year"]) == (2022, 2026)
    assert response["status"] == "running"


def test_data_update_ignores_legacy_preset_and_batch_inputs(tmp_path):
    entries = [_entry(index, f"CO {index:03d}", None) for index in range(1, 701)]
    bridge = _bridge(tmp_path, entries)

    bridge.start_data_update({"universe_preset": "top_200", "batch_size": 50})

    params = bridge._refresh_manager.params
    assert len(params["company_ids"]) == 700
    assert bridge._onboarding_service.calls == [("all", True)]


def test_batch_selection_keeps_requested_company_order():
    class _Read:
        def list_companies(self, **_):
            return SimpleNamespace(items=tuple(SimpleNamespace(cd_cvm=code) for code in (1, 2, 3)))

        def list_refresh_status(self):
            return ()

        def _load_complete_annual_years_map(self, cd_cvms, *, start_year, end_year):
            return {}

    selection = resolve_refresh_batch_selection(
        _Read(), {"company_ids": [3, 1, 2], "start_year": 2022, "end_year": 2026}, mode="full", default_start_year=2010,
    )
    assert selection.companies == ("3", "1", "2")


class _CapturingRefresh:
    def __init__(self):
        self.request = None

    def execute(self, request, **_):
        self.request = request
        return RefreshResult(request=request, companies=(), planning_stats={})


def _run_job_with_scope(tmp_path, scope):
    settings = build_settings(project_root=tmp_path)
    refresh = _CapturingRefresh()

    class _Read:
        def list_companies(self, **_):
            return SimpleNamespace(items=(SimpleNamespace(cd_cvm=9512),))

        def list_refresh_status(self):
            return ()

        def _load_complete_annual_years_map(self, cd_cvms, *, start_year, end_year):
            return {}

    manager = DesktopRefreshJobManager(
        settings=settings, read_service=_Read(), refresh_service=refresh,
        jobs_path=tmp_path / "jobs.json", autostart=False,
    )
    dispatch = manager.request_refresh({"mode": "missing", "scope": scope, "company_ids": [9512], "start_year": 2022, "end_year": 2026})
    manager._run_job(dispatch["job_id"], threading.Event())
    return refresh.request


def test_data_update_honors_the_history_range(tmp_path):
    request = _run_job_with_scope(tmp_path, "data_update")
    assert request.policy.enable_fast_lane is False
    assert request.policy.reuse_catalog_snapshot is True
    assert (request.start_year, request.end_year) == (2022, 2026)


def test_other_missing_mode_batches_keep_the_fast_lane(tmp_path):
    request = _run_job_with_scope(tmp_path, None)
    assert request.policy.enable_fast_lane is True


from src.platform.contracts import CompanyRefreshResult


def _company(code, status):
    return CompanyRefreshResult(
        company_name=f"CO {code}", cvm_code=code, requested_years=(2024,), years_processed=(),
        rows_inserted=0, status=status, attempts=1, error=None if status == "success" else "boom",
    )


class _ScriptedRefresh:
    """Returns one scripted result per execute call, recording requested companies."""

    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.calls = []

    def execute(self, request, **_):
        self.calls.append(tuple(request.companies))
        statuses = self.rounds.pop(0)
        companies = tuple(_company(int(code), statuses.get(int(code), "success")) for code in request.companies)
        return RefreshResult(request=request, companies=companies, planning_stats={})


def _manager(tmp_path, refresh, finished=None):
    class _Read:
        def list_companies(self, **_):
            return SimpleNamespace(items=tuple(SimpleNamespace(cd_cvm=code) for code in (1, 2, 3)))

        def list_refresh_status(self):
            return ()

        def _load_complete_annual_years_map(self, cd_cvms, *, start_year, end_year):
            return {}

    return DesktopRefreshJobManager(
        settings=build_settings(project_root=tmp_path), read_service=_Read(), refresh_service=refresh,
        jobs_path=tmp_path / "jobs.json", autostart=False, on_job_finished=finished,
    )


def _run(manager, scope="data_update"):
    dispatch = manager.request_refresh({"mode": "missing", "scope": scope, "company_ids": [1, 2, 3], "start_year": 2024, "end_year": 2024})
    manager._run_job(dispatch["job_id"], threading.Event())
    return manager.snapshot_jobs()[0]


def test_failed_companies_are_retried_once_inside_the_data_update(tmp_path):
    refresh = _ScriptedRefresh({2: "error"}, {})
    job = _run(_manager(tmp_path, refresh))
    assert refresh.calls == [("1", "2", "3"), ("2",)]
    assert job["state"] == "success"
    assert job["failures"] == 0


def test_a_run_with_some_failed_companies_ends_partial(tmp_path):
    refresh = _ScriptedRefresh({2: "error"}, {2: "error"})
    job = _run(_manager(tmp_path, refresh))
    assert job["state"] == "partial"
    assert job["failures"] == 1


def test_a_run_where_every_company_failed_ends_in_error(tmp_path):
    refresh = _ScriptedRefresh({1: "error", 2: "error", 3: "error"}, {1: "error", 2: "error", 3: "error"})
    assert _run(_manager(tmp_path, refresh))["state"] == "error"


def test_the_job_refreshes_reads_when_it_finishes(tmp_path):
    finished = []
    _run(_manager(tmp_path, _ScriptedRefresh({}), finished=lambda job_id: finished.append(job_id)))
    assert len(finished) == 1


def test_job_store_keeps_only_recent_finished_jobs(tmp_path):
    import json as _json

    manager = _manager(tmp_path, _ScriptedRefresh(*([{}] * 60)))
    for _ in range(60):
        _run(manager, scope="retry")
    stored = _json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    assert len(stored) <= DesktopRefreshJobManager.MAX_STORED_JOBS


def test_light_job_reader_never_rewrites_the_store(tmp_path):
    import json as _json

    bridge = CVMBridge()
    settings = build_settings(project_root=tmp_path)
    bridge._service = SimpleNamespace(settings=settings)
    jobs_path = settings.paths.data_dir / "refresh_jobs.json"
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    original = _json.dumps({"jobs": [{"job_id": "a", "state": "running", "created_at": "2026"}]})
    jobs_path.write_text(original, encoding="utf-8")
    import desktop.bridge_api.refresh as refresh_module

    original_path = refresh_module.RefreshBridgeMixin._refresh_jobs_path
    refresh_module.RefreshBridgeMixin._refresh_jobs_path = staticmethod(lambda: jobs_path)
    try:
        bridge._load_refresh_jobs_light()
    finally:
        refresh_module.RefreshBridgeMixin._refresh_jobs_path = original_path
    assert jobs_path.read_text(encoding="utf-8") == original
