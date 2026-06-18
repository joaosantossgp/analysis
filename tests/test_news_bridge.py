from __future__ import annotations

import time
from typing import Any

from desktop.bridge_api.news import NewsBridgeMixin
from src.news.repository import NewsSource
from src.news.service import CollectionResult, FeedValidationResult
from src.news.sources import builtin_sources


EXPECTED_BUILTIN_SOURCE_IDS = [source.source_id for source in sorted(builtin_sources(), key=lambda item: (item.priority, item.name.lower()))]


class _FakeRepository:
    def __init__(self, rows: dict[str, dict[str, Any]] | None = None) -> None:
        self.rows = rows or {}
        self.article_params: dict[str, Any] | None = None
        self.run_limit: int | None = None
        self.enabled_updates: list[tuple[str, bool]] = []
        self.priority_updates: list[tuple[str, int]] = []
        self.fetch_state_updates: list[dict[str, Any]] = []
        self.article_state_updates: list[dict[str, Any]] = []
        self.classification_article_id: str | None = None
        self.overview_limit: int | None = None
        self.correction_params: dict[str, Any] | None = None
        self.company_scope_override_params: dict[str, Any] | None = None
        self.overview_company_scope_ids: set[int] | None = None
        self.retention_policy_params: dict[str, Any] | None = None
        self.cleanup_params: dict[str, Any] | None = None
        self.health_records: list[dict[str, Any]] = []
        self.company_scope_settings = {
            "settings_id": "default",
            "coverage_universe_id": None,
            "updated_at": None,
        }
        self.google_settings = {
            "settings_id": "default",
            "enabled": 0,
            "max_companies": 50,
            "priority": 140,
            "locale": "pt-BR",
            "country": "BR",
            "updated_at": None,
        }

    def register_source(self, source: NewsSource) -> None:
        self.rows.setdefault(
            source.source_id,
            {
                "source_id": source.source_id,
                "name": source.name,
                "source_type": source.source_type,
                "reliability_layer": source.reliability_layer,
                "feed_url": source.feed_url,
                "homepage_url": source.homepage_url,
                "enabled": 1 if source.enabled else 0,
                "priority": source.priority,
                "user_defined": 1 if source.user_defined else 0,
                "allow_content_storage": source.allow_content_storage,
            },
        )

    def upsert_source(self, source: NewsSource) -> None:
        self.rows[source.source_id] = {
            "source_id": source.source_id,
            "name": source.name,
            "source_type": source.source_type,
            "reliability_layer": source.reliability_layer,
            "feed_url": source.feed_url,
            "homepage_url": source.homepage_url,
            "enabled": 1 if source.enabled else 0,
            "priority": source.priority,
            "user_defined": 1 if source.user_defined else 0,
            "allow_content_storage": source.allow_content_storage,
        }

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        return self.rows.get(source_id)

    def list_sources(self) -> list[dict[str, Any]]:
        return list(self.rows.values())

    def list_enabled_sources(self) -> list[dict[str, Any]]:
        return sorted(
            [row for row in self.rows.values() if int(row.get("enabled", 1)) == 1],
            key=lambda row: (int(row.get("priority") or 100), str(row.get("name") or "").lower()),
        )

    def list_articles(self, **kwargs) -> dict[str, Any]:
        self.article_params = kwargs
        return {
            "items": [{"article_id": "art-1", "title": "News item"}],
            "count": 1,
            "total": 1,
            "limit": kwargs["limit"],
            "offset": kwargs["offset"],
        }

    def list_overview(self, *, limit_per_section: int = 6, company_scope_ids=None) -> dict[str, Any]:
        self.overview_limit = limit_per_section
        self.overview_company_scope_ids = company_scope_ids
        return {
            "sections": [
                {
                    "section_id": "top_market_news",
                    "title": "Top Market News",
                    "reason": "Highest ranked local articles.",
                    "items": [{"article_id": "art-1", "title": "News item"}],
                }
            ],
            "limit_per_section": limit_per_section,
        }

    def list_collection_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        self.run_limit = limit
        return [{"run_id": "run-1", "status": "success"}]

    def get_article_classification(self, article_id: str) -> dict[str, list[dict[str, Any]]]:
        self.classification_article_id = article_id
        return {
            "keywords": [{"keyword_rule_id": "kw_macro_selic", "matched_term": "Selic"}],
            "topics": [{"topic_id": "topic_macro_rates", "label": "Interest rates"}],
            "event_types": [],
        }

    def get_article_content(self, article_id: str):
        if article_id == "missing":
            return None
        return {
            "article_id": article_id,
            "title": "News item",
            "content_status": "full_text_available",
            "paywall_status": None,
            "available": True,
            "content_text": "Local article content",
            "content_format": "feed",
            "source_policy": "feed_content_allowed",
            "storage_bytes": 21,
            "extracted_at": "2026-06-16T10:00:00+00:00",
            "updated_at": "2026-06-16T10:00:00+00:00",
        }

    def set_source_enabled(self, *, source_id: str, enabled: bool) -> bool:
        self.enabled_updates.append((source_id, enabled))
        if source_id not in self.rows:
            return False
        self.rows[source_id]["enabled"] = 1 if enabled else 0
        return True

    def set_source_priority(self, *, source_id: str, priority: int) -> bool:
        self.priority_updates.append((source_id, priority))
        if source_id not in self.rows:
            return False
        self.rows[source_id]["priority"] = priority
        return True

    def update_source_fetch_state(self, **kwargs) -> None:
        self.fetch_state_updates.append(kwargs)

    def record_source_health(self, **kwargs) -> None:
        self.health_records.append(kwargs)

    def update_article_user_state(self, **kwargs):
        self.article_state_updates.append(kwargs)
        if kwargs["article_id"] == "missing":
            return None
        return {
            "article_id": kwargs["article_id"],
            "read": 1 if kwargs.get("read") else 0,
            "saved": 1 if kwargs.get("saved") else 0,
            "hidden": 1 if kwargs.get("hidden") else 0,
            "read_later": 1 if kwargs.get("read_later") else 0,
            "notes": kwargs.get("notes"),
        }

    def apply_classification_correction(self, **kwargs):
        self.correction_params = kwargs
        return {
            "status": "success",
            "correction_id": "corr-1",
            "article_id": kwargs["article_id"],
            "target_type": kwargs["target_type"],
            "target_id": kwargs["target_id"],
            "correction_action": kwargs["action"],
        }

    def list_company_scope_overrides(self):
        return [{"cd_cvm": 9512, "action": "include", "reason": "Manual"}]

    def set_company_scope_override(self, **kwargs):
        self.company_scope_override_params = kwargs
        return {"status": "success", "cd_cvm": kwargs["cd_cvm"], "action": kwargs["action"]}

    def get_company_scope_settings(self):
        return dict(self.company_scope_settings)

    def update_company_scope_settings(self, *, coverage_universe_id):
        self.company_scope_settings["coverage_universe_id"] = coverage_universe_id
        return dict(self.company_scope_settings)

    def get_content_storage_summary(self):
        return {
            "content_count": 2,
            "storage_bytes": 128,
            "saved_content_count": 1,
            "policy": {
                "policy_id": "default",
                "metadata_retention_days": 1825,
                "extracted_text_retention_days": 90,
                "total_storage_limit_mb": 512,
                "preserve_saved": 1,
                "preserve_official_documents": 1,
                "updated_at": None,
            },
        }

    def update_retention_policy(self, **kwargs):
        self.retention_policy_params = kwargs
        return {
            "policy_id": "default",
            "metadata_retention_days": kwargs.get("metadata_retention_days") or 1825,
            "extracted_text_retention_days": kwargs.get("extracted_text_retention_days") or 90,
            "total_storage_limit_mb": kwargs.get("total_storage_limit_mb") or 512,
            "preserve_saved": kwargs.get("preserve_saved"),
            "preserve_official_documents": kwargs.get("preserve_official_documents"),
            "updated_at": None,
        }

    def cleanup_extracted_content(self, **kwargs):
        self.cleanup_params = kwargs
        return {
            "status": "success",
            "dry_run": kwargs.get("dry_run", False),
            "deleted_content_count": 1,
            "freed_bytes": 128,
            "preserved_saved": True,
            "preserved_official_documents": True,
        }

    def get_google_company_feed_settings(self):
        return dict(self.google_settings)

    def update_google_company_feed_settings(self, **kwargs):
        for key, value in kwargs.items():
            if value is not None:
                self.google_settings[key] = 1 if key == "enabled" and value else 0 if key == "enabled" else value
        return dict(self.google_settings)

    def disable_google_company_sources(self) -> int:
        count = 0
        for source_id, row in self.rows.items():
            if source_id.startswith("google_company_") and int(row.get("enabled", 1)) == 1:
                row["enabled"] = 0
                count += 1
        return count


