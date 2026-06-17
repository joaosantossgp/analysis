# -*- coding: utf-8 -*-
"""Test suite for CNPJ and stock ticker metadata logic, backfills, and formatting."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.companies.cnpj import validate_cnpj, format_cnpj
from src.financials.database import _backfill_companies_metadata, init_db_tables, CVMDatabase
from src.financials.scraper import CVMScraper


# ──────────────────────────────────────────────────────────────────────────────
# 1. CNPJ Formatter and Validator Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCNPJValidatorAndFormatter:
    # Valid CNPJ: Petrobras
    PETROBRAS_RAW = "33000167000101"
    PETROBRAS_FORMATTED = "33.000.167/0001-01"

    # Valid CNPJ with leading zero (e.g. AMBEV/another firm)
    LEADING_ZERO_RAW = "00360305000104"
    LEADING_ZERO_FORMATTED = "00.360.305/0001-04"

    def test_valid_unformatted_cnpj(self):
        assert validate_cnpj(self.PETROBRAS_RAW) is True
        assert format_cnpj(self.PETROBRAS_RAW) == self.PETROBRAS_FORMATTED

    def test_valid_formatted_cnpj(self):
        assert validate_cnpj(self.PETROBRAS_FORMATTED) is True
        assert format_cnpj(self.PETROBRAS_FORMATTED) == self.PETROBRAS_FORMATTED

    def test_valid_leading_zero_cnpj(self):
        assert validate_cnpj(self.LEADING_ZERO_RAW) is True
        assert format_cnpj(self.LEADING_ZERO_RAW) == self.LEADING_ZERO_FORMATTED
        assert validate_cnpj(self.LEADING_ZERO_FORMATTED) is True
        assert format_cnpj(self.LEADING_ZERO_FORMATTED) == self.LEADING_ZERO_FORMATTED

    def test_empty_or_null_values(self):
        assert validate_cnpj(None) is False
        assert format_cnpj(None) == "Not available"
        assert validate_cnpj("") is False
        assert format_cnpj("") == "Not available"

    def test_fewer_than_14_digits(self):
        assert validate_cnpj("3300016700010") is False
        assert format_cnpj("3300016700010") == "Not available"
        assert validate_cnpj("123") is False

    def test_more_than_14_digits(self):
        assert validate_cnpj("3300016700010199") is False
        assert format_cnpj("3300016700010199") == "Not available"

    def test_unexpected_characters_and_invalid_pattern(self):
        # Letters/symbols
        assert validate_cnpj("330001670001AB") is False
        assert format_cnpj("330001670001AB") == "Not available"
        # All same digits (invalid CNPJs)
        assert validate_cnpj("00000000000000") is False
        assert validate_cnpj("11111111111111") is False

    def test_invalid_check_digits(self):
        # Swap last digits of Petrobras CNPJ
        assert validate_cnpj("33000167000110") is False
        assert format_cnpj("33000167000110") == "Not available"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Database Metadata Upsert & Backfill Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestDatabaseMetadataBackfill:
    @pytest.fixture
    def memory_db_engine(self):
        engine = create_engine("sqlite:///:memory:")
        init_db_tables(engine)
        return engine

    def test_automatic_local_backfill_normalizes_cnpj_and_sets_ticker(self, memory_db_engine):
        # Insert a company with formatted CNPJ and NULL ticker
        with memory_db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO companies (cd_cvm, company_name, company_type, cnpj, updated_at)
                    VALUES (9512, 'PETROBRAS', 'comercial', '33.000.167/0001-01', '2026-06-09T20:00:00')
                    """
                )
            )

        # Call backfill
        _backfill_companies_metadata(memory_db_engine)

        with memory_db_engine.connect() as conn:
            row = conn.execute(
                text("SELECT cnpj, ticker_b3 FROM companies WHERE cd_cvm = 9512")
            ).fetchone()
            assert row is not None
            # CNPJ should be normalized to exactly 14 digits, and ticker set
            assert row[0] == "33000167000101"
            assert row[1] == "PETR4"

    def test_backfill_is_idempotent_and_preserves_valid_metadata(self, memory_db_engine):
        # Insert a company with predefined custom (or already valid) CNPJ and ticker
        custom_cnpj = "33000167000101"
        custom_ticker = "PETR4_CUSTOM"
        with memory_db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO companies (cd_cvm, company_name, company_type, cnpj, ticker_b3, updated_at)
                    VALUES (9512, 'PETROBRAS', 'comercial', :cnpj, :ticker, '2026-06-09T20:00:00')
                    """
                ),
                {"cnpj": custom_cnpj, "ticker": custom_ticker}
            )

        # Call backfill again — should not overwrite the existing valid ticker with the catalog default
        _backfill_companies_metadata(memory_db_engine)

        with memory_db_engine.connect() as conn:
            row = conn.execute(
                text("SELECT cnpj, ticker_b3 FROM companies WHERE cd_cvm = 9512")
            ).fetchone()
            assert row[0] == custom_cnpj
            assert row[1] == custom_ticker  # Kept the existing custom value

    def test_backfill_handles_invalid_cnpj_gracefully(self, memory_db_engine):
        # Insert a company with an invalid CNPJ
        with memory_db_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO companies (cd_cvm, company_name, company_type, cnpj, updated_at)
                    VALUES (99999, 'INVALID_CO', 'comercial', '12345_invalid', '2026-06-09T20:00:00')
                    """
                )
            )

        # Run backfill. The invalid CNPJ should not be normalized/validated (stays as is, or we can reject it, but it won't crash)
        _backfill_companies_metadata(memory_db_engine)

        with memory_db_engine.connect() as conn:
            row = conn.execute(
                text("SELECT cnpj, ticker_b3 FROM companies WHERE cd_cvm = 99999")
            ).fetchone()
            assert row[0] == "12345_invalid"  # Stays unmodified since it didn't pass validate_cnpj
            assert row[1] is None


