from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from types import SimpleNamespace

from desktop.bridge import CVMBridge
from src.platform.settings import build_settings
from src.refresh.local_database_state import (
    derive_local_database_state,
    latest_passed_deadline,
)

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def _job(**overrides):
    job = {
        "job_id": "j1",
        "state": "success",
        "mode": "missing",
        "scope": "data_update",
        "queued": 10,
        "processed": 10,
        "failures": 0,
        "started_at": "2026-11-20T10:00:00+00:00",
        "finished_at": "2026-11-20T11:00:00+00:00",
        "updated_at": "2026-11-20T11:00:00+00:00",
    }
    job.update(overrides)
    return job


# ---------- stale calendar ----------

def test_no_deadline_passed_since_last_full_update():
    assert latest_passed_deadline(date(2026, 11, 20), date(2026, 11, 25)) is None


def test_itr_deadline_passed_since_last_full_update():
    deadline = latest_passed_deadline(date(2026, 11, 1), date(2026, 11, 25))
    assert deadline is not None
    assert deadline.label == "ITR 3Q26"
    assert deadline.due == date(2026, 11, 14)


def test_deadline_on_update_day_is_not_stale():
    assert latest_passed_deadline(date(2026, 11, 14), date(2026, 11, 25)) is None


def test_latest_of_several_passed_deadlines_is_reported():
    deadline = latest_passed_deadline(date(2026, 1, 10), date(2026, 8, 20))
    assert deadline is not None
    assert deadline.label == "ITR 2Q26"


def test_dfp_deadline_label_uses_fiscal_year():
    deadline = latest_passed_deadline(date(2026, 3, 1), date(2026, 4, 2))
    assert deadline is not None
    assert deadline.label == "DFP 2025"
    assert deadline.due == date(2026, 3, 31)


# ---------- derived state ----------

def test_empty_without_statements_or_jobs():
    state = derive_local_database_state(has_statements=False, jobs=[], now=NOW)
    assert state["state"] == "empty"
    assert state["last_full_update_at"] is None
    assert state["run"] is None


def test_running_job_in_file_phase_is_files():
    job = _job(state="running", stage="download_extract", progress_current=6, progress_total=10, processed=0, finished_at=None)
    state = derive_local_database_state(has_statements=False, jobs=[job], now=NOW)
    assert state["state"] == "files"
    assert state["run"]["phase"] == "files"
    assert state["run"]["files_done"] == 6
    assert state["run"]["files_total"] == 10


def test_running_job_in_company_phase_is_updating_with_pace_eta():
    job = _job(
        state="running",
        stage="process_data",
        queued=400,
        processed=100,
        finished_at=None,
        companies_started_at="2026-11-25T11:00:00+00:00",
    )
    state = derive_local_database_state(has_statements=True, jobs=[job], now=NOW)
    assert state["state"] == "updating"
    assert state["run"]["phase"] == "companies"
    # 100 companies in 3600 s -> 300 remaining take 10800 s.
    assert state["run"]["eta_seconds"] == 10800


def test_eta_is_unknown_before_any_company_finishes():
    job = _job(state="running", stage="process_data", processed=0, finished_at=None, companies_started_at="2026-11-25T11:59:00+00:00")
    state = derive_local_database_state(has_statements=True, jobs=[job], now=NOW)
    assert state["run"]["eta_seconds"] is None


def test_recent_full_update_is_current():
    state = derive_local_database_state(has_statements=True, jobs=[_job()], now=NOW)
    assert state["state"] == "current"
    assert state["last_full_update_at"] == "2026-11-20T11:00:00+00:00"
    assert state["stale_reason"] is None


def test_full_update_before_a_deadline_is_stale():
    job = _job(finished_at="2026-11-01T11:00:00+00:00")
    state = derive_local_database_state(has_statements=True, jobs=[job], now=NOW)
    assert state["state"] == "stale"
    assert state["stale_reason"] == {"label": "ITR 3Q26", "due": "2026-11-14"}


def test_company_update_and_retry_do_not_reset_stale():
    full = _job(job_id="full", finished_at="2026-11-01T11:00:00+00:00")
    company = _job(job_id="company", scope="company", mode="single", finished_at="2026-11-24T11:00:00+00:00")
    retry = _job(job_id="retry", scope="retry", mode="failed", finished_at="2026-11-24T12:00:00+00:00")
    state = derive_local_database_state(has_statements=True, jobs=[full, company, retry], now=NOW)
    assert state["state"] == "stale"
    assert state["last_full_update_at"] == "2026-11-01T11:00:00+00:00"


