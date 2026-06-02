"""User-triggered refresh job for plant and plant-parcel indicators."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import text

from src.energy_kpi.plant_parcel_ingest import (
    PLANT_SOURCES,
    SOURCE_ANEEL_SIGA,
    SOURCE_CCEE_HOURLY,
    SOURCE_CCEE_MONTHLY,
    fetch_aneel_siga_snapshot,
    fetch_ccee_hourly_snapshot,
    fetch_ccee_monthly_snapshot,
    parse_aneel_siga,
    parse_ccee_hourly,
    parse_ccee_monthly,
    persist_plant_snapshot_record,
    seed_plant_sources,
    upsert_aneel_siga_plants,
    upsert_ccee_hourly,
    upsert_ccee_monthly,
)
from src.energy_kpi.schema import get_energy_kpi_engine
from src.settings import AppSettings

logger = logging.getLogger(__name__)

StageCallback = Callable[[str, str], None]


class PlantParcelRefreshJob:
    """Refresh one plant/plant-parcel source.

    The job intentionally refreshes exactly one selected source/period. It never
    downloads all historical hourly data.
    """

    def __init__(
        self,
        settings: AppSettings,
        stage_callback: StageCallback | None = None,
    ) -> None:
        self.settings = settings
        self._stage_cb = stage_callback or (lambda stage, message: None)
        self._refresh_id = str(uuid.uuid4())

    def _stage(self, stage: str, message: str = "") -> None:
        logger.info("[%s] %s %s", self._refresh_id[:8], stage, message)
        self._stage_cb(stage, message)

    def run(
        self,
        *,
        source_id: str,
        triggered_by: str = "user",
        year: int | None = None,
        year_month: str | None = None,
        use_daily_aneel: bool = False,
    ) -> dict:
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        engine = get_energy_kpi_engine(self.settings)
        selected_year = int(year or datetime.now(timezone.utc).year)
        requested_period = _requested_period(
            source_id=source_id,
            year=selected_year,
            year_month=year_month,
            use_daily_aneel=use_daily_aneel,
        )
        source_meta = _source_meta(source_id)
        dataset_name = source_meta.get("dataset_name")
        period_start: str | None = None
        period_end: str | None = None

        with engine.begin() as conn:
            seed_plant_sources(conn)
            conn.execute(
                text("""
                    INSERT INTO energy_source_refresh_log
                        (refresh_id, source_id, requested_by, started_at, status,
                         requested_period, dataset_name)
                    VALUES
                        (:refresh_id, :source_id, :requested_by, :started_at, 'running',
                         :requested_period, :dataset_name)
                """),
                {
                    "refresh_id": self._refresh_id,
                    "source_id": source_id,
                    "requested_by": triggered_by,
                    "started_at": started_at,
                    "requested_period": requested_period,
                    "dataset_name": dataset_name,
                },
            )

        rows_read = 0
        rows_inserted = 0
        rows_updated = 0
        source_rows = 0
        parsed_rows = 0
        normalized_rows = 0
        rows_skipped = 0
        downloaded_bytes = None
        local_file_path = None
        checksum = None
        source_url = None
        status = "success"
        error = None
        warning = None
        snapshot_date = None
        detected_encoding = None

        try:
            if source_id == SOURCE_CCEE_MONTHLY:
                self._stage("fetch", f"CCEE monthly plant parcels {selected_year}")
                snapshot = fetch_ccee_monthly_snapshot(self.settings.paths, selected_year)
                frame = parse_ccee_monthly(snapshot)
                with engine.begin() as conn:
                    persist_plant_snapshot_record(conn, snapshot)
                    rows_inserted = upsert_ccee_monthly(conn, frame)
                rows_read = int(len(frame))
                period_start = snapshot.period_start
                period_end = snapshot.period_end
            elif source_id == SOURCE_CCEE_HOURLY:
                if not year_month:
                    raise ValueError("year_month is required for CCEE hourly refresh")
                self._stage("fetch", f"CCEE hourly plant generation {year_month}")
                snapshot = fetch_ccee_hourly_snapshot(self.settings.paths, year_month)
                frame = parse_ccee_hourly(snapshot)
                with engine.begin() as conn:
                    persist_plant_snapshot_record(conn, snapshot)
                    rows_inserted = upsert_ccee_hourly(conn, frame)
                rows_read = int(len(frame))
                period_start = snapshot.period_start
                period_end = snapshot.period_end
            elif source_id == SOURCE_ANEEL_SIGA:
                self._stage("fetch", "ANEEL SIGA plant registry")
                snapshot = fetch_aneel_siga_snapshot(self.settings.paths, daily=use_daily_aneel)
                frame = parse_aneel_siga(snapshot)
                with engine.begin() as conn:
                    persist_plant_snapshot_record(conn, snapshot)
                    rows_inserted = upsert_aneel_siga_plants(conn, frame)
                rows_read = int(len(frame))
            else:
                raise ValueError(f"unsupported plant source_id: {source_id}")

            local_file_path = str(snapshot.file_path)
            checksum = snapshot.sha256
            snapshot_date = snapshot.fetched_at
            source_url = snapshot.source_url
            downloaded_bytes = int(snapshot.downloaded_bytes or 0)
            source_rows = int(snapshot.row_count or frame.attrs.get("source_row_count") or 0)
            parsed_rows = int(frame.attrs.get("parsed_rows", len(frame)))
            normalized_rows = int(frame.attrs.get("normalized_rows", len(frame)))
            rows_read = parsed_rows
            rows_skipped = max(source_rows - normalized_rows, 0)
            detected_encoding = frame.attrs.get("detected_encoding")
            if rows_inserted <= 0:
                status = "warning"
                warning = _zero_row_warning(
                    source_id=source_id,
                    requested_period=requested_period,
                    source_rows=source_rows,
                    parsed_rows=parsed_rows,
                    normalized_rows=normalized_rows,
                )
        except Exception as exc:
            status = "failed"
            error = str(exc)
            logger.warning("Plant parcel refresh failed for %s: %s", source_id, exc)

        finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE energy_source_refresh_log
                    SET finished_at=:finished_at,
                        status=:status,
                        period_start=:period_start,
                        period_end=:period_end,
                        rows_downloaded=:rows_read,
                        rows_inserted=:rows_inserted,
                        rows_updated=:rows_updated,
                        error_message=:error,
                        warning_message=:warning,
                        local_file_path=:local_file_path,
                        checksum=:checksum,
                        source_snapshot_date=:source_snapshot_date,
                        requested_period=:requested_period,
                        dataset_name=:dataset_name,
                        source_url=:source_url,
                        downloaded_bytes=:downloaded_bytes,
                        source_rows=:source_rows,
                        parsed_rows=:parsed_rows,
                        normalized_rows=:normalized_rows,
                        rows_skipped=:rows_skipped,
                        detected_encoding=:detected_encoding
                    WHERE refresh_id=:refresh_id
                """),
                {
                    "finished_at": finished_at,
                    "status": status,
                    "period_start": period_start,
                    "period_end": period_end,
                    "rows_read": source_rows,
                    "rows_inserted": rows_inserted,
                    "rows_updated": rows_updated,
                    "error": error,
                    "warning": warning,
                    "local_file_path": local_file_path,
                    "checksum": checksum,
                    "source_snapshot_date": snapshot_date,
                    "requested_period": requested_period,
                    "dataset_name": dataset_name,
                    "source_url": source_url,
                    "downloaded_bytes": downloaded_bytes,
                    "source_rows": source_rows,
                    "parsed_rows": parsed_rows,
                    "normalized_rows": normalized_rows,
                    "rows_skipped": rows_skipped,
                    "detected_encoding": detected_encoding,
                    "refresh_id": self._refresh_id,
                },
            )

        return {
            "refresh_id": self._refresh_id,
            "source_id": source_id,
            "status": status,
            "rows_read": rows_read,
            "rows_inserted": rows_inserted,
            "rows_updated": rows_updated,
            "source_rows": source_rows,
            "parsed_rows": parsed_rows,
            "normalized_rows": normalized_rows,
            "rows_skipped": rows_skipped,
            "downloaded_bytes": downloaded_bytes,
            "requested_period": requested_period,
            "dataset": dataset_name,
            "source_url": source_url,
            "detected_encoding": detected_encoding,
            "error": error,
            "warning": warning,
            "started_at": started_at,
            "finished_at": finished_at,
            "period_start": period_start,
            "period_end": period_end,
            "local_file_path": local_file_path,
        }