# ──────────────────────────────────────────────────────────────────────────────
# 3. Scraper & Ingestion Robustness Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestScraperIngestionMetadata:
    def test_scraper_handles_absence_of_cnpj_column(self, tmp_path):
        """Verify the CVMScraper.fetch_company_list is robust to mock data lacking the CNPJ_CIA column."""
        from src.platform.settings import build_settings
        settings = build_settings()
        
        # Instantiate scraper with temp directory
        scraper = CVMScraper(
            output_dir=str(tmp_path / "output"),
            data_dir=str(tmp_path / "data"),
            report_type="consolidated"
        )
        
        # Mock csv response that has no CNPJ_CIA column
        csv_content = (
            "CD_CVM;DENOM_SOCIAL;DENOM_COMERC;SETOR_ATIV\n"
            "9512;PETROBRAS S.A.;PETROBRAS;Petróleo e Gás\n"
        ).encode('latin-1')
        
        mock_resp = MagicMock()
        mock_resp.content = csv_content
        mock_resp.raise_for_status = MagicMock()
        
        with patch('requests.get', return_value=mock_resp):
            df = scraper.fetch_company_list()
            
        assert df is not None
        assert scraper.cnpjs_map == {}  # Gracefully empty, no KeyError thrown!


# ──────────────────────────────────────────────────────────────────────────────
# 4. Ticker Selection Model Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTickerSelectionModel:
    def test_on_only_company(self):
        # VALE (4170) -> VALE3 (Common/ON only)
        from src.companies.ticker_map import TICKER_MAP
        ticker = TICKER_MAP.get(4170)
        assert ticker == "VALE3.SA"

    def test_pn_and_on_company(self):
        # PETROBRAS (9512) -> maps to PETR4.SA (Preferred/PN), which is the most liquid class
        from src.companies.ticker_map import TICKER_MAP
        ticker = TICKER_MAP.get(9512)
        assert ticker == "PETR4.SA"

    def test_unit_company(self):
        # KLABIN (12653) -> KLBN11.SA (Unit)
        from src.companies.ticker_map import TICKER_MAP
        ticker = TICKER_MAP.get(12653)
        assert ticker == "KLBN11.SA"

    def test_no_ticker_company(self):
        # AEGEA (23396) -> None (not in TICKER_MAP)
        from src.companies.ticker_map import TICKER_MAP
        ticker = TICKER_MAP.get(23396)
        assert ticker is None

    def test_stale_or_historical_ticker(self):
        # EDP Brasil (3697) was delisted but retains its historical symbol ENBR3.SA
        from src.companies.ticker_map import TICKER_MAP
        ticker = TICKER_MAP.get(3697)
        assert ticker == "ENBR3.SA"


