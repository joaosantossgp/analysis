from __future__ import annotations

import dataclasses
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from desktop.bridge_api.status_diagnostics import StatusDiagnosticsMixin
from desktop.bridge_api.status_settings_health import StatusSettingsHealthMixin
from desktop.bridge_api.status_updates import StatusUpdatesMixin

logger = logging.getLogger("desktop.bridge")

class StatusBridgeMixin(StatusUpdatesMixin, StatusSettingsHealthMixin, StatusDiagnosticsMixin):
    def get_app_status(self, params=None) -> dict:
        """Compact local runtime status for the packaged Vite UI."""
        p = params or {}
        force_update_check = self._truthy(p.get("force_update_check", False))
        try:
            from desktop.__version__ import __version__  # noqa: PLC0415

            svc = self._svc()
            paths = svc.settings.paths
            path_map = self._status_path_map()
            database = self.get_database_diagnostics({})
            update = self._get_software_update_status(force=force_update_check)
            diagnostics = self._runtime_diagnostics_summary(paths)
            refresh_worker = self._refresh_worker_runtime_status()
            self._append_refresh_worker_diagnostics(diagnostics, refresh_worker)
            recent = self._collect_recent_diagnostics(paths, database)
            from desktop import lockfile as _lockfile  # noqa: PLC0415

            build_commit, build_time = self._build_provenance()

            return self._sanitize_for_json({
                "runtime": {
                    "version": __version__,
                    "build_commit": build_commit,
                    "build_time": build_time,
                    "runtime_mode": self._runtime_mode(),
                    "bridge_status": "ready",
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "desktop_shell": "pywebview/WebView2",
                    "local_first": True,
                    "using_release_data_dir": self._using_release_data_dir(),
                    "write_mode": "read-write" if self._is_write_allowed() else "read-only",
                    "lock_status": _lockfile.get_status(),
                    "refresh_worker": refresh_worker,
                },
                "paths": {
                    key: self._path_payload(key, value)
                    for key, value in path_map.items()
                },
                "database": database,
                "update": update,
                "diagnostics": diagnostics,
                "recent": recent,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "runtime": {
                    "version": "unknown",
                    "runtime_mode": self._runtime_mode(),
                    "bridge_status": "error",
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "desktop_shell": "pywebview/WebView2",
                    "local_first": True,
                    "using_release_data_dir": self._using_release_data_dir(),
                },
                "paths": {},
                "database": None,
                "update": None,
                "diagnostics": {
                    "ok": False,
                    "errors": [str(exc)],
                    "warnings": [],
                },
                "recent": [],
                "error": str(exc),
            })

    def get_storage_inventory(self, params=None) -> dict:
        """Return the latest cached storage inventory without starting a scan."""
        try:
            return self._sanitize_for_json(self._storage_inventory().latest())
        except Exception as exc:
            logger.error("failed to load storage inventory", exc_info=True)
            return self._sanitize_for_json({
                "contract_version": 1,
                "status": "unavailable",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "scanned_at": None,
                "is_cached": True,
                "is_stale": True,
                "scan_status": {"status": "failed", "error": str(exc)},
                "logical_bytes_total": 0,
                "file_count": 0,
                "directory_count": 0,
                "skipped_count": 0,
                "roots": [],
                "excluded_roots": [],
                "volumes": [],
                "categories": [],
                "segments": [],
                "databases": [],
                "largest_items": [],
                "growth": {"available": False, "reason": "Storage inventory could not be loaded."},
                "warnings": [],
                "errors": [str(exc)],
                "measurement_notes": [],
            })

    def start_storage_inventory_scan(self, params=None) -> dict:
        """Start one asynchronous storage inventory scan."""
        try:
            p = params or {}
            persist = not self._truthy(p.get("memory_only", False))
            return self._sanitize_for_json(self._storage_inventory().start_scan(persist=persist))
        except Exception as exc:
            logger.error("failed to start storage inventory scan", exc_info=True)
            return self._sanitize_for_json({"started": False, "error": str(exc), "scan_status": {"status": "failed", "error": str(exc)}})

    def get_storage_inventory_scan_status(self, params=None) -> dict:
        """Return active or last storage scan status without scanning."""
        try:
            return self._sanitize_for_json(self._storage_inventory().status())
        except Exception as exc:
            logger.error("failed to get storage inventory scan status", exc_info=True)
            return self._sanitize_for_json({"status": "failed", "error": str(exc)})

    def open_status_path(self, params=None) -> dict:
        """Open one of the known local diagnostics folders.

        Deliberately accepts only symbolic path kinds; the UI cannot pass an
        arbitrary filesystem path to this method.
        """
        p = params or {}
        kind = str(p.get("kind") or "").strip().lower()
        try:
            path_map = self._status_path_map()
            if kind not in path_map:
                return self._sanitize_for_json({
                    "ok": False,
                    "kind": kind,
                    "path": None,
                    "error": "unsupported_path_kind",
                })
            target = Path(path_map[kind])
            if kind == "database":
                target = target.parent
            if kind in {"data", "output", "logs", "cache"}:
                target.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                return self._sanitize_for_json({
                    "ok": False,
                    "kind": kind,
                    "path": str(target),
                    "error": "path_not_found",
                })
            self._open_local_folder(target)
            return self._sanitize_for_json({
                "ok": True,
                "kind": kind,
                "path": str(target),
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "ok": False,
                "kind": kind,
                "path": None,
                "error": str(exc),
            })

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "sim", "on"}
        return bool(value)

    @staticmethod
    def _build_provenance() -> tuple[str | None, str | None]:
        """Return (build_commit, build_time) written by build_desktop.ps1.

        Generated builds ship desktop/_build_info.py. Dev runs have no such
        file, so a missing module reports (None, None) rather than failing.
        """
        try:
            from desktop._build_info import build_commit, build_time  # noqa: PLC0415

            return (build_commit or None, build_time or None)
        except Exception:
            return (None, None)

    @staticmethod
    def _runtime_mode() -> str:
        argv = {str(arg).lower() for arg in sys.argv}
        if "--dev" in argv and not getattr(sys, "frozen", False):
            use_release = os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {
                "1", "true", "yes",
            }
            return "vite-dev-release-data" if use_release else "vite-dev"
        return "vite"

    @staticmethod
    def _using_release_data_dir() -> bool:
        if getattr(sys, "frozen", False):
            return True
        return os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {"1", "true", "yes"}

    @staticmethod
    def _is_write_allowed() -> bool:
        """Returns True if destructive/write operations are safe in this mode."""
        if getattr(sys, "frozen", False):
            return True
        use_release = os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {
            "1", "true", "yes",
        }
        if not use_release:
            return True
        # Concurrent lock detected — block writes unconditionally.
        if os.environ.get("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", "").strip() == "1":
            return False
        # Allow writes only when explicitly opted in.
        return os.environ.get("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", "").strip().lower() in {
            "1", "true", "yes",
        }

    @staticmethod
    def _write_blocked_response(op_name: str = "operation") -> dict:
        concurrent = os.environ.get("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", "").strip() == "1"
        if concurrent:
            msg = (
                f"Write blocked: release data directory is in use by another CVMAnalytics process. "
                "Close the packaged app before running write operations from dev mode."
            )
            code = "concurrent_lock_conflict"
        else:
            msg = (
                f"Write blocked: dev mode is using the release data directory. "
                "Set CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES=1 to enable writes, "
                "or use isolated dev data (omit CVMANALYTICS_USE_RELEASE_DATA)."
            )
            code = "release_data_write_blocked"
        return {
            "ok": False,
            "status": "blocked",
            "error": msg,
            "status_reason_code": code,
            "status_reason_message": msg,
            "is_retry_allowed": False,
        }

    def _status_path_map(self) -> dict[str, Path]:
        paths = self._svc().settings.paths
        return {
            "data": Path(paths.data_dir),
            "database": Path(paths.db_path),
            "output": Path(paths.output_dir),
            "logs": Path(paths.logs_dir),
            "cache": Path(paths.cache_dir),
        }

    @staticmethod
    def _path_payload(kind: str, path: Path) -> dict:
        path = Path(path)
        return {
            "kind": kind,
            "path": str(path),
            "exists": path.exists(),
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
        }

    @staticmethod
    def _open_local_folder(target: Path) -> None:
        if os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
            return
        subprocess.Popen(["xdg-open", str(target)])

    def set_company_ignored(self, params=None) -> dict:
        """Toggle the per-company `ignored` flag in company_refresh_status."""
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("set_company_ignored"))
        import sqlite3  # noqa: PLC0415
        from datetime import datetime as _dt  # noqa: PLC0415

        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm") or 0)
        except Exception:
            return self._sanitize_for_json({
                "ok": False,
                "error": "cd_cvm invalido",
            })
        if cd_cvm <= 0:
            return self._sanitize_for_json({
                "ok": False,
                "error": "cd_cvm obrigatorio",
            })
        ignored_flag = 1 if self._truthy(p.get("ignored", True)) else 0
        reason_raw = p.get("reason")
        reason = str(reason_raw).strip() if reason_raw else None
        now_iso = _dt.now().isoformat(timespec="seconds")

        try:
            from src.refresh.jobs import (  # noqa: PLC0415
                ensure_refresh_runtime_tables_for_connection,
            )
            from sqlalchemy import text as _text  # noqa: PLC0415

            svc = self._svc()
            with svc.engine.begin() as conn:
                ensure_refresh_runtime_tables_for_connection(conn)
                # INSERT-or-UPDATE so flipping ignored on a company that has
                # never been touched by the refresh pipeline still works.
                conn.execute(
                    _text(
                        """
                        INSERT INTO company_refresh_status (
                            cd_cvm, company_name, source_scope,
                            last_attempt_at, last_status, last_start_year, last_end_year,
                            updated_at, ignored, ignored_at, ignored_reason
                        ) VALUES (
                            :cd_cvm, :company_name, 'local',
                            NULL, NULL, NULL, NULL,
                            :updated_at, :ignored, :ignored_at, :ignored_reason
                        )
                        ON CONFLICT(cd_cvm) DO UPDATE SET
                            ignored = excluded.ignored,
                            ignored_at = excluded.ignored_at,
                            ignored_reason = excluded.ignored_reason,
                            updated_at = excluded.updated_at
                        """
                    ),
                    {
                        "cd_cvm": int(cd_cvm),
                        "company_name": str(p.get("company_name") or cd_cvm),
                        "updated_at": now_iso,
                        "ignored": int(ignored_flag),
                        "ignored_at": now_iso if ignored_flag else None,
                        "ignored_reason": reason if ignored_flag else None,
                    },
                )
            svc.invalidate_read_caches()
            self._clear_data_coverage_cache()
            return self._sanitize_for_json({
                "ok": True,
                "cd_cvm": int(cd_cvm),
                "ignored": bool(ignored_flag),
                "ignored_at": now_iso if ignored_flag else None,
                "ignored_reason": reason if ignored_flag else None,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "ok": False,
                "error": str(exc),
            })

    def get_data_coverage(self, params=None) -> dict:
        """Data Coverage / Missing Data report for the active CVM universe.

        Joins three sources:
          1. Active company universe (cached CVM catalog).
          2. `financial_reports` — latest DFP (PERIOD_LABEL == REPORT_YEAR)
             and latest ITR (interim) per cd_cvm.
          3. `company_refresh_status` — last update status + error.
          4. TICKER_MAP — ticker resolution.

        Returns rows with a derived `status` and per-filter boolean flags so
        the frontend can render summary cards, filter chips, and the table
        from a single payload.
        """
        try:
            from src.platform.settings import get_settings  # noqa: PLC0415

            settings = get_settings()
            cache_signature = self._data_coverage_cache_signature_from_settings(settings)
            cache_path = (
                Path(settings.paths.cache_dir)
                / f"data_coverage_v{self.DATA_COVERAGE_CACHE_SCHEMA_VERSION}.json"
            )
            with self._read_payload_cache_lock:
                if (
                    self._data_coverage_cache is not None
                    and self._data_coverage_cache[0] == cache_signature
                ):
                    return self._sanitize_for_json(self._data_coverage_cache[1])
            cached_payload = self._read_payload_cache(
                cache_path,
                schema_version=self.DATA_COVERAGE_CACHE_SCHEMA_VERSION,
                signature=cache_signature,
            )
            if cached_payload is not None:
                with self._read_payload_cache_lock:
                    self._data_coverage_cache = (cache_signature, cached_payload)
                return self._sanitize_for_json(cached_payload)

            from desktop.services import IntelligentSelectorService  # noqa: PLC0415
            from src.financials.local_data_coverage import (  # noqa: PLC0415
                build_local_data_coverage_report,
            )

            svc = self._svc()
            selector = IntelligentSelectorService(settings=svc.settings)
            universe = selector.load_active_universe()
            report = build_local_data_coverage_report(
                db_path=svc.settings.paths.db_path,
                universe=universe,
            )
            payload = self._sanitize_for_json(report)
            with self._read_payload_cache_lock:
                self._data_coverage_cache = (cache_signature, payload)
            self._write_payload_cache(
                cache_path,
                schema_version=self.DATA_COVERAGE_CACHE_SCHEMA_VERSION,
                signature=cache_signature,
                payload=payload,
            )
            return payload
        except Exception as exc:
            return self._sanitize_for_json({
                "generated_at": None,
                "stale_cutoff_year": None,
                "summary": {
                    "total": 0,
                    "complete": 0,
                    "partial": 0,
                    "no_financial": 0,
                    "failed": 0,
                    "stale": 0,
                    "unmapped": 0,
                },
                "filter_counts": {},
                "rows": [],
                "error": str(exc),
            })

    def get_local_database_state(self, params=None) -> dict:
        """Single read of the local database state for the shell indicator.

        Reads local files only: never starts network work and never rewrites
        the refresh job store.
        """
        from src.refresh.local_database_state import (  # noqa: PLC0415
            derive_local_database_state,
            read_local_database_facts,
        )

        try:
            paths = self._svc().settings.paths
            has_statements, failures = False, []
            if paths.db_path.exists():
                from sqlalchemy import create_engine  # noqa: PLC0415

                engine = create_engine(f"sqlite:///file:{paths.db_path.as_posix()}?mode=ro&uri=true")
                try:
                    has_statements, failures = read_local_database_facts(engine)
                finally:
                    engine.dispose()
            state = derive_local_database_state(
                has_statements=has_statements,
                jobs=self._local_state_jobs(paths.data_dir / "refresh_jobs.json"),
                now=datetime.now(timezone.utc),
            )
            state["failures"] = failures
            return self._sanitize_for_json(state)
        except Exception as exc:
            logger.exception("get_local_database_state failed")
            return self._sanitize_for_json({"state": "unknown", "error": str(exc)})

    def _local_state_jobs(self, jobs_path: Path) -> list[dict[str, Any]]:
        manager = getattr(self, "_refresh_manager", None)
        if manager is not None:
            return manager.snapshot_jobs()
        if not jobs_path.exists():
            return []
        try:
            payload = json.loads(jobs_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        jobs = [j for j in (payload or {}).get("jobs") or [] if isinstance(j, dict)]
        # No manager in this process means nothing is running here: a job left
        # active by a closed app reads as interrupted, without rewriting the file.
        return [
            {**j, "state": "interrupted"} if str(j.get("state")) in {"queued", "running"} else j
            for j in jobs
        ]

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
            if not force_refresh:
                cached = self._get_cached_base_health_snapshot(
                    start_year=start_year,
                    end_year=end_year,
                )
                if cached is not None:
                    return self._sanitize_for_json(cached)
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
