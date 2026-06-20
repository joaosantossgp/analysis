# -*- coding: utf-8 -*-
"""
src/financials/query_layer.py - API de leitura do banco CVM.

Centraliza toda logica de SELECT para que dashboard, scripts e testes
nao precisem escrever SQL raw. Depende apenas de sqlalchemy + pandas.

Schema relevante:
  financial_reports: id, COMPANY_NAME, CD_CVM, COMPANY_TYPE, STATEMENT_TYPE,
                     REPORT_YEAR, PERIOD_LABEL, LINE_ID_BASE, CD_CONTA, DS_CONTA,
                     STANDARD_NAME, QA_CONFLICT, VL_CONTA
  companies:         cd_cvm, company_name, nome_comercial, cnpj, setor_cvm,
                     setor_analitico, company_type, ticker_b3, is_active, updated_at

Note: financial_reports columns were created with quoted uppercase identifiers
(e.g. "CD_CVM"). PostgreSQL treats quoted identifiers as case-sensitive, so all
references to those columns must also be double-quoted in raw SQL. The companies
table uses lowercase unquoted names and needs no quoting.
"""
from __future__ import annotations

import functools
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Engine, inspect, text

from src.platform.db import get_engine
from src.companies.sector_taxonomy import canonical_sector_sql, gics_sector_bucket_sql
from src.financials.marts import DIRECTORY_MART_NAME, KPI_ACCOUNT_MART_NAME, PERIOD_MART_NAME

if TYPE_CHECKING:
    import pandas as pd

_logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _pd():
    import pandas as pd

    return pd


