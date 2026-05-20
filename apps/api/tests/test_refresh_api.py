from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.api.app.services.refresh_jobs import ApiRefreshJobManager, RefreshBatchRequestError
from src.contracts import RefreshResult
from src.settings import AppSettings


def _running_job(job_id: str = "job-batch-1") -> dict[str, object]:
    return {
        "job_id": job_id,
        "state": "running",
        "status": "running",
        "stage": "download_extract",
        "queued": 2,
        "processed": 1,
        "failures": 0,
        "current_cvm": 9512,
        "progress_current": 1,
        "progress_total": 2,
        "log_lines": ["Refresh em lote em execucao.", "Processando CVM 9512."],
        "accepted_at": "2026-05-03T10:00:00",
        "started_at": "2026-05-03T10:00:01",
        "finished_at": None,
        "updated_at": "2026-05-03T10:00:02",
        "error": None,
        "result": None,
    }


class FakeRefreshJobManager:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.active_only_args: list[bool] = []
        self.jobs = {"job-batch-1": _running_job()}

    def request_refresh(self, params: dict[str, object]) -> dict[str, object]:
        self.requests.append(dict(params))
        return {
            "job_id": "job-batch-1",
            "status": "running",
            "accepted_at": "2026-05-03T10:00:00",
            "queued": 2,
            "message": "Refresh em lote iniciado em background.",
            "status_reason_code": "refresh_started",
            "is_retry_allowed": False,
        }

    def get_job(self, job_id: str) -> dict[str, object] | None:
        return self.jobs.get(job_id)

    def list_jobs(self, *, active_only: bool = True) -> list[dict[str, object]]:
        self.active_only_args.append(active_only)
        return list(self.jobs.values())

    def cancel_job(self, job_id: str) -> dict[str, object] | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        job.update(
            {
                "state": "cancelled",
                "status": "cancelled",
                "finished_at": "2026-05-03T10:00:03",
            }
        )
        return {
            "ok": True,
            "job_id": job_id,
            "state": "cancelled",
            "status": "cancelled",
            "message": "Refresh em lote cancelado.",
            "status_reason_code": "cancelled",
            "is_retry_allowed": False,
        }


