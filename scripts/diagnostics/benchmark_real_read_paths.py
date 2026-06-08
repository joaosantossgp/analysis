#!/usr/bin/env python3
"""Benchmark real local read paths used by the desktop app.

It does not modify the database.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from desktop.bridge import CVMBridge  # noqa: E402
from src.financials.read_service import CVMReadService  # noqa: E402


def _time_call(fn: Callable[[], Any], *, runs: int) -> dict[str, float]:
    timings: list[float] = []
    fn()
    for _ in range(max(1, int(runs))):
        start = time.perf_counter()
        fn()
        timings.append((time.perf_counter() - start) * 1000)
    return {
        "median_ms": round(statistics.median(timings), 2),
        "min_ms": round(min(timings), 2),
        "max_ms": round(max(timings), 2),
    }


def _default_health_years() -> tuple[int, int]:
    current_year = time.gmtime().tm_year
    return current_year - 2, current_year - 1


def collect_snapshot(*, runs: int) -> dict[str, Any]:
    service = CVMReadService()
    start_year, end_year = _default_health_years()

    cold_start = time.perf_counter()
    first_page = service.list_companies(page=1, page_size=20)
    cold_directory_ms = round((time.perf_counter() - cold_start) * 1000, 2)
    sample_cd_cvm = first_page.items[0].cd_cvm if first_page.items else 0
    sample_years = list(first_page.items[0].anos_disponiveis[-5:]) if first_page.items else []
    if not sample_years:
        sample_years = [end_year]

    bridge = CVMBridge()
    return {
        "dataset": {
            "db_path": str(service.settings.paths.db_path),
            "sample_cd_cvm": int(sample_cd_cvm),
            "sample_years": sample_years,
        },
        "read_service": {
            "list_companies_cold_ms": cold_directory_ms,
            "list_companies_warm": _time_call(
                lambda: service.list_companies(page=1, page_size=20),
                runs=runs,
            ),
            "search_petro_warm": _time_call(
                lambda: service.list_companies(search="PETRO", page=1, page_size=20),
                runs=runs,
            ),
            "company_filters_warm": _time_call(service.get_company_filters, runs=runs),
            "list_sectors_warm": _time_call(service.list_sectors, runs=runs),
            "health_snapshot_warm": _time_call(
                lambda: service.get_health_snapshot(start_year=start_year, end_year=end_year),
                runs=runs,
            ),
            "suggestions_warm": _time_call(
                lambda: service.suggest_companies("PETRO", 6),
                runs=runs,
            ),
        },
        "desktop_bridge": {
            "get_companies_warm": _time_call(
                lambda: bridge.get_companies({"page": 1, "page_size": 20}),
                runs=runs,
            ),
            "get_base_health_warm": _time_call(
                lambda: bridge.get_base_health(
                    {"start_year": start_year, "end_year": end_year}
                ),
                runs=runs,
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(collect_snapshot(runs=args.runs), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