class _FakeNewsService:
    def __init__(
        self,
        validation: FeedValidationResult | None = None,
        *,
        fail_sources: set[str] | None = None,
    ) -> None:
        self.sources: list[str] = []
        self.validation = validation
        self.validated_urls: list[str] = []
        self.fail_sources = fail_sources or set()
        self.content_fetches: list[str] = []

    def collect_source(self, *, source: NewsSource, trigger: str = "manual") -> CollectionResult:
        self.sources.append(source.source_id)
        if source.source_id in self.fail_sources:
            raise RuntimeError(f"boom {source.source_id}")
        return CollectionResult(
            run_id=f"run-{source.source_id}",
            status="success",
            articles_seen=2,
            articles_inserted=1,
            articles_updated=1,
            error_count=0,
        )

    def validate_feed_url(self, feed_url: str) -> FeedValidationResult:
        self.validated_urls.append(feed_url)
        return self.validation or FeedValidationResult(
            status="success",
            feed_url=feed_url,
            title="Validated Feed",
            entry_count=1,
            http_status=200,
            final_url=feed_url,
            etag='"v1"',
            last_modified="Tue, 16 Jun 2026 10:00:00 GMT",
        )

    def fetch_article_content_on_demand(self, article_id: str):
        self.content_fetches.append(article_id)
        from src.news.service import ArticleContentBackfillResult

        return ArticleContentBackfillResult(
            status="success",
            limit=1,
            include_normal=True,
            candidate_count=1,
            attempted_count=1,
            stored_count=1,
            paywalled_count=0,
            failed_count=0,
            skipped_count=0,
        )


