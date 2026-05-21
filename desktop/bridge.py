"""
CVMBridge — funções Python expostas ao JS via window.pywebview.api.*

Convenção pywebview: objetos JS chegam como dict posicional (params=None),
não como kwargs. Use sempre `def method(self, params=None)` + `params.get(...)`.
"""

from __future__ import annotations

import dataclasses
import base64
import math
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


class CVMBridge:
    def __init__(self) -> None:
        self._service = None
        self._refresh_manager = None
        self._company_info_cache: dict[int, dict[str, Any]] = {}
        self._company_info_pending: set[int] = set()
        self._company_info_lock = threading.RLock()
        # auto-updater state
        self._update_info: dict | None = None
        self._update_progress: dict = {"status": "idle", "percent": 0, "error": None}
        self._update_lock = threading.Lock()

    def _svc(self):
        if self._service is None:
            from src.read_service import CVMReadService  # noqa: PLC0415
            self._service = CVMReadService()
        return self._service

    def _refresh(self):
        if self._refresh_manager is None:
            from desktop.services import DesktopRefreshJobManager  # noqa: PLC0415

            self._refresh_manager = DesktopRefreshJobManager(read_service=self._svc())
        return self._refresh_manager

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    @staticmethod
    def _bounded_int(
        value: Any,
        *,
        default: int,
        minimum: int = 1,
        maximum: int = 100,
    ) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(default)
        return max(int(minimum), min(int(maximum), parsed))

    @staticmethod
    def _sanitize_for_json(value: Any) -> Any:
        """Recursively replace non-finite floats with None for strict JSON."""
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {key: CVMBridge._sanitize_for_json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [CVMBridge._sanitize_for_json(item) for item in value]
        if isinstance(value, tuple):
            return [CVMBridge._sanitize_for_json(item) for item in value]
        return value

    def ping(self, params=None) -> dict:
        return self._sanitize_for_json({"pong": True, "ts": time.time()})

    # ------------------------------------------------------------------
    # Diretório de empresas
    # ------------------------------------------------------------------

    def get_companies(self, params=None) -> dict:
        p = params or {}
        t0 = time.perf_counter()
        try:
            result = self._svc().list_companies(
                search=str(p.get("search", "")),
                sector_slug=p.get("sector_slug") or p.get("sector") or None,
                page=self._bounded_int(p.get("page", 1), default=1, maximum=10_000),
                page_size=self._bounded_int(
                    p.get("page_size", p.get("pageSize", 20)),
                    default=20,
                    maximum=100,
                ),
            )
            payload = dataclasses.asdict(result)
            payload["_bridge_ms"] = round((time.perf_counter() - t0) * 1000, 3)
            return self._sanitize_for_json(payload)
        except Exception as exc:
            return {"error": str(exc), "items": [], "pagination": {}}

    def get_company_filters(self, params=None) -> dict:
        try:
            result = self._svc().get_company_filters()
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc), "sectors": []}

    def get_company_suggestions(self, params=None) -> dict:
        p = params or {}
        try:
            items = self._svc().suggest_companies(
                q=str(p.get("q", "")),
                limit=self._bounded_int(p.get("limit", 6), default=6, maximum=100),
                ready_only=bool(p.get("ready_only", False)),
            )
            return self._sanitize_for_json({"items": [dataclasses.asdict(i) for i in items]})
        except Exception as exc:
            return {"error": str(exc), "items": []}

    def get_populares(self, params=None) -> dict:
        try:
            result = self._svc().get_populares_companies()
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc), "items": [], "pagination": {}}

    def get_em_destaque(self, params=None) -> dict:
        p = params or {}
        try:
            result = self._svc().get_em_destaque_companies(
                limit=int(p.get("limit", 10))
            )
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc), "items": [], "pagination": {}}

    def track_company_view(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            if cd_cvm:
                self._svc().record_company_view(cd_cvm)
            return {"ok": True}
        except Exception:
            return {"ok": False}

    # ------------------------------------------------------------------
    # Detalhe de empresa
    # ------------------------------------------------------------------

    def get_company_info(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            result = self._svc().get_company_info(
                cd_cvm,
                allow_catalog_lookup=True,
            )
            if result is None:
                cached = self._get_cached_company_info(cd_cvm)
                if cached is not None:
                    return self._sanitize_for_json(cached)
                self._queue_company_info_lookup(cd_cvm)
                return {"not_found": True, "catalog_lookup_pending": True}
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def _get_cached_company_info(self, cd_cvm: int) -> dict[str, Any] | None:
        with self._company_info_lock:
            cached = self._company_info_cache.get(int(cd_cvm))
            return dict(cached) if cached is not None else None

    def _queue_company_info_lookup(self, cd_cvm: int) -> None:
        code = int(cd_cvm)
        with self._company_info_lock:
            if code in self._company_info_pending:
                return
            self._company_info_pending.add(code)

        def worker() -> None:
            try:
                result = self._svc().get_company_info(code)
                payload = dataclasses.asdict(result) if result is not None else None
                with self._company_info_lock:
                    if payload is not None:
                        self._company_info_cache[code] = payload
            finally:
                with self._company_info_lock:
                    self._company_info_pending.discard(code)

        threading.Thread(
            target=worker,
            name=f"desktop-company-catalog-{code}",
            daemon=True,
        ).start()

    def get_company_years(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            years = self._svc().get_available_years(cd_cvm)
            return self._sanitize_for_json({"years": years})
        except Exception as exc:
            return {"error": str(exc), "years": []}

    def get_company_kpis(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            years_raw = p.get("years", [])
            if isinstance(years_raw, str):
                years = [int(y) for y in years_raw.split(",") if y.strip()]
            else:
                years = [int(y) for y in years_raw]
            result = self._svc().get_kpi_bundle(cd_cvm, years)
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def get_company_statement(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            years_raw = p.get("years", [])
            if isinstance(years_raw, str):
                years = [int(y) for y in years_raw.split(",") if y.strip()]
            else:
                years = [int(y) for y in years_raw]
            stmt = str(p.get("stmt", "bpa"))
            result = self._svc().get_statement_matrix(cd_cvm, years, stmt)
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def download_company_excel(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            filename, payload = self._svc().build_company_excel_export(cd_cvm)
            return self._sanitize_for_json({
                "filename": filename,
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "content_base64": base64.b64encode(payload).decode("ascii"),
            })
        except Exception as exc:
            return {"error": str(exc)}

    def save_company_excel(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            filename, payload = self._svc().build_company_excel_export(cd_cvm)
            saved_path = self._save_bytes_to_downloads(filename, payload)
            reveal = bool(p.get("reveal", True))
            revealed = self._reveal_in_file_explorer(saved_path) if reveal else False
            return self._sanitize_for_json({
                "filename": filename,
                "saved_path": saved_path,
                "revealed": revealed,
            })
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def _save_bytes_to_downloads(filename: str, payload: bytes) -> str:
        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(str(filename or "download.bin")).name
        stem = Path(safe_name).stem or "download"
        suffix = Path(safe_name).suffix
        target = downloads_dir / safe_name
        counter = 1
        while target.exists():
            target = downloads_dir / f"{stem} ({counter}){suffix}"
            counter += 1
        target.write_bytes(payload)
        return str(target)

    @staticmethod
    def _reveal_in_file_explorer(saved_path: str) -> bool:
        path = Path(saved_path)
        try:
            if os.name == "nt":
                os.startfile(str(path.parent))  # type: ignore[attr-defined]
                return True
            subprocess.Popen(["xdg-open", str(path.parent)])
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Setores
    # ------------------------------------------------------------------

    def get_sectors(self, params=None) -> dict:
        try:
            p = params or {}
            result = self._svc().list_sectors(group_by=str(p.get("group_by") or "sector"))
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc), "items": []}

    def get_sector_detail(self, params=None) -> dict:
        p = params or {}
        try:
            slug = str(p.get("sector_slug", ""))
            year = p.get("year")
            year_int = int(year) if year is not None else None
            result = self._svc().get_sector_detail(slug, year_int)
            if result is None:
                return {"not_found": True}
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def get_sub_sector_detail(self, params=None) -> dict:
        p = params or {}
        try:
            sector_slug = str(p.get("sector_slug", ""))
            sub_industry_slug = str(p.get("sub_industry_slug", ""))
            year = p.get("year")
            year_int = int(year) if year is not None else None
            result = self._svc().get_sub_sector_detail(
                sector_slug=sector_slug,
                sub_industry_slug=sub_industry_slug,
                year=year_int,
            )
            if result is None:
                return {"not_found": True}
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def get_refresh_status(self, params=None) -> dict:
        try:
            return self._sanitize_for_json(self._refresh().get_refresh_status(params or {}))
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
        p = params or {}
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

    # ------------------------------------------------------------------
    # Internal refresh worker (drena jobs enfileirados em refresh_jobs)
    # ------------------------------------------------------------------

    def _start_refresh_worker(self) -> None:
        """Called from a daemon thread in app.py after window creation.

        Jobs enfileirados via ``CVMReadService.request_company_refresh``
        (caminho single-company com período) ficam pendentes na tabela
        ``refresh_jobs``. Sem este worker, eles nunca rodam no .exe.
        """
        try:
            from src.refresh_job_worker import (  # noqa: PLC0415
                RefreshJobWorker,
                RefreshWorkerConfig,
            )
            from src.refresh_service import HeadlessRefreshService  # noqa: PLC0415

            svc = self._svc()
            # Reusa o repository já inicializado pelo CVMReadService
            # (mesmo engine sqlite local, esquema já garantido).
            repository = svc.refresh_job_repository
            try:
                repository.ensure_schema()
            except Exception:
                pass

            refresh_service = HeadlessRefreshService(settings=svc.settings)
            worker = RefreshJobWorker(
                settings=svc.settings,
                repository=repository,
                refresh_service=refresh_service,
                config=RefreshWorkerConfig(),
            )
            worker.run_forever()
        except Exception:
            # Worker é best-effort: se falhar, o usuário ainda vê o status
            # "queued" no UI mas não trava o app.
            pass

    # ------------------------------------------------------------------
    # Auto-updater
    # ------------------------------------------------------------------

    def _start_update_check(self) -> None:
        """Called from a daemon thread in app.py after window creation."""
        try:
            from desktop.__version__ import __version__  # noqa: PLC0415
            from desktop.updater import UpdateChecker  # noqa: PLC0415
            checker = UpdateChecker()
            info = checker.check_for_update(__version__)
            with self._update_lock:
                self._update_info = info
        except Exception:
            pass

    def check_update(self, params=None) -> dict:
        with self._update_lock:
            info = self._update_info
        if not info:
            return self._sanitize_for_json({"available": False})
        return self._sanitize_for_json({
            "available": True,
            "version": info["version"],
            "zip_url": info["zip_url"],
        })

    def apply_update(self, params=None) -> dict:
        with self._update_lock:
            info = self._update_info
            if not info:
                return self._sanitize_for_json({"error": "no_update_available"})
            if self._update_progress.get("status") == "downloading":
                return self._sanitize_for_json({"error": "already_in_progress"})
            self._update_progress = {"status": "downloading", "percent": 0, "error": None}

        def _run() -> None:
            try:
                from desktop.updater import UpdateChecker  # noqa: PLC0415
                checker = UpdateChecker()

                def _progress(status: str, percent: int) -> None:
                    with self._update_lock:
                        self._update_progress = {"status": status, "percent": percent, "error": None}

                staged = checker.download_and_stage(info, _progress)

                with self._update_lock:
                    self._update_progress = {"status": "swapping", "percent": 100, "error": None}

                checker.spawn_helper_and_exit(staged)

                import webview  # noqa: PLC0415
                for w in webview.windows:
                    w.destroy()

            except Exception as exc:
                with self._update_lock:
                    self._update_progress = {"status": "error", "percent": 0, "error": str(exc)}

        threading.Thread(target=_run, name="desktop-apply-update", daemon=True).start()
        return self._sanitize_for_json({"started": True})

    def get_update_progress(self, params=None) -> dict:
        with self._update_lock:
            return self._sanitize_for_json(dict(self._update_progress))

    def snooze_update(self, params=None) -> dict:
        with self._update_lock:
            info = self._update_info
        if not info:
            return self._sanitize_for_json({"ok": False, "error": "no_update_info"})
        try:
            from desktop.updater import UpdateChecker  # noqa: PLC0415
            UpdateChecker().snooze(info["tag"])
            return self._sanitize_for_json({"ok": True})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    # ------------------------------------------------------------------
    # Health / diagnostico
    # ------------------------------------------------------------------

    def get_base_health(self, params=None) -> dict:
        p = params or {}
        try:
            start_year = int(p.get("start_year"))
            end_year = int(p.get("end_year"))
            force_raw = p.get("force_refresh", False)
            force_refresh = (
                force_raw.strip().lower() in {"1", "true", "yes", "sim"}
                if isinstance(force_raw, str)
                else bool(force_raw)
            )
            result = self._svc().get_health_snapshot(
                start_year=start_year,
                end_year=end_year,
                force_refresh=force_refresh,
            )
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def get_health(self, params=None) -> dict:
        try:
            svc = self._svc()
            # Faz uma consulta leve para checar DB
            svc.list_companies(page=1, page_size=1)
            return self._sanitize_for_json({
                "status": "ok",
                "version": "desktop",
                "database_dialect": "sqlite",
                "required_tables": [],
                "warnings": [],
                "errors": [],
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "status": "degraded",
                "version": "desktop",
                "database_dialect": "sqlite",
                "required_tables": [],
                "warnings": [],
                "errors": [{"severity": "error", "code": "db_error",
                            "message": str(exc), "path": None}],
            })

    def get_database_diagnostics(self, params=None) -> dict:
        """Real local SQLite database diagnostics for the Update Base UI.

        Returns explicit row counts for the tables an operator needs to see
        when verifying that a refresh actually populated the runtime DB.
        Distinct from `get_base_health`, which compares against the CVM
        active universe (not local row counts).
        """
        import sqlite3  # noqa: PLC0415

        try:
            svc = self._svc()
            db_path = svc.settings.paths.db_path
            db_path_str = str(db_path)
            db_exists = db_path.exists()
            db_size_bytes = int(db_path.stat().st_size) if db_exists else 0

            counts: dict[str, int | None] = {
                "companies": None,
                "financial_reports": None,
                "refresh_jobs": None,
                "company_refresh_status": None,
                "qa_logs": None,
            }
            latest_success_at: str | None = None
            latest_attempt_at: str | None = None
            latest_error: str | None = None

            if db_exists:
                try:
                    with sqlite3.connect(db_path_str) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        present = {row[0] for row in cur.fetchall()}
                        for table in counts.keys():
                            if table not in present:
                                counts[table] = 0
                                continue
                            try:
                                cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                                counts[table] = int(cur.fetchone()[0] or 0)
                            except Exception:
                                counts[table] = None
                        if "company_refresh_status" in present:
                            try:
                                cur.execute(
                                    "SELECT MAX(last_success_at), MAX(last_attempt_at) "
                                    'FROM "company_refresh_status"'
                                )
                                row = cur.fetchone() or (None, None)
                                latest_success_at = str(row[0]) if row[0] else None
                                latest_attempt_at = str(row[1]) if row[1] else None
                            except Exception:
                                pass
                            try:
                                cur.execute(
                                    "SELECT last_error FROM \"company_refresh_status\" "
                                    "WHERE last_error IS NOT NULL AND last_error <> '' "
                                    "ORDER BY last_attempt_at DESC LIMIT 1"
                                )
                                row = cur.fetchone()
                                if row and row[0]:
                                    latest_error = str(row[0])
                            except Exception:
                                pass
                except Exception as exc:
                    return self._sanitize_for_json({
                        "db_path": db_path_str,
                        "db_exists": db_exists,
                        "db_size_bytes": db_size_bytes,
                        "is_empty": True,
                        "row_counts": counts,
                        "latest_success_at": None,
                        "latest_attempt_at": None,
                        "latest_error": None,
                        "error": f"sqlite_open_failed: {exc}",
                    })

            is_empty = (
                not db_exists
                or (counts.get("companies") or 0) == 0
                or (counts.get("financial_reports") or 0) == 0
            )

            return self._sanitize_for_json({
                "db_path": db_path_str,
                "db_exists": db_exists,
                "db_size_bytes": db_size_bytes,
                "is_empty": is_empty,
                "row_counts": counts,
                "latest_success_at": latest_success_at,
                "latest_attempt_at": latest_attempt_at,
                "latest_error": latest_error,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "db_path": None,
                "db_exists": False,
                "db_size_bytes": 0,
                "is_empty": True,
                "row_counts": {
                    "companies": None,
                    "financial_reports": None,
                    "refresh_jobs": None,
                    "company_refresh_status": None,
                    "qa_logs": None,
                },
                "latest_success_at": None,
                "latest_attempt_at": None,
                "latest_error": None,
                "error": str(exc),
            })


def _serialize(obj: Any) -> Any:
    """Converte dataclasses e tuples para tipos serializáveis por pywebview."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, tuple):
        return list(obj)
    return obj