def test_refresh_batch_dispatch_returns_202(client: TestClient) -> None:
    manager = FakeRefreshJobManager()
    client.app.state.refresh_job_manager = manager

    response = client.post("/refresh/batch", json={"mode": "missing"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"] == "job-batch-1"
    assert payload["status"] == "running"
    assert payload["queued"] == 2
    assert manager.requests == [{"mode": "missing"}]


def test_refresh_batch_accepts_bridge_filter_params(client: TestClient) -> None:
    manager = FakeRefreshJobManager()
    client.app.state.refresh_job_manager = manager

    response = client.post(
        "/refresh/batch",
        json={
            "mode": "failed",
            "sector_slug": "energia",
            "cvm_range": {"start": 4000, "end": 12000},
            "status_filter": "error",
            "start_year": 2023,
            "end_year": 2024,
        },
    )

    assert response.status_code == 202
    assert manager.requests == [
        {
            "mode": "failed",
            "sector_slug": "energia",
            "cvm_range": {"start": 4000, "end": 12000},
            "status_filter": "error",
            "start_year": 2023,
            "end_year": 2024,
        }
    ]


def test_refresh_batch_accepts_desktop_bridge_alias_params(client: TestClient) -> None:
    manager = FakeRefreshJobManager()
    client.app.state.refresh_job_manager = manager

    response = client.post(
        "/refresh/batch",
        json={
            "mode": "missing",
            "sector": "energia",
            "cvm_from": 4000,
            "cvm_to": 12000,
        },
    )

    assert response.status_code == 202
    assert manager.requests == [
        {
            "mode": "missing",
            "sector": "energia",
            "cvm_from": 4000,
            "cvm_to": 12000,
        }
    ]


def test_refresh_job_polling_returns_progress(client: TestClient) -> None:
    manager = FakeRefreshJobManager()
    client.app.state.refresh_job_manager = manager

    response = client.get("/refresh/jobs/job-batch-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "running"
    assert payload["processed"] == 1
    assert payload["failures"] == 0
    assert payload["current_cvm"] == 9512
    assert payload["log_lines"][-1] == "Processando CVM 9512."


def test_refresh_jobs_lists_active_jobs(client: TestClient) -> None:
    manager = FakeRefreshJobManager()
    client.app.state.refresh_job_manager = manager

    response = client.get("/refresh/jobs")

    assert response.status_code == 200
    assert response.json()["items"][0]["job_id"] == "job-batch-1"
    assert manager.active_only_args == [True]


def test_refresh_job_polling_unknown_id_returns_404(client: TestClient) -> None:
    manager = FakeRefreshJobManager()
    client.app.state.refresh_job_manager = manager

    response = client.get("/refresh/jobs/missing-job")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_refresh_job_cancel_returns_cancelled_payload(client: TestClient) -> None:
    manager = FakeRefreshJobManager()
    client.app.state.refresh_job_manager = manager

    response = client.post("/refresh/jobs/job-batch-1/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["job_id"] == "job-batch-1"
    assert payload["state"] == "cancelled"
    assert payload["status_reason_code"] == "cancelled"


def test_refresh_job_cancel_unknown_id_returns_404(client: TestClient) -> None:
    manager = FakeRefreshJobManager()
    client.app.state.refresh_job_manager = manager

    response = client.post("/refresh/jobs/missing-job/cancel")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


class FakeReadService:
    def __init__(
        self,
        *,
        items: list[SimpleNamespace] | None = None,
        statuses: list[SimpleNamespace] | None = None,
        complete_years: dict[int, tuple[int, ...]] | None = None,
    ) -> None:
        self.list_company_calls: list[dict[str, object]] = []
        self.items = items or [
            SimpleNamespace(cd_cvm=9512),
            SimpleNamespace(cd_cvm=4170),
            SimpleNamespace(cd_cvm=11223),
        ]
        self.statuses = statuses or [
            SimpleNamespace(
                cd_cvm=9512,
                tracking_state="success",
                last_status="success",
                latest_attempt_outcome="success",
            ),
            SimpleNamespace(
                cd_cvm=4170,
                tracking_state="error",
                last_status="error",
                latest_attempt_outcome="error",
            ),
            SimpleNamespace(
                cd_cvm=11223,
                tracking_state="queued",
                last_status="queued",
                latest_attempt_outcome="queued",
            ),
        ]
        self.complete_years = complete_years or {}

    def list_companies(self, **kwargs: object) -> SimpleNamespace:
        self.list_company_calls.append(dict(kwargs))
        return SimpleNamespace(items=list(self.items))

    def list_refresh_status(self) -> list[SimpleNamespace]:
        return list(self.statuses)

    def _load_complete_annual_years_map(
        self,
        cd_cvms: list[int],
        *,
        start_year: int,
        end_year: int,
    ) -> dict[int, tuple[int, ...]]:
        return {
            int(cd_cvm): tuple(
                year
                for year in self.complete_years.get(int(cd_cvm), ())
                if int(start_year) <= int(year) <= int(end_year)
            )
            for cd_cvm in cd_cvms
        }


class CancellableRefreshService:
    def __init__(self) -> None:
        self.requests = []
        self.started = threading.Event()
        self.cancel_seen = threading.Event()

    def execute(
        self,
        request,
        *,
        progress_callback=None,
        stage_callback=None,
        should_cancel=None,
        persist_refresh_status=True,
    ) -> RefreshResult:
        del progress_callback, stage_callback, persist_refresh_status
        self.requests.append(request)
        self.started.set()
        deadline = time.time() + 3
        while time.time() < deadline:
            if should_cancel is not None and should_cancel():
                self.cancel_seen.set()
                return RefreshResult(
                    request=request,
                    companies=(),
                    planning_stats={"cancelled": 1},
                    synced_companies=0,
                    cancelled=True,
                )
            time.sleep(0.01)
        return RefreshResult(
            request=request,
            companies=(),
            planning_stats={"cancelled": 0},
            synced_companies=0,
            cancelled=False,
        )


def _wait_for_job_state(
    manager: ApiRefreshJobManager,
    job_id: str,
    expected_state: str,
) -> dict[str, object]:
    deadline = time.time() + 3
    while time.time() < deadline:
        job = manager.get_job(job_id)
        if job is not None and job["state"] == expected_state:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {expected_state}")


def test_refresh_job_manager_reuses_bridge_filter_semantics(api_settings: AppSettings) -> None:
    read_service = FakeReadService()
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=read_service,
        autostart=False,
    )

    result = manager.request_refresh(
        {
            "mode": "failed",
            "sector_slug": "energia",
            "cvm_range": {"start": 4000, "end": 10000},
        }
    )

    assert result["status"] == "queued"
    assert result["queued"] == 1
    job = manager._jobs[str(result["job_id"])]
    assert job["request"]["companies"] == ["4170"]
    assert read_service.list_company_calls == [
        {
            "search": "",
            "sector_slug": "energia",
            "page": 1,
            "page_size": 10000,
        }
    ]


def test_refresh_job_manager_rejects_invalid_mode(api_settings: AppSettings) -> None:
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=FakeReadService(),
        autostart=False,
    )

    with pytest.raises(RefreshBatchRequestError):
        manager.request_refresh({"mode": "unknown"})


def test_refresh_job_manager_cancels_queued_job(api_settings: AppSettings) -> None:
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=FakeReadService(),
        autostart=False,
    )
    dispatch = manager.request_refresh({"mode": "full", "cd_cvm": 9512})

    result = manager.cancel_job(str(dispatch["job_id"]))

    assert result is not None
    assert result["ok"] is True
    assert result["state"] == "cancelled"
    job = manager.get_job(str(dispatch["job_id"]))
    assert job is not None
    assert job["state"] == "cancelled"
    assert job["status"] == "cancelled"
    assert job["finished_at"] is not None
    assert "cancelado antes da execucao" in job["log_lines"][-1]


def test_refresh_job_manager_cancels_running_job(api_settings: AppSettings) -> None:
    refresh_service = CancellableRefreshService()
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=FakeReadService(),
        refresh_service=refresh_service,
    )
    dispatch = manager.request_refresh({"mode": "full", "cd_cvm": 9512})
    job_id = str(dispatch["job_id"])
    assert refresh_service.started.wait(timeout=3)

    result = manager.cancel_job(job_id)

    assert result is not None
    assert result["ok"] is True
    assert result["status_reason_code"] == "cancel_requested"
    assert refresh_service.cancel_seen.wait(timeout=3)
    job = _wait_for_job_state(manager, job_id, "cancelled")
    assert job["status"] == "cancelled"
    assert job["finished_at"] is not None
    assert "Cancelamento solicitado." in job["log_lines"]
    assert job["log_lines"][-1] == "Refresh em lote cancelado."
    assert refresh_service.requests[0].companies == ("9512",)