class _FakeNewsBridge(NewsBridgeMixin):
    def __init__(
        self,
        *,
        repository: _FakeRepository,
        service: _FakeNewsService,
        write_allowed: bool = True,
    ) -> None:
        self.repository = repository
        self.service = service
        self.write_allowed = write_allowed

    def _news_repository(self):
        return self.repository

    def _news_collection_service(self):
        return self.service

    def _news_company_scope(self, repository):
        return {
            "company_ids": {9512, 1234},
            "selected_preset": "top_200",
            "selected_coverage_universe_id": repository.get_company_scope_settings()["coverage_universe_id"],
            "selected_coverage_universe_name": "News Universe" if repository.get_company_scope_settings()["coverage_universe_id"] else None,
            "available_coverage_universes": [
                {"id": "u-news", "name": "News Universe", "status": "active", "company_count": 2}
            ],
            "coverage_companies": [{"cd_cvm": 9512}],
            "overrides": repository.list_company_scope_overrides(),
        }

    def _news_company_rows_by_id(self, company_ids):
        rows = {
            9512: {"cd_cvm": 9512, "company_name": "Petroleo Brasileiro S.A.", "ticker": "PETR4"},
            1234: {"cd_cvm": 1234, "company_name": "Banco Exemplo S.A.", "ticker": "BEXP3"},
        }
        return {cd_cvm: rows[cd_cvm] for cd_cvm in company_ids if cd_cvm in rows}

    def _news_coverage_universe_exists(self, universe_id: str) -> bool:
        return universe_id == "u-news"

    def _is_write_allowed(self) -> bool:
        return self.write_allowed

    def _write_blocked_response(self, op_name: str = "operation") -> dict:
        return {"status": "blocked", "error": op_name}

    def _sanitize_for_json(self, value):
        return value

    @staticmethod
    def _bounded_int(value, *, default: int, minimum: int = 1, maximum: int = 100) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(default)
        return max(int(minimum), min(int(maximum), parsed))


def _wait_for_refresh(bridge: _FakeNewsBridge) -> dict:
    deadline = time.time() + 2
    while time.time() < deadline:
        status = bridge.get_news_refresh_status({})
        if status["status"] != "running":
            return status
        time.sleep(0.01)
    raise AssertionError("news refresh did not finish")