# ──────────────────────────────────────────────────────────────────────────────
# 5. Database Lifecycle, Migrations, and Offline Safety Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestDatabaseLifecycleAndMigrations:
    def test_fresh_profile_init(self, tmp_path):
        db_path = tmp_path / "cvm_financials.db"
        engine = create_engine(f"sqlite:///{db_path}")
        init_db_tables(engine)
        
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
            table_names = [t[0] for t in tables]
            assert "companies" in table_names
            assert "financial_reports" in table_names
            
            # Check GICS and missing columns
            cols = conn.execute(text("PRAGMA table_info(companies)")).fetchall()
            col_names = [c[1] for c in cols]
            assert "cnpj" in col_names
            assert "ticker_b3" in col_names
            assert "setor_analitico" in col_names
            assert "updated_at" in col_names
            
            count = conn.execute(text("SELECT COUNT(*) FROM companies")).scalar()
            assert count == 0

    def test_existing_profile_upgrade_and_backfill(self, tmp_path):
        db_path = tmp_path / "cvm_financials.db"
        engine = create_engine(f"sqlite:///{db_path}")
        
        # Create outdated schema
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE companies (
                    cd_cvm INTEGER PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    cnpj TEXT
                )
            """))
            # Insert legacy records
            conn.execute(text("""
                INSERT INTO companies (cd_cvm, company_name, cnpj)
                VALUES (9512, 'PETROBRAS', '33.000.167/0001-01')
            """))
            conn.execute(text("""
                INSERT INTO companies (cd_cvm, company_name, cnpj)
                VALUES (5410, 'WEG', NULL)
            """))
            # Insert an invalid CNPJ
            conn.execute(text("""
                INSERT INTO companies (cd_cvm, company_name, cnpj)
                VALUES (99999, 'INVALID_CO', '12345_invalid')
            """))
            # Insert a company with pre-existing valid custom ticker to verify preservation
            conn.execute(text("""
                INSERT INTO companies (cd_cvm, company_name, cnpj)
                VALUES (1023, 'BANCO DO BRASIL', '00.000.000/0001-91')
            """))
            
        # Run schema migration & local backfill
        init_db_tables(engine)
        
        with engine.connect() as conn:
            # Check columns added
            cols = conn.execute(text("PRAGMA table_info(companies)")).fetchall()
            col_names = [c[1] for c in cols]
            assert "ticker_b3" in col_names
            assert "setor_analitico" in col_names
            
            # Verify PETROBRAS normalized CNPJ and backfilled ticker
            petr = conn.execute(
                text("SELECT cnpj, ticker_b3 FROM companies WHERE cd_cvm = 9512")
            ).fetchone()
            assert petr[0] == "33000167000101"  # Normalized to raw 14 digits
            assert petr[1] == "PETR4"
            
            # Verify WEG backfilled ticker
            weg = conn.execute(
                text("SELECT cnpj, ticker_b3 FROM companies WHERE cd_cvm = 5410")
            ).fetchone()
            assert weg[0] == "84429695000111"  # Backfilled from resolver
            assert weg[1] == "WEGE3"
            
            # Verify invalid CNPJ rejected/kept untouched
            inv = conn.execute(
                text("SELECT cnpj, ticker_b3 FROM companies WHERE cd_cvm = 99999")
            ).fetchone()
            assert inv[0] == "12345_invalid"  # Kept untouched if invalid
            
            # Verify Banco do Brasil
            bb = conn.execute(
                text("SELECT cnpj, ticker_b3 FROM companies WHERE cd_cvm = 1023")
            ).fetchone()
            assert bb[0] == "00000000000191"  # Normalized with leading zeros
            assert bb[1] == "BBAS3"
            
        # Idempotence test (run init_db_tables again, nothing should break or change)
        init_db_tables(engine)
        with engine.connect() as conn:
            petr = conn.execute(
                text("SELECT cnpj, ticker_b3 FROM companies WHERE cd_cvm = 9512")
            ).fetchone()
            assert petr[0] == "33000167000101"
            assert petr[1] == "PETR4"

    def test_offline_safety(self, tmp_path):
        db_path = tmp_path / "cvm_financials.db"
        engine = create_engine(f"sqlite:///{db_path}")
        
        # Inject network failure endpoint in settings
        import os
        os.environ["CVM_BASE_URL"] = "http://127.0.0.1:9999/invalid"
        try:
            init_db_tables(engine)
        finally:
            os.environ.pop("CVM_BASE_URL", None)

    def test_required_column_migration_failure_propagation(self, tmp_path):
        db_path = tmp_path / "cvm_financials.db"
        engine = create_engine(f"sqlite:///{db_path}")
        
        # Create outdated schema
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE companies (
                    cd_cvm INTEGER PRIMARY KEY,
                    company_name TEXT NOT NULL
                )
            """))
            
        from sqlalchemy.engine import Connection
        real_execute = Connection.execute
        
        def mock_execute(self, statement, *args, **kwargs):
            stmt_str = str(statement)
            if "ALTER TABLE companies ADD COLUMN" in stmt_str:
                from sqlalchemy.exc import OperationalError
                # Raise a standard SQLAlchemy OperationalError
                raise OperationalError("mock_alter_failure", {}, Exception("Mock DB Failure"))
            return real_execute(self, statement, *args, **kwargs)
            
        with patch.object(Connection, "execute", mock_execute):
            from sqlalchemy.exc import OperationalError
            with pytest.raises(OperationalError) as exc_info:
                init_db_tables(engine)
            assert "mock_alter_failure" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────────────
