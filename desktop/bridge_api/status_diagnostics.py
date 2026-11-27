"""Runtime/worker/database diagnostics bridge methods extracted from desktop/bridge_api/status.py."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class StatusDiagnosticsMixin:
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
