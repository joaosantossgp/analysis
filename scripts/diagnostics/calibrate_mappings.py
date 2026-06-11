from __future__ import annotations

import logging
import sys
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.platform.settings import get_settings
from src.financials.read_service import CVMReadService
from src.financials.resolver import ModelResolver

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    settings = get_settings()
    db_path = settings.paths.db_path
    if not Path(db_path).exists():
        logger.error(f"Database does not exist at {db_path}. Please run standardizer/refresh first.")
        return

    svc = CVMReadService(settings=settings)

    # Fetch top 15 companies to calibrate
    logger.info("Fetching companies for mapping calibration...")
    from sqlalchemy import text
    with svc.engine.begin() as conn:
        companies = conn.execute(
            text("SELECT cd_cvm, company_name, ticker_b3 FROM companies LIMIT 15")
        ).mappings().all()

    if not companies:
        logger.warning("No companies with local financial reports found in database.")
        return

    logger.info(f"Calibrating mapping resolver across {len(companies)} companies...")

    total_resolutions = 0
    statuses_count = {
        "manually_confirmed": 0,
        "auto_accepted": 0,
        "suggested": 0,
        "ambiguous": 0,
        "conflict": 0,
        "unresolved": 0,
    }
    
    total_score = 0.0
    scored_resolutions_count = 0

    for comp in companies:
        cd_cvm = comp["cd_cvm"]
        ticker = comp["ticker_b3"] or str(cd_cvm)
        logger.info(f"Processing {comp['company_name']} ({ticker})...")
        
        try:
            workspace = svc.get_excel_mapping_workspace(cd_cvm, period_scope="last_5_years")
            resolutions = workspace.get("resolutions", [])
            
            for res in resolutions:
                total_resolutions += 1
                status = res.get("status", "unresolved")
                statuses_count[status] = statuses_count.get(status, 0) + 1
                
                score = res.get("score", 0.0)
                if score > 0:
                    total_score += score
                    scored_resolutions_count += 1
        except Exception as e:
            logger.error(f"Error processing {ticker}: {e}")

    logger.info("=== CALIBRATION RESULTS ===")
    logger.info(f"Total resolved target-period coordinates: {total_resolutions}")
    for status, count in statuses_count.items():
        pct = (count / total_resolutions * 100) if total_resolutions > 0 else 0
        logger.info(f"  - {status}: {count} ({pct:.1f}%)")
    
    avg_score = (total_score / scored_resolutions_count) if scored_resolutions_count > 0 else 0
    logger.info(f"Average candidate score (non-zero): {avg_score:.2f}")
    
    precision_metric = (statuses_count.get("auto_accepted", 0) + statuses_count.get("manually_confirmed", 0)) / (total_resolutions - statuses_count.get("unresolved", 0)) * 100 if (total_resolutions - statuses_count.get("unresolved", 0)) > 0 else 0
    logger.info(f"Auto-acceptance precision rate: {precision_metric:.2f}%")

if __name__ == "__main__":
    main()
