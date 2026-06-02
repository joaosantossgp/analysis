"""User-triggered refresh job for plant and plant-parcel indicators."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import text

from src.energy_kpi.plant_parcel_ingest import (
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
        period_start: str | None = None
        period_end: str | None = None

        with engine.begin() as conn:
            seed_plant_sources(conn)
            conn.execute(
                text("""
                    INSERT INTO energy_source_refresh_log
                        (refresh_id, source_id, requested_by, started_at, status)
                    VALUES
                        (:refresh_id, :source_id, :requested_by, :started_at, 'running')
                """),
                {
                    "refresh_id": self._refresh_id,
                    "source_id": source_id,
                    "requested_by": triggered_by,
                    "started_at": started_at,
                },
            )

        rows_read = 0
        rows_inserted = 0
        local_file_path = None
        checksum = None
        status = "success"
        error = None
        snapshot_date = None

        try:
            if source_id == SOURCE_CCEE_MONTHLY:
                selected_year = int(year or datetime.now(timezone.utc).year)
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
        except Exception as exc:
            status = "error"
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
                        rows_updated=0,
                        error_message=:error,
                        local_file_path=:local_file_path,
                        checksum=:checksum,
                        source_snapshot_date=:source_snapshot_date
                    WHERE refresh_id=:refresh_id
                """),
                {
                    "finished_at": finished_at,
                    "status": status,
                    "period_start": period_start,
                    "period_end": period_end,
                    "rows_read": rows_read,
                    "rows_inserted": rows_inserted,
                    "error": error,
                    "local_file_path": local_file_path,
                    "checksum": checksum,
                    "source_snapshot_date": snapshot_date,
                    "refresh_id": self._refresh_id,
                },
            )

        return {
            "refresh_id": self._refresh_id,
            "source_id": source_id,
            "status": status,
            "rows_read": rows_read,
            "rows_inserted": rows_inserted,
            "error": error,
            "started_at": started_at,
            "finished_at": finished_at,
            "period_start": period_start,
            "period_end": period_end,
        }
