"""Settings health summary bridge methods extracted from desktop/bridge_api/status.py."""
from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class StatusSettingsHealthMixin:
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
                # Missing CVM data is fixed by "Download CVM data" on Home.
                "action_route": "/" if companies_status == "empty" else "/settings/data",
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
                "action_route": "/" if reports_status in {"empty", "updating"} else "/settings/data",
                "details": {"coverage_route": "/settings/data"},
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
                    "action_route": "/settings/diagnostics",
                })
            elif int(refresh_worker.get("active_jobs") or 0) > 0 and refresh_worker.get("stale"):
                warnings.append({
                    "segment_id": "runtime",
                    "severity": "warning",
                    "message": "Refresh jobs are queued/running but the worker heartbeat is missing or stale.",
                    "action_route": "/settings/diagnostics",
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
            "action_route": "/settings/sources",
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
            return "The local database is empty. Use Download CVM data on Home."
        return "Some optional segment evidence is unavailable or deferred."
