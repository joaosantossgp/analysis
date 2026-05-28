# -*- coding: utf-8 -*-
"""
Backfill companies.gics_* from setor_analitico / setor_cvm using the same
build_gics_classification() logic as the read service.

Use when historical rows were inserted before GICS columns existed or when
heuristics were improved (e.g. English GICS labels).

Examples:
  python scripts/backfill_company_gics.py --dry-run
  python scripts/backfill_company_gics.py
  python scripts/backfill_company_gics.py --force   # recompute all rows (only writes when mapping resolves)
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.database import init_db_tables  # noqa: E402
from src.db import build_engine  # noqa: E402
from src.gics_manual_mapping import build_gics_classification  # noqa: E402
from src.sector_taxonomy import canonical_sector_name  # noqa: E402
from src.settings import build_settings  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _clean(val: object) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill companies.gics_* from CVM sector metadata.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts and sample changes without writing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Consider all companies; still only UPDATE when classification resolves (non-NULL).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max rows to process (after SELECT filter).",
    )
    args = parser.parse_args()

    settings = build_settings()
    engine = build_engine(settings)
    init_db_tables(engine)

    select_sql = """
        SELECT cd_cvm, setor_analitico, setor_cvm, gics_sector
        FROM companies
    """
    if not args.force:
        select_sql += """
        WHERE gics_sector IS NULL OR TRIM(gics_sector) = ''
        """
    select_sql += """
        ORDER BY cd_cvm
    """
    if args.limit is not None:
        select_sql += " LIMIT :limit"

    params: dict[str, object] = {}
    if args.limit is not None:
        params["limit"] = int(args.limit)

    update_sql = text(
        """
        UPDATE companies
        SET gics_sector = :gics_sector,
            gics_sector_slug = :gics_sector_slug,
            gics_industry_group = :gics_industry_group,
            gics_industry = :gics_industry,
            gics_sub_industry = :gics_sub_industry
        WHERE cd_cvm = :cd_cvm
        """
    )

    would_change = 0
    skipped_no_mapping = 0
    unchanged_same = 0
    sample: list[tuple[int, str | None, str | None]] = []
    pending: list[dict[str, object]] = []

    with engine.connect() as conn:
        rows = conn.execute(text(select_sql), params).mappings().all()

    for row in rows:
        cd_cvm = int(row["cd_cvm"])
        setor_analitico = _clean(row.get("setor_analitico"))
        setor_cvm = _clean(row.get("setor_cvm"))
        sector_name = canonical_sector_name(setor_analitico, setor_cvm)
        gics = build_gics_classification(
            sector_name=sector_name,
            setor_analitico=setor_analitico,
            setor_cvm=setor_cvm,
        )
        if gics is None:
            skipped_no_mapping += 1
            continue

        old_gics = _clean(row.get("gics_sector"))
        new_sector = gics.gics_sector
        if old_gics == new_sector and args.force:
            unchanged_same += 1
            continue

        would_change += 1
        if len(sample) < 12:
            sample.append((cd_cvm, old_gics, new_sector))

        if args.dry_run:
            continue

        pending.append(
            {
                "cd_cvm": cd_cvm,
                "gics_sector": gics.gics_sector,
                "gics_sector_slug": gics.gics_sector_slug,
                "gics_industry_group": gics.gics_industry_group,
                "gics_industry": gics.gics_industry,
                "gics_sub_industry": gics.gics_sub_industry,
            }
        )

    if pending and not args.dry_run:
        with engine.begin() as conn:
            for payload in pending:
                conn.execute(update_sql, payload)

    log.info(
        "Candidates scanned: %s | would apply / applied: %s | no heuristic mapping: %s | force-unchanged same: %s",
        len(rows),
        would_change,
        skipped_no_mapping,
        unchanged_same,
    )
    if sample:
        log.info("Sample (cd_cvm, old_gics_sector -> new):")
        for cd, old, new in sample:
            log.info("  %s | %r -> %r", cd, old, new)

    if args.dry_run and would_change:
        log.info("Dry-run: no rows updated. Run without --dry-run to apply.")


if __name__ == "__main__":
    main()
