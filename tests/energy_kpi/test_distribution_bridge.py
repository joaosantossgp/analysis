"""Tests for the DistributionBridgeMixin."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import text

from desktop.bridge import CVMBridge
from src.energy_kpi.distribution import seed_distribution_static_data


class MockBridge(CVMBridge):
    """A mock bridge that inherits from the actual bridge class."""
    def __init__(self, settings, db_conn):
        self.settings = settings
        self.db_conn = db_conn
        self._distribution_read_service = None
        self._dist_refresh_state = {"status": "idle", "error": None}

    def _sanitize_for_json(self, value):
        # Simplistic version of json sanitization for testing
        return value

    def _dist_svc(self):
        if self._distribution_read_service is None:
            from src.energy_kpi.distribution.read import DistributionReadService
            self._distribution_read_service = DistributionReadService(self.settings)
            
            # Mock the connection context manager of DistributionReadService to yield the test db_conn
            class MockConnContext:
                def __init__(self, conn):
                    self.conn = conn
                def __enter__(self):
                    return self.conn
                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass
            
            mock_engine = MagicMock()
            mock_engine.connect.side_effect = lambda: MockConnContext(self.db_conn)
            self._distribution_read_service._engine = MagicMock(return_value=mock_engine)
            
        return self._distribution_read_service


def test_distribution_bridge_read_endpoints(db_conn):
    # Seed static master data
    seed_distribution_static_data(db_conn)

    # Insert some dummy facts
    db_conn.execute(text("""
        INSERT INTO distribution_market_facts (
            fact_id, distributor_id, reference_month, metric_name, raw_value, normalized_value, original_unit, normalized_unit, source_row_hash, snapshot_id
        )
        VALUES ('fact1', 'coelba', '2025-01', 'revenue', 1000.0, 1000.0, 'R$', 'BRL', 'hash1', 'snap1')
    """))

    # Rebuild aggregates
    from src.energy_kpi.distribution.aggregates import rebuild_distribution_aggregates
    rebuild_distribution_aggregates(db_conn)

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.paths.energy_kpi_sqlite_url = "sqlite:///:memory:"

    bridge = MockBridge(mock_settings, db_conn)

    # 1. Test get_distribution_distributors
    res = bridge.get_distribution_distributors()
    assert "error" not in res
    assert res["count"] > 0
    assert any(d["distributor_id"] == "coelba" for d in res["items"])

    # 2. Test get_distribution_distributors with search
    res_search = bridge.get_distribution_distributors({"search": "Coelba"})
    assert res_search["count"] == 1
    assert res_search["items"][0]["distributor_id"] == "coelba"

    # 3. Test get_distribution_distributor_detail
    res_detail = bridge.get_distribution_distributor_detail({"distributor_id": "coelba"})
    assert "error" not in res_detail
    assert res_detail["identity"]["distributor_id"] == "coelba"
    assert "2025-01" in res_detail["available_periods"]

    # 4. Test get_distribution_series
    res_series = bridge.get_distribution_series({
        "entity_type": "distributor",
        "entity_id": "coelba",
        "frequency": "monthly"
    })
    assert "error" not in res_series
    assert res_series["count"] == 1
    assert res_series["series"][0]["period"] == "2025-01"
    assert res_series["series"][0]["revenue_brl"] == 1000.0


@patch("src.energy_kpi.distribution.ingest.requests.get")
def test_distribution_bridge_refresh(mock_get, db_conn, tmp_path):
    # Seed static master data
    seed_distribution_static_data(db_conn)

    # Mock the request get response to return dummy parquet content
    import polars as pl
    mock_df = pl.DataFrame({
        "NumCNPJAgenteDistribuidora": ["15139629000194"],
        "NomAgenteDistribuidora": ["COELBA DISTRIBUIDORA"],
        "SigAgenteDistribuidora": ["COELBA"],
        "NomTipoMercado": ["Regular"],
        "DscModalidadeTarifaria": ["Convencional"],
        "DscSubGrupoTarifario": ["B1"],
        "DscClasseConsumoMercado": ["Residencial"],
        "DscSubClasseConsumidor": ["Residencial"],
        "DscDetalheConsumidor": ["Não se aplica"],
        "NumCNPJAgenteAcessante": [None],
        "NomAgenteAcessante": [None],
        "DscPostoTarifario": ["Não se aplica"],
        "DscOpcaoEnergia": ["CATIVO"],
        "DscDetalheMercado": ["Receita Energia (R$)"],
        "DatCompetencia": ["2025-01-01"],
        "VlrMercado": ["50000.00"]
    })
    import io
    buf = io.BytesIO()
    mock_df.write_parquet(buf)
    parquet_bytes = buf.getvalue()
    
    mock_resp = MagicMock()
    mock_resp.iter_content.return_value = [parquet_bytes]
    mock_get.return_value = mock_resp

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.paths.energy_kpi_raw_dir = tmp_path / "raw"
    mock_settings.paths.energy_kpi_raw_dir.mkdir(parents=True, exist_ok=True)
    mock_settings.paths.energy_kpi_sqlite_url = "sqlite:///:memory:"

    # Patch engine to use our in-memory db_conn
    with patch("src.energy_kpi.schema.get_energy_kpi_engine") as mock_engine_fn, \
         patch("src.platform.settings.get_settings", return_value=mock_settings):
        
        mock_engine = MagicMock()
        mock_engine.begin.return_value = MagicMock(__enter__=MagicMock(return_value=db_conn), __exit__=MagicMock())
        mock_engine_fn.return_value = mock_engine

        bridge = MockBridge(mock_settings, db_conn)

        # Trigger refresh for year 2025
        res = bridge.refresh_distribution_data({"years": [2025]})
        assert res["status"] == "started"

        # Wait for thread to complete
        start_time = time.time()
        while time.time() - start_time < 5.0:
            status = bridge.get_distribution_refresh_status()
            if status["status"] in ("success", "error"):
                break
            time.sleep(0.1)

        final_status = bridge.get_distribution_refresh_status()
        assert final_status["status"] == "success"
        assert final_status["stage"] == "done"
        
        # Verify facts were actually written in db_conn
        count = db_conn.execute(text("SELECT count(*) FROM distribution_market_facts")).scalar()
        assert count == 1


def test_distribution_bridge_groups_and_excel(db_conn, tmp_path):
    seed_distribution_static_data(db_conn)

    # Insert a snapshot to satisfy source_snapshots query in excel
    db_conn.execute(text("""
        INSERT INTO source_snapshots (snapshot_id, source, fetched_at, file_path, sha256, row_count, status)
        VALUES ('snap1', 'SAMP Mercado', '2025-01-01', 'file.parquet', 'sha256_hash', 100, 'ok')
    """))

    mock_settings = MagicMock()
    mock_settings.paths.reports_dir = tmp_path / "reports"
    mock_settings.paths.reports_dir.mkdir(parents=True, exist_ok=True)
    mock_settings.paths.energy_kpi_sqlite_url = "sqlite:///:memory:"

    bridge = MockBridge(mock_settings, db_conn)

    # 1. Test get_distribution_groups
    res_groups = bridge.get_distribution_groups()
    assert "error" not in res_groups
    assert res_groups["count"] > 0
    assert any(g["economic_group_id"] == "neoenergia" for g in res_groups["items"])

    # 2. Test get_distribution_group_detail
    res_detail = bridge.get_distribution_group_detail({"group_id": "neoenergia"})
    assert "error" not in res_detail
    assert res_detail["identity"]["economic_group_id"] == "neoenergia"
    assert len(res_detail["portfolio"]) > 0

    # 3. Test export_distribution_excel for distributor
    # Patch both the engine and the DistributionReadService used inside excel.py
    # so it operates on the same seeded in-memory db_conn rather than a blank :memory:.
    with (
        patch("src.energy_kpi.distribution.excel.get_energy_kpi_engine") as mock_engine_fn,
        patch("src.energy_kpi.distribution.excel.DistributionReadService") as mock_svc_cls,
    ):
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = lambda: bridge._dist_svc()._engine().connect()
        mock_engine_fn.return_value = mock_engine
        # Always return the already-seeded service so detail lookups succeed
        mock_svc_cls.return_value = bridge._dist_svc()

        res_excel = bridge.export_distribution_excel({
            "entity_type": "distributor",
            "entity_id": "coelba"
        })
        assert "error" not in res_excel or res_excel["error"] is None, res_excel
        assert res_excel["path"] is not None
        assert Path(res_excel["path"]).exists()

        # 4. Test export_distribution_excel for group
        res_excel_group = bridge.export_distribution_excel({
            "entity_type": "group",
            "entity_id": "neoenergia"
        })
        assert "error" not in res_excel_group or res_excel_group["error"] is None, res_excel_group
        assert res_excel_group["path"] is not None
        assert Path(res_excel_group["path"]).exists()

