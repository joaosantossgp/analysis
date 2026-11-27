"""Unified in-process batch refresh job engine shared by Desktop and HTTP API."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable
from uuid import uuid4

from src.financials.utils import now_iso_seconds
from src.platform.contracts import RefreshPolicy, RefreshProgressUpdate, RefreshRequest
from src.platform.settings import AppSettings, build_settings
from src.refresh.job_projection import persistable_batch_job, public_batch_job
from src.refresh.local_database_state import COMPANY_STAGES
from src.refresh.service import HeadlessRefreshService


class BatchRefreshJobManager:
    """Shared background batch-refresh queue with optional JSON persistence."""

    VALID_MODES = {"full", "missing", "outdated", "failed"}
    ACTIVE_STATES = {"queued", "running"}
    TERMINAL_STATES = {"success", "partial", "error", "cancelled", "interrupted"}
    DEFAULT_START_YEAR = 2010
    MAX_LOG_LINES = 200
    MAX_STORED_JOBS = 50
    # Progress-only updates are written at most this often; state changes always are.
    SAVE_INTERVAL_SECONDS = 2.0
    THREAD_NAME_PREFIX = "batch-refresh"
    LOG_LABEL = "Refresh"
    ERROR_TYPE: type[Exception] = ValueError
    SUPPORT_PARTIAL_STATE = True

    def __init__(
        self,
        *,
        settings: AppSettings | None = None,
        read_service: Any | None = None,
        refresh_service: HeadlessRefreshService | None = None,
        jobs_path: Path | None = None,
        autostart: bool = True,
        on_job_finished: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings or build_settings()
        self.on_job_finished = on_job_finished
        self._last_save_monotonic = 0.0
        self.read_service = read_service
        self._refresh_service = refresh_service
        self.jobs_path = jobs_path
        self.autostart = bool(autostart)
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._jobs: dict[str, dict[str, Any]] = self._load_jobs() if self.jobs_path is not None else {}
        if self.jobs_path is not None:
            self._mark_unfinished_jobs_interrupted()

    @property
    def refresh_service(self) -> HeadlessRefreshService:
        if self._refresh_service is None:
            self._refresh_service = HeadlessRefreshService(settings=self.settings)
        return self._refresh_service

    @refresh_service.setter
    def refresh_service(self, value: HeadlessRefreshService | None) -> None:
        self._refresh_service = value

    def _enqueue_batch_refresh(
        self,
        params: dict[str, Any] | None = None,
        *,
        raise_on_invalid: bool = False,
    ) -> dict[str, Any]:
        p = dict(params or {})
        mode = str(p.get("mode") or "missing").strip().lower()
        if mode not in self.VALID_MODES:
            msg = f"Modo de refresh invalido: {mode}"
            if raise_on_invalid:
                raise self.ERROR_TYPE(msg)
            return {
                "status": "error",
                "job_id": None,
                "message": msg,
                "status_reason_code": "invalid_mode",
                "is_retry_allowed": True,
            }

        try:
            selection = self._resolve_batch_selection(p, mode=mode)
            companies = list(selection.companies)
            start_year, end_year = selection.start_year, selection.end_year
        except Exception as exc:
            if raise_on_invalid:
                if isinstance(exc, self.ERROR_TYPE):
                    raise
                if isinstance(exc, ValueError):
                    raise self.ERROR_TYPE(str(exc)) from exc
                raise
            return {
                "status": "error",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "invalid_request",
                "is_retry_allowed": True,
            }

        if not companies:
            now = self._now_iso()
            return {
                "status": "already_current",
                "job_id": None,
                "accepted_at": now,
                "queued": 0,
                "message": "Nenhuma empresa elegivel para refresh.",
                "status_reason_code": "empty_scope",
                "is_retry_allowed": False,
            }

        with self._lock:
            active_job = self._find_active_job()
            if active_job is not None:
                return {
                    "status": "already_running",
                    "job_id": active_job["job_id"],
                    "accepted_at": active_job.get("accepted_at") or "",
                    "queued": int(active_job.get("queued") or 0),
                    "message": "Ja existe um refresh em andamento.",
                    "status_reason_code": "already_running",
                    "is_retry_allowed": False,
                }

            job_id = uuid4().hex
            now = self._now_iso()
            job = {
                "job_id": job_id,
                "state": "queued",
                "status": "queued",
                "mode": mode,
                "accepted_at": now,
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "finished_at": None,
                "queued": len(companies),
                "processed": 0,
                "failures": 0,
                "current_cvm": None,
                "stage": None,
                "progress_current": None,
                "progress_total": None,
                "log_lines": [f"{self.LOG_LABEL} enfileirado."],
                "params": p,
                "scope": p.get("scope"),
                "request": {
                    "companies": [str(company) for company in companies],
                    "start_year": int(start_year),
                    "end_year": int(end_year),
                },
                "error": None,
                "result": None,
            }
            self._jobs[job_id] = job
            self._save_jobs()

        if self.autostart:
            self._start_job(job_id)

        return {
            "status": "running" if self.autostart else "queued",
            "job_id": job_id,
            "accepted_at": now,
            "queued": len(companies),
            "message": f"{self.LOG_LABEL} iniciado em background.",
            "status_reason_code": "refresh_started",
            "is_retry_allowed": False,
        }

    def _start_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.get("state") != "queued" or job_id in self._threads:
                return
            cancel_event = threading.Event()
            thread = threading.Thread(
                target=self._run_job,
                args=(job_id, cancel_event),
                name=f"{self.THREAD_NAME_PREFIX}-{job_id[:8]}",
                daemon=True,
            )
            self._cancel_events[job_id] = cancel_event
            self._threads[job_id] = thread
        thread.start()

    def _run_job(self, job_id: str, cancel_event: threading.Event) -> None:
        if cancel_event.is_set():
            self._update_job(
                job_id,
                state="cancelled",
                status="cancelled",
                finished_at=self._now_iso(),
                log_line=f"{self.LOG_LABEL} cancelado antes da execucao.",
            )
            self._cleanup_job_runtime(job_id)
            return

        self._update_job(
            job_id,
            state="running",
            status="running",
            started_at=self._now_iso(),
            log_line=f"{self.LOG_LABEL} em execucao.",
        )
        try:
            with self._lock:
                job = dict(self._jobs[job_id])
            request_payload = dict(job["request"])
            mode = str(job.get("mode") or "missing")
            scope = job.get("scope")
            request = RefreshRequest(
                companies=tuple(str(item) for item in request_payload["companies"]),
                start_year=int(request_payload["start_year"]),
                end_year=int(request_payload["end_year"]),
                policy=RefreshPolicy(
                    skip_complete_company_years=mode != "full",
                    # A data update honors its history range; the fast lane is
                    # for other "missing" batches only.
                    enable_fast_lane=mode == "missing" and scope != "data_update",
                    reuse_catalog_snapshot=scope in {"data_update", "retry"},
                    force_refresh=mode == "full",
                ),
            )
            result = self.refresh_service.execute(
                request,
                progress_callback=lambda current, total, message: self._handle_progress(
                    job_id,
                    current=current,
                    total=total,
                    message=message,
                ),
                stage_callback=lambda update: self._handle_stage(job_id, update),
                should_cancel=cancel_event.is_set,
            )
        except Exception as exc:
            self._update_job(
                job_id,
                state="error",
                status="error",
                finished_at=self._now_iso(),
                error=f"{exc.__class__.__name__}: {exc}",
                log_line=f"Falha no {self.LOG_LABEL.lower()}: {exc}",
            )
            self._cleanup_job_runtime(job_id)
            return

        failures = int(result.error_count)
        failed_codes = [
            str(row.cvm_code)
            for row in result.companies
            if row.status not in {"success", "no_data"}
        ]
        if failed_codes and not result.cancelled and scope == "data_update" and not cancel_event.is_set():
            # Retry failed companies once inside the run, so it never depends on a page being open.
            self._update_job(job_id, log_line=f"Retrying {len(failed_codes)} failed companies once.")
            try:
                retry = self.refresh_service.execute(
                    replace(request, companies=tuple(failed_codes)),
                    stage_callback=lambda update: self._handle_stage(job_id, update),
                    should_cancel=cancel_event.is_set,
                )
                failures = int(retry.error_count)
            except Exception as exc:
                self._append_log(job_id, f"Retry failed: {exc}")

        processed = len(result.companies)
        if result.cancelled:
            state = "cancelled"
        elif not failures:
            state = "success"
        elif self.SUPPORT_PARTIAL_STATE and failures < processed:
            state = "partial"
        else:
            state = "error"
        self._update_job(
            job_id,
            state=state,
            status=state,
            processed=processed,
            failures=failures,
            finished_at=self._now_iso(),
            result=result.to_dict(),
            log_line=f"{self.LOG_LABEL} cancelado." if state == "cancelled" else f"{self.LOG_LABEL} finalizado.",
        )
        self._cleanup_job_runtime(job_id)
        if self.on_job_finished is not None:
            try:
                self.on_job_finished(job_id)
            except Exception:
                pass

    def _cleanup_job_runtime(self, job_id: str) -> None:
        with self._lock:
            self._threads.pop(job_id, None)
            self._cancel_events.pop(job_id, None)

    def _resolve_batch_selection(self, params: dict[str, Any], *, mode: str):
        from src.financials.read_service import resolve_refresh_batch_selection  # noqa: PLC0415

        return resolve_refresh_batch_selection(
            self._read_service(),
            params,
            mode=mode,
            default_start_year=self.DEFAULT_START_YEAR,
        )

    def _read_service(self):
        if self.read_service is None:
            from src.financials.read_service import CVMReadService  # noqa: PLC0415

            self.read_service = CVMReadService(settings=self.settings)
        return self.read_service

    def _find_active_job(self) -> dict[str, Any] | None:
        with self._lock:
            for job in self._jobs.values():
                if str(job.get("state") or "") in self.ACTIVE_STATES:
                    return self._public_job(job)
        return None

    def snapshot_jobs(self) -> list[dict[str, Any]]:
        """Copies of every job, including stage progress, for state derivation."""
        with self._lock:
            return [dict(job) for job in self._jobs.values()]

    def _handle_stage(self, job_id: str, update: RefreshProgressUpdate) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            # Set once: the stage alternates per company, the ETA needs the whole phase (#578).
            enters_companies = (
                job is not None and update.stage in COMPANY_STAGES and not job.get("companies_started_at")
            )
        self._update_job(
            job_id,
            stage=update.stage,
            companies_started_at=self._now_iso() if enters_companies else None,
            progress_current=int(update.current),
            progress_total=max(1, int(update.total)),
            log_line=update.message,
        )

    def _handle_progress(
        self,
        job_id: str,
        *,
        current: int,
        total: int,
        message: str,
    ) -> None:
        current_cvm = self._extract_current_cvm(message)
        self._update_job(
            job_id,
            processed=max(0, int(current) - 1),
            progress_current=int(current),
            progress_total=max(1, int(total)),
            current_cvm=current_cvm,
            log_line=message,
        )

    @staticmethod
    def _extract_current_cvm(message: str) -> int | None:
        for token in str(message or "").replace("=", " ").split():
            if token.isdigit():
                return int(token)
        return None

    def _update_job(self, job_id: str, **changes: Any) -> None:
        log_line = changes.pop("log_line", None)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            state_changed = "state" in changes and changes["state"] != job.get("state")
            for key, value in changes.items():
                if value is not None or key in {"current_cvm", "error", "finished_at"}:
                    job[key] = value
            job["updated_at"] = self._now_iso()
            if log_line:
                self._append_log_locked(job, str(log_line))
            if state_changed or time.monotonic() - self._last_save_monotonic >= self.SAVE_INTERVAL_SECONDS:
                self._save_jobs()

    def _append_log(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            self._append_log_locked(job, message)
            job["updated_at"] = self._now_iso()
            self._save_jobs()

    @classmethod
    def _append_log_locked(cls, job: dict[str, Any], message: str) -> None:
        log_lines = list(job.get("log_lines") or [])
        log_lines.append(message)
        job["log_lines"] = log_lines[-cls.MAX_LOG_LINES :]

    def _load_jobs(self) -> dict[str, dict[str, Any]]:
        if self.jobs_path is None or not self.jobs_path.exists():
            return {}
        try:
            payload = json.loads(self.jobs_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
            jobs: dict[str, dict[str, Any]] = {}
            changed = False
            for job in payload["jobs"]:
                if not isinstance(job, dict) or not job.get("job_id"):
                    continue
                normalized = self._persistable_job(job)
                if normalized != job:
                    changed = True
                jobs[str(normalized.get("job_id"))] = normalized
            if changed:
                self._jobs = jobs
                self._save_jobs()
            return jobs
        return {}

    def _save_jobs(self) -> None:
        if self.jobs_path is None:
            return
        self.jobs_path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(
            self._jobs.values(),
            key=lambda row: str(row.get("created_at") or ""),
            reverse=True,
        )
        active = [job for job in ordered if str(job.get("state")) not in self.TERMINAL_STATES]
        finished = [job for job in ordered if str(job.get("state")) in self.TERMINAL_STATES]
        kept = active + finished[: max(0, self.MAX_STORED_JOBS - len(active))]
        for stale in ordered:
            if stale not in kept:
                self._jobs.pop(str(stale.get("job_id")), None)
        jobs = [self._persistable_job(job) for job in kept]
        self._last_save_monotonic = time.monotonic()
        self.jobs_path.write_text(
            json.dumps({"jobs": jobs}, ensure_ascii=True, indent=2, default=str),
            encoding="utf-8",
        )

    def _persistable_job(self, job: dict[str, Any]) -> dict[str, Any]:
        return persistable_batch_job(job, max_log_lines=self.MAX_LOG_LINES)

    def _mark_unfinished_jobs_interrupted(self) -> None:
        changed = False
        for job in self._jobs.values():
            if str(job.get("state")) in self.ACTIVE_STATES:
                job["state"] = "interrupted"
                job["finished_at"] = self._now_iso()
                job["updated_at"] = job["finished_at"]
                job["error"] = "The app closed before the data update finished."
                self._append_log_locked(job, job["error"])
                changed = True
        if changed:
            self._save_jobs()

    @staticmethod
    def _public_job(job: dict[str, Any], *, include_result: bool = False) -> dict[str, Any]:
        return public_batch_job(job, include_result=include_result)

    @staticmethod
    def _now_iso() -> str:
        return now_iso_seconds()
