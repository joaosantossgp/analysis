from __future__ import annotations

import functools
import json
import time
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable

import pandas as pd
from sqlalchemy import bindparam, inspect, text

from src.companies.catalog import (
    CompanyCatalogEntry,
    CompanyCatalogUnavailableError,
    CompanyCatalogService,
)
from src.companies.gics_manual_mapping import (
    GICS_11_SECTORS,
    gics_sector_sort_key,
    resolve_gics_classification,
    resolve_gics_sector_name,
)
from src.platform.contracts import (
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
from src.refresh.jobs import (
    REFRESH_STAGE_ORDER,
    REFRESH_STAGE_WEIGHTS,
    RefreshJobRepository,
    ensure_refresh_runtime_tables_for_connection,
)
from src.refresh.service import HeadlessRefreshService
from src.financials.statement_summary import build_general_summary_blocks
from src.platform.db import build_engine
from src.financials.excel_exporter import (
    ExcelExporter,
    build_default_model_mapping,
    build_excel_filename,
    _is_annual_period,
    _period_sort_key,
)
from src.financials.excel_mapping import (
    SYSTEM_DEFAULT_PRESET_ID,
    VALID_MAPPING_OPERATIONS,
    ExcelMappingRepository,
    MappingValidationIssue,
    ModelMappingDefinition,
    ModelMappingEntry,
    ModelMappingSource,
)
from src.financials.kpi_engine import compute_all_kpis, compute_quarterly_kpis
from src.financials.query_layer import CVMQueryLayer
from src.companies.sector_taxonomy import canonical_sector_name, sector_slugify
from src.platform.settings import AppSettings, get_settings
from src.financials.utils import current_reporting_year_cap, normalize_account_name, now_iso_seconds

EXPORT_STATEMENT_TYPES = ("DRE", "BPA", "BPP", "DFC")

# Top-10 B3 companies by approximate market cap, ordered largest-first.
# cd_cvm values sourced from src/companies/ticker_map.py.
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
        # Keep the caller's order (data updates process listed companies first).
        position = {int(value): index for index, value in enumerate(company_ids)}
        items = sorted(
            (item for item in items if int(_get_batch_attr(item, "cd_cvm") or 0) in position),
            key=lambda item: position[int(_get_batch_attr(item, "cd_cvm") or 0)],
        )

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
