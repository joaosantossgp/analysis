"""Tests for the DistributionBridgeMixin."""
from __future__ import annotations

import time
import threading
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import polars as pl
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

    def _svc(self):
        if not hasattr(self, "_mock_read_service"):
            class MockConnContext:
                def __init__(self, conn):
                    self.conn = conn
                def __enter__(self):
                    return self.conn
                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass

            mock_engine = MagicMock()
            mock_engine.begin.side_effect = lambda: MockConnContext(self.db_conn)
            svc = MagicMock()
            svc.engine = mock_engine
            svc.settings = self.settings
            svc.invalidate_read_caches = MagicMock()
            self._mock_read_service = svc
        return self._mock_read_service

    def _onboarding(self):
        svc = MagicMock()
        svc.get_onboarding_state.return_value = {}
        return svc


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

    def mock_get_side_effect(url, *args, **kwargs):
        import polars as pl
        import io
        
        # 1. Determine which resource is being requested based on the URL
        if "samp-balanco" in url:
            df = pl.DataFrame({
                "NumCPFCNPJ": ["15139629000194"],
                "NomAgente": ["COELBA DISTRIBUIDORA"],
                "AnmCompetenciaBalanco": ["202501"],
                "DscModalidadeBalanco": ["Regulado"],
                "DscFluxoEnergia": ["Injeção"],
                "DscCctBalanco": ["Ativa"],
                "DscDetalheBalanco": ["Consumo total"],
                "VlrEnergia": ["1000.0"]
            })
        elif "samp-" in url:
            df = pl.DataFrame({
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
        elif "limite" in url:
            df = pl.DataFrame({
                "NumCNPJ": ["15139629000194"],
                "SigAgente": ["COELBA"],
                "IdeConjUndConsumidoras": ["123"],
                "DscConjUndConsumidoras": ["Set 1"],
                "SigIndicador": ["DEC"],
                "AnoLimiteQualidade": [2025],
                "VlrLimite": [10.5]
            })
        elif "coletivos-" in url and "compensacao" not in url:
            df = pl.DataFrame({
                "NumCNPJ": ["15139629000194"],
                "SigAgente": ["COELBA"],
                "IdeConjUndConsumidoras": ["123"],
                "DscConjUndConsumidoras": ["Set 1"],
                "SigIndicador": ["DEC"],
                "AnoIndice": [2025],
                "NumPeriodoIndice": [1],
                "VlrIndiceEnviado": [8.5]
            })
        elif "compensacao" in url:
            df = pl.DataFrame({
                "NumCNPJ": ["15139629000194", "15139629000194"],
                "SigAgente": ["COELBA", "COELBA"],
                "IdeConjUndConsumidoras": ["123", "123"],
                "DscConjUndConsumidoras": ["Set 1", "Set 1"],
                "SigIndicador": ["QT01", "PG01"],
                "AnoIndice": [2025, 2025],
                "NumPeriodoIndice": [1, 1],
                "VlrIndiceEnviado": ["10", "150.0"]
            })
        elif "tarifas" in url:
            df = pl.DataFrame({
                "NumCNPJDistribuidora": ["15139629000194"],
                "NomAgenteRegulado": ["COELBA"],
                "DscREH": ["REH 123"],
                "DatInicioVigencia": ["2025-01-01"],
                "DatFimVigencia": ["2025-12-31"],
                "DscBaseTarifaria": ["Tarifa Base"],
                "NomSubgrupo": ["B1"],
                "DscModalidadeTarifaria": ["Convencional"],
                "DscClasse": ["Residencial"],
                "DscSubClasse": ["Residencial"],
                "DscDetalhe": ["Não se aplica"],
                "NomPostoTarifario": ["Não se aplica"],
                "SigAgenteAcessante": ["Não se aplica"],
                "NomUnidadeMedida": ["R$/kWh"],
                "VlrTUSD": ["0.45"],
                "VlrTE": ["0.35"]
            })
        elif "inadimplencia" in url:
            df = pl.DataFrame({
                "NumCNPJ": ["15139629000194"],
                "SigAgente": ["COELBA"],
                "SigIndicador": ["ITot1"],
                "AnoIndice": [2025],
                "NumPeriodoIndice": [1],
                "VlrIndiceEnviado": ["0.02"]
            })
        elif "geracao-distribuida" in url:
            df = pl.DataFrame({
                "NumCNPJDistribuidora": ["15139629000194"],
                "SigAgente": ["COELBA"],
                "CodEmpreendimento": ["GD-1"],
                "NomMunicipio": ["Salvador"],
                "SigUF": ["BA"],
                "DscClasseConsumo": ["Residencial"],
                "DscSubGrupoTarifario": ["B1"],
                "SigModalidadeEmpreendimento": ["GD"],
                "DscModalidadeHabilitado": ["GD"],
                "SigTipoGeracao": ["Solar"],
                "DscFonteGeracao": ["Solar"],
                "DscPorte": ["Microgeração"],
                "NumCoordNEmpreendimento": [-12.9],
                "NumCoordEEmpreendimento": [-38.5],
                "DthAtualizaCadastralEmpreend": ["2025-01-01"],
                "AnmPeriodoReferencia": ["202501"],
                "MdaPotenciaInstaladaKW": ["5.5"],
                "QtdUCRecebeCredito": [1]
            })
        else:
            df = pl.DataFrame()

        buf = io.BytesIO()
        if "empreendimento-geracao-distribuida" in url or "samp-" in url or "compensacao" in url or url.endswith(".parquet"):
            df.write_parquet(buf)
        else:
            df.write_csv(buf, separator=";")
        
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [buf.getvalue()]
        mock_resp.status_code = 200
        return mock_resp

    mock_get.side_effect = mock_get_side_effect

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.paths.data_dir = tmp_path
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


def test_distribution_refresh_prevents_duplicates_and_settings_stays_readable(db_conn, tmp_path):
    seed_distribution_static_data(db_conn)

    mock_settings = MagicMock()
    mock_settings.paths.data_dir = tmp_path
    mock_settings.paths.energy_kpi_raw_dir = tmp_path / "raw"
    mock_settings.paths.energy_kpi_raw_dir.mkdir(parents=True, exist_ok=True)
    mock_settings.paths.energy_kpi_sqlite_url = "sqlite:///:memory:"

    bridge = MockBridge(mock_settings, db_conn)
    started = threading.Event()
    release = threading.Event()

    def slow_step(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5.0)
        return 0

    mock_engine = MagicMock()
    mock_engine.begin.return_value = MagicMock(__enter__=MagicMock(return_value=db_conn), __exit__=MagicMock())

    with (
        patch("src.energy_kpi.schema.get_energy_kpi_engine", return_value=mock_engine),
        patch("src.platform.settings.get_settings", return_value=mock_settings),
        patch.object(bridge, "_run_and_log_step", side_effect=slow_step),
        patch("src.energy_kpi.distribution.aggregates.rebuild_distribution_aggregates", return_value=None),
    ):
        first = bridge.refresh_distribution_data({"years": [2025]})
        assert first["status"] == "started"
        assert started.wait(timeout=5.0)

        duplicate = bridge.refresh_distribution_data({"years": [2025]})
        assert duplicate["status"] == "already_running"

        settings = bridge.get_data_update_settings({})
        assert "error" not in settings
        assert settings["batch_size"] in bridge.DATA_UPDATE_BATCH_SIZES

        release.set()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            status = bridge.get_distribution_refresh_status()
            if status["status"] in {"success", "error"}:
                break
            time.sleep(0.05)

        final_status = bridge.get_distribution_refresh_status()
        assert final_status["status"] == "success"


def test_distribution_refresh_step_logs_lock_wait_and_resource_diagnostics(db_conn, tmp_path):
    mock_settings = MagicMock()
    mock_settings.paths.data_dir = tmp_path
    mock_settings.paths.energy_kpi_raw_dir = tmp_path / "raw"
    mock_settings.paths.energy_kpi_raw_dir.mkdir(parents=True, exist_ok=True)
    mock_settings.paths.energy_kpi_sqlite_url = "sqlite:///:memory:"

    source_path = mock_settings.paths.energy_kpi_raw_dir / "sample.csv"
    source_path.write_text("period,value\n2025-01,1\n", encoding="utf-8")
    snapshot = SimpleNamespace(
        file_path=source_path,
        snapshot_id="snap-lock-wait",
        sha256="abc123",
        row_count=1,
    )

    class ConnContext:
        def __enter__(self):
            return db_conn

        def __exit__(self, exc_type, exc, tb):
            return False

    class TinyEngine:
        def begin(self):
            return ConnContext()

    bridge = MockBridge(mock_settings, db_conn)

    def parse_fn(path, format_type):
        assert path == source_path
        assert format_type == "csv"
        return pl.DataFrame({"period": ["2025-01"], "value": [1.0]})

    def upsert_fn(conn, df, snapshot_id):
        assert conn is db_conn
        assert df.height == 1
        assert snapshot_id == "snap-lock-wait"
        return 1

    with patch("src.energy_kpi.distribution.ingest.fetch_distribution_resource", return_value=snapshot):
        rows = bridge._run_and_log_step(
            TinyEngine(),
            mock_settings,
            source_id="test_source",
            domain="test",
            resource_key="sample",
            parse_fn=parse_fn,
            upsert_fn=upsert_fn,
            force=False,
        )

    assert rows == 1
    log = db_conn.execute(
        text(
            """
            SELECT source_id, status, source_rows, final_published_rows,
                   elapsed_lock_wait_ms, peak_rss_mb, cpu_time_ms
            FROM energy_source_refresh_log
            WHERE source_id = 'test_source'
            """
        )
    ).fetchone()
    assert log is not None
    assert log[1] == "success"
    assert log[2] == 1
    assert log[3] == 1
    assert log[4] is not None and log[4] >= 0
    assert log[5] is None or log[5] > 0
    assert log[6] is not None and log[6] >= 0


def test_distribution_refresh_status_years(db_conn):
    # Seed static master data
    seed_distribution_static_data(db_conn)

    # Insert a dummy snapshot to mock ingested years
    db_conn.execute(text("""
        INSERT INTO source_snapshots (snapshot_id, source, fetched_at, file_path, sha256, row_count, source_version_label, status)
        VALUES ('snap_test_1', 'ANEEL', '2026-06-15', 'dummy/path', 'dummy_sha', 10, 'ANEEL:samp_mercado:2024', 'ok')
    """))

    mock_settings = MagicMock()
    mock_settings.paths.energy_kpi_sqlite_url = "sqlite:///:memory:"

    bridge = MockBridge(mock_settings, db_conn)
    status = bridge.get_distribution_refresh_status()

    assert "supported_years" in status
    assert 2024 in status["supported_years"]
    assert 2016 in status["supported_years"]
    assert "ingested_years" in status
    assert status["ingested_years"] == [2024]


def test_distribution_refresh_resilience_multi_year(db_conn, tmp_path):
    mock_settings = MagicMock()
    mock_settings.paths.data_dir = tmp_path
    mock_settings.paths.energy_kpi_raw_dir = tmp_path / "raw"
    mock_settings.paths.energy_kpi_raw_dir.mkdir(parents=True, exist_ok=True)
    mock_settings.paths.energy_kpi_sqlite_url = "sqlite:///:memory:"

    bridge = MockBridge(mock_settings, db_conn)
    
    # Mock _run_and_log_step to fail on 2024 but succeed on 2025
    original_run_step = bridge._run_and_log_step
    
    def mock_run_step(engine, settings, source_id, domain, resource_key, parse_fn, upsert_fn, force):
        if resource_key == 2024:
            raise RuntimeError("Mock download failure for 2024")
        return 100

    bridge._run_and_log_step = mock_run_step

    # We mock get_distribution_refresh_status and refresh_distribution_data's thread target
    # or patch the functions to run the loop synchronously.
    # Instead of running thread, let's call the logic or mock the call.
    # Wait, let's test that _run logic behaves correctly by invoking it.
    # Since _run is a nested function in refresh_distribution_data, we can test it by running refresh_distribution_data and waiting.
    # To run it quickly and synchronously in this test, let's patch threading.Thread:
    with patch("threading.Thread") as mock_thread:
        # Capture the target function
        bridge.refresh_distribution_data({"years": [2024, 2025]})
        assert mock_thread.called
        target_fn = mock_thread.call_args[1]["target"]
        
        # Run the target function synchronously in test thread
        with patch("src.energy_kpi.distribution.aggregates.rebuild_distribution_aggregate_slices") as mock_rebuild:
            target_fn()
            assert mock_rebuild.called
            assert mock_rebuild.call_args.args[1] == [
                "balance",
                "market",
                "continuity",
                "compensation",
                "tariff",
                "delinquency",
                "mmgd",
            ]

    status = bridge.get_distribution_refresh_status()
    assert status["status"] == "success"
    # Ensure it reports warning and failed years list
    assert "Refresh completed with warnings" in status["message"]
    assert "Failed years: 2024" in status["message"]


def test_conglomerate_asset_mapping_endpoints(db_conn):
    # 1. Create companies table
    db_conn.execute(text("""
        CREATE TABLE IF NOT EXISTS companies (
            cd_cvm INTEGER PRIMARY KEY,
            company_name TEXT NOT NULL,
            ticker_b3 TEXT,
            cnpj TEXT,
            setor_cvm TEXT,
            gics_sector TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """))

    # 2. Seed static master data for distribution
    seed_distribution_static_data(db_conn)

    # 4. Insert mock companies
    db_conn.execute(text("""
        INSERT OR REPLACE INTO companies (cd_cvm, company_name, ticker_b3, cnpj, setor_cvm, gics_sector, is_active)
        VALUES 
        (1001, 'CPFL ENERGIA S.A.', 'CPFE3', '02429144000193', 'Energia Elétrica', 'Utilities', 1),
        (1002, 'CENTRAIS ELETRICAS BRASILEIRAS S.A. - ELETROBRAS', 'ELET3', '33013807000108', 'Energia Elétrica', 'Utilities', 1)
    """))

    # 5. Insert mock physical assets
    db_conn.execute(text("""
        INSERT OR REPLACE INTO distribution_distributors (distributor_id, canonical_name, trade_name, normalized_cnpj, primary_uf, status)
        VALUES ('cpfl_paulista', 'CPFL Paulista', 'CPFL Paulista', '02429144000193', 'SP', 'active')
    """))
    db_conn.execute(text("""
        INSERT OR REPLACE INTO ccee_plant_parcels (plant_parcel_code, plant_name, agent_name, capacity_mw, uf, raw_payload_hash)
        VALUES ('PLANT_ELET', 'UHE Eletrobras Plant', 'Eletrobras Agent', 150.0, 'RJ', 'dummy_hash')
    """))

    # Mock settings
    mock_settings = MagicMock()
    mock_settings.paths.energy_kpi_sqlite_url = "sqlite:///:memory:"

    # Initialize bridge
    bridge = MockBridge(mock_settings, db_conn)
    
    class MockConnContext:
        def __init__(self, conn):
            self.conn = conn
        def __enter__(self):
            return self.conn
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    # Setup CVM Engine Mock
    svc = bridge._svc()
    svc.engine.connect.side_effect = lambda: MockConnContext(db_conn)
    svc.engine.begin.side_effect = lambda: MockConnContext(db_conn)

    # Setup Energy KPI Engine Mock
    energy_engine = bridge._dist_svc()._engine()
    energy_engine.connect.side_effect = lambda: MockConnContext(db_conn)
    energy_engine.begin.side_effect = lambda: MockConnContext(db_conn)

    # 6. Test run_automatic_mapping
    auto_res = bridge.run_automatic_mapping()
    assert auto_res["status"] == "success"
    assert auto_res["matched"] >= 2

    # 7. Test get_conglomerates
    cong_res = bridge.get_conglomerates()
    assert "error" not in cong_res
    assert cong_res["count"] > 0
    cpfl = next(c for c in cong_res["items"] if c["cd_cvm"] == 1001)
    assert cpfl["distributors_count"] >= 1
    assert cpfl["plants_count"] == 0
    
    eletro = next(c for c in cong_res["items"] if c["cd_cvm"] == 1002)
    assert eletro["plants_count"] >= 1
    assert eletro["total_capacity_mw"] >= 150.0

    # 8. Test get_asset_mappings
    mappings_res = bridge.get_asset_mappings()
    assert "error" not in mappings_res
    assert mappings_res["count"] >= 2
    
    dist_map = next(m for m in mappings_res["items"] if m["id"] == "cpfl_paulista")
    assert dist_map["mapped_cvm"] == 1001
    assert dist_map["mapping_source"] == "auto"

    # 9. Test update_asset_mapping (manual override)
    update_res = bridge.update_asset_mapping({
        "asset_id": "cpfl_paulista",
        "asset_type": "distributor",
        "cd_cvm": 1002,
        "review_notes": "Manual override notes"
    })
    assert update_res["status"] == "success"

    # Verify manual mapping is updated
    mappings_res2 = bridge.get_asset_mappings()
    dist_map2 = next(m for m in mappings_res2["items"] if m["id"] == "cpfl_paulista")
    assert dist_map2["mapped_cvm"] == 1002
    assert dist_map2["mapping_source"] == "manual"

    # 10. Run automatic mapping again and verify that manual override is PRESERVED!
    auto_res2 = bridge.run_automatic_mapping()
    assert auto_res2["status"] == "success"
    assert auto_res2["preserved_manual"] == 1

    mappings_res3 = bridge.get_asset_mappings()
    dist_map3 = next(m for m in mappings_res3["items"] if m["id"] == "cpfl_paulista")
    assert dist_map3["mapped_cvm"] == 1002
    assert dist_map3["mapping_source"] == "manual"

    # 11. Test custom non-listed owner mapping
    update_res_custom = bridge.update_asset_mapping({
        "asset_id": "cpfl_paulista",
        "asset_type": "distributor",
        "custom_owner_name": "State Grid Brazil",
        "review_notes": "Custom owner mapping notes"
    })
    assert update_res_custom["status"] == "success"

    # Verify custom mapping in get_asset_mappings
    mappings_res4 = bridge.get_asset_mappings()
    dist_map4 = next(m for m in mappings_res4["items"] if m["id"] == "cpfl_paulista")
    assert dist_map4["mapped_cvm"] is None
    assert dist_map4["custom_owner_name"] == "State Grid Brazil"
    assert dist_map4["company_name"] == "State Grid Brazil"
    assert dist_map4["ticker"] == "Non-Listed"
    assert dist_map4["mapping_source"] == "manual"

    # Verify custom mapping in get_conglomerates
    cong_res2 = bridge.get_conglomerates()
    state_grid = next(c for c in cong_res2["items"] if c["company_name"] == "State Grid Brazil")
    assert state_grid["is_listed"] is False
    assert state_grid["distributors_count"] == 1
    assert state_grid["cd_cvm"] is None
