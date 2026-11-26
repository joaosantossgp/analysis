from __future__ import annotations

from src.financials import read_service_refresh_selection as _refresh_selection
from src.financials.refresh_commands import RefreshCommandsMixin
from src.financials.mapping_commands import MappingCommandsMixin
from src.financials.read_service_coverage import ReadServiceCoverageMixin
from src.financials.read_service_export import ReadServiceExportMixin
from src.financials.read_service_query import ReadServiceQueryMixin
from src.financials.read_service_refresh_selection import (
    RefreshAlreadyActiveError,
)
from src.financials.utils import current_reporting_year_cap


def resolve_refresh_batch_selection(*args, **kwargs):
    original = _refresh_selection.current_reporting_year_cap
    _refresh_selection.current_reporting_year_cap = current_reporting_year_cap
    try:
        return _refresh_selection.resolve_refresh_batch_selection(*args, **kwargs)
    finally:
        _refresh_selection.current_reporting_year_cap = original


def resolve_refresh_year_range(*args, **kwargs):
    original = _refresh_selection.current_reporting_year_cap
    _refresh_selection.current_reporting_year_cap = current_reporting_year_cap
    try:
        return _refresh_selection.resolve_refresh_year_range(*args, **kwargs)
    finally:
        _refresh_selection.current_reporting_year_cap = original


class CVMReadService(
    ReadServiceQueryMixin,
    ReadServiceExportMixin,
    ReadServiceCoverageMixin,
    RefreshCommandsMixin,
    MappingCommandsMixin,
):
    """Compatibility facade for queries, exports and explicit write commands."""
    REQUIRED_PACKAGE_STATEMENTS = ("BPA", "BPP", "DRE", "DFC")
    BASE_HEALTH_OK_THRESHOLD = 90.0
    BASE_HEALTH_CRITICAL_THRESHOLD = 70.0
    THROUGHPUT_WINDOW_HOURS = 24
    THROUGHPUT_MIN_SUCCESS_SAMPLES = 3
    RANKED_REFRESH_QUEUE_WINDOW_MINUTES = 10
    PRIORITIZED_BACKLOG_STALE_HOURS = 12
    ACTIVE_REFRESH_STATUSES = {"queued", "running"}
    REFRESH_ESTIMATE_DEFAULT_TOTAL_SECONDS = 18 * 60
    REFRESH_ESTIMATE_PROGRESS_FLOOR = 12.0
    REFRESH_ESTIMATE_PROGRESS_CEILING = 92.0
    REFRESH_ESTIMATE_PROGRESS_CAP = 96.0
    REFRESH_QUEUE_PROGRESS_BASE = 14.0
    REFRESH_QUEUE_PROGRESS_STEP = 4.0
    REFRESH_QUEUE_POSITION_STEP_SECONDS = 2 * 60
    REFRESH_RUNNING_PROGRESS_CAP = 88.0
    REFRESH_RUNNING_STALL_SECONDS = 3 * 60
    REFRESH_QUEUE_STALL_SECONDS = 12 * 60
    READ_CACHE_VERSION_CHECK_SECONDS = 30.0
    BASE_HEALTH_CACHE_SCHEMA_VERSION = 1
    SECTOR_DIRECTORY_CACHE_SCHEMA_VERSION = 1
    VALID_PERIOD_SCOPES: frozenset[str] = frozenset(
        {"last_3_years", "last_5_years", "last_10_years", "full_history"}
    )


__all__ = [
    "CVMReadService",
    "RefreshAlreadyActiveError",
    "resolve_refresh_batch_selection",
    "resolve_refresh_year_range",
]
