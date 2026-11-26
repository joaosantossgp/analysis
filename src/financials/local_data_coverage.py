from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from src.companies.identity import CompanyIdentityResolver


_STATUS_SORT_ORDER = {
    "failed": 0,
    "no_financial": 1,
    "partial": 2,
    "unmapped": 3,
    "complete": 4,
    "ignored": 6,
}


def build_local_data_coverage_report(
    *,
    db_path: Path,
    universe: list[dict[str, Any]],
    ticker_lookup: Callable[[int], str | None] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute the local data coverage/missing-data report for the active universe."""
    current_time = now or datetime.now()
    stale_cutoff_year = current_time.year - 2

    latest_dfp: dict[int, int] = {}
    latest_itr: dict[int, str] = {}
    company_rows: dict[int, dict[str, Any]] = {}
    refresh_rows: dict[int, dict[str, Any]] = {}

    if db_path.exists():
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            present = {row[0] for row in cur.fetchall()}

            if "financial_reports" in present:
                try:
                    cur.execute(
                        'SELECT "CD_CVM" AS cd_cvm, MAX("REPORT_YEAR") AS y '
                        'FROM "financial_reports" '
                        'WHERE "CD_CVM" IS NOT NULL '
                        '  AND "PERIOD_LABEL" = CAST("REPORT_YEAR" AS TEXT) '
                        'GROUP BY "CD_CVM"'
                    )
                    for row in cur.fetchall():
                        if row["cd_cvm"] is not None and row["y"] is not None:
                            latest_dfp[int(row["cd_cvm"])] = int(row["y"])
                except Exception:
                    pass
                try:
                    cur.execute(
                        'SELECT "CD_CVM" AS cd_cvm, MAX("PERIOD_LABEL") AS p '
                        'FROM "financial_reports" '
                        'WHERE "CD_CVM" IS NOT NULL '
                        '  AND "PERIOD_LABEL" IS NOT NULL '
                        '  AND "PERIOD_LABEL" <> CAST("REPORT_YEAR" AS TEXT) '
                        'GROUP BY "CD_CVM"'
                    )
                    for row in cur.fetchall():
                        if row["cd_cvm"] is not None and row["p"]:
                            latest_itr[int(row["cd_cvm"])] = str(row["p"])
                except Exception:
                    pass

            if "companies" in present:
                try:
                    cur.execute(
                        "SELECT cd_cvm, company_name, updated_at "
                        'FROM "companies" WHERE cd_cvm IS NOT NULL'
                    )
                    for row in cur.fetchall():
                        company_rows[int(row["cd_cvm"])] = dict(row)
                except Exception:
                    pass

            if "company_refresh_status" in present:
                crs_cols: set[str] = set()
                try:
                    cur.execute('PRAGMA table_info("company_refresh_status")')
                    crs_cols = {str(r[1]).lower() for r in cur.fetchall()}
                except Exception:
                    crs_cols = set()
                ignored_select = ", ignored" if "ignored" in crs_cols else ""
                ignored_reason_select = (
                    ", ignored_reason" if "ignored_reason" in crs_cols else ""
                )
                try:
                    cur.execute(
                        "SELECT cd_cvm, last_status, last_attempt_at, "
                        "last_success_at, last_error"
                        + ignored_select
                        + ignored_reason_select
                        + ' FROM "company_refresh_status" '
                        + "WHERE cd_cvm IS NOT NULL"
                    )
                    for row in cur.fetchall():
                        refresh_rows[int(row["cd_cvm"])] = dict(row)
                except Exception:
                    pass

    resolver = CompanyIdentityResolver() if ticker_lookup is None else None
    rows: list[dict[str, Any]] = []
    summary = {
        "total": 0,
        "complete": 0,
        "partial": 0,
        "no_financial": 0,
        "failed": 0,
        "stale": 0,
        "unmapped": 0,
        "ignored": 0,
    }
    filter_counts: dict[str, int] = {
        "all": 0,
        "no_dfp": 0,
        "no_itr": 0,
        "no_financial": 0,
        "stale": 0,
        "failed": 0,
        "ticker_unmapped": 0,
        "cvm_unmapped": 0,
        "no_registry": 0,
        "ignored": 0,
    }

    for item in universe:
        try:
            cd = int(item["cd_cvm"])
        except Exception:
            continue
        company_name = str(item.get("company_name") or f"CVM {cd}")
        if ticker_lookup is not None:
            ticker = ticker_lookup(cd)
        else:
            identity = resolver.resolve(cd) if resolver is not None else None
            ticker = identity.ticker_b3 if identity else None
        ticker_mapped = bool(ticker)
        cvm_valid = cd > 0
        has_registry = cd in company_rows
        if has_registry:
            reg = company_rows[cd]
            if reg.get("company_name"):
                company_name = str(reg["company_name"])
        dfp_year = latest_dfp.get(cd)
        itr_period = latest_itr.get(cd)
        has_dfp = dfp_year is not None
        has_itr = itr_period is not None
        refresh = refresh_rows.get(cd, {})
        last_status = str(refresh.get("last_status") or "").strip().lower()
        last_error = refresh.get("last_error") or None
        last_attempt_at = refresh.get("last_attempt_at") or None
        last_success_at = refresh.get("last_success_at") or None
        ignored = bool(int(refresh.get("ignored") or 0))
        ignored_reason = refresh.get("ignored_reason") or None
        update_failed = last_status in {"error", "failed", "dispatch_failed"}
        is_stale = has_dfp and int(dfp_year) < stale_cutoff_year

        if ignored:
            status = "ignored"
        elif update_failed:
            status = "failed"
        elif not has_dfp and not has_itr:
            status = "no_financial"
        elif not ticker_mapped or not has_registry:
            status = "unmapped"
        elif not has_dfp or not has_itr or is_stale:
            status = "partial"
        else:
            status = "complete"

        summary["total"] += 1
        summary[status] += 1
        if is_stale and not ignored:
            summary["stale"] += 1

        if not ignored and status != "complete":
            filter_counts["all"] += 1
        if not ignored and not has_dfp:
            filter_counts["no_dfp"] += 1
        if not ignored and not has_itr:
            filter_counts["no_itr"] += 1
        if not ignored and not has_dfp and not has_itr:
            filter_counts["no_financial"] += 1
        if not ignored and is_stale:
            filter_counts["stale"] += 1
        if not ignored and update_failed:
            filter_counts["failed"] += 1
        if not ignored and not ticker_mapped:
            filter_counts["ticker_unmapped"] += 1
        if not ignored and not cvm_valid:
            filter_counts["cvm_unmapped"] += 1
        if not ignored and not has_registry:
            filter_counts["no_registry"] += 1
        if ignored:
            filter_counts["ignored"] += 1

        rows.append(
            {
                "cd_cvm": cd,
                "company_name": company_name,
                "ticker": ticker,
                "ticker_mapped": ticker_mapped,
                "cvm_valid": cvm_valid,
                "has_registry": has_registry,
                "has_dfp": has_dfp,
                "has_itr": has_itr,
                "latest_dfp_year": dfp_year,
                "latest_itr_period": itr_period,
                "last_status": last_status or None,
                "last_attempt_at": last_attempt_at,
                "last_success_at": last_success_at,
                "last_error": last_error,
                "update_failed": update_failed,
                "is_stale": is_stale,
                "ignored": ignored,
                "ignored_reason": str(ignored_reason) if ignored_reason else None,
                "status": status,
            }
        )

    rows.sort(
        key=lambda r: (
            _STATUS_SORT_ORDER.get(str(r.get("status")), 5),
            str(r.get("company_name") or "").upper(),
        )
    )

    return {
        "generated_at": current_time.isoformat(timespec="seconds"),
        "stale_cutoff_year": int(stale_cutoff_year),
        "summary": summary,
        "filter_counts": filter_counts,
        "rows": rows,
    }
