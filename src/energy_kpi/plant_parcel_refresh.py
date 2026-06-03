"""User-triggered refresh job for plant and plant-parcel indicators."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import text

from src.energy_kpi.metrics import normalize_reference_month
from src.energy_kpi.plant_parcel_ingest import (
    PLANT_SOURCES,
    SOURCE_ANEEL_SIGA,
    SOURCE_CCEE_HOURLY,
    SOURCE_CCEE_MONTHLY,
    CCEEBlockedException,
    fetch_source_snapshot_from_local,
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
                         requested_period, dataset_name, import_mode)
                    VALUES
                        (:refresh_id, :source_id, :requested_by, :started_at, 'running',
                         :requested_period, :dataset_name, 'automatic_refresh')
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
                snapshot = fetch_ccee_monthly_snapshot(self.settings, selected_year)
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
                snapshot = fetch_ccee_hourly_snapshot(self.settings, year_month)
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
            if snapshot.status == "warning":
                status = "warning"
                warning = "Package discovery failed, direct resource fallback succeeded."
            elif snapshot.status == "warning_fallback":
                status = "warning"
                warning = "Package download failed (CCEE maintenance), but ingested from local fallback file."
            elif rows_inserted <= 0:
                status = "warning"
                warning = _zero_row_warning(
                    source_id=source_id,
                    requested_period=requested_period,
                    source_rows=source_rows,
                    parsed_rows=parsed_rows,
                    normalized_rows=normalized_rows,
                )
        except CCEEBlockedException as exc:
            status = "failed"
            error = (
                "CCEE source is temporarily unavailable or blocked by maintenance. "
                "Try again later or use a previously discovered resource link if available."
            )
            logger.warning("CCEE blocked refresh for %s: %s", source_id, exc)
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
                        detected_encoding=:detected_encoding,
                        file_size_bytes=:downloaded_bytes,
                        file_hash=:checksum,
                        file_type=:file_type,
                        detected_period=:detected_period,
                        source_page_url=:source_page_url
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
                    "file_type": _file_type_from_path(local_file_path),
                    "detected_period": _format_detected_period(period_start, period_end),
                    "source_page_url": source_meta.get("official_url"),
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

    def run_manual_file_import(
        self,
        *,
        source_id: str,
        file_path: str | Path,
        triggered_by: str = "user",
        expected_period: str | None = None,
        original_file_name: str | None = None,
    ) -> dict:
        if source_id not in {SOURCE_CCEE_MONTHLY, SOURCE_CCEE_HOURLY}:
            return {
                "refresh_id": self._refresh_id,
                "import_id": self._refresh_id,
                "source_id": source_id,
                "status": "failed",
                "error": f"manual import is not supported for source_id={source_id}",
            }

        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        engine = get_energy_kpi_engine(self.settings)
        source_meta = _source_meta(source_id)
        dataset_name = source_meta.get("dataset_name")
        source_page_url = source_meta.get("official_url")
        src_path = Path(file_path).expanduser()
        safe_name = Path(str(original_file_name or src_path.name or "manual-import.csv")).name
        requested_period = _normalize_manual_expected_period(source_id, expected_period)
        file_type = _file_type_from_path(safe_name)
        file_size_bytes = src_path.stat().st_size if src_path.exists() and src_path.is_file() else None

        with engine.begin() as conn:
            seed_plant_sources(conn)
            conn.execute(
                text("""
                    INSERT INTO energy_source_refresh_log
                        (refresh_id, source_id, requested_by, started_at, status,
                         requested_period, dataset_name, import_mode, original_file_name,
                         file_size_bytes, file_type, source_page_url, source_url)
                    VALUES
                        (:refresh_id, :source_id, :requested_by, :started_at, 'running',
                         :requested_period, :dataset_name, 'manual_file', :original_file_name,
                         :file_size_bytes, :file_type, :source_page_url, :source_page_url)
                """),
                {
                    "refresh_id": self._refresh_id,
                    "source_id": source_id,
                    "requested_by": triggered_by,
                    "started_at": started_at,
                    "requested_period": requested_period,
                    "dataset_name": dataset_name,
                    "original_file_name": safe_name,
                    "file_size_bytes": file_size_bytes,
                    "file_type": file_type,
                    "source_page_url": source_page_url,
                },
            )

        rows_read = 0
        rows_inserted = 0
        rows_updated = 0
        source_rows = 0
        parsed_rows = 0
        normalized_rows = 0
        rows_skipped = 0
        local_file_path = None
        checksum = None
        status = "success"
        error = None
        warning = None
        detected_encoding = None
        detected_period = None
        period_start = None
        period_end = None
        snapshot_date = None

        try:
            if not src_path.exists() or not src_path.is_file():
                raise FileNotFoundError(f"Manual import file not found: {src_path}")
            _validate_manual_import_file(source_id, src_path)

            snapshot = fetch_source_snapshot_from_local(
                paths=self.settings.paths,
                source_id=source_id,
                provider=str(source_meta.get("provider") or "CCEE"),
                dataset_name=str(dataset_name or source_id),
                file_path=src_path,
                file_name=safe_name,
                source_version_label=f"{dataset_name}:{requested_period or 'manual'}",
                period_start=requested_period,
                period_end=requested_period,
                source_url=str(source_page_url or "manual_file"),
            )
            local_file_path = str(snapshot.file_path)
            checksum = snapshot.sha256
            snapshot_date = snapshot.fetched_at
            source_rows = int(snapshot.row_count or 0)
            if source_id == SOURCE_CCEE_MONTHLY:
                frame = parse_ccee_monthly(snapshot)
            else:
                frame = parse_ccee_hourly(snapshot)

            detected_periods = _reference_periods_from_frame(frame)
            detected_period = _format_detected_periods(detected_periods)
            requested_period = _validate_manual_period(
                source_id=source_id,
                requested_period=requested_period,
                detected_periods=detected_periods,
            )
            if source_id == SOURCE_CCEE_HOURLY and requested_period:
                frame = frame.loc[frame["reference_month"] == requested_period].copy()
                if not frame.empty:
                    detected_periods = [requested_period]
            normalized_rows = int(len(frame))
            parsed_rows = int(frame.attrs.get("parsed_rows", normalized_rows))
            source_rows = int(snapshot.row_count or frame.attrs.get("source_row_count") or 0)
            rows_skipped = max(source_rows - normalized_rows, 0)
            rows_read = normalized_rows
            detected_encoding = frame.attrs.get("detected_encoding")
            period_start = detected_periods[0] if detected_periods else requested_period
            period_end = detected_periods[-1] if detected_periods else requested_period

            with engine.begin() as conn:
                persist_plant_snapshot_record(conn, snapshot)
                if source_id == SOURCE_CCEE_MONTHLY:
                    rows_inserted = upsert_ccee_monthly(conn, frame)
                else:
                    rows_inserted = upsert_ccee_hourly(conn, frame)

            if rows_inserted <= 0:
                status = "warning"
                warning = _zero_row_warning(
                    source_id=source_id,
                    requested_period=requested_period or detected_period,
                    source_rows=source_rows,
                    parsed_rows=parsed_rows,
                    normalized_rows=normalized_rows,
                )
        except Exception as exc:
            status = "failed"
            error = str(exc)
            logger.warning("Manual plant parcel import failed for %s: %s", source_id, exc)

        finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE energy_source_refresh_log
                    SET finished_at=:finished_at,
                        status=:status,
                        period_start=:period_start,
                        period_end=:period_end,
                        rows_downloaded=:source_rows,
                        rows_inserted=:rows_inserted,
                        rows_updated=:rows_updated,
                        error_message=:error,
                        warning_message=:warning,
                        local_file_path=:local_file_path,
                        checksum=:checksum,
                        file_hash=:checksum,
                        source_snapshot_date=:source_snapshot_date,
                        requested_period=:requested_period,
                        source_url=:source_page_url,
                        downloaded_bytes=:file_size_bytes,
                        source_rows=:source_rows,
                        parsed_rows=:parsed_rows,
                        normalized_rows=:normalized_rows,
                        rows_skipped=:rows_skipped,
                        detected_encoding=:detected_encoding,
                        detected_period=:detected_period,
                        file_size_bytes=:file_size_bytes,
                        file_type=:file_type,
                        source_page_url=:source_page_url
                    WHERE refresh_id=:refresh_id
                """),
                {
                    "finished_at": finished_at,
                    "status": status,
                    "period_start": period_start,
                    "period_end": period_end,
                    "source_rows": source_rows,
                    "rows_inserted": rows_inserted,
                    "rows_updated": rows_updated,
                    "error": error,
                    "warning": warning,
                    "local_file_path": local_file_path,
                    "checksum": checksum,
                    "source_snapshot_date": snapshot_date,
                    "requested_period": requested_period,
                    "source_page_url": source_page_url,
                    "file_size_bytes": file_size_bytes,
                    "parsed_rows": parsed_rows,
                    "normalized_rows": normalized_rows,
                    "rows_skipped": rows_skipped,
                    "detected_encoding": detected_encoding,
                    "detected_period": detected_period,
                    "file_type": file_type,
                    "refresh_id": self._refresh_id,
                },
            )

        return {
            "refresh_id": self._refresh_id,
            "import_id": self._refresh_id,
            "source_id": source_id,
            "status": status,
            "import_mode": "manual_file",
            "rows_read": rows_read,
            "rows_inserted": rows_inserted,
            "rows_updated": rows_updated,
            "source_rows": source_rows,
            "parsed_rows": parsed_rows,
            "normalized_rows": normalized_rows,
            "rows_skipped": rows_skipped,
            "downloaded_bytes": file_size_bytes,
            "file_size_bytes": file_size_bytes,
            "file_hash": checksum,
            "file_type": file_type,
            "original_file_name": safe_name,
            "requested_period": requested_period,
            "detected_period": detected_period,
            "dataset": dataset_name,
            "source_url": source_page_url,
            "source_page_url": source_page_url,
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


def _normalize_manual_expected_period(source_id: str, expected_period: str | None) -> str | None:
    if not expected_period:
        return None
    text_value = str(expected_period).strip()
    if not text_value:
        return None
    if source_id == SOURCE_CCEE_MONTHLY:
        digits = "".join(ch for ch in text_value if ch.isdigit())
        return digits[:4] if len(digits) >= 4 else text_value
    if source_id == SOURCE_CCEE_HOURLY:
        try:
            return normalize_reference_month(text_value)
        except ValueError:
            return text_value
    return text_value


def _validate_manual_import_file(source_id: str, file_path: Path) -> None:
    suffix = file_path.suffix.lower()
    if source_id == SOURCE_CCEE_MONTHLY:
        if suffix != ".csv":
            raise ValueError("CCEE monthly manual import accepts annual .csv files.")
        return
    if source_id == SOURCE_CCEE_HOURLY:
        if suffix not in {".gz", ".gzip", ".csv"}:
            raise ValueError("CCEE hourly manual import accepts monthly .gz, .gzip, or .csv files.")
        return
    raise ValueError(f"manual import is not supported for source_id={source_id}")


def _reference_periods_from_frame(frame) -> list[str]:
    if frame.empty or "reference_month" not in frame.columns:
        return []
    periods = {
        normalize_reference_month(value)
        for value in frame["reference_month"].dropna().astype(str).tolist()
        if str(value).strip()
    }
    return sorted(periods)


def _validate_manual_period(
    *,
    source_id: str,
    requested_period: str | None,
    detected_periods: list[str],
) -> str | None:
    if not detected_periods:
        return requested_period
    if source_id == SOURCE_CCEE_MONTHLY:
        if requested_period and any(period[:4] != requested_period for period in detected_periods):
            raise ValueError(
                "File reference months do not match the selected annual CCEE monthly period "
                f"{requested_period}: {_format_detected_periods(detected_periods)}."
            )
        return requested_period or detected_periods[-1][:4]
    if source_id == SOURCE_CCEE_HOURLY:
        if requested_period and requested_period not in detected_periods:
            raise ValueError(
                "File reference month does not match the selected CCEE hourly month "
                f"{requested_period}: {_format_detected_periods(detected_periods)}."
            )
        if not requested_period and len(detected_periods) > 1:
            raise ValueError(
                "CCEE hourly manual import requires a single reference month; detected "
                f"{_format_detected_periods(detected_periods)}."
            )
        return requested_period or detected_periods[0]
    return requested_period


def _format_detected_periods(periods: list[str]) -> str | None:
    if not periods:
        return None
    if len(periods) == 1:
        return periods[0]
    return f"{periods[0]}..{periods[-1]}"


def _format_detected_period(period_start: str | None, period_end: str | None) -> str | None:
    if not period_start and not period_end:
        return None
    if not period_end or period_start == period_end:
        return period_start
    if not period_start:
        return period_end
    return f"{period_start}..{period_end}"


def _file_type_from_path(path: str | Path | None) -> str | None:
    if not path:
        return None
    suffix = Path(str(path)).suffix.lower()
    if suffix in {".gz", ".gzip"}:
        return "gzip"
    if suffix == ".csv":
        return "csv"
    return suffix[1:] if suffix else None


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