# 6. Metadata Refresh Gating, TTL, and Lock Gating Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestRefreshGatingAndLocking:
    @pytest.fixture
    def setup_temp_db(self, tmp_path):
        db_dir = tmp_path / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "cvm_financials.db"
        engine = create_engine(f"sqlite:///{db_path}")
        init_db_tables(engine)
        return db_path, engine

    @patch("desktop.app._user_data_root")
    @patch("desktop.lockfile.get_status")
    @patch("sqlite3.connect")
    def test_refresh_skips_when_lock_not_owned(self, mock_connect, mock_get_status, mock_user_data_root, tmp_path):
        mock_user_data_root.return_value = tmp_path
        # Lock status says locked by other
        mock_get_status.return_value = {"status": "locked_by_other", "pid": 1234}
        
        from desktop.app import _background_remote_metadata_refresh
        _background_remote_metadata_refresh()
        
        # SQLite connect should not be called since we exit immediately on lock check
        mock_connect.assert_not_called()

    @patch("desktop.app._user_data_root")
    @patch("desktop.lockfile.get_status")
    @patch("src.companies.catalog.CompanyCatalogService.list_entries")
    def test_refresh_skips_when_no_companies_require_enrichment(self, mock_list_entries, mock_get_status, mock_user_data_root, setup_temp_db):
        db_path, engine = setup_temp_db
        mock_user_data_root.return_value = db_path.parent.parent
        mock_get_status.return_value = {"status": "locked_by_self"}
        
        # Seed database with a company that already has a CNPJ (no enrichment needed)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO companies (cd_cvm, company_name, cnpj, ticker_b3, updated_at) "
                    "VALUES (9512, 'PETROBRAS', '33000167000101', 'PETR4', '2026-06-09T20:00:00')"
                )
            )
            
        from desktop.app import _background_remote_metadata_refresh
        
        # Patch time.sleep to run quickly
        with patch("time.sleep"):
            _background_remote_metadata_refresh()
            
        # Catalog fetch list_entries should NOT be called since no companies are missing CNPJs
        mock_list_entries.assert_not_called()

    @patch("desktop.app._user_data_root")
    @patch("desktop.lockfile.get_status")
    @patch("src.companies.catalog.CompanyCatalogService.list_entries")
    def test_refresh_skips_when_ttl_is_still_valid(self, mock_list_entries, mock_get_status, mock_user_data_root, setup_temp_db):
        db_path, engine = setup_temp_db
        mock_user_data_root.return_value = db_path.parent.parent
        mock_get_status.return_value = {"status": "locked_by_self"}
        
        # Seed database with a company missing CNPJ
        # Seed app_settings with a recent successful refresh timestamp (e.g. 1 hour ago)
        import time
        import json
        recent_ts = int(time.time()) - 3600
        
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO companies (cd_cvm, company_name, cnpj, ticker_b3, updated_at) VALUES (9512, 'PETROBRAS', NULL, NULL, '')"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"))
            conn.execute(
                text("INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES ('metadata_last_successful_refresh', :val, :upd)"),
                {"val": json.dumps(recent_ts), "upd": "2026-06-09T20:00:00"}
            )
            
        from desktop.app import _background_remote_metadata_refresh
        with patch("time.sleep"):
            _background_remote_metadata_refresh()
            
        # Catalog fetch should NOT be called since TTL is still valid (7 days not expired)
        mock_list_entries.assert_not_called()

    @patch("desktop.app._user_data_root")
    @patch("desktop.lockfile.get_status")
    @patch("src.companies.catalog.CompanyCatalogService.list_entries")
    @patch("src.companies.catalog.CompanyCatalogService.lookup_company")
    def test_refresh_updates_timestamp_on_success(self, mock_lookup, mock_list_entries, mock_get_status, mock_user_data_root, setup_temp_db):
        db_path, engine = setup_temp_db
        mock_user_data_root.return_value = db_path.parent.parent
        mock_get_status.return_value = {"status": "locked_by_self"}
        
        from src.companies.catalog import CompanyCatalogEntry
        mock_list_entries.return_value = []
        mock_lookup.return_value = CompanyCatalogEntry(
            cd_cvm=9512,
            company_name="PETROBRAS",
            nome_comercial="PETROBRAS",
            cnpj="33000167000101",
            setor_cvm="Petróleo",
            ticker_b3="PETR4",
            is_active=True
        )
        
        # Seed company missing CNPJ
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO companies (cd_cvm, company_name, cnpj, ticker_b3, updated_at) VALUES (9512, 'PETROBRAS', NULL, NULL, '')"))
            
        from desktop.app import _background_remote_metadata_refresh
        with patch("time.sleep"):
            _background_remote_metadata_refresh()
            
        # Verify database has normalized CNPJ and updated app_settings
        with engine.connect() as conn:
            row = conn.execute(text("SELECT cnpj, ticker_b3 FROM companies WHERE cd_cvm = 9512")).fetchone()
            assert row[0] == "33000167000101"
            
            sett = conn.execute(text("SELECT value FROM app_settings WHERE key = 'metadata_last_successful_refresh'")).fetchone()
            assert sett is not None  # Successfully persisted refresh timestamp!

    @patch("desktop.app._user_data_root")
    @patch("desktop.lockfile.get_status")
    @patch("src.companies.catalog.CompanyCatalogService.list_entries")
    def test_refresh_does_not_update_timestamp_on_failure(self, mock_list_entries, mock_get_status, mock_user_data_root, setup_temp_db):
        db_path, engine = setup_temp_db
        mock_user_data_root.return_value = db_path.parent.parent
        mock_get_status.return_value = {"status": "locked_by_self"}
        
        # Mock network failure
        from src.companies.catalog import CompanyCatalogUnavailableError
        mock_list_entries.side_effect = CompanyCatalogUnavailableError("Mock Offline Error")
        
        # Seed company missing CNPJ
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO companies (cd_cvm, company_name, cnpj, ticker_b3, updated_at) VALUES (9512, 'PETROBRAS', NULL, NULL, '')"))
            
        from desktop.app import _background_remote_metadata_refresh
        with patch("time.sleep"):
            _background_remote_metadata_refresh()
            
        # Verify app_settings does NOT contain the successful refresh key because it failed
        with engine.connect() as conn:
            sett = conn.execute(text("SELECT value FROM app_settings WHERE key = 'metadata_last_successful_refresh'")).fetchone()
            assert sett is None

    @patch("desktop.app._user_data_root")
    @patch("desktop.lockfile.get_status")
    def test_concurrent_refresh_in_same_process_prevented(self, mock_get_status, mock_user_data_root, tmp_path):
        # We test that when _refresh_in_progress is True, a second call returns immediately
        import desktop.app
        desktop.app._refresh_in_progress = True
        
        try:
            mock_get_status.return_value = {"status": "locked_by_self"}
            mock_user_data_root.return_value = tmp_path
            
            with patch("sqlite3.connect") as mock_connect:
                from desktop.app import _background_remote_metadata_refresh
                _background_remote_metadata_refresh()
                # Should return immediately and not check lock or connect to DB
                mock_connect.assert_not_called()
        finally:
            desktop.app._refresh_in_progress = False



