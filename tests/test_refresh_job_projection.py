from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text

from src.refresh.job_projection import (
    db_worker_row_to_public,
    list_db_worker_jobs,
    list_db_worker_jobs_sqlite,
    lookup_db_worker_job,
    persistable_batch_job,
    public_batch_job,
)


def test_db_worker_row_to_public_normalizes_states_and_timestamps() -> None:
    no_data = db_worker_row_to_public(
        {
            "id": "j1",
            "cd_cvm": 9512,
            "state": "no_data",
            "stage": "persist_reports",
            "progress_current": 0,
            "progress_total": 1,
            "progress_message": "done",
            "requested_at": "2026-01-01T00:00:00Z",
            "started_at": "2026-01-01T00:00:05Z",
            "finished_at": "2026-01-01T00:00:10Z",
        }
    )
    assert no_data["state"] == "success"
    assert no_data["status"] == "success"
    assert no_data["processed"] == 1
    assert no_data["failures"] == 0
    assert no_data["updated_at"] == "2026-01-01T00:00:10Z"
    assert no_data["source"] == "db_worker"
    assert no_data["log_lines"] == ["done"]

    failed = db_worker_row_to_public(
        {
            "id": "j2",
            "cd_cvm": 4170,
            "state": "failed",
            "error_message": "network timeout",
            "requested_at": "2026-01-01T00:00:00Z",
            "heartbeat_at": "2026-01-01T00:00:08Z",
        }
    )
    assert failed["state"] == "error"
    assert failed["failures"] == 1
    assert failed["processed"] == 1
    assert failed["updated_at"] == "2026-01-01T00:00:08Z"
    assert failed["error"] == "network timeout"
    assert failed["log_lines"] == ["network timeout"]


def test_list_and_lookup_db_worker_jobs_via_engine_and_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "refresh.db"
    assert list_db_worker_jobs_sqlite(db_path) == []

    engine = create_engine(f"sqlite:///{db_path}")
    # Ensure tables and insert 1 active + 2 terminal jobs
    assert list_db_worker_jobs(engine) == []
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO refresh_jobs (id, cd_cvm, start_year, end_year, state, requested_at, started_at, finished_at, progress_message) "
                "VALUES "
                "('active-1', 9512, 2022, 2026, 'running', '2026-01-03T00:00:00Z', '2026-01-03T00:00:01Z', NULL, 'fetching'),"
                "('done-new', 4170, 2022, 2026, 'success', '2026-01-02T00:00:00Z', '2026-01-02T00:00:01Z', '2026-01-02T00:00:10Z', 'ok'),"
                "('done-old', 1023, 2022, 2026, 'failed', '2026-01-01T00:00:00Z', '2026-01-01T00:00:01Z', '2026-01-01T00:00:10Z', 'boom')"
            )
        )

    listed = list_db_worker_jobs(engine, limit=1)
    assert [row["job_id"] for row in listed] == ["active-1", "done-new"]

    single = lookup_db_worker_job(engine, "done-old")
    assert single is not None
    assert single["job_id"] == "done-old"
    assert single["state"] == "error"
    assert lookup_db_worker_job(engine, "missing") is None

    lite_list = list_db_worker_jobs_sqlite(db_path, limit=1)
    assert [row["job_id"] for row in lite_list] == ["active-1", "done-new"]
    lite_single = list_db_worker_jobs_sqlite(db_path, job_id="done-old")
    assert len(lite_single) == 1
    assert lite_single[0]["state"] == "error"
    engine.dispose()


def test_list_db_worker_jobs_sqlite_handles_db_without_table(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE other (id INTEGER)")
    assert list_db_worker_jobs_sqlite(db_path) == []


def test_batch_job_shaping_helpers_cap_logs_and_control_result_visibility() -> None:
    raw = {
        "job_id": "b1",
        "state": "success",
        "mode": "missing",
        "queued": 5,
        "processed": 5,
        "failures": 0,
        "log_lines": [f"line-{i}" for i in range(250)],
        "result": {"heavy": True},
    }
    persisted = persistable_batch_job(raw, max_log_lines=200)
    assert persisted["result"] is None
    assert len(persisted["log_lines"]) == 200
    assert persisted["log_lines"][0] == "line-50"

    pub_default = public_batch_job(raw)
    assert pub_default["result"] is None
    assert pub_default["status"] == "success"

    pub_with_result = public_batch_job(raw, include_result=True)
    assert pub_with_result["result"] == {"heavy": True}