def test_refresh_job_manager_cancel_unknown_job_returns_none(
    api_settings: AppSettings,
) -> None:
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=FakeReadService(),
        autostart=False,
    )

    assert manager.cancel_job("missing-job") is None


def test_refresh_job_manager_cancel_terminal_job_is_noop(
    api_settings: AppSettings,
) -> None:
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=FakeReadService(),
        autostart=False,
    )
    dispatch = manager.request_refresh({"mode": "full", "cd_cvm": 9512})
    job_id = str(dispatch["job_id"])
    manager.cancel_job(job_id)
    before = manager.get_job(job_id)

    result = manager.cancel_job(job_id)
    after = manager.get_job(job_id)

    assert result is not None
    assert result["ok"] is False
    assert result["state"] == "cancelled"
    assert result["status_reason_code"] == "already_terminal"
    assert before is not None
    assert after is not None
    assert after["finished_at"] == before["finished_at"]
    assert after["log_lines"] == before["log_lines"]


def test_refresh_job_manager_resolves_missing_from_real_coverage(
    api_settings: AppSettings,
) -> None:
    read_service = FakeReadService(
        items=[
            SimpleNamespace(cd_cvm=100),
            SimpleNamespace(cd_cvm=200),
            SimpleNamespace(cd_cvm=300),
        ],
        statuses=[],
        complete_years={
            100: (2023, 2024),
            200: (2023,),
            300: (),
        },
    )
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=read_service,
        autostart=False,
    )

    result = manager.request_refresh(
        {"mode": "missing", "start_year": 2023, "end_year": 2024}
    )

    assert result["queued"] == 2
    job = manager._jobs[str(result["job_id"])]
    assert job["request"]["companies"] == ["200", "300"]


def test_refresh_job_manager_resolves_full_after_filters_and_limit(
    api_settings: AppSettings,
) -> None:
    read_service = FakeReadService(
        items=[
            SimpleNamespace(cd_cvm=100),
            SimpleNamespace(cd_cvm=200),
            SimpleNamespace(cd_cvm=300),
        ],
        statuses=[],
    )
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=read_service,
        autostart=False,
    )

    result = manager.request_refresh(
        {
            "mode": "full",
            "cvm_range": {"start": 100, "end": 300},
            "limit": 2,
        }
    )

    assert result["queued"] == 2
    job = manager._jobs[str(result["job_id"])]
    assert job["request"]["companies"] == ["100", "200"]
    assert read_service.list_company_calls[0]["page_size"] == 10000


