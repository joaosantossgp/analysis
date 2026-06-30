"""Precomputes monthly and annual aggregate tables for the electricity distribution domain."""
from __future__ import annotations

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _table_has_rows(conn, table_name: str) -> bool:
    exists = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    ).fetchone()
    if not exists:
        return False
    return conn.execute(text(f"SELECT 1 FROM {table_name} LIMIT 1")).fetchone() is not None


def rebuild_distribution_mmgd_aggregates(conn) -> None:
    """Refresh only MMGD aggregate columns from the compact mart or legacy detail."""
    if _table_has_rows(conn, "distribution_mmgd_monthly_mart"):
        monthly_mmgd_query = """
            INSERT INTO distribution_monthly_aggregates (
                aggregate_id, distributor_id, reference_month, mmgd_projects_count, mmgd_capacity_kw
            )
            SELECT
                distributor_id || '_' || reference_month AS aggregate_id,
                distributor_id,
                reference_month,
                mmgd_projects_count,
                mmgd_capacity_kw
            FROM distribution_mmgd_monthly_mart
            WHERE 1 = 1
            ON CONFLICT(aggregate_id) DO UPDATE SET
                mmgd_projects_count = excluded.mmgd_projects_count,
                mmgd_capacity_kw = excluded.mmgd_capacity_kw,
                created_at = datetime('now')
        """
    else:
        monthly_mmgd_query = """
            INSERT INTO distribution_monthly_aggregates (
                aggregate_id, distributor_id, reference_month, mmgd_projects_count, mmgd_capacity_kw
            )
            SELECT
                p.distributor_id || '_' || s.reference_month AS aggregate_id,
                p.distributor_id,
                s.reference_month,
                COUNT(DISTINCT s.project_id) AS mmgd_projects_count,
                SUM(s.installed_capacity_kw) AS mmgd_capacity_kw
            FROM distribution_mmgd_project_snapshots s
            JOIN distribution_mmgd_projects p ON s.project_id = p.project_id
            GROUP BY p.distributor_id, s.reference_month
            ON CONFLICT(aggregate_id) DO UPDATE SET
                mmgd_projects_count = excluded.mmgd_projects_count,
                mmgd_capacity_kw = excluded.mmgd_capacity_kw,
                created_at = datetime('now')
        """
    conn.execute(text(monthly_mmgd_query))

    annual_mmgd_query = """
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, mmgd_projects_count, mmgd_capacity_kw
        )
        SELECT
            m.distributor_id || '_' || CAST(SUBSTR(m.reference_month, 1, 4) AS INTEGER) AS aggregate_id,
            m.distributor_id,
            CAST(SUBSTR(m.reference_month, 1, 4) AS INTEGER) AS reference_year,
            m.mmgd_projects_count,
            m.mmgd_capacity_kw
        FROM distribution_monthly_aggregates m
        JOIN (
            SELECT
                distributor_id,
                CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS ref_year,
                MAX(reference_month) AS max_month
            FROM distribution_monthly_aggregates
            WHERE mmgd_projects_count IS NOT NULL
            GROUP BY distributor_id, ref_year
        ) latest
          ON m.distributor_id = latest.distributor_id
         AND m.reference_month = latest.max_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            mmgd_projects_count = excluded.mmgd_projects_count,
            mmgd_capacity_kw = excluded.mmgd_capacity_kw,
            created_at = datetime('now')
    """
    conn.execute(text(annual_mmgd_query))


def rebuild_distribution_market_aggregates(conn) -> None:
    """Refresh market aggregate columns only."""
    conn.execute(text("""
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, billed_energy_mwh, revenue_brl
        )
        SELECT
            distributor_id || '_' || reference_month AS aggregate_id,
            distributor_id,
            reference_month,
            SUM(CASE WHEN metric_name = 'billed_energy' THEN normalized_value END) AS billed_energy_mwh,
            SUM(CASE WHEN metric_name = 'revenue' THEN normalized_value END) AS revenue_brl
        FROM distribution_market_facts
        GROUP BY distributor_id, reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            billed_energy_mwh = excluded.billed_energy_mwh,
            revenue_brl = excluded.revenue_brl,
            created_at = datetime('now')
    """))
    conn.execute(text("""
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, billed_energy_mwh, revenue_brl
        )
        SELECT
            distributor_id || '_' || CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS aggregate_id,
            distributor_id,
            CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS reference_year,
            SUM(CASE WHEN metric_name = 'billed_energy' THEN normalized_value END) AS billed_energy_mwh,
            SUM(CASE WHEN metric_name = 'revenue' THEN normalized_value END) AS revenue_brl
        FROM distribution_market_facts
        GROUP BY distributor_id, reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            billed_energy_mwh = excluded.billed_energy_mwh,
            revenue_brl = excluded.revenue_brl,
            created_at = datetime('now')
    """))


