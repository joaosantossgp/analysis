from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from sqlalchemy import text


def _write_csv(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_fuel_distribution_import_writes_raw_parquet_manifest_and_mart(tmp_path: Path, db_conn):
    from src.energy_kpi.fuel_distribution import (
        FuelDistributionSourceFile,
        persist_fuel_distribution_sources_to_managed_store,
    )

    source_path = _write_csv(
        tmp_path / "vendas-combustiveis.csv",
        "\ufeffANO;MÊS;GRANDE REGIÃO;UNIDADE DA FEDERAÇÃO;PRODUTO;VENDAS\n"
        "2026;JAN;REGIÃO SUDESTE;SÃO PAULO;GASOLINA C;1234,5\n"
        "2026;FEV;REGIÃO SUDESTE;SÃO PAULO;GASOLINA C;1500,0\n"
        "2025;JAN;REGIÃO SUL;PARANÁ;ÓLEO DIESEL;700,25\n",
    )

    result = persist_fuel_distribution_sources_to_managed_store(
        data_dir=tmp_path,
        conn=db_conn,
        sources=(
            FuelDistributionSourceFile(
                source_dataset_id="anp_fuel_sales_state_month",
                label="Vendas de derivados petroleo e etanol",
                official_url="https://example.test/anp/vendas.csv",
                path=source_path,
                grain="state-product-month",
                value_unit="m3",
                frequency="monthly",
            ),
        ),
        import_batch_id="fuel-batch-1",
        parser_version="test-parser",
    )

    assert result["row_count"] == 3
    assert result["raw_snapshots"][0]["bytes"] == source_path.stat().st_size

    raw_snapshot_path = Path(result["raw_snapshots"][0]["path"])
    assert raw_snapshot_path.exists()
    assert raw_snapshot_path.read_bytes() == source_path.read_bytes()

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["contract"]["dataset_id"] == "fuel_distribution_sector_intake"
    assert manifest["validation"] == {"ok": True, "row_count": 3}
    assert manifest["selection"]["source_datasets"] == ["anp_fuel_sales_state_month"]
    assert manifest["partitions"][0]["source_dataset_id"] == "anp_fuel_sales_state_month"
    assert manifest["partitions"][0]["year"] == 2025
    assert manifest["partitions"][1]["year"] == 2026

    stored = pl.concat([pl.read_parquet(partition["path"]) for partition in manifest["partitions"]])
    assert stored.select("reference_period").to_series().to_list() == ["2025-01", "2026-01", "2026-02"]
    assert stored.select("value").to_series().to_list() == [700.25, 1234.5, 1500.0]
    assert set(stored.columns) >= {
        "source_dataset_id",
        "source_url_or_path",
        "import_batch_id",
        "parser_version",
        "content_hash",
        "source_row_hash",
        "frequency",
        "unit",
    }

    mart_rows = db_conn.execute(
        text(
            """
            SELECT product, year, unit, total_value, source_row_count
            FROM fuel_distribution_product_year_mart
            ORDER BY product, year
            """
        )
    ).fetchall()
    assert mart_rows == [
        ("GASOLINA C", 2026, "m3", 2734.5, 2),
        ("ÓLEO DIESEL", 2025, "m3", 700.25, 1),
    ]
    state_month_rows = db_conn.execute(
        text(
            """
            SELECT product, reference_period, state, unit, total_value, source_row_count
            FROM fuel_distribution_state_month_mart
            ORDER BY product, reference_period
            """
        )
    ).fetchall()
    assert state_month_rows == [
        ("GASOLINA C", "2026-01", "SÃO PAULO", "m3", 1234.5, 1),
        ("GASOLINA C", "2026-02", "SÃO PAULO", "m3", 1500.0, 1),
        ("ÓLEO DIESEL", "2025-01", "PARANÁ", "m3", 700.25, 1),
    ]

    catalog = db_conn.execute(
        text(
            """
            SELECT dataset_id, row_count, partition_count
            FROM managed_dataset_catalog
            WHERE dataset_id = 'fuel_distribution_sector_intake'
            """
        )
    ).fetchone()
    assert catalog is not None
    assert catalog.row_count == 3
    assert catalog.partition_count == 2


def test_fuel_distribution_summary_reads_use_sqlite_marts(tmp_path: Path, db_conn):
    from src.energy_kpi.fuel_distribution import (
        FuelDistributionSourceFile,
        get_fuel_distribution_product_year_summary,
        get_fuel_distribution_state_month_series,
        persist_fuel_distribution_sources_to_managed_store,
    )

    source_path = _write_csv(
        tmp_path / "vendas-combustiveis.csv",
        "\ufeffANO;MÊS;GRANDE REGIÃO;UNIDADE DA FEDERAÇÃO;PRODUTO;VENDAS\n"
        "2026;JAN;REGIÃO SUDESTE;SÃO PAULO;GASOLINA C;100,0\n"
        "2026;FEV;REGIÃO SUDESTE;SÃO PAULO;GASOLINA C;200,0\n"
        "2026;JAN;REGIÃO SUL;PARANÁ;GASOLINA C;50,0\n"
        "2025;JAN;REGIÃO SUL;PARANÁ;ÓLEO DIESEL;70,0\n",
    )
    persist_fuel_distribution_sources_to_managed_store(
        data_dir=tmp_path,
        conn=db_conn,
        sources=(
            FuelDistributionSourceFile(
                source_dataset_id="anp_fuel_sales_state_month",
                label="Vendas de derivados petroleo e etanol",
                official_url="https://example.test/anp/vendas.csv",
                path=source_path,
                grain="state-product-month",
                value_unit="m3",
                frequency="monthly",
            ),
        ),
        import_batch_id="fuel-batch-summary",
        parser_version="test-parser",
    )

    summary = get_fuel_distribution_product_year_summary(
        db_conn,
        product="GASOLINA C",
        start_year=2026,
        end_year=2026,
    )
    assert summary["source"] == "sqlite_mart"
    assert summary["count"] == 1
    assert summary["items"] == [
        {
            "source_dataset_id": "anp_fuel_sales_state_month",
            "product": "GASOLINA C",
            "year": 2026,
            "unit": "m3",
            "total_value": 350.0,
            "source_row_count": 3,
        }
    ]

    series = get_fuel_distribution_state_month_series(
        db_conn,
        source_dataset_id="anp_fuel_sales_state_month",
        product="GASOLINA C",
        state="SÃO PAULO",
        start_period="2026-01",
        end_period="2026-12",
    )
    assert series["source"] == "sqlite_mart"
    assert series["count"] == 2
    assert series["items"] == [
        {
            "source_dataset_id": "anp_fuel_sales_state_month",
            "product": "GASOLINA C",
            "reference_period": "2026-01",
            "year": 2026,
            "month": 1,
            "region": "REGIÃO SUDESTE",
            "state": "SÃO PAULO",
            "unit": "m3",
            "total_value": 100.0,
            "source_row_count": 1,
        },
        {
            "source_dataset_id": "anp_fuel_sales_state_month",
            "product": "GASOLINA C",
            "reference_period": "2026-02",
            "year": 2026,
            "month": 2,
            "region": "REGIÃO SUDESTE",
            "state": "SÃO PAULO",
            "unit": "m3",
            "total_value": 200.0,
            "source_row_count": 1,
        },
    ]


def test_energy_read_service_exposes_fuel_distribution_marts(tmp_path: Path, db_conn):
    from src.energy_kpi.fuel_distribution import (
        FuelDistributionSourceFile,
        persist_fuel_distribution_sources_to_managed_store,
    )
    from src.energy_kpi.read import EnergyKPIReadService

    source_path = _write_csv(
        tmp_path / "vendas-combustiveis.csv",
        "\ufeffANO;MÊS;GRANDE REGIÃO;UNIDADE DA FEDERAÇÃO;PRODUTO;VENDAS\n"
        "2026;JAN;REGIÃO SUDESTE;SÃO PAULO;GASOLINA C;100,0\n",
    )
    persist_fuel_distribution_sources_to_managed_store(
        data_dir=tmp_path,
        conn=db_conn,
        sources=(
            FuelDistributionSourceFile(
                source_dataset_id="anp_fuel_sales_state_month",
                label="Vendas de derivados petroleo e etanol",
                official_url="https://example.test/anp/vendas.csv",
                path=source_path,
                grain="state-product-month",
                value_unit="m3",
                frequency="monthly",
            ),
        ),
        import_batch_id="fuel-batch-service",
        parser_version="test-parser",
    )

    class MockConnContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, exc_type, exc_val, exc_tb):
            return None

    mock_engine = MagicMock()
    mock_engine.connect.side_effect = lambda: MockConnContext(db_conn)
    settings = MagicMock()
    settings.paths.data_dir = tmp_path
    svc = EnergyKPIReadService(settings)
    svc._engine = MagicMock(return_value=mock_engine)

    summary = svc.get_fuel_distribution_product_year_summary(product="GASOLINA C")
    assert summary["items"][0]["total_value"] == 100.0

    series = svc.get_fuel_distribution_state_month_series(
        source_dataset_id="anp_fuel_sales_state_month",
        product="GASOLINA C",
        state="SÃO PAULO",
    )
    assert series["items"][0]["reference_period"] == "2026-01"


