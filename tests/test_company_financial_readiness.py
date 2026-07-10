from __future__ import annotations

import sqlite3

from desktop.bridge import CVMBridge
from src.financials.read_service import CVMReadService
from src.platform.settings import build_settings


class _ExplodingCatalog:
    def lookup_company(self, cd_cvm: int):
        raise AssertionError("financial readiness must not use a catalog lookup")


def _seed_financial_readiness_service(tmp_path):
    settings = build_settings(project_root=tmp_path)
    db_path = settings.paths.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE companies (
                cd_cvm INTEGER PRIMARY KEY,
                company_name TEXT NOT NULL,
                nome_comercial TEXT,
                cnpj TEXT,
                setor_cvm TEXT,
                setor_analitico TEXT,
                company_type TEXT,
                ticker_b3 TEXT,
                is_active INTEGER,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE financial_reports (
                CD_CVM INTEGER,
                STATEMENT_TYPE TEXT,
                REPORT_YEAR INTEGER,
                PERIOD_LABEL TEXT,
                QA_CONFLICT INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE company_refresh_status (
                cd_cvm INTEGER PRIMARY KEY,
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_status TEXT,
                last_error TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO companies (
                cd_cvm, company_name, company_type, is_active, updated_at
            ) VALUES (?, ?, 'comercial', 1, ?)
            """,
            [
                (9512, "READY S.A.", "2026-06-10T09:00:00Z"),
                (4170, "PARTIAL S.A.", "2026-06-10T09:00:00Z"),
                (11223, "MISSING S.A.", "2026-06-10T09:00:00Z"),
                (9999, "STALE S.A.", "2026-06-10T09:00:00Z"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO financial_reports (
                CD_CVM, STATEMENT_TYPE, REPORT_YEAR, PERIOD_LABEL, QA_CONFLICT
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                *(
                    (9512, statement, 2025, "2025", 0)
                    for statement in ("BPA", "BPP", "DRE", "DFC")
                ),
                (4170, "DRE", 2025, "2025", 0),
                *(
                    (9999, statement, 2025, "2025", 0)
                    for statement in ("BPA", "BPP", "DRE", "DFC")
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO company_refresh_status (
                cd_cvm, last_attempt_at, last_success_at, last_status, last_error
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (9512, "2026-06-12T10:00:00Z", "2026-06-12T10:05:00Z", "success", None),
                (11223, "2026-06-12T10:00:00Z", None, "error", "CVM download failed"),
                (9999, "2026-06-12T10:00:00Z", "2026-06-12T10:05:00Z", "no_data", None),
            ],
        )

    service = CVMReadService(settings=settings)
    service._company_catalog = _ExplodingCatalog()
    return service


def test_financial_readiness_reports_local_financial_states_without_catalog_lookup(tmp_path):
    service = _seed_financial_readiness_service(tmp_path)

    ready = service.get_company_financial_readiness(9512)
    partial = service.get_company_financial_readiness(4170)
    missing = service.get_company_financial_readiness(11223)
    stale = service.get_company_financial_readiness(9999)

    assert ready.source_class == "official_reported"
    assert ready.source_label == "CVM DFP/ITR filings"
    assert ready.availability_state == "ready"
    assert ready.freshness_state == "fresh"
    assert ready.refresh_state == "successful"
    assert ready.financial_export_eligible is True
    assert ready.available_periods[0].period_label == "2025"
    assert ready.latest_local_evidence_at == "2026-06-12T10:05:00Z"

    assert partial.availability_state == "partial"
    assert partial.financial_export_eligible is False
    assert partial.available_periods == ()

    assert missing.availability_state == "missing"
    assert missing.refresh_state == "failed"
    assert missing.last_refresh_error == "CVM download failed"

    assert stale.availability_state == "ready"
    assert stale.freshness_state == "stale"
    assert stale.refresh_state == "no_data"


def test_financial_readiness_bridge_is_additive_and_reports_refresh_availability(tmp_path):
    bridge = CVMBridge()
    bridge._service = _seed_financial_readiness_service(tmp_path)

    payload = bridge.get_company_financial_readiness({"cd_cvm": 9512})

    assert payload["cd_cvm"] == 9512
    assert payload["availability_state"] == "ready"
    assert payload["refresh_available"] is True
    assert payload["financial_export_eligible"] is True
