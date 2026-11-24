"""Rebuildable query marts for CVM financial read paths."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text

MART_BUILD_VERSION = "cvm_financial_marts_v1"
SOURCE_TABLE_NAME = "financial_reports"
DIRECTORY_MART_NAME = "company_financial_directory_mart"
PERIOD_MART_NAME = "company_financial_period_mart"
KPI_ACCOUNT_MART_NAME = "company_kpi_account_mart"

KPI_ACCOUNT_CODES = (
    "3.01",
    "3.03",
    "3.05",
    "3.11",
    "2.03",
    "1",
    "2",
    "2.01",
    "2.02",
    "1.01",
    "1.01.01",
    "6.01",
    "6.02",
    "6.03",
)

logger = logging.getLogger(__name__)


def ensure_financial_mart_tables_for_connection(conn) -> None:
    """Create additive CVM financial mart tables.

    These marts are rebuildable from financial_reports and should not be used
    as the audit source of truth.
    """
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS financial_mart_builds (
            mart_name TEXT PRIMARY KEY,
            build_version TEXT NOT NULL,
            rebuilt_at TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_row_count INTEGER,
            source_max_report_id INTEGER,
            source_min_year INTEGER,
            source_max_year INTEGER,
            row_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error_message TEXT,
            metadata_json TEXT
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_financial_period_mart (
            cd_cvm INTEGER NOT NULL,
            report_year INTEGER NOT NULL,
            period_label TEXT NOT NULL,
            period_type TEXT NOT NULL,
            quarter INTEGER,
            has_bpa INTEGER NOT NULL DEFAULT 0,
            has_bpp INTEGER NOT NULL DEFAULT 0,
            has_dre INTEGER NOT NULL DEFAULT 0,
            has_dfc INTEGER NOT NULL DEFAULT 0,
            is_complete_standard_period INTEGER NOT NULL DEFAULT 0,
            source_row_count INTEGER NOT NULL DEFAULT 0,
            first_source_report_id INTEGER,
            last_source_report_id INTEGER,
            rebuilt_at TEXT NOT NULL,
            build_version TEXT NOT NULL,
            PRIMARY KEY (cd_cvm, report_year, period_label)
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_financial_directory_mart (
            cd_cvm INTEGER PRIMARY KEY,
            company_name TEXT,
            ticker_b3 TEXT,
            gics_sector TEXT,
            company_type TEXT,
            has_financial_data INTEGER NOT NULL DEFAULT 0,
            financial_row_count INTEGER NOT NULL DEFAULT 0,
            first_year INTEGER,
            latest_year INTEGER,
            latest_period_label TEXT,
            latest_period_type TEXT,
            complete_period_count INTEGER NOT NULL DEFAULT 0,
            rebuilt_at TEXT NOT NULL,
            build_version TEXT NOT NULL
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_kpi_account_mart (
            cd_cvm INTEGER NOT NULL,
            report_year INTEGER NOT NULL,
            period_label TEXT NOT NULL,
            statement_type TEXT NOT NULL,
            cd_conta TEXT NOT NULL,
            value REAL,
            source_row_count INTEGER NOT NULL DEFAULT 0,
            first_source_report_id INTEGER,
            last_source_report_id INTEGER,
            rebuilt_at TEXT NOT NULL,
            build_version TEXT NOT NULL,
            PRIMARY KEY (cd_cvm, report_year, period_label, statement_type, cd_conta)
        )
    """))
    # #525: drop the legacy sector column from marts built by older versions.
    inspector = inspect(conn, raiseerr=False)
    directory_columns = {
        str(column.get("name") or "").lower()
        for column in (inspector.get_columns(DIRECTORY_MART_NAME) if inspector is not None else ())
    }
    if "setor_analitico" in directory_columns:
        conn.execute(text(f"ALTER TABLE {DIRECTORY_MART_NAME} DROP COLUMN setor_analitico"))
    for ddl in (
        "CREATE INDEX IF NOT EXISTS idx_cfpm_company_year ON company_financial_period_mart(cd_cvm, report_year)",
        "CREATE INDEX IF NOT EXISTS idx_cfpm_complete ON company_financial_period_mart(cd_cvm, is_complete_standard_period, report_year)",
        "CREATE INDEX IF NOT EXISTS idx_cfdm_latest ON company_financial_directory_mart(latest_year, latest_period_label)",
        "CREATE INDEX IF NOT EXISTS idx_ckam_company_year ON company_kpi_account_mart(cd_cvm, report_year)",
        "CREATE INDEX IF NOT EXISTS idx_ckam_account_period ON company_kpi_account_mart(cd_conta, period_label)",
    ):
        conn.execute(text(ddl))


