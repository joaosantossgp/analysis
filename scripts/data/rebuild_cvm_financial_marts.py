# -*- coding: utf-8 -*-
"""Rebuild CVM financial query marts from local SQLite facts.

Examples:
    python scripts/data/rebuild_cvm_financial_marts.py
    python scripts/data/rebuild_cvm_financial_marts.py --periods-only
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.financials.marts import rebuild_financial_marts
from src.platform.settings import build_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _prefer_documents_data_root() -> None:
    if os.environ.get("CVM_DATA_DIR"):
        return
    documents_root = Path.home() / "Documents" / "CVMAnalytics"
    if (documents_root / "db" / "cvm_financials.db").exists():
        os.environ["CVM_DATA_DIR"] = str(documents_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild local CVM financial query marts.")
    parser.add_argument(
        "--directory-only",
        action="store_true",
        help="Only rebuild the company financial directory mart.",
    )
    parser.add_argument(
        "--periods-only",
        action="store_true",
        help="Only rebuild the company financial period mart.",
    )
    parser.add_argument(
        "--kpi-accounts-only",
        action="store_true",
        help="Only rebuild the KPI account mart.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    only_flags = [args.directory_only, args.periods_only, args.kpi_accounts_only]
    if sum(1 for flag in only_flags if flag) > 1:
        raise SystemExit("--directory-only, --periods-only and --kpi-accounts-only are mutually exclusive")

    _prefer_documents_data_root()
    settings = build_settings(project_root=ROOT)
    engine = create_engine(settings.paths.sqlite_url)

    rebuild_directory = args.directory_only or not (args.periods_only or args.kpi_accounts_only)
    rebuild_periods = args.periods_only or not (args.directory_only or args.kpi_accounts_only)
    rebuild_kpi_accounts = args.kpi_accounts_only or not (args.directory_only or args.periods_only)

    log.info("CVM financial DB: %s", settings.paths.db_path)
    with engine.begin() as conn:
        result = rebuild_financial_marts(
            conn,
            rebuild_directory=rebuild_directory,
            rebuild_periods=rebuild_periods,
            rebuild_kpi_accounts=rebuild_kpi_accounts,
        )
    log.info("Rebuild complete: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