def _source_meta(source_id: str) -> dict[str, str]:
    for source in PLANT_SOURCES:
        if source["source_id"] == source_id:
            return dict(source)
    return {"dataset_name": source_id}


def _requested_period(
    *,
    source_id: str,
    year: int,
    year_month: str | None,
    use_daily_aneel: bool,
) -> str | None:
    if source_id == SOURCE_CCEE_MONTHLY:
        return str(int(year))
    if source_id == SOURCE_CCEE_HOURLY:
        return year_month
    if source_id == SOURCE_ANEEL_SIGA:
        return "daily" if use_daily_aneel else "monthly"
    return None


def _zero_row_warning(
    *,
    source_id: str,
    requested_period: str | None,
    source_rows: int,
    parsed_rows: int,
    normalized_rows: int,
) -> str:
    label = requested_period or "selected period"
    if source_rows <= 0:
        return (
            f"Refresh completed but the source file for {label} contained no rows. "
            "Check source availability or choose another period."
        )
    if parsed_rows <= 0 or normalized_rows <= 0:
        return (
            f"Refresh downloaded {source_rows:,} source rows for {label}, but none matched "
            f"the {source_id} parser requirements. Check source schema and required fields."
        )
    return (
        f"Refresh parsed {normalized_rows:,} rows for {label}, but no rows were cached. "
        "Check local database constraints and source keys."
    )
