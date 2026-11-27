"""Shared refresh job projection and payload shaping helpers.

Single source of truth for reading single-company DB worker rows from the
``refresh_jobs`` table (both SQLAlchemy and lightweight read-only SQLite) and
normalizing batch/DB-worker jobs into the public bridge payload shape.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import text

from src.refresh.jobs import ensure_refresh_runtime_tables_for_connection

DEFAULT_MAX_LOG_LINES = 200
DEFAULT_DB_WORKER_HISTORY_LIMIT = 10


def persistable_batch_job(
    job: dict[str, Any],
    *,
    max_log_lines: int = DEFAULT_MAX_LOG_LINES,
) -> dict[str, Any]:
    payload = dict(job)
    payload["result"] = None
    payload["log_lines"] = list(payload.get("log_lines") or [])[-max_log_lines:]
    return payload


def public_batch_job(
    job: dict[str, Any],
    *,
    include_result: bool = False,
) -> dict[str, Any]:
    payload = {
        "job_id": job.get("job_id"),
        "state": job.get("state"),
        "status": job.get("state"),
        "mode": job.get("mode"),
        "stage": job.get("stage"),
        "queued": int(job.get("queued") or 0),
        "processed": int(job.get("processed") or 0),
        "failures": int(job.get("failures") or 0),
        "current_cvm": job.get("current_cvm"),
        "log_lines": list(job.get("log_lines") or []),
        "accepted_at": job.get("accepted_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "updated_at": job.get("updated_at"),
        "error": job.get("error"),
        "result": None,
    }
    if include_result:
        payload["result"] = job.get("result")
    return payload


def db_worker_row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a ``refresh_jobs`` DB row to the public refresh-job shape."""
    state = str(row.get("state") or "").strip().lower()
    if state in {"no_data"}:
        state = "success"
    elif state in {"error", "failed"}:
        state = "error"
    progress_total = int(row.get("progress_total") or 1) or 1
    progress_current = int(row.get("progress_current") or 0)
    message = row.get("progress_message") or row.get("error_message") or ""
    log_lines = [str(message)] if message else []
    return {
        "job_id": str(row.get("id") or ""),
        "state": state,
        "status": state,
        "mode": "single",
        "stage": row.get("stage"),
        "queued": 1,
        "processed": 1 if state in {"success", "error", "cancelled"} else progress_current,
        "failures": 1 if state == "error" else 0,
        "current_cvm": int(row.get("cd_cvm")) if row.get("cd_cvm") is not None else None,
        "log_lines": log_lines,
        "accepted_at": row.get("requested_at"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "updated_at": (
            row.get("finished_at")
            or row.get("heartbeat_at")
            or row.get("started_at")
            or row.get("requested_at")
        ),
        "error": row.get("error_message"),
        "result": None,
        "source": "db_worker",
        "progress_current": progress_current,
        "progress_total": progress_total,
    }


def list_db_worker_jobs(
    engine: Any,
    *,
    limit: int = DEFAULT_DB_WORKER_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    """Query active plus recent terminal DB-worker jobs via SQLAlchemy engine."""
    try:
        with engine.connect() as conn:
            ensure_refresh_runtime_tables_for_connection(conn)
            active_rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM refresh_jobs
                    WHERE state IN ('queued', 'running')
                    ORDER BY requested_at DESC, id ASC
                    """
                )
            ).mappings().all()
            terminal_rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM refresh_jobs
                    WHERE state NOT IN ('queued', 'running')
                    ORDER BY COALESCE(finished_at, requested_at) DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).mappings().all()
    except Exception:
        return []
    return [db_worker_row_to_public(dict(row)) for row in (*active_rows, *terminal_rows)]


def lookup_db_worker_job(engine: Any, job_id: str) -> dict[str, Any] | None:
    """Look up a single DB-worker job row by id via SQLAlchemy engine."""
    try:
        with engine.connect() as conn:
            ensure_refresh_runtime_tables_for_connection(conn)
            row = conn.execute(
                text("SELECT * FROM refresh_jobs WHERE id = :id"),
                {"id": str(job_id)},
            ).mappings().fetchone()
    except Exception:
        return None
    if row is None:
        return None
    return db_worker_row_to_public(dict(row))


def list_db_worker_jobs_sqlite(
    db_path: Path,
    *,
    job_id: str | None = None,
    limit: int = DEFAULT_DB_WORKER_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    """Read-only SQLite lookup used by the lightweight bridge status path."""
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            exists = cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='refresh_jobs'"
            ).fetchone()
            if not exists:
                return []
            if job_id:
                row = cur.execute(
                    "SELECT * FROM refresh_jobs WHERE id = ?",
                    (str(job_id),),
                ).fetchone()
                return [db_worker_row_to_public(dict(row))] if row is not None else []
            active_rows = cur.execute(
                """
                SELECT *
                FROM refresh_jobs
                WHERE state IN ('queued', 'running')
                ORDER BY requested_at DESC, id ASC
                """
            ).fetchall()
            terminal_rows = cur.execute(
                """
                SELECT *
                FROM refresh_jobs
                WHERE state NOT IN ('queued', 'running')
                ORDER BY COALESCE(finished_at, requested_at) DESC, id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [db_worker_row_to_public(dict(row)) for row in (*active_rows, *terminal_rows)]
    except Exception:
        return []
