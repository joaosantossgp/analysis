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


class StatusBridgeMixin:
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
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("apply_update"))
        with self._update_lock:
            info = self._update_info
            if not info:
                return self._sanitize_for_json({"error": "no_update_available"})
            if self._update_progress.get("status") == "downloading":
                return self._sanitize_for_json({"error": "already_in_progress"})
            self._update_progress = {"status": "downloading", "percent": 0, "error": None}

        def _run() -> None:
            try:
                from desktop.updater import UpdateChecker, _log as _update_log  # noqa: PLC0415
                _update_log(
                    f"apply_update invoked: version={info.get('version')} "
                    f"tag={info.get('tag')} zip_url={info.get('zip_url')}"
                )
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
                try:
                    from desktop.updater import _log as _update_log  # noqa: PLC0415
                    _update_log(f"ERROR apply_update failed: {exc}")
                except Exception:
                    pass
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

    def _refresh_worker_runtime_status(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "unknown",
            "worker_id": None,
            "started_at": None,
            "last_heartbeat_at": None,
            "last_error": None,
            "active_jobs": 0,
            "heartbeat_age_seconds": None,
            "stale": False,
        }
        try:
            db_path = Path(self._svc().settings.paths.db_path)
            if not db_path.exists():
                payload["status"] = "database_missing"
                return payload

            uri = db_path.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                conn.row_factory = sqlite3.Row
                present = {
                    str(row[0])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "app_settings" in present:
                    keys = (
                        "refresh_worker_status",
                        "refresh_worker_id",
                        "refresh_worker_started_at",
                        "refresh_worker_last_heartbeat_at",
                        "refresh_worker_last_error",
                    )
                    placeholders = ",".join("?" for _ in keys)
                    rows = conn.execute(
                        f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
                        keys,
                    ).fetchall()
                    for row in rows:
                        raw = row["value"]
                        try:
                            value = json.loads(raw) if raw is not None else None
                        except Exception:
                            value = raw
                        key = str(row["key"])
                        if key == "refresh_worker_status":
                            payload["status"] = str(value or "unknown")
                        elif key == "refresh_worker_id":
                            payload["worker_id"] = value
                        elif key == "refresh_worker_started_at":
                            payload["started_at"] = value
                        elif key == "refresh_worker_last_heartbeat_at":
                            payload["last_heartbeat_at"] = value
                        elif key == "refresh_worker_last_error":
                            payload["last_error"] = value or None

                if "refresh_jobs" in present:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM refresh_jobs WHERE lower(state) IN ('queued', 'running')"
                    ).fetchone()
                    payload["active_jobs"] = int(row[0] or 0) if row else 0

            last_heartbeat_at = payload.get("last_heartbeat_at")
            if last_heartbeat_at:
                try:
                    raw_ts = str(last_heartbeat_at).replace("Z", "+00:00")
                    heartbeat_dt = datetime.fromisoformat(raw_ts)
                    if heartbeat_dt.tzinfo is None:
                        heartbeat_dt = heartbeat_dt.replace(tzinfo=timezone.utc)
                    age = max(
                        0,
                        int((datetime.now(timezone.utc) - heartbeat_dt.astimezone(timezone.utc)).total_seconds()),
                    )
                    payload["heartbeat_age_seconds"] = age
                except Exception:
                    payload["heartbeat_age_seconds"] = None

            heartbeat_age = payload.get("heartbeat_age_seconds")
            active_jobs = int(payload.get("active_jobs") or 0)
            if active_jobs > 0 and (heartbeat_age is None or int(heartbeat_age) > 30):
                payload["stale"] = True
            return payload
        except Exception as exc:
            payload["status"] = "error"
            payload["last_error"] = str(exc)
            return payload

    @staticmethod
    def _append_refresh_worker_diagnostics(
        diagnostics: dict[str, Any],
        worker_status: dict[str, Any],
    ) -> None:
        warnings = diagnostics.setdefault("warnings", [])
        errors = diagnostics.setdefault("errors", [])
        status = str(worker_status.get("status") or "unknown").lower()
        active_jobs = int(worker_status.get("active_jobs") or 0)
        if status == "error":
            errors.append(
                "Refresh worker failed: "
                + str(worker_status.get("last_error") or "no error recorded")
            )
        elif active_jobs > 0 and worker_status.get("stale"):
            warnings.append(
                "Refresh jobs are queued/running but the worker heartbeat is missing or stale."
            )

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

    def get_settings_health_summary(self, params=None) -> dict:
        """Fast, read-only Settings health summary.

        This intentionally avoids the full coverage table and distribution
        health reads. Segment details stay behind their existing routes.
        """
        started = time.perf_counter()
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        warnings: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []

        def add_provenance(metric: str, source: str, meaning: str, cost: str, cache_policy: str = "live") -> None:
            provenance.append({
                "metric": metric,
                "source": source,
                "meaning": meaning,
                "cost": cost,
                "cache_policy": cache_policy,
                "failure_behavior": "reported as unknown/unavailable; errors are not coerced to healthy",
            })

        try:
            from desktop.__version__ import __version__  # noqa: PLC0415
            from desktop import lockfile as _lockfile  # noqa: PLC0415

            svc = self._svc()
            paths = svc.settings.paths
            path_map = self._status_path_map()
            lock_status = _lockfile.get_status()
            write_mode = "read-write" if self._is_write_allowed() else "read-only"
            refresh_worker = self._refresh_worker_runtime_status()
            runtime = {
                "version": __version__,
                "runtime_mode": self._runtime_mode(),
                "bridge_status": "ready",
                "frozen": bool(getattr(sys, "frozen", False)),
                "desktop_shell": "pywebview/WebView2",
                "local_first": True,
                "using_release_data_dir": self._using_release_data_dir(),
                "write_mode": write_mode,
                "lock_status": lock_status,
                "refresh_worker": refresh_worker,
            }
            storage = {
                key: self._path_payload(key, value)
                for key, value in path_map.items()
            }
            storage_inventory = self._storage_inventory().compact_summary()
            database = self.get_database_diagnostics({"summary_only": True})
            cvm_presence = self._settings_cvm_presence()
            refresh_payload = self._get_refresh_status_light({})
            active_jobs = [
                {
                    "job_id": item.get("job_id"),
                    "segment_id": "cvm_financials",
                    "status": item.get("state") or item.get("status"),
                    "stage": item.get("stage"),
                    "started_at": item.get("started_at") or item.get("accepted_at"),
                    "updated_at": item.get("updated_at"),
                    "message": (item.get("log_lines") or [None])[-1],
                }
                for item in refresh_payload.get("items", [])
                if str(item.get("state") or item.get("status") or "").lower() in {"queued", "running"}
            ]

            add_provenance(
                "runtime",
                "desktop.bridge_api.status.get_settings_health_summary",
                "Desktop mode, write policy, and lock status.",
                "constant-time environment and lockfile read",
            )
            add_provenance(
                "storage",
                "src.platform.settings.AppPaths",
                "Configured local data folders and database paths.",
                "filesystem stat only",
            )
            add_provenance(
                "storage_inventory",
                "desktop.storage_inventory cached snapshot",
                "Latest persisted local data footprint inventory; never starts a recursive scan.",
                "metadata JSON read only",
            )
            add_provenance(
                "cvm_presence",
                "cvm_financials.db sqlite_master + SELECT 1 probes",
                "Whether required CVM tables contain at least one usable row.",
                "bounded table-existence and one-row probes",
            )
            add_provenance(
                "active_jobs",
                "get_refresh_status light path",
                "Active CVM refresh jobs without instantiating the full refresh manager.",
                "JSON status file plus indexed recent refresh_jobs rows",
            )

            segments: list[dict[str, Any]] = []

            db_error = database.get("error")
            if db_error:
                errors.append({
                    "segment_id": "cvm_financials",
                    "severity": "critical",
                    "message": str(db_error),
                    "action_route": "/settings/diagnostics",
                })

            companies_count = cvm_presence.get("companies_count")
            companies_status = "healthy" if cvm_presence.get("companies_has_rows") else "empty"
            if db_error:
                companies_status = "critical"
            elif not database.get("db_exists"):
                companies_status = "empty"
            segments.append({
                "id": "cvm_registry",
                "name": "Companies and CVM Registry",
                "required": True,
                "status": companies_status,
                "reason": (
                    "Company registry is readable."
                    if companies_status == "healthy"
                    else "No company registry rows were found."
                ),
                "owner": "cvm_financials.db",
                "provider": "CVM/B3 metadata",
                "record_count": companies_count,
                "latest_reference": None,
                "last_successful_update": database.get("latest_success_at"),
                "last_attempted_update": database.get("latest_attempt_at"),
                "dimensions": {
                    "availability": companies_status,
                    "freshness": "unknown",
                    "coverage": "unknown",
                    "integrity": "critical" if db_error else "unknown",
                    "last_refresh": "unknown",
                    "source": "unknown",
                },
                "warnings": [],
                "errors": [str(db_error)] if db_error else [],
                "action_route": "/settings/storage" if companies_status == "empty" else "/settings/health",
                "details": {"metric_source": "bounded_presence_probe"},
            })

            reports_status = "healthy" if cvm_presence.get("financial_reports_has_rows") else "empty"
            refresh_errors = database.get("refresh_errors_count")
            if db_error:
                reports_status = "critical"
            elif active_jobs:
                reports_status = "updating"
            elif database.get("latest_error"):
                reports_status = "degraded"
            elif refresh_errors:
                reports_status = "degraded"
            segments.append({
                "id": "cvm_financials",
                "name": "CVM Financial Statements",
                "required": True,
                "status": reports_status,
                "reason": self._settings_segment_reason(
                    reports_status,
                    healthy="Financial statement rows are present.",
                    empty="No usable local financial statements were found.",
                    degraded="Recent refresh errors are recorded, but local data may remain usable.",
                    updating="A CVM data update is currently running.",
                    critical=str(db_error) if db_error else "Database diagnostics failed.",
                ),
                "owner": "cvm_financials.db",
                "provider": "CVM filings",
                "record_count": cvm_presence.get("financial_reports_count"),
                "latest_reference": self._settings_report_period(database),
                "last_successful_update": database.get("latest_success_at"),
                "last_attempted_update": database.get("latest_attempt_at"),
                "dimensions": {
                    "availability": "healthy" if cvm_presence.get("financial_reports_has_rows") else "empty",
                    "freshness": "unknown",
                    "coverage": "deferred",
                    "integrity": "critical" if db_error else "unknown",
                    "last_refresh": "degraded" if database.get("latest_error") else "unknown",
                    "source": "unknown",
                },
                "warnings": [database.get("latest_error")] if database.get("latest_error") else [],
                "errors": [str(db_error)] if db_error else [],
                "action_route": "/settings/updates" if reports_status in {"empty", "degraded"} else "/settings/coverage",
                "details": {"coverage_route": "/settings/coverage"},
            })

            self._append_optional_settings_segments(
                segments=segments,
                warnings=warnings,
                add_provenance=add_provenance,
            )

            if write_mode == "read-only":
                warnings.append({
                    "segment_id": "runtime",
                    "severity": "warning",
                    "message": "The app is in read-only mode. Diagnostics remain available, but update/import actions are blocked.",
                    "action_route": "/settings/diagnostics",
                })
            storage_status = str(storage_inventory.get("status") or "unknown")
            if storage_status in {"degraded", "critical", "unknown", "updating"}:
                issue = {
                    "segment_id": "storage",
                    "severity": "error" if storage_status == "critical" else "warning",
                    "message": self._settings_storage_issue(storage_inventory),
                    "action_route": "/settings/storage",
                }
                if storage_status == "critical":
                    errors.append(issue)
                else:
                    warnings.append(issue)
            if str(lock_status.get("status") or "") == "locked_by_other":
                errors.append({
                    "segment_id": "runtime",
                    "severity": "critical",
                    "message": "The local data directory is locked by another CVMAnalytics process.",
                    "action_route": "/settings/diagnostics",
                })
            if str(refresh_worker.get("status") or "").lower() == "error":
                errors.append({
                    "segment_id": "runtime",
                    "severity": "critical",
                    "message": "Refresh worker failed: "
                    + str(refresh_worker.get("last_error") or "no error recorded"),
                    "action_route": "/settings/updates",
                })
            elif int(refresh_worker.get("active_jobs") or 0) > 0 and refresh_worker.get("stale"):
                warnings.append({
                    "segment_id": "runtime",
                    "severity": "warning",
                    "message": "Refresh jobs are queued/running but the worker heartbeat is missing or stale.",
                    "action_route": "/settings/updates",
                })

            overall_status = self._settings_overall_status(
                segments=segments,
                active_jobs=active_jobs,
                errors=errors,
                warnings=warnings,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            return self._sanitize_for_json({
                "generated_at": generated_at,
                "overall_status": overall_status,
                "summary": {
                    "title": self._settings_overall_title(overall_status),
                    "message": self._settings_overall_message(overall_status, segments, active_jobs),
                    "required_segments": sum(1 for s in segments if s.get("required")),
                    "critical_segments": sum(1 for s in segments if s.get("status") == "critical"),
                    "degraded_segments": sum(1 for s in segments if s.get("status") == "degraded"),
                    "empty_segments": sum(1 for s in segments if s.get("status") == "empty"),
                    "updating_segments": sum(1 for s in segments if s.get("status") == "updating"),
                    "unknown_segments": sum(1 for s in segments if s.get("status") in {"unknown", "unavailable"}),
                    "initial_load_duration_ms": duration_ms,
                    "initial_bridge_calls": 1,
                    "full_table_scans": False,
                    "deferred_detail_contracts": ["get_data_coverage", "get_distribution_health"],
                },
                "segments": self._settings_sorted_segments(segments),
                "active_jobs": active_jobs,
                "warnings": warnings,
                "errors": errors,
                "storage": storage,
                "storage_inventory": storage_inventory,
                "runtime": runtime,
                "provenance": provenance,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "generated_at": generated_at,
                "overall_status": "unknown",
                "summary": {
                    "title": "Settings health unavailable",
                    "message": str(exc),
                    "initial_bridge_calls": 1,
                    "full_table_scans": False,
                },
                "segments": [],
                "active_jobs": [],
                "warnings": [],
                "errors": [{
                    "segment_id": "settings",
                    "severity": "critical",
                    "message": str(exc),
                    "action_route": "/settings/diagnostics",
                }],
                "storage": {},
                "storage_inventory": None,
                "runtime": {
                    "version": "unknown",
                    "runtime_mode": self._runtime_mode(),
                    "bridge_status": "error",
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "desktop_shell": "pywebview/WebView2",
                    "local_first": True,
                    "using_release_data_dir": self._using_release_data_dir(),
                },
                "provenance": [],
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

    def _settings_cvm_presence(self) -> dict[str, Any]:
        db_path = self._svc().settings.paths.db_path
        result: dict[str, Any] = {
            "companies_has_rows": False,
            "financial_reports_has_rows": False,
            "companies_count": None,
            "financial_reports_count": None,
        }
        if not Path(db_path).exists():
            return result
        try:
            with sqlite3.connect(str(db_path)) as conn:
                cur = conn.cursor()
                present = {
                    row[0]
                    for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                for table, key in (
                    ("companies", "companies"),
                    ("financial_reports", "financial_reports"),
                ):
                    if table not in present:
                        continue
                    safe_table = table.replace('"', '""')
                    has_row = cur.execute(f'SELECT 1 FROM "{safe_table}" LIMIT 1').fetchone() is not None
                    result[f"{key}_has_rows"] = has_row
                    # Exact count is intentionally skipped here; Status/Diagnostics owns full row counts.
        except Exception as exc:
            result["error"] = str(exc)
        return result

    @staticmethod
    def _settings_storage_issue(storage_inventory: dict[str, Any]) -> str:
        status = str(storage_inventory.get("status") or "unknown")
        if status == "critical":
            return "Storage inventory reports critically low disk space or a blocking storage error."
        if status in {"degraded", "partial"}:
            return "Storage inventory is partial, stale, or has warnings that need review."
        if status == "updating":
            return "Storage inventory scan is currently running; cached values remain visible."
        if status == "unknown":
            return "No storage inventory snapshot is available yet."
        return "Storage inventory needs review."

    def _append_optional_settings_segments(self, *, segments: list[dict[str, Any]], warnings: list[dict[str, Any]], add_provenance) -> None:
        add_provenance(
            "energy_macro_health",
            "get_energy_kpi_health",
            "Country-level energy KPI refresh, staleness, and data-quality summary.",
            "small indexed summary queries",
        )
        try:
            energy = self.get_energy_kpi_health({})
            if energy.get("error"):
                raise RuntimeError(str(energy.get("error")))
            status = "updating" if energy.get("refresh_running") else (
                "critical" if energy.get("refresh_error") else
                "degraded" if energy.get("is_stale") or energy.get("dq_errors") or energy.get("dq_warnings") else
                "empty" if not energy.get("last_refresh_at") and not energy.get("rows_ingested") else
                "healthy"
            )
            segments.append({
                "id": "energy_macro",
                "name": "Energy Macro Indicators",
                "required": False,
                "status": status,
                "reason": self._settings_segment_reason(
                    status,
                    healthy="Energy KPI cache has recent usable data.",
                    empty="No energy KPI refresh has been recorded.",
                    degraded="Energy KPI data is stale or has data-quality warnings.",
                    updating="An energy KPI refresh is running.",
                    critical=str(energy.get("refresh_error") or "Energy KPI health failed."),
                ),
                "owner": "energy_kpis.db",
                "provider": "OWID / Ember",
                "record_count": energy.get("rows_ingested"),
                "latest_reference": energy.get("owid_fetched_at"),
                "last_successful_update": energy.get("last_refresh_at"),
                "last_attempted_update": energy.get("last_refresh_at"),
                "dimensions": {
                    "availability": "healthy" if energy.get("last_refresh_at") else "empty",
                    "freshness": "degraded" if energy.get("is_stale") else "healthy",
                    "coverage": "unknown",
                    "integrity": "degraded" if energy.get("dq_errors") or energy.get("dq_warnings") else "unknown",
                    "last_refresh": "critical" if energy.get("refresh_error") else "unknown",
                    "source": "unknown",
                },
                "warnings": [f"{energy.get('dq_warnings')} data-quality warning(s)"] if energy.get("dq_warnings") else [],
                "errors": [str(energy.get("refresh_error"))] if energy.get("refresh_error") else [],
                "action_route": "/indicators",
                "details": {"source": "get_energy_kpi_health"},
            })
        except Exception as exc:
            segments.append(self._settings_unavailable_segment(
                "energy_macro",
                "Energy Macro Indicators",
                "energy_kpis.db",
                "OWID / Ember",
                "/indicators",
                str(exc),
            ))

        add_provenance(
            "sin_health",
            "get_sin_kpi_health",
            "SIN/ONS latest reference, refresh status, and data-quality summary.",
            "small indexed summary queries",
        )
        try:
            sin = self.get_sin_kpi_health({})
            if sin.get("error"):
                raise RuntimeError(str(sin.get("error")))
            status = "updating" if sin.get("refresh_running") else (
                "critical" if sin.get("refresh_error") else
                "degraded" if sin.get("is_stale") or sin.get("dq_errors") or sin.get("dq_warnings") else
                "empty" if not sin.get("latest_reference_datetime") else
                "healthy"
            )
            segments.append({
                "id": "sin",
                "name": "SIN / ONS",
                "required": False,
                "status": status,
                "reason": self._settings_segment_reason(
                    status,
                    healthy="SIN cache has a latest reference timestamp.",
                    empty="No SIN observations were found.",
                    degraded="SIN data is stale or has data-quality warnings.",
                    updating="A SIN refresh is running.",
                    critical=str(sin.get("refresh_error") or "SIN health failed."),
                ),
                "owner": "energy_kpis.db",
                "provider": "ONS / CCEE",
                "record_count": sin.get("rows_ingested"),
                "latest_reference": sin.get("latest_reference_datetime"),
                "last_successful_update": sin.get("last_refresh_at"),
                "last_attempted_update": sin.get("last_refresh_at"),
                "dimensions": {
                    "availability": "healthy" if sin.get("latest_reference_datetime") else "empty",
                    "freshness": "degraded" if sin.get("is_stale") else "healthy",
                    "coverage": "unknown",
                    "integrity": "degraded" if sin.get("dq_errors") or sin.get("dq_warnings") else "unknown",
                    "last_refresh": "critical" if sin.get("refresh_error") else "unknown",
                    "source": "unknown",
                },
                "warnings": [f"{sin.get('dq_warnings')} data-quality warning(s)"] if sin.get("dq_warnings") else [],
                "errors": [str(sin.get("refresh_error"))] if sin.get("refresh_error") else [],
                "action_route": "/indicators",
                "details": {"source": "get_sin_kpi_health"},
            })
        except Exception as exc:
            segments.append(self._settings_unavailable_segment(
                "sin",
                "SIN / ONS",
                "energy_kpis.db",
                "ONS / CCEE",
                "/indicators",
                str(exc),
            ))

        plant_state = self._plant_parcel_refresh_status()
        segments.append({
            "id": "plant_parcels",
            "name": "Generation Assets and CCEE Plant Data",
            "required": False,
            "status": "updating" if plant_state.get("status") == "running" else (
                "critical" if plant_state.get("status") == "error" else "unknown"
            ),
            "reason": (
                "Plant source import or refresh is running."
                if plant_state.get("status") == "running"
                else "Detailed plant source counts are loaded only in Sources and Imports."
            ),
            "owner": "energy_kpis.db",
            "provider": "ANEEL / CCEE",
            "record_count": None,
            "latest_reference": None,
            "last_successful_update": plant_state.get("finished_at"),
            "last_attempted_update": plant_state.get("started_at"),
            "dimensions": {
                "availability": "deferred",
                "freshness": "deferred",
                "coverage": "deferred",
                "integrity": "unknown",
                "last_refresh": "updating" if plant_state.get("status") == "running" else "unknown",
                "source": "deferred",
            },
            "warnings": [plant_state.get("warning")] if plant_state.get("warning") else [],
            "errors": [plant_state.get("error")] if plant_state.get("error") else [],
            "action_route": "/settings/sources",
            "details": {"deferred_contract": "get_plant_parcel_source_statuses"},
        })
        add_provenance(
            "plant_parcels",
            "_plant_parcel_refresh_status",
            "Active plant/CCEE refresh state only; source counts are deferred.",
            "in-memory state only",
        )

        dist_state = self._dist_refresh_status()
        segments.append({
            "id": "distribution",
            "name": "Distribution / ANEEL",
            "required": False,
            "status": "updating" if dist_state.get("status") == "running" else (
                "critical" if dist_state.get("status") == "error" else "unknown"
            ),
            "reason": (
                str(dist_state.get("message") or "Distribution refresh is running.")
                if dist_state.get("status") == "running"
                else "Distribution row counts and source snapshots are loaded only in the Indicators module."
            ),
            "owner": "energy_kpis.db",
            "provider": "ANEEL",
            "record_count": None,
            "latest_reference": None,
            "last_successful_update": None,
            "last_attempted_update": None,
            "dimensions": {
                "availability": "deferred",
                "freshness": "deferred",
                "coverage": "deferred",
                "integrity": "deferred",
                "last_refresh": "updating" if dist_state.get("status") == "running" else "unknown",
                "source": "deferred",
            },
            "warnings": [],
            "errors": [dist_state.get("error")] if dist_state.get("error") else [],
            "action_route": "/indicators",
            "details": {"deferred_contract": "get_distribution_health"},
        })
        add_provenance(
            "distribution",
            "get_distribution_refresh_status",
            "Active distribution refresh state only; full health is deferred to avoid initial COUNT scans.",
            "small refresh-state read",
        )

        segments.append({
            "id": "market_data",
            "name": "Market Data",
            "required": False,
            "status": "unknown",
            "reason": "Market snapshots are checked in company and update workflows; Settings does not infer official availability from row counts.",
            "owner": "cvm_financials.db",
            "provider": "Yahoo Finance / local snapshots",
            "record_count": None,
            "latest_reference": None,
            "last_successful_update": None,
            "last_attempted_update": None,
            "dimensions": {
                "availability": "unknown",
                "freshness": "unknown",
                "coverage": "unknown",
                "integrity": "unknown",
                "last_refresh": "unknown",
                "source": "unknown",
            },
            "warnings": [],
            "errors": [],
            "action_route": "/settings/updates",
            "details": {"note": "Yahoo Finance data is unofficial and not CVM/B3 official data."},
        })

    @staticmethod
    def _settings_unavailable_segment(segment_id: str, name: str, owner: str, provider: str, route: str, reason: str) -> dict[str, Any]:
        return {
            "id": segment_id,
            "name": name,
            "required": False,
            "status": "unavailable",
            "reason": reason,
            "owner": owner,
            "provider": provider,
            "record_count": None,
            "latest_reference": None,
            "last_successful_update": None,
            "last_attempted_update": None,
            "dimensions": {
                "availability": "unavailable",
                "freshness": "unknown",
                "coverage": "unknown",
                "integrity": "unknown",
                "last_refresh": "unknown",
                "source": "unknown",
            },
            "warnings": [reason],
            "errors": [],
            "action_route": route,
            "details": {},
        }

    @staticmethod
    def _settings_segment_reason(status: str, **messages: str) -> str:
        return messages.get(status) or messages.get("healthy") or status

    @staticmethod
    def _settings_report_period(database: dict[str, Any]) -> str | None:
        year = database.get("latest_report_year")
        period = database.get("latest_period_label")
        if not year:
            return None
        return f"{year} · {period}" if period else str(year)

    @staticmethod
    def _settings_sorted_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        order = {"critical": 0, "degraded": 1, "empty": 2, "updating": 3, "healthy": 4, "unknown": 5, "unavailable": 6}
        return sorted(segments, key=lambda row: (order.get(str(row.get("status")), 9), not bool(row.get("required")), str(row.get("name") or "")))

    @staticmethod
    def _settings_overall_status(*, segments: list[dict[str, Any]], active_jobs: list[dict[str, Any]], errors: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> str:
        required = [s for s in segments if s.get("required")]
        if errors or any(s.get("status") == "critical" and s.get("required") for s in required):
            return "critical"
        if any(s.get("status") == "empty" and s.get("required") for s in required):
            return "empty"
        if active_jobs or any(s.get("status") == "updating" for s in segments):
            return "updating"
        if warnings or any(s.get("status") == "degraded" for s in segments):
            return "degraded"
        if required and all(s.get("status") == "healthy" for s in required):
            return "healthy"
        return "unknown"

    @staticmethod
    def _settings_overall_title(status: str) -> str:
        labels = {
            "healthy": "Local data environment healthy",
            "degraded": "Local data environment degraded",
            "critical": "Local data environment needs attention",
            "updating": "Data update in progress",
            "empty": "Local database is empty",
            "unavailable": "Health unavailable",
            "unknown": "Health evidence incomplete",
        }
        return labels.get(status, "Health evidence incomplete")

    @staticmethod
    def _settings_overall_message(status: str, segments: list[dict[str, Any]], active_jobs: list[dict[str, Any]]) -> str:
        if status == "updating":
            return f"{len(active_jobs)} active job(s) reported. Read-only diagnostics remain available while data changes."
        attention = [s for s in segments if s.get("status") in {"critical", "degraded", "empty"}]
        if attention:
            first = attention[0]
            return f"{first.get('name')} is {first.get('status')}: {first.get('reason')}"
        if status == "healthy":
            return "Required CVM registry and financial statement checks passed. Optional segments may still have deferred details."
        if status == "empty":
            return "Required CVM local data is not populated yet. Start with Database Updates."
        return "Some optional segment evidence is unavailable or deferred."

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

    def _get_software_update_status(self, *, force: bool = False) -> dict:
        with self._update_lock:
            cached_status = dict(self._latest_update_status or {})
            cached_info = dict(self._update_info or {})
            progress = dict(self._update_progress)
        if cached_status and not force:
            return self._sanitize_for_json({
                **cached_status,
                "progress": progress,
                "apply_supported": True,
            })
        try:
            from desktop.__version__ import __version__  # noqa: PLC0415
            from desktop.updater import UpdateChecker  # noqa: PLC0415

            checker = UpdateChecker()
            status = checker.get_latest_release_status(__version__)
            if status.get("update_available") and status.get("zip_url"):
                update_info = {
                    "version": status.get("latest_version"),
                    "tag": status.get("latest_tag"),
                    "zip_url": status.get("zip_url"),
                    "sha256_url": status.get("sha256_url"),
                }
                with self._update_lock:
                    self._update_info = update_info
            elif status.get("status") == "check_failed" and cached_info:
                status = {
                    **status,
                    "status": "available_cached",
                    "latest_version": cached_info.get("version"),
                    "latest_tag": cached_info.get("tag"),
                    "zip_url": cached_info.get("zip_url"),
                    "sha256_url": cached_info.get("sha256_url"),
                    "update_available": True,
                    "error": status.get("error"),
                }
            with self._update_lock:
                self._latest_update_status = dict(status)
                progress = dict(self._update_progress)
            return self._sanitize_for_json({
                **status,
                "progress": progress,
                "apply_supported": True,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "current_version": None,
                "latest_version": None,
                "latest_tag": None,
                "update_available": False,
                "release_url": None,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "check_failed",
                "error": f"Could not check GitHub Releases: {exc}",
                "progress": progress,
                "apply_supported": True,
            })

    @staticmethod
    def _runtime_diagnostics_summary(paths: Any) -> dict:
        warnings: list[str] = []
        errors: list[str] = []
        # Warn when dev mode is running against the real release data directory.
        if not getattr(sys, "frozen", False):
            use_release = os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {
                "1", "true", "yes",
            }
            if use_release:
                warnings.append(
                    "Dev mode is using the release data directory "
                    f"({paths.data_dir}). Destructive actions affect real user data."
                )
        try:
            from desktop.__version__ import __version__ as app_version  # noqa: PLC0415
        except Exception:
            app_version = "unknown"
        dotnet_status = "unavailable"
        webview2_version = None
        try:
            from desktop import app as desktop_app  # noqa: PLC0415

            release = desktop_app._detect_net_framework_release()
            min_release = desktop_app._NET_FRAMEWORK_48_RELEASE_KEY
            if release is None:
                dotnet_status = "not_detected"
                warnings.append(".NET Framework 4.8 registry key was not detected.")
            elif int(release) < int(min_release):
                dotnet_status = f"pre_4_8:{release}"
                warnings.append(f".NET Framework release {release} is below {min_release}.")
            else:
                dotnet_status = f"ok:{release}"
            webview2_version = desktop_app._detect_webview2_runtime()
            if not webview2_version:
                warnings.append("Microsoft Edge WebView2 Runtime was not detected.")
        except Exception as exc:
            warnings.append(f"Runtime prerequisite probe failed: {exc}")

        pythonnet_status = "unknown"
        try:
            import clr  # noqa: F401, PLC0415

            pythonnet_status = "ok"
        except Exception as exc:
            pythonnet_status = f"error:{type(exc).__name__}"
            errors.append(f"pythonnet import failed: {exc}")

        sqlite_status = "unknown"
        try:
            import sqlite3  # noqa: PLC0415

            db_path = Path(paths.db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(db_path)) as conn:
                row = conn.execute("SELECT sqlite_version()").fetchone()
            sqlite_status = f"ok:{row[0] if row else 'unknown'}"
        except Exception as exc:
            sqlite_status = f"error:{type(exc).__name__}"
            errors.append(f"SQLite probe failed: {exc}")

        return {
            "ok": len(errors) == 0,
            "version": app_version,
            "dotnet_status": dotnet_status,
            "webview2_version": webview2_version,
            "pythonnet_status": pythonnet_status,
            "sqlite_status": sqlite_status,
            "db_path": str(paths.db_path),
            "data_root": str(paths.data_dir),
            "errors": errors,
            "warnings": warnings,
        }

    def _collect_recent_diagnostics(self, paths: Any, database: dict | None) -> list[dict]:
        entries: list[dict] = []

        latest_error = (database or {}).get("latest_error") if isinstance(database, dict) else None
        if latest_error:
            entries.append({
                "source": "company_refresh_status",
                "severity": "error",
                "timestamp": (database or {}).get("latest_attempt_at"),
                "message": str(latest_error),
            })

        recovery_log = Path(paths.data_dir) / "recovery.log"
        for line in self._tail_text_lines(recovery_log, limit=4):
            entries.append({
                "source": "recovery.log",
                "severity": "warning" if "failed" in line.lower() else "info",
                "timestamp": self._parse_bracket_timestamp(line),
                "message": self._trim_log_line(line),
            })

        update_log = Path(os.environ.get("LOCALAPPDATA") or Path(paths.data_dir)) / "CVMAnalytics" / "update_error.log"
        for line in self._tail_text_lines(update_log, limit=4):
            entries.append({
                "source": "update_error.log",
                "severity": "error" if "error" in line.lower() else "info",
                "timestamp": self._parse_bracket_timestamp(line),
                "message": self._trim_log_line(line),
            })

        refresh_log = Path(paths.logs_dir) / "refresh_runs.jsonl"
        for line in self._tail_text_lines(refresh_log, limit=6):
            entry = self._refresh_log_entry(line)
            if entry:
                entries.append(entry)

        entries.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        return entries[:12]

    @staticmethod
    def _tail_text_lines(path: Path, *, limit: int) -> list[str]:
        try:
            if not path.exists() or not path.is_file():
                return []
            size = path.stat().st_size
            with path.open("rb") as fh:
                fh.seek(max(0, size - 65536))
                data = fh.read().decode("utf-8", errors="replace")
            return [line for line in data.splitlines() if line.strip()][-limit:]
        except Exception:
            return []

    @staticmethod
    def _parse_bracket_timestamp(line: str) -> str | None:
        if not line.startswith("[") or "]" not in line:
            return None
        return line[1:line.find("]")]

    @staticmethod
    def _trim_log_line(line: str, *, max_len: int = 320) -> str:
        text = " ".join(str(line).split())
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "..."

    def _refresh_log_entry(self, line: str) -> dict | None:
        try:
            payload = json.loads(line)
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return None
        status = str(payload.get("status") or payload.get("state") or "refresh")
        message = (
            payload.get("message")
            or payload.get("error")
            or payload.get("latest_error")
            or f"Refresh result: {status}"
        )
        timestamp = (
            payload.get("finished_at")
            or payload.get("completed_at")
            or payload.get("started_at")
            or payload.get("accepted_at")
        )
        lower = f"{status} {message}".lower()
        severity = "error" if "error" in lower or "failed" in lower else "info"
        return {
            "source": "refresh_runs.jsonl",
            "severity": severity,
            "timestamp": timestamp,
            "message": self._trim_log_line(str(message)),
        }

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

    def get_database_diagnostics(self, params=None) -> dict:
        """Real local SQLite database diagnostics for the Update Base UI.

        Returns explicit row counts for the tables an operator needs to see
        when verifying that a refresh actually populated the runtime DB.
        Distinct from `get_base_health`, which compares against the CVM
        active universe (not local row counts).
        """
        import sqlite3  # noqa: PLC0415

        try:
            p = params or {}
            svc = self._svc()
            db_path = svc.settings.paths.db_path
            data_dir = svc.settings.paths.data_dir
            db_path_str = str(db_path)
            data_root_str = str(data_dir)
            db_exists = db_path.exists()
            db_size_bytes = int(db_path.stat().st_size) if db_exists else 0
            summary_only = self._truthy(p.get("summary_only", False))

            counts: dict[str, int | None] = {
                "companies": None,
                "financial_reports": None,
                "refresh_jobs": None,
                "company_refresh_status": None,
                "qa_logs": None,
            }
            has_statements = False
            latest_success_at: str | None = None
            latest_attempt_at: str | None = None
            latest_error: str | None = None
            latest_report_year: int | None = None
            latest_period_label: str | None = None
            refresh_errors_count: int | None = None

            if db_exists:
                try:
                    with sqlite3.connect(db_path_str) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        present = {row[0] for row in cur.fetchall()}
                        if "financial_reports" in present:
                            cur.execute('SELECT EXISTS(SELECT 1 FROM "financial_reports")')
                            has_statements = cur.fetchone()[0] == 1
                        if not summary_only:
                            for table in counts.keys():
                                if table not in present:
                                    counts[table] = 0
                                    continue
                                try:
                                    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                                    counts[table] = int(cur.fetchone()[0] or 0)
                                except Exception:
                                    counts[table] = None
                        if "financial_reports" in present and not summary_only:
                            try:
                                cur.execute(
                                    'SELECT "REPORT_YEAR", "PERIOD_LABEL" '
                                    'FROM "financial_reports" '
                                    'WHERE "REPORT_YEAR" IS NOT NULL '
                                    'ORDER BY "REPORT_YEAR" DESC, "PERIOD_LABEL" DESC '
                                    "LIMIT 1"
                                )
                                row = cur.fetchone()
                                if row:
                                    latest_report_year = int(row[0]) if row[0] is not None else None
                                    latest_period_label = str(row[1]) if row[1] else None
                            except Exception:
                                pass
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
                            try:
                                cur.execute(
                                    "SELECT COUNT(*) FROM \"company_refresh_status\" "
                                    "WHERE last_error IS NOT NULL AND last_error <> ''"
                                )
                                row = cur.fetchone()
                                refresh_errors_count = int(row[0] or 0) if row else 0
                            except Exception:
                                pass
                except Exception as exc:
                    return self._sanitize_for_json({
                        "db_path": db_path_str,
                        "data_root": data_root_str,
                        "db_exists": db_exists,
                        "db_size_bytes": db_size_bytes,
                        "is_empty": True,
                        "row_counts": counts,
                        "latest_success_at": None,
                        "latest_attempt_at": None,
                        "latest_error": None,
                        "latest_report_year": None,
                        "latest_period_label": None,
                        "refresh_errors_count": None,
                        "error": f"sqlite_open_failed: {exc}",
                    })

            if summary_only:
                is_empty = not db_exists or not has_statements
            else:
                is_empty = (
                    not db_exists
                    or (counts.get("companies") or 0) == 0
                    or (counts.get("financial_reports") or 0) == 0
                )

            return self._sanitize_for_json({
                "db_path": db_path_str,
                "data_root": data_root_str,
                "db_exists": db_exists,
                "db_size_bytes": db_size_bytes,
                "is_empty": is_empty,
                "row_counts": counts,
                "latest_success_at": latest_success_at,
                "latest_attempt_at": latest_attempt_at,
                "latest_error": latest_error,
                "latest_report_year": latest_report_year,
                "latest_period_label": latest_period_label,
                "refresh_errors_count": refresh_errors_count,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "db_path": None,
                "data_root": None,
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
                "latest_report_year": None,
                "latest_period_label": None,
                "refresh_errors_count": None,
                "error": str(exc),
            })