def test_refresh_job_manager_composes_cd_cvm_with_explicit_filters(
    api_settings: AppSettings,
) -> None:
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=FakeReadService(
            items=[
                SimpleNamespace(cd_cvm=100),
                SimpleNamespace(cd_cvm=200),
                SimpleNamespace(cd_cvm=300),
            ],
            statuses=[],
        ),
        autostart=False,
    )

    result = manager.request_refresh(
        {
            "mode": "full",
            "cd_cvm": 300,
            "cvm_range": {"start": 100, "end": 250},
        }
    )

    assert result["status"] == "already_current"
    assert result["queued"] == 0


def test_refresh_job_manager_resolves_outdated_from_freshness_metadata(
    api_settings: AppSettings,
) -> None:
    read_service = FakeReadService(
        items=[
            SimpleNamespace(cd_cvm=100),
            SimpleNamespace(cd_cvm=200),
            SimpleNamespace(cd_cvm=300),
        ],
        statuses=[
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
                cd_cvm=200,
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
                cd_cvm=300,
                tracking_state="error",
                last_status="error",
                latest_attempt_outcome="error",
                is_retry_allowed=True,
                has_readable_current_data=True,
                freshness_summary_severity="warning",
            ),
        ],
    )
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=read_service,
        autostart=False,
    )

    result = manager.request_refresh(
        {"mode": "outdated", "start_year": 2023, "end_year": 2024}
    )

    assert result["queued"] == 1
    job = manager._jobs[str(result["job_id"])]
    assert job["request"]["companies"] == ["200"]


def test_refresh_job_manager_resolves_failed_retryable_only(
    api_settings: AppSettings,
) -> None:
    read_service = FakeReadService(
        items=[
            SimpleNamespace(cd_cvm=100),
            SimpleNamespace(cd_cvm=200),
            SimpleNamespace(cd_cvm=300),
        ],
        statuses=[
            SimpleNamespace(
                cd_cvm=100,
                tracking_state="error",
                last_status="error",
                latest_attempt_outcome="error",
                is_retry_allowed=True,
            ),
            SimpleNamespace(
                cd_cvm=200,
                tracking_state="error",
                last_status="error",
                latest_attempt_outcome="error",
                is_retry_allowed=False,
            ),
            SimpleNamespace(
                cd_cvm=300,
                tracking_state="success",
                last_status="success",
                latest_attempt_outcome="success",
            ),
        ],
    )
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=read_service,
        autostart=False,
    )

    result = manager.request_refresh({"mode": "failed"})

    assert result["queued"] == 1
    job = manager._jobs[str(result["job_id"])]
    assert job["request"]["companies"] == ["100"]


@pytest.mark.parametrize(
    "params, expected_message",
    [
        ({"mode": "missing", "start_year": 2025, "end_year": 2024}, "start_year"),
        (
            {"mode": "full", "cvm_range": {"start": 200, "end": 100}},
            "cvm_range.start",
        ),
    ],
)
def test_refresh_job_manager_rejects_invalid_ranges(
    api_settings: AppSettings,
    params: dict[str, object],
    expected_message: str,
) -> None:
    manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=FakeReadService(),
        autostart=False,
    )

    with pytest.raises(RefreshBatchRequestError, match=expected_message):
        manager.request_refresh(params)


def test_refresh_batch_invalid_manager_request_returns_422(client: TestClient) -> None:
    class FailingManager:
        def request_refresh(self, params: dict[str, object]) -> dict[str, object]:
            raise RefreshBatchRequestError("start_year nao pode ser maior que end_year.")

    client.app.state.refresh_job_manager = FailingManager()

    response = client.post(
        "/refresh/batch",
        json={"mode": "missing", "start_year": 2025, "end_year": 2024},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert "start_year" in response.json()["error"]["message"]


def test_refresh_batch_actual_manager_invalid_range_returns_422(
    client: TestClient,
    api_settings: AppSettings,
) -> None:
    client.app.state.refresh_job_manager = ApiRefreshJobManager(
        settings=api_settings,
        read_service=FakeReadService(),
        autostart=False,
    )

    response = client.post(
        "/refresh/batch",
        json={"mode": "full", "cvm_range": {"start": "200", "end": "100"}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert "cvm_range.start" in response.json()["error"]["message"]


def test_refresh_job_manager_now_iso_is_utc_with_offset() -> None:
    from datetime import datetime

    value = ApiRefreshJobManager._now_iso()

    parsed = datetime.fromisoformat(value)
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0
    assert parsed.microsecond == 0