def test_energy_bridge_exposes_fuel_distribution_read_contracts():
    from desktop.bridge import CVMBridge

    class MockBridge(CVMBridge):
        def __init__(self):
            self._energy_read_service = MagicMock()
            self._energy_read_service.get_fuel_distribution_product_year_summary.return_value = {
                "source": "sqlite_mart",
                "items": [{"product": "GASOLINA C"}],
                "count": 1,
            }
            self._energy_read_service.get_fuel_distribution_state_month_series.return_value = {
                "source": "sqlite_mart",
                "items": [{"reference_period": "2026-01"}],
                "count": 1,
            }

        def _energy_svc(self):
            return self._energy_read_service

        def _sanitize_for_json(self, value):
            return value

    bridge = MockBridge()
    summary = bridge.get_fuel_distribution_product_year_summary({"product": "GASOLINA C"})
    assert summary["count"] == 1
    bridge._energy_read_service.get_fuel_distribution_product_year_summary.assert_called_once_with(
        source_dataset_id=None,
        product="GASOLINA C",
        unit=None,
        start_year=None,
        end_year=None,
        limit=500,
    )

    series = bridge.get_fuel_distribution_state_month_series(
        {"source_dataset_id": "anp_fuel_sales_state_month", "product": "GASOLINA C", "state": "SP"}
    )
    assert series["items"][0]["reference_period"] == "2026-01"
    bridge._energy_read_service.get_fuel_distribution_state_month_series.assert_called_once_with(
        source_dataset_id="anp_fuel_sales_state_month",
        product="GASOLINA C",
        state="SP",
        start_period=None,
        end_period=None,
        unit=None,
        limit=5000,
    )