def test_news_bridge_manual_refresh_collects_enabled_builtin_sources():
    service = _FakeNewsService()
    bridge = _FakeNewsBridge(repository=_FakeRepository(), service=service)

    result = bridge.refresh_news_sources({})
    status = _wait_for_refresh(bridge)

    assert result["status"] == "started"
    assert status["status"] == "success"
    assert status["source_count"] == len(EXPECTED_BUILTIN_SOURCE_IDS)
    assert status["completed_sources"] == len(EXPECTED_BUILTIN_SOURCE_IDS)
    assert status["articles_seen"] == 2 * len(EXPECTED_BUILTIN_SOURCE_IDS)
    assert status["articles_inserted"] == len(EXPECTED_BUILTIN_SOURCE_IDS)
    assert status["articles_updated"] == len(EXPECTED_BUILTIN_SOURCE_IDS)
    assert service.sources == EXPECTED_BUILTIN_SOURCE_IDS


def test_news_bridge_manual_refresh_isolates_unexpected_source_failure():
    repository = _FakeRepository()
    service = _FakeNewsService(fail_sources={"bcb-rss"})
    bridge = _FakeNewsBridge(repository=repository, service=service)

    result = bridge.refresh_news_sources({})
    status = _wait_for_refresh(bridge)

    assert result["status"] == "started"
    assert status["status"] == "error"
    assert status["source_count"] == len(EXPECTED_BUILTIN_SOURCE_IDS)
    assert status["completed_sources"] == len(EXPECTED_BUILTIN_SOURCE_IDS)
    assert status["articles_inserted"] == len(EXPECTED_BUILTIN_SOURCE_IDS) - 1
    assert status["error_count"] == 1
    assert [source["source_id"] for source in status["sources"]] == EXPECTED_BUILTIN_SOURCE_IDS
    assert next(source for source in status["sources"] if source["source_id"] == "bcb-rss")["status"] == "error"
    assert service.sources == EXPECTED_BUILTIN_SOURCE_IDS
    assert repository.health_records == [
        {"source_id": "bcb-rss", "status": "error", "error": "boom bcb-rss"}
    ]


def test_news_bridge_preserves_disabled_source_choice():
    rows = {
        "bcb-rss": {
            "source_id": "bcb-rss",
            "name": "Banco Central do Brasil",
            "source_type": "official",
            "reliability_layer": "official",
            "feed_url": "https://www.bcb.gov.br/acessoinformacao/rss",
            "homepage_url": "https://www.bcb.gov.br/",
            "enabled": 0,
            "priority": 1,
            "user_defined": 0,
        }
    }
    service = _FakeNewsService()
    bridge = _FakeNewsBridge(repository=_FakeRepository(rows), service=service)

    bridge.refresh_news_sources({})
    status = _wait_for_refresh(bridge)

    assert status["status"] == "success"
    assert status["source_count"] == len(EXPECTED_BUILTIN_SOURCE_IDS) - 1
    assert service.sources == [source_id for source_id in EXPECTED_BUILTIN_SOURCE_IDS if source_id != "bcb-rss"]


def test_news_bridge_refresh_collects_enabled_custom_sources():
    rows = {
        "user_custom": {
            "source_id": "user_custom",
            "name": "Custom Feed",
            "source_type": "user_provided_rss",
            "reliability_layer": "user_provided",
            "feed_url": "https://example.com/feed.xml",
            "homepage_url": None,
            "enabled": 1,
            "priority": 80,
            "user_defined": 1,
        }
    }
    service = _FakeNewsService()
    bridge = _FakeNewsBridge(repository=_FakeRepository(rows), service=service)

    bridge.refresh_news_sources({})
    status = _wait_for_refresh(bridge)

    assert status["status"] == "success"
    assert "user_custom" in service.sources
    assert status["source_count"] == len(EXPECTED_BUILTIN_SOURCE_IDS) + 1