def rebuild_financial_marts(
    conn,
    *,
    rebuild_directory: bool = True,
    rebuild_periods: bool = True,
    rebuild_kpi_accounts: bool = True,
) -> dict[str, Any]:
    """Rebuild selected CVM financial marts from local financial_reports.

    The caller owns the transaction. Rebuilds are full-table for this first
    phase because cvm_financials.db is small enough for predictable local
    maintenance and does not yet have import batch high-water metadata.
    """
    started = time.perf_counter()
    rebuilt_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result: dict[str, Any] = {
        "build_version": MART_BUILD_VERSION,
        "rebuilt_at": rebuilt_at,
        "directory_rows": None,
        "period_rows": None,
        "kpi_account_rows": None,
        "elapsed_ms": None,
    }

    ensure_financial_mart_tables_for_connection(conn)
    source_stats = _source_stats(conn)
    try:
        if rebuild_periods:
            result["period_rows"] = _rebuild_period_mart(conn, rebuilt_at)
            _record_mart_build(
                conn,
                mart_name=PERIOD_MART_NAME,
                rebuilt_at=rebuilt_at,
                row_count=int(result["period_rows"] or 0),
                source_stats=source_stats,
                status="success",
            )
        if rebuild_directory:
            result["directory_rows"] = _rebuild_directory_mart(conn, rebuilt_at)
            _record_mart_build(
                conn,
                mart_name=DIRECTORY_MART_NAME,
                rebuilt_at=rebuilt_at,
                row_count=int(result["directory_rows"] or 0),
                source_stats=source_stats,
                status="success",
            )
        if rebuild_kpi_accounts:
            result["kpi_account_rows"] = _rebuild_kpi_account_mart(conn, rebuilt_at)
            _record_mart_build(
                conn,
                mart_name=KPI_ACCOUNT_MART_NAME,
                rebuilt_at=rebuilt_at,
                row_count=int(result["kpi_account_rows"] or 0),
                source_stats=source_stats,
                status="success",
                metadata={"account_codes": KPI_ACCOUNT_CODES},
            )
    except Exception as exc:
        logger.exception("CVM financial mart rebuild failed")
        _record_mart_build(
            conn,
            mart_name="cvm_financial_marts",
            rebuilt_at=rebuilt_at,
            row_count=0,
            source_stats=source_stats,
            status="failed",
            error_message=str(exc),
        )
        raise
    finally:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)

    return result


def get_financial_mart_status(conn) -> dict[str, Any]:
    ensure_financial_mart_tables_for_connection(conn)
    rows = conn.execute(text("""
        SELECT mart_name, build_version, rebuilt_at, source_table,
               source_row_count, source_max_report_id, source_min_year,
               source_max_year, row_count, status, error_message, metadata_json
        FROM financial_mart_builds
        ORDER BY mart_name
    """)).mappings().all()
    return {str(row["mart_name"]): dict(row) for row in rows}


