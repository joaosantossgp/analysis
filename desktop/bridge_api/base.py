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
from typing import Any, Callable

logger = logging.getLogger("desktop.bridge")


class BaseBridgeMixin:
    BASE_HEALTH_CACHE_SCHEMA_VERSION = 1
    DATA_COVERAGE_CACHE_SCHEMA_VERSION = 1
    DATA_UPDATE_PRESETS = {"top_100", "top_200", "top_500", "all"}
    DATA_UPDATE_BATCH_SIZES = {50, 100, 200, 500}
    DATA_UPDATE_SETTING_KEYS = {
            "data_update_universe_preset",
            "data_update_batch_size",
            "data_update_retry_failed",
            "data_update_recompute_coverage",
            "data_update_start_year",
            "data_update_end_year",
        }
    CVM_MIN_YEAR = 2010
    KPI_CATALOG_CACHE_SCHEMA_VERSION = 1
    COUNTRY_KPI_SERIES_CACHE_SCHEMA_VERSION = 1
    SIN_DASHBOARD_CACHE_SCHEMA_VERSION = 2

    def __init__(self) -> None:
        self._service = None
        self._refresh_manager = None
        self._onboarding_service = None
        self._storage_inventory_manager = None
        self._company_info_cache: dict[int, dict[str, Any]] = {}
        self._company_info_pending: set[int] = set()
        self._company_info_lock = threading.RLock()
        self._read_payload_cache_lock = threading.RLock()
        self._data_coverage_cache: tuple[Any, dict[str, Any]] | None = None
        self._kpi_catalog_cache: tuple[Any, dict[str, Any]] | None = None
        self._country_kpi_series_cache: tuple[Any, dict[str, Any]] | None = None
        self._sin_dashboard_cache: tuple[Any, dict[str, Any]] | None = None
        # auto-updater state
        self._update_info: dict | None = None
        self._latest_update_status: dict | None = None
        self._update_progress: dict = {"status": "idle", "percent": 0, "error": None}
        self._update_lock = threading.Lock()
        self._excel_mapping_window_opener: Callable[[int], dict[str, object]] | None = None

    def set_excel_mapping_window_opener(
        self,
        opener: Callable[[int], dict[str, object]],
    ) -> None:
        self._excel_mapping_window_opener = opener

    def open_company_excel_mapping_window(self, params: dict | None = None) -> dict[str, object]:
        try:
            cd_cvm = int((params or {}).get("cd_cvm") or 0)
        except (TypeError, ValueError):
            cd_cvm = 0
        if cd_cvm <= 0:
            return {"ok": False, "error": "A valid CVM code is required."}
        if self._excel_mapping_window_opener is None:
            return {"ok": False, "error": "Excel Mapping windows are unavailable."}
        return self._excel_mapping_window_opener(cd_cvm)

    def _svc(self):
        if self._service is None:
            from src.financials.read_service import CVMReadService  # noqa: PLC0415
            self._service = CVMReadService()
        return self._service

    def _refresh(self):
        if self._refresh_manager is None:
            from desktop.services import DesktopRefreshJobManager  # noqa: PLC0415

            self._refresh_manager = DesktopRefreshJobManager(read_service=self._svc())
        return self._refresh_manager

    def _onboarding(self):
        if self._onboarding_service is None:
            from src.companies.universe import CompanyUniverseService  # noqa: PLC0415

            svc = self._svc()
            self._onboarding_service = CompanyUniverseService(
                settings=svc.settings,
                read_service=svc,
            )
        return self._onboarding_service

    def _storage_inventory(self):
        if self._storage_inventory_manager is None:
            from desktop.storage_inventory import StorageInventoryManager  # noqa: PLC0415

            self._storage_inventory_manager = StorageInventoryManager(self._svc().settings)
        return self._storage_inventory_manager

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
            return {key: BaseBridgeMixin._sanitize_for_json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [BaseBridgeMixin._sanitize_for_json(item) for item in value]
        if isinstance(value, tuple):
            return [BaseBridgeMixin._sanitize_for_json(item) for item in value]
        return value

    @staticmethod
    def _path_signature(path: Path) -> dict[str, Any]:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return {"path": str(path), "exists": False}
        except Exception:
            return {"path": str(path), "exists": None}
        return {
            "path": str(path),
            "exists": True,
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }

    @classmethod
    def _sqlite_signature(cls, db_path: Path) -> list[dict[str, Any]]:
        return [
            cls._path_signature(db_path),
            cls._path_signature(Path(f"{db_path}-wal")),
        ]

    @staticmethod
    def _table_fingerprint(
        cur: sqlite3.Cursor,
        table_name: str,
        *,
        max_columns: tuple[str, ...] = (),
        include_count: bool = False,
    ) -> dict[str, Any]:
        exists = cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if not exists:
            return {"exists": False}

        fingerprint: dict[str, Any] = {"exists": True}
        if include_count:
            safe_table = str(table_name).replace('"', '""')
            fingerprint["row_count"] = cur.execute(
                f'SELECT COUNT(*) FROM "{safe_table}"'
            ).fetchone()[0]
        safe_table = str(table_name).replace('"', '""')
        fingerprint["max_rowid"] = cur.execute(
            f'SELECT MAX(rowid) FROM "{safe_table}"'
        ).fetchone()[0]
        for column in max_columns:
            safe_column = str(column).replace('"', '""')
            fingerprint[str(column)] = cur.execute(
                f'SELECT MAX("{safe_column}") FROM "{safe_table}"'
            ).fetchone()[0]
        return fingerprint

    def _cvm_data_cache_signature(self, db_path: Path) -> dict[str, Any]:
        if not db_path.exists():
            return {"database": str(db_path), "exists": False}
        try:
            with sqlite3.connect(str(db_path)) as conn:
                cur = conn.cursor()
                return {
                    "database": str(db_path.resolve()),
                    "exists": True,
                    "financial_reports": self._table_fingerprint(
                        cur,
                        "financial_reports",
                        max_columns=("REPORT_YEAR",),
                    ),
                    "companies": self._table_fingerprint(
                        cur,
                        "companies",
                        include_count=True,
                    ),
                    "company_refresh_status": self._table_fingerprint(
                        cur,
                        "company_refresh_status",
                        max_columns=("updated_at", "last_success_at", "last_attempt_at"),
                        include_count=True,
                    ),
                }
        except Exception:
            return {"database": str(db_path), "exists": None}

    @staticmethod
    def _read_payload_cache(
        cache_path: Path,
        *,
        schema_version: int,
        signature: Any,
    ) -> dict[str, Any] | None:
        try:
            with cache_path.open("r", encoding="utf-8") as fh:
                cached = json.load(fh)
        except Exception:
            return None
        if not isinstance(cached, dict):
            return None
        if cached.get("schema_version") != schema_version:
            return None
        if cached.get("signature") != signature:
            return None
        payload = cached.get("payload")
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _write_payload_cache(
        cache_path: Path,
        *,
        schema_version: int,
        signature: Any,
        payload: dict[str, Any],
    ) -> None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
            with temp_path.open("w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "schema_version": schema_version,
                        "signature": signature,
                        "payload": payload,
                    },
                    fh,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            temp_path.replace(cache_path)
        except Exception:
            logger.debug("failed to write bridge payload cache %s", cache_path, exc_info=True)

    def _clear_data_coverage_cache(self) -> None:
        with self._read_payload_cache_lock:
            self._data_coverage_cache = None

    def _clear_sin_dashboard_cache(self) -> None:
        with self._read_payload_cache_lock:
            self._sin_dashboard_cache = None

    def _clear_energy_indicator_caches(self) -> None:
        with self._read_payload_cache_lock:
            self._kpi_catalog_cache = None
            self._country_kpi_series_cache = None
            self._sin_dashboard_cache = None

    def _data_coverage_cache_signature_from_settings(self, settings: Any) -> list[Any]:
        today = datetime.now().date()
        return [
            "data_coverage",
            self.DATA_COVERAGE_CACHE_SCHEMA_VERSION,
            int(today.year),
            self._cvm_data_cache_signature(Path(settings.paths.db_path)),
            self._path_signature(Path(settings.paths.active_universe_cache_path)),
        ]

    def _data_coverage_cache_signature(self, svc: Any) -> list[Any]:
        return self._data_coverage_cache_signature_from_settings(svc.settings)

    def _base_health_cache_signature(
        self,
        settings: Any,
        *,
        start_year: int,
        end_year: int,
    ) -> list[Any]:
        return [
            "base_health",
            self.BASE_HEALTH_CACHE_SCHEMA_VERSION,
            int(start_year),
            int(end_year),
            self._cvm_data_cache_signature(Path(settings.paths.db_path)),
            self._path_signature(Path(settings.paths.active_universe_cache_path)),
        ]

    @staticmethod
    def _coerce_health_priorities(rows: Any) -> list[dict[str, Any]]:
        priorities: list[dict[str, Any]] = []
        for raw_row in rows or []:
            if not isinstance(raw_row, dict):
                continue
            row = dict(raw_row)
            row["cd_cvm"] = int(row.get("cd_cvm") or 0)
            row["company_name"] = str(row.get("company_name") or "")
            row["priority_score"] = int(row.get("priority_score") or 0)
            row["missing_years_count"] = int(row.get("missing_years_count") or 0)
            row["gap_to_leader_years"] = int(row.get("gap_to_leader_years") or 0)
            row["years_missing"] = [int(year) for year in row.get("years_missing") or []]
            row["recommended_action"] = str(row.get("recommended_action") or "")
            row["reason"] = str(row.get("reason") or "")
            priorities.append(row)
        return priorities

    def _base_health_snapshot_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        global_stats = payload.get("global") if isinstance(payload.get("global"), dict) else {}
        throughput = payload.get("throughput") if isinstance(payload.get("throughput"), dict) else {}
        company_inventory = (
            payload.get("company_inventory")
            if isinstance(payload.get("company_inventory"), dict)
            else {}
        )
        total_companies = int(
            company_inventory.get("total_companies")
            or global_stats.get("active_universe")
            or 0
        )
        companies_with_historical_data = int(
            company_inventory.get("companies_with_historical_data")
            or global_stats.get("companies_with_historical_data")
            or 0
        )
        return {
            "generated_at": payload.get("generated_at"),
            "start_year": int(payload.get("start_year") or 0),
            "end_year": int(payload.get("end_year") or 0),
            "total_cells": int(global_stats.get("total_cells") or 0),
            "completed_cells": int(global_stats.get("completed_cells") or 0),
            "missing_cells": int(global_stats.get("missing_cells") or 0),
            "pct": float(global_stats.get("pct") or 0.0),
            "health_score": float(payload.get("health_score") or 0.0),
            "health_status": str(payload.get("health_status") or ""),
            "eta_hours": (
                float(global_stats.get("eta_hours"))
                if global_stats.get("eta_hours") is not None
                else None
            ),
            "throughput_per_hour": (
                float(throughput.get("per_hour"))
                if throughput.get("per_hour") is not None
                else None
            ),
            "throughput_confidence": str(throughput.get("confidence") or "low"),
            "per_year": list(payload.get("per_year") or []),
            "prioritized_companies": self._coerce_health_priorities(
                payload.get("prioritized_companies")
            ),
            "raw": dict(payload),
            "total_companies": total_companies,
            "companies_with_historical_data": companies_with_historical_data,
            "companies_without_historical_data": max(
                0,
                total_companies - companies_with_historical_data,
            ),
            "companies_with_any_local_financial_report": int(
                company_inventory.get("companies_with_any_local_financial_report") or 0
            ),
            "companies_partial_local": int(company_inventory.get("companies_partial_local") or 0),
            "companies_fully_updated": int(company_inventory.get("companies_fully_updated") or 0),
            "companies_with_refresh_status_recorded": int(
                company_inventory.get("companies_with_refresh_status_recorded") or 0
            ),
            "companies_with_last_refresh_error": int(
                company_inventory.get("companies_with_last_refresh_error") or 0
            ),
        }

    def _get_cached_base_health_snapshot(
        self,
        *,
        start_year: int,
        end_year: int,
    ) -> dict[str, Any] | None:
        from src.platform.settings import get_settings  # noqa: PLC0415

        settings = get_settings()
        cache_path = settings.paths.cache_dir / (
            f"base_health_db_snapshot_v{self.BASE_HEALTH_CACHE_SCHEMA_VERSION}.json"
        )
        signature = self._base_health_cache_signature(
            settings,
            start_year=start_year,
            end_year=end_year,
        )
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(cached, dict):
            return None
        if cached.get("schema_version") != self.BASE_HEALTH_CACHE_SCHEMA_VERSION:
            return None
        if cached.get("signature") != signature:
            return None
        raw_payload = cached.get("data")
        if not isinstance(raw_payload, dict):
            return None
        return self._base_health_snapshot_from_payload(raw_payload)

    def _sin_dashboard_cache_signature(self, settings: Any) -> list[Any]:
        return [
            "sin_dashboard",
            self.SIN_DASHBOARD_CACHE_SCHEMA_VERSION,
            datetime.now(timezone.utc).date().isoformat(),
            self._sqlite_signature(Path(settings.paths.energy_kpi_db_path)),
        ]

    @staticmethod
    def _normalized_cache_list(values: Any) -> list[Any]:
        if not values:
            return []
        if isinstance(values, (list, tuple, set)):
            return sorted(str(value) for value in values)
        return [str(values)]

    def _kpi_catalog_cache_signature(self, settings: Any, params: dict[str, Any]) -> list[Any]:
        return [
            "kpi_catalog",
            self.KPI_CATALOG_CACHE_SCHEMA_VERSION,
            {
                "sector": params.get("sector") or None,
                "v1_status": params.get("v1_status") or None,
                "dashboard_priority": params.get("dashboard_priority") or None,
                "excel_export_priority": params.get("excel_export_priority") or None,
                "macro_category": params.get("macro_category") or None,
                "source_verification_status": params.get("source_verification_status") or None,
            },
            self._sqlite_signature(Path(settings.paths.energy_kpi_db_path)),
        ]

    def _country_kpi_series_cache_signature(self, settings: Any, params: dict[str, Any]) -> list[Any]:
        return [
            "country_kpi_series",
            self.COUNTRY_KPI_SERIES_CACHE_SCHEMA_VERSION,
            {
                "kpi_ids": self._normalized_cache_list(params.get("kpi_ids")),
                "iso_codes": self._normalized_cache_list(params.get("iso_codes")),
                "years": self._normalized_cache_list(params.get("years")),
            },
            self._sqlite_signature(Path(settings.paths.energy_kpi_db_path)),
        ]

    def _append_runtime_log(self, message: str) -> None:
        """Append bridge diagnostics to the packaged runtime log surface."""
        try:
            raw_data_dir = os.environ.get("CVM_DATA_DIR")
            data_dir = (
                Path(raw_data_dir)
                if raw_data_dir
                else Path(self._svc().settings.paths.data_dir)
            )
            data_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with (data_dir / "recovery.log").open("a", encoding="utf-8") as fh:
                fh.write(f"[{stamp}] {message}\n")
        except Exception:
            logger.debug("failed to append runtime log", exc_info=True)

    def ping(self, params=None) -> dict:
        return self._sanitize_for_json({"pong": True, "ts": time.time()})
