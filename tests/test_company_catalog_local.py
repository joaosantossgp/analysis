import json
from types import SimpleNamespace

import pytest
import requests

from src.companies.catalog import CompanyCatalogService, CompanyCatalogUnavailableError


CSV = (
    "CD_CVM;DENOM_SOCIAL;DENOM_COMERC;CNPJ_CIA;SETOR_ATIV;SIT\n"
    "9512;PETROLEO BRASILEIRO;PETROBRAS;33.000.167/0001-01;Petróleo;ATIVO\n"
).encode("latin1")


def test_cold_catalog_reads_never_request_network(tmp_path, monkeypatch):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise requests.ConnectionError("offline")
    monkeypatch.setattr("src.companies.catalog.requests.get", forbidden)
    catalog = CompanyCatalogService(timeout=1, snapshot_path=tmp_path / "catalog.json")
    for read in (lambda: catalog.lookup_company(9512), catalog.list_entries,
                 lambda: catalog.search_companies(q="PETRO", limit=5)):
        with pytest.raises(CompanyCatalogUnavailableError, match="local catalog"):
            read()
    assert calls == []


def test_explicit_refresh_survives_restart_and_expired_ttl(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    calls = []
    def fetch(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(content=CSV, raise_for_status=lambda: None)
    monkeypatch.setattr("src.companies.catalog.requests.get", fetch)
    catalog = CompanyCatalogService(timeout=1, snapshot_path=path, ttl_seconds=0)
    catalog.refresh()
    evidence = json.loads(path.read_text(encoding="utf-8"))
    assert evidence["source_url"].startswith("https://")
    assert evidence["downloaded_at"]
    fresh = CompanyCatalogService(timeout=1, snapshot_path=path, ttl_seconds=0)
    assert fresh.lookup_company(9512).company_name == "PETROLEO BRASILEIRO"
    assert len(fresh.list_entries()) == 1
    assert fresh.search_companies(q="PETRO", limit=5)[0].cd_cvm == 9512
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["network", "invalid", "empty"])
def test_failed_refresh_preserves_last_snapshot(tmp_path, monkeypatch, failure):
    path = tmp_path / "catalog.json"
    monkeypatch.setattr("src.companies.catalog.requests.get",
                        lambda *a, **k: SimpleNamespace(content=CSV, raise_for_status=lambda: None))
    catalog = CompanyCatalogService(timeout=1, snapshot_path=path)
    catalog.refresh()
    previous = path.read_bytes()
    def failed(*args, **kwargs):
        if failure == "network":
            raise requests.ConnectionError("offline")
        content = b"not a catalog" if failure == "invalid" else CSV.splitlines()[0] + b"\n"
        return SimpleNamespace(content=content, raise_for_status=lambda: None)
    monkeypatch.setattr("src.companies.catalog.requests.get", failed)
    with pytest.raises(CompanyCatalogUnavailableError):
        catalog.refresh()
    assert path.read_bytes() == previous
    assert catalog.lookup_company(9512) is not None


def test_corrupt_snapshot_is_explicit_and_never_fetches(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    path.write_text("{}", encoding="utf-8")
    def forbidden(*args, **kwargs):
        pytest.fail("A local read must not request the network")
    monkeypatch.setattr("src.companies.catalog.requests.get", forbidden)
    with pytest.raises(CompanyCatalogUnavailableError, match="local catalog"):
        CompanyCatalogService(timeout=1, snapshot_path=path).list_entries()


def test_coverage_universe_read_never_fetches(tmp_path, monkeypatch):
    from desktop.services import IntelligentSelectorService
    from src.platform.settings import build_settings
    service = IntelligentSelectorService(settings=build_settings(project_root=tmp_path))
    monkeypatch.setattr(service, "_load_db_company_rows", lambda: [])
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise requests.ConnectionError("offline")
    monkeypatch.setattr("requests.get", forbidden)
    assert service._load_active_universe() == []
    assert calls == []


def test_setup_refreshes_catalog_only_when_explicit(tmp_path):
    from src.companies.universe import CompanyUniverseService
    from src.platform.settings import build_settings
    events = []
    read_service = SimpleNamespace(
        engine=object(),
        company_catalog=SimpleNamespace(refresh=lambda: events.append("refresh")),
        invalidate_read_caches=lambda: events.append("invalidate"),
    )
    service = CompanyUniverseService(
        settings=build_settings(project_root=tmp_path), read_service=read_service,
    )
    service.provider = SimpleNamespace(get_company_universe_by_preset=lambda preset: preset)
    assert service.get_company_universe_by_preset("all") == "all"
    assert events == []
    assert service.get_company_universe_by_preset("all", refresh_catalog=True) == "all"
    assert events == ["refresh", "invalidate"]


def test_universe_preview_does_not_request_catalog_refresh():
    from desktop.bridge import CVMBridge
    calls = []
    def select(preset, *, refresh_catalog=False):
        calls.append(refresh_catalog)
        return SimpleNamespace(to_dict=lambda: {"company_ids": []})
    bridge = CVMBridge()
    bridge._onboarding_service = SimpleNamespace(get_company_universe_by_preset=select)
    bridge._resolve_data_update_settings = lambda: {"universe_preset": "all"}
    assert bridge.get_company_universe_selection({"preset": "all"}) == {"company_ids": []}
    assert calls == [False]


def test_explicit_company_refresh_can_bootstrap_missing_catalog():
    from src.financials.read_service import CVMReadService
    events = []
    def lookup(code):
        if not events:
            raise CompanyCatalogUnavailableError("missing local catalog")
        return None
    service = object.__new__(CVMReadService)
    service.query_layer = SimpleNamespace(get_company_info=lambda code: None)
    service._company_catalog = SimpleNamespace(
        lookup_company=lookup, refresh=lambda: events.append("refresh"),
    )
    assert service._ensure_company_catalog_metadata(999999) is False
    assert events == ["refresh"]
