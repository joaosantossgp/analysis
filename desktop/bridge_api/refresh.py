from __future__ import annotations

import base64
import dataclasses
import json
import logging
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("desktop.bridge")


class RefreshBridgeMixin:
    @staticmethod
    def _persistable_refresh_job(job: dict[str, Any]) -> dict[str, Any]:
        payload = dict(job)
        payload["result"] = None
        payload["log_lines"] = list(payload.get("log_lines") or [])[-200:]
        return payload

    @staticmethod
    def _public_refresh_job(
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

    @staticmethod
    def _db_worker_refresh_job_to_public(row: dict[str, Any]) -> dict[str, Any]:
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

    @staticmethod
    def _refresh_jobs_path() -> Path:
        from src.platform.settings import get_settings  # noqa: PLC0415

        return get_settings().paths.data_dir / "refresh_jobs.json"

    def _load_refresh_jobs_light(self) -> dict[str, dict[str, Any]]:
        jobs_path = self._refresh_jobs_path()
        if not jobs_path.exists():
            return {}
        try:
            payload = json.loads(jobs_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            return {}

        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        jobs: dict[str, dict[str, Any]] = {}
        changed = False
        for raw_job in payload["jobs"]:
            if not isinstance(raw_job, dict) or not raw_job.get("job_id"):
                continue
            job = self._persistable_refresh_job(raw_job)
            if str(job.get("state")) in {"queued", "running"}:
                job["state"] = "interrupted"
                job["finished_at"] = now_iso
                job["updated_at"] = now_iso
                job["error"] = "O app foi encerrado antes do refresh terminar."
                log_lines = list(job.get("log_lines") or [])
                log_lines.append(str(job["error"]))
                job["log_lines"] = log_lines[-200:]
            if job != raw_job:
                changed = True
            jobs[str(job["job_id"])] = job

        if changed:
            try:
                jobs_path.write_text(
                    json.dumps(
                        {
                            "jobs": sorted(
                                jobs.values(),
                                key=lambda row: str(row.get("created_at") or ""),
                                reverse=True,
                            )
                        },
                        ensure_ascii=True,
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
        return jobs

    @staticmethod
    def _db_worker_refresh_rows(
        *,
        job_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from src.platform.settings import get_settings  # noqa: PLC0415

        db_path = get_settings().paths.db_path
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
                        """
                        SELECT *
                        FROM refresh_jobs
                        WHERE id = ?
                        """,
                        (str(job_id),),
                    ).fetchone()
                    return [dict(row)] if row is not None else []
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
                return [dict(row) for row in (*active_rows, *terminal_rows)]
        except Exception:
            return []

    def _get_refresh_status_light(self, params: dict[str, Any]) -> dict[str, Any]:
        job_id = params.get("job_id")
        include_result = str(params.get("include_result") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        jobs = self._load_refresh_jobs_light()
        if job_id:
            job = jobs.get(str(job_id))
            if job is not None:
                return self._public_refresh_job(job, include_result=True)
            db_rows = self._db_worker_refresh_rows(job_id=str(job_id))
            if db_rows:
                return self._db_worker_refresh_job_to_public(db_rows[0])
            return {
                "state": "not_found",
                "job_id": str(job_id),
                "processed": 0,
                "failures": 0,
                "current_cvm": None,
                "log_lines": [],
            }

        items = [
            self._public_refresh_job(job, include_result=include_result)
            for job in jobs.values()
        ]
        items.extend(
            self._db_worker_refresh_job_to_public(row)
            for row in self._db_worker_refresh_rows(limit=10)
        )
        items.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return {"items": items}

    def get_refresh_status(self, params=None) -> dict:
        try:
            p = params or {}
            if self._refresh_manager is None and p.get("cd_cvm") in (None, ""):
                return self._sanitize_for_json(self._get_refresh_status_light(p))
            return self._sanitize_for_json(self._refresh().get_refresh_status(p))
        except Exception as exc:
            return self._sanitize_for_json({
                "state": "error",
                "processed": 0,
                "failures": 1,
                "current_cvm": None,
                "log_lines": [str(exc)],
                "error": str(exc),
            })

    def request_refresh(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("request_refresh"))
        p = params or {}
        if p.get("ui_route") or p.get("ui_route_cd_cvm") or p.get("ui_action"):
            self._append_runtime_log(
                "request_refresh "
                f"cd_cvm={p.get('cd_cvm')} "
                f"ui_route_cd_cvm={p.get('ui_route_cd_cvm')} "
                f"ui_action={p.get('ui_action')} "
                f"ui_route={p.get('ui_route')}"
            )
        # Single-company refresh (from no-data company page) routes through the
        # same code path as the HTTP API (`service.request_company_refresh`),
        # which does a full incremental backfill (2010..current). The batch
        # manager defaults to mode="missing" with fast_lane=True, which would
        # only fetch the last 2 years.
        batch_signals = (
            "company_ids",
            "sector_slug",
            "gics_sub_industry",
            "cvm_range",
            "mode",
        )
        is_single_company = (
            p.get("cd_cvm") is not None
            and not any(p.get(key) for key in batch_signals)
        )
        if is_single_company:
            try:
                import dataclasses  # noqa: PLC0415
                cd_cvm = int(p.get("cd_cvm"))
                start_year_raw = p.get("start_year")
                end_year_raw = p.get("end_year")
                start_year = int(start_year_raw) if start_year_raw is not None else None
                end_year = int(end_year_raw) if end_year_raw is not None else None
                result = self._svc().request_company_refresh(
                    cd_cvm,
                    start_year=start_year,
                    end_year=end_year,
                )
                self._svc().invalidate_read_caches()
                self._clear_data_coverage_cache()
                return self._sanitize_for_json(dataclasses.asdict(result))
            except Exception as exc:
                return self._sanitize_for_json({
                    "status": "error",
                    "job_id": None,
                    "message": str(exc),
                    "status_reason_code": "desktop_refresh_error",
                    "status_reason_message": str(exc),
                    "is_retry_allowed": True,
                })

        try:
            result = self._refresh().request_refresh(p)
            self._svc().invalidate_read_caches()
            self._clear_data_coverage_cache()
            return self._sanitize_for_json(result)
        except Exception as exc:
            return self._sanitize_for_json({
                "status": "error",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "desktop_refresh_error",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
            })

    def cancel_refresh(self, params=None) -> dict:
        try:
            return self._sanitize_for_json(self._refresh().cancel_job(params or {}))
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "message": str(exc)})

    def get_onboarding_state(self, params=None) -> dict:
        try:
            state = self._onboarding().get_onboarding_state()
            job_id = state.get("refresh_job_id")
            if job_id:
                state["refresh_job"] = self._refresh().get_refresh_status({"job_id": job_id})
            return self._sanitize_for_json(state)
        except Exception as exc:
            return self._sanitize_for_json({
                "first_run_completed": False,
                "should_show": True,
                "setup_status": "error",
                "error": str(exc),
            })

    def start_onboarding_setup(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("start_onboarding_setup"))
        p = params or {}
        preset = str(p.get("preset") or "").strip().lower()
        try:
            selection = self._onboarding().get_company_universe_by_preset(preset, refresh_catalog=True)
        except Exception as exc:
            return self._sanitize_for_json({
                "status": "error",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "company_universe_unavailable",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
            })

        refresh_params: dict[str, Any] = {
            "mode": "missing",
            "company_ids": list(selection.company_ids),
        }
        for key in ("start_year", "end_year"):
            if p.get(key) not in (None, ""):
                refresh_params[key] = p.get(key)

        try:
            dispatch = self._refresh().request_refresh(refresh_params)
        except Exception as exc:
            return self._sanitize_for_json({
                "status": "error",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "desktop_refresh_error",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
                "selection": selection.to_dict(),
            })

        if str(dispatch.get("status") or "").lower() in {"error", "already_running"}:
            dispatch["selection"] = selection.to_dict()
            return self._sanitize_for_json(dispatch)

        job_id = dispatch.get("job_id")
        self._onboarding().mark_setup_started(
            selection,
            refresh_job_id=str(job_id) if job_id else None,
        )
        if not job_id:
            self._onboarding().mark_setup_completed(status=str(dispatch.get("status") or "success"))
        self._svc().invalidate_read_caches()
        self._clear_data_coverage_cache()
        return self._sanitize_for_json({
            **dispatch,
            "selection": selection.to_dict(),
        })

    def complete_onboarding_setup(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("complete_onboarding_setup"))
        try:
            status = str((params or {}).get("status") or "success")
            return self._sanitize_for_json(self._onboarding().mark_setup_completed(status=status))
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def skip_onboarding_setup(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("skip_onboarding_setup"))
        try:
            return self._sanitize_for_json(self._onboarding().skip_setup())
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def get_market_cap_list(self, params=None) -> dict:
        try:
            from src.companies.market_cap import MarketCapService  # noqa: PLC0415
            svc = self._svc()
            market_cap_service = MarketCapService(settings=svc.settings, read_service=svc)
            entries = market_cap_service.read_snapshot()
            return self._sanitize_for_json({
                "ok": True,
                "items": [e.to_dict() for e in entries]
            })
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc), "items": []})

    def import_market_cap_snapshot(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("import_market_cap_snapshot"))
        p = params or {}
        csv_content = p.get("csv_content")
        file_path = p.get("file_path")
        try:
            from src.companies.market_cap import MarketCapService  # noqa: PLC0415
            svc = self._svc()
            market_cap_service = MarketCapService(settings=svc.settings, read_service=svc)
            if csv_content:
                import io  # noqa: PLC0415
                res = market_cap_service.import_snapshot(io.StringIO(str(csv_content)))
            elif file_path:
                res = market_cap_service.import_snapshot(Path(str(file_path)))
            else:
                return self._sanitize_for_json({
                    "ok": False,
                    "error": "Either csv_content or file_path must be provided."
                })
            self._svc().invalidate_read_caches()
            return self._sanitize_for_json({"ok": True, "status": res})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def get_market_cap_status(self, params=None) -> dict:
        try:
            from src.companies.market_cap import MarketCapService  # noqa: PLC0415
            svc = self._svc()
            market_cap_service = MarketCapService(settings=svc.settings, read_service=svc)
            status = market_cap_service.get_status()
            return self._sanitize_for_json(status)
        except Exception as exc:
            return self._sanitize_for_json({
                "available": False,
                "row_count": 0,
                "error": str(exc)
            })

    def get_data_update_settings(self, params=None) -> dict:
        try:
            return self._sanitize_for_json(self._resolve_data_update_settings())
        except Exception as exc:
            return self._sanitize_for_json({
                **self._default_data_update_settings(),
                "error": str(exc),
            })

    def save_data_update_settings(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("save_data_update_settings"))
        p = params or {}
        try:
            settings = self._normalize_data_update_settings(p)
            self._write_app_settings(settings)
            return self._sanitize_for_json(settings)
        except Exception as exc:
            return self._sanitize_for_json({
                **self._default_data_update_settings(),
                "error": str(exc),
            })

    def get_company_universe_selection(self, params=None) -> dict:
        p = params or {}
        try:
            settings = self._resolve_data_update_settings()
            preset = str(p.get("preset") or settings["universe_preset"]).strip().lower()
            if preset not in self.DATA_UPDATE_PRESETS:
                raise ValueError(f"Universo de empresas invalido: {preset}")
            selection = self._onboarding().get_company_universe_by_preset(preset)
            return self._sanitize_for_json(selection.to_dict())
        except Exception as exc:
            return self._sanitize_for_json({
                "preset": str((params or {}).get("preset") or ""),
                "selected_count": 0,
                "company_ids": [],
                "source": None,
                "source_date": None,
                "warning": None,
                "companies": [],
                "error": str(exc),
            })

    def start_data_update(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("start_data_update"))
        from src.companies.universe import CompanyUniverseUnavailableError  # noqa: PLC0415

        p = params or {}
        try:
            current_settings = self._resolve_data_update_settings()
            settings = self._normalize_data_update_settings({
                **current_settings,
                **p,
            })
            mode = str(p.get("mode") or "missing").strip().lower()
            if mode not in {"missing", "full", "outdated", "failed"}:
                raise ValueError(f"Invalid update mode: {mode}")

            selection = self._onboarding().get_company_universe_by_preset(
                str(settings["universe_preset"]), refresh_catalog=True
            )
            refresh_params: dict[str, Any] = {
                "mode": mode,
                "company_ids": list(selection.company_ids),
                # The current backend processes one queue per request. This is
                # the safe per-run cap exposed as "empresas por lote" in the UI.
                "limit": int(settings["batch_size"]),
                "start_year": int(settings["start_year"]),
                "end_year": int(settings["end_year"]),
            }

            dispatch = self._refresh().request_refresh(refresh_params)
            if str(dispatch.get("status") or "").lower() not in {
                "error",
                "already_running",
            }:
                self._write_app_settings(settings)
            self._svc().invalidate_read_caches()
            self._clear_data_coverage_cache()
            return self._sanitize_for_json({
                **dispatch,
                "selection": selection.to_dict(),
                "settings": settings,
            })
        except CompanyUniverseUnavailableError as exc:
            logger.warning("start_data_update blocked: company universe unavailable: %s", exc)
            self._append_runtime_log(
                f"start_data_update blocked: company_universe_unavailable: {exc}"
            )
            return self._sanitize_for_json({
                "status": "blocked",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "company_universe_unavailable",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
            })
        except Exception as exc:
            logger.exception("start_data_update failed")
            self._append_runtime_log(f"start_data_update failed: {exc}")
            return self._sanitize_for_json({
                "status": "error",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "data_update_error",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
            })

    def reset_local_database(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("reset_local_database"))
        p = params or {}
        action = str(p.get("action") or "").strip().lower()
        expected = "RESET" if action == "restart_current" else "REBUILD"
        if action not in {"restart_current", "recreate_local"}:
            return self._sanitize_for_json({
                "ok": False,
                "action": action,
                "error": "Invalid reset action.",
            })
        if str(p.get("confirm") or "") != expected:
            return self._sanitize_for_json({
                "ok": False,
                "action": action,
                "error": f"Type {expected} to confirm.",
            })

        try:
            active_job = self._active_refresh_job()
            if active_job is not None:
                return self._sanitize_for_json({
                    "ok": False,
                    "action": action,
                    "error": "An update is in progress. Cancel or wait for it to finish before resetting the database.",
                    "active_job_id": active_job.get("job_id"),
                })

            if action == "restart_current":
                result = self._restart_current_database_state()
            else:
                result = self._recreate_local_database()
            self._reset_bridge_runtime()
            return self._sanitize_for_json({
                "ok": True,
                "action": action,
                **result,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "ok": False,
                "action": action,
                "error": str(exc),
            })

    def _default_data_update_settings(self) -> dict[str, Any]:
        preset = "top_200"
        try:
            state = self._onboarding().get_onboarding_state()
            selected = str(state.get("selected_company_universe") or "").strip().lower()
            if selected in self.DATA_UPDATE_PRESETS:
                preset = selected
        except Exception:
            pass
        current_year = datetime.now(timezone.utc).year
        return {
            "universe_preset": preset,
            "batch_size": 100,
            "retry_failed": True,
            "recompute_coverage": True,
            "start_year": current_year - 4,
            "end_year": current_year,
        }

    def _resolve_data_update_settings(self) -> dict[str, Any]:
        defaults = self._default_data_update_settings()
        stored = self._read_app_settings(self.DATA_UPDATE_SETTING_KEYS)
        raw = {
            "universe_preset": stored.get("data_update_universe_preset", defaults["universe_preset"]),
            "batch_size": stored.get("data_update_batch_size", defaults["batch_size"]),
            "retry_failed": stored.get("data_update_retry_failed", defaults["retry_failed"]),
            "recompute_coverage": stored.get("data_update_recompute_coverage", defaults["recompute_coverage"]),
            "start_year": stored.get("data_update_start_year", defaults["start_year"]),
            "end_year": stored.get("data_update_end_year", defaults["end_year"]),
        }
        return self._normalize_data_update_settings(raw)

    def _normalize_data_update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        preset = str(
            payload.get("universe_preset")
            or payload.get("preset")
            or payload.get("selected_company_universe")
            or "top_200"
        ).strip().lower()
        if preset not in self.DATA_UPDATE_PRESETS:
            raise ValueError(f"Universo de empresas invalido: {preset}")

        try:
            batch_size = int(payload.get("batch_size") or 100)
        except (TypeError, ValueError) as exc:
            raise ValueError("Empresas por lote deve ser 50, 100, 200 ou 500.") from exc
        if batch_size not in self.DATA_UPDATE_BATCH_SIZES:
            raise ValueError("Empresas por lote deve ser 50, 100, 200 ou 500.")

        current_year = datetime.now(timezone.utc).year
        default_start = current_year - 4
        default_end = current_year
        try:
            start_year = int(payload.get("start_year") or default_start)
        except (TypeError, ValueError) as exc:
            raise ValueError("Ano inicial deve ser um numero inteiro.") from exc
        try:
            end_year = int(payload.get("end_year") or default_end)
        except (TypeError, ValueError) as exc:
            raise ValueError("Ano final deve ser um numero inteiro.") from exc
        if start_year < self.CVM_MIN_YEAR:
            raise ValueError(f"Ano inicial minimo permitido: {self.CVM_MIN_YEAR}.")
        if end_year > current_year:
            raise ValueError(f"Ano final maximo permitido: {current_year}.")
        if start_year > end_year:
            raise ValueError(f"Ano inicial ({start_year}) nao pode ser maior que o ano final ({end_year}).")

        return {
            "universe_preset": preset,
            "batch_size": batch_size,
            "retry_failed": self._coerce_bool(payload.get("retry_failed"), default=True),
            "recompute_coverage": self._coerce_bool(
                payload.get("recompute_coverage"),
                default=True,
            ),
            "start_year": start_year,
            "end_year": end_year,
        }

    @staticmethod
    def _coerce_bool(value: Any, *, default: bool) -> bool:
        if value is None:
            return bool(default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "sim", "on"}
        return bool(value)

    def _read_app_settings(self, keys: set[str]) -> dict[str, Any]:
        from sqlalchemy import bindparam, text  # noqa: PLC0415
        from src.companies.universe import ensure_company_universe_tables_for_connection  # noqa: PLC0415

        with self._svc().engine.begin() as conn:
            ensure_company_universe_tables_for_connection(conn)
            rows = conn.execute(
                text("SELECT key, value FROM app_settings WHERE key IN :keys")
                .bindparams(bindparam("keys", expanding=True)),
                {"keys": sorted(keys)},
            ).mappings().all()

        parsed: dict[str, Any] = {}
        for row in rows:
            key = str(row["key"])
            raw = row.get("value")
            try:
                parsed[key] = json.loads(raw) if raw is not None else None
            except Exception:
                parsed[key] = raw
        return parsed

    def _write_app_settings(self, settings: dict[str, Any]) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        from src.companies.universe import ensure_company_universe_tables_for_connection  # noqa: PLC0415

        values = {
            "data_update_universe_preset": settings["universe_preset"],
            "data_update_batch_size": int(settings["batch_size"]),
            "data_update_retry_failed": bool(settings["retry_failed"]),
            "data_update_recompute_coverage": bool(settings["recompute_coverage"]),
            "data_update_start_year": int(settings["start_year"]),
            "data_update_end_year": int(settings["end_year"]),
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._svc().engine.begin() as conn:
            ensure_company_universe_tables_for_connection(conn)
            for key, value in values.items():
                conn.execute(text("DELETE FROM app_settings WHERE key = :key"), {"key": key})
                conn.execute(
                    text(
                        """
                        INSERT INTO app_settings (key, value, updated_at)
                        VALUES (:key, :value, :updated_at)
                        """
                    ),
                    {
                        "key": key,
                        "value": json.dumps(value, ensure_ascii=True),
                        "updated_at": now,
                    },
                )

    def _record_refresh_worker_diagnostic(
        self,
        *,
        status: str,
        worker_id: str | None = None,
        error: str | None = None,
    ) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        from src.companies.universe import ensure_company_universe_tables_for_connection  # noqa: PLC0415

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        values: dict[str, Any] = {
            "refresh_worker_status": str(status),
            "refresh_worker_last_heartbeat_at": now,
        }
        if worker_id:
            values["refresh_worker_id"] = str(worker_id)
        if error is not None:
            values["refresh_worker_last_error"] = str(error)
        elif status in {"starting", "running", "idle"}:
            values["refresh_worker_last_error"] = ""
        if status == "starting":
            values["refresh_worker_started_at"] = now

        with self._svc().engine.begin() as conn:
            ensure_company_universe_tables_for_connection(conn)
            for key, value in values.items():
                conn.execute(text("DELETE FROM app_settings WHERE key = :key"), {"key": key})
                conn.execute(
                    text(
                        """
                        INSERT INTO app_settings (key, value, updated_at)
                        VALUES (:key, :value, :updated_at)
                        """
                    ),
                    {
                        "key": key,
                        "value": json.dumps(value, ensure_ascii=True),
                        "updated_at": now,
                    },
                )

    def _active_refresh_job(self) -> dict[str, Any] | None:
        try:
            response = self._refresh().get_refresh_status({})
            for item in response.get("items", []):
                if str(item.get("state") or "").lower() in {"queued", "running"}:
                    return dict(item)
        except Exception:
            return None
        return None

    def _restart_current_database_state(self) -> dict[str, Any]:
        from sqlalchemy import text  # noqa: PLC0415
        from src.companies.universe import ensure_company_universe_tables_for_connection  # noqa: PLC0415
        from src.refresh.jobs import ensure_refresh_runtime_tables_for_connection  # noqa: PLC0415

        svc = self._svc()
        removed: list[str] = []
        settings_snapshot = self._resolve_data_update_settings()

        blank: dict[str, Any] = {
            "first_run_completed": False,
            "should_show": True,
            "selected_company_universe": None,
            "company_universe_source": None,
            "company_universe_source_date": None,
            "setup_status": None,
            "selected_company_count": 0,
            "refresh_job_id": None,
            "warning": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        onboarding = self._onboarding()
        onboarding._write_state(blank)  # type: ignore[attr-defined]

        with svc.engine.begin() as conn:
            ensure_company_universe_tables_for_connection(conn)
            ensure_refresh_runtime_tables_for_connection(conn)
            conn.execute(text("DELETE FROM company_universe"))
            conn.execute(text("DELETE FROM refresh_jobs"))
            conn.execute(text("DELETE FROM company_refresh_status"))
            conn.execute(
                text(
                    """
                    DELETE FROM app_settings
                    WHERE key IN (
                        'first_run_completed',
                        'selected_company_universe',
                        'company_universe_source',
                        'company_universe_source_date',
                        'download_status',
                        'refresh_job_id'
                    )
                    """
                )
            )
        removed.extend(["company_universe", "refresh_jobs", "company_refresh_status", "onboarding_state"])
        self._remove_runtime_state_files(removed)
        self._write_app_settings(settings_snapshot)
        svc.invalidate_read_caches()
        self._clear_data_coverage_cache()
        return {
            "backup_path": None,
            "removed": removed,
            "message": "Setup state and update history cleared. Local financial data was preserved.",
        }

    def _recreate_local_database(self) -> dict[str, Any]:
        from src.financials.database import init_db_tables  # noqa: PLC0415
        from src.platform.db import build_engine  # noqa: PLC0415

        svc = self._svc()
        if svc.settings.database_url:
            raise RuntimeError("Automatic rebuild is only supported for local SQLite databases.")

        settings_snapshot = self._resolve_data_update_settings()
        db_path = Path(svc.settings.paths.db_path)
        data_dir = Path(svc.settings.paths.data_dir)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = data_dir / "backup" / f"db-reset-{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_items = self._backup_database_artifacts(db_path, backup_dir)

        try:
            svc.engine.dispose()
        except Exception:
            pass

        removed: list[str] = []
        for candidate in (db_path, db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")):
            if candidate.exists():
                candidate.unlink()
                removed.append(str(candidate))
        self._remove_runtime_state_files(removed)

        db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = build_engine(svc.settings)
        try:
            init_db_tables(engine)
        finally:
            engine.dispose()

        self._reset_bridge_runtime()
        self._write_app_settings(settings_snapshot)
        return {
            "backup_path": str(backup_dir),
            "backup_items": backup_items,
            "removed": removed,
            "message": "Local SQLite database rebuilt. Start an update to populate the database.",
        }

    def _backup_database_artifacts(self, db_path: Path, backup_dir: Path) -> list[str]:
        copied: list[str] = []
        if db_path.exists():
            target = backup_dir / db_path.name
            src_uri = f"file:{db_path.as_posix()}?mode=ro"
            src = sqlite3.connect(src_uri, uri=True)
            try:
                dst = sqlite3.connect(str(target))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            copied.append(str(target))

        for source in (
            db_path.with_name(db_path.name + "-wal"),
            db_path.with_name(db_path.name + "-shm"),
            Path(self._svc().settings.paths.data_dir) / "refresh_jobs.json",
            Path(self._svc().settings.paths.onboarding_state_path),
            Path(self._svc().settings.paths.base_health_snapshot_path),
        ):
            if source.exists():
                target = backup_dir / source.name
                shutil.copy2(source, target)
                copied.append(str(target))
        return copied

    def _remove_runtime_state_files(self, removed: list[str]) -> None:
        svc = self._svc()
        for path in (
            Path(svc.settings.paths.data_dir) / "refresh_jobs.json",
            Path(svc.settings.paths.onboarding_state_path),
            Path(svc.settings.paths.base_health_snapshot_path),
        ):
            if path.exists():
                path.unlink()
                removed.append(str(path))

    def _reset_bridge_runtime(self) -> None:
        for service in (self._service,):
            try:
                if service is not None:
                    service.engine.dispose()
            except Exception:
                pass
        self._service = None
        self._refresh_manager = None
        self._onboarding_service = None
        self._company_info_cache.clear()
        self._company_info_pending.clear()

    def dev_reset_onboarding(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_reset_onboarding"))
        try:
            svc = self._onboarding()
            blank: dict = {
                "first_run_completed": False,
                "should_show": True,
                "selected_company_universe": None,
                "company_universe_source": None,
                "company_universe_source_date": None,
                "setup_status": None,
                "selected_company_count": 0,
                "refresh_job_id": None,
                "warning": None,
            }
            svc._write_state(blank)  # type: ignore[attr-defined]
            svc._write_app_settings(blank)  # type: ignore[attr-defined]
            return self._sanitize_for_json({"ok": True})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def dev_reset_universe(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_reset_universe"))
        try:
            from sqlalchemy import text  # noqa: PLC0415
            with self._svc().engine.begin() as conn:
                conn.execute(text("DELETE FROM company_universe"))
            return self._sanitize_for_json({"ok": True})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def dev_reset_jobs(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_reset_jobs"))
        try:
            from sqlalchemy import text  # noqa: PLC0415
            with self._svc().engine.begin() as conn:
                conn.execute(text("DELETE FROM refresh_jobs"))
                conn.execute(text("DELETE FROM company_refresh_status"))
            return self._sanitize_for_json({"ok": True})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def dev_simulate_refresh(self, params=None) -> dict:  # noqa: C901
        """Insert synthetic job rows so UI can exercise all terminal states."""
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_simulate_refresh"))
        import threading  # noqa: PLC0415
        import uuid  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415
        from src.refresh.jobs import ensure_refresh_runtime_tables  # noqa: PLC0415

        mode = str((params or {}).get("mode") or "success").lower()
        engine = self._svc().engine
        ensure_refresh_runtime_tables(engine)

        _MOCK_CVM = 99999999
        _MOCK_NAME = "DEV_MOCK_COMPANY"
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        def _upsert(job_id: str, state: str, stage: str | None = None,
                    cur: int = 0, tot: int = 10, err: str | None = None,
                    finished: bool = False) -> None:
            fin = now if finished else None
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM refresh_jobs WHERE id = :id"), {"id": job_id})
                conn.execute(
                    text(
                        "INSERT INTO refresh_jobs "
                        "(id, cd_cvm, company_name, source_scope, start_year, end_year, "
                        " state, stage, requested_at, started_at, finished_at, "
                        " progress_current, progress_total, error_message) "
                        "VALUES (:id, :cvm, :name, 'dev_mock', 2024, 2024, "
                        ":state, :stage, :now, :now, :fin, :cur, :tot, :err)"
                    ),
                    {
                        "id": job_id, "cvm": _MOCK_CVM, "name": _MOCK_NAME,
                        "state": state, "stage": stage, "now": now, "fin": fin,
                        "cur": cur, "tot": tot, "err": err,
                    },
                )

        if mode in ("success", "partial", "fail"):
            jid = str(uuid.uuid4())
            if mode == "success":
                _upsert(jid, "success", "finalizing", 10, 10, finished=True)
            elif mode == "fail":
                _upsert(jid, "error", None, 0, 10,
                        err="[dev_simulate] Simulated failure", finished=True)
            else:  # partial
                _upsert(str(uuid.uuid4()), "success", "finalizing", 10, 10, finished=True)
                _upsert(str(uuid.uuid4()), "error", None, 3, 10,
                        err="[dev_simulate] Simulated partial failure", finished=True)
            return self._sanitize_for_json({"ok": True, "mode": mode, "job_id": jid})

        # slow — advance through stages in background; worker ignores RUNNING rows
        jid = str(uuid.uuid4())
        _upsert(jid, "running", "planning", 0, 10)

        def _advance() -> None:
            import time as _t  # noqa: PLC0415
            stages = [
                ("download_extract", 2, 10),
                ("process_data", 5, 10),
                ("persist_reports", 8, 10),
                ("finalizing", 9, 10),
            ]
            for stage, cur, tot in stages:
                _t.sleep(3)
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE refresh_jobs SET stage=:stage, progress_current=:cur, "
                            "progress_total=:tot WHERE id=:id"
                        ),
                        {"stage": stage, "cur": cur, "tot": tot, "id": jid},
                    )
            _t.sleep(2)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE refresh_jobs SET state='success', stage='finalizing', "
                        "progress_current=10, progress_total=10, "
                        "finished_at=:now WHERE id=:id"
                    ),
                    {"now": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"), "id": jid},
                )

        threading.Thread(target=_advance, daemon=True).start()
        return self._sanitize_for_json({"ok": True, "mode": "slow", "job_id": jid})

    def dev_start_small_setup(self, params=None) -> dict:
        """Run request_refresh against the first N companies already in the local DB."""
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_start_small_setup"))
        count = min(int((params or {}).get("count") or 5), 10)
        try:
            page = self._svc().list_companies(page=1, page_size=count, search="")
            cd_cvms = [int(c["cd_cvm"]) for c in page.get("items", [])]
            if not cd_cvms:
                return self._sanitize_for_json({
                    "status": "error",
                    "message": "No companies in local DB yet. Run a preset first.",
                })
            return self._sanitize_for_json(
                self._refresh().request_refresh({
                    "mode": "missing",
                    "company_ids": cd_cvms,
                })
            )
        except Exception as exc:
            return self._sanitize_for_json({"status": "error", "message": str(exc)})

    def dev_get_raw_state(self, params=None) -> dict:
        """Return raw app_settings and recent refresh_jobs for the dev inspector."""
        try:
            from sqlalchemy import text  # noqa: PLC0415
            engine = self._svc().engine
            with engine.connect() as conn:
                settings_rows = [
                    {"key": str(r[0]), "value": str(r[1]) if r[1] is not None else None,
                     "updated_at": str(r[2]) if r[2] is not None else None}
                    for r in conn.execute(
                        text("SELECT key, value, updated_at FROM app_settings ORDER BY key")
                    )
                ]
                jobs_rows = [
                    {
                        "id": str(r[0]), "cd_cvm": int(r[1]),
                        "company_name": r[2],
                        "state": str(r[3]), "stage": r[4],
                        "progress_current": r[5], "progress_total": r[6],
                        "error_message": r[7],
                        "requested_at": r[8], "started_at": r[9], "finished_at": r[10],
                    }
                    for r in conn.execute(
                        text(
                            "SELECT id, cd_cvm, company_name, state, stage, "
                            "progress_current, progress_total, error_message, "
                            "requested_at, started_at, finished_at "
                            "FROM refresh_jobs ORDER BY requested_at DESC LIMIT 30"
                        )
                    )
                ]
            return self._sanitize_for_json({
                "app_settings": settings_rows,
                "refresh_jobs": jobs_rows,
            })
        except Exception as exc:
            return self._sanitize_for_json({"error": str(exc)})

    def _start_refresh_worker(self) -> None:
        """Called from a daemon thread in app.py after window creation.

        Jobs enfileirados via ``CVMReadService.request_company_refresh``
        (caminho single-company com período) ficam pendentes na tabela
        ``refresh_jobs``. Sem este worker, eles nunca rodam no .exe.
        """
        try:
            from src.refresh.job_worker import (  # noqa: PLC0415
                RefreshJobWorker,
                RefreshWorkerConfig,
            )
            from src.refresh.service import HeadlessRefreshService  # noqa: PLC0415

            svc = self._svc()
            # Reusa o repository já inicializado pelo CVMReadService
            # (mesmo engine sqlite local, esquema já garantido).
            repository = svc.refresh_job_repository
            try:
                repository.ensure_schema()
            except Exception:
                pass

            config = RefreshWorkerConfig()
            self._record_refresh_worker_diagnostic(
                status="starting",
                worker_id=config.worker_id,
            )

            last_worker_diagnostic = {"status": "starting", "written_at": 0.0}

            def _heartbeat(state: str) -> None:
                mapped_status = "running" if state in {"running", "idle"} else state
                now_monotonic = time.monotonic()
                if (
                    mapped_status == last_worker_diagnostic["status"]
                    and now_monotonic - float(last_worker_diagnostic["written_at"]) < 15.0
                ):
                    return
                self._record_refresh_worker_diagnostic(
                    status=mapped_status,
                    worker_id=config.worker_id,
                )
                last_worker_diagnostic["status"] = mapped_status
                last_worker_diagnostic["written_at"] = now_monotonic

            refresh_service = HeadlessRefreshService(settings=svc.settings)
            worker = RefreshJobWorker(
                settings=svc.settings,
                repository=repository,
                refresh_service=refresh_service,
                config=config,
                worker_heartbeat_callback=_heartbeat,
            )
            worker.run_forever()
        except Exception as exc:
            logger.exception("desktop-refresh-worker failed")
            try:
                self._record_refresh_worker_diagnostic(
                    status="error",
                    error=f"{exc.__class__.__name__}: {exc}",
                )
            except Exception:
                logger.exception("failed to persist refresh worker diagnostic")
