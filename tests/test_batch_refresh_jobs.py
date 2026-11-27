from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.platform.contracts import RefreshProgressUpdate
from src.refresh.batch_jobs import BatchRefreshJobManager


class _StubReadService:
    def list_refresh_status(self, _cd_cvm: int | None = None):
        return []


def test_batch_manager_in_memory_does_not_write_files(tmp_path: Path) -> None:
    mgr = BatchRefreshJobManager(read_service=_StubReadService(), jobs_path=None, autostart=False)
    res = mgr._enqueue_batch_refresh({"mode": "invalid"})
    assert res["status"] == "error"
    assert res["status_reason_code"] == "invalid_mode"
    assert list(tmp_path.iterdir()) == []


def test_batch_manager_persists_prunes_and_marks_unfinished_interrupted(tmp_path: Path) -> None:
    jobs_file = tmp_path / "refresh_jobs.json"
    jobs_file.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "job_id": "in-flight",
                        "state": "running",
                        "mode": "missing",
                        "created_at": "2026-01-01T00:00:00Z",
                        "log_lines": ["started"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    mgr = BatchRefreshJobManager(read_service=_StubReadService(), jobs_path=jobs_file, autostart=False)
    snap = mgr.snapshot_jobs()
    assert len(snap) == 1
    assert snap[0]["state"] == "interrupted"
    assert "closed before" in str(snap[0]["error"]).lower()


def test_batch_manager_stage_sets_companies_started_at_once(tmp_path: Path) -> None:
    mgr = BatchRefreshJobManager(
        read_service=_StubReadService(),
        jobs_path=tmp_path / "jobs.json",
        autostart=False,
    )
    mgr._jobs["j1"] = {
        "job_id": "j1",
        "state": "running",
        "mode": "missing",
        "created_at": "2026-01-01T00:00:00Z",
        "log_lines": [],
    }
    clock = iter(["2026-01-01T00:01:00Z", "2026-01-01T00:01:01Z", "2026-01-01T00:02:00Z", "2026-01-01T00:02:01Z"])
    mgr._now_iso = lambda: next(clock)  # type: ignore[method-assign]

    mgr._handle_stage("j1", RefreshProgressUpdate(stage="process_data", current=1, total=5, message="c1"))
    first_ts = mgr._jobs["j1"]["companies_started_at"]
    mgr._handle_stage("j1", RefreshProgressUpdate(stage="persist_reports", current=2, total=5, message="c2"))
    assert mgr._jobs["j1"]["companies_started_at"] == first_ts
    assert mgr._jobs["j1"]["progress_current"] == 2
    assert mgr._jobs["j1"]["progress_total"] == 5


def test_desktop_and_api_managers_share_batch_refresh_base() -> None:
    from apps.api.app.services.refresh_jobs import ApiRefreshJobManager
    from desktop.services import DesktopRefreshJobManager

    assert issubclass(DesktopRefreshJobManager, BatchRefreshJobManager)
    assert issubclass(ApiRefreshJobManager, BatchRefreshJobManager)
    assert SimpleNamespace(d=DesktopRefreshJobManager.SUPPORT_PARTIAL_STATE, a=ApiRefreshJobManager.SUPPORT_PARTIAL_STATE) == SimpleNamespace(d=True, a=False)
    assert DesktopRefreshJobManager.LOG_LABEL == "Refresh"
    assert ApiRefreshJobManager.LOG_LABEL == "Refresh em lote"
