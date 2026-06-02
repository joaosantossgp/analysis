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
    SOURCE_ANEEL_SIGA,
    SOURCE_CCEE_HOURLY,
    SOURCE_CCEE_MONTHLY,
    seed_plant_sources,
)
from src.energy_kpi.schema import get_energy_kpi_engine
from src.energy_kpi.sin_catalog import SIN_KPI_CATALOG
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
        limit_sql = ""
        if limit is not None and int(limit) > 0:
            limit_sql = "LIMIT :limit"
            params["limit"] = int(limit)

        sql = f"""
            SELECT v.kpi_id, v.subsystem_code,
                   COALESCE(d.display_name, v.subsystem_code) AS subsystem_name,
                   v.reference_datetime, v.normalized_value, v.unit, v.source,
                   v.source_dataset, v.source_field, v.data_quality_status,
                   v.snapshot_id
            FROM subsystem_kpi_values v
            LEFT JOIN subsystem_dimension d ON d.subsystem_code = v.subsystem_code
            {where}
            ORDER BY v.reference_datetime, v.subsystem_code, v.kpi_id
            {limit_sql}
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

    def get_plant_parcel_source_statuses(self) -> dict[str, Any]:
        """Return local cache status for ANEEL SIGA and CCEE plant datasets."""
        with self._engine().begin() as conn:
            seed_plant_sources(conn)
            source_rows = conn.execute(text("""
                SELECT source_id, source_name, dataset_name, provider, official_url,
                       refresh_frequency, granularity, description, known_caveats
                FROM energy_sources
                WHERE source_id IN (
                    'ccee_plant_parcel_monthly',
                    'ccee_plant_generation_hourly',
                    'aneel_siga_plants'
                )
                ORDER BY
                    CASE source_id
                        WHEN 'aneel_siga_plants' THEN 1
                        WHEN 'ccee_plant_parcel_monthly' THEN 2
                        WHEN 'ccee_plant_generation_hourly' THEN 3
                        ELSE 9
                    END
            """)).mappings().all()
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
            counts = {
                SOURCE_ANEEL_SIGA: {
                    "records": int(conn.execute(text("SELECT COUNT(*) FROM aneel_siga_plants")).scalar() or 0),
                    "latest_reference": conn.execute(text("SELECT MAX(source_updated_at) FROM aneel_siga_plants")).scalar(),
                },
                SOURCE_CCEE_MONTHLY: {
                    "records": int(conn.execute(text("SELECT COUNT(*) FROM ccee_plant_parcel_monthly")).scalar() or 0),
                    "latest_reference": conn.execute(text("SELECT MAX(reference_month) FROM ccee_plant_parcel_monthly")).scalar(),
                },
                SOURCE_CCEE_HOURLY: {
                    "records": int(conn.execute(text("SELECT COUNT(*) FROM ccee_plant_parcel_hourly")).scalar() or 0),
                    "latest_reference": conn.execute(text("SELECT MAX(reference_datetime) FROM ccee_plant_parcel_hourly")).scalar(),
                },
            }

        statuses: list[dict[str, Any]] = []
        for row in source_rows:
            source_id = str(row["source_id"])
            log_row = latest_logs.get(source_id, {})
            count_info = counts.get(source_id, {"records": 0, "latest_reference": None})
            status = self._plant_source_cache_status(
                latest_status=log_row.get("status"),
                local_records=int(count_info["records"] or 0),
                latest_reference=count_info.get("latest_reference"),
                source_id=source_id,
            )
            statuses.append({
                **dict(row),
                "local_records_count": int(count_info["records"] or 0),
                "latest_reference": count_info.get("latest_reference"),
                "last_refresh_at": log_row.get("finished_at") or log_row.get("started_at"),
                "last_status": log_row.get("status"),
                "last_error": log_row.get("error_message"),
                "refresh_id": log_row.get("refresh_id"),
                "cache_status": status,
            })
        return {"source_statuses": statuses, "count": len(statuses)}

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
            params["search"] = f"%{search.strip().lower()}%"
            conditions.append(
                "(LOWER(COALESCE(plant_name, '')) LIKE :search "
                "OR LOWER(COALESCE(plant_parcel_code, '')) LIKE :search "
                "OR LOWER(COALESCE(plant_parcel_acronym, '')) LIKE :search "
                "OR LOWER(COALESCE(ceg, '')) LIKE :search "
                "OR LOWER(COALESCE(agent_name, '')) LIKE :search)"
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
            SELECT *
            FROM entities
            {where}
            ORDER BY COALESCE(plant_name, entity_id), entity_type, entity_id
            LIMIT :limit OFFSET :offset
        """
        count_sql = f"""
            {self._plant_entities_cte()}
            SELECT COUNT(*) FROM entities {where}
        """
        with self._engine().begin() as conn:
            seed_plant_sources(conn)
            rows = [dict(row) for row in conn.execute(text(sql), params).mappings().all()]
            total = int(conn.execute(text(count_sql), params).scalar() or 0)

        facets = self._plant_facets(rows)
        return {
            "records": rows,
            "count": len(rows),
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

        with self._engine().begin() as conn:
            seed_plant_sources(conn)
            resolved_type = entity_type or self._resolve_plant_entity_type(conn, entity_id)
            parcel = None
            aneel = None
            parcels: list[dict[str, Any]] = []
            monthly: list[dict[str, Any]] = []
            hourly: list[dict[str, Any]] = []

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
                    FROM ccee_plant_parcel_hourly
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
            "metadata": {
                "caveats": [
                    "CCEE plant parcel is not always equivalent to an ANEEL CEG plant or an ONS plant/group.",
                    "A CEG can map to multiple CCEE plant parcels.",
                    "Source reference date and local refresh timestamp are different and both are shown where available.",
                    "Load and demand remain system/subsystem context metrics, not plant-parcel metrics.",
                    "Energia firme, energia assegurada, and gross/net generation are not inferred without an explicit source methodology.",
                ],
                "latest_refresh_by_source": latest_logs,
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
    def _plant_source_cache_status(
        *,
        latest_status: str | None,
        local_records: int,
        latest_reference: str | None,
        source_id: str,
    ) -> str:
        if latest_status == "error":
            return "failed"
        if local_records <= 0:
            return "missing"
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


def _kw_to_mw(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return None
