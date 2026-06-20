# -*- coding: utf-8 -*-
"""Rebuild Energy KPI query marts from local SQLite facts.

Examples:
    python scripts/data/rebuild_energy_marts.py --reference-month 2026-04
    python scripts/data/rebuild_energy_marts.py --all
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.energy_kpi.plant_marts import rebuild_plant_hourly_marts
from src.energy_kpi.schema import get_energy_kpi_engine
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
    if (documents_root / "db" / "energy_kpis.db").exists():
        os.environ["CVM_DATA_DIR"] = str(documents_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild local Energy KPI query marts.")
    parser.add_argument(
        "--reference-month",
        action="append",
        default=[],
        help="Scoped CCEE hourly month to rebuild, in YYYY-MM or YYYYMM format. Can repeat.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Rebuild all plant hourly marts. This scans the full hourly table and can be slow on large databases.",
    )
    parser.add_argument(
        "--daily-only",
        action="store_true",
        help="Only rebuild the daily generation mart.",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Only rebuild the latest hourly preview mart.",
    )
    parser.add_argument(
        "--source-submarket-only",
        action="store_true",
        help="Only rebuild the monthly source/submarket summary mart.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.all and args.reference_month:
        raise SystemExit("--all cannot be combined with --reference-month")
    if not args.all and not args.reference_month:
        raise SystemExit("Pass at least one --reference-month or use --all explicitly.")
    only_flags = [args.daily_only, args.preview_only, args.source_submarket_only]
    if sum(1 for flag in only_flags if flag) > 1:
        raise SystemExit("--daily-only, --preview-only and --source-submarket-only are mutually exclusive")

    _prefer_documents_data_root()
    settings = build_settings(project_root=ROOT)
    engine = get_energy_kpi_engine(settings)
    reference_months = None if args.all else args.reference_month
    rebuild_daily = args.daily_only or not (args.preview_only or args.source_submarket_only)
    rebuild_preview = args.preview_only or not (args.daily_only or args.source_submarket_only)
    rebuild_source_submarket = args.source_submarket_only or not (args.daily_only or args.preview_only)

    log.info("Energy DB: %s", settings.paths.energy_kpi_db_path)
    log.info("Rebuild scope: %s", "all months" if reference_months is None else ", ".join(reference_months))
    with engine.begin() as conn:
        result = rebuild_plant_hourly_marts(
            conn,
            reference_months=reference_months,
            rebuild_daily=rebuild_daily,
            rebuild_preview=rebuild_preview,
            rebuild_source_submarket=rebuild_source_submarket,
        )
    log.info("Rebuild complete: %s", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