def rebuild_distribution_balance_aggregates(conn) -> None:
    """Refresh energy-balance aggregate columns only."""
    conn.execute(text("""
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, losses_mwh, injected_energy_mwh, measured_energy_mwh, losses_pct
        )
        SELECT
            distributor_id || '_' || reference_month AS aggregate_id,
            distributor_id,
            reference_month,
            SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) AS losses_mwh,
            SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) AS injected_energy_mwh,
            SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) -
            SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) AS measured_energy_mwh,
            CASE
                WHEN SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) > 0
                THEN SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) /
                     SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END)
                ELSE NULL
            END AS losses_pct
        FROM distribution_energy_balance_facts
        GROUP BY distributor_id, reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            losses_mwh = excluded.losses_mwh,
            injected_energy_mwh = excluded.injected_energy_mwh,
            measured_energy_mwh = excluded.measured_energy_mwh,
            losses_pct = excluded.losses_pct,
            created_at = datetime('now')
    """))
    conn.execute(text("""
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, losses_mwh, injected_energy_mwh, measured_energy_mwh, losses_pct
        )
        SELECT
            distributor_id || '_' || CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS aggregate_id,
            distributor_id,
            CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS reference_year,
            SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) AS losses_mwh,
            SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) AS injected_energy_mwh,
            SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) -
            SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) AS measured_energy_mwh,
            CASE
                WHEN SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) > 0
                THEN SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) /
                     SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END)
                ELSE NULL
            END AS losses_pct
        FROM distribution_energy_balance_facts
        GROUP BY distributor_id, reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            losses_mwh = excluded.losses_mwh,
            injected_energy_mwh = excluded.injected_energy_mwh,
            measured_energy_mwh = excluded.measured_energy_mwh,
            losses_pct = excluded.losses_pct,
            created_at = datetime('now')
    """))