def test_news_bridge_google_company_feed_settings_generate_and_disable_sources():
    repository = _FakeRepository()
    service = _FakeNewsService()
    bridge = _FakeNewsBridge(repository=repository, service=service)

    saved = bridge.save_news_google_company_feed_settings({
        "enabled": True,
        "max_companies": 2,
        "priority": 140,
        "locale": "pt-BR",
        "country": "BR",
    })
    sources = bridge.get_news_sources({})
    disabled = bridge.save_news_google_company_feed_settings({"enabled": False})

    google_sources = [row for row in sources["items"] if row["source_id"].startswith("google_company_")]
    assert saved["status"] == "success"
    assert saved["settings"]["generated_count"] == 2
    assert len(google_sources) == 2
    assert all("news.google.com/rss/search" in row["feed_url"] for row in google_sources)
    assert all(row["allow_content_storage"] is True for row in google_sources)
    assert disabled["settings"]["disabled_count"] == 2


def test_news_bridge_blocks_manual_refresh_when_writes_are_not_allowed():
    bridge = _FakeNewsBridge(
        repository=_FakeRepository(),
        service=_FakeNewsService(),
        write_allowed=False,
    )

    result = bridge.refresh_news_sources({})

    assert result == {"status": "blocked", "error": "refresh_news_sources"}


def test_news_bridge_allows_news_refresh_in_dev_release_data_mode(monkeypatch):
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.delenv("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", raising=False)
    monkeypatch.delenv("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", raising=False)
    service = _FakeNewsService()
    bridge = _FakeNewsBridge(
        repository=_FakeRepository(),
        service=service,
        write_allowed=False,
    )

    result = bridge.refresh_news_sources({})
    status = _wait_for_refresh(bridge)

    assert result["status"] == "started"
    assert status["status"] == "success"
    assert service.sources == EXPECTED_BUILTIN_SOURCE_IDS


def test_news_bridge_blocks_news_refresh_under_concurrent_lock(monkeypatch):
    monkeypatch.setenv("CVMANALYTICS_USE_RELEASE_DATA", "1")
    monkeypatch.delenv("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", raising=False)
    monkeypatch.setenv("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", "1")
    bridge = _FakeNewsBridge(
        repository=_FakeRepository(),
        service=_FakeNewsService(),
        write_allowed=False,
    )

    result = bridge.refresh_news_sources({})

    assert result == {"status": "blocked", "error": "refresh_news_sources"}


def test_news_bridge_rejects_duplicate_running_refresh():
    bridge = _FakeNewsBridge(repository=_FakeRepository(), service=_FakeNewsService())
    bridge._news_refresh_state = {"status": "running"}

    result = bridge.refresh_news_sources({})

    assert result == {"status": "already_running", "error": None}


def test_news_bridge_returns_sources_with_health_payload():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    result = bridge.get_news_sources({})

    assert result["count"] == len(EXPECTED_BUILTIN_SOURCE_IDS)
    assert [item["source_id"] for item in result["items"]] == EXPECTED_BUILTIN_SOURCE_IDS


def test_news_bridge_returns_articles_with_bounded_params():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    result = bridge.get_news_articles({
        "limit": 999,
        "offset": -20,
        "source_id": "bcb-rss",
        "include_hidden": True,
    })

    assert result["count"] == 1
    assert result["limit"] == 200
    assert result["offset"] == 0
    assert repository.article_params == {
        "limit": 200,
        "offset": 0,
        "source_id": "bcb-rss",
        "include_hidden": True,
        "order": "latest",
    }


def test_news_bridge_passes_top_news_order():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    result = bridge.get_news_articles({"order": "top"})
    top_params = dict(repository.article_params)
    fallback = bridge.get_news_articles({"order": "unexpected"})
    fallback_params = dict(repository.article_params)

    assert result["count"] == 1
    assert top_params["order"] == "top"
    assert fallback["count"] == 1
    assert fallback_params["order"] == "latest"


def test_news_bridge_returns_overview_with_bounded_limit():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    result = bridge.get_news_overview({"limit_per_section": 999})

    assert result["sections"][0]["section_id"] == "top_market_news"
    assert result["limit_per_section"] == 20
    assert repository.overview_limit == 20
    assert repository.overview_company_scope_ids == {9512, 1234}


