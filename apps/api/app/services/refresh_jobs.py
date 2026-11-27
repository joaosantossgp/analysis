from __future__ import annotations

from typing import Any

from src.platform.settings import AppSettings
from src.refresh.batch_jobs import BatchRefreshJobManager
from src.refresh.service import HeadlessRefreshService


class RefreshBatchRequestError(ValueError):
    """Raised when the batch refresh request is not executable."""


class ApiRefreshJobManager(BatchRefreshJobManager):
    """In-process background queue for API-triggered batch refreshes."""

    TERMINAL_STATES = {"success", "error", "cancelled"}
    THREAD_NAME_PREFIX = "api-refresh"
    LOG_LABEL = "Refresh em lote"
    ERROR_TYPE = RefreshBatchRequestError
    SUPPORT_PARTIAL_STATE = False

    def __init__(
        self,
        *,
        settings: AppSettings,
        read_service: Any,
        refresh_service: HeadlessRefreshService | None = None,
        autostart: bool = True,
    ) -> None:
        super().__init__(
            settings=settings,
            read_service=read_service,
            refresh_service=refresh_service or HeadlessRefreshService(settings=settings),
            jobs_path=None,
            autostart=autostart,
        )

    def request_refresh(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._enqueue_batch_refresh(params, raise_on_invalid=True)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(str(job_id))
            return self._public_job(job) if job is not None else None

    def list_jobs(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        with self._lock:
            jobs = [self._public_job(job) for job in self._jobs.values()]
        if active_only:
            jobs = [
                job for job in jobs if str(job.get("state") or "") in self.ACTIVE_STATES
            ]
        jobs.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return jobs

    def cancel_job(self, job_id: str) -> dict[str, Any] | None:
        resolved_job_id = str(job_id or "")
        if not resolved_job_id:
            return None

        with self._lock:
            job = self._jobs.get(resolved_job_id)
            if job is None:
                return None

            state = str(job.get("state") or "")
            if state in self.TERMINAL_STATES:
                return {
                    "ok": False,
                    "job_id": resolved_job_id,
                    "state": state,
                    "status": state,
                    "message": f"Job de refresh {resolved_job_id} ja esta finalizado como {state}.",
                    "status_reason_code": "already_terminal",
                    "is_retry_allowed": False,
                }

            cancel_event = self._cancel_events.get(resolved_job_id)
            if cancel_event is not None:
                cancel_event.set()

            if state == "queued" and resolved_job_id not in self._threads:
                now = self._now_iso()
                job["state"] = "cancelled"
                job["status"] = "cancelled"
                job["finished_at"] = now
                job["updated_at"] = now
                self._append_log_locked(job, "Refresh em lote cancelado antes da execucao.")
                return {
                    "ok": True,
                    "job_id": resolved_job_id,
                    "state": "cancelled",
                    "status": "cancelled",
                    "message": "Refresh em lote cancelado antes da execucao.",
                    "status_reason_code": "cancelled",
                    "is_retry_allowed": False,
                }

            self._append_log_locked(job, "Cancelamento solicitado.")
            job["updated_at"] = self._now_iso()
            return {
                "ok": True,
                "job_id": resolved_job_id,
                "state": str(job.get("state") or state),
                "status": str(job.get("status") or job.get("state") or state),
                "message": "Cancelamento solicitado para o refresh em lote.",
                "status_reason_code": "cancel_requested",
                "is_retry_allowed": False,
            }

    @staticmethod
    def _public_job(job: dict[str, Any], *, include_result: bool = True) -> dict[str, Any]:
        return {
            "job_id": job.get("job_id"),
            "state": job.get("state"),
            "status": job.get("status") or job.get("state"),
            "stage": job.get("stage"),
            "queued": int(job.get("queued") or 0),
            "processed": int(job.get("processed") or 0),
            "failures": int(job.get("failures") or 0),
            "current_cvm": job.get("current_cvm"),
            "progress_current": job.get("progress_current"),
            "progress_total": job.get("progress_total"),
            "log_lines": list(job.get("log_lines") or []),
            "accepted_at": job.get("accepted_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "updated_at": job.get("updated_at"),
            "error": job.get("error"),
            "result": job.get("result") if include_result else None,
        }