def rebuild_distribution_continuity_aggregates(conn) -> None:
    """Refresh DEC/FEC aggregate columns only."""
    conn.execute(text("""
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, dec_actual, fec_actual, dec_limit, fec_limit
        )
        SELECT
            act.distributor_id || '_' || act.reference_month AS aggregate_id,
            act.distributor_id,
            act.reference_month,
            MAX(CASE WHEN act.indicator_code = 'DEC' THEN act.weighted_actual END) AS dec_actual,
            MAX(CASE WHEN act.indicator_code = 'FEC' THEN act.weighted_actual END) AS fec_actual,
            MAX(CASE WHEN lim.indicator_code = 'DEC' THEN lim.weighted_limit END) AS dec_limit,
            MAX(CASE WHEN lim.indicator_code = 'FEC' THEN lim.weighted_limit END) AS fec_limit
        FROM (
            SELECT
                f.distributor_id,
                f.reference_month,
                f.indicator_code,
                SUM(f.actual_value * w.actual_value) / SUM(w.actual_value) AS weighted_actual
            FROM distribution_continuity_facts f
            JOIN distribution_continuity_facts w
              ON f.distributor_id = w.distributor_id
             AND f.set_id = w.set_id
             AND f.reference_month = w.reference_month
             AND w.indicator_code = 'NumCon'
            WHERE f.indicator_code IN ('DEC', 'FEC')
              AND f.set_name NOT LIKE '%CONSOLIDADO%'
              AND w.actual_value > 0
            GROUP BY f.distributor_id, f.reference_month, f.indicator_code
        ) act
        LEFT JOIN (
            SELECT
                l.distributor_id,
                w.reference_month,
                l.indicator_code,
                SUM(l.limit_value * w.actual_value) / SUM(w.actual_value) AS weighted_limit
            FROM distribution_continuity_limits l
            JOIN distribution_continuity_facts w
              ON l.distributor_id = w.distributor_id
             AND l.set_id = w.set_id
             AND l.validity_year = CAST(SUBSTR(w.reference_month, 1, 4) AS INTEGER)
             AND w.indicator_code = 'NumCon'
            WHERE l.indicator_code IN ('DEC', 'FEC')
              AND l.set_name NOT LIKE '%CONSOLIDADO%'
              AND w.actual_value > 0
            GROUP BY l.distributor_id, w.reference_month, l.indicator_code
        ) lim
          ON act.distributor_id = lim.distributor_id
         AND act.reference_month = lim.reference_month
         AND act.indicator_code = lim.indicator_code
        GROUP BY act.distributor_id, act.reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            dec_actual = excluded.dec_actual,
            fec_actual = excluded.fec_actual,
            dec_limit = excluded.dec_limit,
            fec_limit = excluded.fec_limit,
            created_at = datetime('now')
    """))
    conn.execute(text("""
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, dec_actual, fec_actual, dec_limit, fec_limit
        )
        SELECT
            act.distributor_id || '_' || act.reference_year AS aggregate_id,
            act.distributor_id,
            act.reference_year,
            MAX(CASE WHEN act.indicator_code = 'DEC' THEN act.weighted_actual END) AS dec_actual,
            MAX(CASE WHEN act.indicator_code = 'FEC' THEN act.weighted_actual END) AS fec_actual,
            MAX(CASE WHEN lim.indicator_code = 'DEC' THEN lim.weighted_limit END) AS dec_limit,
            MAX(CASE WHEN lim.indicator_code = 'FEC' THEN lim.weighted_limit END) AS fec_limit
        FROM (
            SELECT
                f.distributor_id,
                CAST(SUBSTR(f.reference_month, 1, 4) AS INTEGER) AS reference_year,
                f.indicator_code,
                SUM(f.actual_value * w.actual_value) / SUM(w.actual_value) AS weighted_actual
            FROM distribution_continuity_facts f
            JOIN distribution_continuity_facts w
              ON f.distributor_id = w.distributor_id
             AND f.set_id = w.set_id
             AND f.reference_month = w.reference_month
             AND w.indicator_code = 'NumCon'
            WHERE f.indicator_code IN ('DEC', 'FEC')
              AND f.set_name NOT LIKE '%CONSOLIDADO%'
              AND w.actual_value > 0
            GROUP BY f.distributor_id, reference_year, f.indicator_code
        ) act
        LEFT JOIN (
            SELECT
                l.distributor_id,
                CAST(SUBSTR(w.reference_month, 1, 4) AS INTEGER) AS reference_year,
                l.indicator_code,
                SUM(l.limit_value * w.actual_value) / SUM(w.actual_value) AS weighted_limit
            FROM distribution_continuity_limits l
            JOIN distribution_continuity_facts w
              ON l.distributor_id = w.distributor_id
             AND l.set_id = w.set_id
             AND l.validity_year = CAST(SUBSTR(w.reference_month, 1, 4) AS INTEGER)
             AND w.indicator_code = 'NumCon'
            WHERE l.indicator_code IN ('DEC', 'FEC')
              AND l.set_name NOT LIKE '%CONSOLIDADO%'
              AND w.actual_value > 0
            GROUP BY l.distributor_id, reference_year, l.indicator_code
        ) lim
          ON act.distributor_id = lim.distributor_id
         AND act.reference_year = lim.reference_year
         AND act.indicator_code = lim.indicator_code
        GROUP BY act.distributor_id, act.reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            dec_actual = excluded.dec_actual,
            fec_actual = excluded.fec_actual,
            dec_limit = excluded.dec_limit,
            fec_limit = excluded.fec_limit,
            created_at = datetime('now')
    """))