def test_fuel_distribution_detail_reads_require_bounds(tmp_path: Path, db_conn):
    from src.energy_kpi.fuel_distribution import (
        FuelDistributionSourceFile,
        persist_fuel_distribution_sources_to_managed_store,
        read_fuel_distribution_detail,
    )

    source_path = _write_csv(
        tmp_path / "vendas-anuais.csv",
        "\ufeffANO;GRANDE REGIÃO;UF;PRODUTO;CÓDIGO IBGE;MUNICÍPIO;VENDAS\n"
        "2024;REGIÃO SUDESTE;SP;GASOLINA C;3550308;SAO PAULO;1000\n"
        "2024;REGIÃO SUDESTE;SP;GASOLINA C;3509502;CAMPINAS;200\n"
        "2024;REGIÃO SUL;PR;GASOLINA C;4106902;CURITIBA;300\n",
    )
    persist_fuel_distribution_sources_to_managed_store(
        data_dir=tmp_path,
        conn=db_conn,
        sources=(
            FuelDistributionSourceFile(
                source_dataset_id="anp_fuel_sales_municipality_year",
                label="Vendas de gasolina C por municipio",
                official_url="https://example.test/anp/gasolina.csv",
                path=source_path,
                grain="municipality-product-year",
                value_unit="liters",
                frequency="annual",
            ),
        ),
        import_batch_id="fuel-batch-2",
        parser_version="test-parser",
    )

    with pytest.raises(ValueError, match="require source_dataset_id, product, and year"):
        read_fuel_distribution_detail(
            data_dir=tmp_path,
            source_dataset_id="anp_fuel_sales_municipality_year",
            product="GASOLINA C",
            year=None,
        )

    result = read_fuel_distribution_detail(
        data_dir=tmp_path,
        source_dataset_id="anp_fuel_sales_municipality_year",
        product="GASOLINA C",
        year=2024,
        region_or_state="SP",
        limit=1,
    )

    assert result["source"] == "managed_parquet"
    assert result["count"] == 1
    assert result["total_matching_rows"] == 2
    assert result["truncated"] is True
    assert result["rows"][0]["municipality"] == "CAMPINAS"
    assert result["rows"][0]["source_dataset_id"] == "anp_fuel_sales_municipality_year"


def test_fuel_distribution_import_accepts_optional_columns_that_appear_later(tmp_path: Path, db_conn):
    from src.energy_kpi.fuel_distribution import (
        FuelDistributionSourceFile,
        persist_fuel_distribution_sources_to_managed_store,
    )

    plain_state_source = _write_csv(
        tmp_path / "plain.csv",
        "\ufeffANO;MÊS;GRANDE REGIÃO;UNIDADE DA FEDERAÇÃO;PRODUTO;VENDAS\n"
        + "".join(
            "2026;JAN;REGIÃO SUDESTE;SÃO PAULO;GASOLINA C;10,0\n"
            for _ in range(101)
        ),
    )
    segmented_source = _write_csv(
        tmp_path / "segmented.csv",
        "\ufeffANO;MÊS;UNIDADE DA FEDERAÇÃO;PRODUTO;SEGMENTO;VENDAS\n"
        "2026;JAN;SÃO PAULO;GASOLINA C;POSTO REVENDEDOR;20,0\n",
    )

    result = persist_fuel_distribution_sources_to_managed_store(
        data_dir=tmp_path,
        conn=db_conn,
        sources=(
            FuelDistributionSourceFile(
                source_dataset_id="anp_fuel_sales_state_month",
                label="Plain",
                official_url="https://example.test/plain.csv",
                path=plain_state_source,
                grain="state-product-month",
                value_unit="m3",
                frequency="monthly",
            ),
            FuelDistributionSourceFile(
                source_dataset_id="anp_fuel_sales_segment_state_month",
                label="Segmented",
                official_url="https://example.test/segmented.csv",
                path=segmented_source,
                grain="state-product-segment-month",
                value_unit="m3",
                frequency="monthly",
            ),
        ),
        import_batch_id="fuel-batch-mixed",
        parser_version="test-parser",
    )

    assert result["row_count"] == 102
