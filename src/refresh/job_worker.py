from __future__ import annotations

import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy import text

from src.platform.contracts import (
    RefreshProgressUpdate,
    RefreshRequest,
    default_incremental_refresh_policy,
)
from src.platform.db import build_engine
from src.platform.observability import log_event
from src.refresh.jobs import (
    JOB_STATE_ERROR,
    JOB_STATE_NO_DATA,
    JOB_STATE_SUCCESS,
    RefreshJobRecord,
    RefreshJobRepository,
)
from src.refresh.service import HeadlessRefreshService
from src.financials.source_cache import AnnualSourceCache
from src.platform.settings import AppSettings, get_settings


def _default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


@dataclass(frozen=True)
class RefreshWorkerConfig:
    worker_id: str = field(default_factory=_default_worker_id)
    poll_interval_seconds: float = 2.0
    heartbeat_interval_seconds: float = 5.0
    lease_seconds: int = 60
    max_attempts: int = 3


class _HeartbeatLoop:
    def __init__(
        self,
        *,
        repository: RefreshJobRepository,
        job_id: str,
        interval_seconds: float,
        logger: logging.Logger,
    ) -> None:
        self.repository = repository
        self.job_id = str(job_id)
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.logger = logger
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"refresh-heartbeat-{self.job_id[:8]}",
            daemon=True,
        )

    def __enter__(self) -> "_HeartbeatLoop":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop_event.set()
        self._thread.join(timeout=self.interval_seconds + 1.0)

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self.repository.heartbeat(job_id=self.job_id)
            except Exception:
                self.logger.exception(
                    "refresh_job_heartbeat_failed job_id=%s",
                    self.job_id,
                )