def slow_query_warn(threshold_ms: float = 200.0):
    """Decorator that emits a structured WARN log when the wrapped method exceeds threshold_ms.

    Usage::

        @slow_query_warn(threshold_ms=200)
        def get_companies_directory_page(self, ...):
            ...

    The log record is a JSON line compatible with the existing observability format::

        {"event": "slow_query", "query": "get_companies_directory_page",
         "elapsed_ms": 312.4, "threshold_ms": 200.0}
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                if elapsed_ms > threshold_ms:
                    _logger.warning(
                        json.dumps(
                            {
                                "event": "slow_query",
                                "query": func.__name__,
                                "elapsed_ms": round(elapsed_ms, 1),
                                "threshold_ms": threshold_ms,
                            }
                        )
                    )

        return wrapper

    return decorator

_KPI_ACCOUNTS = {
    "Receita": "3.01",
    "Res_Bruto": "3.03",
    "EBIT": "3.05",
    "Lucro_Liq": "3.11",
    "PL": "2.03",
    "Ativo_Total": "1",
    "Passivo_Total": "2",
    "PC": "2.01",
    "PNC": "2.02",
    "AC": "1.01",
    "Caixa": "1.01.01",
    "FCO": "6.01",
    "FCI": "6.02",
    "FCF": "6.03",
}

_REQUIRED_PERIOD_STATEMENTS = ("BPA", "BPP", "DRE", "DFC")
_ANNUAL_PERIOD_RE = re.compile(r"^(?:19|20)\d{2}$")
_QUARTER_PERIOD_RE = re.compile(r"^([1-4])[QT](\d{2}|\d{4})$", flags=re.IGNORECASE)

_CANONICAL_SECTOR_SQL = canonical_sector_sql("c")

_HAS_ANNUAL_HISTORY_SQL = """
EXISTS (
    SELECT 1
    FROM financial_reports fr_ready
    WHERE fr_ready."CD_CVM" = c.cd_cvm
      AND fr_ready."PERIOD_LABEL" = CAST(fr_ready."REPORT_YEAR" AS TEXT)
)
"""


def _parse_period_label(label: object) -> tuple[int, int | None] | None:
    text_value = str(label or "").strip()
    if _ANNUAL_PERIOD_RE.match(text_value):
        return int(text_value), None
    q_match = _QUARTER_PERIOD_RE.match(text_value)
    if not q_match:
        return None
    year_text = q_match.group(2)
    year = int(year_text) if len(year_text) == 4 else 2000 + int(year_text)
    return year, int(q_match.group(1))


def _period_sort_key(label: str) -> tuple[int, int]:
    parsed = _parse_period_label(label)
    if parsed is None:
        return (9999, 99)
    year, quarter = parsed
    return (year, 5 if quarter is None else quarter)


def _period_display_label(label: object) -> str | None:
    parsed = _parse_period_label(label)
    if parsed is None:
        return None
    year, quarter = parsed
    if quarter is None:
        return f"FY{year}"
    return f"{quarter}Q{year % 100:02d}"


def _period_type(label: object) -> str | None:
    parsed = _parse_period_label(label)
    if parsed is None:
        return None
    return "annual" if parsed[1] is None else "quarter"


def _optional_float(value) -> float | None:
    try:
        if value is None or _pd().isna(value):
            return None
        return float(value)
    except Exception:
        return None


class CVMQueryLayer:
    """Camada de leitura reutilizavel do banco CVM."""

    def __init__(self, engine: Optional[Engine] = None):
        self.engine = engine or get_engine()
        self._company_columns: frozenset[str] | None = None
        self._mart_ready_cache: dict[str, bool] = {}

    def _company_column_names(self) -> frozenset[str]:
        if self._company_columns is None:
            try:
                insp = inspect(self.engine)
                self._company_columns = frozenset(
                    str(c.get("name") or "").lower()
                    for c in insp.get_columns("companies")
                )
            except Exception:
                self._company_columns = frozenset()
        return self._company_columns

    def _persisted_gics_max_sql(self) -> str:
        cols = self._company_column_names()
        parts: list[str] = []
        mapping = (
            ("gics_sector", "persisted_gics_sector"),
            ("gics_sector_slug", "persisted_gics_sector_slug"),
            ("gics_industry_group", "persisted_gics_industry_group"),
            ("gics_industry", "persisted_gics_industry"),
            ("gics_sub_industry", "persisted_gics_sub_industry"),
        )
        for col, alias in mapping:
            if col in cols:
                parts.append(f"MAX(c.{col}) AS {alias}")
        if not parts:
            return ""
        return ",\n                " + ",\n                ".join(parts)

    def _persisted_gics_select_sql(self) -> str:
        cols = self._company_column_names()
        parts: list[str] = []
        mapping = (
            ("gics_sector", "persisted_gics_sector"),
            ("gics_sector_slug", "persisted_gics_sector_slug"),
            ("gics_industry_group", "persisted_gics_industry_group"),
            ("gics_industry", "persisted_gics_industry"),
            ("gics_sub_industry", "persisted_gics_sub_industry"),
        )
        for col, alias in mapping:
            if col in cols:
                parts.append(f"c.{col} AS {alias}")
        if not parts:
            return ""
        return ",\n                " + ",\n                ".join(parts)

    def _sector_bucket_expression_sql(self) -> str:
        """Prefer persisted GICS sector label when present for histograms/filters."""
        return gics_sector_bucket_sql(self._company_column_names(), table_alias="c")

    def _is_financial_mart_ready(self, mart_name: str) -> bool:
        cached = self._mart_ready_cache.get(mart_name)
        if cached is not None:
            return cached
        ready = False
        try:
            inspector = inspect(self.engine)
            if inspector.has_table(mart_name) and inspector.has_table("financial_mart_builds"):
                with self.engine.connect() as conn:
                    row = conn.execute(
                        text("""
                            SELECT status, row_count
                            FROM financial_mart_builds
                            WHERE mart_name = :mart_name
                            LIMIT 1
                        """),
                        {"mart_name": mart_name},
                    ).mappings().first()
                ready = bool(row and row["status"] == "success" and int(row["row_count"] or 0) >= 0)
        except Exception:
            _logger.debug("financial mart readiness check failed mart=%s", mart_name, exc_info=True)
            ready = False
        self._mart_ready_cache[mart_name] = ready
        return ready

    def clear_financial_mart_readiness_cache(self) -> None:
        self._mart_ready_cache.clear()

    def get_companies(self, search: str = "") -> _pd().DataFrame:
        rows_df, _ = self.get_companies_directory_page(
            search=search,
            sector_name=None,
            page=1,
            page_size=None,
        )
        if rows_df.empty:
            rows_df["anos_disponiveis"] = []
            return rows_df.reset_index(drop=True)

        years_map = self.get_company_years_map(rows_df["cd_cvm"].tolist())
        rows_df = rows_df.copy()
        rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(
            lambda cd_cvm: ",".join(str(year) for year in years_map.get(int(cd_cvm), ()))
        )
        return rows_df.reset_index(drop=True)

    @slow_query_warn(threshold_ms=200)
    def get_companies_directory_page(
        self,
        *,
        search: str = "",
        sector_name: str | None = None,
        page: int = 1,
        page_size: int | None = 20,
    ) -> tuple[_pd().DataFrame, int]:
        if self._is_financial_mart_ready(DIRECTORY_MART_NAME):
            return self._get_companies_directory_page_from_mart(
                search=search,
                sector_name=sector_name,
                page=page,
                page_size=page_size,
            )

        where_sql, params = self._company_directory_filters(search=search, sector_name=sector_name)

        count_sql = text(
            f"""
            SELECT COUNT(*) AS total_items
            FROM companies c
            WHERE {where_sql}
            """
        )
        total_items = int(_pd().read_sql(count_sql, self.engine, params=params).iloc[0]["total_items"])

        paging_sql = ""
        paged_params = dict(params)
        if page_size is not None:
            paging_sql = " LIMIT :limit OFFSET :offset"
            paged_params["limit"] = int(page_size)
            paged_params["offset"] = max(0, (int(page) - 1) * int(page_size))

        gics_sql = self._persisted_gics_select_sql()
        rows_sql = text(
            f"""
            WITH ranked AS (
                SELECT
                    c.cd_cvm,
                    c.company_name,
                    COALESCE(c.ticker_b3, '') AS ticker_b3,
                    c.setor_analitico,
                    c.setor_cvm,
                    {_CANONICAL_SECTOR_SQL} AS sector_name,
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM financial_reports fr_exists
                            WHERE fr_exists."CD_CVM" = c.cd_cvm
                            LIMIT 1
                        ) THEN 1
                        ELSE 0
                    END AS has_financial_data,
                    c.coverage_rank{gics_sql}
                FROM companies c
                WHERE {where_sql}
            ),
            page AS (
                SELECT *
                FROM ranked
                ORDER BY
                    CASE WHEN has_financial_data > 0 THEN 0 ELSE 1 END ASC,
                    CASE WHEN coverage_rank IS NULL THEN 1 ELSE 0 END ASC,
                    coverage_rank ASC,
                    company_name ASC
                {paging_sql}
            ),
            page_counts AS (
                SELECT fr."CD_CVM" AS cd_cvm, COUNT(*) AS total_rows
                FROM financial_reports fr
                WHERE fr."CD_CVM" IN (SELECT cd_cvm FROM page)
                GROUP BY fr."CD_CVM"
            )
            SELECT
                page.*,
                COALESCE(page_counts.total_rows, 0) AS total_rows
            FROM page
            LEFT JOIN page_counts ON page_counts.cd_cvm = page.cd_cvm
            ORDER BY
                CASE WHEN page.has_financial_data > 0 THEN 0 ELSE 1 END ASC,
                CASE WHEN page.coverage_rank IS NULL THEN 1 ELSE 0 END ASC,
                page.coverage_rank ASC,
                page.company_name ASC
            """
        )
        rows_df = _pd().read_sql(rows_sql, self.engine, params=paged_params)
        return rows_df.reset_index(drop=True), total_items

    def _get_companies_directory_page_from_mart(
        self,
        *,
        search: str = "",
        sector_name: str | None = None,
        page: int = 1,
        page_size: int | None = 20,
    ) -> tuple[_pd().DataFrame, int]:
        where_sql, params = self._company_directory_filters(search=search, sector_name=sector_name)

        count_sql = text(
            f"""
            SELECT COUNT(*) AS total_items
            FROM companies c
            LEFT JOIN {DIRECTORY_MART_NAME} dm ON dm.cd_cvm = c.cd_cvm
            WHERE {where_sql}
            """
        )
        total_items = int(_pd().read_sql(count_sql, self.engine, params=params).iloc[0]["total_items"])

        paging_sql = ""
        paged_params = dict(params)
        if page_size is not None:
            paging_sql = " LIMIT :limit OFFSET :offset"
            paged_params["limit"] = int(page_size)
            paged_params["offset"] = max(0, (int(page) - 1) * int(page_size))

        gics_sql = self._persisted_gics_select_sql()
        rows_sql = text(
            f"""
            SELECT
                c.cd_cvm,
                c.company_name,
                COALESCE(c.ticker_b3, '') AS ticker_b3,
                c.setor_analitico,
                c.setor_cvm,
                {_CANONICAL_SECTOR_SQL} AS sector_name,
                COALESCE(dm.has_financial_data, 0) AS has_financial_data,
                c.coverage_rank{gics_sql},
                COALESCE(dm.financial_row_count, 0) AS total_rows
            FROM companies c
            LEFT JOIN {DIRECTORY_MART_NAME} dm ON dm.cd_cvm = c.cd_cvm
            WHERE {where_sql}
            ORDER BY
                CASE WHEN COALESCE(dm.has_financial_data, 0) > 0 THEN 0 ELSE 1 END ASC,
                CASE WHEN c.coverage_rank IS NULL THEN 1 ELSE 0 END ASC,
                c.coverage_rank ASC,
                c.company_name ASC
            {paging_sql}
            """
        )
        rows_df = _pd().read_sql(rows_sql, self.engine, params=paged_params)
        return rows_df.reset_index(drop=True), total_items

    def get_available_company_sectors(self) -> _pd().DataFrame:
        bucket = self._sector_bucket_expression_sql()
        sql = text(
            f"""
            SELECT
                {bucket} AS sector_name,
                COUNT(DISTINCT c.cd_cvm) AS company_count
            FROM companies c
            LEFT JOIN financial_reports fr ON fr."CD_CVM" = c.cd_cvm
            GROUP BY {bucket}
            ORDER BY sector_name ASC
            """
        )
        return _pd().read_sql(sql, self.engine).reset_index(drop=True)

    @slow_query_warn(threshold_ms=200)
    def get_companies_directory_light(self) -> _pd().DataFrame:
        """Return all local company rows without counting financial report rows.

        Used by in-memory catalog/market-cap merges where exact row counts are
        not needed for sorting or display. Avoids a full aggregation over the
        multi-million-row financial_reports table.
        """
        if self._is_financial_mart_ready(DIRECTORY_MART_NAME):
            return self._get_companies_directory_light_from_mart()

        gics_sql = self._persisted_gics_select_sql()
        sql = text(
            f"""
            SELECT
                c.cd_cvm,
                c.company_name,
                COALESCE(c.ticker_b3, '') AS ticker_b3,
                c.setor_analitico,
                c.setor_cvm,
                {_CANONICAL_SECTOR_SQL} AS sector_name,
                0 AS total_rows,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM financial_reports fr_exists
                        WHERE fr_exists."CD_CVM" = c.cd_cvm
                        LIMIT 1
                    ) THEN 1
                    ELSE 0
                END AS has_financial_data,
                c.coverage_rank{gics_sql}
            FROM companies c
            ORDER BY
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM financial_reports fr_exists
                        WHERE fr_exists."CD_CVM" = c.cd_cvm
                        LIMIT 1
                    ) THEN 0
                    ELSE 1
                END ASC,
                CASE WHEN c.coverage_rank IS NULL THEN 1 ELSE 0 END ASC,
                c.coverage_rank ASC,
                c.company_name ASC
            """
        )
        return _pd().read_sql(sql, self.engine).reset_index(drop=True)

    def _get_companies_directory_light_from_mart(self) -> _pd().DataFrame:
        gics_sql = self._persisted_gics_select_sql()
        sql = text(
            f"""
            SELECT
                c.cd_cvm,
                c.company_name,
                COALESCE(c.ticker_b3, '') AS ticker_b3,
                c.setor_analitico,
                c.setor_cvm,
                {_CANONICAL_SECTOR_SQL} AS sector_name,
                0 AS total_rows,
                COALESCE(dm.has_financial_data, 0) AS has_financial_data,
                c.coverage_rank{gics_sql}
            FROM companies c
            LEFT JOIN {DIRECTORY_MART_NAME} dm ON dm.cd_cvm = c.cd_cvm
            ORDER BY
                CASE WHEN COALESCE(dm.has_financial_data, 0) > 0 THEN 0 ELSE 1 END ASC,
                CASE WHEN c.coverage_rank IS NULL THEN 1 ELSE 0 END ASC,
                c.coverage_rank ASC,
                c.company_name ASC
            """
        )
        return _pd().read_sql(sql, self.engine).reset_index(drop=True)

    def get_sector_available_years(self, sector_name: str) -> list[int]:
        sql = text(
            f"""
            SELECT DISTINCT fr."REPORT_YEAR"
            FROM financial_reports fr
            JOIN companies c ON c.cd_cvm = fr."CD_CVM"
            WHERE {_CANONICAL_SECTOR_SQL} = :sector_name
              AND fr."PERIOD_LABEL" = CAST(fr."REPORT_YEAR" AS TEXT)
            ORDER BY fr."REPORT_YEAR"
            """
        )
        df = _pd().read_sql(sql, self.engine, params={"sector_name": str(sector_name)})
        return [int(year) for year in df["REPORT_YEAR"].tolist()]

    @functools.lru_cache(maxsize=10)
    def get_sector_years_map(self) -> dict[str, list[int]]:
        """Returns sector_name -> sorted list of years with annual data, for all sectors at once."""
        sql = text(
            f"""
            SELECT DISTINCT {_CANONICAL_SECTOR_SQL} AS sector_name, fr."REPORT_YEAR"
            FROM financial_reports fr
            JOIN companies c ON c.cd_cvm = fr."CD_CVM"
            WHERE fr."PERIOD_LABEL" = CAST(fr."REPORT_YEAR" AS TEXT)
            ORDER BY sector_name, fr."REPORT_YEAR"
            """
        )
        df = _pd().read_sql(sql, self.engine)
        result: dict[str, list[int]] = {}
        for _, row in df.iterrows():
            result.setdefault(str(row["sector_name"]), []).append(int(row["REPORT_YEAR"]))
        return result

    def get_company_suggestions(
        self,
        q: str,
        limit: int,
        *,
        ready_only: bool = False,
    ) -> _pd().DataFrame:
        """Returns up to `limit` companies ranked by relevance to query `q`.

        Ranking: exact ticker > name prefix > ticker prefix > contains match.
        Empty `q` returns the first `limit` companies alphabetically.
        """
        normalized = q.strip().lower()
        ready_only_sql = f"WHERE {_HAS_ANNUAL_HISTORY_SQL}" if ready_only else ""
        if not normalized:
            sql = text(
                f"""
                SELECT c.cd_cvm, c.company_name,
                       COALESCE(c.ticker_b3, '') AS ticker_b3,
                       {_CANONICAL_SECTOR_SQL} AS sector_name,
                       c.gics_sector,
                       c.gics_sector_slug
                FROM companies c
                {ready_only_sql}
                ORDER BY c.company_name ASC
                LIMIT :limit
                """
            )
            return _pd().read_sql(sql, self.engine, params={"limit": int(limit)}).reset_index(drop=True)

        search_filters = """
                LOWER(c.company_name) LIKE :contains
                OR LOWER(COALESCE(c.ticker_b3, '')) LIKE :contains
                OR CAST(c.cd_cvm AS TEXT) LIKE :contains
        """
        if ready_only:
            search_filters = f"({_HAS_ANNUAL_HISTORY_SQL}) AND ({search_filters})"

        sql = text(
            f"""
            SELECT c.cd_cvm, c.company_name,
                   COALESCE(c.ticker_b3, '') AS ticker_b3,
                   {_CANONICAL_SECTOR_SQL} AS sector_name,
                   c.gics_sector,
                   c.gics_sector_slug
            FROM companies c
            WHERE
                {search_filters}
            ORDER BY
                CASE
                    WHEN LOWER(COALESCE(c.ticker_b3, '')) = :exact   THEN 0
                    WHEN LOWER(c.company_name)             LIKE :prefix THEN 1
                    WHEN LOWER(COALESCE(c.ticker_b3, '')) LIKE :prefix THEN 2
                    ELSE 3
                END ASC,
                c.company_name ASC
            LIMIT :limit
            """
        )
        return _pd().read_sql(sql, self.engine, params={
            "contains": f"%{normalized}%",
            "prefix": f"{normalized}%",
            "exact": normalized,
            "limit": int(limit),
        }).reset_index(drop=True)

    def get_sector_companies(self, sector_name: str) -> tuple[_pd().DataFrame, int]:
        """Returns (df[cd_cvm, company_name, ticker_b3], total_count) for a sector.

        Lighter than get_companies_directory_page(page_size=None): no LEFT JOIN to
        financial_reports, no aggregation columns.
        """
        params = {"sector_name": str(sector_name)}
        count_sql = text(
            f"SELECT COUNT(*) AS total_items FROM companies c WHERE {_CANONICAL_SECTOR_SQL} = :sector_name"
        )
        total_items = int(
            _pd().read_sql(count_sql, self.engine, params=params).iloc[0]["total_items"]
        )
        rows_sql = text(
            f"""
            SELECT c.cd_cvm, c.company_name, COALESCE(c.ticker_b3, '') AS ticker_b3
            FROM companies c
            WHERE {_CANONICAL_SECTOR_SQL} = :sector_name
            ORDER BY c.company_name ASC
            """
        )
        df = _pd().read_sql(rows_sql, self.engine, params=params)
        return df.reset_index(drop=True), total_items

    @slow_query_warn(threshold_ms=200)
    def get_sector_metric_rows(
        self,
        *,
        sector_name: str | None = None,
        years: list[int] | None = None,
        cd_cvms: list[int] | None = None,
    ) -> _pd().DataFrame:
        result_columns = [
            "cd_cvm",
            "company_name",
            "ticker_b3",
            "sector_name",
            "report_year",
            "roe",
            "mg_ebit",
            "mg_liq",
        ]
        if self._is_financial_mart_ready(KPI_ACCOUNT_MART_NAME):
            return self._get_sector_metric_rows_from_kpi_mart(
                sector_name=sector_name,
                years=years,
                cd_cvms=cd_cvms,
                result_columns=result_columns,
            )

        where_parts = [
            'fr."PERIOD_LABEL" = CAST(fr."REPORT_YEAR" AS TEXT)',
            'fr."QA_CONFLICT" = false',
            """fr."CD_CONTA" IN ('3.01', '3.05', '3.11', '2.03')""",
        ]
        params: dict[str, object] = {}

        if sector_name:
            where_parts.append(f"{_CANONICAL_SECTOR_SQL} = :sector_name")
            params["sector_name"] = str(sector_name)

        normalized_years = sorted({int(year) for year in years or []})
        if normalized_years:
            placeholders = ", ".join(f":y{i}" for i in range(len(normalized_years)))
            where_parts.append(f'fr."REPORT_YEAR" IN ({placeholders})')
            params.update({f"y{i}": year for i, year in enumerate(normalized_years)})

        normalized_cd_cvms = sorted({int(cd_cvm) for cd_cvm in cd_cvms or []})
        if cd_cvms is not None and not normalized_cd_cvms:
            return _pd().DataFrame(columns=result_columns)
        if normalized_cd_cvms:
            placeholders = ", ".join(f":cd{i}" for i in range(len(normalized_cd_cvms)))
            where_parts.append(f'fr."CD_CVM" IN ({placeholders})')
            params.update({f"cd{i}": cd_cvm for i, cd_cvm in enumerate(normalized_cd_cvms)})

        sql = text(
            f"""
            SELECT
                c.cd_cvm,
                c.company_name,
                c.ticker_b3,
                {_CANONICAL_SECTOR_SQL} AS sector_name,
                fr."REPORT_YEAR",
                fr."CD_CONTA",
                SUM(fr."VL_CONTA") AS account_value
            FROM financial_reports fr
            JOIN companies c ON c.cd_cvm = fr."CD_CVM"
            WHERE {' AND '.join(where_parts)}
            GROUP BY
                c.cd_cvm,
                c.company_name,
                c.ticker_b3,
                {_CANONICAL_SECTOR_SQL},
                fr."REPORT_YEAR",
                fr."CD_CONTA"
            """
        )
        df = _pd().read_sql(sql, self.engine, params=params)
        if df.empty:
            return _pd().DataFrame(columns=result_columns)

        pivot = df.pivot_table(
            index=["cd_cvm", "company_name", "ticker_b3", "sector_name", "REPORT_YEAR"],
            columns="CD_CONTA",
            values="account_value",
            aggfunc="first",
        ).reset_index()
        pivot.columns.name = None
        pivot = pivot.rename(
            columns={
                "REPORT_YEAR": "report_year",
                "3.01": "receita",
                "3.05": "ebit",
                "3.11": "lucro_liq",
                "2.03": "pl",
            }
        )

        for column in ("receita", "ebit", "lucro_liq", "pl"):
            if column not in pivot.columns:
                pivot[column] = _pd().NA

        receita = _pd().to_numeric(pivot["receita"], errors="coerce")
        ebit = _pd().to_numeric(pivot["ebit"], errors="coerce")
        lucro_liq = _pd().to_numeric(pivot["lucro_liq"], errors="coerce")
        pl = _pd().to_numeric(pivot["pl"], errors="coerce")

        pivot["mg_ebit"] = ebit.divide(receita.where(receita != 0))
        pivot["mg_liq"] = lucro_liq.divide(receita.where(receita != 0))
        pivot["roe"] = lucro_liq.divide(pl.where(pl != 0))

        return pivot[result_columns].reset_index(drop=True)

    def _get_sector_metric_rows_from_kpi_mart(
        self,
        *,
        sector_name: str | None,
        years: list[int] | None,
        cd_cvms: list[int] | None,
        result_columns: list[str],
    ) -> _pd().DataFrame:
        where_parts = [
            "kam.period_label = CAST(kam.report_year AS TEXT)",
            "kam.cd_conta IN ('3.01', '3.05', '3.11', '2.03')",
        ]
        params: dict[str, object] = {}

        if sector_name:
            where_parts.append(f"{_CANONICAL_SECTOR_SQL} = :sector_name")
            params["sector_name"] = str(sector_name)

        normalized_years = sorted({int(year) for year in years or []})
        if normalized_years:
            placeholders = ", ".join(f":y{i}" for i in range(len(normalized_years)))
            where_parts.append(f"kam.report_year IN ({placeholders})")
            params.update({f"y{i}": year for i, year in enumerate(normalized_years)})

        normalized_cd_cvms = sorted({int(cd_cvm) for cd_cvm in cd_cvms or []})
        if cd_cvms is not None and not normalized_cd_cvms:
            return _pd().DataFrame(columns=result_columns)
        if normalized_cd_cvms:
            placeholders = ", ".join(f":cd{i}" for i in range(len(normalized_cd_cvms)))
            where_parts.append(f"kam.cd_cvm IN ({placeholders})")
            params.update({f"cd{i}": cd_cvm for i, cd_cvm in enumerate(normalized_cd_cvms)})

        sql = text(
            f"""
            SELECT
                c.cd_cvm,
                c.company_name,
                c.ticker_b3,
                {_CANONICAL_SECTOR_SQL} AS sector_name,
                kam.report_year,
                kam.cd_conta,
                SUM(kam.value) AS account_value
            FROM {KPI_ACCOUNT_MART_NAME} kam
            JOIN companies c ON c.cd_cvm = kam.cd_cvm
            WHERE {' AND '.join(where_parts)}
            GROUP BY
                c.cd_cvm,
                c.company_name,
                c.ticker_b3,
                {_CANONICAL_SECTOR_SQL},
                kam.report_year,
                kam.cd_conta
            """
        )
        df = _pd().read_sql(sql, self.engine, params=params)
        return self._sector_metric_rows_from_account_frame(df, result_columns)

    def _sector_metric_rows_from_account_frame(self, df, result_columns: list[str]):
        if df.empty:
            return _pd().DataFrame(columns=result_columns)

        pivot = df.pivot_table(
            index=["cd_cvm", "company_name", "ticker_b3", "sector_name", "report_year"],
            columns="cd_conta",
            values="account_value",
            aggfunc="first",
        ).reset_index()
        pivot.columns.name = None
        pivot = pivot.rename(
            columns={
                "3.01": "receita",
                "3.05": "ebit",
                "3.11": "lucro_liq",
                "2.03": "pl",
            }
        )

        for column in ("receita", "ebit", "lucro_liq", "pl"):
            if column not in pivot.columns:
                pivot[column] = _pd().NA

        receita = _pd().to_numeric(pivot["receita"], errors="coerce")
        ebit = _pd().to_numeric(pivot["ebit"], errors="coerce")
        lucro_liq = _pd().to_numeric(pivot["lucro_liq"], errors="coerce")
        pl = _pd().to_numeric(pivot["pl"], errors="coerce")

        pivot["mg_ebit"] = ebit.divide(receita.where(receita != 0))
        pivot["mg_liq"] = lucro_liq.divide(receita.where(receita != 0))
        pivot["roe"] = lucro_liq.divide(pl.where(pl != 0))

        return pivot[result_columns].reset_index(drop=True)

    def get_company_historical_indicator_metrics(self, cd_cvm: int) -> dict[int, dict[str, float | None]]:
        """Return annual ROE/EBIT margin/net margin metrics by year."""
        df = self.get_sector_metric_rows(cd_cvms=[int(cd_cvm)])
        metrics_by_year: dict[int, dict[str, float | None]] = {}
        if df.empty:
            return metrics_by_year

        for _, row in df.iterrows():
            year = int(row["report_year"])
            metrics_by_year[year] = {
                "roe": _optional_float(row.get("roe")),
                "mg_ebit": _optional_float(row.get("mg_ebit")),
                "mg_liq": _optional_float(row.get("mg_liq")),
            }
        return metrics_by_year

    @slow_query_warn(threshold_ms=200)
    def get_company_years_map(self, cd_cvms: list[int]) -> dict[int, tuple[int, ...]]:
        """Retorna mapa cd_cvm -> anos com dados anuais completos (DFP).

        Filtra por PERIOD_LABEL = REPORT_YEAR (ex: '2024') para excluir anos que
        possuam apenas dados trimestrais ITR, mantendo consistencia com
        get_available_years e garantindo que anos_disponiveis reflita apenas
        periodos computaveis pelo KPI engine.
        """
        if not cd_cvms:
            return {}

        unique_ids = tuple(sorted({int(cd_cvm) for cd_cvm in cd_cvms}))
        if self._is_financial_mart_ready(PERIOD_MART_NAME):
            placeholders = ", ".join(f":cd{i}" for i in range(len(unique_ids)))
            params = {f"cd{i}": cd_cvm for i, cd_cvm in enumerate(unique_ids)}
            sql = text(
                f"""
                SELECT DISTINCT cd_cvm, report_year
                FROM {PERIOD_MART_NAME}
                WHERE cd_cvm IN ({placeholders})
                  AND period_label = CAST(report_year AS TEXT)
                ORDER BY cd_cvm, report_year
                """
            )
            df = _pd().read_sql(sql, self.engine, params=params)
            years_map: dict[int, list[int]] = {int(cd_cvm): [] for cd_cvm in unique_ids}
            for _, row in df.iterrows():
                years_map.setdefault(int(row["cd_cvm"]), []).append(int(row["report_year"]))
            return {cd_cvm: tuple(years) for cd_cvm, years in years_map.items()}

        if not inspect(self.engine).has_table("financial_reports"):
            return {int(cd_cvm): () for cd_cvm in unique_ids}

        placeholders = ", ".join(f":cd{i}" for i in range(len(unique_ids)))
        params = {f"cd{i}": cd_cvm for i, cd_cvm in enumerate(unique_ids)}
        sql = text(
            f"""
            SELECT DISTINCT "CD_CVM", "REPORT_YEAR"
            FROM financial_reports
            WHERE "CD_CVM" IN ({placeholders})
              AND "PERIOD_LABEL" = CAST("REPORT_YEAR" AS TEXT)
            ORDER BY "CD_CVM", "REPORT_YEAR"
            """
        )
        df = _pd().read_sql(sql, self.engine, params=params)
        years_map: dict[int, list[int]] = {int(cd_cvm): [] for cd_cvm in unique_ids}
        for _, row in df.iterrows():
            years_map.setdefault(int(row["CD_CVM"]), []).append(int(row["REPORT_YEAR"]))
        return {cd_cvm: tuple(years) for cd_cvm, years in years_map.items()}

    @slow_query_warn(threshold_ms=200)
    def get_companies_by_cvm_ids(self, cvm_ids: list[int]) -> _pd().DataFrame:
        """Returns directory rows for a specific ordered set of cd_cvm values.

        Result rows are returned in database order; callers are responsible for
        re-applying the desired ordering (e.g. static market-cap rank).
        Returns an empty DataFrame when cvm_ids is empty.
        """
        if not cvm_ids:
            return _pd().DataFrame()
        unique_ids = [int(cd) for cd in cvm_ids]
        placeholders = ", ".join(f":id_{i}" for i in range(len(unique_ids)))
        params: dict[str, object] = {f"id_{i}": cd for i, cd in enumerate(unique_ids)}
        gics_sql = self._persisted_gics_select_sql()
        sql = text(
            f"""
            WITH selected_companies AS (
                SELECT
                    c.cd_cvm,
                    c.company_name,
                    COALESCE(c.ticker_b3, '') AS ticker_b3,
                    c.setor_analitico,
                    c.setor_cvm,
                    {_CANONICAL_SECTOR_SQL} AS sector_name,
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM financial_reports fr_exists
                            WHERE fr_exists."CD_CVM" = c.cd_cvm
                            LIMIT 1
                        ) THEN 1
                        ELSE 0
                    END AS has_financial_data,
                    c.coverage_rank{gics_sql}
                FROM companies c
                WHERE c.cd_cvm IN ({placeholders})
            ),
            selected_counts AS (
                SELECT fr."CD_CVM" AS cd_cvm, COUNT(*) AS total_rows
                FROM financial_reports fr
                WHERE fr."CD_CVM" IN ({placeholders})
                GROUP BY fr."CD_CVM"
            )
            SELECT
                selected_companies.*,
                COALESCE(selected_counts.total_rows, 0) AS total_rows
            FROM selected_companies
            LEFT JOIN selected_counts ON selected_counts.cd_cvm = selected_companies.cd_cvm
            """
        )
        return _pd().read_sql(sql, self.engine, params=params).reset_index(drop=True)

    @slow_query_warn(threshold_ms=200)
    def get_companies_by_cvm_ids_light(self, cvm_ids: list[int]) -> _pd().DataFrame:
        """Return company rows for specific CVM IDs without report row counts."""
        if not cvm_ids:
            return _pd().DataFrame()
        unique_ids = [int(cd) for cd in cvm_ids]
        placeholders = ", ".join(f":id_{i}" for i in range(len(unique_ids)))
        params: dict[str, object] = {f"id_{i}": cd for i, cd in enumerate(unique_ids)}
        gics_sql = self._persisted_gics_select_sql()
        sql = text(
            f"""
            SELECT
                c.cd_cvm,
                c.company_name,
                COALESCE(c.ticker_b3, '') AS ticker_b3,
                c.setor_analitico,
                c.setor_cvm,
                {_CANONICAL_SECTOR_SQL} AS sector_name,
                0 AS total_rows,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM financial_reports fr_exists
                        WHERE fr_exists."CD_CVM" = c.cd_cvm
                        LIMIT 1
                    ) THEN 1
                    ELSE 0
                END AS has_financial_data,
                c.coverage_rank{gics_sql}
            FROM companies c
            WHERE c.cd_cvm IN ({placeholders})
            """
        )
        return _pd().read_sql(sql, self.engine, params=params).reset_index(drop=True)

    @slow_query_warn(threshold_ms=200)
    def get_top_viewed_companies(self, limit: int = 10) -> _pd().DataFrame:
        """Returns top-N companies ordered by view_count DESC.

        Falls back to coverage_rank ASC when view_count values are equal (or when
        the company_views table is empty), matching the existing smart default.
        """
        sql = text(
            f"""
            SELECT
                c.cd_cvm,
                c.company_name,
                COALESCE(c.ticker_b3, '') AS ticker_b3,
                c.setor_analitico,
                c.setor_cvm,
                {_CANONICAL_SECTOR_SQL} AS sector_name,
                COALESCE(COUNT(fr."CD_CVM"), 0) AS total_rows,
                CASE WHEN COUNT(fr."CD_CVM") > 0 THEN 1 ELSE 0 END AS has_financial_data,
                c.coverage_rank,
                COALESCE(cv.view_count, 0) AS view_count
            FROM companies c
            LEFT JOIN financial_reports fr ON fr."CD_CVM" = c.cd_cvm
            LEFT JOIN company_views cv ON cv.cd_cvm = c.cd_cvm
            GROUP BY c.cd_cvm, c.company_name, c.ticker_b3,
                     c.setor_analitico, c.setor_cvm, c.coverage_rank, cv.view_count
            ORDER BY
                COALESCE(cv.view_count, 0) DESC,
                CASE WHEN c.coverage_rank IS NULL THEN 1 ELSE 0 END ASC,
                c.coverage_rank ASC
            LIMIT :limit
            """
        )
        return _pd().read_sql(sql, self.engine, params={"limit": int(limit)}).reset_index(drop=True)

    def _company_directory_filters(
        self,
        *,
        search: str,
        sector_name: str | None,
    ) -> tuple[str, dict]:
        where_parts = ["1 = 1"]
        params: dict[str, object] = {}

        normalized_search = search.strip().lower()
        if normalized_search:
            params["search"] = f"%{normalized_search}%"
            where_parts.append(
                """
                (
                    LOWER(c.company_name) LIKE :search
                    OR LOWER(COALESCE(c.ticker_b3, '')) LIKE :search
                    OR CAST(c.cd_cvm AS TEXT) LIKE :search
                )
                """
            )

        if sector_name:
            params["sector_name"] = str(sector_name)
            where_parts.append(f"{_CANONICAL_SECTOR_SQL} = :sector_name")

        return " AND ".join(where_parts), params

    def get_company_info(self, cd_cvm: int) -> dict:
        sql = text(
            f"""
            SELECT
                cd_cvm,
                company_name,
                nome_comercial,
                cnpj,
                setor_cvm,
                setor_analitico,
                {canonical_sector_sql(None)} AS sector_name,
                company_type,
                ticker_b3
            FROM companies
            WHERE cd_cvm = :cd_cvm
            LIMIT 1
            """
        )
        row = _pd().read_sql(sql, self.engine, params={"cd_cvm": int(cd_cvm)})
        if row.empty:
            return {}
        return row.iloc[0].to_dict()

    def get_company_info_with_read_model_state(self, cd_cvm: int) -> dict:
        if (
            self._is_financial_mart_ready(DIRECTORY_MART_NAME)
            and self._is_financial_mart_ready(PERIOD_MART_NAME)
        ):
            return self._get_company_info_with_read_model_state_from_marts(cd_cvm)

        inspector = inspect(self.engine)
        has_financial_reports = inspector.has_table("financial_reports")
        has_refresh_status = inspector.has_table("company_refresh_status")
        has_status_read_model = False
        if has_refresh_status:
            status_columns = {
                str(column.get("name") or "").lower()
                for column in inspector.get_columns("company_refresh_status")
            }
            has_status_read_model = "read_model_updated_at" in status_columns

        annual_join = ""
        readable_years_count = "0"
        latest_readable_year = "NULL"
        has_local_financial_reports_sql = "0"
        if has_financial_reports:
            has_local_financial_reports_sql = """CASE WHEN EXISTS (
                    SELECT 1 FROM financial_reports fr WHERE fr."CD_CVM" = c.cd_cvm LIMIT 1
                ) THEN 1 ELSE 0 END"""
            annual_join = """
            LEFT JOIN (
                SELECT
                    "CD_CVM" AS cd_cvm,
                    COUNT(DISTINCT "REPORT_YEAR") AS readable_years_count,
                    MAX("REPORT_YEAR") AS latest_readable_year
                FROM financial_reports
                WHERE "CD_CVM" = :cd_cvm
                  AND "PERIOD_LABEL" = CAST("REPORT_YEAR" AS TEXT)
                GROUP BY "CD_CVM"
            ) annual ON annual.cd_cvm = c.cd_cvm
            """
            readable_years_count = "COALESCE(annual.readable_years_count, 0)"
            latest_readable_year = "annual.latest_readable_year"

        status_join = ""
        read_model_updated_at = (
            f"CASE WHEN {latest_readable_year} IS NOT NULL THEN c.updated_at ELSE NULL END"
        )
        if has_status_read_model:
            status_join = """
            LEFT JOIN company_refresh_status crs ON crs.cd_cvm = c.cd_cvm
            """
            read_model_updated_at = (
                "COALESCE(crs.read_model_updated_at, "
                f"CASE WHEN {latest_readable_year} IS NOT NULL THEN c.updated_at ELSE NULL END)"
            )

        cols = self._company_column_names()
        is_active_sql = "1 AS is_active"
        if "is_active" in cols:
            is_active_sql = "COALESCE(c.is_active, 1) AS is_active"

        gics_parts: list[str] = []
        for col in (
            "gics_sector",
            "gics_sector_slug",
            "gics_industry_group",
            "gics_industry",
            "gics_sub_industry",
        ):
            if col in cols:
                gics_parts.append(f"c.{col}")
        gics_cols_sql = (",\n                " + ",\n                ".join(gics_parts)) if gics_parts else ""

        sql = text(
            f"""
            SELECT
                c.cd_cvm,
                c.company_name,
                c.nome_comercial,
                c.cnpj,
                c.setor_cvm,
                c.setor_analitico,
                {_CANONICAL_SECTOR_SQL} AS sector_name,
                c.company_type,
                c.ticker_b3,
                {is_active_sql},
                {has_local_financial_reports_sql} AS has_local_financial_reports,
                CASE WHEN {latest_readable_year} IS NOT NULL THEN 1 ELSE 0 END AS has_readable_current_data,
                {readable_years_count} AS readable_years_count,
                {latest_readable_year} AS latest_readable_year,
                {read_model_updated_at} AS read_model_updated_at{gics_cols_sql}
            FROM companies c
            {annual_join}
            {status_join}
            WHERE c.cd_cvm = :cd_cvm
            LIMIT 1
            """
        )
        row = _pd().read_sql(sql, self.engine, params={"cd_cvm": int(cd_cvm)})
        if row.empty:
            return {}
        payload = row.iloc[0].to_dict()
        payload.update(self.get_latest_financial_period(cd_cvm))
        return payload

    def _get_company_info_with_read_model_state_from_marts(self, cd_cvm: int) -> dict:
        inspector = inspect(self.engine)
        has_refresh_status = inspector.has_table("company_refresh_status")
        has_status_read_model = False
        if has_refresh_status:
            status_columns = {
                str(column.get("name") or "").lower()
                for column in inspector.get_columns("company_refresh_status")
            }
            has_status_read_model = "read_model_updated_at" in status_columns

        status_join = ""
        read_model_updated_at = (
            "CASE WHEN annual.latest_readable_year IS NOT NULL THEN c.updated_at ELSE NULL END"
        )
        if has_status_read_model:
            status_join = """
            LEFT JOIN company_refresh_status crs ON crs.cd_cvm = c.cd_cvm
            """
            read_model_updated_at = (
                "COALESCE(crs.read_model_updated_at, "
                "CASE WHEN annual.latest_readable_year IS NOT NULL THEN c.updated_at ELSE NULL END)"
            )

        cols = self._company_column_names()
        is_active_sql = "1 AS is_active"
        if "is_active" in cols:
            is_active_sql = "COALESCE(c.is_active, 1) AS is_active"

        gics_parts: list[str] = []
        for col in (
            "gics_sector",
            "gics_sector_slug",
            "gics_industry_group",
            "gics_industry",
            "gics_sub_industry",
        ):
            if col in cols:
                gics_parts.append(f"c.{col}")
        gics_cols_sql = (",\n                " + ",\n                ".join(gics_parts)) if gics_parts else ""

        sql = text(
            f"""
            SELECT
                c.cd_cvm,
                c.company_name,
                c.nome_comercial,
                c.cnpj,
                c.setor_cvm,
                c.setor_analitico,
                {_CANONICAL_SECTOR_SQL} AS sector_name,
                c.company_type,
                c.ticker_b3,
                {is_active_sql},
                COALESCE(dm.has_financial_data, 0) AS has_local_financial_reports,
                CASE WHEN annual.latest_readable_year IS NOT NULL THEN 1 ELSE 0 END AS has_readable_current_data,
                COALESCE(annual.readable_years_count, 0) AS readable_years_count,
                annual.latest_readable_year AS latest_readable_year,
                {read_model_updated_at} AS read_model_updated_at{gics_cols_sql}
            FROM companies c
            LEFT JOIN {DIRECTORY_MART_NAME} dm ON dm.cd_cvm = c.cd_cvm
            LEFT JOIN (
                SELECT
                    cd_cvm,
                    COUNT(DISTINCT report_year) AS readable_years_count,
                    MAX(report_year) AS latest_readable_year
                FROM {PERIOD_MART_NAME}
                WHERE cd_cvm = :cd_cvm
                  AND period_label = CAST(report_year AS TEXT)
                GROUP BY cd_cvm
            ) annual ON annual.cd_cvm = c.cd_cvm
            {status_join}
            WHERE c.cd_cvm = :cd_cvm
            LIMIT 1
            """
        )
        row = _pd().read_sql(sql, self.engine, params={"cd_cvm": int(cd_cvm)})
        if row.empty:
            return {}
        payload = row.iloc[0].to_dict()
        payload.update(self.get_latest_financial_period(cd_cvm))
        return payload

    def get_available_years(self, cd_cvm: int) -> list[int]:
        """Retorna os anos com dados anuais completos (DFP) para a empresa.

        Filtra por PERIOD_LABEL = REPORT_YEAR (ex: '2024') para excluir anos que
        possuam apenas dados trimestrais ITR (ex: '1Q24', '3Q25').  Isso garante
        que o endpoint /years retorne somente anos computaveis pelo KPI engine,
        que tambem filtra por periodo anual.  Sem esse filtro, companias com ITR
        mais recente do que o ultimo DFP publicado causariam referenceYear sem
        dados no Comparar, exibindo '-' em todas as celulas.
        """
        if self._is_financial_mart_ready(PERIOD_MART_NAME):
            sql = text(
                f"""
                SELECT DISTINCT report_year
                FROM {PERIOD_MART_NAME}
                WHERE cd_cvm = :cd_cvm
                  AND period_label = CAST(report_year AS TEXT)
                ORDER BY report_year
                """
            )
            df = _pd().read_sql(sql, self.engine, params={"cd_cvm": int(cd_cvm)})
            return [int(year) for year in df["report_year"].tolist()]

        sql = text(
            """
            SELECT DISTINCT "REPORT_YEAR"
            FROM financial_reports
            WHERE "CD_CVM" = :cd_cvm
              AND "PERIOD_LABEL" = CAST("REPORT_YEAR" AS TEXT)
            ORDER BY "REPORT_YEAR"
            """
        )
        df = _pd().read_sql(sql, self.engine, params={"cd_cvm": int(cd_cvm)})
        return [int(year) for year in df["REPORT_YEAR"].tolist()]

    def get_company_complete_periods(self, cd_cvm: int) -> list[dict]:
        """Return periods with the full core statement package available.

        A period is complete only when BPA, BPP, DRE, and DFC all have at
        least one non-conflict row for the same ``PERIOD_LABEL``. This keeps
        freshness labels and export scope from overstating partial ITR loads.
        """
        if not inspect(self.engine).has_table("financial_reports"):
            return []

        statement_placeholders = ", ".join(
            f":stmt{i}" for i, _ in enumerate(_REQUIRED_PERIOD_STATEMENTS)
        )
        params: dict[str, object] = {
            "cd_cvm": int(cd_cvm),
            "required_count": len(_REQUIRED_PERIOD_STATEMENTS),
        }
        params.update(
            {f"stmt{i}": stmt for i, stmt in enumerate(_REQUIRED_PERIOD_STATEMENTS)}
        )
        sql = text(
            f"""
            SELECT
                "REPORT_YEAR",
                "PERIOD_LABEL",
                COUNT(DISTINCT "STATEMENT_TYPE") AS statement_count
            FROM financial_reports
            WHERE "CD_CVM" = :cd_cvm
              AND "STATEMENT_TYPE" IN ({statement_placeholders})
              AND "PERIOD_LABEL" IS NOT NULL
              AND COALESCE("QA_CONFLICT", 0) = 0
            GROUP BY "REPORT_YEAR", "PERIOD_LABEL"
            HAVING COUNT(DISTINCT "STATEMENT_TYPE") = :required_count
            """
        )
        df = _pd().read_sql(sql, self.engine, params=params)
        if df.empty:
            return []

        periods: list[dict] = []
        for _, row in df.iterrows():
            period_label = str(row["PERIOD_LABEL"])
            parsed = _parse_period_label(period_label)
            if parsed is None:
                continue
            year, quarter = parsed
            periods.append(
                {
                    "report_year": int(row["REPORT_YEAR"]),
                    "period_label": period_label,
                    "period_display": _period_display_label(period_label),
                    "period_type": "annual" if quarter is None else "quarter",
                    "period_year": int(year),
                    "period_quarter": int(quarter) if quarter is not None else None,
                    "statement_count": int(row["statement_count"]),
                }
            )
        return sorted(periods, key=lambda item: _period_sort_key(item["period_label"]))

    def get_latest_financial_period(self, cd_cvm: int) -> dict:
        if self._is_financial_mart_ready(PERIOD_MART_NAME):
            complete_periods = self._get_company_complete_periods_from_mart(cd_cvm)
        else:
            complete_periods = self.get_company_complete_periods(cd_cvm)
        latest = complete_periods[-1] if complete_periods else {}
        return {
            "readable_financial_periods_count": len(complete_periods),
            "latest_financial_period_label": latest.get("period_label"),
            "latest_financial_period_display": latest.get("period_display"),
            "latest_financial_period_type": latest.get("period_type"),
            "latest_financial_period_year": latest.get("period_year"),
            "latest_financial_period_quarter": latest.get("period_quarter"),
        }

    def _get_company_complete_periods_from_mart(self, cd_cvm: int) -> list[dict]:
        sql = text(
            f"""
            SELECT report_year, period_label, period_type, quarter,
                   has_bpa + has_bpp + has_dre + has_dfc AS statement_count
            FROM {PERIOD_MART_NAME}
            WHERE cd_cvm = :cd_cvm
              AND is_complete_standard_period = 1
            """
        )
        df = _pd().read_sql(sql, self.engine, params={"cd_cvm": int(cd_cvm)})
        if df.empty:
            return []

        periods: list[dict] = []
        for _, row in df.iterrows():
            period_label = str(row["period_label"])
            parsed = _parse_period_label(period_label)
            if parsed is None:
                continue
            year, quarter = parsed
            periods.append(
                {
                    "report_year": int(row["report_year"]),
                    "period_label": period_label,
                    "period_display": _period_display_label(period_label),
                    "period_type": "annual" if quarter is None else "quarter",
                    "period_year": int(year),
                    "period_quarter": int(quarter) if quarter is not None else None,
                    "statement_count": int(row["statement_count"]),
                }
            )
        return sorted(periods, key=lambda item: _period_sort_key(item["period_label"]))

    def get_available_export_periods(self, cd_cvm: int) -> dict:
        """Returns exportable periods split into annual DFP years and ITR-only years.

        Annual years: years where a complete closing DFP package exists
        (BPA + BPP + DRE + DFC at PERIOD_LABEL = REPORT_YEAR).

        ITR-only years: years where complete quarterly periods exist and
        the year is strictly newer than the latest annual year (e.g. 2026 when
        1Q26 exists but the 2026 DFP has not been filed yet). Older years that
        have only ITR data are excluded — they are typically data-quality gaps,
        not genuine current-year ITR windows.

        When no annual years exist at all, every year with complete quarterly
        data is returned as an ITR-only year so companies without any DFP can
        still be exported.

        Returns
        -------
        dict with keys:
          annual_years      — sorted list[int]
          itr_only_years    — sorted list[int]
          all_export_years  — annual_years + itr_only_years, sorted
        """
        complete_periods = self.get_company_complete_periods(cd_cvm)
        if not complete_periods:
            return {"annual_years": [], "itr_only_years": [], "all_export_years": []}

        annual_years: list[int] = sorted(
            {
                int(period["period_year"])
                for period in complete_periods
                if period["period_type"] == "annual"
            }
        )
        quarter_years: list[int] = sorted(
            {
                int(period["period_year"])
                for period in complete_periods
                if period["period_type"] == "quarter"
            }
        )

        max_annual: int | None = max(annual_years, default=None)
        if max_annual is None:
            # No annual DFP exists — include every complete quarterly year.
            itr_only_years: list[int] = quarter_years
        else:
            itr_only_years = [year for year in quarter_years if year > max_annual]

        return {
            "annual_years": annual_years,
            "itr_only_years": itr_only_years,
            "all_export_years": sorted(set(annual_years) | set(itr_only_years)),
        }

    def get_available_statements(self, cd_cvm: int) -> list[str]:
        sql = text(
            """
            SELECT DISTINCT "STATEMENT_TYPE"
            FROM financial_reports
            WHERE "CD_CVM" = :cd_cvm
            ORDER BY "STATEMENT_TYPE"
            """
        )
        df = _pd().read_sql(sql, self.engine, params={"cd_cvm": int(cd_cvm)})
        return df["STATEMENT_TYPE"].tolist()

    @slow_query_warn(threshold_ms=200)
    def get_statement(
        self,
        cd_cvm: int,
        years: list[int],
        stmt_type: str,
        exclude_conflicts: bool = True,
    ) -> _pd().DataFrame:
        if not years:
            return _pd().DataFrame()

        years_int = [int(year) for year in years]
        placeholders = ", ".join(f":y{i}" for i in range(len(years_int)))
        params: dict = {f"y{i}": year for i, year in enumerate(years_int)}
        params["cd_cvm"] = int(cd_cvm)
        params["stmt"] = stmt_type

        conflict_clause = 'AND "QA_CONFLICT" = false' if exclude_conflicts else ""
        sql = text(
            f"""
            SELECT "CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE",
                   "PERIOD_LABEL", "VL_CONTA"
            FROM financial_reports
            WHERE "CD_CVM" = :cd_cvm
              AND "STATEMENT_TYPE" = :stmt
              AND "REPORT_YEAR" IN ({placeholders})
              {conflict_clause}
            """
        )

        df = _pd().read_sql(sql, self.engine, params=params)
        if df.empty:
            return df

        df["STANDARD_NAME"] = df["STANDARD_NAME"].fillna("")
        pivot = df.pivot_table(
            index=["CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"],
            columns="PERIOD_LABEL",
            values="VL_CONTA",
            aggfunc="first",
        ).reset_index()
        pivot.columns.name = None

        id_cols = ["CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"]
        period_cols = [column for column in pivot.columns if column not in id_cols]
        period_cols_sorted = sorted(period_cols, key=_period_sort_key)
        result = pivot[id_cols + period_cols_sorted]

        if period_cols_sorted:
            numeric_data = result[period_cols_sorted].fillna(0)
            all_zero_mask = (numeric_data == 0).all(axis=1)
            result = result[~all_zero_mask].reset_index(drop=True)

        return result

    @slow_query_warn(threshold_ms=200)
    def get_kpi_accounts(self, cd_cvm: int, years: list[int]) -> _pd().DataFrame:
        if not years:
            return _pd().DataFrame()

        years_int = [int(year) for year in years]
        if self._is_financial_mart_ready(KPI_ACCOUNT_MART_NAME):
            return self._get_kpi_accounts_from_mart(cd_cvm, years_int, annual_only=True)

        cd_contas = list(_KPI_ACCOUNTS.values())
        placeholders_y = ", ".join(f":y{i}" for i in range(len(years_int)))
        placeholders_c = ", ".join(f":c{i}" for i in range(len(cd_contas)))

        params: dict = {f"y{i}": year for i, year in enumerate(years_int)}
        params.update({f"c{i}": conta for i, conta in enumerate(cd_contas)})
        params["cd_cvm"] = int(cd_cvm)

        sql = text(
            f"""
            SELECT "REPORT_YEAR", "PERIOD_LABEL", "CD_CONTA", SUM("VL_CONTA") AS "VL_CONTA"
            FROM financial_reports
            WHERE "CD_CVM" = :cd_cvm
              AND "REPORT_YEAR" IN ({placeholders_y})
              AND "CD_CONTA" IN ({placeholders_c})
              AND "QA_CONFLICT" = false
            GROUP BY "REPORT_YEAR", "PERIOD_LABEL", "CD_CONTA"
            """
        )

        df = _pd().read_sql(sql, self.engine, params=params)
        if df.empty:
            return _pd().DataFrame()

        df = df[df["PERIOD_LABEL"] == df["REPORT_YEAR"].astype(str)].copy()
        pivot = df.pivot_table(
            index="REPORT_YEAR",
            columns="CD_CONTA",
            values="VL_CONTA",
            aggfunc="first",
        ).reset_index()
        pivot.columns.name = None

        inv_map = {value: key for key, value in _KPI_ACCOUNTS.items()}
        pivot = pivot.rename(columns=inv_map)
        return pivot.sort_values("REPORT_YEAR").reset_index(drop=True)

    def get_kpi_accounts_all_periods(self, cd_cvm: int, years: list[int]) -> _pd().DataFrame:
        if not years:
            return _pd().DataFrame()

        years_int = [int(year) for year in years]
        if self._is_financial_mart_ready(KPI_ACCOUNT_MART_NAME):
            return self._get_kpi_accounts_from_mart(cd_cvm, years_int, annual_only=False)

        cd_contas = list(_KPI_ACCOUNTS.values())
        placeholders_y = ", ".join(f":y{i}" for i in range(len(years_int)))
        placeholders_c = ", ".join(f":c{i}" for i in range(len(cd_contas)))

        params: dict = {f"y{i}": year for i, year in enumerate(years_int)}
        params.update({f"c{i}": conta for i, conta in enumerate(cd_contas)})
        params["cd_cvm"] = int(cd_cvm)

        sql = text(
            f"""
            SELECT "REPORT_YEAR", "PERIOD_LABEL", "CD_CONTA", SUM("VL_CONTA") AS "VL_CONTA"
            FROM financial_reports
            WHERE "CD_CVM" = :cd_cvm
              AND "REPORT_YEAR" IN ({placeholders_y})
              AND "CD_CONTA" IN ({placeholders_c})
              AND "QA_CONFLICT" = false
            GROUP BY "REPORT_YEAR", "PERIOD_LABEL", "CD_CONTA"
            """
        )

        df = _pd().read_sql(sql, self.engine, params=params)
        if df.empty:
            return _pd().DataFrame()

        pivot = df.pivot_table(
            index=["REPORT_YEAR", "PERIOD_LABEL"],
            columns="CD_CONTA",
            values="VL_CONTA",
            aggfunc="first",
        ).reset_index()
        pivot.columns.name = None

        inv_map = {value: key for key, value in _KPI_ACCOUNTS.items()}
        pivot = pivot.rename(columns=inv_map)
        pivot["_sort"] = pivot["PERIOD_LABEL"].apply(_period_sort_key)
        return pivot.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)

    def _get_kpi_accounts_from_mart(self, cd_cvm: int, years: list[int], *, annual_only: bool):
        if not years:
            return _pd().DataFrame()

        years_int = [int(year) for year in years]
        cd_contas = list(_KPI_ACCOUNTS.values())
        placeholders_y = ", ".join(f":y{i}" for i in range(len(years_int)))
        placeholders_c = ", ".join(f":c{i}" for i in range(len(cd_contas)))

        params: dict = {f"y{i}": year for i, year in enumerate(years_int)}
        params.update({f"c{i}": conta for i, conta in enumerate(cd_contas)})
        params["cd_cvm"] = int(cd_cvm)
        annual_clause = "AND period_label = CAST(report_year AS TEXT)" if annual_only else ""

        sql = text(
            f"""
            SELECT report_year AS "REPORT_YEAR",
                   period_label AS "PERIOD_LABEL",
                   cd_conta AS "CD_CONTA",
                   SUM(value) AS "VL_CONTA"
            FROM {KPI_ACCOUNT_MART_NAME}
            WHERE cd_cvm = :cd_cvm
              AND report_year IN ({placeholders_y})
              AND cd_conta IN ({placeholders_c})
              {annual_clause}
            GROUP BY report_year, period_label, cd_conta
            """
        )

        df = _pd().read_sql(sql, self.engine, params=params)
        if df.empty:
            return _pd().DataFrame()

        if annual_only:
            pivot = df.pivot_table(
                index="REPORT_YEAR",
                columns="CD_CONTA",
                values="VL_CONTA",
                aggfunc="first",
            ).reset_index()
        else:
            pivot = df.pivot_table(
                index=["REPORT_YEAR", "PERIOD_LABEL"],
                columns="CD_CONTA",
                values="VL_CONTA",
                aggfunc="first",
            ).reset_index()
        pivot.columns.name = None

        inv_map = {value: key for key, value in _KPI_ACCOUNTS.items()}
        pivot = pivot.rename(columns=inv_map)
        if annual_only:
            return pivot.sort_values("REPORT_YEAR").reset_index(drop=True)
        pivot["_sort"] = pivot["PERIOD_LABEL"].apply(_period_sort_key)
        return pivot.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)

    def get_da_all_periods(self, cd_cvm: int, years: list[int]) -> _pd().DataFrame:
        if not years:
            return _pd().DataFrame()

        years_int = [int(year) for year in years]
        placeholders = ", ".join(f":y{i}" for i in range(len(years_int)))
        params: dict = {f"y{i}": year for i, year in enumerate(years_int)}
        params["cd_cvm"] = int(cd_cvm)

        sql = text(
            f"""
            SELECT "REPORT_YEAR", "PERIOD_LABEL", SUM(ABS("VL_CONTA")) AS da_value
            FROM financial_reports
            WHERE "CD_CVM" = :cd_cvm
              AND "STATEMENT_TYPE" = 'DFC'
              AND "REPORT_YEAR" IN ({placeholders})
              AND "CD_CONTA" LIKE '6.01.01%'
              AND LOWER("DS_CONTA") LIKE '%depreci%'
              AND "QA_CONFLICT" = false
            GROUP BY "REPORT_YEAR", "PERIOD_LABEL"
            """
        )

        return _pd().read_sql(sql, self.engine, params=params)

    def get_da_from_dfc(self, cd_cvm: int, years: list[int]) -> _pd().Series:
        if not years:
            return _pd().Series(dtype=float)

        years_int = [int(year) for year in years]
        placeholders = ", ".join(f":y{i}" for i in range(len(years_int)))
        params: dict = {f"y{i}": year for i, year in enumerate(years_int)}
        params["cd_cvm"] = int(cd_cvm)

        sql = text(
            f"""
            SELECT "REPORT_YEAR", "PERIOD_LABEL", SUM(ABS("VL_CONTA")) AS da_value
            FROM financial_reports
            WHERE "CD_CVM" = :cd_cvm
              AND "STATEMENT_TYPE" = 'DFC'
              AND "REPORT_YEAR" IN ({placeholders})
              AND "CD_CONTA" LIKE '6.01.01%'
              AND LOWER("DS_CONTA") LIKE '%depreci%'
              AND "QA_CONFLICT" = false
            GROUP BY "REPORT_YEAR", "PERIOD_LABEL"
            """
        )

        df = _pd().read_sql(sql, self.engine, params=params)
        if df.empty:
            return _pd().Series(dtype=float)

        df = df[df["PERIOD_LABEL"] == df["REPORT_YEAR"].astype(str)]
        return df.set_index("REPORT_YEAR")["da_value"]