def rebuild_distribution_compensation_aggregates(conn) -> None:
    """Refresh continuity compensation aggregate columns only."""
    conn.execute(text("""
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, compensation_count, compensation_value
        )
        SELECT
            distributor_id || '_' || reference_month AS aggregate_id,
            distributor_id,
            reference_month,
            SUM(compensation_count) AS compensation_count,
            SUM(compensation_value) AS compensation_value
        FROM distribution_continuity_compensations
        GROUP BY distributor_id, reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            compensation_count = excluded.compensation_count,
            compensation_value = excluded.compensation_value,
            created_at = datetime('now')
    """))
    conn.execute(text("""
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, compensation_count, compensation_value
        )
        SELECT
            distributor_id || '_' || CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS aggregate_id,
            distributor_id,
            CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS reference_year,
            SUM(compensation_count) AS compensation_count,
            SUM(compensation_value) AS compensation_value
        FROM distribution_continuity_compensations
        GROUP BY distributor_id, reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            compensation_count = excluded.compensation_count,
            compensation_value = excluded.compensation_value,
            created_at = datetime('now')
    """))


def rebuild_distribution_delinquency_aggregates(conn) -> None:
    """Refresh delinquency aggregate columns only."""
    conn.execute(text("""
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, delinquency_pct
        )
        SELECT
            distributor_id || '_' || reference_month AS aggregate_id,
            distributor_id,
            reference_month,
            MAX(CASE WHEN indicator_code = 'ITot1' THEN actual_value END) AS delinquency_pct
        FROM distribution_delinquency_facts
        GROUP BY distributor_id, reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            delinquency_pct = excluded.delinquency_pct,
            created_at = datetime('now')
    """))
    conn.execute(text("""
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, delinquency_pct
        )
        SELECT
            d.distributor_id || '_' || CAST(SUBSTR(d.reference_month, 1, 4) AS INTEGER) AS aggregate_id,
            d.distributor_id,
            CAST(SUBSTR(d.reference_month, 1, 4) AS INTEGER) AS reference_year,
            CASE
                WHEN SUM(m.revenue_brl) > 0
                THEN SUM(d.actual_value * m.revenue_brl) / SUM(m.revenue_brl)
                ELSE NULL
            END AS delinquency_pct
        FROM distribution_delinquency_facts d
        LEFT JOIN distribution_monthly_aggregates m
          ON d.distributor_id = m.distributor_id
         AND d.reference_month = m.reference_month
        WHERE d.indicator_code = 'ITot1'
          AND d.actual_value IS NOT NULL
        GROUP BY d.distributor_id, reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            delinquency_pct = excluded.delinquency_pct,
            created_at = datetime('now')
    """))


def rebuild_distribution_tariff_aggregates(conn) -> None:
    """No-op placeholder: tariffs are read as validity intervals, not aggregate columns."""
    return None


ALL_DISTRIBUTION_AGGREGATE_SLICES = (
    "balance",
    "market",
    "continuity",
    "compensation",
    "tariff",
    "delinquency",
    "mmgd",
)


_DISTRIBUTION_AGGREGATE_REBUILDERS = {
    "balance": rebuild_distribution_balance_aggregates,
    "market": rebuild_distribution_market_aggregates,
    "continuity": rebuild_distribution_continuity_aggregates,
    "compensation": rebuild_distribution_compensation_aggregates,
    "tariff": rebuild_distribution_tariff_aggregates,
    "delinquency": rebuild_distribution_delinquency_aggregates,
    "mmgd": rebuild_distribution_mmgd_aggregates,
}


def rebuild_distribution_aggregate_slices(conn, slices: list[str] | tuple[str, ...] | None = None) -> None:
    """Refresh only the requested distribution aggregate slices."""
    selected = tuple(slices or ALL_DISTRIBUTION_AGGREGATE_SLICES)
    unknown = [name for name in selected if name not in _DISTRIBUTION_AGGREGATE_REBUILDERS]
    if unknown:
        raise ValueError(f"Unknown distribution aggregate slice(s): {', '.join(sorted(unknown))}")
    for name in selected:
        logger.info("Rebuilding distribution aggregate slice: %s", name)
        _DISTRIBUTION_AGGREGATE_REBUILDERS[name](conn)