def test_news_bridge_returns_and_updates_company_scope_overrides():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    scope = bridge.get_news_company_scope({})
    updated = bridge.set_news_company_scope_override({
        "cd_cvm": 9512,
        "action": "exclude",
        "reason": "Not relevant for News",
    })

    assert scope["selected_preset"] == "top_200"
    assert scope["coverage_count"] == 1
    assert scope["included_count"] == 2
    assert scope["overrides"][0]["action"] == "include"
    assert updated == {"status": "success", "cd_cvm": 9512, "action": "exclude"}
    assert repository.company_scope_override_params == {
        "cd_cvm": 9512,
        "action": "exclude",
        "reason": "Not relevant for News",
    }


def test_news_bridge_selects_news_specific_coverage_universe():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    selected = bridge.set_news_company_scope_universe({"coverage_universe_id": "u-news"})
    missing = bridge.set_news_company_scope_universe({"coverage_universe_id": "missing"})
    cleared = bridge.set_news_company_scope_universe({"coverage_universe_id": None})

    assert selected["status"] == "success"
    assert selected["selected_coverage_universe_id"] == "u-news"
    assert selected["selected_coverage_universe_name"] == "News Universe"
    assert missing["status"] == "not_found"
    assert cleared["status"] == "success"
    assert cleared["selected_coverage_universe_id"] is None


def test_news_bridge_retention_policy_and_cleanup():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    status = bridge.get_news_retention_status({})
    saved = bridge.save_news_retention_policy({
        "extracted_text_retention_days": 45,
        "total_storage_limit_mb": 256,
        "preserve_saved": True,
        "preserve_official_documents": True,
    })
    cleanup = bridge.cleanup_news_extracted_content({"dry_run": True})

    assert status["content_count"] == 2
    assert status["saved_content_count"] == 1
    assert saved["status"] == "success"
    assert repository.retention_policy_params == {
        "metadata_retention_days": None,
        "extracted_text_retention_days": 45,
        "total_storage_limit_mb": 256,
        "preserve_saved": True,
        "preserve_official_documents": True,
    }
    assert cleanup["dry_run"] is True
    assert cleanup["deleted_content_count"] == 1
    assert repository.cleanup_params == {"dry_run": True}


def test_news_bridge_returns_article_classification():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    result = bridge.get_news_article_classification({"article_id": "art-1"})
    missing = bridge.get_news_article_classification({})

    assert result["keywords"][0]["keyword_rule_id"] == "kw_macro_selic"
    assert result["topics"][0]["topic_id"] == "topic_macro_rates"
    assert repository.classification_article_id == "art-1"
    assert missing["error"] == "article_id is required"


def test_news_bridge_returns_article_content_without_fetching_network():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    result = bridge.get_news_article_content({"article_id": "art-1"})
    missing = bridge.get_news_article_content({"article_id": "missing"})
    invalid = bridge.get_news_article_content({})

    assert result["available"] is True
    assert result["content_text"] == "Local article content"
    assert missing["available"] is False
    assert "not found" in missing["error"]
    assert invalid["error"] == "article_id is required"


def test_news_bridge_fetches_article_content_on_demand_when_local_text_is_missing():
    class _OnDemandRepository(_FakeRepository):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def get_article_content(self, article_id: str):
            self.calls += 1
            if self.calls == 1:
                return {
                    "article_id": article_id,
                    "title": "News item",
                    "content_status": "metadata_only",
                    "paywall_status": None,
                    "available": False,
                    "content_text": None,
                }
            return {
                "article_id": article_id,
                "title": "News item",
                "content_status": "full_text_available",
                "paywall_status": None,
                "available": True,
                "content_text": "Fetched article text",
            }

    repository = _OnDemandRepository()
    service = _FakeNewsService()
    bridge = _FakeNewsBridge(repository=repository, service=service)

    result = bridge.get_news_article_content({"article_id": "needs-fetch"})

    assert result["available"] is True
    assert result["content_text"] == "Fetched article text"
    assert result["fetch_status"] == "success"
    assert service.content_fetches == ["needs-fetch"]


