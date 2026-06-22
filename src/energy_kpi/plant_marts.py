"""Rebuildable query marts for CCEE plant-parcel hourly reads."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text

MART_BUILD_VERSION = "plant_hourly_marts_v2"
DAILY_MART_NAME = "plant_parcel_daily_generation_mart"
HOURLY_PREVIEW_MART_NAME = "plant_parcel_hourly_preview_mart"
CEG_HOURLY_MART_NAME = "plant_ceg_hourly_generation_mart"
SOURCE_SUBMARKET_MART_NAME = "plant_parcel_source_submarket_monthly_mart"
SOURCE_TABLE_NAME = "ccee_plant_parcel_hourly"
PLANT_PARCELS_TABLE_NAME = "ccee_plant_parcels"

logger = logging.getLogger(__name__)


def normalize_reference_months(reference_months: list[str] | tuple[str, ...] | set[str] | None) -> list[str] | None:
    if not reference_months:
        return None
    normalized: list[str] = []
    for value in reference_months:
        text_value = str(value or "").strip().replace("/", "-")
        if not text_value:
            continue
        if len(text_value) == 6 and "-" not in text_value:
            text_value = f"{text_value[:4]}-{text_value[4:]}"
        normalized.append(text_value)
    return sorted(set(normalized)) or None


def rebuild_plant_hourly_marts(
    conn,
    *,
    reference_months: list[str] | tuple[str, ...] | set[str] | None = None,
    rebuild_daily: bool = True,
    rebuild_preview: bool = True,
    rebuild_ceg_hourly: bool = True,
    rebuild_source_submarket: bool = True,
) -> dict[str, Any]:
    """Rebuild plant-parcel marts from local hourly facts.

    The caller owns the transaction. Month-scoped rebuilds are preferred after
    hourly imports; full rebuilds are available for explicit maintenance.
    """
    months = normalize_reference_months(reference_months)
    started = time.perf_counter()
    rebuilt_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result: dict[str, Any] = {
        "build_version": MART_BUILD_VERSION,
        "rebuilt_at": rebuilt_at,
        "reference_months": months,
        "daily_rows": None,
        "preview_rows": None,
        "ceg_hourly_rows": None,
        "source_submarket_rows": None,
        "elapsed_ms": None,
    }

    try:
        source_stats = _source_stats(conn, months)
        if rebuild_daily:
            result["daily_rows"] = _rebuild_daily_mart(conn, months, rebuilt_at)
            _record_mart_build(
                conn,
                mart_name=DAILY_MART_NAME,
                rebuilt_at=rebuilt_at,
                row_count=int(result["daily_rows"] or 0),
                source_stats=source_stats,
                status="success",
                metadata={"reference_months": months, "scope": "monthly" if months else "full"},
            )
        if rebuild_preview:
            result["preview_rows"] = _rebuild_hourly_preview_mart(conn, months, rebuilt_at)
            _record_mart_build(
                conn,
                mart_name=HOURLY_PREVIEW_MART_NAME,
                rebuilt_at=rebuilt_at,
                row_count=int(result["preview_rows"] or 0),
                source_stats=source_stats,
                status="success",
                metadata={"reference_months": months, "scope": "monthly" if months else "full"},
            )
        if rebuild_ceg_hourly:
            result["ceg_hourly_rows"] = _rebuild_ceg_hourly_mart(conn, months, rebuilt_at)
            _record_mart_build(
                conn,
                mart_name=CEG_HOURLY_MART_NAME,
                rebuilt_at=rebuilt_at,
                row_count=int(result["ceg_hourly_rows"] or 0),
                source_stats=source_stats,
                status="success",
                metadata={"reference_months": months, "scope": "monthly" if months else "full"},
            )
        if rebuild_source_submarket:
            result["source_submarket_rows"] = _rebuild_source_submarket_mart(conn, months, rebuilt_at)
            _record_mart_build(
                conn,
                mart_name=SOURCE_SUBMARKET_MART_NAME,
                rebuilt_at=rebuilt_at,
                row_count=int(result["source_submarket_rows"] or 0),
                source_stats=source_stats,
                status="success",
                metadata={"reference_months": months, "scope": "monthly" if months else "full"},
            )
    except Exception as exc:
        logger.exception("Plant hourly mart rebuild failed")
        _record_mart_build(
            conn,
            mart_name="plant_hourly_marts",
            rebuilt_at=rebuilt_at,
            row_count=0,
            source_stats={},
            status="failed",
            error_message=str(exc),
            metadata={"reference_months": months},
        )
        raise
    finally:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)

    return result


def get_plant_hourly_mart_status(conn) -> dict[str, Any]:
    rows = conn.execute(text("""
        SELECT mart_name, build_version, rebuilt_at, source_table,
               source_row_estimate, source_max_rowid, source_latest_reference,
               period_start, period_end, row_count, status, error_message,
               metadata_json
        FROM energy_mart_builds
        WHERE mart_name IN (:daily, :preview, :ceg_hourly, :source_submarket)
        ORDER BY mart_name
    """), {
        "daily": DAILY_MART_NAME,
        "preview": HOURLY_PREVIEW_MART_NAME,
        "ceg_hourly": CEG_HOURLY_MART_NAME,
        "source_submarket": SOURCE_SUBMARKET_MART_NAME,
    }).mappings().all()
    return {str(row["mart_name"]): dict(row) for row in rows}


def _rebuild_daily_mart(conn, months: list[str] | None, rebuilt_at: str) -> int:
    if months:
        conn.execute(
            text(f"DELETE FROM {DAILY_MART_NAME} WHERE reference_month IN :reference_months").bindparams(
                bindparam("reference_months", expanding=True)
            ),
            {"reference_months": months},
        )
        return _insert_daily_mart_months(conn, months, rebuilt_at)

    conn.execute(text(f"DELETE FROM {DAILY_MART_NAME}"))
    total_rows = 0
    for reference_month in _source_reference_months(conn):
        logger.info("Rebuilding %s for reference_month=%s", DAILY_MART_NAME, reference_month)
        total_rows += _insert_daily_mart_months(conn, [reference_month], rebuilt_at)
    return total_rows


def _insert_daily_mart_months(conn, months: list[str], rebuilt_at: str) -> int:
    stmt = text(f"""
        INSERT INTO {DAILY_MART_NAME} (
            plant_parcel_code, reference_date, reference_month,
            generation_mwh, verified_generation_mwh,
            verified_availability_mwh, unavailability_mwh,
            hourly_observations, first_reference_datetime, last_reference_datetime,
            source_dataset, first_snapshot_id, last_snapshot_id, rebuilt_at,
            build_version
        )
        SELECT
            plant_parcel_code,
            date(reference_datetime) AS reference_date,
            reference_month,
            SUM(generation_center_of_gravity_mwh) AS generation_mwh,
            SUM(verified_generation_ons_mwh) AS verified_generation_mwh,
            SUM(verified_availability_mwh) AS verified_availability_mwh,
            SUM(unavailability_mwh) AS unavailability_mwh,
            COUNT(*) AS hourly_observations,
            MIN(reference_datetime) AS first_reference_datetime,
            MAX(reference_datetime) AS last_reference_datetime,
            MIN(source_dataset) AS source_dataset,
            MIN(snapshot_id) AS first_snapshot_id,
            MAX(snapshot_id) AS last_snapshot_id,
            :rebuilt_at AS rebuilt_at,
            :build_version AS build_version
        FROM {SOURCE_TABLE_NAME}
        WHERE reference_month IN :reference_months
        GROUP BY plant_parcel_code, reference_date, reference_month
    """).bindparams(bindparam("reference_months", expanding=True))
    conn.execute(
        stmt,
        {
            "reference_months": months,
            "rebuilt_at": rebuilt_at,
            "build_version": MART_BUILD_VERSION,
        },
    )
    return _scoped_mart_count(conn, DAILY_MART_NAME, months)


def _rebuild_hourly_preview_mart(conn, months: list[str] | None, rebuilt_at: str) -> int:
    conn.execute(text("""
        CREATE TEMP TABLE IF NOT EXISTS temp_plant_mart_scope_parcels (
            plant_parcel_code TEXT PRIMARY KEY
        )
    """))
    conn.execute(text("DELETE FROM temp_plant_mart_scope_parcels"))
    if months:
        conn.execute(
            text(f"""
                INSERT OR IGNORE INTO temp_plant_mart_scope_parcels(plant_parcel_code)
                SELECT DISTINCT plant_parcel_code
                FROM {SOURCE_TABLE_NAME}
                WHERE reference_month IN :reference_months
            """).bindparams(bindparam("reference_months", expanding=True)),
            {"reference_months": months},
        )
    else:
        conn.execute(text(f"""
            INSERT OR IGNORE INTO temp_plant_mart_scope_parcels(plant_parcel_code)
            SELECT DISTINCT plant_parcel_code
            FROM {SOURCE_TABLE_NAME}
        """))

    scoped_codes = int(conn.execute(text("SELECT COUNT(*) FROM temp_plant_mart_scope_parcels")).scalar() or 0)
    if scoped_codes <= 0:
        return 0

    conn.execute(text(f"""
        DELETE FROM {HOURLY_PREVIEW_MART_NAME}
        WHERE plant_parcel_code IN (
            SELECT plant_parcel_code FROM temp_plant_mart_scope_parcels
        )
    """))

    conn.execute(text("""
        CREATE TEMP TABLE IF NOT EXISTS temp_plant_mart_preview_rowids (
            rowid INTEGER PRIMARY KEY
        )
    """))
    conn.execute(text("DELETE FROM temp_plant_mart_preview_rowids"))

    scoped_parcels = conn.execute(text("""
        SELECT plant_parcel_code
        FROM temp_plant_mart_scope_parcels
        ORDER BY plant_parcel_code
    """)).scalars().all()
    preview_rowid_stmt = text(f"""
        INSERT OR IGNORE INTO temp_plant_mart_preview_rowids(rowid)
        SELECT rowid
        FROM {SOURCE_TABLE_NAME}
        WHERE plant_parcel_code = :plant_parcel_code
        ORDER BY reference_datetime DESC
        LIMIT 48
    """)
    for plant_parcel_code in scoped_parcels:
        conn.execute(preview_rowid_stmt, {"plant_parcel_code": plant_parcel_code})

    conn.execute(
        text(f"""
            INSERT INTO {HOURLY_PREVIEW_MART_NAME} (
                plant_parcel_code, reference_datetime, reference_month,
                commercialization_period, generation_center_of_gravity_mwh,
                verified_generation_ons_mwh, verified_availability_mwh,
                unavailability_mwh, source_dataset, snapshot_id, rebuilt_at,
                build_version
            )
            SELECT
                h.plant_parcel_code, h.reference_datetime, h.reference_month,
                h.commercialization_period, h.generation_center_of_gravity_mwh,
                h.verified_generation_ons_mwh, h.verified_availability_mwh,
                h.unavailability_mwh, h.source_dataset, h.snapshot_id,
                :rebuilt_at AS rebuilt_at, :build_version AS build_version
            FROM {SOURCE_TABLE_NAME} h
            JOIN temp_plant_mart_preview_rowids preview
              ON preview.rowid = h.rowid
        """),
        {"rebuilt_at": rebuilt_at, "build_version": MART_BUILD_VERSION},
    )
    return _scoped_preview_count(conn)


def _rebuild_ceg_hourly_mart(conn, months: list[str] | None, rebuilt_at: str) -> int:
    if months:
        conn.execute(
            text(f"DELETE FROM {CEG_HOURLY_MART_NAME} WHERE reference_month IN :reference_months").bindparams(
                bindparam("reference_months", expanding=True)
            ),
            {"reference_months": months},
        )
        return _insert_ceg_hourly_mart_months(conn, months, rebuilt_at)

    conn.execute(text(f"DELETE FROM {CEG_HOURLY_MART_NAME}"))
    total_rows = 0
    for reference_month in _source_reference_months(conn):
        logger.info("Rebuilding %s for reference_month=%s", CEG_HOURLY_MART_NAME, reference_month)
        total_rows += _insert_ceg_hourly_mart_months(conn, [reference_month], rebuilt_at)
    return total_rows


def _insert_ceg_hourly_mart_months(conn, months: list[str], rebuilt_at: str) -> int:
    stmt = text(f"""
        INSERT INTO {CEG_HOURLY_MART_NAME} (
            ceg, reference_datetime, reference_month, commercialization_period,
            generation_mwh, verified_generation_mwh, verified_availability_mwh,
            unavailability_mwh, plant_parcel_count, source_dataset,
            first_snapshot_id, last_snapshot_id, rebuilt_at, build_version
        )
        SELECT
            p.ceg AS ceg,
            h.reference_datetime AS reference_datetime,
            h.reference_month AS reference_month,
            h.commercialization_period AS commercialization_period,
            SUM(h.generation_center_of_gravity_mwh) AS generation_mwh,
            SUM(h.verified_generation_ons_mwh) AS verified_generation_mwh,
            SUM(h.verified_availability_mwh) AS verified_availability_mwh,
            SUM(h.unavailability_mwh) AS unavailability_mwh,
            COUNT(DISTINCT h.plant_parcel_code) AS plant_parcel_count,
            MIN(h.source_dataset) AS source_dataset,
            MIN(h.snapshot_id) AS first_snapshot_id,
            MAX(h.snapshot_id) AS last_snapshot_id,
            :rebuilt_at AS rebuilt_at,
            :build_version AS build_version
        FROM {SOURCE_TABLE_NAME} h
        JOIN {PLANT_PARCELS_TABLE_NAME} p ON p.plant_parcel_code = h.plant_parcel_code
        WHERE h.reference_month IN :reference_months
          AND p.ceg IS NOT NULL
          AND TRIM(p.ceg) <> ''
        GROUP BY p.ceg, h.reference_month, h.reference_datetime, h.commercialization_period
    """).bindparams(bindparam("reference_months", expanding=True))
    conn.execute(
        stmt,
        {
            "reference_months": months,
            "rebuilt_at": rebuilt_at,
            "build_version": MART_BUILD_VERSION,
        },
    )
    return _scoped_mart_count(conn, CEG_HOURLY_MART_NAME, months)


def _rebuild_source_submarket_mart(conn, months: list[str] | None, rebuilt_at: str) -> int:
    if months:
        conn.execute(
            text(f"DELETE FROM {SOURCE_SUBMARKET_MART_NAME} WHERE reference_month IN :reference_months").bindparams(
                bindparam("reference_months", expanding=True)
            ),
            {"reference_months": months},
        )
        return _insert_source_submarket_mart_months(conn, months, rebuilt_at)

    conn.execute(text(f"DELETE FROM {SOURCE_SUBMARKET_MART_NAME}"))
    total_rows = 0
    for reference_month in _source_reference_months(conn):
        logger.info("Rebuilding %s for reference_month=%s", SOURCE_SUBMARKET_MART_NAME, reference_month)
        total_rows += _insert_source_submarket_mart_months(conn, [reference_month], rebuilt_at)
    return total_rows


def _insert_source_submarket_mart_months(conn, months: list[str], rebuilt_at: str) -> int:
    stmt = text(f"""
        INSERT INTO {SOURCE_SUBMARKET_MART_NAME} (
            reference_month, generation_source, submarket,
            plant_parcel_count, hourly_observations, generation_mwh,
            verified_generation_mwh, first_reference_datetime, last_reference_datetime,
            source_dataset, first_snapshot_id, last_snapshot_id, rebuilt_at,
            build_version
        )
        SELECT
            reference_month,
            COALESCE(NULLIF(TRIM(generation_source), ''), '(unknown)') AS generation_source,
            COALESCE(NULLIF(TRIM(submarket), ''), '(unknown)') AS submarket,
            COUNT(DISTINCT plant_parcel_code) AS plant_parcel_count,
            COUNT(*) AS hourly_observations,
            SUM(generation_center_of_gravity_mwh) AS generation_mwh,
            SUM(verified_generation_ons_mwh) AS verified_generation_mwh,
            MIN(reference_datetime) AS first_reference_datetime,
            MAX(reference_datetime) AS last_reference_datetime,
            MIN(source_dataset) AS source_dataset,
            MIN(snapshot_id) AS first_snapshot_id,
            MAX(snapshot_id) AS last_snapshot_id,
            :rebuilt_at AS rebuilt_at,
            :build_version AS build_version
        FROM {SOURCE_TABLE_NAME}
        WHERE reference_month IN :reference_months
        GROUP BY reference_month,
                 COALESCE(NULLIF(TRIM(generation_source), ''), '(unknown)'),
                 COALESCE(NULLIF(TRIM(submarket), ''), '(unknown)')
    """).bindparams(bindparam("reference_months", expanding=True))
    conn.execute(
        stmt,
        {
            "reference_months": months,
            "rebuilt_at": rebuilt_at,
            "build_version": MART_BUILD_VERSION,
        },
    )
    return _scoped_mart_count(conn, SOURCE_SUBMARKET_MART_NAME, months)


def _scoped_mart_count(conn, table_name: str, months: list[str] | None) -> int:
    if months:
        return int(
            conn.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE reference_month IN :reference_months").bindparams(
                    bindparam("reference_months", expanding=True)
                ),
                {"reference_months": months},
            ).scalar()
            or 0
        )
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)


def _source_reference_months(conn) -> list[str]:
    rows = conn.execute(text(f"""
        SELECT DISTINCT reference_month
        FROM {SOURCE_TABLE_NAME}
        WHERE reference_month IS NOT NULL
        ORDER BY reference_month
    """)).scalars().all()
    return [str(row) for row in rows]


def _scoped_preview_count(conn) -> int:
    return int(conn.execute(text(f"""
        SELECT COUNT(*)
        FROM {HOURLY_PREVIEW_MART_NAME}
        WHERE plant_parcel_code IN (
            SELECT plant_parcel_code FROM temp_plant_mart_scope_parcels
        )
    """)).scalar() or 0)


def _source_stats(conn, months: list[str] | None) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    try:
        stats["source_max_rowid"] = int(conn.execute(text(f"SELECT MAX(rowid) FROM {SOURCE_TABLE_NAME}")).scalar() or 0)
        stats["source_row_estimate"] = stats["source_max_rowid"]
        stats["source_latest_reference"] = conn.execute(text(f"SELECT MAX(reference_datetime) FROM {SOURCE_TABLE_NAME}")).scalar()
    except Exception:
        logger.debug("could not collect source stats for plant hourly marts", exc_info=True)
    if months:
        stats["period_start"] = min(months)
        stats["period_end"] = max(months)
    else:
        try:
            stats["period_start"] = conn.execute(text(f"SELECT MIN(reference_month) FROM {SOURCE_TABLE_NAME}")).scalar()
            stats["period_end"] = conn.execute(text(f"SELECT MAX(reference_month) FROM {SOURCE_TABLE_NAME}")).scalar()
        except Exception:
            logger.debug("could not collect period stats for plant hourly marts", exc_info=True)
    return stats


def _record_mart_build(
    conn,
    *,
    mart_name: str,
    rebuilt_at: str,
    row_count: int,
    source_stats: dict[str, Any],
    status: str,
    error_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        text("""
            INSERT INTO energy_mart_builds (
                mart_name, build_version, rebuilt_at, source_table,
                source_row_estimate, source_max_rowid, source_latest_reference,
                period_start, period_end, row_count, status, error_message,
                metadata_json
            )
            VALUES (
                :mart_name, :build_version, :rebuilt_at, :source_table,
                :source_row_estimate, :source_max_rowid, :source_latest_reference,
                :period_start, :period_end, :row_count, :status, :error_message,
                :metadata_json
            )
            ON CONFLICT(mart_name) DO UPDATE SET
                build_version = excluded.build_version,
                rebuilt_at = excluded.rebuilt_at,
                source_table = excluded.source_table,
                source_row_estimate = excluded.source_row_estimate,
                source_max_rowid = excluded.source_max_rowid,
                source_latest_reference = excluded.source_latest_reference,
                period_start = excluded.period_start,
                period_end = excluded.period_end,
                row_count = excluded.row_count,
                status = excluded.status,
                error_message = excluded.error_message,
                metadata_json = excluded.metadata_json
        """),
        {
            "mart_name": mart_name,
            "build_version": MART_BUILD_VERSION,
            "rebuilt_at": rebuilt_at,
            "source_table": SOURCE_TABLE_NAME,
            "source_row_estimate": source_stats.get("source_row_estimate"),
            "source_max_rowid": source_stats.get("source_max_rowid"),
            "source_latest_reference": source_stats.get("source_latest_reference"),
            "period_start": source_stats.get("period_start"),
            "period_end": source_stats.get("period_end"),
            "row_count": row_count,
            "status": status,
            "error_message": error_message,
            "metadata_json": json.dumps(metadata or {}, sort_keys=True),
        },
    )