def test_statements_without_any_full_update_are_stale():
    company = _job(scope="company", mode="single")
    state = derive_local_database_state(has_statements=True, jobs=[company], now=NOW)
    assert state["state"] == "stale"
    assert state["stale_reason"] == {"label": None, "due": None}


def test_last_full_update_with_some_failed_companies_is_partial():
    job = _job(state="error", queued=10, processed=10, failures=3)
    state = derive_local_database_state(has_statements=True, jobs=[job], now=NOW)
    assert state["state"] == "partial"
    assert state["last_run"]["failures"] == 3
    assert state["last_full_update_at"] == "2026-11-20T11:00:00+00:00"


def test_failed_first_run_without_statements_is_failed():
    job = _job(state="error", processed=0, failures=0, error="CVM unreachable")
    state = derive_local_database_state(has_statements=False, jobs=[job], now=NOW)
    assert state["state"] == "failed"
    assert state["last_run"]["error"] == "CVM unreachable"


def test_legacy_batch_job_with_many_companies_counts_as_full_update():
    legacy = _job(scope=None, params={"company_ids": [1, 2, 3], "limit": 100})
    legacy.pop("scope")
    state = derive_local_database_state(has_statements=True, jobs=[legacy], now=NOW)
    assert state["last_full_update_at"] == "2026-11-20T11:00:00+00:00"


# ---------- bridge contract ----------

def _bridge(tmp_path):
    settings = build_settings(project_root=tmp_path)
    bridge = CVMBridge()
    bridge._service = SimpleNamespace(settings=settings)
    return bridge, settings


def _schema_only_db(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE companies (cd_cvm INTEGER PRIMARY KEY, company_name TEXT)")
        conn.execute('CREATE TABLE financial_reports ("CD_CVM" INTEGER, "REPORT_YEAR" INTEGER)')
        conn.execute(
            "CREATE TABLE company_refresh_status (cd_cvm INTEGER PRIMARY KEY, last_success_at TEXT, last_attempt_at TEXT, last_error TEXT)"
        )


def test_bridge_reports_empty_for_schema_only_database(tmp_path):
    bridge, settings = _bridge(tmp_path)
    _schema_only_db(settings.paths.db_path)
    state = bridge.get_local_database_state()
    assert state["state"] == "empty"
    assert state["has_statements"] is False


def test_bridge_reports_failures_with_company_names(tmp_path):
    bridge, settings = _bridge(tmp_path)
    _schema_only_db(settings.paths.db_path)
    with sqlite3.connect(str(settings.paths.db_path)) as conn:
        conn.execute("INSERT INTO companies VALUES (4170, 'OI SA')")
        conn.execute("INSERT INTO financial_reports VALUES (4170, 2025)")
        conn.execute(
            "INSERT INTO company_refresh_status VALUES (4170, NULL, '2026-11-20T10:30:00+00:00', 'DFP 2024 rows rejected')"
        )
    jobs_path = settings.paths.data_dir / "refresh_jobs.json"
    jobs_path.write_text(json.dumps({"jobs": [_job(state="error", failures=1)]}), encoding="utf-8")
    state = bridge.get_local_database_state()
    assert state["state"] == "partial"
    assert state["failures"] == [{"cd_cvm": 4170, "company_name": "OI SA", "error": "DFP 2024 rows rejected"}]


def test_bridge_state_read_does_not_rewrite_running_jobs(tmp_path):
    bridge, settings = _bridge(tmp_path)
    _schema_only_db(settings.paths.db_path)
    jobs_path = settings.paths.data_dir / "refresh_jobs.json"
    original = json.dumps({"jobs": [_job(state="running", stage="download_extract", finished_at=None)]})
    jobs_path.write_text(original, encoding="utf-8")
    bridge.get_local_database_state()
    assert jobs_path.read_text(encoding="utf-8") == original


def test_summary_diagnostics_report_schema_only_database_as_empty(tmp_path):
    bridge, settings = _bridge(tmp_path)
    _schema_only_db(settings.paths.db_path)
    diagnostics = bridge.get_database_diagnostics({"summary_only": True})
    assert diagnostics["is_empty"] is True


def test_running_job_lists_its_companies_and_the_current_one():
    job = _job(
        state="running",
        stage="process_data",
        finished_at=None,
        current_cvm=4170,
        request={"companies": ["9512", "4170", "1023"], "start_year": 2022, "end_year": 2026},
    )
    state = derive_local_database_state(has_statements=True, jobs=[job], now=NOW)
    assert state["run"]["company_ids"] == [9512, 4170, 1023]
    assert state["run"]["current_cvm"] == 4170