def test_news_bridge_applies_classification_correction_and_blocks_when_read_only():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())
    read_only_bridge = _FakeNewsBridge(
        repository=_FakeRepository(),
        service=_FakeNewsService(),
        write_allowed=False,
    )

    result = bridge.apply_news_classification_correction({
        "article_id": "art-1",
        "target_type": "company",
        "target_id": "9512",
        "action": "add",
        "user_value": {"match_reason": "Manual"},
    })
    blocked = read_only_bridge.apply_news_classification_correction({
        "article_id": "art-1",
        "target_type": "company",
        "target_id": "9512",
        "action": "add",
    })

    assert result["status"] == "success"
    assert repository.correction_params == {
        "article_id": "art-1",
        "target_type": "company",
        "target_id": "9512",
        "action": "add",
        "user_value": {"match_reason": "Manual"},
        "rule_suggestion": None,
    }
    assert blocked == {"status": "blocked", "error": "apply_news_classification_correction"}


def test_news_bridge_returns_collection_runs_with_bounded_limit():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    result = bridge.get_news_collection_runs({"limit": 999})

    assert result == {"items": [{"run_id": "run-1", "status": "success"}], "count": 1}
    assert repository.run_limit == 100


def test_news_bridge_updates_source_enabled_and_priority():
    rows = {
        "bcb-rss": {
            "source_id": "bcb-rss",
            "name": "Banco Central do Brasil",
            "source_type": "official",
            "reliability_layer": "official",
            "feed_url": "https://www.bcb.gov.br/acessoinformacao/rss",
            "enabled": 1,
            "priority": 10,
            "user_defined": 0,
        }
    }
    repository = _FakeRepository(rows)
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    enabled_result = bridge.set_news_source_enabled({"source_id": "bcb-rss", "enabled": False})
    priority_result = bridge.set_news_source_priority({"source_id": "bcb-rss", "priority": 9999})

    assert enabled_result == {"status": "success", "source_id": "bcb-rss", "enabled": False}
    assert priority_result == {"status": "success", "source_id": "bcb-rss", "priority": 1000}
    assert repository.enabled_updates == [("bcb-rss", False)]
    assert repository.priority_updates == [("bcb-rss", 1000)]


def test_news_bridge_adds_validated_custom_source_without_collecting_articles():
    repository = _FakeRepository()
    service = _FakeNewsService()
    bridge = _FakeNewsBridge(repository=repository, service=service)

    result = bridge.add_custom_news_source({
        "feed_url": "https://example.com/feed.xml",
        "name": "Example Feed",
        "priority": 42,
    })

    assert result["status"] == "success"
    assert result["source"]["name"] == "Example Feed"
    assert result["source"]["source_type"] == "user_provided_rss"
    assert result["source"]["user_defined"] == 1
    assert result["validation"]["entry_count"] == 1
    assert service.validated_urls == ["https://example.com/feed.xml"]
    assert service.sources == []
    assert repository.fetch_state_updates[0]["etag"] == '"v1"'


def test_news_bridge_rejects_invalid_custom_source_url_and_feed():
    bridge = _FakeNewsBridge(repository=_FakeRepository(), service=_FakeNewsService())
    invalid_url = bridge.add_custom_news_source({"feed_url": "file:///tmp/feed.xml"})

    failed_validation = _FakeNewsService(
        FeedValidationResult(
            status="error",
            feed_url="https://example.com/feed.xml",
            http_status=200,
            error_message="Unsupported feed root",
        )
    )
    bridge = _FakeNewsBridge(repository=_FakeRepository(), service=failed_validation)
    invalid_feed = bridge.add_custom_news_source({"feed_url": "https://example.com/feed.xml"})

    assert invalid_url["status"] == "error"
    assert "HTTP or HTTPS" in invalid_url["error"]
    assert invalid_feed["status"] == "error"
    assert invalid_feed["error"] == "Unsupported feed root"


def test_news_bridge_updates_article_user_state():
    repository = _FakeRepository()
    bridge = _FakeNewsBridge(repository=repository, service=_FakeNewsService())

    result = bridge.update_news_article_state({
        "article_id": "art-1",
        "read": True,
        "saved": True,
        "hidden": False,
        "read_later": True,
        "notes": "Check later",
    })
    missing = bridge.update_news_article_state({"article_id": "missing", "saved": True})

    assert result["status"] == "success"
    assert result["state"]["saved"] == 1
    assert result["state"]["read_later"] == 1
    assert repository.article_state_updates[0]["article_id"] == "art-1"
    assert missing["status"] == "not_found"
