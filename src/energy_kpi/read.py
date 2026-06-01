"""EnergyKPIReadService — offline-only reads from energy_kpis.db.

All methods query local SQLite. No network calls on the read path.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from src.contracts import (
    CountryKPIValueDTO,
    EnergyKPIHealthDTO,
    KPICatalogEntryDTO,
)
from src.energy_kpi.schema import get_energy_kpi_engine
from src.settings import AppSettings

logger = logging.getLogger(__name__)

_STALE_THRESHOLD_DAYS = 90


class EnergyKPIReadService:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def _engine(self):
        return get_energy_kpi_engine(self._settings)

    # ── Catalog ───────────────────────────────────────────────────────────────

    def get_kpi_catalog(
        self,
        *,
        sector: str | None = None,
        v1_status: str | None = None,
        dashboard_priority: str | None = None,
        excel_export_priority: str | None = None,
        macro_category: str | None = None,
        source_verification_status: str | None = None,
    ) -> list[KPICatalogEntryDTO]:
        """Return KPI catalog entries filtered by any combination of fields."""
        conditions = []
        params: dict[str, Any] = {}
        if sector:
            conditions.append("sector = :sector")
            params["sector"] = sector
        if v1_status:
            conditions.append("v1_status = :v1_status")
            params["v1_status"] = v1_status
        if dashboard_priority:
            conditions.append("dashboard_priority = :dashboard_priority")
            params["dashboard_priority"] = dashboard_priority
        if excel_export_priority:
            conditions.append("excel_export_priority = :excel_export_priority")
            params["excel_export_priority"] = excel_export_priority
        if macro_category:
            conditions.append("macro_category = :macro_category")
            params["macro_category"] = macro_category
        if source_verification_status:
            conditions.append("source_verification_status = :svs")
            params["svs"] = source_verification_status

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT kpi_id, display_name, description, kpi_type, macro_category,
                   subsector, unit, primary_source, calculation_method, v1_status,
                   dashboard_priority, excel_export_priority, source_verification_status,
                   higher_is_better, source_caveats, audit_notes
            FROM kpi_catalog {where}
            ORDER BY kpi_id
        """
        with self._engine().connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [
            KPICatalogEntryDTO(
                kpi_id=r[0],
                display_name=r[1],
                description=r[2] or "",
                kpi_type=r[3] or "",
                macro_category=r[4] or "",
                subsector=r[5] or "",
                unit=r[6] or "",
                primary_source=r[7] or "",
                calculation_method=r[8] or "",
                v1_status=r[9] or "",
                dashboard_priority=r[10] or "",
                excel_export_priority=r[11] or "",
                source_verification_status=r[12] or "",
                higher_is_better=None if r[13] is None else bool(r[13]),
                source_caveats=r[14] or "",
                audit_notes=r[15] or "",
            )
            for r in rows
        ]

    # ── Time series ───────────────────────────────────────────────────────────

    def get_country_kpi_series(
        self,
        kpi_ids: list[str] | None = None,
        iso_codes: list[str] | None = None,
        years: list[int] | None = None,
    ) -> list[CountryKPIValueDTO]:
        """Return time-series values filtered by KPI IDs, country codes, and/or years."""
        conditions = []
        params: dict[str, Any] = {}

        if kpi_ids:
            placeholders = ",".join(f":kpi_{i}" for i in range(len(kpi_ids)))
            conditions.append(f"v.kpi_id IN ({placeholders})")
            for i, k in enumerate(kpi_ids):
                params[f"kpi_{i}"] = k

        if iso_codes:
            placeholders = ",".join(f":iso_{i}" for i in range(len(iso_codes)))
            conditions.append(f"v.iso_code IN ({placeholders})")
            for i, c in enumerate(iso_codes):
                params[f"iso_{i}"] = c

        if years:
            placeholders = ",".join(f":yr_{i}" for i in range(len(years)))
            conditions.append(f"v.period IN ({placeholders})")
            for i, y in enumerate(years):
                params[f"yr_{i}"] = y

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT v.kpi_id, v.iso_code,
                   COALESCE(c.country_name, v.iso_code) AS country_name,
                   v.period, v.value, v.unit, v.source, v.source_priority,
                   v.source_field, v.data_quality_status,
                   v.source_conflict, v.fallback_used, v.snapshot_id,
                   v.value_owid, v.value_ember
            FROM country_kpi_values v
            LEFT JOIN country_dimension c ON c.iso_code = v.iso_code
            {where}
            ORDER BY v.kpi_id, v.iso_code, v.period
        """
        with self._engine().connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_dto(r) for r in rows]

    # ── Cross-country comparison ──────────────────────────────────────────────

    def get_country_kpi_compare(
        self,
        kpi_id: str,
        year: int,
    ) -> list[CountryKPIValueDTO]:
        """Return all countries' value for a single KPI in a single year."""
        sql = """
            SELECT v.kpi_id, v.iso_code,
                   COALESCE(c.country_name, v.iso_code) AS country_name,
                   v.period, v.value, v.unit, v.source, v.source_priority,
                   v.source_field, v.data_quality_status,
                   v.source_conflict, v.fallback_used, v.snapshot_id,
                   v.value_owid, v.value_ember
            FROM country_kpi_values v
            LEFT JOIN country_dimension c ON c.iso_code = v.iso_code
            WHERE v.kpi_id = :kpi_id AND v.period = :year
            ORDER BY v.value DESC NULLS LAST
        """
        with self._engine().connect() as conn:
            rows = conn.execute(text(sql), {"kpi_id": kpi_id, "year": year}).fetchall()
        return [self._row_to_dto(r) for r in rows]

    # ── Health / staleness ────────────────────────────────────────────────────

    def get_energy_kpi_health(self) -> EnergyKPIHealthDTO:
        """Return staleness, last refresh info, and DQ summary."""
        sql_last = """
            SELECT started_at, finished_at, status, rows_ingested, rows_conflict
            FROM kpi_refresh_log
            ORDER BY started_at DESC
            LIMIT 1
        """
        sql_snap = """
            SELECT snapshot_id, fetched_at
            FROM source_snapshots
            WHERE source = 'OWID' AND status = 'ok'
            ORDER BY fetched_at DESC
            LIMIT 1
        """
        sql_dq = """
            SELECT
                SUM(CASE WHEN severity='error' AND passed=0 THEN 1 ELSE 0 END) AS errors,
                SUM(CASE WHEN severity='warn' AND passed=0 THEN 1 ELSE 0 END) AS warnings
            FROM data_quality_checks
            WHERE run_id = (
                SELECT run_id FROM kpi_refresh_log ORDER BY started_at DESC LIMIT 1
            )
        """
        with self._engine().connect() as conn:
            log_row = conn.execute(text(sql_last)).fetchone()
            snap_row = conn.execute(text(sql_snap)).fetchone()
            dq_row = conn.execute(text(sql_dq)).fetchone()

        last_refresh_at = log_row[0] if log_row else None
        last_refresh_status = log_row[2] if log_row else None
        rows_ingested = int(log_row[3] or 0) if log_row else 0
        rows_conflict = int(log_row[4] or 0) if log_row else 0

        owid_snapshot_id = snap_row[0] if snap_row else None
        owid_fetched_at = snap_row[1] if snap_row else None

        is_stale = False
        if owid_fetched_at:
            try:
                fetched = datetime.fromisoformat(owid_fetched_at.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - fetched).days
                is_stale = age > _STALE_THRESHOLD_DAYS
            except Exception:
                pass

        dq_errors = int(dq_row[0] or 0) if dq_row else 0
        dq_warnings = int(dq_row[1] or 0) if dq_row else 0

        return EnergyKPIHealthDTO(
            last_refresh_at=last_refresh_at,
            last_refresh_status=last_refresh_status,
            rows_ingested=rows_ingested,
            rows_conflict=rows_conflict,
            is_stale=is_stale,
            owid_snapshot_id=owid_snapshot_id,
            owid_fetched_at=owid_fetched_at,
            dq_errors=dq_errors,
            dq_warnings=dq_warnings,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dto(r) -> CountryKPIValueDTO:
        return CountryKPIValueDTO(
            kpi_id=r[0],
            iso_code=r[1],
            country_name=r[2],
            period=int(r[3]),
            value=float(r[4]) if r[4] is not None else None,
            unit=r[5] or "",
            source=r[6] or "",
            source_priority=int(r[7]) if r[7] is not None else 1,
            source_field=r[8] or "",
            data_quality_status=r[9] or "ok",
            source_conflict=bool(r[10]),
            fallback_used=bool(r[11]),
            snapshot_id=r[12] or "",
            value_owid=float(r[13]) if r[13] is not None else None,
            value_ember=float(r[14]) if r[14] is not None else None,
        )
