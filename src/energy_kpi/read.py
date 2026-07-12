"""EnergyKPIReadService — offline-only reads from energy_kpis.db.

All methods query local SQLite. No network calls on the read path.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text

from src.energy_kpi.hourly_read_adapter import (
    HourlyReadRequest,
    read_hourly_from_hot_cold,
)
from src.energy_kpi.fuel_distribution import (
    get_fuel_distribution_product_year_summary,
    get_fuel_distribution_state_month_series,
    read_fuel_distribution_detail,
)
from src.platform.contracts import (
    CountryKPIValueDTO,
    EnergyKPIHealthDTO,
    KPICatalogEntryDTO,
    SINKPIDashboardDTO,
    SINKPIHealthDTO,
    SINKPIObservationDTO,
    SINKPISourceStatusDTO,
)
from src.energy_kpi.metrics import (
    capacity_factor,
    hours_in_reference_month,
    mwh_to_gwh,
    mwmed_to_mwh,
)
from src.energy_kpi.plant_parcel_ingest import (
    PLANT_SOURCES,
    SOURCE_ANEEL_SIGA,
    SOURCE_CCEE_HOURLY,
    SOURCE_CCEE_MONTHLY,
)
from src.energy_kpi.plant_marts import CEG_HOURLY_MART_NAME, get_plant_hourly_mart_status
from src.energy_kpi.schema import get_energy_kpi_engine
from src.energy_kpi.sin_catalog import SIN_KPI_CATALOG
from src.platform.settings import AppSettings

logger = logging.getLogger(__name__)

_STALE_THRESHOLD_DAYS = 90
_PLANT_SOURCE_STATUS_ORDER = (SOURCE_ANEEL_SIGA, SOURCE_CCEE_MONTHLY, SOURCE_CCEE_HOURLY)
_HOURLY_HOT_COLD_MANIFEST_ENV = "CVM_ENERGY_HOURLY_HOT_COLD_MANIFEST"
_DEFAULT_HOURLY_STORE_MANIFEST = Path("analytics") / "energy" / "ccee_plant_generation_hourly" / "manifest.json"


def _normalize_plant_source_ids(source_ids: list[str] | None) -> list[str]:
    if not source_ids:
        return list(_PLANT_SOURCE_STATUS_ORDER)
    requested = {str(source_id) for source_id in source_ids}
    return [source_id for source_id in _PLANT_SOURCE_STATUS_ORDER if source_id in requested]


def _is_runtime_eligible_hourly_manifest(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if payload.get("runtime_eligible") is True:
        return True
    return bool(
        payload.get("validation", {}).get("ok") is True
        and payload.get("selection", {}).get("full_months") is True
        and payload.get("source_unchanged") is True
    )


def _hourly_hot_cold_manifest_path(settings: AppSettings) -> Path | None:
    value = os.getenv(_HOURLY_HOT_COLD_MANIFEST_ENV)
    if not value or not value.strip():
        default_path = Path(settings.paths.data_dir) / _DEFAULT_HOURLY_STORE_MANIFEST
        return default_path if default_path.exists() and _is_runtime_eligible_hourly_manifest(default_path) else None
    return Path(value.strip()).expanduser()


def _plant_source_status_rows(
    db_rows: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    """Return plant source metadata without requiring a write on the read path."""
    by_source_id = {str(row["source_id"]): dict(row) for row in db_rows}
    fallback_by_source_id = {str(row["source_id"]): dict(row) for row in PLANT_SOURCES}
    return [
        by_source_id.get(source_id) or fallback_by_source_id[source_id]
        for source_id in source_ids
    ]


class EnergyKPIReadService:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def _engine(self):
        return get_energy_kpi_engine(self._settings)

    def get_fuel_distribution_product_year_summary(
        self,
        *,
        source_dataset_id: str | None = None,
        product: str | None = None,
        unit: str | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
        limit: int | None = 500,
    ) -> dict[str, Any]:
        """Return compact ANP Fuel Distribution yearly summaries from SQLite marts."""
        with self._engine().connect() as conn:
            return get_fuel_distribution_product_year_summary(
                conn,
                source_dataset_id=source_dataset_id,
                product=product,
                unit=unit,
                start_year=start_year,
                end_year=end_year,
                limit=limit,
            )

    def get_fuel_distribution_state_month_series(
        self,
        *,
        source_dataset_id: str | None,
        product: str | None,
        state: str | None = None,
        start_period: str | None = None,
        end_period: str | None = None,
        unit: str | None = None,
        limit: int | None = 5_000,
    ) -> dict[str, Any]:
        """Return bounded state/month ANP Fuel Distribution series from SQLite marts."""
        with self._engine().connect() as conn:
            return get_fuel_distribution_state_month_series(
                conn,
                source_dataset_id=source_dataset_id,
                product=product,
                state=state,
                start_period=start_period,
                end_period=end_period,
                unit=unit,
                limit=limit,
            )

    def get_fuel_distribution_detail(
        self,
        *,
        source_dataset_id: str | None,
        product: str | None,
        year: int | None,
        region_or_state: str | None = None,
        limit: int | None = 500,
        offset: int | None = 0,
    ) -> dict[str, Any]:
        """Return bounded ANP Fuel Distribution detail from managed Parquet."""
        return read_fuel_distribution_detail(
            data_dir=Path(self._settings.paths.data_dir),
            source_dataset_id=source_dataset_id,
            product=product,
            year=year,
            region_or_state=region_or_state,
            limit=limit,
            offset=offset,
        )

    def get_energy_mart_status(self) -> dict[str, Any]:
        """Return lightweight Energy mart maintenance status.

        This intentionally avoids exact counts on the raw hourly fact table.
        Mart row counts are acceptable here because the marts are compact
        relative to the raw CCEE hourly table and are meant for diagnostics.
        """
        db_path = self._settings.paths.energy_kpi_db_path
        with self._engine().connect() as conn:
            mart_status = get_plant_hourly_mart_status(conn)
            source_max_rowid = int(
                conn.execute(text("SELECT MAX(rowid) FROM ccee_plant_parcel_hourly")).scalar()
                or 0
            )
            source_latest_reference = conn.execute(
                text("SELECT MAX(reference_datetime) FROM ccee_plant_parcel_hourly")
            ).scalar()
            daily_rows = int(
                conn.execute(text("SELECT COUNT(*) FROM plant_parcel_daily_generation_mart")).scalar()
                or 0
            )
            preview_rows = int(
                conn.execute(text("SELECT COUNT(*) FROM plant_parcel_hourly_preview_mart")).scalar()
                or 0
            )
            ceg_hourly_rows = int(
                conn.execute(text(f"SELECT COUNT(*) FROM {CEG_HOURLY_MART_NAME}")).scalar()
                or 0
            )
            daily_coverage = conn.execute(text("""
                SELECT MIN(reference_month) AS period_start,
                       MAX(reference_month) AS period_end,
                       COUNT(DISTINCT reference_month) AS period_count,
                       COUNT(DISTINCT plant_parcel_code) AS parcel_count,
                       SUM(hourly_observations) AS source_observations
                FROM plant_parcel_daily_generation_mart
            """)).mappings().first() or {}
            preview_coverage = conn.execute(text("""
                SELECT MIN(reference_month) AS period_start,
                       MAX(reference_month) AS period_end,
                       COUNT(DISTINCT plant_parcel_code) AS parcel_count
                FROM plant_parcel_hourly_preview_mart
            """)).mappings().first() or {}
            ceg_hourly_coverage = conn.execute(text(f"""
                SELECT MIN(reference_month) AS period_start,
                       MAX(reference_month) AS period_end,
                       COUNT(DISTINCT reference_month) AS period_count,
                       COUNT(DISTINCT ceg) AS ceg_count,
                       SUM(plant_parcel_count) AS grouped_parcel_count
                FROM {CEG_HOURLY_MART_NAME}
            """)).mappings().first() or {}
            source_submarket_rows = int(
                conn.execute(text("SELECT COUNT(*) FROM plant_parcel_source_submarket_monthly_mart")).scalar()
                or 0
            )
            source_submarket_coverage = conn.execute(text("""
                SELECT MIN(reference_month) AS period_start,
                       MAX(reference_month) AS period_end,
                       COUNT(DISTINCT reference_month) AS period_count,
                       COUNT(DISTINCT generation_source) AS generation_source_count,
                       COUNT(DISTINCT submarket) AS submarket_count,
                       SUM(plant_parcel_count) AS grouped_parcel_count,
                       SUM(hourly_observations) AS source_observations
                FROM plant_parcel_source_submarket_monthly_mart
            """)).mappings().first() or {}

        source_latest_month = str(source_latest_reference)[:7] if source_latest_reference else None
        daily_build = dict(mart_status.get("plant_parcel_daily_generation_mart") or {})
        preview_build = dict(mart_status.get("plant_parcel_hourly_preview_mart") or {})
        daily_period_end = daily_coverage.get("period_end")
        is_daily_current = bool(source_latest_month and daily_period_end and str(daily_period_end) >= source_latest_month)
        return {
            "db_path": str(db_path),
            "db_size_bytes": db_path.stat().st_size if db_path.exists() else 0,
            "source": {
                "table": "ccee_plant_parcel_hourly",
                "row_estimate": source_max_rowid,
                "max_rowid": source_max_rowid,
                "latest_reference": source_latest_reference,
                "latest_reference_month": source_latest_month,
                "count_method": "MAX(rowid)",
            },
            "marts": {
                "plant_parcel_daily_generation_mart": {
                    **daily_build,
                    "row_count_current": daily_rows,
                    "period_start_current": daily_coverage.get("period_start"),
                    "period_end_current": daily_period_end,
                    "period_count_current": int(daily_coverage.get("period_count") or 0),
                    "parcel_count_current": int(daily_coverage.get("parcel_count") or 0),
                    "source_observations_current": int(daily_coverage.get("source_observations") or 0),
                    "is_current_for_latest_source_month": is_daily_current,
                },
                "plant_parcel_hourly_preview_mart": {
                    **preview_build,
                    "row_count_current": preview_rows,
                    "period_start_current": preview_coverage.get("period_start"),
                    "period_end_current": preview_coverage.get("period_end"),
                    "parcel_count_current": int(preview_coverage.get("parcel_count") or 0),
                },
                CEG_HOURLY_MART_NAME: {
                    **dict(mart_status.get(CEG_HOURLY_MART_NAME) or {}),
                    "row_count_current": ceg_hourly_rows,
                    "period_start_current": ceg_hourly_coverage.get("period_start"),
                    "period_end_current": ceg_hourly_coverage.get("period_end"),
                    "period_count_current": int(ceg_hourly_coverage.get("period_count") or 0),
                    "ceg_count_current": int(ceg_hourly_coverage.get("ceg_count") or 0),
                    "grouped_parcel_count_current": int(ceg_hourly_coverage.get("grouped_parcel_count") or 0),
                },
                "plant_parcel_source_submarket_monthly_mart": {
                    **dict(mart_status.get("plant_parcel_source_submarket_monthly_mart") or {}),
                    "row_count_current": source_submarket_rows,
                    "period_start_current": source_submarket_coverage.get("period_start"),
                    "period_end_current": source_submarket_coverage.get("period_end"),
                    "period_count_current": int(source_submarket_coverage.get("period_count") or 0),
                    "generation_source_count_current": int(source_submarket_coverage.get("generation_source_count") or 0),
                    "submarket_count_current": int(source_submarket_coverage.get("submarket_count") or 0),
                    "grouped_parcel_count_current": int(source_submarket_coverage.get("grouped_parcel_count") or 0),
                    "source_observations_current": int(source_submarket_coverage.get("source_observations") or 0),
                },
            },
            "recommended_daily_rebuild_month": source_latest_month,
            "notes": [
                "Raw hourly row count is estimated with MAX(rowid); exact COUNT(*) is intentionally avoided.",
                "Daily marts are rebuildable from ccee_plant_parcel_hourly and do not replace raw/source facts.",
            ],
        }

    def get_plant_parcel_source_submarket_summary(
        self,
        *,
        reference_month: str | None = None,
        generation_source: str | None = None,
        submarket: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return compact source/submarket monthly summaries from the mart."""
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if reference_month:
            params["reference_month"] = str(reference_month).strip()
            conditions.append("reference_month = :reference_month")
        if generation_source:
            params["generation_source"] = str(generation_source).strip()
            conditions.append("generation_source = :generation_source")
        if submarket:
            params["submarket"] = str(submarket).strip()
            conditions.append("submarket = :submarket")
        bounded_limit = max(1, min(int(limit or 500), 1000))
        bounded_offset = max(0, int(offset or 0))
        params.update({"limit": bounded_limit, "offset": bounded_offset})
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with self._engine().connect() as conn:
            rows = conn.execute(text(f"""
                SELECT reference_month, generation_source, submarket,
                       plant_parcel_count, hourly_observations,
                       generation_mwh, verified_generation_mwh,
                       first_reference_datetime, last_reference_datetime,
                       source_dataset, first_snapshot_id, last_snapshot_id,
                       rebuilt_at, build_version
                FROM plant_parcel_source_submarket_monthly_mart
                {where}
                ORDER BY reference_month DESC, hourly_observations DESC,
                         generation_source, submarket
                LIMIT :limit OFFSET :offset
            """), params).mappings().all()
            total = int(conn.execute(text(f"""
                SELECT COUNT(*)
                FROM plant_parcel_source_submarket_monthly_mart
                {where}
            """), params).scalar() or 0)
            coverage = conn.execute(text(f"""
                SELECT MIN(reference_month) AS period_start,
                       MAX(reference_month) AS period_end,
                       COUNT(DISTINCT reference_month) AS period_count,
                       COUNT(DISTINCT generation_source) AS generation_source_count,
                       COUNT(DISTINCT submarket) AS submarket_count,
                       SUM(hourly_observations) AS source_observations
                FROM plant_parcel_source_submarket_monthly_mart
                {where}
            """), params).mappings().first() or {}

        return {
            "records": [dict(row) for row in rows],
            "count": len(rows),
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
            "filters": {
                "reference_month": reference_month,
                "generation_source": generation_source,
                "submarket": submarket,
            },
            "data_source": "plant_parcel_source_submarket_monthly_mart",
            "coverage": {
                "period_start": coverage.get("period_start"),
                "period_end": coverage.get("period_end"),
                "period_count": int(coverage.get("period_count") or 0),
                "generation_source_count": int(coverage.get("generation_source_count") or 0),
                "submarket_count": int(coverage.get("submarket_count") or 0),
                "source_observations": int(coverage.get("source_observations") or 0),
            },
        }

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

    # ── SIN subsystem KPIs ───────────────────────────────────────────────────

    def get_sin_kpi_series(
        self,
        *,
        kpi_ids: list[str] | None = None,
        subsystem_codes: list[str] | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        limit: int | None = None,
    ) -> list[SINKPIObservationDTO]:
        """Return local SIN KPI observations. No network calls."""
        conditions = []
        params: dict[str, Any] = {}
        if kpi_ids:
            placeholders = ",".join(f":kpi_{i}" for i in range(len(kpi_ids)))
            conditions.append(f"v.kpi_id IN ({placeholders})")
            for i, value in enumerate(kpi_ids):
                params[f"kpi_{i}"] = value
        if subsystem_codes:
            placeholders = ",".join(f":sub_{i}" for i in range(len(subsystem_codes)))
            conditions.append(f"v.subsystem_code IN ({placeholders})")
            for i, value in enumerate(subsystem_codes):
                params[f"sub_{i}"] = value
        if start_datetime:
            conditions.append("v.reference_datetime >= :start_datetime")
            params["start_datetime"] = start_datetime
        if end_datetime:
            conditions.append("v.reference_datetime <= :end_datetime")
            params["end_datetime"] = end_datetime

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        has_limit = limit is not None and int(limit) > 0
        if has_limit:
            params["limit"] = int(limit)

        select_sql = f"""
            SELECT v.kpi_id, v.subsystem_code,
                   COALESCE(d.display_name, v.subsystem_code) AS subsystem_name,
                   v.reference_datetime, v.normalized_value, v.unit, v.source,
                   v.source_dataset, v.source_field, v.data_quality_status,
                   v.snapshot_id
            FROM subsystem_kpi_values v
            LEFT JOIN subsystem_dimension d ON d.subsystem_code = v.subsystem_code
            {where}
        """
        if has_limit:
            sql = f"""
                WITH newest AS (
                    {select_sql}
                    ORDER BY v.reference_datetime DESC, v.subsystem_code DESC, v.kpi_id DESC
                    LIMIT :limit
                )
                SELECT *
                FROM newest
                ORDER BY reference_datetime, subsystem_code, kpi_id
            """
        else:
            sql = f"""
                {select_sql}
                ORDER BY v.reference_datetime, v.subsystem_code, v.kpi_id
            """
        with self._engine().connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._sin_row_to_dto(row) for row in rows]

    def get_sin_kpi_dashboard(self) -> SINKPIDashboardDTO:
        """Return latest SIN KPI snapshot plus provenance source panel."""
        latest_sql = """
            WITH latest AS (
                SELECT kpi_id, subsystem_code, MAX(reference_datetime) AS reference_datetime
                FROM subsystem_kpi_values
                GROUP BY kpi_id, subsystem_code
            )
            SELECT v.kpi_id, v.subsystem_code,
                   COALESCE(d.display_name, v.subsystem_code) AS subsystem_name,
                   v.reference_datetime, v.normalized_value, v.unit, v.source,
                   v.source_dataset, v.source_field, v.data_quality_status,
                   v.snapshot_id
            FROM subsystem_kpi_values v
            JOIN latest l
              ON l.kpi_id = v.kpi_id
             AND l.subsystem_code = v.subsystem_code
             AND l.reference_datetime = v.reference_datetime
            LEFT JOIN subsystem_dimension d ON d.subsystem_code = v.subsystem_code
            ORDER BY d.sort_order, v.kpi_id
        """
        with self._engine().connect() as conn:
            rows = conn.execute(text(latest_sql)).fetchall()
            source_statuses = self._get_sin_source_statuses(conn)
            last_successful_update = conn.execute(text("""
                SELECT finished_at
                FROM kpi_refresh_log
                WHERE source = 'SIN' AND status IN ('success', 'partial')
                ORDER BY started_at DESC
                LIMIT 1
            """)).scalar()
            latest_reference = conn.execute(text("""
                SELECT MAX(reference_datetime) FROM subsystem_kpi_values
            """)).scalar()
        observations = tuple(self._sin_row_to_dto(row) for row in rows)
        return SINKPIDashboardDTO(
            last_successful_update=last_successful_update,
            latest_reference_datetime=latest_reference,
            is_empty=len(observations) == 0,
            is_stale=self._is_sin_stale(latest_reference),
            observations=observations,
            source_statuses=tuple(source_statuses),
        )

    def get_sin_kpi_health(self) -> SINKPIHealthDTO:
        sql_last = """
            SELECT started_at, finished_at, status, rows_ingested, error
            FROM kpi_refresh_log
            WHERE source = 'SIN'
            ORDER BY started_at DESC
            LIMIT 1
        """
        sql_dq = """
            SELECT
                SUM(CASE WHEN severity='error' AND passed=0 THEN 1 ELSE 0 END) AS errors,
                SUM(CASE WHEN severity='warn' AND passed=0 THEN 1 ELSE 0 END) AS warnings
            FROM data_quality_checks
            WHERE run_id = (
                SELECT run_id FROM kpi_refresh_log WHERE source = 'SIN' ORDER BY started_at DESC LIMIT 1
            )
        """
        with self._engine().connect() as conn:
            log_row = conn.execute(text(sql_last)).fetchone()
            latest_reference = conn.execute(text("""
                SELECT MAX(reference_datetime) FROM subsystem_kpi_values
            """)).scalar()
            dq_row = conn.execute(text(sql_dq)).fetchone()
        return SINKPIHealthDTO(
            last_refresh_at=log_row[0] if log_row else None,
            last_refresh_status=log_row[2] if log_row else None,
            rows_ingested=int(log_row[3] or 0) if log_row else 0,
            latest_reference_datetime=latest_reference,
            is_stale=self._is_sin_stale(latest_reference),
            dq_errors=int(dq_row[0] or 0) if dq_row else 0,
            dq_warnings=int(dq_row[1] or 0) if dq_row else 0,
        )

    # ── Plant / plant-parcel KPIs ───────────────────────────────────────────

    def get_plant_parcel_source_statuses(self, source_ids: list[str] | None = None) -> dict[str, Any]:
        """Return local cache status for ANEEL SIGA and CCEE plant datasets."""
        selected_source_ids = _normalize_plant_source_ids(source_ids)
        with self._engine().connect() as conn:
            db_source_rows = [
                dict(row)
                for row in conn.execute(
                    text("""
                    SELECT source_id, source_name, dataset_name, provider, official_url,
                           refresh_frequency, granularity, description, known_caveats
                    FROM energy_sources
                    WHERE source_id IN :source_ids
                    ORDER BY
                        CASE source_id
                            WHEN 'aneel_siga_plants' THEN 1
                            WHEN 'ccee_plant_parcel_monthly' THEN 2
                            WHEN 'ccee_plant_generation_hourly' THEN 3
                            ELSE 9
                        END
                    """).bindparams(bindparam("source_ids", expanding=True)),
                    {"source_ids": selected_source_ids},
                ).mappings().all()
            ]
            source_rows = _plant_source_status_rows(db_source_rows, selected_source_ids)
            latest_logs = {
                row["source_id"]: dict(row)
                for row in conn.execute(
                    text("""
                    SELECT l.*
                    FROM energy_source_refresh_log l
                    JOIN (
                        SELECT source_id, MAX(started_at) AS started_at
                        FROM energy_source_refresh_log
                        WHERE source_id IN :source_ids
                        GROUP BY source_id
                    ) x
                      ON x.source_id = l.source_id
                     AND x.started_at = l.started_at
                    """).bindparams(bindparam("source_ids", expanding=True)),
                    {"source_ids": selected_source_ids},
                ).mappings().all()
            }
            latest_manual_logs = {
                row["source_id"]: dict(row)
                for row in conn.execute(
                    text("""
                    SELECT l.*
                    FROM energy_source_refresh_log l
                    JOIN (
                        SELECT source_id, MAX(started_at) AS started_at
                        FROM energy_source_refresh_log
                        WHERE import_mode = 'manual_file'
                          AND source_id IN :source_ids
                        GROUP BY source_id
                    ) x
                      ON x.source_id = l.source_id
                     AND x.started_at = l.started_at
                    """).bindparams(bindparam("source_ids", expanding=True)),
                    {"source_ids": selected_source_ids},
                ).mappings().all()
            }
            counts: dict[str, dict[str, Any]] = {}
            if SOURCE_ANEEL_SIGA in selected_source_ids:
                counts[SOURCE_ANEEL_SIGA] = {
                    "records": int(conn.execute(text("SELECT COUNT(*) FROM aneel_siga_plants")).scalar() or 0),
                    "latest_reference": conn.execute(text("SELECT MAX(source_updated_at) FROM aneel_siga_plants")).scalar(),
                }
            if SOURCE_CCEE_MONTHLY in selected_source_ids:
                counts[SOURCE_CCEE_MONTHLY] = {
                    "records": int(conn.execute(text("SELECT COUNT(*) FROM ccee_plant_parcel_monthly")).scalar() or 0),
                    "latest_reference": conn.execute(text("SELECT MAX(reference_month) FROM ccee_plant_parcel_monthly")).scalar(),
                }
            if SOURCE_CCEE_HOURLY in selected_source_ids:
                counts[SOURCE_CCEE_HOURLY] = {
                    "records": self._fast_ccee_hourly_record_count(conn, latest_logs.get(SOURCE_CCEE_HOURLY, {})),
                    "latest_reference": conn.execute(text("SELECT MAX(reference_datetime) FROM ccee_plant_parcel_hourly")).scalar(),
                }
            plant_hourly_mart_status = get_plant_hourly_mart_status(conn)

        statuses: list[dict[str, Any]] = []
        for row in source_rows:
            source_id = str(row["source_id"])
            log_row = latest_logs.get(source_id, {})
            manual_log_row = latest_manual_logs.get(source_id, {})
            count_info = counts.get(source_id, {"records": 0, "latest_reference": None})
            status = self._plant_source_cache_status(
                latest_status=log_row.get("status"),
                local_records=int(count_info["records"] or 0),
                latest_reference=count_info.get("latest_reference"),
                source_id=source_id,
                has_refresh_log=bool(log_row),
                rows_inserted=log_row.get("rows_inserted"),
            )
            statuses.append({
                **dict(row),
                "local_records_count": int(count_info["records"] or 0),
                "latest_reference": count_info.get("latest_reference"),
                "last_refresh_at": log_row.get("finished_at") or log_row.get("started_at"),
                "last_status": log_row.get("status"),
                "last_error": log_row.get("error_message"),
                "last_warning": log_row.get("warning_message"),
                "last_requested_period": log_row.get("requested_period"),
                "last_period_start": log_row.get("period_start"),
                "last_period_end": log_row.get("period_end"),
                "last_source_url": log_row.get("source_url"),
                "last_local_file_path": log_row.get("local_file_path"),
                "last_checksum": log_row.get("checksum"),
                "last_downloaded_bytes": log_row.get("downloaded_bytes"),
                "last_source_rows": log_row.get("source_rows") or log_row.get("rows_downloaded"),
                "last_parsed_rows": log_row.get("parsed_rows"),
                "last_normalized_rows": log_row.get("normalized_rows"),
                "last_rows_inserted": log_row.get("rows_inserted"),
                "last_rows_updated": log_row.get("rows_updated"),
                "last_rows_skipped": log_row.get("rows_skipped"),
                "last_detected_encoding": log_row.get("detected_encoding"),
                "last_import_mode": log_row.get("import_mode"),
                "last_original_file_name": log_row.get("original_file_name"),
                "last_file_size_bytes": log_row.get("file_size_bytes"),
                "last_file_hash": log_row.get("file_hash") or log_row.get("checksum"),
                "last_file_type": log_row.get("file_type"),
                "last_detected_period": log_row.get("detected_period"),
                "last_manual_import_at": manual_log_row.get("finished_at") or manual_log_row.get("started_at"),
                "last_manual_status": manual_log_row.get("status"),
                "last_manual_error": manual_log_row.get("error_message"),
                "last_manual_warning": manual_log_row.get("warning_message"),
                "last_manual_file_name": manual_log_row.get("original_file_name"),
                "last_manual_file_size_bytes": manual_log_row.get("file_size_bytes"),
                "last_manual_file_hash": manual_log_row.get("file_hash") or manual_log_row.get("checksum"),
                "last_manual_file_type": manual_log_row.get("file_type"),
                "last_manual_detected_period": manual_log_row.get("detected_period"),
                "last_manual_rows_inserted": manual_log_row.get("rows_inserted"),
                "last_manual_rows_skipped": manual_log_row.get("rows_skipped"),
                "source_page_url": log_row.get("source_page_url") or row["official_url"],
                "refresh_id": log_row.get("refresh_id"),
                "cache_status": status,
            })
        return {
            "source_statuses": statuses,
            "count": len(statuses),
            "database_path": str(self._settings.paths.energy_kpi_db_path),
            "raw_data_dir": str(self._settings.paths.energy_kpi_raw_dir),
            "mart_status": plant_hourly_mart_status,
        }

    def get_plant_parcel_catalog(
        self,
        *,
        search: str | None = None,
        entity_type: str | None = None,
        generation_source: str | None = None,
        submarket: str | None = None,
        uf: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return compact searchable plant/parcel catalog rows."""
        params: dict[str, Any] = {}
        conditions = []
        if search:
            params["search"] = f"%{_normalize_search_text(search)}%"
            conditions.append(
                "(cvm_norm(COALESCE(entity_id, '')) LIKE :search "
                "OR cvm_norm(COALESCE(plant_name, '')) LIKE :search "
                "OR cvm_norm(COALESCE(plant_parcel_code, '')) LIKE :search "
                "OR cvm_norm(COALESCE(plant_parcel_acronym, '')) LIKE :search "
                "OR cvm_norm(COALESCE(ceg, '')) LIKE :search "
                "OR cvm_norm(COALESCE(agent_name, '')) LIKE :search "
                "OR cvm_norm(COALESCE(generation_source, '')) LIKE :search "
                "OR cvm_norm(COALESCE(submarket, '')) LIKE :search "
                "OR cvm_norm(COALESCE(uf, '')) LIKE :search "
                "OR cvm_norm(COALESCE(phase, '')) LIKE :search)"
            )
        if entity_type:
            params["entity_type"] = entity_type
            conditions.append("entity_type = :entity_type")
        if generation_source:
            params["generation_source"] = generation_source
            conditions.append("generation_source = :generation_source")
        if submarket:
            params["submarket"] = submarket
            conditions.append("submarket = :submarket")
        if uf:
            params["uf"] = uf
            conditions.append("uf = :uf")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        bounded_limit = max(1, min(int(limit), 250))
        bounded_offset = max(0, int(offset))
        params.update({"limit": bounded_limit, "offset": bounded_offset})

        sql = f"""
            {self._plant_entities_cte()}
            SELECT e.*, 
                   m.cd_cvm AS mapped_cvm, 
                   m.custom_owner_name AS mapped_custom_owner,
                   lc.company_name AS mapped_cvm_company_name,
                   lc.ticker_b3 AS mapped_cvm_ticker,
                   m.mapping_source
            FROM entities e
            LEFT JOIN conglomerate_asset_mappings m
              ON e.entity_id = m.asset_id
             AND m.asset_type = 'plant'
            LEFT JOIN distribution_listed_companies lc
              ON m.cd_cvm = lc.cd_cvm
            {where}
            ORDER BY COALESCE(e.plant_name, e.entity_id), e.entity_type, e.entity_id
            LIMIT :limit OFFSET :offset
        """
        count_sql = f"""
            {self._plant_entities_cte()}
            SELECT COUNT(*) FROM entities {where}
        """
        with self._engine().connect() as conn:
            _install_sqlite_functions(conn)
            raw_rows = [dict(row) for row in conn.execute(text(sql), params).mappings().all()]
            total = int(conn.execute(text(count_sql), params).scalar() or 0)

        resolved_records = []
        for r_dict in raw_rows:
            m_cvm = r_dict.get("mapped_cvm")
            m_custom = r_dict.get("mapped_custom_owner")
            mc_name = r_dict.get("mapped_cvm_company_name")
            mc_ticker = r_dict.get("mapped_cvm_ticker")
            
            if m_cvm is not None:
                r_dict["owner_name"] = mc_name or f"CVM: {m_cvm}"
                r_dict["owner_ticker"] = mc_ticker
                r_dict["is_custom_owner"] = False
            elif m_custom is not None and m_custom.strip() != "":
                r_dict["owner_name"] = m_custom.strip()
                r_dict["owner_ticker"] = "Non-Listed"
                r_dict["is_custom_owner"] = True
            else:
                r_dict["owner_name"] = None
                r_dict["owner_ticker"] = None
                r_dict["is_custom_owner"] = False
            resolved_records.append(r_dict)

        facets = self._plant_facets(resolved_records)
        return {
            "records": resolved_records,
            "count": len(resolved_records),
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
            "facets": facets,
        }

    def get_plant_parcel_detail(
        self,
        *,
        entity_id: str,
        entity_type: str | None = None,
    ) -> dict[str, Any]:
        """Return selected plant/parcel detail with metrics and provenance."""
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            return {"error": "entity_id is required"}

        with self._engine().connect() as conn:
            resolved_type = entity_type or self._resolve_plant_entity_type(conn, entity_id)
            parcel = None
            aneel = None
            parcels: list[dict[str, Any]] = []
            monthly: list[dict[str, Any]] = []
            hourly: list[dict[str, Any]] = []

            # Query mapping info
            mapping_row = conn.execute(text("""
                SELECT m.cd_cvm, m.custom_owner_name, m.mapping_source,
                       lc.company_name, lc.ticker_b3
                FROM conglomerate_asset_mappings m
                LEFT JOIN distribution_listed_companies lc ON m.cd_cvm = lc.cd_cvm
                WHERE m.asset_id = :entity_id AND m.asset_type = 'plant'
            """), {"entity_id": entity_id}).mappings().first()
            
            owner_info = None
            if mapping_row:
                m_cvm = mapping_row["cd_cvm"]
                m_custom = mapping_row["custom_owner_name"]
                if m_cvm is not None:
                    owner_info = {
                        "cd_cvm": m_cvm,
                        "owner_name": mapping_row["company_name"] or f"CVM: {m_cvm}",
                        "ticker_b3": mapping_row["ticker_b3"],
                        "is_custom": False,
                        "source": mapping_row["mapping_source"]
                    }
                elif m_custom is not None and m_custom.strip() != "":
                    owner_info = {
                        "cd_cvm": None,
                        "owner_name": m_custom.strip(),
                        "ticker_b3": "Non-Listed",
                        "is_custom": True,
                        "source": mapping_row["mapping_source"]
                    }

            if resolved_type == "ccee_plant_parcel":
                parcel = conn.execute(text("""
                    SELECT p.*, a.plant_name AS aneel_plant_name, a.phase AS aneel_phase,
                           a.authorized_capacity_kw, a.inspected_capacity_kw,
                           a.physical_guarantee_kw, a.operation_start_date AS aneel_operation_start_date,
                           a.grant_type AS aneel_grant_type, a.ownership_description
                    FROM ccee_plant_parcels p
                    LEFT JOIN aneel_siga_plants a ON a.ceg = p.ceg
                    WHERE p.plant_parcel_code = :entity_id
                """), {"entity_id": entity_id}).mappings().first()
                if not parcel:
                    return {"error": f"Plant parcel not found: {entity_id}"}
                parcel = dict(parcel)
                ceg = parcel.get("ceg")
                if ceg:
                    aneel_row = conn.execute(text("""
                        SELECT * FROM aneel_siga_plants WHERE ceg = :ceg
                    """), {"ceg": ceg}).mappings().first()
                    aneel = dict(aneel_row) if aneel_row else None
                    parcels = [dict(row) for row in conn.execute(text("""
                        SELECT plant_parcel_code, plant_parcel_acronym, plant_name,
                               agent_name, submarket, generation_source, capacity_mw,
                               physical_guarantee_mwmed, source_reference_month
                        FROM ccee_plant_parcels
                        WHERE ceg = :ceg
                        ORDER BY plant_parcel_code
                    """), {"ceg": ceg}).mappings().all()]
                monthly = [dict(row) for row in conn.execute(text("""
                    SELECT *
                    FROM ccee_plant_parcel_monthly
                    WHERE plant_parcel_code = :entity_id
                    ORDER BY reference_month DESC
                    LIMIT 36
                """), {"entity_id": entity_id}).mappings().all()]
                hourly = [dict(row) for row in conn.execute(text("""
                    SELECT reference_datetime, commercialization_period,
                           generation_center_of_gravity_mwh, verified_generation_ons_mwh,
                           verified_availability_mwh, unavailability_mwh, source_dataset, snapshot_id
                    FROM plant_parcel_hourly_preview_mart
                    WHERE plant_parcel_code = :entity_id
                    ORDER BY reference_datetime DESC, commercialization_period DESC
                    LIMIT 48
                """), {"entity_id": entity_id}).mappings().all()]
            else:
                aneel_row = conn.execute(text("""
                    SELECT * FROM aneel_siga_plants WHERE ceg = :entity_id
                """), {"entity_id": entity_id}).mappings().first()
                if not aneel_row:
                    return {"error": f"ANEEL plant not found: {entity_id}"}
                resolved_type = "aneel_plant"
                aneel = dict(aneel_row)
                parcels = [dict(row) for row in conn.execute(text("""
                    SELECT plant_parcel_code, plant_parcel_acronym, plant_name,
                           agent_name, submarket, generation_source, capacity_mw,
                           physical_guarantee_mwmed, source_reference_month
                    FROM ccee_plant_parcels
                    WHERE ceg = :entity_id
                    ORDER BY plant_parcel_code
                """), {"entity_id": entity_id}).mappings().all()]
                if parcels:
                    parcel = parcels[0]

            latest_logs = {
                row["source_id"]: dict(row)
                for row in conn.execute(text("""
                    SELECT l.*
                    FROM energy_source_refresh_log l
                    JOIN (
                        SELECT source_id, MAX(started_at) AS started_at
                        FROM energy_source_refresh_log
                        GROUP BY source_id
                    ) x
                      ON x.source_id = l.source_id
                     AND x.started_at = l.started_at
                """)).mappings().all()
            }
            plant_hourly_marts = get_plant_hourly_mart_status(conn)

        metrics = self._build_plant_metrics(
            entity_type=resolved_type,
            parcel=parcel,
            aneel=aneel,
            monthly=monthly,
            latest_logs=latest_logs,
        )
        return {
            "entity_type": resolved_type,
            "entity_id": entity_id,
            "parcel": parcel,
            "aneel_plant": aneel,
            "related_parcels": parcels,
            "metrics": metrics,
            "monthly_series": list(reversed(monthly)),
            "hourly_preview": list(reversed(hourly)),
            "owner": owner_info,
            "metadata": {
                "caveats": [
                    "CCEE plant parcel is not always equivalent to an ANEEL CEG plant or an ONS plant/group.",
                    "A CEG can map to multiple CCEE plant parcels.",
                    "Source reference date and local refresh timestamp are different and both are shown where available.",
                    "Load and demand remain system/subsystem context metrics, not plant-parcel metrics.",
                    "Energia firme, energia assegurada, and gross/net generation are not inferred without an explicit source methodology.",
                ],
                "latest_refresh_by_source": latest_logs,
                "plant_hourly_marts": plant_hourly_marts,
            },
        }

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

    @staticmethod
    def _sin_row_to_dto(r) -> SINKPIObservationDTO:
        return SINKPIObservationDTO(
            kpi_id=r[0],
            subsystem_code=r[1],
            subsystem_name=r[2],
            reference_datetime=r[3],
            value=float(r[4]) if r[4] is not None else None,
            unit=r[5] or "",
            source=r[6] or "",
            source_dataset=r[7] or "",
            source_field=r[8] or "",
            data_quality_status=r[9] or "ok",
            snapshot_id=r[10] or "",
        )

    def _get_sin_source_statuses(self, conn) -> list[SINKPISourceStatusDTO]:
        latest_log = conn.execute(text("""
            SELECT status, error
            FROM kpi_refresh_log
            WHERE source = 'SIN'
            ORDER BY started_at DESC
            LIMIT 1
        """)).fetchone()
        latest_status = latest_log[0] if latest_log else None
        error_by_dataset = self._parse_sin_error_by_dataset(latest_log[1] if latest_log else None)
        records = conn.execute(text("""
            SELECT source_dataset, COUNT(*) AS row_count, MAX(reference_datetime) AS latest_reference
            FROM subsystem_kpi_values
            GROUP BY source_dataset
        """)).fetchall()
        count_by_dataset = {row[0]: int(row[1] or 0) for row in records}
        snapshots = conn.execute(text("""
            SELECT source_version_label, MAX(fetched_at) AS fetched_at
            FROM source_snapshots
            WHERE source IN ('ONS', 'CCEE')
            GROUP BY source_version_label
        """)).fetchall()
        snapshot_by_dataset: dict[str, str] = {}
        for row in snapshots:
            label = str(row[0] or "")
            dataset = label.split(":", 1)[0]
            if dataset:
                snapshot_by_dataset[dataset] = row[1]
        by_dataset: dict[str, SINKPISourceStatusDTO] = {}
        for entry in SIN_KPI_CATALOG:
            if entry.source_dataset in by_dataset:
                continue
            by_dataset[entry.source_dataset] = SINKPISourceStatusDTO(
                source=entry.source,
                dataset=entry.source_dataset,
                frequency=entry.frequency,
                last_snapshot_at=snapshot_by_dataset.get(entry.source_dataset),
                local_records_count=count_by_dataset.get(entry.source_dataset, 0),
                last_status=latest_status,
                last_error=error_by_dataset.get(entry.source_dataset),
            )
        return list(by_dataset.values())

    @staticmethod
    def _parse_sin_error_by_dataset(error_text: str | None) -> dict[str, str]:
        if not error_text:
            return {}
        try:
            import json
            items = json.loads(error_text)
        except Exception:
            return {"unknown": error_text}
        if not isinstance(items, list):
            return {}
        result = {}
        for item in items:
            if isinstance(item, dict) and item.get("dataset"):
                result[str(item["dataset"])] = str(item.get("error") or "")
        return result

    @staticmethod
    def _is_sin_stale(latest_reference: str | None, threshold_days: int = 7) -> bool:
        if not latest_reference:
            return False
        try:
            ref = datetime.fromisoformat(str(latest_reference).replace("Z", "+00:00"))
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - ref).days > threshold_days
        except Exception:
            return False

    @staticmethod
    def _plant_entities_cte() -> str:
        return """
            WITH latest_monthly AS (
                SELECT m.*
                FROM ccee_plant_parcel_monthly m
                JOIN (
                    SELECT plant_parcel_code, MAX(reference_month) AS reference_month
                    FROM ccee_plant_parcel_monthly
                    GROUP BY plant_parcel_code
                ) latest
                  ON latest.plant_parcel_code = m.plant_parcel_code
                 AND latest.reference_month = m.reference_month
            ),
            entities AS (
                SELECT
                    'ccee_plant_parcel' AS entity_type,
                    p.plant_parcel_code AS entity_id,
                    p.plant_parcel_code,
                    p.plant_parcel_acronym,
                    p.ceg,
                    COALESCE(p.plant_name, a.plant_name, p.plant_parcel_acronym) AS plant_name,
                    COALESCE(p.agent_name, a.agent_name) AS agent_name,
                    COALESCE(p.generation_source, a.generation_source) AS generation_source,
                    p.submarket,
                    COALESCE(p.uf, a.uf) AS uf,
                    a.phase,
                    p.capacity_mw,
                    a.authorized_capacity_kw / 1000.0 AS authorized_capacity_mw,
                    a.inspected_capacity_kw / 1000.0 AS inspected_capacity_mw,
                    p.physical_guarantee_mwmed,
                    a.physical_guarantee_kw / 1000.0 AS physical_guarantee_mw,
                    p.source_reference_month AS latest_reference_month,
                    lm.generation_center_of_gravity_mwmed AS latest_generation_mwmed,
                    CASE
                        WHEN p.source_reference_month IS NULL THEN 'missing'
                        ELSE 'cached'
                    END AS data_status
                FROM ccee_plant_parcels p
                LEFT JOIN aneel_siga_plants a ON a.ceg = p.ceg
                LEFT JOIN latest_monthly lm ON lm.plant_parcel_code = p.plant_parcel_code
                UNION ALL
                SELECT
                    'aneel_plant' AS entity_type,
                    a.ceg AS entity_id,
                    NULL AS plant_parcel_code,
                    NULL AS plant_parcel_acronym,
                    a.ceg,
                    a.plant_name,
                    a.agent_name,
                    a.generation_source,
                    NULL AS submarket,
                    a.uf,
                    a.phase,
                    NULL AS capacity_mw,
                    a.authorized_capacity_kw / 1000.0 AS authorized_capacity_mw,
                    a.inspected_capacity_kw / 1000.0 AS inspected_capacity_mw,
                    NULL AS physical_guarantee_mwmed,
                    a.physical_guarantee_kw / 1000.0 AS physical_guarantee_mw,
                    a.source_updated_at AS latest_reference_month,
                    NULL AS latest_generation_mwmed,
                    'registry_only' AS data_status
                FROM aneel_siga_plants a
                WHERE NOT EXISTS (
                    SELECT 1 FROM ccee_plant_parcels p WHERE p.ceg = a.ceg
                )
            )
        """

    @staticmethod
    def _plant_facets(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
        facets: dict[str, set[str]] = {
            "entity_type": set(),
            "generation_source": set(),
            "submarket": set(),
            "uf": set(),
            "data_status": set(),
        }
        for row in rows:
            for key in facets:
                value = row.get(key)
                if value:
                    facets[key].add(str(value))
        return {key: sorted(values) for key, values in facets.items()}

    @staticmethod
    def _resolve_plant_entity_type(conn, entity_id: str) -> str:
        exists = conn.execute(text("""
            SELECT 1 FROM ccee_plant_parcels WHERE plant_parcel_code = :entity_id
        """), {"entity_id": entity_id}).scalar()
        if exists:
            return "ccee_plant_parcel"
        return "aneel_plant"

    @staticmethod
    def _positive_int(value: Any) -> int:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

    @classmethod
    def _fast_ccee_hourly_record_count(cls, conn, latest_log: dict[str, Any]) -> int:
        """Return a fast row-count estimate for the large CCEE hourly cache.

        The packaged database can hold tens of millions of hourly rows. SQLite's
        exact COUNT(*) can take over a minute on that table, and this status is
        used only to decide/display whether a local cache exists.
        """
        try:
            rowid_estimate = cls._positive_int(
                conn.execute(text("SELECT MAX(rowid) FROM ccee_plant_parcel_hourly")).scalar()
            )
            if rowid_estimate:
                return rowid_estimate
        except Exception:
            logger.debug("could not estimate CCEE hourly rows from rowid", exc_info=True)

        log_estimate = max(
            cls._positive_int(latest_log.get("rows_inserted")),
            cls._positive_int(latest_log.get("normalized_rows")),
            cls._positive_int(latest_log.get("parsed_rows")),
            cls._positive_int(latest_log.get("source_rows")),
            cls._positive_int(latest_log.get("rows_downloaded")),
        )
        if log_estimate:
            return log_estimate

        try:
            return 1 if conn.execute(text("SELECT 1 FROM ccee_plant_parcel_hourly LIMIT 1")).scalar() else 0
        except Exception:
            logger.debug("could not detect CCEE hourly cache presence", exc_info=True)
            return 0

    @staticmethod
    def _plant_source_cache_status(
        *,
        latest_status: str | None,
        local_records: int,
        latest_reference: str | None,
        source_id: str,
        has_refresh_log: bool = True,
        rows_inserted: Any = None,
    ) -> str:
        if local_records <= 0:
            if latest_status in {"error", "failed"}:
                return "failed"
            if latest_status == "warning":
                return "warning"
            if not has_refresh_log:
                return "never_refreshed"
            try:
                if rows_inserted is not None and int(rows_inserted or 0) <= 0:
                    return "warning"
            except (TypeError, ValueError):
                pass
            return "missing"
        if latest_status in {"error", "failed", "warning"}:
            return "cached"
        if not latest_reference:
            return "cached"
        threshold = 45 if source_id in {SOURCE_CCEE_HOURLY, SOURCE_ANEEL_SIGA} else 75
        try:
            parsed = datetime.fromisoformat(str(latest_reference).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return "stale" if (datetime.now(timezone.utc) - parsed).days > threshold else "fresh"
        except Exception:
            return "cached"

    @staticmethod
    def _build_plant_metrics(
        *,
        entity_type: str,
        parcel: dict[str, Any] | None,
        aneel: dict[str, Any] | None,
        monthly: list[dict[str, Any]],
        latest_logs: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        latest_monthly = monthly[0] if monthly else None
        metrics: list[dict[str, Any]] = []

        def add(
            metric_id: str,
            label: str,
            value: float | int | None,
            unit: str,
            source_id: str,
            dataset: str,
            period: str | None,
            raw_or_derived: str,
            methodology: str,
        ) -> None:
            if value is None:
                return
            log = latest_logs.get(source_id, {})
            metrics.append({
                "metric_id": metric_id,
                "label": label,
                "value": float(value),
                "unit": unit,
                "source_id": source_id,
                "source": dataset.split(":", 1)[0],
                "dataset": dataset,
                "reference_period": period,
                "local_refresh_timestamp": log.get("finished_at") or log.get("started_at"),
                "raw_or_derived": raw_or_derived,
                "methodology": methodology,
            })

        if parcel:
            add(
                "capacity_mw",
                "Capacity",
                parcel.get("capacity_mw"),
                "MW",
                SOURCE_CCEE_MONTHLY,
                "CCEE:PARCELA_USINA_MONTANTE_MENSAL",
                parcel.get("source_reference_month"),
                "raw",
                "Direct CCEE CAP_T field.",
            )
            add(
                "physical_guarantee_mwmed",
                "Physical Guarantee",
                parcel.get("physical_guarantee_mwmed"),
                "MWmed",
                SOURCE_CCEE_MONTHLY,
                "CCEE:PARCELA_USINA_MONTANTE_MENSAL",
                parcel.get("source_reference_month"),
                "raw",
                "Direct CCEE GARANTIA_FISICA field.",
            )

        if aneel:
            add(
                "authorized_capacity_mw",
                "Authorized Capacity",
                _kw_to_mw(aneel.get("authorized_capacity_kw")),
                "MW",
                SOURCE_ANEEL_SIGA,
                "ANEEL:siga-empreendimentos-geracao.csv",
                aneel.get("source_updated_at"),
                "derived",
                "ANEEL MdaPotenciaOutorgadaKw / 1000.",
            )
            add(
                "inspected_capacity_mw",
                "Inspected Capacity",
                _kw_to_mw(aneel.get("inspected_capacity_kw")),
                "MW",
                SOURCE_ANEEL_SIGA,
                "ANEEL:siga-empreendimentos-geracao.csv",
                aneel.get("source_updated_at"),
                "derived",
                "ANEEL MdaPotenciaFiscalizadaKw / 1000.",
            )
            add(
                "aneel_physical_guarantee_mw",
                "ANEEL Physical Guarantee",
                _kw_to_mw(aneel.get("physical_guarantee_kw")),
                "MW",
                SOURCE_ANEEL_SIGA,
                "ANEEL:siga-empreendimentos-geracao.csv",
                aneel.get("source_updated_at"),
                "derived",
                "ANEEL MdaGarantiaFisicaKw / 1000. Unit is preserved as regulatory kW converted to MW.",
            )

        if latest_monthly:
            ref = latest_monthly.get("reference_month")
            generation_mwmed = latest_monthly.get("generation_center_of_gravity_mwmed")
            add(
                "generation_center_of_gravity_mwmed",
                "Generation at Center of Gravity",
                generation_mwmed,
                "MWmed",
                SOURCE_CCEE_MONTHLY,
                "CCEE:PARCELA_USINA_MONTANTE_MENSAL",
                ref,
                "raw",
                "Direct CCEE GERACAO_CENTRO_GRAVIDADE field.",
            )
            try:
                hours = hours_in_reference_month(ref)
            except Exception:
                hours = 0
            generation_mwh = mwmed_to_mwh(generation_mwmed, hours) if hours else None
            add(
                "generation_center_of_gravity_gwh",
                "Generation at Center of Gravity",
                mwh_to_gwh(generation_mwh),
                "GWh",
                SOURCE_CCEE_MONTHLY,
                "CCEE:PARCELA_USINA_MONTANTE_MENSAL",
                ref,
                "derived",
                "GWh = MWmed * hours_in_month / 1000.",
            )
            capacity_mw = (parcel or {}).get("capacity_mw") or latest_monthly.get("capacity_mw")
            cf = capacity_factor(generation_mwh, capacity_mw, hours) if hours else None
            add(
                "capacity_factor_pct",
                "Capacity Factor",
                None if cf is None else cf * 100.0,
                "%",
                SOURCE_CCEE_MONTHLY,
                "CCEE:PARCELA_USINA_MONTANTE_MENSAL",
                ref,
                "derived",
                "Capacity factor = generated MWh / (capacity MW * hours_in_month).",
            )

        return metrics

    def get_plant_parcel_chart_data(
        self,
        *,
        entity_id: str,
        entity_type: str | None = None,
        frequency: str,
        year_month: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Query and return chart-ready historical data for selected plant/parcel."""
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            return {"error": "entity_id is required", "series": [], "periods": []}

        with self._engine().connect() as conn:
            resolved_type = entity_type or self._resolve_plant_entity_type(conn, entity_id)

            periods: list[str] = []
            series_data: dict[str, dict[str, Any]] = {}
            data_source = "unknown"
            guardrails: dict[str, Any] = {}
            hourly_read_path: dict[str, Any] | None = None

            def init_series(name: str, label: str, unit: str, axis: str, chart_type: str = "line", color: str = "") -> None:
                series_data[name] = {
                    "id": name,
                    "label": label,
                    "unit": unit,
                    "axis": axis,
                    "type": chart_type,
                    "color": color,
                    "points": [],
                    "latest": None,
                }

            if frequency == "monthly":
                data_source = "ccee_plant_parcel_monthly"
                init_series("generation_mwmed", "Generation (MWmed)", "number", "left", "line")
                init_series("generation_gwh", "Generation (GWh)", "number", "left", "line")
                init_series("capacity_mw", "Capacity (MW)", "number", "right", "line")
                init_series("physical_guarantee_mwmed", "Physical Guarantee (MWmed)", "number", "right", "line")
                init_series("capacity_factor_pct", "Capacity Factor (%)", "pct", "left", "line")

                if resolved_type == "aneel_plant":
                    sql = """
                        SELECT 
                            reference_month,
                            SUM(capacity_mw) AS capacity_mw,
                            SUM(physical_guarantee_mwmed) AS physical_guarantee_mwmed,
                            SUM(generation_center_of_gravity_mwmed) AS generation_center_of_gravity_mwmed
                        FROM ccee_plant_parcel_monthly
                        WHERE ceg = :entity_id
                        GROUP BY reference_month
                        ORDER BY reference_month ASC
                    """
                else:
                    sql = """
                        SELECT 
                            reference_month,
                            capacity_mw,
                            physical_guarantee_mwmed,
                            generation_center_of_gravity_mwmed
                        FROM ccee_plant_parcel_monthly
                        WHERE plant_parcel_code = :entity_id
                        ORDER BY reference_month ASC
                    """

                rows = conn.execute(text(sql), {"entity_id": entity_id}).mappings().all()
                for row in rows:
                    ref = row["reference_month"]
                    periods.append(ref)
                    cap = row["capacity_mw"]
                    gf = row["physical_guarantee_mwmed"]
                    gen = row["generation_center_of_gravity_mwmed"]
                    
                    try:
                        hours = hours_in_reference_month(ref)
                    except Exception:
                        hours = 0
                    gen_mwh = mwmed_to_mwh(gen, hours) if hours else None
                    gen_gwh = mwh_to_gwh(gen_mwh) if gen_mwh is not None else None
                    cf = capacity_factor(gen_mwh, cap, hours) if hours else None
                    cf_pct = cf * 100.0 if cf is not None else None

                    series_data["generation_mwmed"]["points"].append(gen)
                    series_data["generation_gwh"]["points"].append(gen_gwh)
                    series_data["capacity_mw"]["points"].append(cap)
                    series_data["physical_guarantee_mwmed"]["points"].append(gf)
                    series_data["capacity_factor_pct"]["points"].append(cf_pct)

            elif frequency in ("daily", "hourly"):
                if not year_month:
                    return {"error": "year_month is required for daily/hourly charts", "series": [], "periods": []}
                
                year_month_val = year_month.replace("/", "-")
                if len(year_month_val) == 6 and "-" not in year_month_val:
                    year_month_val = f"{year_month_val[:4]}-{year_month_val[4:]}"
                
                init_series("generation_mwh", "Generation (MWh)", "number", "left", "line")
                init_series("verified_generation_mwh", "Verified Generation ONS (MWh)", "number", "left", "line")
                init_series("verified_availability_mwh", "Verified Availability (MWh)", "number", "right", "line")
                init_series("unavailability_mwh", "Unavailability (MWh)", "number", "right", "line")
                init_series("capacity_factor_pct", "Capacity Factor (%)", "pct", "left", "line")

                if resolved_type == "aneel_plant":
                    cap_sql = "SELECT SUM(capacity_mw) FROM ccee_plant_parcels WHERE ceg = :entity_id"
                else:
                    cap_sql = "SELECT capacity_mw FROM ccee_plant_parcels WHERE plant_parcel_code = :entity_id"
                cap_mw = conn.execute(text(cap_sql), {"entity_id": entity_id}).scalar() or 0.0

                if frequency == "daily":
                    data_source = "plant_parcel_daily_generation_mart"
                    if resolved_type == "aneel_plant":
                        sql = """
                            SELECT 
                                d.reference_date,
                                SUM(d.generation_mwh) AS generation_mwh,
                                SUM(d.verified_generation_mwh) AS verified_generation_mwh,
                                SUM(d.verified_availability_mwh) AS verified_availability_mwh,
                                SUM(d.unavailability_mwh) AS unavailability_mwh
                            FROM plant_parcel_daily_generation_mart d
                            JOIN ccee_plant_parcels p ON p.plant_parcel_code = d.plant_parcel_code
                            WHERE p.ceg = :entity_id
                              AND d.reference_month = :year_month
                            GROUP BY d.reference_date
                            ORDER BY d.reference_date ASC
                        """
                    else:
                        sql = """
                            SELECT 
                                reference_date,
                                generation_mwh,
                                verified_generation_mwh,
                                verified_availability_mwh,
                                unavailability_mwh
                            FROM plant_parcel_daily_generation_mart
                            WHERE plant_parcel_code = :entity_id
                              AND reference_month = :year_month
                            ORDER BY reference_date ASC
                        """
                    rows = conn.execute(text(sql), {"entity_id": entity_id, "year_month": year_month_val}).mappings().all()
                    if not rows:
                        return {
                            "error": (
                                "Daily hourly mart has no rows for this entity/month. "
                                "Rebuild energy marts before requesting daily CCEE charts."
                            ),
                            "series": [],
                            "periods": [],
                            "frequency": frequency,
                            "entity_type": resolved_type,
                            "entity_id": entity_id,
                            "metadata": {
                                "data_source": data_source,
                                "reference_month": year_month_val,
                                "mart_status": get_plant_hourly_mart_status(conn),
                            },
                        }
                    for row in rows:
                        ref = row["reference_date"]
                        periods.append(ref)
                        gen = row["generation_mwh"]
                        vgen = row["verified_generation_mwh"]
                        vavail = row["verified_availability_mwh"]
                        unavail = row["unavailability_mwh"]

                        cf = capacity_factor(gen, cap_mw, 24)
                        cf_pct = cf * 100.0 if cf is not None else None

                        series_data["generation_mwh"]["points"].append(gen)
                        series_data["verified_generation_mwh"]["points"].append(vgen)
                        series_data["verified_availability_mwh"]["points"].append(vavail)
                        series_data["unavailability_mwh"]["points"].append(unavail)
                        series_data["capacity_factor_pct"]["points"].append(cf_pct)
                else: # hourly
                    data_source = "ccee_plant_parcel_hourly"
                    start_value = str(start_datetime or "").strip()
                    end_value = str(end_datetime or "").strip()
                    if not start_value or not end_value:
                        return {
                            "error": "Hourly drill-down requires explicit start_datetime and end_datetime.",
                            "series": [],
                            "periods": [],
                            "frequency": frequency,
                            "entity_type": resolved_type,
                            "entity_id": entity_id,
                            "metadata": {
                                "data_source": data_source,
                                "guardrails": {
                                    "requires_entity_id": True,
                                    "requires_reference_month": True,
                                    "requires_start_datetime": True,
                                    "requires_end_datetime": True,
                                    "max_window_days": 31,
                                },
                            },
                        }
                    window_days = _datetime_window_days(start_value, end_value)
                    if window_days is None or window_days < 0 or window_days > 31:
                        return {
                            "error": "Hourly drill-down date window must be valid and at most 31 days.",
                            "series": [],
                            "periods": [],
                            "frequency": frequency,
                            "entity_type": resolved_type,
                            "entity_id": entity_id,
                            "metadata": {
                                "data_source": data_source,
                                "guardrails": {
                                    "requires_entity_id": True,
                                    "requires_reference_month": True,
                                    "requires_start_datetime": True,
                                    "requires_end_datetime": True,
                                    "max_window_days": 31,
                                },
                            },
                        }
                    row_limit = max(1, min(int(limit or 2000), 5000))
                    guardrails = {
                        "requires_entity_id": True,
                        "requires_reference_month": True,
                        "requires_start_datetime": True,
                        "requires_end_datetime": True,
                        "max_window_days": 31,
                        "limit": row_limit,
                    }
                    manifest_path = _hourly_hot_cold_manifest_path(self._settings)
                    hourly_read_path = {
                        "attempted": False,
                        "selected": "raw_sqlite",
                        "fallback_reason": None,
                        "manifest_path": str(manifest_path) if manifest_path is not None else None,
                        "artifact_path": None,
                        "source_signature_ok": None,
                        "ceg_mart_attempted": resolved_type == "aneel_plant",
                        "ceg_mart_fallback_reason": None,
                    }
                    rows: Any
                    if resolved_type == "aneel_plant":
                        rows = conn.execute(
                            text(f"""
                                SELECT
                                    reference_datetime,
                                    commercialization_period,
                                    generation_mwh,
                                    verified_generation_mwh,
                                    verified_availability_mwh,
                                    unavailability_mwh
                                FROM {CEG_HOURLY_MART_NAME}
                                WHERE ceg = :entity_id
                                  AND reference_month = :year_month
                                  AND reference_datetime >= :start_datetime
                                  AND reference_datetime <= :end_datetime
                                ORDER BY reference_datetime ASC, commercialization_period ASC
                                LIMIT :limit
                            """),
                            {
                                "entity_id": entity_id,
                                "year_month": year_month_val,
                                "start_datetime": start_value,
                                "end_datetime": end_value,
                                "limit": row_limit,
                            },
                        ).mappings().all()
                        if rows:
                            data_source = CEG_HOURLY_MART_NAME
                            hourly_read_path["selected"] = CEG_HOURLY_MART_NAME
                            hourly_read_path["fallback_reason"] = None
                        else:
                            hourly_read_path["ceg_mart_fallback_reason"] = "ceg_mart_missing"
                            rows = None
                    else:
                        rows = None

                    if rows is None:
                        adapter_result = read_hourly_from_hot_cold(
                            source_db_path=Path(self._settings.paths.energy_kpi_db_path),
                            manifest_path=manifest_path,
                            request=HourlyReadRequest(
                                entity_id=entity_id,
                                entity_type=(
                                    "aneel_plant" if resolved_type == "aneel_plant" else "ccee_plant_parcel"
                                ),
                                reference_month=year_month_val,
                                start_datetime=start_value,
                                end_datetime=end_value,
                                limit=row_limit,
                            ),
                        )
                        hourly_read_path = {
                            "attempted": manifest_path is not None,
                            "selected": adapter_result.read_path or "raw_sqlite",
                            "fallback_reason": adapter_result.fallback_reason,
                            "manifest_path": adapter_result.manifest_path
                            or (str(manifest_path) if manifest_path is not None else None),
                            "artifact_path": adapter_result.artifact_path,
                            "source_signature_ok": adapter_result.source_signature_ok,
                            "ceg_mart_attempted": resolved_type == "aneel_plant",
                            "ceg_mart_fallback_reason": hourly_read_path.get("ceg_mart_fallback_reason"),
                        }
                        if adapter_result.ok:
                            rows = adapter_result.rows
                            data_source = adapter_result.read_path or data_source
                        else:
                            rows = None

                    if rows is None:
                        data_source = "ccee_plant_parcel_hourly"
                        if resolved_type == "aneel_plant":
                            sql = """
                                SELECT
                                    h.reference_datetime,
                                    h.commercialization_period,
                                    SUM(h.generation_center_of_gravity_mwh) AS generation_mwh,
                                    SUM(h.verified_generation_ons_mwh) AS verified_generation_mwh,
                                    SUM(h.verified_availability_mwh) AS verified_availability_mwh,
                                    SUM(h.unavailability_mwh) AS unavailability_mwh
                                FROM ccee_plant_parcel_hourly h
                                JOIN ccee_plant_parcels p ON p.plant_parcel_code = h.plant_parcel_code
                                WHERE p.ceg = :entity_id
                                  AND h.reference_month = :year_month
                                  AND h.reference_datetime >= :start_datetime
                                  AND h.reference_datetime <= :end_datetime
                                GROUP BY h.reference_datetime, h.commercialization_period
                                ORDER BY h.reference_datetime ASC, h.commercialization_period ASC
                                LIMIT :limit
                            """
                        else:
                            sql = """
                                SELECT
                                    reference_datetime,
                                    commercialization_period,
                                    generation_center_of_gravity_mwh AS generation_mwh,
                                    verified_generation_ons_mwh AS verified_generation_mwh,
                                    verified_availability_mwh AS verified_availability_mwh,
                                    unavailability_mwh AS unavailability_mwh
                                FROM ccee_plant_parcel_hourly
                                WHERE plant_parcel_code = :entity_id
                                  AND reference_month = :year_month
                                  AND reference_datetime >= :start_datetime
                                  AND reference_datetime <= :end_datetime
                                ORDER BY reference_datetime ASC, commercialization_period ASC
                                LIMIT :limit
                            """
                        rows = conn.execute(
                            text(sql),
                            {
                                "entity_id": entity_id,
                                "year_month": year_month_val,
                                "start_datetime": start_value,
                                "end_datetime": end_value,
                                "limit": row_limit,
                            },
                        ).mappings().all()
                    for row in rows:
                        dt = row["reference_datetime"]
                        p = row["commercialization_period"]
                        periods.append(f"{dt[11:13]}h" if len(dt) >= 16 else f"p{p}")
                        gen = row["generation_mwh"]
                        vgen = row["verified_generation_mwh"]
                        vavail = row["verified_availability_mwh"]
                        unavail = row["unavailability_mwh"]

                        cf = capacity_factor(gen, cap_mw, 1)
                        cf_pct = cf * 100.0 if cf is not None else None

                        series_data["generation_mwh"]["points"].append(gen)
                        series_data["verified_generation_mwh"]["points"].append(vgen)
                        series_data["verified_availability_mwh"]["points"].append(vavail)
                        series_data["unavailability_mwh"]["points"].append(unavail)
                        series_data["capacity_factor_pct"]["points"].append(cf_pct)

            for s in series_data.values():
                valid = [v for v in s["points"] if v is not None]
                s["latest"] = valid[-1] if valid else None

            metadata = {
                "data_source": data_source,
                "guardrails": guardrails,
                "mart_status": get_plant_hourly_mart_status(conn),
            }
            if hourly_read_path is not None:
                metadata["hourly_read_path"] = hourly_read_path

            return {
                "series": list(series_data.values()),
                "periods": periods,
                "frequency": frequency,
                "entity_type": resolved_type,
                "entity_id": entity_id,
                "metadata": metadata,
            }



def _kw_to_mw(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return None


def _datetime_window_days(start_datetime: str, end_datetime: str) -> int | None:
    try:
        start = datetime.fromisoformat(str(start_datetime).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(end_datetime).replace("Z", "+00:00"))
    except Exception:
        return None
    return (end.date() - start.date()).days + 1


def _normalize_search_text(value: Any) -> str:
    no_accents = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", no_accents.strip().lower())


def _install_sqlite_functions(conn) -> None:
    raw_connection = getattr(conn.connection, "driver_connection", None)
    if raw_connection is None:
        raw_connection = getattr(conn.connection, "connection", None)
    if raw_connection is not None:
        raw_connection.create_function("cvm_norm", 1, _normalize_search_text)