def rebuild_distribution_aggregates(conn) -> None:
    """Rebuild precomputed monthly and annual aggregates for distributors from facts tables."""
    logger.info("Rebuilding electricity distribution aggregates...")

    # 1. Update/insert monthly aggregates from market facts
    # We use SQLite ON CONFLICT DO UPDATE to merge fields slice-by-slice
    monthly_market_query = """
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, billed_energy_mwh, revenue_brl
        )
        SELECT
            distributor_id || '_' || reference_month AS aggregate_id,
            distributor_id,
            reference_month,
            SUM(CASE WHEN metric_name = 'billed_energy' THEN normalized_value END) AS billed_energy_mwh,
            SUM(CASE WHEN metric_name = 'revenue' THEN normalized_value END) AS revenue_brl
        FROM distribution_market_facts
        GROUP BY distributor_id, reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            billed_energy_mwh = excluded.billed_energy_mwh,
            revenue_brl = excluded.revenue_brl,
            created_at = datetime('now')
    """
    conn.execute(text(monthly_market_query))

    # 2. Update/insert annual aggregates from market facts
    annual_market_query = """
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, billed_energy_mwh, revenue_brl
        )
        SELECT
            distributor_id || '_' || CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS aggregate_id,
            distributor_id,
            CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS reference_year,
            SUM(CASE WHEN metric_name = 'billed_energy' THEN normalized_value END) AS billed_energy_mwh,
            SUM(CASE WHEN metric_name = 'revenue' THEN normalized_value END) AS revenue_brl
        FROM distribution_market_facts
        GROUP BY distributor_id, reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            billed_energy_mwh = excluded.billed_energy_mwh,
            revenue_brl = excluded.revenue_brl,
            created_at = datetime('now')
    """
    conn.execute(text(annual_market_query))

    # 3. Update/insert monthly aggregates from balance facts
    monthly_balance_query = """
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, losses_mwh, injected_energy_mwh, measured_energy_mwh, losses_pct
        )
        SELECT
            distributor_id || '_' || reference_month AS aggregate_id,
            distributor_id,
            reference_month,
            SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) AS losses_mwh,
            SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) AS injected_energy_mwh,
            SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) -
            SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) AS measured_energy_mwh,
            CASE 
                WHEN SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) > 0 
                THEN SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) / 
                     SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END)
                ELSE NULL
            END AS losses_pct
        FROM distribution_energy_balance_facts
        GROUP BY distributor_id, reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            losses_mwh = excluded.losses_mwh,
            injected_energy_mwh = excluded.injected_energy_mwh,
            measured_energy_mwh = excluded.measured_energy_mwh,
            losses_pct = excluded.losses_pct,
            created_at = datetime('now')
    """
    conn.execute(text(monthly_balance_query))

    # 4. Update/insert annual aggregates from balance facts
    annual_balance_query = """
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, losses_mwh, injected_energy_mwh, measured_energy_mwh, losses_pct
        )
        SELECT
            distributor_id || '_' || CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS aggregate_id,
            distributor_id,
            CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS reference_year,
            SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) AS losses_mwh,
            SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) AS injected_energy_mwh,
            SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) -
            SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) AS measured_energy_mwh,
            CASE 
                WHEN SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END) > 0 
                THEN SUM(CASE WHEN balance_modality LIKE '%medido%' AND balance_characteristic = 'Perdas Totais' THEN normalized_value END) / 
                     SUM(CASE WHEN balance_modality = 'Energia Injetada' AND balance_characteristic = 'Energia Injetada Total' THEN normalized_value END)
                ELSE NULL
            END AS losses_pct
        FROM distribution_energy_balance_facts
        GROUP BY distributor_id, reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            losses_mwh = excluded.losses_mwh,
            injected_energy_mwh = excluded.injected_energy_mwh,
            measured_energy_mwh = excluded.measured_energy_mwh,
            losses_pct = excluded.losses_pct,
            created_at = datetime('now')
    """
    conn.execute(text(annual_balance_query))

    # 5. Update/insert monthly aggregates for continuity quality (DEC/FEC) actuals & limits
    monthly_continuity_query = """
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, dec_actual, fec_actual, dec_limit, fec_limit
        )
        SELECT
            act.distributor_id || '_' || act.reference_month AS aggregate_id,
            act.distributor_id,
            act.reference_month,
            MAX(CASE WHEN act.indicator_code = 'DEC' THEN act.weighted_actual END) AS dec_actual,
            MAX(CASE WHEN act.indicator_code = 'FEC' THEN act.weighted_actual END) AS fec_actual,
            MAX(CASE WHEN lim.indicator_code = 'DEC' THEN lim.weighted_limit END) AS dec_limit,
            MAX(CASE WHEN lim.indicator_code = 'FEC' THEN lim.weighted_limit END) AS fec_limit
        FROM (
            SELECT
                f.distributor_id,
                f.reference_month,
                f.indicator_code,
                SUM(f.actual_value * w.actual_value) / SUM(w.actual_value) AS weighted_actual
            FROM distribution_continuity_facts f
            JOIN distribution_continuity_facts w
              ON f.distributor_id = w.distributor_id
             AND f.set_id = w.set_id
             AND f.reference_month = w.reference_month
             AND w.indicator_code = 'NumCon'
            WHERE f.indicator_code IN ('DEC', 'FEC')
              AND f.set_name NOT LIKE '%CONSOLIDADO%'
              AND w.actual_value > 0
            GROUP BY f.distributor_id, f.reference_month, f.indicator_code
        ) act
        LEFT JOIN (
            SELECT
                l.distributor_id,
                w.reference_month,
                l.indicator_code,
                SUM(l.limit_value * w.actual_value) / SUM(w.actual_value) AS weighted_limit
            FROM distribution_continuity_limits l
            JOIN distribution_continuity_facts w
              ON l.distributor_id = w.distributor_id
             AND l.set_id = w.set_id
             AND l.validity_year = CAST(SUBSTR(w.reference_month, 1, 4) AS INTEGER)
             AND w.indicator_code = 'NumCon'
            WHERE l.indicator_code IN ('DEC', 'FEC')
              AND l.set_name NOT LIKE '%CONSOLIDADO%'
              AND w.actual_value > 0
            GROUP BY l.distributor_id, w.reference_month, l.indicator_code
        ) lim
          ON act.distributor_id = lim.distributor_id
         AND act.reference_month = lim.reference_month
         AND act.indicator_code = lim.indicator_code
        GROUP BY act.distributor_id, act.reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            dec_actual = excluded.dec_actual,
            fec_actual = excluded.fec_actual,
            dec_limit = excluded.dec_limit,
            fec_limit = excluded.fec_limit,
            created_at = datetime('now')
    """
    conn.execute(text(monthly_continuity_query))

    # 6. Update/insert monthly aggregates for compensations
    monthly_compensation_query = """
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, compensation_count, compensation_value
        )
        SELECT
            distributor_id || '_' || reference_month AS aggregate_id,
            distributor_id,
            reference_month,
            SUM(compensation_count) AS compensation_count,
            SUM(compensation_value) AS compensation_value
        FROM distribution_continuity_compensations
        GROUP BY distributor_id, reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            compensation_count = excluded.compensation_count,
            compensation_value = excluded.compensation_value,
            created_at = datetime('now')
    """
    conn.execute(text(monthly_compensation_query))

    # 7. Update/insert annual aggregates for continuity quality (DEC/FEC) actuals & limits
    annual_continuity_query = """
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, dec_actual, fec_actual, dec_limit, fec_limit
        )
        SELECT
            act.distributor_id || '_' || act.reference_year AS aggregate_id,
            act.distributor_id,
            act.reference_year,
            MAX(CASE WHEN act.indicator_code = 'DEC' THEN act.weighted_actual END) AS dec_actual,
            MAX(CASE WHEN act.indicator_code = 'FEC' THEN act.weighted_actual END) AS fec_actual,
            MAX(CASE WHEN lim.indicator_code = 'DEC' THEN lim.weighted_limit END) AS dec_limit,
            MAX(CASE WHEN lim.indicator_code = 'FEC' THEN lim.weighted_limit END) AS fec_limit
        FROM (
            SELECT
                f.distributor_id,
                CAST(SUBSTR(f.reference_month, 1, 4) AS INTEGER) AS reference_year,
                f.indicator_code,
                SUM(f.actual_value * w.actual_value) / SUM(w.actual_value) AS weighted_actual
            FROM distribution_continuity_facts f
            JOIN distribution_continuity_facts w
              ON f.distributor_id = w.distributor_id
             AND f.set_id = w.set_id
             AND f.reference_month = w.reference_month
             AND w.indicator_code = 'NumCon'
            WHERE f.indicator_code IN ('DEC', 'FEC')
              AND f.set_name NOT LIKE '%CONSOLIDADO%'
              AND w.actual_value > 0
            GROUP BY f.distributor_id, reference_year, f.indicator_code
        ) act
        LEFT JOIN (
            SELECT
                l.distributor_id,
                CAST(SUBSTR(w.reference_month, 1, 4) AS INTEGER) AS reference_year,
                l.indicator_code,
                SUM(l.limit_value * w.actual_value) / SUM(w.actual_value) AS weighted_limit
            FROM distribution_continuity_limits l
            JOIN distribution_continuity_facts w
              ON l.distributor_id = w.distributor_id
             AND l.set_id = w.set_id
             AND l.validity_year = CAST(SUBSTR(w.reference_month, 1, 4) AS INTEGER)
             AND w.indicator_code = 'NumCon'
            WHERE l.indicator_code IN ('DEC', 'FEC')
              AND l.set_name NOT LIKE '%CONSOLIDADO%'
              AND w.actual_value > 0
            GROUP BY l.distributor_id, reference_year, l.indicator_code
        ) lim
          ON act.distributor_id = lim.distributor_id
         AND act.reference_year = lim.reference_year
         AND act.indicator_code = lim.indicator_code
        GROUP BY act.distributor_id, act.reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            dec_actual = excluded.dec_actual,
            fec_actual = excluded.fec_actual,
            dec_limit = excluded.dec_limit,
            fec_limit = excluded.fec_limit,
            created_at = datetime('now')
    """
    conn.execute(text(annual_continuity_query))

    # 8. Update/insert annual aggregates for compensations
    annual_compensation_query = """
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, compensation_count, compensation_value
        )
        SELECT
            distributor_id || '_' || CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS aggregate_id,
            distributor_id,
            CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS reference_year,
            SUM(compensation_count) AS compensation_count,
            SUM(compensation_value) AS compensation_value
        FROM distribution_continuity_compensations
        GROUP BY distributor_id, reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            compensation_count = excluded.compensation_count,
            compensation_value = excluded.compensation_value,
            created_at = datetime('now')
    """
    conn.execute(text(annual_compensation_query))

    # 9. Update/insert monthly aggregates for delinquency
    monthly_delinquency_query = """
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, delinquency_pct
        )
        SELECT
            distributor_id || '_' || reference_month AS aggregate_id,
            distributor_id,
            reference_month,
            MAX(CASE WHEN indicator_code = 'ITot1' THEN actual_value END) AS delinquency_pct
        FROM distribution_delinquency_facts
        GROUP BY distributor_id, reference_month
        ON CONFLICT(aggregate_id) DO UPDATE SET
            delinquency_pct = excluded.delinquency_pct,
            created_at = datetime('now')
    """
    conn.execute(text(monthly_delinquency_query))

    # 10. Update/insert annual aggregates for delinquency (weighted by monthly revenue)
    annual_delinquency_query = """
        INSERT INTO distribution_annual_aggregates (
            aggregate_id, distributor_id, reference_year, delinquency_pct
        )
        SELECT
            d.distributor_id || '_' || CAST(SUBSTR(d.reference_month, 1, 4) AS INTEGER) AS aggregate_id,
            d.distributor_id,
            CAST(SUBSTR(d.reference_month, 1, 4) AS INTEGER) AS reference_year,
            CASE 
                WHEN SUM(m.revenue_brl) > 0 
                THEN SUM(d.actual_value * m.revenue_brl) / SUM(m.revenue_brl)
                ELSE NULL
            END AS delinquency_pct
        FROM distribution_delinquency_facts d
        LEFT JOIN distribution_monthly_aggregates m
          ON d.distributor_id = m.distributor_id
         AND d.reference_month = m.reference_month
        WHERE d.indicator_code = 'ITot1'
          AND d.actual_value IS NOT NULL
        GROUP BY d.distributor_id, reference_year
        ON CONFLICT(aggregate_id) DO UPDATE SET
            delinquency_pct = excluded.delinquency_pct,
            created_at = datetime('now')
    """
    conn.execute(text(annual_delinquency_query))

    # 11-12. Update/insert monthly and annual aggregates for MMGD
    rebuild_distribution_mmgd_aggregates(conn)

    logger.info("Successfully rebuilt distribution aggregates.")
