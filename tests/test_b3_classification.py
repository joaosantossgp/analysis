"""B3 sector source: explicit refresh, offline reads, visible failures (#523)."""
import sqlite3

import pytest

from desktop.bridge import CVMBridge
from src.companies.b3_classification import (
    b3_refresh_status,
    parse_industry_classification,
    refresh_b3_classification,
)
from test_company_market_cap_sort import _company, _seed_db

PETRO = "Petróleo. Gás e Biocombustíveis / Petróleo. Gás e Biocombustíveis / Exploração. Refino e Distribuição"


def _fetcher(responses):
    calls = []

    def fetch(url):
        calls.append(url)
        cd = next(code for code in responses if _code_in(url, code))
        value = responses[cd]
        if isinstance(value, Exception):
            raise value
        return value

    return fetch, calls


def _code_in(url, code):
    import base64, json
    token = url.rsplit("/", 1)[1]
    return json.loads(base64.b64decode(token))["codeCVM"] == str(code)


@pytest.fixture
def svc(tmp_path):
    return _seed_db(tmp_path, [_company(9512, "Petrobras"), _company(20, "Not on B3"), _company(30, "Flaky")])


def test_parse_keeps_b3_labels_as_published():
    assert parse_industry_classification(PETRO) == (
        "Petróleo. Gás e Biocombustíveis", "Petróleo. Gás e Biocombustíveis", "Exploração. Refino e Distribuição")
    assert parse_industry_classification("Financeiro") == ("Financeiro", None, None)
    assert parse_industry_classification(None) == (None, None, None)


def test_refresh_stores_labels_logs_failures_and_reads_offline(svc):
    fetch, calls = _fetcher({9512: {"industryClassification": PETRO}, 20: {}, 30: ConnectionError("offline")})
    summary = refresh_b3_classification(svc.engine, fetch=fetch, delay_seconds=0)
    assert (summary["requested"], summary["succeeded"], summary["not_listed"], summary["failed"]) == (3, 1, 1, 1)
    assert "30: offline" in summary["errors"][0]
    assert len(calls) == 3

    # Normal reads never call the network.
    info = svc.get_company_info(9512)
    assert info.b3_classification["b3_segment"] == "Exploração. Refino e Distribuição"
    assert info.b3_classification["source_url"].startswith("https://sistemaswebb3-listados.b3.com.br/")
    assert info.b3_classification["stale"] is False
    assert svc.get_company_info(20).b3_classification is None

    status = b3_refresh_status(svc.engine)
    assert status["stored_companies"] == 1
    assert status["last_run"]["failed"] == 1 and status["stale"] is False


def test_failed_refresh_keeps_previous_labels(svc):
    fetch, _ = _fetcher({9512: {"industryClassification": PETRO}, 20: {}, 30: {}})
    refresh_b3_classification(svc.engine, fetch=fetch, delay_seconds=0)
    broken, _ = _fetcher({9512: ConnectionError("offline"), 20: {}, 30: {}})
    summary = refresh_b3_classification(svc.engine, fetch=broken, delay_seconds=0)
    assert summary["failed"] == 1
    assert svc.get_company_info(9512).b3_classification["b3_sector"] == "Petróleo. Gás e Biocombustíveis"


def test_status_before_any_refresh_is_stale_and_bridge_reads_it(svc):
    bridge = CVMBridge()
    bridge._service = svc
    status = bridge.get_b3_classification_status()
    assert status["ok"] and status["last_run"] is None and status["stale"] is True
    with sqlite3.connect(svc.settings.paths.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 3
