from __future__ import annotations

import functools
import time
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Callable

import pandas as pd
from sqlalchemy import bindparam, inspect, text

from src.company_catalog import (
    CompanyCatalogEntry,
    CompanyCatalogUnavailableError,
    CompanyCatalogService,
)
from src.gics_manual_mapping import (
    GICS_11_SECTORS,
    gics_sector_sort_key,
    resolve_gics_classification,
    resolve_gics_sector_name,
)
from src.contracts import (
    CompanyDirectoryAppliedFilters,
    CompanyDirectoryPage,
    CompanyDirectoryPagination,
    CompanyFiltersDTO,
    CompanyInfoDTO,
    CompanySectorFilterOption,
    CompanySearchResult,
    CompanySuggestionDTO,
    HealthSnapshot,
    KPIBundle,
    RankedRefreshQueueItem,
    RankedRefreshQueueResult,
    RefreshBatchSelection,
    RefreshDispatchDTO,
    RefreshRequest,
    RefreshStatusDTO,
    SectorCompanyMetricDTO,
    SectorDetailDTO,
    SectorDirectoryDTO,
    SectorDirectoryItemDTO,
    SectorSnapshotDTO,
    SubIndustryCountDTO,
    SectorYearOverviewDTO,
    StatementMatrix,
    StatementSummaryDTO,
    SummaryBlockDTO,
    TabularData,
    default_incremental_refresh_policy,
)
from src.refresh_jobs import (
    REFRESH_STAGE_ORDER,
    REFRESH_STAGE_WEIGHTS,
    RefreshJobRepository,
    ensure_refresh_runtime_tables_for_connection,
)
from src.refresh_service import HeadlessRefreshService
from src.statement_summary import build_general_summary_blocks
from src.db import build_engine
from src.excel_exporter import ExcelExporter, build_excel_filename
from src.kpi_engine import compute_all_kpis, compute_quarterly_kpis
from src.query_layer import CVMQueryLayer
from src.sector_taxonomy import canonical_sector_name, sector_slugify
from src.settings import AppSettings, get_settings
from src.utils import current_reporting_year_cap, now_iso_seconds

EXPORT_STATEMENT_TYPES = ("DRE", "BPA", "BPP", "DFC", "DVA", "DMPL")

# Top-10 B3 companies by approximate market cap, ordered largest-first.
# cd_cvm values sourced from src/ticker_map.py.
# Update this list when B3 composition changes significantly (roughly annual).
POPULARES_CVM_IDS: tuple[int, ...] = (
    9512,   # PETR4  – PETROBRAS
    4170,   # VALE3  – VALE
    19348,  # ITUB4  – ITAÚ UNIBANCO
    906,    # BBDC4  – BANCO BRADESCO
    1023,   # BBAS3  – BANCO DO BRASIL
    22616,  # BPAC11 – BTG PACTUAL
    23264,  # ABEV3  – AMBEV
    5410,   # WEGE3  – WEG
    24813,  # RENT3  – LOCALIZA
    21610,  # B3SA3  – B3
)


class RefreshAlreadyActiveError(RuntimeError):
    """Raised when an internal on-demand refresh is already active."""


def _parse_years(raw_years: str | None) -> tuple[int, ...]:
    if not raw_years:
        return ()
    if isinstance(raw_years, (list, tuple)):
        return tuple(sorted({int(value) for value in raw_years}))
    result = []
    for value in str(raw_years).split(","):
        value = value.strip()
        if not value:
            continue
        try:
            result.append(int(value))
        except ValueError:
            continue
    return tuple(sorted(set(result)))


BATCH_REFRESH_VALID_MODES = {"full", "missing", "outdated", "failed"}
BATCH_REFRESH_FAILED_STATES = {"failed", "error", "dispatch_failed"}
BATCH_REFRESH_ACTIVE_STATES = {"queued", "running"}
BATCH_REFRESH_CURRENT_CODES = {
    "already_current",
    "local_data_ready",
    "readable_history_available",
    "refresh_completed",
    "refresh_completed_readable",
}
BATCH_REFRESH_OUTDATED_CODES = {
    "mixed_retryable_error_readable",
    "mixed_refresh_stalled_readable",
    "mixed_no_new_data_readable",
    "refresh_completed_no_readable",
}
BATCH_REFRESH_MAX_PAGE_SIZE = 10000


def resolve_refresh_batch_selection(
    read_service: Any,
    params: dict[str, Any] | None = None,
    *,
    mode: str = "missing",
    default_start_year: int = 2010,
    max_page_size: int = BATCH_REFRESH_MAX_PAGE_SIZE,
) -> RefreshBatchSelection:
    """Resolve the exact company queue for API and desktop batch refreshes."""

    request_params = dict(params or {})
    normalized_mode = str(mode or "missing").strip().lower()
    if normalized_mode not in BATCH_REFRESH_VALID_MODES:
        raise ValueError(f"Modo de refresh invalido: {normalized_mode}")

    start_year, end_year = _resolve_batch_year_range(
        request_params,
        default_start_year=default_start_year,
    )
    limit = _resolve_batch_limit(request_params.get("limit"))
    companies = _load_batch_candidate_companies(
        read_service,
        request_params,
        page_size=max(1, min(int(max_page_size), BATCH_REFRESH_MAX_PAGE_SIZE)),
    )
    companies = _filter_batch_cvm_range(
        companies,
        _resolve_batch_cvm_range_param(request_params),
    )
    companies = _filter_batch_cd_cvm(companies, request_params.get("cd_cvm"))

    status_items = _load_batch_refresh_status_map(read_service)
    status_filter = request_params.get("status_filter")
    if normalized_mode == "failed" and not status_filter:
        status_filter = "failed"
    if status_filter:
        companies = _filter_batch_status(companies, status_items, str(status_filter))

    if normalized_mode == "missing":
        companies = _filter_batch_missing_companies(
            read_service,
            companies,
            start_year=start_year,
            end_year=end_year,
        )
    elif normalized_mode == "outdated":
        companies = _filter_batch_outdated_companies(
            companies,
            status_items,
            end_year=end_year,
        )
    elif normalized_mode == "failed":
        companies = _filter_batch_failed_companies(companies, status_items)

    if limit is not None:
        companies = companies[:limit]

    return RefreshBatchSelection(
        mode=normalized_mode,
        companies=tuple(companies),
        start_year=start_year,
        end_year=end_year,
    )


def resolve_refresh_year_range(
    params: dict[str, Any],
    *,
    default_start_year: int,
    error_factory: Callable[[str], Exception] = ValueError,
) -> tuple[int, int]:
    """Resolve (start_year, end_year) for any refresh request.

    Shared by `resolve_refresh_batch_selection` (read service),
    `ApiRefreshJobManager` (HTTP API), and `DesktopRefreshJobManager`
    (desktop bridge). Each caller can pass its own ``error_factory`` so
    the raised exception matches its transport layer (e.g. API converts
    its custom exception to HTTP 400).
    """
    # Default through the current year so on-demand/batch refreshes pick up
    # current-year quarterly ITR (e.g. 1T26) rather than stopping at the last
    # closed year. Explicit end_year still overrides this.
    end_default = current_reporting_year_cap()
    try:
        start_year = int(params.get("start_year") or default_start_year)
        end_year = int(params.get("end_year") or end_default)
    except (TypeError, ValueError) as exc:
        raise error_factory("start_year e end_year devem ser inteiros.") from exc
    if start_year > end_year:
        raise error_factory("start_year nao pode ser maior que end_year.")
    return start_year, end_year


# Backwards-compatible alias kept for internal callsites; new code should
# use ``resolve_refresh_year_range`` directly.
_resolve_batch_year_range = resolve_refresh_year_range


def _resolve_batch_limit(raw_limit: Any) -> int | None:
    if raw_limit in (None, ""):
        return None
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit deve ser um inteiro entre 1 e 10000.") from exc
    if limit < 1 or limit > BATCH_REFRESH_MAX_PAGE_SIZE:
        raise ValueError("limit deve ser um inteiro entre 1 e 10000.")
    return limit


def _load_batch_candidate_companies(
    read_service: Any,
    params: dict[str, Any],
    *,
    page_size: int,
) -> list[str]:
    company_ids = _resolve_batch_company_ids(params.get("company_ids"))
    sector_slug = params.get("sector_slug") or params.get("sector")
    page = read_service.list_companies(
        search=str(params.get("search") or ""),
        sector_slug=str(sector_slug) if sector_slug else None,
        page=1,
        page_size=int(page_size),
    )
    items = list(getattr(page, "items", ()))

    sub_sector = str(params.get("gics_sub_industry") or params.get("sub_sector") or "").strip()
    if sub_sector:
        items = [
            item
            for item in items
            if str(_get_batch_attr(item, "gics_sub_industry") or "").strip() == sub_sector
        ]

    if company_ids:
        wanted = {int(value) for value in company_ids}
        items = [
            item
            for item in items
            if int(_get_batch_attr(item, "cd_cvm") or 0) in wanted
        ]

    return _unique_company_codes(items)


def _resolve_batch_company_ids(raw_ids: Any) -> list[int]:
    if raw_ids in (None, ""):
        return []
    values = raw_ids
    if isinstance(raw_ids, str):
        values = [part.strip() for part in raw_ids.split(",") if part.strip()]
    if not isinstance(values, (list, tuple, set)):
        raise ValueError("company_ids deve ser uma lista de codigos CVM.")
    parsed: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            code = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("company_ids aceita apenas codigos CVM inteiros.") from exc
        if code <= 0:
            raise ValueError("company_ids aceita apenas codigos CVM positivos.")
        if code not in seen:
            seen.add(code)
            parsed.append(code)
    return parsed


def _unique_company_codes(items: Any) -> list[str]:
    companies: list[str] = []
    seen: set[int] = set()
    for item in items:
        cd_cvm = _get_batch_attr(item, "cd_cvm")
        try:
            code = int(cd_cvm)
        except (TypeError, ValueError):
            continue
        if code in seen:
            continue
        seen.add(code)
        companies.append(str(code))
    return companies


def _resolve_batch_cvm_range_param(params: dict[str, Any]) -> Any:
    raw_range = params.get("cvm_range")
    if raw_range not in (None, ""):
        return raw_range
    cvm_from = params.get("cvm_from")
    cvm_to = params.get("cvm_to")
    if cvm_from not in (None, "") or cvm_to not in (None, ""):
        return {"start": cvm_from, "end": cvm_to}
    return None


def _filter_batch_cvm_range(companies: list[str], raw_range: Any) -> list[str]:
    if raw_range in (None, ""):
        return companies

    start: Any | None = None
    end: Any | None = None
    if isinstance(raw_range, dict):
        start = raw_range.get("start") or raw_range.get("from")
        end = raw_range.get("end") or raw_range.get("to")
    elif isinstance(raw_range, (list, tuple)):
        if len(raw_range) != 2:
            raise ValueError("cvm_range deve conter exatamente dois limites.")
        start, end = raw_range[0], raw_range[1]
    elif isinstance(raw_range, str):
        if "-" not in raw_range:
            raise ValueError(
                "cvm_range deve usar {start,end}, [start,end] ou 'start-end'."
            )
        left, right = raw_range.split("-", 1)
        start, end = left.strip(), right.strip()
    else:
        raise ValueError(
            "cvm_range deve usar {start,end}, [start,end] ou 'start-end'."
        )

    if start in (None, "") and end in (None, ""):
        return companies
    try:
        start_int = int(start) if start not in (None, "") else -1
        end_int = int(end) if end not in (None, "") else 10**9
    except (TypeError, ValueError) as exc:
        raise ValueError("cvm_range deve conter numeros inteiros.") from exc
    if start_int > end_int:
        raise ValueError("cvm_range.start nao pode ser maior que cvm_range.end.")
    return [code for code in companies if start_int <= int(code) <= end_int]


def _filter_batch_cd_cvm(companies: list[str], raw_cd_cvm: Any) -> list[str]:
    if raw_cd_cvm in (None, ""):
        return companies
    try:
        target = int(raw_cd_cvm)
    except (TypeError, ValueError) as exc:
        raise ValueError("cd_cvm deve ser um inteiro.") from exc
    return [code for code in companies if int(code) == target]


def _load_batch_refresh_status_map(read_service: Any) -> dict[int, Any]:
    try:
        statuses = read_service.list_refresh_status()
    except AttributeError:
        return {}
    return {
        int(_get_batch_attr(item, "cd_cvm")): item
        for item in statuses
        if _get_batch_attr(item, "cd_cvm") is not None
    }


def _filter_batch_status(
    companies: list[str],
    status_items: dict[int, Any],
    status_filter: str,
) -> list[str]:
    normalized = str(status_filter or "").strip().lower()
    if not normalized or normalized in {"all", "todos"}:
        return companies
    return [
        code
        for code in companies
        if _batch_status_matches(status_items.get(int(code)), normalized)
    ]


def _batch_status_matches(status_item: Any, normalized_filter: str) -> bool:
    if status_item is None:
        return normalized_filter in {"missing", "idle"}
    if normalized_filter == "failed":
        return _batch_status_has_failure(status_item)
    if normalized_filter == "outdated":
        return _batch_status_is_outdated(status_item, end_year=None)
    if normalized_filter in {"active", "ativo"}:
        return bool(_batch_status_values(status_item) & BATCH_REFRESH_ACTIVE_STATES)
    if normalized_filter in {"missing", "sem_dados"}:
        return not bool(_get_batch_attr(status_item, "has_readable_current_data"))
    return normalized_filter in _batch_status_values(status_item)


def _filter_batch_missing_companies(
    read_service: Any,
    companies: list[str],
    *,
    start_year: int,
    end_year: int,
) -> list[str]:
    if not companies:
        return []
    years_scope = set(range(int(start_year), int(end_year) + 1))
    if not years_scope:
        return []
    complete_years_map = _load_batch_complete_years_map(
        read_service,
        companies,
        start_year=start_year,
        end_year=end_year,
    )
    return [
        code
        for code in companies
        if not years_scope.issubset(
            {int(year) for year in complete_years_map.get(int(code), ())}
        )
    ]


def _load_batch_complete_years_map(
    read_service: Any,
    companies: list[str],
    *,
    start_year: int,
    end_year: int,
) -> dict[int, tuple[int, ...]]:
    codes = [int(code) for code in companies]
    load_complete = getattr(read_service, "_load_complete_annual_years_map", None)
    if callable(load_complete):
        return {
            int(code): tuple(int(year) for year in years)
            for code, years in load_complete(
                codes,
                start_year=int(start_year),
                end_year=int(end_year),
            ).items()
        }

    get_available_years = getattr(read_service, "get_available_years", None)
    if not callable(get_available_years):
        return {}

    complete_years_map: dict[int, tuple[int, ...]] = {}
    for code in codes:
        years = [
            int(year)
            for year in get_available_years(int(code))
            if int(start_year) <= int(year) <= int(end_year)
        ]
        complete_years_map[int(code)] = tuple(sorted(set(years)))
    return complete_years_map


def _filter_batch_outdated_companies(
    companies: list[str],
    status_items: dict[int, Any],
    *,
    end_year: int,
) -> list[str]:
    return [
        code
        for code in companies
        if _batch_status_is_outdated(status_items.get(int(code)), end_year=end_year)
    ]


def _batch_status_is_outdated(status_item: Any, *, end_year: int | None) -> bool:
    if status_item is None:
        return False
    if _batch_status_has_failure(status_item):
        return False
    values = _batch_status_values(status_item)
    if values & BATCH_REFRESH_ACTIVE_STATES:
        return False
    if values & BATCH_REFRESH_OUTDATED_CODES:
        return True

    severity = str(_get_batch_attr(status_item, "freshness_summary_severity") or "").lower()
    has_readable_data = bool(_get_batch_attr(status_item, "has_readable_current_data"))
    if severity in {"warning", "error"} and has_readable_data:
        return True

    if end_year is not None and has_readable_data:
        latest_year = _get_batch_attr(status_item, "latest_readable_year")
        if latest_year is not None and int(latest_year) < int(end_year):
            return True
        last_end_year = _get_batch_attr(status_item, "last_end_year")
        if last_end_year is not None and int(last_end_year) < int(end_year):
            return True
    if values & BATCH_REFRESH_CURRENT_CODES:
        return False
    return False


def _filter_batch_failed_companies(
    companies: list[str],
    status_items: dict[int, Any],
) -> list[str]:
    return [
        code
        for code in companies
        if _batch_status_is_retryable_failure(status_items.get(int(code)))
    ]


def _batch_status_is_retryable_failure(status_item: Any) -> bool:
    if status_item is None or not _batch_status_has_failure(status_item):
        return False
    retry_flags = [
        _get_batch_attr(status_item, "is_retry_allowed"),
        _get_batch_attr(status_item, "latest_attempt_retryable"),
    ]
    explicit_flags = [flag for flag in retry_flags if flag is not None]
    if not explicit_flags:
        return True
    return any(bool(flag) for flag in explicit_flags)


def _batch_status_has_failure(status_item: Any) -> bool:
    values = _batch_status_values(status_item)
    if values & BATCH_REFRESH_ACTIVE_STATES:
        return False
    return bool(values & BATCH_REFRESH_FAILED_STATES)


def _batch_status_values(status_item: Any) -> set[str]:
    fields = (
        "tracking_state",
        "last_status",
        "latest_attempt_outcome",
        "latest_attempt_reason_code",
        "status_reason_code",
        "freshness_summary_code",
    )
    return {
        str(value).strip().lower()
        for field in fields
        for value in (_get_batch_attr(status_item, field),)
        if value not in (None, "")
    }


def _get_batch_attr(item: Any, field: str) -> Any:
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


