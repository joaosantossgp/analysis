#!/usr/bin/env python3
"""Build a validated local hot/cold store for CCEE hourly plant generation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.diagnostics.phase5_hot_cold_hourly_prototype import build_hot_cold_prototype  # noqa: E402
from src.platform.settings import build_settings  # noqa: E402


def _default_output_dir() -> Path:
    settings = build_settings()
    return (
        Path(settings.paths.data_dir)
        / "analytics"
        / "energy"
        / "ccee_plant_generation_hourly"
    ).expanduser().resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the production-facing CCEE hourly hot/cold local store from "
            "a read-only energy_kpis.db source. The source database is not modified."
        )
    )
    parser.add_argument("--database", help="Source energy_kpis.db. Defaults to the configured Documents database.")
    parser.add_argument(
        "--output-dir",
        help="Store directory. Defaults to <data>/analytics/energy/ccee_plant_generation_hourly.",
    )
    parser.add_argument("--replace-output", action="store_true", help="Replace an existing store directory.")
    parser.add_argument("--hot-months", type=int, default=2, help="Latest months to copy into hot SQLite.")
    parser.add_argument(
        "--cold-month",
        action="append",
        default=[],
        help="Specific cold month to export, YYYY-MM. Can repeat. Defaults to all non-hot months.",
    )
    parser.add_argument(
        "--cold-month-limit",
        type=int,
        default=None,
        help="Oldest non-hot months to export when --cold-month is omitted. Defaults to all non-hot months; use 0 to skip cold export.",
    )
    parser.add_argument(
        "--full-months",
        action="store_true",
        help="Export full selected months and create a runtime-eligible manifest.",
    )
    parser.add_argument(
        "--sample-rows-per-month",
        type=int,
        default=100_000,
        help="Bounded rows per selected month when --full-months is not set.",
    )
    parser.add_argument("--chunk-size", type=int, default=50_000, help="Rows per SQLite fetch/write chunk.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else _default_output_dir()
    full_months = bool(args.full_months)
    manifest = build_hot_cold_prototype(
        database=Path(args.database).expanduser().resolve() if args.database else None,
        output_dir=output_dir,
        hot_months=max(0, int(args.hot_months or 0)),
        cold_months=args.cold_month or None,
        cold_month_limit=10_000 if args.cold_month_limit is None else max(0, int(args.cold_month_limit)),
        max_rows_per_month=int(args.sample_rows_per_month or 100_000),
        full_months=full_months,
        chunk_size=max(1, int(args.chunk_size or 50_000)),
        replace_output=bool(args.replace_output),
    )
    manifest["mode"] = "energy_hourly_hot_cold_store"
    manifest["runtime_eligible"] = bool(full_months and manifest.get("validation", {}).get("ok"))
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest.get("validation", {}).get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