def _rebuild_period_mart(conn, rebuilt_at: str) -> int:
    conn.execute(text(f"DELETE FROM {PERIOD_MART_NAME}"))
    conn.execute(text(f"""
        INSERT INTO {PERIOD_MART_NAME} (
            cd_cvm, report_year, period_label, period_type, quarter,
            has_bpa, has_bpp, has_dre, has_dfc, is_complete_standard_period,
            source_row_count, first_source_report_id, last_source_report_id,
            rebuilt_at, build_version
        )
        SELECT
            "CD_CVM" AS cd_cvm,
            "REPORT_YEAR" AS report_year,
            "PERIOD_LABEL" AS period_label,
            CASE
                WHEN "PERIOD_LABEL" = CAST("REPORT_YEAR" AS TEXT) THEN 'annual'
                WHEN UPPER("PERIOD_LABEL") LIKE '1Q%' OR UPPER("PERIOD_LABEL") LIKE '1T%' THEN 'quarter'
                WHEN UPPER("PERIOD_LABEL") LIKE '2Q%' OR UPPER("PERIOD_LABEL") LIKE '2T%' THEN 'quarter'
                WHEN UPPER("PERIOD_LABEL") LIKE '3Q%' OR UPPER("PERIOD_LABEL") LIKE '3T%' THEN 'quarter'
                WHEN UPPER("PERIOD_LABEL") LIKE '4Q%' OR UPPER("PERIOD_LABEL") LIKE '4T%' THEN 'quarter'
                ELSE 'other'
            END AS period_type,
            CASE
                WHEN UPPER("PERIOD_LABEL") LIKE '1Q%' OR UPPER("PERIOD_LABEL") LIKE '1T%' THEN 1
                WHEN UPPER("PERIOD_LABEL") LIKE '2Q%' OR UPPER("PERIOD_LABEL") LIKE '2T%' THEN 2
                WHEN UPPER("PERIOD_LABEL") LIKE '3Q%' OR UPPER("PERIOD_LABEL") LIKE '3T%' THEN 3
                WHEN UPPER("PERIOD_LABEL") LIKE '4Q%' OR UPPER("PERIOD_LABEL") LIKE '4T%' THEN 4
                ELSE NULL
            END AS quarter,
            MAX(CASE WHEN "STATEMENT_TYPE" = 'BPA' THEN 1 ELSE 0 END) AS has_bpa,
            MAX(CASE WHEN "STATEMENT_TYPE" = 'BPP' THEN 1 ELSE 0 END) AS has_bpp,
            MAX(CASE WHEN "STATEMENT_TYPE" = 'DRE' THEN 1 ELSE 0 END) AS has_dre,
            MAX(CASE WHEN "STATEMENT_TYPE" = 'DFC' THEN 1 ELSE 0 END) AS has_dfc,
            CASE WHEN COUNT(DISTINCT CASE
                WHEN "STATEMENT_TYPE" IN ('BPA', 'BPP', 'DRE', 'DFC') THEN "STATEMENT_TYPE"
            END) = 4 THEN 1 ELSE 0 END AS is_complete_standard_period,
            COUNT(*) AS source_row_count,
            MIN(id) AS first_source_report_id,
            MAX(id) AS last_source_report_id,
            :rebuilt_at AS rebuilt_at,
            :build_version AS build_version
        FROM {SOURCE_TABLE_NAME}
        WHERE "CD_CVM" IS NOT NULL
          AND "REPORT_YEAR" IS NOT NULL
          AND "PERIOD_LABEL" IS NOT NULL
          AND ("QA_CONFLICT" = false OR "QA_CONFLICT" IS NULL)
        GROUP BY "CD_CVM", "REPORT_YEAR", "PERIOD_LABEL"
    """), {"rebuilt_at": rebuilt_at, "build_version": MART_BUILD_VERSION})
    return _table_count(conn, PERIOD_MART_NAME)


def _rebuild_directory_mart(conn, rebuilt_at: str) -> int:
    conn.execute(text(f"DELETE FROM {DIRECTORY_MART_NAME}"))
    conn.execute(text(f"""
        INSERT INTO {DIRECTORY_MART_NAME} (
            cd_cvm, company_name, ticker_b3, gics_sector,
            company_type, has_financial_data, financial_row_count, first_year,
            latest_year, latest_period_label, latest_period_type,
            complete_period_count, rebuilt_at, build_version
        )
        WITH fr_stats AS (
            SELECT
                "CD_CVM" AS cd_cvm,
                COUNT(*) AS financial_row_count,
                MIN("REPORT_YEAR") AS first_year,
                MAX("REPORT_YEAR") AS latest_year
            FROM {SOURCE_TABLE_NAME}
            WHERE "CD_CVM" IS NOT NULL
            GROUP BY "CD_CVM"
        ),
        complete_periods AS (
            SELECT
                cd_cvm,
                COUNT(*) AS complete_period_count,
                MAX(report_year * 10 + COALESCE(quarter, 9)) AS latest_sort_key
            FROM {PERIOD_MART_NAME}
            WHERE is_complete_standard_period = 1
            GROUP BY cd_cvm
        ),
        latest_period AS (
            SELECT p.cd_cvm, p.report_year, p.period_label, p.period_type
            FROM {PERIOD_MART_NAME} p
            JOIN complete_periods cp
              ON cp.cd_cvm = p.cd_cvm
             AND cp.latest_sort_key = p.report_year * 10 + COALESCE(p.quarter, 9)
            WHERE p.is_complete_standard_period = 1
        )
        SELECT
            c.cd_cvm,
            c.company_name,
            c.ticker_b3,
            c.gics_sector,
            c.company_type,
            CASE WHEN COALESCE(fr.financial_row_count, 0) > 0 THEN 1 ELSE 0 END AS has_financial_data,
            COALESCE(fr.financial_row_count, 0) AS financial_row_count,
            fr.first_year,
            lp.report_year AS latest_year,
            lp.period_label AS latest_period_label,
            lp.period_type AS latest_period_type,
            COALESCE(cp.complete_period_count, 0) AS complete_period_count,
            :rebuilt_at AS rebuilt_at,
            :build_version AS build_version
        FROM companies c
        LEFT JOIN fr_stats fr ON fr.cd_cvm = c.cd_cvm
        LEFT JOIN complete_periods cp ON cp.cd_cvm = c.cd_cvm
        LEFT JOIN latest_period lp ON lp.cd_cvm = c.cd_cvm
    """), {"rebuilt_at": rebuilt_at, "build_version": MART_BUILD_VERSION})
    return _table_count(conn, DIRECTORY_MART_NAME)