class CVMReadService:
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
    CATALOG_FALLBACK_MIN_LOCAL_COMPANIES = 100
    READ_CACHE_VERSION_CHECK_SECONDS = 30.0

    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or get_settings()
        self.engine = build_engine(self.settings)
        self.query_layer = CVMQueryLayer(engine=self.engine)
        self.refresh_job_repository = RefreshJobRepository(self.engine)
        self._company_catalog = None
        self._operational_service = None
        self._refresh_service = None
        self._read_cache_data_version: int | None = None
        self._read_cache_checked_at = 0.0
        self._company_universe_cache: tuple[CompanySearchResult, ...] | None = None
        self._company_page_cache: dict[tuple[str, str | None, int, int], CompanyDirectoryPage] = {}
        self._local_company_catalog_is_sufficient_cache: bool | None = None
        self._company_filters_cache: CompanyFiltersDTO | None = None
        self._market_cap_index_cache: tuple[dict[int, Any], dict[str, Any], list[Any]] | None = None
        self._market_cap_index_mtime: float | None = None
        self._sector_directory_cache: dict[str, SectorDirectoryDTO] = {}
        self._health_snapshot_cache: dict[tuple[int, int], HealthSnapshot] = {}

    def invalidate_read_caches(self) -> None:
        self._company_universe_cache = None
        self._company_page_cache.clear()
        self._local_company_catalog_is_sufficient_cache = None
        self._company_filters_cache = None
        self._market_cap_index_cache = None
        self._market_cap_index_mtime = None
        self._sector_directory_cache.clear()
        self._health_snapshot_cache.clear()
        self._read_cache_data_version = None
        self._read_cache_checked_at = 0.0
        self.get_available_years.cache_clear()
        self.get_available_export_periods.cache_clear()
        self.suggest_companies.cache_clear()
        self.query_layer.get_sector_years_map.cache_clear()

    def _current_read_cache_data_version(self) -> int:
        if self.engine.dialect.name != "sqlite":
            return -1
        try:
            with self.engine.connect() as conn:
                value = conn.exec_driver_sql("PRAGMA data_version").scalar()
        except Exception:
            return -1
        return int(value or 0)

    def _ensure_read_cache_fresh(self) -> None:
        now = time.monotonic()
        if (
            self._read_cache_data_version is not None
            and now - self._read_cache_checked_at < self.READ_CACHE_VERSION_CHECK_SECONDS
        ):
            return

        data_version = self._current_read_cache_data_version()
        self._read_cache_checked_at = now
        if self._read_cache_data_version is None:
            self._read_cache_data_version = data_version
            return
        if data_version == self._read_cache_data_version:
            return
        self.invalidate_read_caches()
        self._read_cache_data_version = data_version

    @property
    def operational_service(self):
        if self._operational_service is None:
            from desktop.services import IntelligentSelectorService
            self._operational_service = IntelligentSelectorService(settings=self.settings)
        return self._operational_service

    @property
    def refresh_service(self) -> HeadlessRefreshService:
        if self._refresh_service is None:
            self._refresh_service = HeadlessRefreshService(settings=self.settings)
        return self._refresh_service

    @property
    def company_catalog(self) -> CompanyCatalogService:
        if self._company_catalog is None:
            self._company_catalog = CompanyCatalogService(
                timeout=self.settings.company_list_timeout
            )
        return self._company_catalog

    def resolve_batch_refresh_selection(
        self,
        params: dict[str, Any] | None = None,
        *,
        mode: str = "missing",
        default_start_year: int = 2010,
        max_page_size: int = BATCH_REFRESH_MAX_PAGE_SIZE,
    ) -> RefreshBatchSelection:
        return resolve_refresh_batch_selection(
            self,
            params,
            mode=mode,
            default_start_year=default_start_year,
            max_page_size=max_page_size,
        )

    def search_companies(self, search: str = "") -> list[CompanySearchResult]:
        df = self.query_layer.get_companies(search)
        return self._build_company_results(df)

    def search_companies_df(self, search: str = "") -> pd.DataFrame:
        rows = [row.to_dict() for row in self.search_companies(search)]
        return pd.DataFrame(rows)

    def get_company_info(
        self,
        cd_cvm: int,
        *,
        allow_catalog_lookup: bool = True,
    ) -> CompanyInfoDTO | None:
        payload = self.query_layer.get_company_info_with_read_model_state(cd_cvm)
        if payload:
            return self._apply_company_read_model_state(
                self._build_company_info_dto(payload, default_cd_cvm=cd_cvm),
                payload,
            )

        if not allow_catalog_lookup:
            return None

        catalog_entry = self.company_catalog.lookup_company(cd_cvm)
        if catalog_entry is None:
            return None
        return self._with_company_read_model_state(
            self._build_company_info_dto(
                self._company_catalog_payload(catalog_entry),
                default_cd_cvm=cd_cvm,
            )
        )

    def get_company_info_dict(self, cd_cvm: int) -> dict[str, Any]:
        info = self.get_company_info(cd_cvm)
        return info.to_dict() if info else {}

    @functools.lru_cache(maxsize=10)
    def get_available_years(self, cd_cvm: int) -> list[int]:
        return self.query_layer.get_available_years(cd_cvm)

    @functools.lru_cache(maxsize=10)
    def get_available_export_periods(self, cd_cvm: int) -> dict:
        """Returns annual DFP years and ITR-only years for export.

        Delegates to ``QueryLayer.get_available_export_periods``.  Result is
        cached per company for the lifetime of the service instance (same
        cache-clear policy as ``get_available_years``).
        """
        return self.query_layer.get_available_export_periods(cd_cvm)

    # Valid period scope identifiers accepted by build_company_excel_export.
    VALID_PERIOD_SCOPES: frozenset[str] = frozenset(
        {"last_3_years", "last_5_years", "last_10_years", "full_history"}
    )

    def resolve_excel_export_scope(self, cd_cvm: int, period_scope: str) -> dict:
        """Map a period_scope string to the concrete years and window needed.

        Parameters
        ----------
        cd_cvm : int
        period_scope : str
            One of ``last_3_years``, ``last_5_years``, ``last_10_years``,
            ``full_history``.

        Returns
        -------
        dict with keys:
          all_export_years  — list[int] to pass as ``years`` when loading data
          period_window     — (annuals, quarters_per_year) for ExcelExporter
          scope_label       — human-readable string for workbook metadata
          itr_only_years    — list[int] of ITR-only years included
        """
        _SCOPE_LABELS = {
            "last_3_years":  "Last 3 years",
            "last_5_years":  "Last 5 years",
            "last_10_years": "Last 10 years",
            "full_history":  "Full history",
        }
        _SCOPE_N = {
            "last_3_years":  3,
            "last_5_years":  5,
            "last_10_years": 10,
        }

        if period_scope not in self.VALID_PERIOD_SCOPES:
            raise ValueError(
                f"Invalid period_scope: {period_scope!r}. "
                f"Must be one of: {', '.join(sorted(self.VALID_PERIOD_SCOPES))}"
            )

        periods = self.get_available_export_periods(cd_cvm)
        annual_years: list[int] = periods["annual_years"]
        itr_only_years: list[int] = periods["itr_only_years"]

        scope_label = _SCOPE_LABELS.get(period_scope, period_scope)

        if period_scope == "full_history":
            n_annuals = len(annual_years)
        else:
            n_annuals = _SCOPE_N.get(period_scope, 5)

        # Slice the last N annual years according to scope.
        selected_annual_years = annual_years[-n_annuals:] if n_annuals > 0 else annual_years

        # Always include ITR-only years that are newer than the latest selected
        # annual year — this is the core "current-year ITR inclusion" guarantee.
        max_selected_annual = max(selected_annual_years, default=0)
        included_itr_only = [y for y in itr_only_years if y > max_selected_annual]

        all_export_years = sorted(set(selected_annual_years) | set(included_itr_only))

        # period_window controls how _pick_model_periods slices the data.
        # annuals = number of annual periods to show; quarters_per_year = 4.
        # When there are no annual years (ITR-only company), use 0 so
        # _pick_model_periods falls through to the ITR-only branch.
        annuals_for_window = n_annuals if annual_years else 0

        return {
            "all_export_years": all_export_years,
            "period_window": (annuals_for_window, 4),
            "scope_label": scope_label,
            "itr_only_years": included_itr_only,
        }

    def get_available_statements(self, cd_cvm: int) -> list[str]:
        return self.query_layer.get_available_statements(cd_cvm)

    @staticmethod
    def _company_catalog_payload(entry: CompanyCatalogEntry) -> dict[str, Any]:
        return {
            "cd_cvm": int(entry.cd_cvm),
            "company_name": entry.company_name,
            "nome_comercial": entry.nome_comercial,
            "cnpj": entry.cnpj,
            "setor_cvm": entry.setor_cvm,
            "setor_analitico": None,
            "company_type": "comercial",
            "ticker_b3": entry.ticker_b3,
        }

    @staticmethod
    def _build_company_info_dto(
        payload: dict[str, Any],
        *,
        default_cd_cvm: int,
    ) -> CompanyInfoDTO:
        sector_name = canonical_sector_name(
            payload.get("setor_analitico"),
            payload.get("setor_cvm"),
        )
        company_name = str(payload.get("company_name") or "").strip() or f"CVM_{default_cd_cvm}"
        company_type = str(payload.get("company_type") or "comercial").strip() or "comercial"
        gics = resolve_gics_classification(
            sector_name=sector_name,
            setor_analitico=payload.get("setor_analitico"),
            setor_cvm=payload.get("setor_cvm"),
            gics_sector=payload.get("gics_sector"),
            gics_sector_slug=payload.get("gics_sector_slug"),
            gics_industry_group=payload.get("gics_industry_group"),
            gics_industry=payload.get("gics_industry"),
            gics_sub_industry=payload.get("gics_sub_industry"),
        )
        return CompanyInfoDTO(
            cd_cvm=int(payload.get("cd_cvm") or default_cd_cvm),
            company_name=company_name,
            nome_comercial=payload.get("nome_comercial"),
            cnpj=payload.get("cnpj"),
            setor_cvm=payload.get("setor_cvm"),
            setor_analitico=payload.get("setor_analitico"),
            sector_name=sector_name,
            sector_slug=sector_slugify(sector_name),
            company_type=company_type,
            ticker_b3=payload.get("ticker_b3"),
            gics_sector=gics.gics_sector if gics else None,
            gics_sector_slug=gics.gics_sector_slug if gics else None,
            gics_industry_group=gics.gics_industry_group if gics else None,
            gics_industry=gics.gics_industry if gics else None,
            gics_sub_industry=gics.gics_sub_industry if gics else None,
        )

    def _with_company_read_model_state(self, dto: CompanyInfoDTO) -> CompanyInfoDTO:
        state = self._load_company_read_model_state_map([dto.cd_cvm]).get(
            int(dto.cd_cvm),
            {},
        )
        return self._apply_company_read_model_state(dto, state)

    def _apply_company_read_model_state(
        self,
        dto: CompanyInfoDTO,
        state: dict[str, Any],
    ) -> CompanyInfoDTO:
        readable_years_count = int(state.get("readable_years_count") or 0)
        latest_readable_year = (
            int(state["latest_readable_year"])
            if state.get("latest_readable_year") is not None
            else None
        )
        read_availability = self._build_read_availability_summary(
            has_readable_current_data=bool(state.get("has_readable_current_data")),
            readable_years_count=readable_years_count,
            latest_readable_year=latest_readable_year,
        )
        raw_local = state.get("has_local_financial_reports")
        has_local_financial_reports = (
            bool(raw_local) if raw_local is not None else dto.has_local_financial_reports
        )
        return replace(
            dto,
            read_model_updated_at=state.get("read_model_updated_at"),
            has_local_financial_reports=has_local_financial_reports,
            has_readable_current_data=bool(state.get("has_readable_current_data")),
            readable_years_count=readable_years_count,
            latest_readable_year=latest_readable_year,
            read_availability_code=read_availability["code"],
            read_availability_message=read_availability["message"],
        )

    def _ensure_company_catalog_metadata(self, cd_cvm: int) -> bool:
        if self.query_layer.get_company_info(cd_cvm):
            return False

        catalog_entry = self.company_catalog.lookup_company(cd_cvm)
        if catalog_entry is None:
            return False

        now_iso = now_iso_seconds()
        gics = resolve_gics_classification(
            sector_name=canonical_sector_name(None, catalog_entry.setor_cvm),
            setor_analitico=None,
            setor_cvm=catalog_entry.setor_cvm,
        )
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO companies (
                        cd_cvm,
                        company_name,
                        nome_comercial,
                        cnpj,
                        setor_cvm,
                        gics_sector,
                        gics_sector_slug,
                        gics_industry_group,
                        gics_industry,
                        gics_sub_industry,
                        company_type,
                        ticker_b3,
                        is_active,
                        updated_at
                    ) VALUES (
                        :cd_cvm,
                        :company_name,
                        :nome_comercial,
                        :cnpj,
                        :setor_cvm,
                        :gics_sector,
                        :gics_sector_slug,
                        :gics_industry_group,
                        :gics_industry,
                        :gics_sub_industry,
                        :company_type,
                        :ticker_b3,
                        :is_active,
                        :updated_at
                    )
                    ON CONFLICT(cd_cvm) DO UPDATE SET
                        company_name = excluded.company_name,
                        nome_comercial = COALESCE(excluded.nome_comercial, companies.nome_comercial),
                        cnpj = COALESCE(excluded.cnpj, companies.cnpj),
                        setor_cvm = COALESCE(excluded.setor_cvm, companies.setor_cvm),
                        gics_sector = COALESCE(excluded.gics_sector, companies.gics_sector),
                        gics_sector_slug = COALESCE(excluded.gics_sector_slug, companies.gics_sector_slug),
                        gics_industry_group = COALESCE(excluded.gics_industry_group, companies.gics_industry_group),
                        gics_industry = COALESCE(excluded.gics_industry, companies.gics_industry),
                        gics_sub_industry = COALESCE(excluded.gics_sub_industry, companies.gics_sub_industry),
                        company_type = COALESCE(excluded.company_type, companies.company_type),
                        ticker_b3 = COALESCE(excluded.ticker_b3, companies.ticker_b3),
                        is_active = excluded.is_active,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "cd_cvm": int(catalog_entry.cd_cvm),
                    "company_name": catalog_entry.company_name,
                    "nome_comercial": catalog_entry.nome_comercial,
                    "cnpj": catalog_entry.cnpj,
                    "setor_cvm": catalog_entry.setor_cvm,
                    "gics_sector": gics.gics_sector if gics else None,
                    "gics_sector_slug": gics.gics_sector_slug if gics else None,
                    "gics_industry_group": gics.gics_industry_group if gics else None,
                    "gics_industry": gics.gics_industry if gics else None,
                    "gics_sub_industry": gics.gics_sub_industry if gics else None,
                    "company_type": "comercial",
                    "ticker_b3": catalog_entry.ticker_b3,
                    "is_active": 1 if catalog_entry.is_active else 0,
                    "updated_at": now_iso,
                },
            )
        return True

    # ------------------------------------------------------------------
    # Market-cap enrichment helpers
    # ------------------------------------------------------------------

    def _load_market_cap_index(
        self,
    ) -> tuple[dict[int, Any], dict[str, Any], list[Any]] | None:
        """Load snapshot into (by_cd_cvm, by_ticker_stripped, all_entries).

        Returns None when no snapshot exists, the file is malformed, or any
        error occurs — callers must gracefully fall back to existing sort.
        File mtime gates re-parsing so parsing is skipped on repeated calls
        with an unchanged CSV.
        """
        from pathlib import Path as _Path  # noqa: PLC0415

        snapshot_path = _Path(self.settings.paths.company_universe_snapshot_path)
        if not snapshot_path.exists():
            return None
        try:
            mtime = snapshot_path.stat().st_mtime
        except OSError:
            return None

        if (
            self._market_cap_index_cache is not None
            and self._market_cap_index_mtime == mtime
        ):
            return self._market_cap_index_cache

        try:
            from src.market_cap import MarketCapService  # noqa: PLC0415

            entries = MarketCapService(settings=self.settings).read_snapshot()
        except Exception as exc:
            import logging as _logging  # noqa: PLC0415
            _logging.getLogger(__name__).warning(
                "market-cap index load failed, skipping sort: %s", exc
            )
            return None

        if not entries:
            return None

        by_cd_cvm: dict[int, Any] = {}
        by_ticker: dict[str, Any] = {}
        for entry in entries:
            if entry.cd_cvm is not None:
                by_cd_cvm[entry.cd_cvm] = entry
            if entry.ticker:
                # Strip .SA suffix so "PETR4.SA" → "PETR4" matches ticker_b3 "PETR4"
                by_ticker[entry.ticker.replace(".SA", "").upper()] = entry

        self._market_cap_index_cache = (by_cd_cvm, by_ticker, entries)
        self._market_cap_index_mtime = mtime
        return self._market_cap_index_cache

    def _list_companies_with_market_cap_sort(
        self,
        *,
        search: str,
        sector_slug: str | None,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage | None:
        """Return a Companies page sorted by market-cap descending.

        Uses the local snapshot — no network calls.  Falls back (returns None)
        when the snapshot is unavailable or unreadable so the caller can
        transparently use the existing sort path.
        """
        idx = self._load_market_cap_index()
        if idx is None:
            return None

        by_cd_cvm, by_ticker, all_entries = idx
        # Always use the full catalog merge so every known company is visible,
        # regardless of how many have been downloaded (DB threshold bypassed).
        all_items = self._merge_catalog_with_db()

        normalized_search = str(search or "").strip().lower()
        normalized_sector_slug = str(sector_slug or "").strip().lower() or None

        # Filter DB companies
        filtered: list[CompanySearchResult] = []
        for item in all_items:
            if normalized_sector_slug and item.sector_slug != normalized_sector_slug:
                continue
            if normalized_search:
                tokens = [
                    item.company_name.lower(),
                    (item.ticker_b3 or "").lower(),
                    str(item.cd_cvm),
                ]
                if not any(normalized_search in t for t in tokens if t):
                    continue
            filtered.append(item)

        # Enrich DB companies with market cap; also fill ticker from snapshot when DB
        # has none (DFP import does not carry B3 ticker data).
        enriched: list[CompanySearchResult] = []
        mapped_count = 0
        for item in filtered:
            entry = by_cd_cvm.get(item.cd_cvm)
            if entry is None and item.ticker_b3:
                # DB may store ticker with or without .SA suffix — normalise
                ticker_key = item.ticker_b3.upper().replace(".SA", "")
                entry = by_ticker.get(ticker_key)
            if entry is not None:
                mapped_count += 1
                snap_ticker = (
                    entry.ticker.replace(".SA", "").upper()
                    if entry.ticker
                    else None
                )
                item = replace(
                    item,
                    # Use snapshot ticker as fallback when DB ticker is null
                    ticker_b3=item.ticker_b3 or snap_ticker,
                    market_cap_brl=entry.market_cap_brl,
                    market_cap_rank=entry.rank,
                    market_cap_as_of_date=entry.as_of_date,
                    market_cap_source=entry.source,
                    market_cap_provider_status=entry.provider_status,
                )
            enriched.append(item)

        # Sort:
        #  1. Mapped companies → market_cap_brl DESC
        #  2. Unmapped but has financial data → matches old "data-first" UX
        #  3. Unmapped / no data → company_name ASC
        # Tier 2 preserves the pre-existing sort for companies not in the snapshot
        # (they have tickers/sectors; pure catalog stubs usually don't).
        enriched.sort(
            key=lambda c: (
                0 if c.market_cap_brl is not None else 1,
                -(c.market_cap_brl or 0.0),
                0 if c.has_financial_data else 1,
                c.company_name.lower(),
            )
        )

        # Snapshot-level metadata (from first entry — all share same date/source)
        meta = None
        if all_entries and len(all_entries) > 0:
            e0 = all_entries[0]
            from src.contracts import MarketCapSortMeta  # noqa: PLC0415

            meta = MarketCapSortMeta(
                as_of_date=e0.as_of_date,
                source=e0.source,
                provider_status=e0.provider_status,
                mapped_count=len(all_entries),
                total_in_snapshot=len(all_entries),
            )

        # Paginate
        total_items = len(enriched)
        start = max(0, (int(page) - 1) * int(page_size))
        end = start + int(page_size)
        total_pages = max(1, ((total_items - 1) // int(page_size)) + 1) if total_items else 1
        return CompanyDirectoryPage(
            items=tuple(enriched[start:end]),
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=total_items,
                total_pages=total_pages,
                has_next=int(page) < total_pages,
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
            market_cap_sort_meta=meta,
        )

    def list_companies(
        self,
        *,
        search: str = "",
        sector_slug: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CompanyDirectoryPage:
        self._ensure_read_cache_fresh()
        resolved_sector_name = self._resolve_sector_slug(sector_slug)
        if sector_slug and resolved_sector_name is None:
            return self._empty_company_page(
                search=search,
                sector_slug=sector_slug,
                page=page,
                page_size=page_size,
            )
        if resolved_sector_name in GICS_11_SECTORS:
            return self._list_companies_by_gics_sector(
                search=search,
                sector_slug=sector_slug,
                gics_sector=resolved_sector_name,
                page=page,
                page_size=page_size,
            )

        # Try market-cap-sorted path when local snapshot is available.
        # Falls back transparently when snapshot is missing, malformed, or empty.
        mkt_page = self._list_companies_with_market_cap_sort(
            search=search,
            sector_slug=sector_slug,
            page=page,
            page_size=page_size,
        )
        if mkt_page is not None:
            return mkt_page

        catalog_page = self._list_companies_from_catalog(
            search=search,
            sector_slug=sector_slug,
            page=page,
            page_size=page_size,
        )
        if catalog_page is not None:
            return catalog_page

        rows_df, total_items = self.query_layer.get_companies_directory_page(
            search=search,
            sector_name=resolved_sector_name,
            page=page,
            page_size=page_size,
        )
        years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist()) if not rows_df.empty else {}
        if not rows_df.empty:
            rows_df = rows_df.copy()
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(lambda cd_cvm: years_map.get(int(cd_cvm), ()))
            try:
                from sqlalchemy import text as _sa_text  # noqa: PLC0415
                import pandas as _pd  # noqa: PLC0415
                failed_df = _pd.read_sql(
                    _sa_text(
                        "SELECT cd_cvm FROM company_refresh_status "
                        "WHERE last_status IN ('error', 'failed', 'dispatch_failed')"
                    ),
                    self.query_layer.engine,
                )
                if not failed_df.empty:
                    failed_set = frozenset(int(x) for x in failed_df["cd_cvm"].dropna())
                    rows_df.loc[rows_df["cd_cvm"].isin(failed_set), "data_status"] = "failed"
            except Exception:
                pass

        total_pages = max(1, ((int(total_items) - 1) // int(page_size)) + 1) if total_items else 1
        pagination = CompanyDirectoryPagination(
            page=int(page),
            page_size=int(page_size),
            total_items=int(total_items),
            total_pages=int(total_pages),
            has_next=int(page) < int(total_pages),
            has_previous=int(page) > 1,
        )
        return CompanyDirectoryPage(
            items=tuple(self._build_company_results(rows_df)),
            pagination=pagination,
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )

    def _list_companies_from_catalog(
        self,
        *,
        search: str,
        sector_slug: str | None,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage | None:
        normalized_search = str(search or "").strip().lower()
        normalized_sector_slug = str(sector_slug or "").strip().lower() or None
        if normalized_sector_slug is None and self._has_sufficient_local_company_catalog():
            local_page = self._list_local_company_page(
                search=search,
                sector_slug=sector_slug,
                page=page,
                page_size=page_size,
            )
            return local_page

        universe_items = self._list_company_universe_results()
        if not universe_items:
            return None

        filtered: list[CompanySearchResult] = []
        for item in universe_items:
            current_sector_slug = item.sector_slug
            if normalized_sector_slug and current_sector_slug != normalized_sector_slug:
                continue

            if normalized_search:
                tokens = [
                    item.company_name.lower(),
                    (item.ticker_b3 or "").lower(),
                    str(item.cd_cvm),
                ]
                if not any(normalized_search in token for token in tokens if token):
                    continue
            filtered.append(item)

        filtered.sort(key=lambda item: (0 if item.has_financial_data else 1, item.company_name.lower()))
        total_items = len(filtered)
        if total_items == 0:
            return self._empty_company_page(
                search=search,
                sector_slug=sector_slug,
                page=page,
                page_size=page_size,
            )

        start = max(0, (int(page) - 1) * int(page_size))
        end = start + int(page_size)
        page_items = tuple(filtered[start:end])
        total_pages = max(1, ((int(total_items) - 1) // int(page_size)) + 1)
        return CompanyDirectoryPage(
            items=page_items,
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=int(total_items),
                total_pages=int(total_pages),
                has_next=int(page) < int(total_pages),
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )

    def _list_local_company_page(
        self,
        *,
        search: str,
        sector_slug: str | None,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage:
        cache_key = (
            str(search or "").strip().lower(),
            str(sector_slug).strip().lower() if sector_slug else None,
            int(page),
            int(page_size),
        )
        cached = self._company_page_cache.get(cache_key)
        if cached is not None:
            return cached

        rows_df, total_items = self.query_layer.get_companies_directory_page(
            search=search,
            sector_name=None,
            page=page,
            page_size=page_size,
        )
        if not rows_df.empty:
            rows_df = rows_df.copy()
            years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist())
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(
                lambda cd_cvm: years_map.get(int(cd_cvm), ())
            )
        total_pages = max(1, ((int(total_items) - 1) // int(page_size)) + 1) if total_items else 1
        result = CompanyDirectoryPage(
            items=tuple(self._build_company_results(rows_df)),
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=int(total_items),
                total_pages=int(total_pages),
                has_next=int(page) < int(total_pages),
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )
        self._company_page_cache[cache_key] = result
        return result

    def _has_sufficient_local_company_catalog(self) -> bool:
        if self._local_company_catalog_is_sufficient_cache is None:
            self._local_company_catalog_is_sufficient_cache = (
                len(self._load_local_active_company_rows())
                >= self.CATALOG_FALLBACK_MIN_LOCAL_COMPANIES
            )
        return self._local_company_catalog_is_sufficient_cache

    def get_populares_companies(self) -> CompanyDirectoryPage:
        """Returns top-10 B3 companies by market cap in static rank order.

        The ranking is maintained in POPULARES_CVM_IDS. Companies missing from
        the local DB (e.g. during seeding) are silently omitted.
        """
        ids = list(POPULARES_CVM_IDS)
        rows_df = self.query_layer.get_companies_by_cvm_ids(ids)
        if not rows_df.empty:
            order_map = {cd: i for i, cd in enumerate(ids)}
            rows_df = rows_df.copy()
            rows_df["_order"] = rows_df["cd_cvm"].map(lambda x: order_map.get(int(x), 999))
            rows_df = rows_df.sort_values("_order").drop(columns=["_order"]).reset_index(drop=True)
            years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist())
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(lambda cd: years_map.get(int(cd), ()))
        n = len(rows_df)
        return CompanyDirectoryPage(
            items=tuple(self._build_company_results(rows_df)),
            pagination=CompanyDirectoryPagination(
                page=1, page_size=n, total_items=n,
                total_pages=1, has_next=False, has_previous=False,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(search="", sector=None),
        )

    def get_em_destaque_companies(self, limit: int = 10) -> CompanyDirectoryPage:
        """Returns companies most visited globally, ordered by view_count DESC.

        Falls back gracefully to coverage_rank ordering when the company_views
        table is empty (e.g. immediately after deployment).
        """
        rows_df = self.query_layer.get_top_viewed_companies(limit=limit)
        if not rows_df.empty:
            rows_df = rows_df.copy()
            years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist())
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(lambda cd: years_map.get(int(cd), ()))
        n = len(rows_df)
        return CompanyDirectoryPage(
            items=tuple(self._build_company_results(rows_df)),
            pagination=CompanyDirectoryPagination(
                page=1, page_size=n, total_items=n,
                total_pages=1, has_next=False, has_previous=False,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(search="", sector=None),
        )

    def record_company_view(self, cd_cvm: int) -> None:
        """Increments the global view counter for a company.

        Uses an upsert so the call is idempotent and safe under concurrent
        writes. Silently ignores unknown cd_cvm values (FK constraint skips
        the insert rather than raising).
        """
        now_iso = now_iso_seconds()
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO company_views (cd_cvm, view_count, last_viewed_at)
                        VALUES (:cd, 1, :now)
                        ON CONFLICT(cd_cvm) DO UPDATE SET
                            view_count     = company_views.view_count + 1,
                            last_viewed_at = :now
                    """),
                    {"cd": int(cd_cvm), "now": now_iso},
                )
        except Exception:
            # Analytics must never break the API — log and continue
            import logging
            logging.getLogger(__name__).warning(
                "record_company_view failed for cd_cvm=%s", cd_cvm, exc_info=True
            )

    def get_company_filters(self) -> CompanyFiltersDTO:
        self._ensure_read_cache_fresh()
        if self._company_filters_cache is not None:
            return self._company_filters_cache

        sector_counts: dict[str, int] = defaultdict(int)
        for item in self._list_company_universe_results():
            if item.gics_sector and item.gics_sector in GICS_11_SECTORS:
                sector_counts[item.gics_sector] += 1

        sectors_list: list[CompanySectorFilterOption] = []
        for sector_name, company_count in sorted(sector_counts.items(), key=lambda item: gics_sector_sort_key(item[0])):
            sectors_list.append(
                CompanySectorFilterOption(
                    sector_name=sector_name,
                    sector_slug=sector_slugify(sector_name),
                    company_count=int(company_count),
                    gics_sector=sector_name,
                    gics_sector_slug=sector_slugify(sector_name),
                )
            )
        sectors = tuple(sectors_list)
        self._company_filters_cache = CompanyFiltersDTO(sectors=sectors)
        return self._company_filters_cache

    @staticmethod
    def _histogram_bucket_from_directory_row(row: pd.Series) -> str:
        """Align with query_layer._sector_bucket_expression_sql (persisted GICS over canonical setor)."""
        persisted = CVMReadService._clean_optional_text(row.get("persisted_gics_sector"))
        canonical = CVMReadService._clean_optional_text(row.get("sector_name"))
        if persisted:
            return persisted
        return canonical or "Nao classificado"

    @staticmethod
    def _hub_gics_key_for_histogram_bucket(bucket_label: str) -> str | None:
        """Histogram bucket label -> GICS 11 hub key (same resolution as filters / sector routing)."""
        return resolve_gics_sector_name(
            sector_name=bucket_label,
            setor_analitico=bucket_label,
            setor_cvm=bucket_label,
        )

    def _filter_directory_rows_by_hub_gics(
        self,
        rows_df: pd.DataFrame,
        hub_gics_sector: str,
    ) -> pd.DataFrame:
        if rows_df.empty:
            return rows_df

        def _row_matches(row: pd.Series) -> bool:
            bucket = self._histogram_bucket_from_directory_row(row)
            hub_key = self._hub_gics_key_for_histogram_bucket(bucket)
            return hub_key == hub_gics_sector

        mask = rows_df.apply(_row_matches, axis=1)
        return rows_df.loc[mask].reset_index(drop=True)

    @functools.lru_cache(maxsize=128)
    def suggest_companies(
        self,
        q: str,
        limit: int,
        *,
        ready_only: bool = False,
    ) -> tuple[CompanySuggestionDTO, ...]:
        df = self.query_layer.get_company_suggestions(
            q=q,
            limit=limit,
            ready_only=ready_only,
        )
        def _clean_gics(value: object) -> str | None:
            if value is None:
                return None
            text_value = str(value).strip()
            return text_value or None

        local_items = tuple(
            CompanySuggestionDTO(
                cd_cvm=int(row["cd_cvm"]),
                company_name=str(row["company_name"]),
                ticker_b3=str(row["ticker_b3"]) if row["ticker_b3"] else None,
                sector_slug=sector_slugify(str(row["sector_name"])),
                gics_sector=_clean_gics(row.get("gics_sector")),
                gics_sector_slug=_clean_gics(row.get("gics_sector_slug")),
            )
            for _, row in df.iterrows()
        )
        if ready_only or not str(q or "").strip() or len(local_items) >= int(limit):
            return local_items[: int(limit)]

        seen_codes = {item.cd_cvm for item in local_items}
        try:
            catalog_items = self.company_catalog.search_companies(
                q=q,
                limit=max(0, int(limit) - len(local_items)),
                exclude_codes=seen_codes,
            )
        except CompanyCatalogUnavailableError:
            return local_items[: int(limit)]

        fallback_items = tuple(
            CompanySuggestionDTO(
                cd_cvm=int(entry.cd_cvm),
                company_name=entry.company_name,
                ticker_b3=entry.ticker_b3,
                sector_slug=sector_slugify(
                    canonical_sector_name(None, entry.setor_cvm)
                ),
            )
            for entry in catalog_items
        )
        return (local_items + fallback_items)[: int(limit)]

    def resolve_sector_slug(self, sector_slug: str | None) -> str | None:
        return self._resolve_sector_slug(sector_slug)

    def list_sectors(self, group_by: str = "sector") -> SectorDirectoryDTO:
        self._ensure_read_cache_fresh()
        normalized_group_by = str(group_by or "sector").strip().lower()
        if normalized_group_by in {"subsector", "sub-sector", "sub_setor", "sub-setor"}:
            normalized_group_by = "sub_sector"
        if normalized_group_by not in {"sector", "sub_sector"}:
            normalized_group_by = "sector"
        cached = self._sector_directory_cache.get(normalized_group_by)
        if cached is not None:
            return cached

        # Full unpaged directory so hub counts match the entire `companies` universe (not capped at
        # BATCH_REFRESH_MAX_PAGE_SIZE used for refresh batching).
        company_items = self._list_company_universe_results()
        companies_by_gics: dict[str, list[CompanySearchResult]] = defaultdict(list)
        companies_by_sub_sector: dict[str, list[CompanySearchResult]] = defaultdict(list)
        hub_counts: dict[str, int] = defaultdict(int)
        sub_industries_by_gics: dict[str, set[str]] = defaultdict(set)
        sub_industry_counts_by_gics: dict[str, Counter] = defaultdict(Counter)
        unclassified_items: list[CompanySearchResult] = []
        for item in company_items:
            sector_hub = item.gics_sector
            if not sector_hub or sector_hub not in GICS_11_SECTORS:
                unclassified_items.append(item)
                continue
            hub_counts[sector_hub] += 1
            companies_by_gics[sector_hub].append(item)
            if item.gics_sub_industry:
                sub_industries_by_gics[sector_hub].add(item.gics_sub_industry)
                sub_industry_counts_by_gics[sector_hub][item.gics_sub_industry] += 1
                companies_by_sub_sector[item.gics_sub_industry].append(item)

        metric_rows = self.query_layer.get_sector_metric_rows()
        if metric_rows is not None and not metric_rows.empty and company_items:
            gics_by_cd_cvm = {
                int(item.cd_cvm): item.gics_sector
                for item in company_items
                if item.gics_sector
            }
            metric_rows = metric_rows.copy()
            metric_rows["sector_name"] = metric_rows["cd_cvm"].map(
                lambda code: gics_by_cd_cvm.get(int(code))
            )
            metric_rows = metric_rows.dropna(subset=["sector_name"])
        yearly = self._aggregate_sector_yearly_metrics(metric_rows)

        latest_snapshot_by_sector: dict[str, tuple[int, pd.Series]] = {}
        if not yearly.empty:
            for sector_name, group_df in yearly.groupby("sector_name", dropna=False):
                if group_df.empty:
                    continue
                latest_idx = group_df["year"].astype(int).idxmax()
                latest_row = group_df.loc[latest_idx]
                latest_snapshot_by_sector[str(sector_name)] = (
                    int(latest_row["year"]),
                    latest_row,
                )

        items: list[SectorDirectoryItemDTO] = []

        if normalized_group_by == "sub_sector":
            for sub_sector_name, sub_items in sorted(companies_by_sub_sector.items(), key=lambda item: item[0]):
                parent_counts = Counter(item.gics_sector for item in sub_items if item.gics_sector)
                parent_sector_name = str(parent_counts.most_common(1)[0][0]) if parent_counts else None
                latest_year, snapshot_row = latest_snapshot_by_sector.get(
                    parent_sector_name or "",
                    (None, None),
                )
                items.append(
                    SectorDirectoryItemDTO(
                        sector_name=sub_sector_name,
                        sector_slug=sector_slugify(sub_sector_name),
                        company_count=len(sub_items),
                        latest_year=latest_year,
                        snapshot=SectorSnapshotDTO(
                            roe=self._coerce_optional_float(snapshot_row["roe"]) if snapshot_row is not None else None,
                            mg_ebit=self._coerce_optional_float(snapshot_row["mg_ebit"]) if snapshot_row is not None else None,
                            mg_liq=self._coerce_optional_float(snapshot_row["mg_liq"]) if snapshot_row is not None else None,
                        ),
                        group_type="sub_sector",
                        parent_sector_name=parent_sector_name,
                        parent_sector_slug=sector_slugify(parent_sector_name) if parent_sector_name else None,
                        companies=self._sector_company_preview(sub_items),
                    )
                )
        else:
            candidate_sector_names = sorted(
                {name for name, count in hub_counts.items() if count > 0 and name in GICS_11_SECTORS},
                key=gics_sector_sort_key,
            )
            for sector_name in candidate_sector_names:
                latest_year, snapshot_row = latest_snapshot_by_sector.get(
                    sector_name,
                    (None, None),
                )
                company_count = int(hub_counts.get(sector_name, 0))
                breakdown_counter = sub_industry_counts_by_gics.get(sector_name, Counter())
                breakdown = tuple(
                    SubIndustryCountDTO(name=name, count=int(count))
                    for name, count in sorted(
                        breakdown_counter.items(),
                        key=lambda item: (-int(item[1]), str(item[0])),
                    )
                )
                items.append(
                    SectorDirectoryItemDTO(
                        sector_name=sector_name,
                        sector_slug=sector_slugify(sector_name),
                        company_count=company_count,
                        latest_year=latest_year,
                        snapshot=SectorSnapshotDTO(
                            roe=self._coerce_optional_float(snapshot_row["roe"]) if snapshot_row is not None else None,
                            mg_ebit=self._coerce_optional_float(snapshot_row["mg_ebit"]) if snapshot_row is not None else None,
                            mg_liq=self._coerce_optional_float(snapshot_row["mg_liq"]) if snapshot_row is not None else None,
                        ),
                        sub_industries=tuple(sorted(sub_industries_by_gics.get(sector_name, ()))),
                        sub_industry_breakdown=breakdown,
                        group_type="sector",
                        companies=self._sector_company_preview(companies_by_gics.get(sector_name, [])),
                    )
                )

        if unclassified_items:
            items.append(
                SectorDirectoryItemDTO(
                    sector_name="Sem classificacao GICS",
                    sector_slug="sem-classificacao-gics",
                    company_count=len(unclassified_items),
                    latest_year=None,
                    snapshot=SectorSnapshotDTO(roe=None, mg_ebit=None, mg_liq=None),
                    group_type="unclassified",
                    companies=self._sector_company_preview(unclassified_items),
                )
            )

        items.sort(key=lambda item: gics_sector_sort_key(item.sector_name))
        result = SectorDirectoryDTO(items=tuple(items))
        self._sector_directory_cache[normalized_group_by] = result
        return result

    def _list_companies_by_gics_sector(
        self,
        *,
        search: str,
        sector_slug: str | None,
        gics_sector: str,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage:
        normalized_search = str(search or "").strip().lower()
        filtered = [
            item
            for item in self._list_company_universe_results()
            if item.gics_sector == gics_sector
            and (
                not normalized_search
                or normalized_search in item.company_name.lower()
                or normalized_search in (item.ticker_b3 or "").lower()
                or normalized_search in str(item.cd_cvm)
            )
        ]
        total_items = len(filtered)
        start = max(0, (int(page) - 1) * int(page_size))
        end = start + int(page_size)
        total_pages = max(1, ((total_items - 1) // int(page_size)) + 1) if total_items else 1
        return CompanyDirectoryPage(
            items=tuple(filtered[start:end]),
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=int(total_items),
                total_pages=int(total_pages),
                has_next=int(page) < int(total_pages),
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )

    def get_sector_detail(self, sector_slug: str, year: int | None = None) -> SectorDetailDTO | None:
        resolved_sector_name = self._resolve_sector_slug(sector_slug)
        if resolved_sector_name is None:
            return None

        if resolved_sector_name in GICS_11_SECTORS:
            company_items = [
                item
                for item in self._list_company_universe_results()
                if item.gics_sector == resolved_sector_name
            ]
            if not company_items:
                return None
            total_items = len(company_items)
            company_rows = pd.DataFrame(
                [
                    {
                        "cd_cvm": int(item.cd_cvm),
                        "company_name": str(item.company_name),
                        "ticker_b3": item.ticker_b3,
                        "anos_disponiveis": tuple(item.anos_disponiveis),
                        "gics_sub_industry": item.gics_sub_industry,
                    }
                    for item in company_items
                ]
            )
        else:
            return None

        if "anos_disponiveis" not in company_rows.columns:
            years_map = self.query_layer.get_company_years_map(company_rows["cd_cvm"].tolist())
            company_rows = company_rows.copy()
            company_rows["anos_disponiveis"] = company_rows["cd_cvm"].map(
                lambda cd_cvm: years_map.get(int(cd_cvm), ())
            )
        if "gics_sub_industry" not in company_rows.columns:
            company_rows = company_rows.copy()
            company_rows["gics_sub_industry"] = None
        available_years = self._extract_years_from_company_rows(company_rows)
        if not available_years:
            selected_year = int(year or datetime.now(timezone.utc).year - 1)
            return SectorDetailDTO(
                sector_name=resolved_sector_name,
                sector_slug=sector_slugify(resolved_sector_name),
                company_count=int(total_items),
                available_years=(),
                selected_year=selected_year,
                yearly_overview=(),
                companies=tuple(
                    SectorCompanyMetricDTO(
                        cd_cvm=int(row["cd_cvm"]),
                        company_name=str(row["company_name"]),
                        ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                        gics_sub_industry=self._clean_optional_text(row.get("gics_sub_industry")),
                        roe=None,
                        mg_ebit=None,
                        mg_liq=None,
                    )
                    for _, row in company_rows.sort_values("company_name").iterrows()
                ),
            )

        if year is None:
            selected_year = max(available_years)
        else:
            selected_year = int(year)
            if selected_year not in available_years:
                raise ValueError(
                    f"O parametro 'year' precisa ser um dos anos disponiveis do setor: {', '.join(str(value) for value in available_years)}."
                )

        if resolved_sector_name in GICS_11_SECTORS:
            metric_rows = self.query_layer.get_sector_metric_rows()
            company_codes = {int(value) for value in company_rows["cd_cvm"].tolist()}
            if metric_rows is None or metric_rows.empty:
                metric_rows = pd.DataFrame(
                    columns=["cd_cvm", "report_year", "roe", "mg_ebit", "mg_liq", "sector_name"]
                )
            else:
                metric_rows = metric_rows[metric_rows["cd_cvm"].map(lambda code: int(code) in company_codes)].copy()
                metric_rows["sector_name"] = resolved_sector_name
        else:
            metric_rows = self.query_layer.get_sector_metric_rows(sector_name=resolved_sector_name)
        yearly = self._aggregate_sector_yearly_metrics(metric_rows)
        yearly_overview = tuple(
            SectorYearOverviewDTO(
                year=int(row["year"]),
                roe=self._coerce_optional_float(row["roe"]),
                mg_ebit=self._coerce_optional_float(row["mg_ebit"]),
                mg_liq=self._coerce_optional_float(row["mg_liq"]),
            )
            for _, row in yearly[yearly["sector_name"] == resolved_sector_name]
            .sort_values("year")
            .iterrows()
        )

        company_metrics = metric_rows[metric_rows["report_year"] == selected_year].copy()
        selected_companies = company_rows[
            company_rows["anos_disponiveis"].map(lambda years: selected_year in years)
        ][["cd_cvm", "company_name", "ticker_b3", "gics_sub_industry"]].drop_duplicates()
        selected_companies = selected_companies.merge(
            company_metrics[
                ["cd_cvm", "roe", "mg_ebit", "mg_liq"]
            ],
            on="cd_cvm",
            how="left",
        )
        selected_companies["ticker_b3"] = selected_companies["ticker_b3"].replace("", None)
        selected_companies["sort_roe"] = pd.to_numeric(selected_companies["roe"], errors="coerce")
        selected_companies = selected_companies.sort_values(
            by=["sort_roe", "company_name"],
            ascending=[False, True],
            na_position="last",
        )

        companies = tuple(
            SectorCompanyMetricDTO(
                cd_cvm=int(row["cd_cvm"]),
                company_name=str(row["company_name"]),
                ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                gics_sub_industry=self._clean_optional_text(row.get("gics_sub_industry")),
                roe=self._coerce_optional_float(row.get("roe")),
                mg_ebit=self._coerce_optional_float(row.get("mg_ebit")),
                mg_liq=self._coerce_optional_float(row.get("mg_liq")),
            )
            for _, row in selected_companies.iterrows()
        )

        return SectorDetailDTO(
            sector_name=resolved_sector_name,
            sector_slug=sector_slugify(resolved_sector_name),
            company_count=int(total_items),
            available_years=tuple(available_years),
            selected_year=int(selected_year),
            yearly_overview=yearly_overview,
            companies=companies,
        )

    def get_sub_sector_detail(
        self,
        *,
        sector_slug: str,
        sub_industry_slug: str,
        year: int | None = None,
    ) -> SectorDetailDTO | None:
        """Detail for a GICS sub-industry inside a parent GICS sector.

        Returns None if the sector slug is not one of the 11 GICS hubs or if
        no company in that sector has the requested sub-industry slug.
        """
        sector_name = self._resolve_sector_slug(sector_slug)
        if sector_name is None or sector_name not in GICS_11_SECTORS:
            return None

        normalized_sub_slug = str(sub_industry_slug or "").strip().lower()
        if not normalized_sub_slug:
            return None

        universe = self._list_company_universe_results()
        sub_industry_name: str | None = None
        matching: list[CompanySearchResult] = []
        for item in universe:
            if item.gics_sector != sector_name:
                continue
            if not item.gics_sub_industry:
                continue
            if sector_slugify(item.gics_sub_industry) != normalized_sub_slug:
                continue
            sub_industry_name = item.gics_sub_industry
            matching.append(item)

        if not matching or sub_industry_name is None:
            return None

        company_rows = pd.DataFrame(
            [
                {
                    "cd_cvm": int(item.cd_cvm),
                    "company_name": str(item.company_name),
                    "ticker_b3": item.ticker_b3,
                    "anos_disponiveis": tuple(item.anos_disponiveis),
                    "gics_sub_industry": item.gics_sub_industry,
                }
                for item in matching
            ]
        )
        total_items = len(company_rows)
        available_years = self._extract_years_from_company_rows(company_rows)
        parent_sector_slug = sector_slugify(sector_name)

        empty_companies = tuple(
            SectorCompanyMetricDTO(
                cd_cvm=int(row["cd_cvm"]),
                company_name=str(row["company_name"]),
                ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                gics_sub_industry=self._clean_optional_text(row.get("gics_sub_industry")),
                roe=None,
                mg_ebit=None,
                mg_liq=None,
            )
            for _, row in company_rows.sort_values("company_name").iterrows()
        )

        if not available_years:
            selected_year = int(year or datetime.now(timezone.utc).year - 1)
            return SectorDetailDTO(
                sector_name=sub_industry_name,
                sector_slug=normalized_sub_slug,
                company_count=int(total_items),
                available_years=(),
                selected_year=selected_year,
                yearly_overview=(),
                companies=empty_companies,
                parent_sector_name=sector_name,
                parent_sector_slug=parent_sector_slug,
            )

        if year is None:
            selected_year = max(available_years)
        else:
            selected_year = int(year)
            if selected_year not in available_years:
                raise ValueError(
                    f"O parametro 'year' precisa ser um dos anos disponiveis do sub-setor: {', '.join(str(value) for value in available_years)}."
                )

        metric_rows = self.query_layer.get_sector_metric_rows()
        company_codes = {int(value) for value in company_rows["cd_cvm"].tolist()}
        if metric_rows is None or metric_rows.empty:
            metric_rows = pd.DataFrame(
                columns=["cd_cvm", "report_year", "roe", "mg_ebit", "mg_liq", "sector_name"]
            )
        else:
            metric_rows = metric_rows[
                metric_rows["cd_cvm"].map(lambda code: int(code) in company_codes)
            ].copy()
            metric_rows["sector_name"] = sub_industry_name

        yearly = self._aggregate_sector_yearly_metrics(metric_rows)
        yearly_overview = tuple(
            SectorYearOverviewDTO(
                year=int(row["year"]),
                roe=self._coerce_optional_float(row["roe"]),
                mg_ebit=self._coerce_optional_float(row["mg_ebit"]),
                mg_liq=self._coerce_optional_float(row["mg_liq"]),
            )
            for _, row in yearly[yearly["sector_name"] == sub_industry_name]
            .sort_values("year")
            .iterrows()
        )

        company_metrics = metric_rows[metric_rows["report_year"] == selected_year].copy()
        selected_companies = company_rows[
            company_rows["anos_disponiveis"].map(lambda years: selected_year in years)
        ][["cd_cvm", "company_name", "ticker_b3", "gics_sub_industry"]].drop_duplicates()
        selected_companies = selected_companies.merge(
            company_metrics[["cd_cvm", "roe", "mg_ebit", "mg_liq"]],
            on="cd_cvm",
            how="left",
        )
        selected_companies["ticker_b3"] = selected_companies["ticker_b3"].replace("", None)
        selected_companies["sort_roe"] = pd.to_numeric(
            selected_companies["roe"], errors="coerce"
        )
        selected_companies = selected_companies.sort_values(
            by=["sort_roe", "company_name"],
            ascending=[False, True],
            na_position="last",
        )

        companies = tuple(
            SectorCompanyMetricDTO(
                cd_cvm=int(row["cd_cvm"]),
                company_name=str(row["company_name"]),
                ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                gics_sub_industry=self._clean_optional_text(row.get("gics_sub_industry")),
                roe=self._coerce_optional_float(row.get("roe")),
                mg_ebit=self._coerce_optional_float(row.get("mg_ebit")),
                mg_liq=self._coerce_optional_float(row.get("mg_liq")),
            )
            for _, row in selected_companies.iterrows()
        )

        return SectorDetailDTO(
            sector_name=sub_industry_name,
            sector_slug=normalized_sub_slug,
            company_count=int(total_items),
            available_years=tuple(available_years),
            selected_year=int(selected_year),
            yearly_overview=yearly_overview,
            companies=companies,
            parent_sector_name=sector_name,
            parent_sector_slug=parent_sector_slug,
        )

    def get_statement_matrix(
        self,
        cd_cvm: int,
        years: list[int],
        stmt_type: str,
        *,
        exclude_conflicts: bool = True,
    ) -> StatementMatrix:
        df = self.query_layer.get_statement(
            cd_cvm=cd_cvm,
            years=years,
            stmt_type=stmt_type,
            exclude_conflicts=exclude_conflicts,
        )
        return StatementMatrix(
            cd_cvm=int(cd_cvm),
            statement_type=str(stmt_type),
            years=tuple(int(year) for year in years),
            table=TabularData.from_dataframe(df),
            exclude_conflicts=bool(exclude_conflicts),
        )

    def get_statement_dataframe(
        self,
        cd_cvm: int,
        years: list[int],
        stmt_type: str,
        *,
        exclude_conflicts: bool = True,
    ) -> pd.DataFrame:
        return self.get_statement_matrix(
            cd_cvm,
            years,
            stmt_type,
            exclude_conflicts=exclude_conflicts,
        ).to_dataframe()

    def get_kpi_bundle(self, cd_cvm: int, years: list[int]) -> KPIBundle:
        accounts = self.query_layer.get_kpi_accounts(cd_cvm, years)
        da_series = self.query_layer.get_da_from_dfc(cd_cvm, years)
        annual = compute_all_kpis(accounts, da_series)

        quarterly_accounts = self.query_layer.get_kpi_accounts_all_periods(cd_cvm, years)
        quarterly_da = self.query_layer.get_da_all_periods(cd_cvm, years)
        quarterly = compute_quarterly_kpis(quarterly_accounts, quarterly_da)

        return KPIBundle(
            cd_cvm=int(cd_cvm),
            years=tuple(int(year) for year in years),
            annual=TabularData.from_dataframe(annual),
            quarterly=TabularData.from_dataframe(quarterly),
        )

    def get_statement_summary(self, cd_cvm: int, years: list[int]) -> StatementSummaryDTO:
        stmt_types = ["DRE", "BPA", "BPP", "DFC"]
        statements = {
            s: self.query_layer.get_statement(
                cd_cvm=cd_cvm,
                years=years,
                stmt_type=s,
                exclude_conflicts=True,
            )
            for s in stmt_types
        }
        raw_blocks = build_general_summary_blocks(statements)
        blocks = tuple(
            SummaryBlockDTO(
                stmt_type=b.stmt_type,
                title=b.title,
                table=TabularData.from_dataframe(b.rows),
            )
            for b in raw_blocks
        )
        return StatementSummaryDTO(
            cd_cvm=int(cd_cvm),
            years=tuple(sorted(int(y) for y in years)),
            blocks=blocks,
        )

    def build_company_excel_export(
        self,
        cd_cvm: int,
        statement_type: Optional[str] = None,
        period_scope: str = "last_5_years",
    ) -> tuple[str, bytes]:
        """Build the Excel workbook for a company.

        Parameters
        ----------
        cd_cvm : int
        statement_type : str, optional
            If set, builds a single-statement scoped workbook.
        period_scope : str
            One of ``last_3_years``, ``last_5_years``, ``last_10_years``,
            ``full_history``.  Defaults to ``last_5_years``.  Current-year
            ITR-only periods (e.g. 1Q26 when 2026 DFP is not yet filed) are
            always appended regardless of scope.
        """
        if period_scope not in self.VALID_PERIOD_SCOPES:
            raise ValueError(
                f"Invalid period_scope: {period_scope!r}. "
                f"Must be one of: {', '.join(sorted(self.VALID_PERIOD_SCOPES))}"
            )

        company_info = self.get_company_info_dict(cd_cvm)
        if not company_info:
            raise ValueError(f"Empresa {cd_cvm} nao encontrada.")

        scope = self.resolve_excel_export_scope(cd_cvm, period_scope)
        years: list[int] = scope["all_export_years"]
        period_window: tuple[int, int] = scope["period_window"]
        scope_label: str = scope["scope_label"]
        itr_only_years: list[int] = scope["itr_only_years"]

        if not years:
            raise ValueError(
                f"Empresa {cd_cvm} nao possui periodos disponiveis para exportacao."
            )

        if statement_type:
            df = self.get_statement_dataframe(cd_cvm, years, statement_type)
            exportable_statements = {
                statement_type: df
            } if df is not None and not df.empty else {}
            extra_sheets = [statement_type] if statement_type in ("DVA", "DMPL") else []
            kpis_df = pd.DataFrame()
        else:
            all_stmts = {
                stmt_type: self.get_statement_dataframe(cd_cvm, years, stmt_type)
                for stmt_type in EXPORT_STATEMENT_TYPES
            }
            exportable_statements = {
                stmt_type: df
                for stmt_type, df in all_stmts.items()
                if df is not None and not df.empty
            }
            extra_sheets = [
                stmt_type
                for stmt_type in ("DVA", "DMPL")
                if stmt_type in exportable_statements
            ]
            kpis_df = self.get_kpi_bundle(cd_cvm, years).quarterly_dataframe()

        exporter = ExcelExporter(
            company_info=company_info,
            statements=exportable_statements,
            kpis_df=kpis_df,
            extra_sheets=extra_sheets,
            statement_type=statement_type,
            period_window=period_window,
            period_scope_label=scope_label,
            itr_only_years=itr_only_years,
        )
        return (
            build_excel_filename(company_info, statement_type=statement_type),
            exporter.export(statement_type=statement_type)
        )

    def get_health_snapshot(
        self,
        start_year: int,
        end_year: int,
        *,
        force_refresh: bool = False,
    ) -> HealthSnapshot:
        resolved_start_year, resolved_end_year = self._resolve_refresh_range(
            start_year=start_year,
            end_year=end_year,
        )
        if force_refresh:
            self.invalidate_read_caches()
        else:
            self._ensure_read_cache_fresh()
            cached = self._health_snapshot_cache.get((resolved_start_year, resolved_end_year))
            if cached is not None:
                return cached

        payload = self._build_db_health_snapshot(
            start_year=resolved_start_year,
            end_year=resolved_end_year,
        )
        snapshot = HealthSnapshot.from_payload(payload)
        self._health_snapshot_cache[(resolved_start_year, resolved_end_year)] = snapshot
        return snapshot

    def list_refresh_status(self, cd_cvm: int | None = None) -> list[RefreshStatusDTO]:
        self.refresh_job_repository.ensure_schema()

        query = text(
            """
            SELECT
                cd_cvm,
                company_name,
                source_scope,
                job_id,
                stage,
                queue_position,
                last_attempt_at,
                last_success_at,
                last_status,
                last_error,
                last_start_year,
                last_end_year,
                last_rows_inserted,
                progress_current,
                progress_total,
                progress_message,
                started_at,
                heartbeat_at,
                finished_at,
                read_model_updated_at,
                updated_at
            FROM company_refresh_status
            WHERE (:cd_cvm IS NULL OR cd_cvm = :cd_cvm)
            ORDER BY company_name
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"cd_cvm": int(cd_cvm) if cd_cvm is not None else None}).mappings().all()
        cd_cvms = [int(row["cd_cvm"]) for row in rows]
        active_jobs = self._load_active_refresh_jobs_map(cd_cvms)
        readable_years_map = (
            self.query_layer.get_company_years_map(cd_cvms)
            if cd_cvms
            else {}
        )
        read_model_state_map = self._load_company_read_model_state_map(
            cd_cvms,
            precomputed_years_map=readable_years_map,
        )
        duration_profile = (
            self._estimate_refresh_duration_profile()
            if any(
                str(row.get("last_status") or "").strip().lower()
                in self.ACTIVE_REFRESH_STATUSES
                for row in rows
            ) or active_jobs
            else None
        )
        return [
            self._build_refresh_status_dto(
                row,
                duration_profile=duration_profile,
                active_job=active_jobs.get(int(row["cd_cvm"])),
                read_model_state=read_model_state_map.get(
                    int(row["cd_cvm"]),
                    {},
                ),
            )
            for row in rows
        ]

    def _load_company_read_model_state_map(
        self,
        cd_cvms: list[int] | tuple[int, ...],
        *,
        precomputed_years_map: dict[int, Any] | None = None,
    ) -> dict[int, dict[str, Any]]:
        unique_ids = sorted({int(cd_cvm) for cd_cvm in cd_cvms})
        if not unique_ids:
            return {}

        years_map = (
            precomputed_years_map
            if precomputed_years_map is not None
            else self.query_layer.get_company_years_map(unique_ids)
        )
        projection_updated_at: dict[int, str] = {}
        company_updated_at: dict[int, str] = {}

        with self.engine.connect() as conn:
            if inspect(conn).has_table("company_refresh_status"):
                status_columns = {
                    str(column.get("name") or "").lower()
                    for column in inspect(conn).get_columns("company_refresh_status")
                }
                if "read_model_updated_at" in status_columns:
                    rows = conn.execute(
                        text(
                            """
                            SELECT cd_cvm, read_model_updated_at
                            FROM company_refresh_status
                            WHERE cd_cvm IN :cd_cvms
                            """
                        ).bindparams(bindparam("cd_cvms", expanding=True)),
                        {"cd_cvms": unique_ids},
                    ).mappings().all()
                    projection_updated_at = {
                        int(row["cd_cvm"]): str(row["read_model_updated_at"])
                        for row in rows
                        if row.get("read_model_updated_at") is not None
                    }
            if inspect(conn).has_table("companies"):
                company_rows = conn.execute(
                    text(
                        """
                        SELECT cd_cvm, updated_at
                        FROM companies
                        WHERE cd_cvm IN :cd_cvms
                        """
                    ).bindparams(bindparam("cd_cvms", expanding=True)),
                    {"cd_cvms": unique_ids},
                ).mappings().all()
                company_updated_at = {
                    int(row["cd_cvm"]): str(row["updated_at"])
                    for row in company_rows
                    if row.get("updated_at") is not None
                }

        state_map: dict[int, dict[str, Any]] = {}
        for cd_cvm in unique_ids:
            readable_years = tuple(
                sorted(int(year) for year in years_map.get(int(cd_cvm), ()))
            )
            has_readable_data = bool(readable_years)
            state_map[int(cd_cvm)] = {
                "has_readable_current_data": has_readable_data,
                "readable_years_count": len(readable_years),
                "latest_readable_year": (
                    int(readable_years[-1]) if readable_years else None
                ),
                "read_model_updated_at": (
                    projection_updated_at.get(int(cd_cvm))
                    or (
                        company_updated_at.get(int(cd_cvm))
                        if has_readable_data
                        else None
                    )
                ),
            }
        return state_map

    def _build_refresh_status_dto(
        self,
        row: dict[str, Any],
        *,
        duration_profile: dict[str, Any] | None,
        active_job: dict[str, Any] | None,
        read_model_state: dict[str, Any],
    ) -> RefreshStatusDTO:
        readable_years_count = int(
            read_model_state.get("readable_years_count") or 0
        )
        has_readable_current_data = bool(
            read_model_state.get("has_readable_current_data")
        )
        latest_readable_year = read_model_state.get("latest_readable_year")
        latest_attempt_outcome = self._normalize_refresh_status(row.get("last_status")) or None
        tracking_state = self._resolve_refresh_tracking_state(
            row,
            active_job=active_job,
            duration_profile=duration_profile,
            has_readable_current_data=has_readable_current_data,
        )
        estimate = self._estimate_refresh_runtime(
            row,
            duration_profile=duration_profile,
            active_job=active_job,
            tracking_state=tracking_state,
        )
        status_reason_code, status_reason_message = self._build_refresh_status_reason(
            row,
            tracking_state=tracking_state,
            active_job=active_job,
            has_readable_current_data=has_readable_current_data,
        )
        read_availability = self._build_read_availability_summary(
            has_readable_current_data=has_readable_current_data,
            readable_years_count=readable_years_count,
            latest_readable_year=(
                int(latest_readable_year)
                if latest_readable_year is not None
                else None
            ),
        )
        latest_attempt_reason = self._build_latest_attempt_reason(
            row,
            tracking_state=tracking_state,
            active_job=active_job,
            has_readable_current_data=has_readable_current_data,
        )
        freshness_summary = self._build_freshness_summary(
            row,
            tracking_state=tracking_state,
            has_readable_current_data=has_readable_current_data,
            status_reason_code=status_reason_code,
            status_reason_message=status_reason_message,
            latest_attempt_reason=latest_attempt_reason,
        )
        return RefreshStatusDTO(
            cd_cvm=int(row["cd_cvm"]),
            company_name=str(row["company_name"] or ""),
            source_scope=row.get("source_scope"),
            job_id=row.get("job_id"),
            stage=row.get("stage"),
            queue_position=(
                int(row["queue_position"])
                if row.get("queue_position") is not None
                else None
            ),
            last_attempt_at=row.get("last_attempt_at"),
            last_success_at=row.get("last_success_at"),
            last_status=row.get("last_status"),
            last_error=row.get("last_error"),
            last_start_year=(
                int(row["last_start_year"])
                if row.get("last_start_year") is not None
                else None
            ),
            last_end_year=(
                int(row["last_end_year"])
                if row.get("last_end_year") is not None
                else None
            ),
            last_rows_inserted=(
                int(row["last_rows_inserted"])
                if row.get("last_rows_inserted") is not None
                else None
            ),
            progress_current=(
                int(row["progress_current"])
                if row.get("progress_current") is not None
                else None
            ),
            progress_total=(
                int(row["progress_total"])
                if row.get("progress_total") is not None
                else None
            ),
            progress_message=row.get("progress_message"),
            started_at=row.get("started_at"),
            heartbeat_at=row.get("heartbeat_at"),
            finished_at=row.get("finished_at"),
            updated_at=row.get("updated_at"),
            read_model_updated_at=(
                str(read_model_state["read_model_updated_at"])
                if read_model_state.get("read_model_updated_at") is not None
                else row.get("read_model_updated_at")
            ),
            estimated_progress_pct=estimate["estimated_progress_pct"],
            estimated_eta_seconds=estimate["estimated_eta_seconds"],
            estimated_total_seconds=estimate["estimated_total_seconds"],
            elapsed_seconds=estimate["elapsed_seconds"],
            estimated_completion_at=estimate["estimated_completion_at"],
            estimate_confidence=estimate["estimate_confidence"],
            tracking_state=tracking_state,
            progress_mode=estimate["progress_mode"],
            is_retry_allowed=self._is_refresh_retry_allowed(
                tracking_state=tracking_state,
                active_job=active_job,
            ),
            status_reason_code=status_reason_code,
            status_reason_message=status_reason_message,
            has_readable_current_data=has_readable_current_data,
            readable_years_count=int(readable_years_count or 0),
            latest_readable_year=(
                int(latest_readable_year)
                if latest_readable_year is not None
                else None
            ),
            latest_attempt_outcome=latest_attempt_outcome,
            latest_attempt_reason_code=latest_attempt_reason["code"],
            latest_attempt_reason_message=latest_attempt_reason["message"],
            latest_attempt_retryable=bool(latest_attempt_reason["retryable"]),
            read_availability_code=read_availability["code"],
            read_availability_message=read_availability["message"],
            freshness_summary_code=freshness_summary["code"],
            freshness_summary_message=freshness_summary["message"],
            freshness_summary_severity=freshness_summary["severity"],
            source_label=self._build_refresh_source_label(
                row.get("source_scope"),
                has_readable_current_data=has_readable_current_data,
            ),
        )

    def request_company_refresh(
        self,
        cd_cvm: int,
        *,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> RefreshDispatchDTO:
        """Enqueue internal on-demand ingest for one company.

        When ``start_year``/``end_year`` are omitted, falls back to the
        historical default window (2010..current). When provided, the
        caller can narrow the ingest to a specific period — the dispatch
        still flows through ``refresh_job_repository`` so that
        ``company_refresh_status`` reflects the running job for polling.
        """
        from src.api_errors import NotFoundError

        bootstrapped = self._ensure_company_catalog_metadata(cd_cvm)
        requested_start = int(start_year) if start_year is not None else 2010
        requested_end = int(end_year) if end_year is not None else None
        start_year, end_year = self._resolve_refresh_range(
            start_year=requested_start,
            end_year=requested_end,
        )
        company_info = self.get_company_info(cd_cvm)
        if company_info is None:
            raise NotFoundError(f"Company cd_cvm={cd_cvm} not found")

        source_scope = "on_demand_bootstrap" if bootstrapped else "on_demand"
        request = RefreshRequest(
            companies=(str(cd_cvm),),
            start_year=start_year,
            end_year=end_year,
            policy=default_incremental_refresh_policy(),
        )
        planned_companies, _, _ = self.refresh_service.build_company_year_plan(request)

        active_job = self.refresh_job_repository.get_active_job_for_company(cd_cvm)
        if active_job is not None:
            raise RefreshAlreadyActiveError(
                f"Refresh already active for cd_cvm={cd_cvm}"
            )

        if not planned_companies:
            projection = self.refresh_job_repository.mark_already_current(
                cd_cvm=cd_cvm,
                company_name=company_info.company_name,
                source_scope=source_scope,
                start_year=start_year,
                end_year=end_year,
                message=(
                    "Empresa ja atualizada para "
                    f"{start_year}-{end_year}."
                ),
            )
            return RefreshDispatchDTO(
                status="already_current",
                cd_cvm=int(cd_cvm),
                job_id=None,
                accepted_at=str(projection["accepted_at"]),
                message=str(projection["message"]),
                status_reason_code="already_current",
                status_reason_message=(
                    "Esta empresa ja estava atualizada para a janela padrao."
                ),
                is_retry_allowed=False,
            )

        job = self.refresh_job_repository.enqueue_job(
            cd_cvm=cd_cvm,
            company_name=company_info.company_name,
            source_scope=source_scope,
            start_year=start_year,
            end_year=end_year,
        )
        if job is None:
            raise RefreshAlreadyActiveError(
                f"Refresh already active for cd_cvm={cd_cvm}"
            )

        return RefreshDispatchDTO(
            status="queued",
            cd_cvm=int(cd_cvm),
            job_id=str(job.id),
            accepted_at=str(job.requested_at),
            message=str(
                job.progress_message
                or "Solicitacao enfileirada para processamento interno."
            ),
            status_reason_code="refresh_queued",
            status_reason_message=(
                "Solicitacao aceita e aguardando processamento interno."
            ),
            is_retry_allowed=False,
        )

    def request_top_ranked_historical_refresh(
        self,
        *,
        limit: int = 80,
        start_year: int = 2010,
        end_year: int | None = None,
    ) -> RankedRefreshQueueResult:
        resolved_start_year, resolved_end_year = self._resolve_refresh_range(
            start_year=start_year,
            end_year=end_year,
        )
        backlog = self._build_ranked_backlog(
            limit=int(limit),
            start_year=resolved_start_year,
            end_year=resolved_end_year,
        )

        queue_window = timedelta(hours=self.PRIORITIZED_BACKLOG_STALE_HOURS)
        items: list[RankedRefreshQueueItem] = []
        counters = {
            "queued_count": 0,
            "already_queued_count": 0,
            "no_data_excluded_count": 0,
            "already_complete_count": 0,
            "dispatch_failed_count": 0,
        }

        for row in backlog["items"]:
            status = str(row["recommended_action"])
            note = str(row["reason"])

            if status == "queue_historical_backfill":
                dispatch_result = self._dispatch_refresh_request(
                    cd_cvm=int(row["cd_cvm"]),
                    start_year=resolved_start_year,
                    end_year=resolved_end_year,
                    source_scope="ranked_backfill",
                    already_queued_window=queue_window,
                )
                if dispatch_result == "dispatched":
                    status = "queued"
                    note = (
                        f"Workflow enfileirado para backfill anual entre "
                        f"{resolved_start_year} e {resolved_end_year}."
                    )
                    counters["queued_count"] += 1
                elif dispatch_result == "already_queued":
                    status = "already_queued"
                    note = "Ja existe uma execucao recente em fila para esta empresa."
                    counters["already_queued_count"] += 1
                else:
                    status = "dispatch_failed"
                    note = "Falha ao disparar o workflow de backfill historico."
                    counters["dispatch_failed_count"] += 1
            elif status == "await_existing_queue":
                status = "already_queued"
                counters["already_queued_count"] += 1
            elif status == "skip_no_data":
                status = "no_data_excluded"
                counters["no_data_excluded_count"] += 1
            else:
                status = "already_complete"
                counters["already_complete_count"] += 1

            items.append(
                RankedRefreshQueueItem(
                    cd_cvm=int(row["cd_cvm"]),
                    company_name=str(row["company_name"]),
                    coverage_rank=(
                        int(row["coverage_rank"])
                        if row.get("coverage_rank") is not None
                        else None
                    ),
                    status=status,
                    last_status=(
                        str(row["last_status"])
                        if row.get("last_status") is not None
                        else None
                    ),
                    missing_years_count=int(row["missing_years_count"]),
                    years_missing=tuple(int(year) for year in row["years_missing"]),
                    note=note,
                )
            )

        return RankedRefreshQueueResult(
            start_year=resolved_start_year,
            end_year=resolved_end_year,
            requested_limit=int(limit),
            total_ranked=int(backlog["summary"]["total_ranked"]),
            queued_count=int(counters["queued_count"]),
            already_queued_count=int(counters["already_queued_count"]),
            no_data_excluded_count=int(counters["no_data_excluded_count"]),
            already_complete_count=int(counters["already_complete_count"]),
            dispatch_failed_count=int(counters["dispatch_failed_count"]),
            items=tuple(items),
        )

    def _build_db_health_snapshot(self, *, start_year: int, end_year: int) -> dict[str, Any]:
        active_rows = self._load_active_company_rows()
        years_scope = list(range(int(start_year), int(end_year) + 1))
        company_codes = [int(row["cd_cvm"]) for row in active_rows]
        complete_years_map = self._load_complete_annual_years_map(
            company_codes,
            start_year=start_year,
            end_year=end_year,
        )
        all_years_map = self.query_layer.get_company_years_map(company_codes)
        companies_with_historical_data = sum(
            1 for cd_cvm in company_codes if all_years_map.get(int(cd_cvm))
        )
        status_map = self._load_refresh_status_map(company_codes)
        any_local_cd_set = self._cd_cvms_with_any_financial_report_row(company_codes)
        companies_with_any_local_financial_report = sum(
            1 for cd_cvm in company_codes if cd_cvm in any_local_cd_set
        )
        companies_partial_local = sum(
            1
            for cd_cvm in company_codes
            if cd_cvm in any_local_cd_set and not all_years_map.get(int(cd_cvm))
        )
        companies_with_refresh_status_recorded = sum(
            1 for cd_cvm in company_codes if cd_cvm in status_map
        )
        companies_with_last_refresh_error = sum(
            1
            for cd_cvm in company_codes
            if self._normalize_refresh_status(
                status_map.get(cd_cvm, {}).get("last_status"),
            )
            in BATCH_REFRESH_FAILED_STATES
        )

        per_year_buckets = {
            int(year): {
                "year": int(year),
                "total_companies": int(len(active_rows)),
                "completed": 0,
            }
            for year in years_scope
        }
        company_rows: list[dict[str, Any]] = []
        leader_completed = 0
        companies_fully_updated = 0

        for row in active_rows:
            cd_cvm = int(row["cd_cvm"])
            completed_years = set(complete_years_map.get(cd_cvm, ()))
            years_completed = [year for year in years_scope if year in completed_years]
            years_missing = [year for year in years_scope if year not in completed_years]
            if not years_missing:
                companies_fully_updated += 1
            leader_completed = max(leader_completed, len(years_completed))
            for year in years_completed:
                per_year_buckets[int(year)]["completed"] += 1
            company_rows.append(
                {
                    "cd_cvm": cd_cvm,
                    "company_name": str(row["company_name"]),
                    "coverage_rank": (
                        int(row["coverage_rank"])
                        if row.get("coverage_rank") is not None
                        else None
                    ),
                    "years_completed": years_completed,
                    "years_missing": years_missing,
                    "completed_years_count": len(years_completed),
                    "missing_years_count": len(years_missing),
                    "last_status": status_map.get(cd_cvm, {}).get("last_status"),
                }
            )

        total_cells = int(len(active_rows) * len(years_scope))
        completed_cells = int(sum(bucket["completed"] for bucket in per_year_buckets.values()))
        missing_cells = max(0, total_cells - completed_cells)
        pct = (100.0 * completed_cells / total_cells) if total_cells else 0.0

        throughput = self._estimate_refresh_throughput()
        throughput_per_hour = throughput.get("per_hour")
        remaining_companies = sum(
            1 for row in company_rows if int(row["missing_years_count"]) > 0
        )
        eta_hours = (
            float(remaining_companies) / float(throughput_per_hour)
            if throughput_per_hour
            else None
        )

        per_year = []
        for year in years_scope:
            completed = int(per_year_buckets[int(year)]["completed"])
            total_companies = int(per_year_buckets[int(year)]["total_companies"])
            missing = max(0, total_companies - completed)
            per_year.append(
                {
                    "year": int(year),
                    "total_companies": total_companies,
                    "completed": completed,
                    "missing": missing,
                    "pct": (100.0 * completed / total_companies) if total_companies else 0.0,
                    "eta_hours": (
                        float(missing) / float(throughput_per_hour)
                        if throughput_per_hour
                        else None
                    ),
                }
            )

        ranked_backlog = self._build_ranked_backlog(
            limit=80,
            start_year=start_year,
            end_year=end_year,
            complete_years_map=complete_years_map,
            refresh_status_map=status_map,
        )

        prioritized_companies: list[dict[str, Any]] = []
        for row in ranked_backlog["items"]:
            gap_to_leader = max(
                0,
                int(leader_completed) - int(row["completed_years_count"]),
            )
            prioritized_companies.append(
                {
                    "cd_cvm": int(row["cd_cvm"]),
                    "company_name": str(row["company_name"]),
                    "coverage_rank": (
                        int(row["coverage_rank"])
                        if row.get("coverage_rank") is not None
                        else None
                    ),
                    "last_status": (
                        str(row["last_status"])
                        if row.get("last_status") is not None
                        else None
                    ),
                    "excluded_from_queue": bool(row["excluded_from_queue"]),
                    "risk_level": str(row["risk_level"]),
                    "priority_score": int(row["priority_score"]),
                    "missing_years_count": int(row["missing_years_count"]),
                    "gap_to_leader_years": int(gap_to_leader),
                    "years_missing": list(int(year) for year in row["years_missing"]),
                    "recommended_action": str(row["recommended_action"]),
                    "reason": str(row["reason"]),
                }
            )

        throughput_confidence = str(throughput.get("confidence") or "low")
        if throughput_per_hour:
            throughput_score = {
                "high": 100.0,
                "medium": 75.0,
                "low": 55.0,
            }.get(throughput_confidence, 55.0)
        else:
            throughput_score = {
                "high": 70.0,
                "medium": 50.0,
                "low": 30.0,
            }.get(throughput_confidence, 30.0)

        latest_year_pct = float(per_year[-1]["pct"]) if per_year else pct
        health_score = max(
            0.0,
            min(
                100.0,
                (0.6 * float(pct))
                + (0.2 * float(latest_year_pct))
                + (0.2 * float(throughput_score)),
            ),
        )

        return {
            "generated_at": now_iso_seconds(),
            "start_year": int(start_year),
            "end_year": int(end_year),
            "scope": "database_backed",
            "required_package": list(self.REQUIRED_PACKAGE_STATEMENTS),
            "ranked_backlog": dict(ranked_backlog["summary"]),
            "active_companies": int(len(active_rows)),
            "company_inventory": {
                "total_companies": int(len(active_rows)),
                "companies_with_historical_data": int(companies_with_historical_data),
                "companies_without_historical_data": max(
                    0,
                    int(len(active_rows)) - int(companies_with_historical_data),
                ),
                "companies_with_any_local_financial_report": int(
                    companies_with_any_local_financial_report
                ),
                "companies_partial_local": int(companies_partial_local),
                "companies_fully_updated": int(companies_fully_updated),
                "companies_with_refresh_status_recorded": int(
                    companies_with_refresh_status_recorded
                ),
                "companies_with_last_refresh_error": int(companies_with_last_refresh_error),
            },
            "global": {
                "total_cells": int(total_cells),
                "completed_cells": int(completed_cells),
                "missing_cells": int(missing_cells),
                "pct": float(pct),
                "active_universe": int(len(active_rows)),
                "companies_with_historical_data": int(companies_with_historical_data),
                "remaining_companies": int(remaining_companies),
                "eta_hours": eta_hours,
            },
            "throughput": throughput,
            "per_year": per_year,
            "health_score": round(float(health_score), 2),
            "health_status": self._health_status_from_score(health_score),
            "prioritized_companies": prioritized_companies,
        }

    def _build_ranked_backlog(
        self,
        *,
        limit: int,
        start_year: int,
        end_year: int,
        complete_years_map: dict[int, tuple[int, ...]] | None = None,
        refresh_status_map: dict[int, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ranked_rows = self._load_ranked_company_rows(limit)
        company_codes = [int(row["cd_cvm"]) for row in ranked_rows]
        years_scope = list(range(int(start_year), int(end_year) + 1))
        complete_map = complete_years_map or self._load_complete_annual_years_map(
            company_codes,
            start_year=start_year,
            end_year=end_year,
        )
        status_map = refresh_status_map or self._load_refresh_status_map(company_codes)
        leader_completed = max(
            (len(complete_map.get(code, ())) for code in company_codes),
            default=0,
        )

        items: list[dict[str, Any]] = []
        companies_with_some_data = 0
        fully_covered_companies = 0
        queue_eligible_companies = 0
        queued_companies = 0
        no_data_excluded_companies = 0

        for row in ranked_rows:
            cd_cvm = int(row["cd_cvm"])
            coverage_rank = (
                int(row["coverage_rank"])
                if row.get("coverage_rank") is not None
                else None
            )
            completed_years = set(int(year) for year in complete_map.get(cd_cvm, ()))
            years_completed = [year for year in years_scope if year in completed_years]
            years_missing = [year for year in years_scope if year not in completed_years]
            status_row = status_map.get(cd_cvm, {})
            last_status = (
                str(status_row.get("last_status")).strip().lower()
                if status_row.get("last_status") is not None
                else None
            )
            excluded_from_queue = last_status == "no_data"
            already_queued = self._is_recently_queued(
                status_row,
                window=timedelta(hours=self.PRIORITIZED_BACKLOG_STALE_HOURS),
            )

            if years_completed:
                companies_with_some_data += 1
            if not years_missing:
                fully_covered_companies += 1
            elif excluded_from_queue:
                no_data_excluded_companies += 1
            elif already_queued:
                queued_companies += 1
            else:
                queue_eligible_companies += 1

            if not years_missing:
                recommended_action = "already_complete"
                reason = "Cobertura anual completa na janela solicitada."
            elif excluded_from_queue:
                recommended_action = "skip_no_data"
                reason = "Empresa marcada como no_data; backlog automatico nao reenfileira."
            elif already_queued:
                recommended_action = "await_existing_queue"
                reason = "Ja existe refresh recente em fila para esta empresa."
            elif years_completed:
                recommended_action = "queue_historical_backfill"
                reason = "Empresa com dados parciais; falta backfill anual dos anos ausentes."
            else:
                recommended_action = "queue_historical_backfill"
                reason = "Empresa sem cobertura anual na janela; elegivel para ingestao historica."

            gap_to_leader = max(0, leader_completed - len(years_completed))
            items.append(
                {
                    "cd_cvm": cd_cvm,
                    "company_name": str(row["company_name"]),
                    "coverage_rank": coverage_rank,
                    "last_status": last_status,
                    "excluded_from_queue": excluded_from_queue,
                    "completed_years_count": len(years_completed),
                    "missing_years_count": len(years_missing),
                    "years_missing": years_missing,
                    "priority_score": self._priority_score(
                        coverage_rank=coverage_rank,
                        missing_years_count=len(years_missing),
                        gap_to_leader_years=gap_to_leader,
                    ),
                    "risk_level": self._risk_level(
                        coverage_rank=coverage_rank,
                        missing_years_count=len(years_missing),
                        excluded_from_queue=excluded_from_queue,
                    ),
                    "recommended_action": recommended_action,
                    "reason": reason,
                }
            )

        return {
            "summary": {
                "total_ranked": int(len(ranked_rows)),
                "companies_with_some_data": int(companies_with_some_data),
                "fully_covered_companies": int(fully_covered_companies),
                "queue_eligible_companies": int(queue_eligible_companies),
                "already_queued_companies": int(queued_companies),
                "no_data_excluded_companies": int(no_data_excluded_companies),
            },
            "items": items,
        }

    def _dispatch_refresh_request(
        self,
        *,
        cd_cvm: int,
        start_year: int,
        end_year: int,
        source_scope: str,
        already_queued_window: timedelta,
    ) -> str:
        from src.api_errors import NotFoundError
        from src.github_dispatch import dispatch_on_demand_ingest

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        with self.engine.begin() as conn:
            self._ensure_refresh_status_table(conn)
            company_row = conn.execute(
                text(
                    """
                    SELECT c.company_name, crs.last_status, crs.last_attempt_at
                    FROM companies c
                    LEFT JOIN company_refresh_status crs ON crs.cd_cvm = c.cd_cvm
                    WHERE c.cd_cvm = :cd_cvm
                    """
                ),
                {"cd_cvm": int(cd_cvm)},
            ).mappings().fetchone()
            if company_row is None:
                raise NotFoundError(f"Company cd_cvm={cd_cvm} not found")
            if self._is_recently_queued(company_row, window=already_queued_window):
                return "already_queued"

            company_name = str(company_row.get("company_name") or cd_cvm)
            conn.execute(
                text(
                    """
                    INSERT INTO company_refresh_status (
                        cd_cvm,
                        company_name,
                        source_scope,
                        last_attempt_at,
                        last_status,
                        last_error,
                        last_start_year,
                        last_end_year,
                        updated_at
                    ) VALUES (
                        :cd_cvm,
                        :company_name,
                        :source_scope,
                        :now,
                        'queued',
                        NULL,
                        :start_year,
                        :end_year,
                        :now
                    )
                    ON CONFLICT (cd_cvm) DO UPDATE SET
                        company_name = excluded.company_name,
                        source_scope = excluded.source_scope,
                        last_attempt_at = excluded.last_attempt_at,
                        last_status = excluded.last_status,
                        last_error = excluded.last_error,
                        last_start_year = excluded.last_start_year,
                        last_end_year = excluded.last_end_year,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "cd_cvm": int(cd_cvm),
                    "company_name": company_name,
                    "source_scope": str(source_scope),
                    "start_year": int(start_year),
                    "end_year": int(end_year),
                    "now": now_iso,
                },
            )

        ok, error_msg = dispatch_on_demand_ingest(
            int(cd_cvm),
            start_year=int(start_year),
            end_year=int(end_year),
        )
        if not ok:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE company_refresh_status
                        SET last_status = 'dispatch_failed',
                            last_error = :error_msg,
                            last_start_year = :start_year,
                            last_end_year = :end_year,
                            updated_at = :now
                        WHERE cd_cvm = :cd_cvm
                        """
                    ),
                    {
                        "cd_cvm": int(cd_cvm),
                        "error_msg": error_msg,
                        "start_year": int(start_year),
                        "end_year": int(end_year),
                        "now": now_iso,
                    },
                )
            return "dispatch_failed"

        return "dispatched"

    def _resolve_refresh_range(
        self,
        *,
        start_year: int,
        end_year: int | None,
    ) -> tuple[int, int]:
        resolved_start_year = int(start_year)
        resolved_end_year = (
            int(end_year)
            if end_year is not None
            else max(2010, current_reporting_year_cap())
        )
        if resolved_start_year > resolved_end_year:
            raise ValueError("start_year must be <= end_year")
        return resolved_start_year, resolved_end_year

    def _load_active_company_rows(self) -> list[dict[str, Any]]:
        local_rows = self._load_local_active_company_rows()
        if len(local_rows) >= self.CATALOG_FALLBACK_MIN_LOCAL_COMPANIES:
            return local_rows

        local_by_code = {int(row["cd_cvm"]): row for row in local_rows}
        try:
            entries = [entry for entry in self.company_catalog.list_entries() if entry.is_active]
        except CompanyCatalogUnavailableError:
            return local_rows
        if not entries:
            return local_rows

        rows: list[dict[str, Any]] = []
        for entry in entries:
            local = local_by_code.get(int(entry.cd_cvm), {})
            rows.append(
                {
                    "cd_cvm": int(entry.cd_cvm),
                    "company_name": str(local.get("company_name") or entry.company_name),
                    "coverage_rank": local.get("coverage_rank"),
                }
            )
        rows.sort(
            key=lambda row: (
                1 if row.get("coverage_rank") is None else 0,
                int(row.get("coverage_rank") or 999999),
                str(row.get("company_name") or "").upper(),
            )
        )
        return rows

    def _load_local_company_universe_results(self) -> list[CompanySearchResult]:
        rows_df, _ = self.query_layer.get_companies_directory_page(
            search="",
            sector_name=None,
            page=1,
            page_size=None,
        )
        if not rows_df.empty:
            years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist())
            rows_df = rows_df.copy()
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(
                lambda cd_cvm: years_map.get(int(cd_cvm), ())
            )
        return self._build_company_results(rows_df)

    def _load_local_active_company_rows(self) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT cd_cvm, company_name, coverage_rank
            FROM companies
            WHERE COALESCE(is_active, 1) = 1
            ORDER BY
                CASE WHEN coverage_rank IS NULL THEN 1 ELSE 0 END,
                coverage_rank ASC,
                company_name ASC
            """
        )
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(query).mappings().all()]

    def _load_ranked_company_rows(self, limit: int) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT cd_cvm, company_name, coverage_rank
            FROM companies
            WHERE COALESCE(is_active, 1) = 1
              AND coverage_rank IS NOT NULL
            ORDER BY coverage_rank ASC, company_name ASC
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(query, {"limit": int(limit)}).mappings().all()
            ]

    def _load_complete_annual_years_map(
        self,
        cd_cvms: list[int],
        *,
        start_year: int,
        end_year: int,
    ) -> dict[int, tuple[int, ...]]:
        if not cd_cvms or not inspect(self.engine).has_table("financial_reports"):
            return {}

        query = text(
            """
            SELECT "CD_CVM" AS cd_cvm, "REPORT_YEAR" AS report_year
            FROM financial_reports
            WHERE "CD_CVM" IN :cd_cvms
              AND "REPORT_YEAR" BETWEEN :start_year AND :end_year
              AND "STATEMENT_TYPE" IN :statement_types
              AND "PERIOD_LABEL" = CAST("REPORT_YEAR" AS TEXT)
            GROUP BY "CD_CVM", "REPORT_YEAR"
            HAVING COUNT(DISTINCT "STATEMENT_TYPE") >= :required_count
            ORDER BY "CD_CVM", "REPORT_YEAR"
            """
        ).bindparams(
            bindparam("cd_cvms", expanding=True),
            bindparam("statement_types", expanding=True),
        )

        params = {
            "cd_cvms": [int(cd_cvm) for cd_cvm in cd_cvms],
            "start_year": int(start_year),
            "end_year": int(end_year),
            "statement_types": list(self.REQUIRED_PACKAGE_STATEMENTS),
            "required_count": len(self.REQUIRED_PACKAGE_STATEMENTS),
        }
        with self.engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()

        years_map: dict[int, list[int]] = defaultdict(list)
        for row in rows:
            years_map[int(row["cd_cvm"])].append(int(row["report_year"]))
        return {
            int(cd_cvm): tuple(sorted(set(years)))
            for cd_cvm, years in years_map.items()
        }

    def _cd_cvms_with_any_financial_report_row(self, cd_cvms: list[int]) -> set[int]:
        """Companies with at least one row in financial_reports (any period / tipo)."""
        if not cd_cvms:
            return set()
        if not inspect(self.engine).has_table("financial_reports"):
            return set()
        unique_ids = sorted({int(cd_cvm) for cd_cvm in cd_cvms})
        query = text(
            """
            SELECT DISTINCT "CD_CVM" AS cd_cvm
            FROM financial_reports
            WHERE "CD_CVM" IN :cd_cvms
            """
        ).bindparams(bindparam("cd_cvms", expanding=True))
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"cd_cvms": unique_ids}).mappings().all()
        return {int(row["cd_cvm"]) for row in rows}

    @staticmethod
    def _normalize_refresh_status(value: Any) -> str:
        return str(value or "").strip().lower()

    def _resolve_refresh_tracking_state(
        self,
        row: dict[str, Any],
        *,
        active_job: dict[str, Any] | None,
        duration_profile: dict[str, Any] | None,
        has_readable_current_data: bool,
    ) -> str:
        last_status = self._normalize_refresh_status(row.get("last_status"))
        if last_status in {"success", "no_data", "error"}:
            return last_status

        active_state = (
            self._normalize_refresh_status(active_job.get("state"))
            if active_job is not None
            else ""
        )
        if active_state in self.ACTIVE_REFRESH_STATUSES:
            if self._is_refresh_tracking_stalled(
                row,
                active_job=active_job,
                duration_profile=duration_profile,
                active_state=active_state,
            ):
                return "stalled"
            return active_state

        if last_status in self.ACTIVE_REFRESH_STATUSES:
            return "stalled"

        return "success" if has_readable_current_data else "idle"

    def _is_refresh_tracking_stalled(
        self,
        row: dict[str, Any],
        *,
        active_job: dict[str, Any] | None,
        duration_profile: dict[str, Any] | None,
        active_state: str,
    ) -> bool:
        now = datetime.now(timezone.utc)
        if active_state == "running":
            activity_at = (
                self._parse_timestamp(active_job.get("heartbeat_at"))
                or self._parse_timestamp(active_job.get("started_at"))
                or self._parse_timestamp(row.get("heartbeat_at"))
                or self._parse_timestamp(row.get("started_at"))
                or self._parse_timestamp(active_job.get("requested_at"))
                or self._parse_timestamp(row.get("last_attempt_at"))
            )
            if activity_at is None:
                return False
            return (
                now - activity_at
            ).total_seconds() >= self.REFRESH_RUNNING_STALL_SECONDS

        if active_state == "queued":
            requested_at = (
                self._parse_timestamp(active_job.get("requested_at"))
                or self._parse_timestamp(row.get("last_attempt_at"))
            )
            if requested_at is None:
                return False
            queue_position = (
                int(row["queue_position"])
                if row.get("queue_position") is not None
                else 0
            )
            typical_total_seconds = int(
                round(
                    float(
                        (duration_profile or {}).get("typical_total_seconds")
                        or self.REFRESH_ESTIMATE_DEFAULT_TOTAL_SECONDS
                    )
                )
            )
            threshold_seconds = max(
                self.REFRESH_QUEUE_STALL_SECONDS,
                typical_total_seconds
                + 120
                + (min(max(queue_position, 0), 5) * self.REFRESH_QUEUE_POSITION_STEP_SECONDS),
            )
            return (
                now - requested_at
            ).total_seconds() >= threshold_seconds

        return False

    @staticmethod
    def _build_read_availability_summary(
        *,
        has_readable_current_data: bool,
        readable_years_count: int,
        latest_readable_year: int | None,
    ) -> dict[str, str]:
        if has_readable_current_data:
            if latest_readable_year is not None:
                return {
                    "code": "readable_history_available",
                    "message": (
                        f"Leitura anual disponivel ate {int(latest_readable_year)}."
                    ),
                }
            return {
                "code": "readable_history_available",
                "message": "Leitura anual disponivel nesta pagina.",
            }

        return {
            "code": "no_readable_annual_history",
            "message": (
                "Ainda nao ha historico anual legivel para esta companhia."
            ),
        }

    def _build_latest_attempt_reason(
        self,
        row: dict[str, Any],
        *,
        tracking_state: str,
        active_job: dict[str, Any] | None,
        has_readable_current_data: bool,
    ) -> dict[str, Any]:
        last_status = self._normalize_refresh_status(row.get("last_status"))
        progress_message = self._clean_optional_text(row.get("progress_message"))
        last_error = self._clean_optional_text(row.get("last_error"))
        normalized_progress_message = str(progress_message or "").lower()
        normalized_last_error = str(last_error or "").lower()

        if tracking_state == "queued":
            return {
                "code": "refresh_queued",
                "message": (
                    "Solicitacao recebida e aguardando processamento interno."
                ),
                "retryable": False,
            }

        if tracking_state == "running":
            return {
                "code": "refresh_running",
                "message": (
                    "Os demonstrativos desta companhia estao sendo atualizados agora."
                ),
                "retryable": False,
            }

        if tracking_state == "stalled":
            if active_job is None and last_status in self.ACTIVE_REFRESH_STATUSES:
                return {
                    "code": "refresh_tracking_lost",
                    "message": (
                        "A ultima solicitacao nao aparece mais como ativa."
                    ),
                    "retryable": True,
                }
            return {
                "code": "refresh_stalled",
                "message": (
                    "A solicitacao esta acima do esperado e sem sinais recentes de progresso."
                ),
                "retryable": active_job is None,
            }

        if last_status == "success":
            if "ja atualizada" in normalized_progress_message:
                return {
                    "code": "already_current",
                    "message": (
                        "Esta empresa ja estava atualizada para a janela padrao."
                    ),
                    "retryable": False,
                }
            if has_readable_current_data:
                return {
                    "code": "refresh_completed",
                    "message": "Dados prontos para leitura nesta pagina.",
                    "retryable": False,
                }
            return {
                "code": "refresh_completed_without_readable_data",
                "message": (
                    "A ultima atualizacao terminou, mas a leitura anual ainda nao ficou disponivel."
                ),
                "retryable": False,
            }

        if last_status == "no_data":
            if has_readable_current_data:
                return {
                    "code": "no_new_financial_history",
                    "message": (
                        "A ultima tentativa nao encontrou novos demonstrativos."
                    ),
                    "retryable": True,
                }
            return {
                "code": "no_annual_history",
                "message": (
                    "Nenhuma serie anual legivel foi encontrada para esta companhia."
                ),
                "retryable": True,
            }

        if last_status == "error":
            if "expirou" in normalized_progress_message:
                return {
                    "code": "refresh_expired",
                    "message": (
                        "A solicitacao expirou antes de terminar."
                    ),
                    "retryable": True,
                }
            if "no financial rows found" in normalized_last_error:
                return {
                    "code": "no_annual_history",
                    "message": (
                        "Nenhuma serie anual legivel foi encontrada para esta companhia."
                    ),
                    "retryable": True,
                }
            return {
                "code": "refresh_failed_retryable",
                "message": (
                    "Nao foi possivel concluir a atualizacao desta empresa agora."
                ),
                "retryable": True,
            }

        if has_readable_current_data:
            return {
                "code": "local_data_ready",
                "message": "Leitura local pronta para consulta.",
                "retryable": False,
            }

        return {
            "code": "no_local_history_yet",
            "message": (
                "Esta empresa ainda nao tem historico anual processado na base local."
            ),
            "retryable": False,
        }

    def _build_freshness_summary(
        self,
        row: dict[str, Any],
        *,
        tracking_state: str,
        has_readable_current_data: bool,
        status_reason_code: str,
        status_reason_message: str,
        latest_attempt_reason: dict[str, Any],
    ) -> dict[str, str]:
        last_status = self._normalize_refresh_status(row.get("last_status"))
        attempt_code = str(latest_attempt_reason.get("code") or "")

        if tracking_state in {"queued", "running"}:
            return {
                "code": status_reason_code,
                "message": status_reason_message,
                "severity": "info",
            }

        if tracking_state == "stalled":
            if has_readable_current_data:
                return {
                    "code": "mixed_refresh_stalled_readable",
                    "message": (
                        "A leitura atual continua disponivel, mas a ultima solicitacao esta sem sinais recentes."
                    ),
                    "severity": "warning",
                }
            return {
                "code": "refresh_stalled_no_readable",
                "message": (
                    "A solicitacao esta sem sinais recentes e ainda nao ha leitura anual disponivel."
                ),
                "severity": "warning",
            }

        if last_status == "success":
            if attempt_code == "already_current":
                return {
                    "code": "already_current",
                    "message": (
                        "A leitura local ja estava atualizada para a janela padrao."
                    ),
                    "severity": "success",
                }
            if has_readable_current_data:
                return {
                    "code": "refresh_completed_readable",
                    "message": "Dados prontos para leitura nesta pagina.",
                    "severity": "success",
                }
            return {
                "code": "refresh_completed_no_readable",
                "message": (
                    "A atualizacao terminou, mas a leitura anual ainda nao esta disponivel."
                ),
                "severity": "warning",
            }

        if last_status == "no_data":
            if has_readable_current_data:
                return {
                    "code": "mixed_no_new_data_readable",
                    "message": (
                        "A ultima tentativa nao encontrou novos demonstrativos; a leitura atual continua disponivel."
                    ),
                    "severity": "info",
                }
            return {
                "code": "no_annual_history",
                "message": (
                    "Nenhuma serie anual legivel foi encontrada para esta companhia."
                ),
                "severity": "info",
            }

        if last_status == "error":
            if has_readable_current_data:
                return {
                    "code": "mixed_retryable_error_readable",
                    "message": (
                        "A leitura atual continua disponivel, mas a ultima atualizacao falhou e pode ser tentada novamente."
                    ),
                    "severity": "warning",
                }
            return {
                "code": "refresh_failed_retryable",
                "message": (
                    "A ultima atualizacao falhou e ainda nao ha leitura anual disponivel."
                ),
                "severity": "error",
            }

        if has_readable_current_data:
            return {
                "code": "readable_history_available",
                "message": "Leitura local pronta para consulta.",
                "severity": "success",
            }

        return {
            "code": "no_readable_annual_history",
            "message": (
                "Ainda nao ha historico anual legivel para esta companhia."
            ),
            "severity": "info",
        }

    def _build_refresh_status_reason(
        self,
        row: dict[str, Any],
        *,
        tracking_state: str,
        active_job: dict[str, Any] | None,
        has_readable_current_data: bool,
    ) -> tuple[str, str]:
        last_status = self._normalize_refresh_status(row.get("last_status"))
        progress_message = self._clean_optional_text(row.get("progress_message"))
        last_error = self._clean_optional_text(row.get("last_error"))
        normalized_progress_message = str(progress_message or "").lower()
        normalized_last_error = str(last_error or "").lower()

        if tracking_state == "queued":
            return (
                "refresh_queued",
                "Solicitacao recebida e aguardando processamento interno.",
            )

        if tracking_state == "running":
            return (
                "refresh_running",
                "Os demonstrativos desta companhia estao sendo atualizados agora.",
            )

        if tracking_state == "stalled":
            if active_job is None and last_status in self.ACTIVE_REFRESH_STATUSES:
                return (
                    "refresh_tracking_lost",
                    "A ultima solicitacao nao aparece mais como ativa. Atualize o status ou tente novamente.",
                )
            return (
                "refresh_stalled",
                "A solicitacao esta acima do esperado e sem sinais recentes de progresso.",
            )

        if last_status == "success":
            if "ja atualizada" in normalized_progress_message:
                return (
                    "already_current",
                    "Esta empresa ja estava atualizada para a janela padrao.",
                )
            if has_readable_current_data:
                return (
                    "refresh_completed",
                    "Dados prontos para leitura nesta pagina.",
                )
            return ("refresh_completed", "Processamento concluido.")

        if last_status == "no_data":
            if has_readable_current_data:
                return (
                    "no_new_financial_history",
                    "A ultima tentativa nao encontrou novos demonstrativos, mas a leitura atual continua disponivel.",
                )
            return (
                "no_financial_history_found",
                "Ainda nao foi encontrada uma serie anual suficiente para liberar esta leitura.",
            )

        if last_status == "error":
            if "expirou" in normalized_progress_message:
                return (
                    "refresh_stalled",
                    "A solicitacao expirou antes de terminar. Voce pode tentar novamente.",
                )
            if "no financial rows found" in normalized_last_error:
                return (
                    "no_financial_history_found",
                    "Nenhuma serie anual utilizavel foi encontrada para esta empresa.",
                )
            return (
                "refresh_failed",
                "Nao foi possivel concluir a atualizacao desta empresa agora.",
            )

        if has_readable_current_data:
            return ("local_data_ready", "Leitura local pronta para consulta.")

        return (
            "no_local_history_yet",
            "Esta empresa ainda nao tem historico anual processado na base local.",
        )

    @staticmethod
    def _build_refresh_source_label(
        source_scope: Any,
        *,
        has_readable_current_data: bool,
    ) -> str:
        normalized_scope = str(source_scope or "").strip().lower()
        if normalized_scope == "local":
            return (
                "Base local materializada"
                if has_readable_current_data
                else "Base local"
            )
        if normalized_scope == "on_demand":
            return "Solicitacao on-demand"
        if normalized_scope == "on_demand_bootstrap":
            return "Primeira carga on-demand"
        if normalized_scope == "ranked_backfill":
            return "Backfill historico"
        return "Leitura CVM processada"

    @staticmethod
    def _is_refresh_retry_allowed(
        *,
        tracking_state: str,
        active_job: dict[str, Any] | None,
    ) -> bool:
        if tracking_state in {"no_data", "error"}:
            return True
        return tracking_state == "stalled" and active_job is None

    def _load_refresh_status_map(
        self,
        cd_cvms: list[int] | None = None,
    ) -> dict[int, dict[str, Any]]:
        if not inspect(self.engine).has_table("company_refresh_status"):
            return {}

        if cd_cvms:
            query = text(
                """
                SELECT *
                FROM company_refresh_status
                WHERE cd_cvm IN :cd_cvms
                """
            ).bindparams(bindparam("cd_cvms", expanding=True))
            params = {"cd_cvms": [int(cd_cvm) for cd_cvm in cd_cvms]}
        else:
            query = text("SELECT * FROM company_refresh_status")
            params = {}

        with self.engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()
        return {int(row["cd_cvm"]): dict(row) for row in rows}

    def _load_active_refresh_jobs_map(
        self,
        cd_cvms: list[int] | None = None,
    ) -> dict[int, dict[str, Any]]:
        if not inspect(self.engine).has_table("refresh_jobs"):
            return {}

        if cd_cvms:
            query = text(
                """
                SELECT *
                FROM refresh_jobs
                WHERE state IN ('queued', 'running')
                  AND cd_cvm IN :cd_cvms
                ORDER BY
                    CASE WHEN state = 'running' THEN 0 ELSE 1 END,
                    requested_at ASC,
                    id ASC
                """
            ).bindparams(bindparam("cd_cvms", expanding=True))
            params = {"cd_cvms": [int(cd_cvm) for cd_cvm in cd_cvms]}
        else:
            query = text(
                """
                SELECT *
                FROM refresh_jobs
                WHERE state IN ('queued', 'running')
                ORDER BY
                    CASE WHEN state = 'running' THEN 0 ELSE 1 END,
                    requested_at ASC,
                    id ASC
                """
            )
            params = {}

        with self.engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()

        active_jobs: dict[int, dict[str, Any]] = {}
        for row in rows:
            cd_cvm = int(row["cd_cvm"])
            if cd_cvm not in active_jobs:
                active_jobs[cd_cvm] = dict(row)
        return active_jobs

    def _default_refresh_year_span(self) -> int:
        start_year, end_year = self._resolve_refresh_range(
            start_year=2010,
            end_year=None,
        )
        return max(1, int(end_year) - int(start_year) + 1)

    def _refresh_year_span(self, row: dict[str, Any]) -> int:
        start_year = row.get("last_start_year")
        end_year = row.get("last_end_year")
        if start_year is None or end_year is None:
            return self._default_refresh_year_span()
        try:
            year_span = int(end_year) - int(start_year) + 1
        except (TypeError, ValueError):
            return self._default_refresh_year_span()
        return max(1, year_span)

    def _estimate_refresh_duration_profile(self) -> dict[str, Any]:
        typical_year_span = float(self._default_refresh_year_span())
        year_span_samples = 0

        if inspect(self.engine).has_table("company_refresh_status"):
            query = text(
                """
                SELECT last_start_year, last_end_year
                FROM company_refresh_status
                WHERE last_status = 'success'
                  AND last_start_year IS NOT NULL
                  AND last_end_year IS NOT NULL
                ORDER BY last_success_at DESC
                LIMIT 200
                """
            )
            with self.engine.connect() as conn:
                rows = conn.execute(query).mappings().all()

            year_spans = []
            for row in rows:
                try:
                    year_span = int(row["last_end_year"]) - int(row["last_start_year"]) + 1
                except (TypeError, ValueError):
                    continue
                if year_span > 0:
                    year_spans.append(year_span)

            if year_spans:
                typical_year_span = float(median(year_spans))
                year_span_samples = len(year_spans)

        throughput = self._estimate_refresh_throughput()
        per_hour = throughput.get("per_hour")
        typical_total_seconds = (
            max(60.0, 3600.0 / float(per_hour))
            if per_hour
            else float(self.REFRESH_ESTIMATE_DEFAULT_TOTAL_SECONDS)
        )

        return {
            "typical_year_span": max(1.0, typical_year_span),
            "typical_total_seconds": float(typical_total_seconds),
            "sample_size": max(
                int(throughput.get("sample_size") or 0),
                int(year_span_samples),
            ),
            "confidence": str(throughput.get("confidence") or "low"),
        }

    def _estimate_refresh_runtime(
        self,
        row: dict[str, Any],
        *,
        duration_profile: dict[str, Any] | None,
        active_job: dict[str, Any] | None,
        tracking_state: str,
    ) -> dict[str, Any]:
        active_state = (
            self._normalize_refresh_status(active_job.get("state"))
            if active_job is not None
            else self._normalize_refresh_status(row.get("last_status"))
        )
        if tracking_state not in {"queued", "running", "stalled"}:
            return {
                "estimated_progress_pct": None,
                "estimated_eta_seconds": None,
                "estimated_total_seconds": None,
                "elapsed_seconds": None,
                "estimated_completion_at": None,
                "estimate_confidence": None,
                "progress_mode": "none",
            }

        real_progress_estimate = self._estimate_refresh_runtime_from_real_progress(
            row,
            tracking_state=tracking_state,
        )
        if real_progress_estimate is not None:
            return real_progress_estimate

        attempted_at = (
            self._parse_timestamp(row.get("started_at"))
            or self._parse_timestamp(row.get("last_attempt_at"))
            or (
                self._parse_timestamp(active_job.get("requested_at"))
                if active_job is not None
                else None
            )
        )
        now = datetime.now(timezone.utc)
        elapsed_seconds = (
            max(0, int(round((now - attempted_at).total_seconds())))
            if attempted_at is not None
            else None
        )

        if active_state == "queued" and tracking_state != "running":
            queue_position = (
                int(row["queue_position"])
                if row.get("queue_position") is not None
                else 0
            )
            estimated_progress_pct = min(
                32.0,
                self.REFRESH_QUEUE_PROGRESS_BASE
                + (min(max(queue_position, 0), 4) * self.REFRESH_QUEUE_PROGRESS_STEP),
            )
            if tracking_state == "stalled":
                estimated_progress_pct = max(estimated_progress_pct, 22.0)
            return {
                "estimated_progress_pct": round(float(estimated_progress_pct), 1),
                "estimated_eta_seconds": None,
                "estimated_total_seconds": None,
                "elapsed_seconds": elapsed_seconds,
                "estimated_completion_at": None,
                "estimate_confidence": "low",
                "progress_mode": "stalled" if tracking_state == "stalled" else "queue",
            }

        profile = duration_profile or self._estimate_refresh_duration_profile()
        typical_year_span = max(
            1.0,
            float(profile.get("typical_year_span") or self._default_refresh_year_span()),
        )
        current_year_span = float(self._refresh_year_span(row))
        typical_total_seconds = max(
            60.0,
            float(
                profile.get("typical_total_seconds")
                or self.REFRESH_ESTIMATE_DEFAULT_TOTAL_SECONDS
            ),
        )
        estimated_total_seconds = max(
            60,
            int(round(typical_total_seconds * (current_year_span / typical_year_span))),
        )
        estimated_completion_at = (
            (
                attempted_at + timedelta(seconds=estimated_total_seconds)
                if attempted_at is not None
                else now + timedelta(seconds=estimated_total_seconds)
            )
            .replace(microsecond=0)
            .isoformat()
        )

        if elapsed_seconds is None:
            estimated_progress_pct = self.REFRESH_ESTIMATE_PROGRESS_FLOOR
            estimated_eta_seconds = estimated_total_seconds
        else:
            ratio = float(elapsed_seconds) / float(estimated_total_seconds)
            estimated_progress_pct = self.REFRESH_ESTIMATE_PROGRESS_FLOOR + (
                min(1.0, ratio)
                * (
                    self.REFRESH_ESTIMATE_PROGRESS_CEILING
                    - self.REFRESH_ESTIMATE_PROGRESS_FLOOR
                )
            )
            if ratio > 1.0:
                estimated_progress_pct = min(
                    self.REFRESH_RUNNING_PROGRESS_CAP,
                    estimated_progress_pct + min(6.0, (ratio - 1.0) * 10.0),
                )
            estimated_eta_seconds = max(0, estimated_total_seconds - elapsed_seconds)

        if active_state == "running":
            estimated_progress_pct = max(estimated_progress_pct, 28.0)

        if tracking_state == "stalled":
            return {
                "estimated_progress_pct": round(float(estimated_progress_pct), 1),
                "estimated_eta_seconds": None,
                "estimated_total_seconds": int(estimated_total_seconds),
                "elapsed_seconds": elapsed_seconds,
                "estimated_completion_at": None,
                "estimate_confidence": str(profile.get("confidence") or "low"),
                "progress_mode": "stalled",
            }

        return {
            "estimated_progress_pct": round(float(estimated_progress_pct), 1),
            "estimated_eta_seconds": int(estimated_eta_seconds),
            "estimated_total_seconds": int(estimated_total_seconds),
            "elapsed_seconds": elapsed_seconds,
            "estimated_completion_at": estimated_completion_at,
            "estimate_confidence": str(profile.get("confidence") or "low"),
            "progress_mode": "time_window",
        }

    def _estimate_refresh_runtime_from_real_progress(
        self,
        row: dict[str, Any],
        *,
        tracking_state: str,
    ) -> dict[str, Any] | None:
        stage = str(row.get("stage") or "").strip().lower()
        if stage not in REFRESH_STAGE_WEIGHTS:
            return None

        raw_total = row.get("progress_total")
        raw_current = row.get("progress_current")
        total = max(1, int(raw_total or 1))
        current = max(0, min(total, int(raw_current or 0)))

        completed_before_stage = 0.0
        for stage_name in REFRESH_STAGE_ORDER:
            if stage_name == stage:
                break
            completed_before_stage += float(REFRESH_STAGE_WEIGHTS[stage_name])

        stage_weight = float(REFRESH_STAGE_WEIGHTS[stage])
        stage_ratio = min(1.0, max(0.0, float(current) / float(total)))
        progress_pct = completed_before_stage + (stage_weight * stage_ratio)
        progress_pct = max(0.0, min(100.0, progress_pct))

        started_at = self._parse_timestamp(row.get("started_at")) or self._parse_timestamp(
            row.get("last_attempt_at")
        )
        now = datetime.now(timezone.utc)
        elapsed_seconds = (
            max(0, int(round((now - started_at).total_seconds())))
            if started_at is not None
            else None
        )

        estimated_total_seconds: int | None = None
        estimated_eta_seconds: int | None = None
        estimated_completion_at: str | None = None
        if elapsed_seconds is not None and progress_pct > 0.0:
            progress_ratio = min(1.0, max(0.0001, progress_pct / 100.0))
            if progress_ratio >= 1.0:
                estimated_total_seconds = elapsed_seconds
                estimated_eta_seconds = 0
                estimated_completion_at = now.replace(microsecond=0).isoformat()
            else:
                estimated_total_seconds = max(
                    elapsed_seconds,
                    int(round(float(elapsed_seconds) / progress_ratio)),
                )
                estimated_eta_seconds = max(
                    0,
                    int(estimated_total_seconds) - int(elapsed_seconds),
                )
                estimated_completion_at = (
                    started_at + timedelta(seconds=int(estimated_total_seconds))
                ).replace(microsecond=0).isoformat()

        if tracking_state == "stalled":
            estimated_eta_seconds = None
            estimated_completion_at = None

        return {
            "estimated_progress_pct": round(float(progress_pct), 1),
            "estimated_eta_seconds": estimated_eta_seconds,
            "estimated_total_seconds": estimated_total_seconds,
            "elapsed_seconds": elapsed_seconds,
            "estimated_completion_at": estimated_completion_at,
            "estimate_confidence": "high",
            "progress_mode": (
                "stalled" if tracking_state == "stalled" else "real_progress"
            ),
        }

    def _estimate_refresh_throughput(self) -> dict[str, Any]:
        if not inspect(self.engine).has_table("company_refresh_status"):
            return {"per_hour": None, "sample_size": 0, "confidence": "low"}

        query = text(
            """
            SELECT last_success_at
            FROM company_refresh_status
            WHERE last_status = 'success'
              AND last_success_at IS NOT NULL
            ORDER BY last_success_at DESC
            LIMIT 200
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()

        parsed = [
            timestamp
            for timestamp in (
                self._parse_timestamp(row.get("last_success_at"))
                for row in rows
            )
            if timestamp is not None
        ]
        if not parsed:
            return {"per_hour": None, "sample_size": 0, "confidence": "low"}

        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=self.THROUGHPUT_WINDOW_HOURS)
        recent = sorted(timestamp for timestamp in parsed if timestamp >= recent_cutoff)
        if len(recent) < self.THROUGHPUT_MIN_SUCCESS_SAMPLES:
            return {"per_hour": None, "sample_size": len(recent), "confidence": "low"}

        span_hours = (recent[-1] - recent[0]).total_seconds() / 3600.0
        if span_hours <= 0:
            return {"per_hour": None, "sample_size": len(recent), "confidence": "low"}

        per_hour = max(0.0, (len(recent) - 1) / span_hours)
        confidence = "high" if len(recent) >= 12 and span_hours >= 6 else "medium"
        return {
            "per_hour": float(per_hour) if per_hour > 0 else None,
            "sample_size": len(recent),
            "confidence": confidence if per_hour > 0 else "low",
        }

    def _ensure_refresh_status_table(self, conn) -> None:
        ensure_refresh_runtime_tables_for_connection(conn)

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if value is None:
            return None
        raw_value = str(value).strip()
        if not raw_value:
            return None
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_recently_queued(
        self,
        status_row: dict[str, Any] | Any,
        *,
        window: timedelta,
    ) -> bool:
        if not status_row:
            return False
        last_status = (
            str(status_row.get("last_status") or "").strip().lower()
            if hasattr(status_row, "get")
            else str(getattr(status_row, "last_status", "") or "").strip().lower()
        )
        if last_status != "queued":
            return False
        last_attempt_at = (
            status_row.get("last_attempt_at")
            if hasattr(status_row, "get")
            else getattr(status_row, "last_attempt_at", None)
        )
        attempted_at = self._parse_timestamp(last_attempt_at)
        if attempted_at is None:
            return False
        return (datetime.now(timezone.utc) - attempted_at) < window

    def _priority_score(
        self,
        *,
        coverage_rank: int | None,
        missing_years_count: int,
        gap_to_leader_years: int,
    ) -> int:
        normalized_rank = coverage_rank if coverage_rank is not None else 999
        rank_score = max(0, 81 - int(normalized_rank)) * 100
        return int(rank_score + (int(missing_years_count) * 25) + (int(gap_to_leader_years) * 10))

    def _risk_level(
        self,
        *,
        coverage_rank: int | None,
        missing_years_count: int,
        excluded_from_queue: bool,
    ) -> str:
        if excluded_from_queue:
            return "alto"
        if missing_years_count <= 0:
            return "baixo"
        if coverage_rank is not None and coverage_rank <= 20:
            return "alto"
        if coverage_rank is not None and coverage_rank <= 50:
            return "medio"
        if missing_years_count >= 3:
            return "medio"
        return "baixo"

    def _health_status_from_score(self, score: float) -> str:
        if score >= self.BASE_HEALTH_OK_THRESHOLD:
            return "ok"
        if score >= self.BASE_HEALTH_CRITICAL_THRESHOLD:
            return "atencao"
        return "critico"

    def _build_company_results(self, df: pd.DataFrame) -> list[CompanySearchResult]:
        results = []
        if df is None or df.empty:
            return results

        for _, row in df.iterrows():
            setor_analitico = self._clean_optional_text(row.get("setor_analitico"))
            setor_cvm = self._clean_optional_text(row.get("setor_cvm"))
            raw_sector_name = self._clean_optional_text(row.get("sector_name"))
            sector_name = raw_sector_name or canonical_sector_name(setor_analitico, setor_cvm)
            gics = resolve_gics_classification(
                sector_name=sector_name,
                setor_analitico=setor_analitico,
                setor_cvm=setor_cvm,
                gics_sector=row.get("persisted_gics_sector"),
                gics_sector_slug=row.get("persisted_gics_sector_slug"),
                gics_industry_group=row.get("persisted_gics_industry_group"),
                gics_industry=row.get("persisted_gics_industry"),
                gics_sub_industry=row.get("persisted_gics_sub_industry"),
            )
            raw_coverage_rank = row.get("coverage_rank")
            anos = _parse_years(row.get("anos_disponiveis"))
            has_data = bool(int(row.get("has_financial_data") or 0))
            raw_status = str(row.get("data_status") or "").strip()
            # Precedence: failed > unmapped > explicit status > heuristic
            # "complete" only when coverage_rank confirms the company is tracked with data.
            # Heuristic year count is intentionally NOT used to claim "complete".
            if raw_status == "failed":
                data_status = "failed"
            elif raw_status == "unmapped":
                data_status = "unmapped"
            elif raw_status in ("no_history", "partial", "complete"):
                data_status = raw_status
            elif not has_data:
                data_status = "no_history"
            elif raw_coverage_rank is not None and str(raw_coverage_rank) not in ("", "nan"):
                data_status = "complete"
            else:
                data_status = "partial"
            results.append(
                CompanySearchResult(
                    cd_cvm=int(row["cd_cvm"]),
                    company_name=str(row["company_name"]),
                    ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                    setor_analitico=setor_analitico,
                    setor_cvm=setor_cvm,
                    sector_name=sector_name,
                    sector_slug=sector_slugify(sector_name),
                    anos_disponiveis=anos,
                    total_rows=int(row.get("total_rows") or 0),
                    has_financial_data=has_data,
                    coverage_rank=int(raw_coverage_rank) if raw_coverage_rank is not None and str(raw_coverage_rank) != "nan" else None,
                    gics_sector=gics.gics_sector if gics else None,
                    gics_sector_slug=gics.gics_sector_slug if gics else None,
                    gics_industry_group=gics.gics_industry_group if gics else None,
                    gics_industry=gics.gics_industry if gics else None,
                    gics_sub_industry=gics.gics_sub_industry if gics else None,
                    data_status=data_status,
                )
            )
        return results

    def _merge_catalog_with_db(self) -> list[CompanySearchResult]:
        """Full catalog × DB merge — always returns all active catalog companies.

        For each catalog entry the local DB row is used when present (has
        financial-data counts, GICS, coverage_rank).  Catalog-only entries get
        a lightweight stub (name, ticker, legacy sector).

        Unlike _list_company_universe_results this method is never gated by the
        CATALOG_FALLBACK_MIN_LOCAL_COMPANIES threshold, so it always exposes the
        full known universe regardless of how many companies have been downloaded.
        """
        local_items = self._load_local_company_universe_results()
        try:
            catalog_entries = [entry for entry in self.company_catalog.list_entries() if entry.is_active]
        except CompanyCatalogUnavailableError:
            return local_items
        if not catalog_entries:
            return local_items

        page_codes = [int(entry.cd_cvm) for entry in catalog_entries]
        local_results_by_code: dict[int, CompanySearchResult] = {}
        if page_codes:
            local_rows = self.query_layer.get_companies_by_cvm_ids(page_codes)
            if not local_rows.empty:
                local_rows = local_rows.copy()
                years_map = self.query_layer.get_company_years_map(local_rows["cd_cvm"].tolist())
                local_rows["anos_disponiveis"] = local_rows["cd_cvm"].map(
                    lambda cd_cvm: years_map.get(int(cd_cvm), ())
                )
                local_results_by_code = {
                    int(item.cd_cvm): item for item in self._build_company_results(local_rows)
                }

        # Also include DB-only companies not present in the catalog
        catalog_codes = {int(entry.cd_cvm) for entry in catalog_entries}
        items: list[CompanySearchResult] = []
        seen: set[int] = set()

        for entry in catalog_entries:
            cd = int(entry.cd_cvm)
            seen.add(cd)
            local_result = local_results_by_code.get(cd)
            if local_result is not None:
                items.append(local_result)
                continue
            legacy_sector = canonical_sector_name(None, entry.setor_cvm)
            items.append(
                CompanySearchResult(
                    cd_cvm=cd,
                    company_name=entry.company_name,
                    ticker_b3=entry.ticker_b3,
                    setor_analitico=None,
                    setor_cvm=entry.setor_cvm,
                    sector_name=legacy_sector,
                    sector_slug=sector_slugify(legacy_sector),
                    anos_disponiveis=(),
                    total_rows=0,
                    has_financial_data=False,
                    coverage_rank=None,
                    gics_sector=None,
                    gics_sector_slug=None,
                    gics_industry_group=None,
                    gics_industry=None,
                    gics_sub_industry=None,
                )
            )

        # Append any local DB companies not in catalog (custom/imported entities)
        for item in local_items:
            if item.cd_cvm not in seen:
                items.append(item)

        return items

    def _list_company_universe_results(self) -> list[CompanySearchResult]:
        self._ensure_read_cache_fresh()
        if self._company_universe_cache is not None:
            return list(self._company_universe_cache)

        def _cache_and_return(items: list[CompanySearchResult]) -> list[CompanySearchResult]:
            self._company_universe_cache = tuple(items)
            return list(self._company_universe_cache)

        local_items = self._load_local_company_universe_results()
        if len(local_items) >= self.CATALOG_FALLBACK_MIN_LOCAL_COMPANIES:
            return _cache_and_return(local_items)

        merged = self._merge_catalog_with_db()
        return _cache_and_return(merged)

    def _sector_company_preview(
        self,
        items: list[CompanySearchResult],
        limit: int = 12,
    ) -> tuple[SectorCompanyMetricDTO, ...]:
        ordered = sorted(
            items,
            key=lambda item: (
                0 if item.has_financial_data else 1,
                item.company_name.upper(),
            ),
        )
        return tuple(
            SectorCompanyMetricDTO(
                cd_cvm=int(item.cd_cvm),
                company_name=str(item.company_name),
                ticker_b3=item.ticker_b3,
                gics_sub_industry=item.gics_sub_industry,
                roe=None,
                mg_ebit=None,
                mg_liq=None,
            )
            for item in ordered[: int(limit)]
        )

    @staticmethod
    def _clean_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        if pd.isna(value):
            return None
        text_value = str(value).strip()
        return text_value or None

    def _resolve_sector_slug(self, sector_slug: str | None) -> str | None:
        if not sector_slug:
            return None
        normalized_slug = str(sector_slug).strip().lower()
        if not normalized_slug:
            return None
        for option in self.get_company_filters().sectors:
            if option.sector_slug == normalized_slug:
                return option.sector_name
        return None

    @staticmethod
    def _extract_years_from_company_rows(df: pd.DataFrame) -> list[int]:
        years: set[int] = set()
        if df is None or df.empty:
            return []
        for raw_years in df.get("anos_disponiveis", []):
            years.update(_parse_years(raw_years))
        return sorted(years)

    @staticmethod
    def _aggregate_sector_yearly_metrics(metric_rows: pd.DataFrame) -> pd.DataFrame:
        if metric_rows is None or metric_rows.empty:
            return pd.DataFrame(columns=["sector_name", "year", "roe", "mg_ebit", "mg_liq"])

        aggregated = (
            metric_rows.groupby(["sector_name", "report_year"], dropna=False)[["roe", "mg_ebit", "mg_liq"]]
            .mean()
            .reset_index()
            .rename(columns={"report_year": "year"})
        )
        return aggregated

    @staticmethod
    def _coerce_optional_float(value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    @staticmethod
    def _empty_company_page(
        *,
        search: str,
        sector_slug: str | None,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage:
        return CompanyDirectoryPage(
            items=(),
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=0,
                total_pages=1,
                has_next=False,
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )
