from __future__ import annotations

import ast
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_src_has_no_desktop_imports() -> None:
    violations: list[str] = []
    for py_file in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "desktop" or alias.name.startswith("desktop."):
                        violations.append(f"{py_file.relative_to(ROOT)}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "desktop" or node.module.startswith("desktop."):
                    violations.append(f"{py_file.relative_to(ROOT)}:{node.lineno}: from {node.module}")
    assert not violations, "src/ must stay independent of desktop/:\n" + "\n".join(violations)


def test_build_local_data_coverage_report_classifies_rows_and_counts(tmp_path: Path) -> None:
    from src.financials.local_data_coverage import build_local_data_coverage_report

    db_path = tmp_path / "test.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            'CREATE TABLE "financial_reports" ("CD_CVM" INTEGER, "REPORT_YEAR" INTEGER, "PERIOD_LABEL" TEXT)'
        )
        conn.execute('CREATE TABLE "companies" (cd_cvm INTEGER, company_name TEXT, updated_at TEXT)')
        conn.execute(
            'CREATE TABLE "company_refresh_status" '
            "(cd_cvm INTEGER, last_status TEXT, last_attempt_at TEXT, last_success_at TEXT, "
            "last_error TEXT, ignored INTEGER, ignored_reason TEXT)"
        )
        # 1: failed
        conn.execute(
            'INSERT INTO "company_refresh_status" VALUES (1, "failed", "2026-01-01", NULL, "timeout", 0, NULL)'
        )
        # 2: complete (recent DFP + ITR + registry + ticker)
        conn.execute('INSERT INTO "companies" VALUES (2, "Company Two", "2026-01-01")')
        conn.execute('INSERT INTO "financial_reports" VALUES (2, 2025, "2025")')
        conn.execute('INSERT INTO "financial_reports" VALUES (2, 2025, "3T2025")')
        # 3: stale partial (old DFP only)
        conn.execute('INSERT INTO "companies" VALUES (3, "Company Three", "2026-01-01")')
        conn.execute('INSERT INTO "financial_reports" VALUES (3, 2021, "2021")')
        # 4: ignored
        conn.execute(
            'INSERT INTO "company_refresh_status" VALUES (4, "failed", "2026-01-01", NULL, "err", 1, "delisted")'
        )
        # 5: no_financial
        conn.execute('INSERT INTO "companies" VALUES (5, "Company Five", "2026-01-01")')

    universe = [
        {"cd_cvm": 1, "company_name": "One"},
        {"cd_cvm": 2, "company_name": "Two"},
        {"cd_cvm": 3, "company_name": "Three"},
        {"cd_cvm": 4, "company_name": "Four"},
        {"cd_cvm": 5, "company_name": "Five"},
    ]
    tickers = {2: "TWO3", 3: "THR3"}
    report = build_local_data_coverage_report(
        db_path=db_path,
        universe=universe,
        ticker_lookup=lambda cd: tickers.get(cd),
        now=datetime(2026, 11, 25, 12, 0, 0),
    )

    assert report["stale_cutoff_year"] == 2024
    assert report["summary"] == {
        "total": 5,
        "complete": 1,
        "partial": 1,
        "no_financial": 1,
        "failed": 1,
        "stale": 1,
        "unmapped": 0,
        "ignored": 1,
    }
    assert report["filter_counts"]["all"] == 3
    assert report["filter_counts"]["ignored"] == 1
    assert report["filter_counts"]["stale"] == 1
    assert [row["status"] for row in report["rows"]] == [
        "failed",
        "no_financial",
        "partial",
        "complete",
        "ignored",
    ]


def test_excel_exporter_supports_injected_app_version() -> None:
    from src.financials.excel_exporter import ExcelExporter, set_default_app_version

    set_default_app_version("0.30.0-test")
    exp_default = ExcelExporter({"cd_cvm": 1, "company_name": "Test"}, {}, pd.DataFrame())
    assert exp_default._app_version == "0.30.0-test"

    exp_override = ExcelExporter(
        {"cd_cvm": 1, "company_name": "Test"},
        {},
        pd.DataFrame(),
        app_version="0.99.0",
    )
    assert exp_override._app_version == "0.99.0"