def _rebuild_kpi_account_mart(conn, rebuilt_at: str) -> int:
    conn.execute(text(f"DELETE FROM {KPI_ACCOUNT_MART_NAME}"))
    account_list = ", ".join(f"'{code}'" for code in KPI_ACCOUNT_CODES)
    conn.execute(text(f"""
        INSERT INTO {KPI_ACCOUNT_MART_NAME} (
            cd_cvm, report_year, period_label, statement_type, cd_conta,
            value, source_row_count, first_source_report_id, last_source_report_id,
            rebuilt_at, build_version
        )
        SELECT
            "CD_CVM" AS cd_cvm,
            "REPORT_YEAR" AS report_year,
            "PERIOD_LABEL" AS period_label,
            "STATEMENT_TYPE" AS statement_type,
            "CD_CONTA" AS cd_conta,
            SUM("VL_CONTA") AS value,
            COUNT(*) AS source_row_count,
            MIN(id) AS first_source_report_id,
            MAX(id) AS last_source_report_id,
            :rebuilt_at AS rebuilt_at,
            :build_version AS build_version
        FROM {SOURCE_TABLE_NAME}
        WHERE "CD_CVM" IS NOT NULL
          AND "REPORT_YEAR" IS NOT NULL
          AND "PERIOD_LABEL" IS NOT NULL
          AND "STATEMENT_TYPE" IS NOT NULL
          AND "CD_CONTA" IN ({account_list})
          AND ("QA_CONFLICT" = false OR "QA_CONFLICT" IS NULL)
        GROUP BY "CD_CVM", "REPORT_YEAR", "PERIOD_LABEL", "STATEMENT_TYPE", "CD_CONTA"
    """), {"rebuilt_at": rebuilt_at, "build_version": MART_BUILD_VERSION})
    return _table_count(conn, KPI_ACCOUNT_MART_NAME)


def _source_stats(conn) -> dict[str, Any]:
    row = conn.execute(text(f"""
        SELECT
            COUNT(*) AS source_row_count,
            MAX(id) AS source_max_report_id,
            MIN("REPORT_YEAR") AS source_min_year,
            MAX("REPORT_YEAR") AS source_max_year
        FROM {SOURCE_TABLE_NAME}
    """)).mappings().first()
    return dict(row or {})


def _table_count(conn, table_name: str) -> int:
    return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)


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
            INSERT INTO financial_mart_builds (
                mart_name, build_version, rebuilt_at, source_table,
                source_row_count, source_max_report_id, source_min_year,
                source_max_year, row_count, status, error_message, metadata_json
            )
            VALUES (
                :mart_name, :build_version, :rebuilt_at, :source_table,
                :source_row_count, :source_max_report_id, :source_min_year,
                :source_max_year, :row_count, :status, :error_message,
                :metadata_json
            )
            ON CONFLICT(mart_name) DO UPDATE SET
                build_version = excluded.build_version,
                rebuilt_at = excluded.rebuilt_at,
                source_table = excluded.source_table,
                source_row_count = excluded.source_row_count,
                source_max_report_id = excluded.source_max_report_id,
                source_min_year = excluded.source_min_year,
                source_max_year = excluded.source_max_year,
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
            "source_row_count": source_stats.get("source_row_count"),
            "source_max_report_id": source_stats.get("source_max_report_id"),
            "source_min_year": source_stats.get("source_min_year"),
            "source_max_year": source_stats.get("source_max_year"),
            "row_count": row_count,
            "status": status,
            "error_message": error_message,
            "metadata_json": json.dumps(metadata or {}, sort_keys=True),
        },
    )
