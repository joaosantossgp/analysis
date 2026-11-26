"""Local database state: one derived answer every surface renders.

Pure functions only: callers pass whether statements exist and the batch
refresh jobs they know about. No network and no file writes here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable

ACTIVE_STATES = {"queued", "running"}
FULL_SCOPES = {"data_update"}
RUN_SCOPES = {"data_update", "retry"}
FILE_STAGES = {"download_extract"}
COMPANY_STAGES = {"process_data", "persist_reports"}


@dataclass(frozen=True)
class FilingDeadline:
    label: str
    due: date


def _deadlines_for_year(year: int) -> list[FilingDeadline]:
    """CVM filing deadlines that fall in calendar ``year``.

    ITR: 45 days after each of the first three quarters. DFP: three months
    after the fiscal year end (fiscal year = calendar year).
    """
    yy = f"{year % 100:02d}"
    return [
        FilingDeadline(f"DFP {year - 1}", date(year, 3, 31)),
        FilingDeadline(f"ITR 1Q{yy}", date(year, 5, 15)),
        FilingDeadline(f"ITR 2Q{yy}", date(year, 8, 14)),
        FilingDeadline(f"ITR 3Q{yy}", date(year, 11, 14)),
    ]


def latest_passed_deadline(last_full_update: date | None, today: date) -> FilingDeadline | None:
    """Latest deadline after ``last_full_update`` and on or before ``today``."""
    if last_full_update is None:
        return None
    passed = [
        d
        for year in range(last_full_update.year, today.year + 1)
        for d in _deadlines_for_year(year)
        if last_full_update < d.due <= today
    ]
    return max(passed, key=lambda d: d.due) if passed else None


def _parse(ts: Any) -> datetime | None:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def job_scope(job: dict[str, Any]) -> str | None:
    """Scope of a batch job: data_update, retry, company or None."""
    scope = job.get("scope")
    if scope:
        return str(scope)
    # Legacy jobs (before scopes were recorded): a multi-company batch that is
    # not a failure retry was a data update started from the updates page.
    if str(job.get("mode") or "") == "failed":
        return "retry"
    company_ids = (job.get("params") or {}).get("company_ids") or []
    return "data_update" if len(company_ids) > 1 else None


def _is_partial(job: dict[str, Any]) -> bool:
    failures = int(job.get("failures") or 0)
    processed = int(job.get("processed") or 0)
    queued = int(job.get("queued") or 0)
    if str(job.get("state")) == "partial":
        return True
    return str(job.get("state")) == "error" and 0 < failures and processed > 0 and failures < max(queued, processed)


def _run_payload(job: dict[str, Any], now: datetime) -> dict[str, Any]:
    stage = str(job.get("stage") or "")
    if stage in FILE_STAGES:
        phase = "files"
    elif stage in COMPANY_STAGES:
        phase = "companies"
    elif stage == "finalizing":
        phase = "finalizing"
    else:
        phase = "starting"
    processed = int(job.get("processed") or 0)
    queued = int(job.get("queued") or 0)
    eta_seconds = None
    companies_started = _parse(job.get("companies_started_at"))
    if phase == "companies" and processed > 0 and companies_started is not None and queued > processed:
        elapsed = (now - companies_started).total_seconds()
        eta_seconds = int(round(elapsed / processed * (queued - processed)))
    return {
        "job_id": job.get("job_id"),
        "scope": job_scope(job),
        "phase": phase,
        "files_done": int(job.get("progress_current") or 0) if phase == "files" else None,
        "files_total": int(job.get("progress_total") or 0) if phase == "files" else None,
        "processed": processed,
        "queued": queued,
        "failures": int(job.get("failures") or 0),
        "started_at": job.get("started_at"),
        "eta_seconds": eta_seconds,
        # The run's companies in processing order, so the directory can mark
        # rows of this run only (never inferred for other companies).
        "company_ids": [
            int(code)
            for code in ((job.get("request") or {}).get("companies") or (job.get("params") or {}).get("company_ids") or [])
            if str(code).isdigit()
        ],
        "current_cvm": int(job["current_cvm"]) if str(job.get("current_cvm") or "").isdigit() else None,
    }


def _last_run_payload(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job.get("job_id"),
        "scope": job_scope(job),
        "state": "partial" if _is_partial(job) else job.get("state"),
        "finished_at": job.get("finished_at"),
        "queued": int(job.get("queued") or 0),
        "processed": int(job.get("processed") or 0),
        "failures": int(job.get("failures") or 0),
        "error": job.get("error"),
    }


def derive_local_database_state(
    *,
    has_statements: bool,
    jobs: Iterable[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    batch = [j for j in jobs if job_scope(j) in RUN_SCOPES]
    active = [j for j in batch if str(j.get("state")) in ACTIVE_STATES]
    terminal = sorted(
        (j for j in batch if str(j.get("state")) not in ACTIVE_STATES),
        key=lambda j: str(j.get("finished_at") or j.get("updated_at") or ""),
        reverse=True,
    )
    full_done = [
        j
        for j in terminal
        if job_scope(j) in FULL_SCOPES and (str(j.get("state")) == "success" or _is_partial(j))
    ]
    last_full_update_at = full_done[0].get("finished_at") if full_done else None
    last_run = terminal[0] if terminal else None

    stale_reason: dict[str, Any] | None = None
    if has_statements:
        last_full = _parse(last_full_update_at)
        if last_full is None:
            stale_reason = {"label": None, "due": None}
        else:
            deadline = latest_passed_deadline(last_full.date(), now.date())
            if deadline is not None:
                stale_reason = {"label": deadline.label, "due": deadline.due.isoformat()}

    run = _run_payload(active[0], now) if active else None
    if run is not None:
        state = "files" if run["phase"] in {"files", "starting"} else "updating"
    elif last_run is not None and _is_partial(last_run) and has_statements:
        state = "partial"
    elif last_run is not None and str(last_run.get("state")) == "error":
        state = "failed"
    elif not has_statements:
        state = "empty"
    elif stale_reason is not None:
        state = "stale"
    else:
        state = "current"

    return {
        "state": state,
        "has_statements": bool(has_statements),
        "last_full_update_at": last_full_update_at,
        "stale_reason": stale_reason,
        "run": run,
        "last_run": _last_run_payload(last_run) if last_run is not None else None,
        "generated_at": now.replace(microsecond=0).isoformat(),
    }


def read_local_database_facts(engine: Any) -> tuple[bool, list[dict[str, Any]]]:
    """Whether statements exist, plus companies whose last refresh failed.

    ``engine`` is a SQLAlchemy engine; reads only, cheap existence checks.
    """
    from sqlalchemy import inspect, text  # noqa: PLC0415

    present = set(inspect(engine).get_table_names())
    has_statements = False
    failures: list[dict[str, Any]] = []
    with engine.connect() as conn:
        if "financial_reports" in present:
            has_statements = bool(
                conn.execute(text("SELECT EXISTS(SELECT 1 FROM financial_reports)")).scalar()
            )
        if "company_refresh_status" in present:
            name_col, join = ("c.company_name", "LEFT JOIN companies c ON c.cd_cvm = s.cd_cvm") if "companies" in present else ("NULL", "")
            rows = conn.execute(
                text(
                    f"SELECT s.cd_cvm, {name_col}, s.last_error FROM company_refresh_status s {join} "
                    "WHERE s.last_error IS NOT NULL AND s.last_error <> '' "
                    "ORDER BY s.last_attempt_at DESC LIMIT 50"
                )
            ).fetchall()
            failures = [{"cd_cvm": int(r[0]), "company_name": r[1], "error": str(r[2])} for r in rows]
    return has_statements, failures