class RefreshJobWorker:
    SOURCE_CACHE_SECONDS = 60.0

    def __init__(
        self,
        *,
        settings: AppSettings | None = None,
        repository: RefreshJobRepository | None = None,
        refresh_service: HeadlessRefreshService | None = None,
        logger: logging.Logger | None = None,
        config: RefreshWorkerConfig | None = None,
        worker_heartbeat_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.logger = logger or logging.getLogger(__name__)
        self.repository = repository or RefreshJobRepository(build_engine(self.settings))
        self.refresh_service = refresh_service or HeadlessRefreshService(
            settings=self.settings,
            logger=self.logger,
        )
        self.config = config or RefreshWorkerConfig()
        self.worker_heartbeat_callback = worker_heartbeat_callback
        self._source_cache: AnnualSourceCache | None = None
        self._source_job_ids: set[str] = set()
        self._source_scope = None
        self._source_admitted_at = 0.0

    @property
    def engine(self):
        return self.repository.engine

    def run_forever(self, *, stop_event: threading.Event | None = None) -> None:
        self.repository.ensure_schema()
        log_event(
            self.logger,
            "refresh-worker-started",
            worker_id=self.config.worker_id,
            poll_interval_seconds=self.config.poll_interval_seconds,
            heartbeat_interval_seconds=self.config.heartbeat_interval_seconds,
            lease_seconds=self.config.lease_seconds,
            max_attempts=self.config.max_attempts,
        )
        self._emit_worker_heartbeat("running")
        try:
            while stop_event is None or not stop_event.is_set():
                claimed = self.run_once()
                if claimed:
                    continue
                self._emit_worker_heartbeat("idle")
                wait_seconds = max(0.2, float(self.config.poll_interval_seconds))
                if stop_event is not None:
                    stop_event.wait(wait_seconds)
                else:
                    time.sleep(wait_seconds)
        finally:
            self._clear_source_cache()
            self._emit_worker_heartbeat("stopped")

    def run_once(self) -> bool:
        self._emit_worker_heartbeat("running")
        recovered = self.repository.recover_stale_jobs(
            lease_seconds=self.config.lease_seconds,
            max_attempts=self.config.max_attempts,
        )
        if recovered:
            self._clear_source_cache()
            log_event(
                self.logger,
                "refresh-worker-recovered-stale-jobs",
                worker_id=self.config.worker_id,
                recovered=recovered,
            )

        job = self.repository.claim_next_job(worker_id=self.config.worker_id)
        if job is None:
            self._clear_source_cache()
            return False

        try:
            self._run_job(job)
        except BaseException:
            self._clear_source_cache()
            raise
        finally:
            self._source_job_ids.discard(job.id)
            if not self._source_job_ids:
                self._clear_source_cache()
        return True

    def _clear_source_cache(self) -> None:
        if self._source_cache is not None:
            self._source_cache.clear()
        self._source_cache = None
        self._source_job_ids.clear()

    def _source_cache_for(self, job, request):
        scope = (job.source_scope, job.start_year, job.end_year, request.report_type,
                 request.data_dir, request.policy)
        if self._source_cache is not None and (
            job.id not in self._source_job_ids or self._source_scope != scope
            or time.monotonic() - self._source_admitted_at > self.SOURCE_CACHE_SECONDS
            or not self._source_cache.active
        ):
            self._clear_source_cache()
        if job.attempt_count > 1 or request.policy.force_refresh or os.getenv("CVM_FORCE_REFRESH") == "1":
            self._clear_source_cache()
            return None
        if self._source_cache is None:
            jobs = [job]
            next_job = self.repository.peek_next_job()
            if next_job is not None and not next_job.attempt_count and (
                next_job.source_scope, next_job.start_year, next_job.end_year
            ) == (job.source_scope, job.start_year, job.end_year):
                jobs.append(next_job)
            self._source_cache = AnnualSourceCache(tuple(item.cd_cvm for item in jobs))
            self._source_job_ids = {item.id for item in jobs}
            self._source_scope = scope
            self._source_admitted_at = time.monotonic()
        return self._source_cache

    def _emit_worker_heartbeat(self, state: str) -> None:
        if self.worker_heartbeat_callback is None:
            return
        try:
            self.worker_heartbeat_callback(str(state))
        except Exception:
            self.logger.exception(
                "refresh_worker_heartbeat_callback_failed worker_id=%s",
                self.config.worker_id,
            )

    def _run_job(self, job: RefreshJobRecord) -> None:
        log_event(
            self.logger,
            "refresh-worker-claimed-job",
            worker_id=self.config.worker_id,
            job_id=job.id,
            cd_cvm=job.cd_cvm,
            start_year=job.start_year,
            end_year=job.end_year,
            attempt_count=job.attempt_count,
        )
        try:
            request = self._build_request(job)
            with _HeartbeatLoop(
                repository=self.repository,
                job_id=job.id,
                interval_seconds=self.config.heartbeat_interval_seconds,
                logger=self.logger,
            ):
                result = self.refresh_service.execute(
                    request,
                    stage_callback=lambda update: self._handle_stage_progress(
                        job.id,
                        update,
                    ),
                    persist_refresh_status=False,
                    source_cache=self._source_cache_for(job, request),
                )
        except Exception as exc:
            self._clear_source_cache()
            error_message = f"{exc.__class__.__name__}: {exc}"
            self.logger.exception(
                "refresh-worker-job-failed job_id=%s cd_cvm=%s",
                job.id,
                job.cd_cvm,
            )
            self.repository.complete_job(
                job_id=job.id,
                final_state=JOB_STATE_ERROR,
                message=error_message,
                error_message=error_message,
            )
            return

        if result.cancelled or result.error_count or any(item.attempts > 1 for item in result.companies):
            self._clear_source_cache()

        if not result.companies:
            rows_inserted = self._count_rows_in_range(
                cd_cvm=job.cd_cvm,
                start_year=job.start_year,
                end_year=job.end_year,
            )
            self.repository.complete_job(
                job_id=job.id,
                final_state=JOB_STATE_SUCCESS,
                message=(
                    "Empresa ja atualizada para "
                    f"{job.start_year}-{job.end_year}."
                ),
                last_rows_inserted=rows_inserted,
            )
            return

        company_result = next(
            (
                item
                for item in result.companies
                if int(item.cvm_code) == int(job.cd_cvm)
            ),
            result.companies[0],
        )
        if company_result.status == JOB_STATE_SUCCESS:
            rows_inserted = int(company_result.rows_inserted or 0)
            if rows_inserted <= 0:
                rows_inserted = self._count_rows_in_range(
                    cd_cvm=job.cd_cvm,
                    start_year=job.start_year,
                    end_year=job.end_year,
                )
            final_state, completion_message = self._resolve_public_success_state(
                job,
                rows_inserted=rows_inserted,
            )
            self.repository.complete_job(
                job_id=job.id,
                final_state=final_state,
                message=completion_message,
                last_rows_inserted=rows_inserted if final_state == JOB_STATE_SUCCESS else None,
            )
            return

        if company_result.status == JOB_STATE_NO_DATA:
            self.repository.complete_job(
                job_id=job.id,
                final_state=JOB_STATE_NO_DATA,
                message=(
                    "Nenhuma demonstracao encontrada para "
                    f"{job.start_year}-{job.end_year}."
                ),
            )
            return

        error_message = str(
            company_result.error
            or "Falha operacional ao processar o refresh."
        )
        self.repository.complete_job(
            job_id=job.id,
            final_state=JOB_STATE_ERROR,
            message=error_message,
            error_message=error_message,
        )

    def _build_request(self, job: RefreshJobRecord) -> RefreshRequest:
        return RefreshRequest(
            companies=(str(job.cd_cvm),),
            start_year=int(job.start_year),
            end_year=int(job.end_year),
            policy=default_incremental_refresh_policy(),
        )

    def _resolve_public_success_state(
        self,
        job: RefreshJobRecord,
        *,
        rows_inserted: int,
    ) -> tuple[str, str]:
        snapshot = self.repository.load_read_model_snapshot(cd_cvm=job.cd_cvm)
        baseline_fingerprint = str(job.baseline_read_model_fingerprint or "").strip()
        read_model_changed = (
            snapshot.fingerprint != baseline_fingerprint
            if baseline_fingerprint
            else snapshot.readable_years_count > 0 and int(rows_inserted) > 0
        )
        if read_model_changed:
            return (
                JOB_STATE_SUCCESS,
                (
                    "Refresh concluido com leitura pronta para "
                    f"{job.start_year}-{job.end_year}."
                ),
            )
        return (
            JOB_STATE_NO_DATA,
            (
                "Nenhuma nova leitura anual ficou disponivel para "
                f"{job.start_year}-{job.end_year}."
            ),
        )

    def _handle_stage_progress(
        self,
        job_id: str,
        update: RefreshProgressUpdate,
    ) -> None:
        self.repository.update_progress(
            job_id=job_id,
            stage=update.stage,
            current=update.current,
            total=update.total,
            message=update.message,
        )

    def _count_rows_in_range(
        self,
        *,
        cd_cvm: int,
        start_year: int,
        end_year: int,
    ) -> int:
        with self.engine.connect() as conn:
            total = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS total
                    FROM financial_reports
                    WHERE "CD_CVM" = :cd_cvm
                      AND "REPORT_YEAR" BETWEEN :start_year AND :end_year
                    """
                ),
                {
                    "cd_cvm": int(cd_cvm),
                    "start_year": int(start_year),
                    "end_year": int(end_year),
                },
            ).scalar()
        return int(total or 0)
