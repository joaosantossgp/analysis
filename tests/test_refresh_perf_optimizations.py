from __future__ import annotations

from pathlib import Path
import pandas as pd
from sqlalchemy import text

from src.financials.database import CVMDatabase
from src.financials.periodization import _parse_ymd_fast, build_statement


def test_parse_ymd_fast_handles_iso_timestamps_and_invalid_inputs() -> None:
    cache: dict[object, tuple[int, int, int] | None] = {}
    assert _parse_ymd_fast("2024-12-31", cache) == (2024, 12, 31)
    assert _parse_ymd_fast("2024-03-31 00:00:00", cache) == (2024, 3, 31)
    assert _parse_ymd_fast(pd.Timestamp("2023-06-30"), cache) == (2023, 6, 30)
    assert _parse_ymd_fast("not-a-date", cache) is None
    assert _parse_ymd_fast(None, cache) is None
    assert _parse_ymd_fast("2024-02-30", cache) is None
    # Cached hit returns identical value
    assert _parse_ymd_fast("2024-12-31", cache) == (2024, 12, 31)


def test_build_statement_preserves_standalone_quarters_and_lineage() -> None:
    frame = pd.DataFrame(
        [
            {
                "CD_CVM": 9512,
                "CD_CONTA": "3.01",
                "DS_CONTA": "Receita de Venda de Bens e/ou Serviços",
                "LINE_ID_BASE": "3.01",
                "VL_CONTA": 100.0,
                "RAW_VL_CONTA": "100.0",
                "DT_INI_EXERC": "2024-01-01",
                "DT_FIM_EXERC": "2024-03-31",
                "DT_REFER": "2024-03-31",
                "VERSAO": "1",
                "MOEDA": "REAL",
                "ESCALA_MOEDA": "MIL",
                "REPORT_TYPE": "consolidated",
                "GRUPO_DFP": "DF Consolidado - Demonstração do Resultado",
            },
            {
                "CD_CVM": 9512,
                "CD_CONTA": "3.01",
                "DS_CONTA": "Receita de Venda de Bens e/ou Serviços",
                "LINE_ID_BASE": "3.01",
                "VL_CONTA": 250.0,
                "RAW_VL_CONTA": "250.0",
                "DT_INI_EXERC": "2024-01-01",
                "DT_FIM_EXERC": "2024-06-30",
                "DT_REFER": "2024-06-30",
                "VERSAO": "1",
                "MOEDA": "REAL",
                "ESCALA_MOEDA": "MIL",
                "REPORT_TYPE": "consolidated",
                "GRUPO_DFP": "DF Consolidado - Demonstração do Resultado",
            },
        ]
    )

    result, events = build_statement(frame, "DRE", tolerance=0.01)
    assert len(result) == 1
    assert float(result.loc[0, "1Q24"]) == 100.0
    assert float(result.loc[0, "2Q24"]) == 150.0
    assert len(result.attrs["source_observations"]) == 2
    assert len(result.attrs["value_lineage"]) == 2
    assert events == []


def test_cvm_database_connect_pragmas_and_bulk_insert_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "perf_test.db"
    db = CVMDatabase(str(db_path))
    try:
        with db._engine.connect() as conn:
            busy = conn.execute(text("PRAGMA busy_timeout")).scalar()
            sync = conn.execute(text("PRAGMA synchronous")).scalar()
            temp_store = conn.execute(text("PRAGMA temp_store")).scalar()
            assert int(busy) >= 5000
            # synchronous=NORMAL is 1, synchronous=OFF is 0 (init_db_tables may share pooled conn)
            assert int(sync) in {0, 1}
            assert int(temp_store) == 2

        df = pd.DataFrame(
            [
                {
                    "COMPANY_NAME": "TEST CO",
                    "CD_CVM": 9512,
                    "COMPANY_TYPE": "comercial",
                    "STATEMENT_TYPE": "DRE",
                    "REPORT_YEAR": 2024,
                    "PERIOD_LABEL": "2024",
                    "LINE_ID_BASE": "3.01",
                    "CD_CONTA": "3.01",
                    "DS_CONTA": "Receita",
                    "STANDARD_NAME": "Receita Liquida",
                    "QA_CONFLICT": False,
                    "VL_CONTA": 1234.5,
                },
                {
                    "COMPANY_NAME": "TEST CO",
                    "CD_CVM": 9512,
                    "COMPANY_TYPE": "comercial",
                    "STATEMENT_TYPE": "DRE",
                    "REPORT_YEAR": 2024,
                    "PERIOD_LABEL": "1Q24",
                    "LINE_ID_BASE": "3.01",
                    "CD_CONTA": "3.01",
                    "DS_CONTA": "Receita",
                    "STANDARD_NAME": None,
                    "QA_CONFLICT": True,
                    "VL_CONTA": float("nan"),
                },
            ]
        )
        with db._engine.begin() as conn:
            db._to_sql_with_retry("financial_reports", df, conn)

        with db._engine.connect() as conn:
            rows = conn.execute(
                text(
                    'SELECT "PERIOD_LABEL", "VL_CONTA", "QA_CONFLICT", "STANDARD_NAME" '
                    'FROM financial_reports ORDER BY "PERIOD_LABEL"'
                )
            ).fetchall()
        assert rows == [
            ("1Q24", None, 1, None),
            ("2024", 1234.5, 0, "Receita Liquida"),
        ]
    finally:
        db._engine.dispose()
