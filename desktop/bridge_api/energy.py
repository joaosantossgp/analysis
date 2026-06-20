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


class EnergyBridgeMixin:
    def _energy_svc(self):
        if not hasattr(self, "_energy_read_service") or self._energy_read_service is None:
            from src.energy_kpi.read import EnergyKPIReadService  # noqa: PLC0415
            from src.platform.settings import get_settings  # noqa: PLC0415
            self._energy_read_service = EnergyKPIReadService(get_settings())
        return self._energy_read_service

    def _energy_refresh_status(self) -> dict:
        return getattr(self, "_energy_refresh_state", {"status": "idle", "error": None})

    def _sin_refresh_status(self) -> dict:
        return getattr(self, "_sin_refresh_state", {"status": "idle", "error": None})

    def _plant_parcel_refresh_status(self) -> dict:
        return getattr(self, "_plant_parcel_refresh_state", {"status": "idle", "error": None})

    @staticmethod
    def _is_sqlite_locked_error(exc: Exception) -> bool:
        return "database is locked" in str(exc).lower()

    def _retry_energy_read(self, fn, *, attempts: int = 4):
        last_exc: Exception | None = None
        for attempt in range(max(1, attempts)):
            try:
                return fn()
            except Exception as exc:
                if not self._is_sqlite_locked_error(exc):
                    raise
                last_exc = exc
                self._energy_read_service = None
                if attempt >= attempts - 1:
                    break
                from desktop import bridge as bridge_module  # noqa: PLC0415

                bridge_module.time.sleep(0.2 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("energy KPI read failed")

    def get_kpi_catalog(self, params=None) -> dict:
        params = params or {}
        try:
            from src.platform.settings import get_settings  # noqa: PLC0415

            settings = get_settings()
            cache_signature = self._kpi_catalog_cache_signature(settings, params)
            cache_path = (
                Path(settings.paths.cache_dir)
                / f"energy_kpi_catalog_v{self.KPI_CATALOG_CACHE_SCHEMA_VERSION}.json"
            )
            with self._read_payload_cache_lock:
                if (
                    self._kpi_catalog_cache is not None
                    and self._kpi_catalog_cache[0] == cache_signature
                ):
                    return self._sanitize_for_json(self._kpi_catalog_cache[1])
            cached_payload = self._read_payload_cache(
                cache_path,
                schema_version=self.KPI_CATALOG_CACHE_SCHEMA_VERSION,
                signature=cache_signature,
            )
            if cached_payload is not None:
                with self._read_payload_cache_lock:
                    self._kpi_catalog_cache = (cache_signature, cached_payload)
                return self._sanitize_for_json(cached_payload)

            entries = self._retry_energy_read(
                lambda: self._energy_svc().get_kpi_catalog(
                    sector=params.get("sector"),
                    v1_status=params.get("v1_status"),
                    dashboard_priority=params.get("dashboard_priority"),
                    excel_export_priority=params.get("excel_export_priority"),
                    macro_category=params.get("macro_category"),
                    source_verification_status=params.get("source_verification_status"),
                )
            )
            payload = self._sanitize_for_json({
                "entries": [e.to_dict() for e in entries],
                "count": len(entries),
            })
            with self._read_payload_cache_lock:
                self._kpi_catalog_cache = (cache_signature, payload)
            self._write_payload_cache(
                cache_path,
                schema_version=self.KPI_CATALOG_CACHE_SCHEMA_VERSION,
                signature=cache_signature,
                payload=payload,
            )
            return payload
        except Exception as exc:
            return {"error": str(exc), "entries": [], "count": 0}

    def get_country_kpi_series(self, params=None) -> dict:
        params = params or {}
        try:
            from src.platform.settings import get_settings  # noqa: PLC0415

            settings = get_settings()
            cache_signature = self._country_kpi_series_cache_signature(settings, params)
            cache_path = (
                Path(settings.paths.cache_dir)
                / f"country_kpi_series_v{self.COUNTRY_KPI_SERIES_CACHE_SCHEMA_VERSION}.json"
            )
            with self._read_payload_cache_lock:
                if (
                    self._country_kpi_series_cache is not None
                    and self._country_kpi_series_cache[0] == cache_signature
                ):
                    return self._sanitize_for_json(self._country_kpi_series_cache[1])
            cached_payload = self._read_payload_cache(
                cache_path,
                schema_version=self.COUNTRY_KPI_SERIES_CACHE_SCHEMA_VERSION,
                signature=cache_signature,
            )
            if cached_payload is not None:
                with self._read_payload_cache_lock:
                    self._country_kpi_series_cache = (cache_signature, cached_payload)
                return self._sanitize_for_json(cached_payload)

            values = self._retry_energy_read(
                lambda: self._energy_svc().get_country_kpi_series(
                    kpi_ids=params.get("kpi_ids"),
                    iso_codes=params.get("iso_codes"),
                    years=params.get("years"),
                )
            )
            payload = self._sanitize_for_json({
                "values": [v.to_dict() for v in values],
                "count": len(values),
            })
            with self._read_payload_cache_lock:
                self._country_kpi_series_cache = (cache_signature, payload)
            self._write_payload_cache(
                cache_path,
                schema_version=self.COUNTRY_KPI_SERIES_CACHE_SCHEMA_VERSION,
                signature=cache_signature,
                payload=payload,
            )
            return payload
        except Exception as exc:
            return {"error": str(exc), "values": [], "count": 0}

    def get_country_kpi_compare(self, params=None) -> dict:
        params = params or {}
        try:
            kpi_id = params.get("kpi_id", "")
            year = int(params.get("year", 0))
            values = self._retry_energy_read(
                lambda: self._energy_svc().get_country_kpi_compare(kpi_id=kpi_id, year=year)
            )
            return self._sanitize_for_json({
                "kpi_id": kpi_id,
                "year": year,
                "values": [v.to_dict() for v in values],
            })
        except Exception as exc:
            return {"error": str(exc), "values": []}

    def get_energy_kpi_health(self, params=None) -> dict:
        try:
            health = self._retry_energy_read(lambda: self._energy_svc().get_energy_kpi_health())
            result = self._sanitize_for_json(health.to_dict())
            result["refresh_running"] = self._energy_refresh_status().get("status") == "running"
            result["refresh_error"] = self._energy_refresh_status().get("error")
            return result
        except Exception as exc:
            return {"error": str(exc), "refresh_running": False, "refresh_error": None}

    def refresh_energy_kpis(self, params=None) -> dict:
        params = params or {}
        state = self._energy_refresh_status()
        if state.get("status") == "running":
            return {"status": "already_running", "error": None}

        self._energy_refresh_state = {"status": "running", "error": None}

        def _run():
            try:
                from src.energy_kpi.refresh import EnergyKPIRefreshJob  # noqa: PLC0415
                from src.platform.settings import get_settings  # noqa: PLC0415
                job = EnergyKPIRefreshJob(get_settings())
                result = job.run(triggered_by=params.get("triggered_by", "user"))
                self._energy_refresh_state = {
                    "status": result.get("status", "success"),
                    "error": result.get("error"),
                    "rows_ingested": result.get("rows_ingested", 0),
                }
            except Exception as exc:
                self._energy_refresh_state = {"status": "error", "error": str(exc)}
            finally:
                # Invalidate read service so next read sees fresh data
                self._energy_read_service = None
                self._clear_energy_indicator_caches()

        threading.Thread(target=_run, name="energy-kpi-refresh", daemon=True).start()
        return {"status": "started", "error": None}

    def export_country_kpis_excel(self, params=None) -> dict:
        params = params or {}
        try:
            from src.energy_kpi.excel import export_country_kpis  # noqa: PLC0415
            from src.platform.settings import get_settings  # noqa: PLC0415
            settings = get_settings()
            output_path = export_country_kpis(
                settings=settings,
                iso_codes=params.get("iso_codes"),
                kpi_ids=params.get("kpi_ids"),
            )
            return {"path": str(output_path), "error": None}
        except Exception as exc:
            return {"error": str(exc), "path": None}

    def get_sin_kpi_dashboard(self, params=None) -> dict:
        try:
            from src.platform.settings import get_settings  # noqa: PLC0415

            settings = get_settings()
            cache_signature = self._sin_dashboard_cache_signature(settings)
            cache_path = (
                Path(settings.paths.cache_dir)
                / f"sin_kpi_dashboard_v{self.SIN_DASHBOARD_CACHE_SCHEMA_VERSION}.json"
            )
            with self._read_payload_cache_lock:
                if (
                    self._sin_dashboard_cache is not None
                    and self._sin_dashboard_cache[0] == cache_signature
                ):
                    result = self._sanitize_for_json(self._sin_dashboard_cache[1])
                    result["refresh_running"] = self._sin_refresh_status().get("status") == "running"
                    result["refresh_error"] = self._sin_refresh_status().get("error")
                    return result
            cached_payload = self._read_payload_cache(
                cache_path,
                schema_version=self.SIN_DASHBOARD_CACHE_SCHEMA_VERSION,
                signature=cache_signature,
            )
            if cached_payload is not None:
                with self._read_payload_cache_lock:
                    self._sin_dashboard_cache = (cache_signature, cached_payload)
                result = self._sanitize_for_json(cached_payload)
                result["refresh_running"] = self._sin_refresh_status().get("status") == "running"
                result["refresh_error"] = self._sin_refresh_status().get("error")
                return result

            dashboard = self._retry_energy_read(lambda: self._energy_svc().get_sin_kpi_dashboard())
            payload = self._sanitize_for_json(dashboard.to_dict())
            with self._read_payload_cache_lock:
                self._sin_dashboard_cache = (cache_signature, payload)
            self._write_payload_cache(
                cache_path,
                schema_version=self.SIN_DASHBOARD_CACHE_SCHEMA_VERSION,
                signature=cache_signature,
                payload=payload,
            )
            result = self._sanitize_for_json(payload)
            result["refresh_running"] = self._sin_refresh_status().get("status") == "running"
            result["refresh_error"] = self._sin_refresh_status().get("error")
            return result
        except Exception as exc:
            return {
                "error": str(exc),
                "observations": [],
                "source_statuses": [],
                "refresh_running": False,
                "refresh_error": None,
            }

    def get_sin_kpi_series(self, params=None) -> dict:
        params = params or {}
        try:
            values = self._retry_energy_read(
                lambda: self._energy_svc().get_sin_kpi_series(
                    kpi_ids=params.get("kpi_ids"),
                    subsystem_codes=params.get("subsystem_codes"),
                    start_datetime=params.get("start_datetime"),
                    end_datetime=params.get("end_datetime"),
                    limit=params.get("limit"),
                )
            )
            return self._sanitize_for_json({
                "values": [v.to_dict() for v in values],
                "count": len(values),
            })
        except Exception as exc:
            return {"error": str(exc), "values": [], "count": 0}

    def get_sin_kpi_health(self, params=None) -> dict:
        try:
            health = self._retry_energy_read(lambda: self._energy_svc().get_sin_kpi_health())
            result = self._sanitize_for_json(health.to_dict())
            result["refresh_running"] = self._sin_refresh_status().get("status") == "running"
            result["refresh_error"] = self._sin_refresh_status().get("error")
            return result
        except Exception as exc:
            return {"error": str(exc), "refresh_running": False, "refresh_error": None}

    def refresh_sin_kpis(self, params=None) -> dict:
        params = params or {}
        state = self._sin_refresh_status()
        if state.get("status") == "running":
            return {"status": "already_running", "error": None}

        self._clear_energy_indicator_caches()
        self._sin_refresh_state = {"status": "running", "error": None}

        def _run():
            try:
                from src.energy_kpi.sin_refresh import SINKPIRefreshJob  # noqa: PLC0415
                from src.platform.settings import get_settings  # noqa: PLC0415
                years = params.get("years")
                if years is not None:
                    years = [int(y) for y in years]
                include_ccee = bool(params.get("include_ccee", True))
                job = SINKPIRefreshJob(get_settings())
                result = job.run(
                    triggered_by=params.get("triggered_by", "user"),
                    years=years,
                    include_ccee=include_ccee,
                )
                self._sin_refresh_state = {
                    "status": result.get("status", "success"),
                    "error": result.get("error"),
                    "rows_inserted": result.get("rows_inserted", 0),
                }
            except Exception as exc:
                self._sin_refresh_state = {"status": "error", "error": str(exc)}
            finally:
                self._energy_read_service = None

        threading.Thread(target=_run, name="sin-kpi-refresh", daemon=True).start()
        return {"status": "started", "error": None}

    def get_plant_parcel_source_statuses(self, params=None) -> dict:
        params = params or {}
        try:
            source_ids = params.get("source_ids")
            if source_ids is not None and not isinstance(source_ids, list):
                source_ids = [source_ids]
            result = self._retry_energy_read(
                lambda: self._energy_svc().get_plant_parcel_source_statuses(source_ids=source_ids)
            )
            result = self._sanitize_for_json(result)
            refresh_state = self._plant_parcel_refresh_status()
            result["refresh_running"] = refresh_state.get("status") == "running"
            result["refresh_status"] = refresh_state.get("status")
            result["refresh_error"] = refresh_state.get("error")
            result["refresh_warning"] = refresh_state.get("warning")
            result["refresh_source_id"] = refresh_state.get("source_id")
            result["refresh_mode"] = refresh_state.get("mode")
            result["refresh_id"] = refresh_state.get("refresh_id")
            result["refresh_import_id"] = refresh_state.get("import_id")
            result["refresh_total_files"] = refresh_state.get("total_files")
            result["refresh_current_file_index"] = refresh_state.get("current_file_index")
            result["refresh_current_file_name"] = refresh_state.get("current_file_name")
            result["refresh_rows_inserted"] = refresh_state.get("rows_inserted")
            result["refresh_rows_skipped"] = refresh_state.get("rows_skipped")
            result["refresh_started_at"] = refresh_state.get("started_at")
            result["refresh_updated_at"] = refresh_state.get("updated_at")
            result["refresh_finished_at"] = refresh_state.get("finished_at")
            return result
        except Exception as exc:
            return {
                "error": str(exc),
                "source_statuses": [],
                "count": 0,
                "refresh_running": False,
                "refresh_error": None,
                "refresh_source_id": None,
            }

    def get_energy_mart_status(self, params=None) -> dict:
        try:
            payload = self._retry_energy_read(lambda: self._energy_svc().get_energy_mart_status())
            rebuild_state = getattr(self, "_energy_mart_rebuild_state", {"status": "idle", "error": None})
            payload["rebuild"] = rebuild_state
            payload["write_mode"] = "read-write" if self._is_write_allowed() else "read-only"
            return self._sanitize_for_json(payload)
        except Exception as exc:
            return self._sanitize_for_json({
                "error": str(exc),
                "rebuild": getattr(self, "_energy_mart_rebuild_state", {"status": "idle", "error": None}),
                "write_mode": "read-write" if self._is_write_allowed() else "read-only",
            })

    def start_energy_mart_rebuild(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("start_energy_mart_rebuild"))

        params = params or {}
        state = getattr(self, "_energy_mart_rebuild_state", {"status": "idle", "error": None})
        if state.get("status") == "running":
            return self._sanitize_for_json({
                "status": "already_running",
                "error": None,
                "started_at": state.get("started_at"),
                "reference_months": state.get("reference_months"),
            })

        reference_month = str(params.get("reference_month") or "").strip()
        rebuild_all = bool(params.get("all"))
        if rebuild_all:
            expected = "REBUILD ENERGY MARTS"
            if str(params.get("confirm") or "") != expected:
                return self._sanitize_for_json({
                    "status": "blocked",
                    "error": f"Type {expected} to confirm a full Energy mart rebuild.",
                    "status_reason_code": "confirmation_required",
                    "is_retry_allowed": True,
                })
            reference_months = None
        else:
            if not reference_month:
                return self._sanitize_for_json({
                    "status": "blocked",
                    "error": "Energy mart rebuild requires reference_month unless full rebuild is explicitly confirmed.",
                    "status_reason_code": "reference_month_required",
                    "is_retry_allowed": True,
                })
            reference_months = [reference_month]

        rebuild_daily = bool(params.get("rebuild_daily", True))
        rebuild_preview = bool(params.get("rebuild_preview", False))
        rebuild_source_submarket = bool(params.get("rebuild_source_submarket", True))
        if not rebuild_daily and not rebuild_preview and not rebuild_source_submarket:
            return self._sanitize_for_json({
                "status": "blocked",
                "error": "Select at least one mart to rebuild.",
                "status_reason_code": "empty_rebuild_scope",
                "is_retry_allowed": True,
            })

        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rebuild_id = str(uuid.uuid4())
        self._energy_mart_rebuild_state = {
            "status": "running",
            "error": None,
            "rebuild_id": rebuild_id,
            "started_at": started_at,
            "finished_at": None,
            "reference_months": reference_months,
            "rebuild_daily": rebuild_daily,
            "rebuild_preview": rebuild_preview,
            "rebuild_source_submarket": rebuild_source_submarket,
            "result": None,
        }

        def _run():
            try:
                from src.energy_kpi.plant_marts import rebuild_plant_hourly_marts  # noqa: PLC0415
                from src.energy_kpi.schema import get_energy_kpi_engine  # noqa: PLC0415
                from src.platform.settings import get_settings  # noqa: PLC0415

                engine = get_energy_kpi_engine(get_settings())
                with engine.begin() as conn:
                    result = rebuild_plant_hourly_marts(
                        conn,
                        reference_months=reference_months,
                        rebuild_daily=rebuild_daily,
                        rebuild_preview=rebuild_preview,
                        rebuild_source_submarket=rebuild_source_submarket,
                    )
                self._energy_mart_rebuild_state = {
                    **self._energy_mart_rebuild_state,
                    "status": "success",
                    "error": None,
                    "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "result": result,
                }
            except Exception as exc:
                logger.exception("Energy mart rebuild failed")
                self._energy_mart_rebuild_state = {
                    **self._energy_mart_rebuild_state,
                    "status": "error",
                    "error": str(exc),
                    "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            finally:
                self._energy_read_service = None
                self._clear_energy_indicator_caches()

        threading.Thread(target=_run, name="energy-mart-rebuild", daemon=True).start()
        return self._sanitize_for_json(self._energy_mart_rebuild_state)

    def get_plant_parcel_catalog(self, params=None) -> dict:
        params = params or {}
        try:
            return self._sanitize_for_json(
                self._retry_energy_read(
                    lambda: self._energy_svc().get_plant_parcel_catalog(
                        search=params.get("search"),
                        entity_type=params.get("entity_type"),
                        generation_source=params.get("generation_source"),
                        submarket=params.get("submarket"),
                        uf=params.get("uf"),
                        limit=int(params.get("limit", 100) or 100),
                        offset=int(params.get("offset", 0) or 0),
                    )
                )
            )
        except Exception as exc:
            return {"error": str(exc), "records": [], "count": 0, "total": 0}

    def get_plant_parcel_source_submarket_summary(self, params=None) -> dict:
        params = params or {}
        try:
            return self._sanitize_for_json(
                self._retry_energy_read(
                    lambda: self._energy_svc().get_plant_parcel_source_submarket_summary(
                        reference_month=params.get("reference_month"),
                        generation_source=params.get("generation_source"),
                        submarket=params.get("submarket"),
                        limit=int(params.get("limit", 500) or 500),
                        offset=int(params.get("offset", 0) or 0),
                    )
                )
            )
        except Exception as exc:
            return {
                "error": str(exc),
                "records": [],
                "count": 0,
                "total": 0,
                "data_source": "plant_parcel_source_submarket_monthly_mart",
            }

    def get_plant_parcel_detail(self, params=None) -> dict:
        params = params or {}
        try:
            return self._sanitize_for_json(
                self._retry_energy_read(
                    lambda: self._energy_svc().get_plant_parcel_detail(
                        entity_id=str(params.get("entity_id") or ""),
                        entity_type=params.get("entity_type"),
                    )
                )
            )
        except Exception as exc:
            return {"error": str(exc), "metrics": [], "monthly_series": [], "hourly_preview": []}

    def get_plant_parcel_chart_data(self, params=None) -> dict:
        params = params or {}
        try:
            return self._sanitize_for_json(
                self._retry_energy_read(
                    lambda: self._energy_svc().get_plant_parcel_chart_data(
                        entity_id=str(params.get("entity_id") or ""),
                        entity_type=params.get("entity_type"),
                        frequency=str(params.get("frequency") or "monthly"),
                        year_month=params.get("year_month"),
                        start_datetime=params.get("start_datetime"),
                        end_datetime=params.get("end_datetime"),
                        limit=params.get("limit"),
                    )
                )
            )
        except Exception as exc:
            return {"error": str(exc), "series": [], "periods": []}

    def select_plant_parcel_import_file(self, params=None) -> dict:
        params = params or {}
        source_id = str(params.get("source_id") or "")
        try:
            import webview  # noqa: PLC0415

            file_types = _plant_parcel_import_file_types(source_id)
            if not webview.windows:
                return {"ok": False, "canceled": False, "error": "Desktop window is not ready."}
            try:
                selected = webview.windows[0].create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=True,
                    file_types=file_types,
                )
            except TypeError:
                selected = webview.windows[0].create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=True,
                )
            if not selected:
                return {"ok": False, "canceled": True, "error": None}
            selected_paths = [
                Path(str(item))
                for item in (selected if isinstance(selected, (list, tuple)) else [selected])
            ]
            selected_path = selected_paths[0]
            return self._sanitize_for_json({
                "ok": True,
                "canceled": False,
                "file_path": str(selected_path),
                "file_name": selected_path.name,
                "file_paths": [str(path) for path in selected_paths],
                "file_names": [path.name for path in selected_paths],
            })
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "canceled": False, "error": str(exc)})

    def import_plant_parcel_source_file(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("import_plant_parcel_source_file"))
        params = params or {}
        source_id = str(params.get("source_id") or "")
        if not source_id:
            return {"status": "failed", "error": "source_id is required"}
        state = self._plant_parcel_refresh_status()
        if state.get("status") == "running":
            return {
                "status": "already_running",
                "error": None,
                "source_id": state.get("source_id"),
            }

        try:
            from src.platform.settings import get_settings  # noqa: PLC0415

            settings = get_settings()
            requested_files = params.get("files")
            if not isinstance(requested_files, list) or not requested_files:
                requested_files = [{
                    "file_path": params.get("file_path"),
                    "file_content_base64": params.get("file_content_base64"),
                    "original_file_name": params.get("original_file_name"),
                }]

            temp_paths: list[Path] = []
            import_files: list[dict[str, str | None]] = []
            temp_dir = settings.paths.energy_kpi_raw_dir / "manual_uploads_tmp"
            for raw_file in requested_files:
                if not isinstance(raw_file, dict):
                    continue
                original_file_name = str(raw_file.get("original_file_name") or "")
                file_path_value = raw_file.get("file_path")
                if not file_path_value and raw_file.get("file_content_base64"):
                    safe_name = Path(original_file_name or "manual-import.csv").name
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    temp_path = temp_dir / f"{uuid.uuid4()}-{safe_name}"
                    temp_path.write_bytes(base64.b64decode(str(raw_file.get("file_content_base64"))))
                    temp_paths.append(temp_path)
                    file_path_value = str(temp_path)
                if file_path_value:
                    import_files.append({
                        "file_path": str(file_path_value),
                        "original_file_name": original_file_name or None,
                    })

            if not import_files:
                return {
                    "status": "failed",
                    "error": "At least one file_path or file_content_base64 entry must be provided.",
                    "source_id": source_id,
                }

            import_id = str(uuid.uuid4())
            started_at = datetime.now(timezone.utc).isoformat()
            self._plant_parcel_refresh_state = {
                "status": "running",
                "error": None,
                "warning": None,
                "source_id": source_id,
                "mode": "manual_file",
                "import_id": import_id,
                "total_files": len(import_files),
                "started_at": started_at,
                "updated_at": started_at,
            }

            def _run():
                try:
                    from src.energy_kpi.plant_parcel_refresh import PlantParcelRefreshJob  # noqa: PLC0415

                    rows_inserted = 0
                    rows_skipped = 0
                    failed = 0
                    warnings = 0
                    errors: list[str] = []
                    warning_messages: list[str] = []
                    last_result: dict[str, Any] = {}
                    last_label: str | None = None
                    for index, item in enumerate(import_files, start=1):
                        label = item.get("original_file_name") or Path(str(item.get("file_path"))).name
                        last_label = label
                        self._plant_parcel_refresh_state = {
                            "status": "running",
                            "error": None,
                            "warning": None,
                            "source_id": source_id,
                            "mode": "manual_file",
                            "import_id": import_id,
                            "total_files": len(import_files),
                            "current_file_index": index,
                            "current_file_name": label,
                            "rows_inserted": rows_inserted,
                            "rows_skipped": rows_skipped,
                            "started_at": started_at,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                        result = PlantParcelRefreshJob(settings).run_manual_file_import(
                            source_id=source_id,
                            file_path=Path(str(item.get("file_path"))),
                            triggered_by=str(params.get("triggered_by") or "user"),
                            expected_period=params.get("expected_period"),
                            original_file_name=item.get("original_file_name"),
                        )
                        last_result = result
                        rows_inserted += int(result.get("rows_inserted") or 0)
                        rows_skipped += int(result.get("rows_skipped") or 0)
                        status = str(result.get("status") or "").lower()
                        if status in {"failed", "error"}:
                            failed += 1
                            errors.append(f"{label}: {result.get('error') or 'failed'}")
                        elif status == "warning":
                            warnings += 1
                            warning_messages.append(f"{label}: {result.get('warning') or 'warning'}")

                    if failed >= len(import_files):
                        final_status = "error"
                        error = "; ".join(errors[:2]) or "Manual import failed."
                        warning = None
                    elif failed > 0 or warnings > 0:
                        final_status = "warning"
                        error = None
                        warning_parts = errors[:2] if failed > 0 else warning_messages[:2]
                        warning = "; ".join(warning_parts) or "Manual import completed with warnings."
                    else:
                        final_status = "success"
                        error = None
                        warning = None

                    self._plant_parcel_refresh_state = {
                        "status": final_status,
                        "error": error,
                        "warning": warning,
                        "source_id": source_id,
                        "mode": "manual_file",
                        "import_id": import_id,
                        "total_files": len(import_files),
                        "current_file_index": len(import_files),
                        "current_file_name": last_label,
                        "rows_inserted": rows_inserted,
                        "rows_skipped": rows_skipped,
                        "refresh_id": last_result.get("refresh_id"),
                        "started_at": started_at,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    }
                except Exception as exc:
                    finished_at = datetime.now(timezone.utc).isoformat()
                    self._plant_parcel_refresh_state = {
                        "status": "error",
                        "error": str(exc),
                        "source_id": source_id,
                        "mode": "manual_file",
                        "import_id": import_id,
                        "started_at": started_at,
                        "updated_at": finished_at,
                        "finished_at": finished_at,
                    }
                finally:
                    self._energy_read_service = None
                    for temp_path in temp_paths:
                        try:
                            temp_path.unlink(missing_ok=True)
                        except Exception:
                            logger.debug("failed to remove temporary manual upload", exc_info=True)

            threading.Thread(target=_run, name="plant-parcel-manual-import", daemon=True).start()
            return self._sanitize_for_json({
                "status": "started",
                "error": None,
                "source_id": source_id,
                "import_id": import_id,
                "total_files": len(import_files),
            })
        except Exception as exc:
            self._plant_parcel_refresh_state = {
                "status": "error",
                "error": str(exc),
                "source_id": source_id,
            }
            return self._sanitize_for_json({"status": "failed", "error": str(exc), "source_id": source_id})

    def refresh_plant_parcel_source(self, params=None) -> dict:
        params = params or {}
        source_id = str(params.get("source_id") or "")
        if not source_id:
            return {"status": "error", "error": "source_id is required"}
        state = self._plant_parcel_refresh_status()
        if state.get("status") == "running":
            return {
                "status": "already_running",
                "error": None,
                "source_id": state.get("source_id"),
            }

        started_at = datetime.now(timezone.utc).isoformat()
        self._plant_parcel_refresh_state = {
            "status": "running",
            "error": None,
            "source_id": source_id,
            "mode": "automatic_refresh",
            "started_at": started_at,
            "updated_at": started_at,
        }

        def _run():
            try:
                from src.energy_kpi.plant_parcel_refresh import PlantParcelRefreshJob  # noqa: PLC0415
                from src.platform.settings import get_settings  # noqa: PLC0415
                job = PlantParcelRefreshJob(get_settings())
                result = job.run(
                    source_id=source_id,
                    triggered_by=params.get("triggered_by", "user"),
                    year=int(params["year"]) if params.get("year") else None,
                    year_month=params.get("year_month"),
                    use_daily_aneel=bool(params.get("use_daily_aneel", False)),
                )
                self._plant_parcel_refresh_state = {
                    "status": result.get("status", "success"),
                    "error": result.get("error"),
                    "warning": result.get("warning"),
                    "source_id": source_id,
                    "mode": "automatic_refresh",
                    "rows_inserted": result.get("rows_inserted", 0),
                    "refresh_id": result.get("refresh_id"),
                    "started_at": started_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as exc:
                finished_at = datetime.now(timezone.utc).isoformat()
                self._plant_parcel_refresh_state = {
                    "status": "error",
                    "error": str(exc),
                    "source_id": source_id,
                    "mode": "automatic_refresh",
                    "started_at": started_at,
                    "updated_at": finished_at,
                    "finished_at": finished_at,
                }
            finally:
                self._energy_read_service = None

        threading.Thread(target=_run, name="plant-parcel-refresh", daemon=True).start()
        return {"status": "started", "error": None, "source_id": source_id}


def _plant_parcel_import_file_types(source_id: str) -> tuple[str, ...]:
    if source_id == "ccee_plant_parcel_monthly":
        return ("CSV files (*.csv)", "All files (*.*)")
    if source_id == "ccee_plant_generation_hourly":
        return ("GZIP files (*.gz;*.gzip)", "CSV files (*.csv)", "All files (*.*)")
    return ("All files (*.*)",)


def _serialize(obj: Any) -> Any:
    """Converte dataclasses e tuples para tipos serializáveis por pywebview."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, tuple):
        return list(obj)
    return obj
