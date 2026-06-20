from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from src.financials.database import init_db_tables
from src.financials.marts import (
    DIRECTORY_MART_NAME,
    KPI_ACCOUNT_MART_NAME,
    PERIOD_MART_NAME,
    get_financial_mart_status,
    rebuild_financial_marts,
)
from src.financials.query_layer import CVMQueryLayer


def _seed_financial_db(tmp_path: Path):
    db_path = tmp_path / "cvm_financials.db"
    engine = create_engine(f"sqlite:///{db_path}")
    init_db_tables(engine)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO companies (
                cd_cvm, company_name, company_type, ticker_b3, is_active, updated_at
            )
            VALUES
                (9512, 'PETROBRAS', 'comercial', 'PETR4', 1, '2026-01-01'),
                (99999, 'NO_DATA', 'comercial', NULL, 1, '2026-01-01')
        """))
        rows = []
        line_map = {
            "BPA": ("1", "Ativo Total", "Ativo Total", 100.0),
            "BPP": ("2", "Passivo Total", "Passivo Total", 60.0),
            "DRE": ("3.01", "Receita", "Receita", 40.0),
            "DFC": ("6.01", "Fluxo de Caixa Operacional", "Fluxo de Caixa Operacional", 20.0),
        }
        for period, year, multiplier in (("2025", 2025, 1.0), ("1Q26", 2026, 0.25)):
            for stmt, (cd_conta, ds_conta, standard_name, value) in line_map.items():
                rows.append(
                    {
                        "company": "PETROBRAS",
                        "cd_cvm": 9512,
                        "stmt": stmt,
                        "year": year,
                        "period": period,
                        "line_id": f"{stmt}:{cd_conta}:{period}",
                        "cd_conta": cd_conta,
                        "ds_conta": ds_conta,
                        "standard_name": standard_name,
                        "qa_conflict": False,
                        "value": value * multiplier,
                    }
                )
            for cd_conta, standard_name, value in (
                ("3.05", "EBIT", 10.0),
                ("3.11", "Lucro_Liq", 8.0),
                ("2.03", "PL", 40.0),
            ):
                stmt = "BPP" if cd_conta == "2.03" else "DRE"
                rows.append(
                    {
                        "company": "PETROBRAS",
                        "cd_cvm": 9512,
                        "stmt": stmt,
                        "year": year,
                        "period": period,
                        "line_id": f"{stmt}:{cd_conta}:{period}",
                        "cd_conta": cd_conta,
                        "ds_conta": standard_name,
                        "standard_name": standard_name,
                        "qa_conflict": False,
                        "value": value * multiplier,
                    }
                )
        rows.append(
            {
                "company": "PETROBRAS",
                "cd_cvm": 9512,
                "stmt": "DRE",
                "year": 2026,
                "period": "2Q26",
                "line_id": "DRE:3.01:2Q26",
                "cd_conta": "3.01",
                "ds_conta": "Receita",
                "standard_name": "Receita",
                "qa_conflict": True,
                "value": 999.0,
            }
        )
        conn.execute(
            text("""
                INSERT INTO financial_reports (
                    "COMPANY_NAME", "CD_CVM", "COMPANY_TYPE", "STATEMENT_TYPE",
                    "REPORT_YEAR", "PERIOD_LABEL", "LINE_ID_BASE", "CD_CONTA",
                    "DS_CONTA", "STANDARD_NAME", "QA_CONFLICT", "VL_CONTA"
                )
                VALUES (
                    :company, :cd_cvm, 'comercial', :stmt, :year, :period,
                    :line_id, :cd_conta, :ds_conta, :standard_name,
                    :qa_conflict, :value
                )
            """),
            rows,
        )
    return engine


def test_financial_marts_rebuild_is_idempotent_and_preserves_source_rows(tmp_path):
    engine = _seed_financial_db(tmp_path)
    with engine.begin() as conn:
        source_count_before = conn.execute(text("SELECT COUNT(*) FROM financial_reports")).scalar()
        first = rebuild_financial_marts(conn)
        second = rebuild_financial_marts(conn)
        source_count_after = conn.execute(text("SELECT COUNT(*) FROM financial_reports")).scalar()

        assert source_count_before == source_count_after == 15
        assert first["period_rows"] == second["period_rows"] == 2
        assert first["directory_rows"] == second["directory_rows"] == 2
        assert first["kpi_account_rows"] == second["kpi_account_rows"] == 14

        status = get_financial_mart_status(conn)
        assert set(status) == {DIRECTORY_MART_NAME, PERIOD_MART_NAME, KPI_ACCOUNT_MART_NAME}
        assert status[PERIOD_MART_NAME]["source_row_count"] == 15
        assert status[PERIOD_MART_NAME]["status"] == "success"


def test_financial_period_and_directory_marts_capture_complete_latest_period(tmp_path):
    engine = _seed_financial_db(tmp_path)
    with engine.begin() as conn:
        rebuild_financial_marts(conn)
        periods = conn.execute(text("""
            SELECT report_year, period_label, period_type, quarter,
                   has_bpa, has_bpp, has_dre, has_dfc, is_complete_standard_period
            FROM company_financial_period_mart
            WHERE cd_cvm = 9512
            ORDER BY report_year, period_label
        """)).mappings().all()
        assert [dict(row) for row in periods] == [
            {
                "report_year": 2025,
                "period_label": "2025",
                "period_type": "annual",
                "quarter": None,
                "has_bpa": 1,
                "has_bpp": 1,
                "has_dre": 1,
                "has_dfc": 1,
                "is_complete_standard_period": 1,
            },
            {
                "report_year": 2026,
                "period_label": "1Q26",
                "period_type": "quarter",
                "quarter": 1,
                "has_bpa": 1,
                "has_bpp": 1,
                "has_dre": 1,
                "has_dfc": 1,
                "is_complete_standard_period": 1,
            },
        ]

        directory = conn.execute(text("""
            SELECT has_financial_data, financial_row_count, first_year,
                   latest_year, latest_period_label, latest_period_type,
                   complete_period_count
            FROM company_financial_directory_mart
            WHERE cd_cvm = 9512
        """)).mappings().one()
        assert dict(directory) == {
            "has_financial_data": 1,
            "financial_row_count": 15,
            "first_year": 2025,
            "latest_year": 2026,
            "latest_period_label": "1Q26",
            "latest_period_type": "quarter",
            "complete_period_count": 2,
        }


def test_query_layer_uses_financial_marts_without_changing_directory_or_info_shape(tmp_path):
    engine = _seed_financial_db(tmp_path)
    raw_query = CVMQueryLayer(engine=engine)
    raw_rows, raw_total = raw_query.get_companies_directory_page(page=1, page_size=25)
    raw_years = raw_query.get_available_years(9512)
    raw_years_map = raw_query.get_company_years_map([9512, 99999])
    raw_info = raw_query.get_company_info_with_read_model_state(9512)

    with engine.begin() as conn:
        rebuild_financial_marts(conn)

    mart_query = CVMQueryLayer(engine=engine)
    mart_rows, mart_total = mart_query.get_companies_directory_page(page=1, page_size=25)
    mart_years = mart_query.get_available_years(9512)
    mart_years_map = mart_query.get_company_years_map([9512, 99999])
    mart_info = mart_query.get_company_info_with_read_model_state(9512)

    assert mart_query._is_financial_mart_ready(DIRECTORY_MART_NAME)
    assert mart_query._is_financial_mart_ready(PERIOD_MART_NAME)
    assert mart_total == raw_total == 2
    assert mart_rows[["cd_cvm", "has_financial_data", "total_rows"]].to_dict("records") == raw_rows[
        ["cd_cvm", "has_financial_data", "total_rows"]
    ].to_dict("records")
    assert mart_years == raw_years == [2025]
    assert mart_years_map == raw_years_map == {9512: (2025,), 99999: ()}

    compared_keys = {
        "cd_cvm",
        "has_local_financial_reports",
        "has_readable_current_data",
        "readable_years_count",
        "latest_readable_year",
        "readable_financial_periods_count",
        "latest_financial_period_label",
        "latest_financial_period_type",
        "latest_financial_period_year",
        "latest_financial_period_quarter",
    }
    assert {key: mart_info[key] for key in compared_keys} == {
        key: raw_info[key] for key in compared_keys
    }


def test_query_layer_uses_kpi_account_mart_without_changing_metric_outputs(tmp_path):
    engine = _seed_financial_db(tmp_path)
    raw_query = CVMQueryLayer(engine=engine)
    raw_annual = raw_query.get_kpi_accounts(9512, [2025, 2026])
    raw_all_periods = raw_query.get_kpi_accounts_all_periods(9512, [2025, 2026])
    raw_sector = raw_query.get_sector_metric_rows(cd_cvms=[9512])
    raw_historical = raw_query.get_company_historical_indicator_metrics(9512)

    with engine.begin() as conn:
        rebuild_financial_marts(conn)

    mart_query = CVMQueryLayer(engine=engine)
    mart_annual = mart_query.get_kpi_accounts(9512, [2025, 2026])
    mart_all_periods = mart_query.get_kpi_accounts_all_periods(9512, [2025, 2026])
    mart_sector = mart_query.get_sector_metric_rows(cd_cvms=[9512])
    mart_historical = mart_query.get_company_historical_indicator_metrics(9512)

    assert mart_query._is_financial_mart_ready(KPI_ACCOUNT_MART_NAME)
    assert mart_annual.to_dict("records") == raw_annual.to_dict("records")
    assert mart_all_periods.to_dict("records") == raw_all_periods.to_dict("records")
    assert mart_sector.to_dict("records") == raw_sector.to_dict("records")
    assert mart_historical == raw_historical
