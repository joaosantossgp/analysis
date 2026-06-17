from __future__ import annotations

import time

import requests
from sqlalchemy import create_engine, text

from src.news.fetcher import NewsFeedFetcher
from src.news.feed_parser import NewsFeedParseError, parse_feed_bytes
from src.news.repository import NewsRepository, NewsSource, canonicalize_url, google_company_source_id, user_source_id_for_url
from src.news.schema import ensure_news_tables_for_connection, get_news_engine
from src.news.service import NewsCollectionService
from src.news.sources import builtin_sources
from src.platform.settings import build_settings


VALID_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Market Feed</title>
    <language>pt-BR</language>
    <item>
      <title>Petrobras aprova dividendos</title>
      <link>https://example.com/news/petrobras-dividendos?utm_source=x&amp;id=1</link>
      <guid>rss-1</guid>
      <pubDate>Mon, 15 Jun 2026 13:45:00 -0300</pubDate>
      <description>Conselho aprovou nova distribuicao.</description>
    </item>
  </channel>
</rss>
"""


VALID_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">
  <title>Global Markets</title>
  <entry>
    <id>tag:example.com,2026:china-rates</id>
    <title>China rate decision moves commodities</title>
    <link href="https://example.com/global/china-rates?fbclid=abc&amp;ref=terminal" rel="alternate" />
    <updated>2026-06-16T09:10:00Z</updated>
    <summary>Iron ore and FX reacted after the decision.</summary>
  </entry>
</feed>
"""


GOOGLE_NEWS_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>Petrobras anuncia investimento</title>
      <link>https://news.google.com/rss/articles/CBMiExample</link>
      <guid>google-1</guid>
      <pubDate>Tue, 16 Jun 2026 10:00:00 GMT</pubDate>
      <description>Snippet from Google News.</description>
      <source url="https://www.moneytimes.com.br">Money Times</source>
    </item>
  </channel>
</rss>
"""


VALID_RDF = b"""<?xml version="1.0" encoding="utf-8" ?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns="http://purl.org/rss/1.0/">
  <channel rdf:about="https://www.gov.br/cvm/RSS">
    <title>Comissao de Valores Mobiliarios</title>
    <link>https://www.gov.br/cvm</link>
  </channel>
  <item rdf:about="https://www.gov.br/cvm/noticia">
    <title>CVM cancela registro de companhia aberta</title>
    <link>https://www.gov.br/cvm/noticia</link>
    <description>Area tecnica aponta falta de informacoes.</description>
    <dc:date>2026-06-10T12:45:40Z</dc:date>
  </item>
</rdf:RDF>
"""


def _source() -> NewsSource:
    return NewsSource(
        source_id="fixture-source",
        name="Fixture Source",
        source_type="official",
        reliability_layer="official",
        feed_url="https://example.com/feed.xml",
        priority=10,
    )


def _content_source() -> NewsSource:
    return NewsSource(
        source_id="official-content-source",
        name="Official Content Source",
        source_type="official",
        reliability_layer="official",
        feed_url="https://example.com/feed.xml",
        priority=10,
        allow_content_storage=True,
    )


def _aggregator_source() -> NewsSource:
    return NewsSource(
        source_id="google_company_9512",
        name="Google News - PETR4",
        source_type="aggregator_search",
        reliability_layer="aggregator",
        feed_url="https://news.google.com/rss/search?q=PETR4",
        priority=140,
        allow_content_storage=False,
    )


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        url: str = "https://example.com/feed.xml",
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        self.url = url

    def iter_content(self, chunk_size: int):
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start : start + chunk_size]


class _FakeSession:
    def __init__(self, response=None, exception: Exception | None = None) -> None:
        self.response = response
        self.exception = exception
        self.calls: list[dict] = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.exception:
            raise self.exception
        return self.response

    def head(self, url, **kwargs):
        self.calls.append({"method": "HEAD", "url": url, **kwargs})
        if self.exception:
            raise self.exception
        return self.response


def _service_with_fake_fetcher(tmp_path, session: _FakeSession) -> tuple[NewsCollectionService, object]:
    engine = create_engine(f"sqlite:///{tmp_path / 'news.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
    fetcher = NewsFeedFetcher(session=session, max_bytes=500)
    return NewsCollectionService(NewsRepository(engine), fetcher=fetcher), engine


def test_news_schema_creates_adjacent_db_tables_and_fts(tmp_path):
    db_path = tmp_path / "news.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')")
            ).fetchall()
        }
        assert "news_sources" in tables
        assert "news_articles" in tables
        assert "news_article_content" in tables
        assert "news_retention_policy" in tables
        assert "news_source_health" in tables
        fts_enabled = conn.execute(
            text("SELECT value FROM news_schema_capabilities WHERE key = 'fts5'")
        ).scalar()
        assert fts_enabled in {"0", "1"}
        if fts_enabled == "1":
            assert "news_articles_fts" in tables


def test_news_schema_clean_install_creates_news_db_at_configured_path(tmp_path):
    settings = build_settings(project_root=tmp_path)

    assert not settings.paths.news_db_path.exists()

    engine = get_news_engine(settings)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')")
            ).fetchall()
        }
        policy = conn.execute(
            text("SELECT extracted_text_retention_days FROM news_retention_policy WHERE policy_id = 'default'")
        ).scalar()

    assert settings.paths.news_db_path.exists()
    assert "news_articles" in tables
    assert "news_article_content" in tables
    assert "news_company_scope_overrides" in tables
    assert policy == 90


def test_news_schema_seeds_classification_catalog_and_preserves_user_flags(tmp_path):
    db_path = tmp_path / "news-classification.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
        conn.execute(text("UPDATE news_topics SET active = 0 WHERE topic_id = 'topic_macro_rates'"))
        conn.execute(text("UPDATE news_event_types SET active = 0 WHERE event_type_id = 'event_debt_covenant_breach'"))
        conn.execute(text("UPDATE news_keyword_rules SET active = 0, priority = 7 WHERE keyword_rule_id = 'kw_macro_selic'"))

    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    topics = repository.list_topics(active_only=False)
    event_types = repository.list_event_types(active_only=False)
    rules = repository.list_keyword_rules(active_only=False)

    assert any(topic["topic_id"] == "topic_markets_commodities" for topic in topics)
    assert any(event_type["event_type_id"] == "event_debt_covenant_breach" for event_type in event_types)
    selic = next(rule for rule in rules if rule["keyword_rule_id"] == "kw_macro_selic")
    assert selic["aliases"]
    assert selic["active"] == 0
    assert selic["priority"] == 7
    assert next(topic for topic in topics if topic["topic_id"] == "topic_macro_rates")["active"] == 0
    assert next(
        event_type for event_type in event_types if event_type["event_type_id"] == "event_debt_covenant_breach"
    )["active"] == 0


def test_news_schema_upgrade_adds_columns_without_data_loss(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old-news.db'}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE news_sources (
                source_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                reliability_layer TEXT NOT NULL,
                feed_url TEXT NOT NULL,
                homepage_url TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                priority INTEGER NOT NULL DEFAULT 100,
                user_defined INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO news_sources (
                source_id, name, source_type, reliability_layer, feed_url,
                enabled, priority, user_defined, created_at, updated_at
            )
            VALUES (
                'src', 'Old Source', 'official', 'official', 'https://example.com/feed.xml',
                1, 10, 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
            )
        """))
        conn.execute(text("""
            CREATE TABLE news_articles (
                article_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                source_name TEXT NOT NULL,
                original_url TEXT NOT NULL,
                canonical_url TEXT NOT NULL UNIQUE,
                published_at TEXT,
                discovered_at TEXT NOT NULL,
                fetched_at TEXT,
                extracted_at TEXT,
                summary TEXT,
                content_status TEXT NOT NULL DEFAULT 'metadata_only',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO news_articles (
                article_id, source_id, title, source_name, original_url,
                canonical_url, discovered_at, created_at, updated_at
            )
            VALUES (
                'old', 'src', 'Old title', 'Source', 'https://example.com/a',
                'https://example.com/a', '2026-01-01T00:00:00+00:00',
                '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
            )
        """))

    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')")
            ).fetchall()
        }
        source_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(news_sources)")).fetchall()}
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(news_articles)")).fetchall()}
        retention = conn.execute(text("SELECT * FROM news_retention_policy WHERE policy_id = 'default'")).mappings().fetchone()
        source = conn.execute(text("SELECT * FROM news_sources WHERE source_id = 'src'")).mappings().fetchone()
        assert {"source_item_id", "language", "paywall_status"}.issubset(cols)
        assert "allow_content_storage" in source_cols
        assert "news_article_content" in tables
        assert "news_retention_policy" in tables
        assert "news_company_scope_overrides" in tables
        assert source["name"] == "Old Source"
        assert source["allow_content_storage"] == 0
        assert retention["extracted_text_retention_days"] == 90
        assert retention["preserve_saved"] == 1
        count = conn.execute(text("SELECT count(*) FROM news_articles WHERE article_id = 'old'")).scalar()
        assert count == 1


def test_parse_valid_rss_and_atom_fixtures():
    rss = parse_feed_bytes(VALID_RSS, feed_url="https://example.com/feed.xml")
    atom = parse_feed_bytes(VALID_ATOM, feed_url="https://example.com/atom.xml")

    assert rss.title == "Market Feed"
    assert rss.entries[0].title == "Petrobras aprova dividendos"
    assert rss.entries[0].published_at == "2026-06-15T16:45:00+00:00"
    assert atom.language == "en"
    assert atom.entries[0].source_item_id == "tag:example.com,2026:china-rates"
    assert atom.entries[0].published_at == "2026-06-16T09:10:00+00:00"


def test_parse_valid_rdf_feed():
    rdf = parse_feed_bytes(VALID_RDF, feed_url="https://www.gov.br/cvm/RSS")

    assert rdf.title == "Comissao de Valores Mobiliarios"
    assert len(rdf.entries) == 1
    assert rdf.entries[0].source_item_id == "https://www.gov.br/cvm/noticia"
    assert rdf.entries[0].published_at == "2026-06-10T12:45:40+00:00"


def test_builtin_sources_include_validated_official_and_press_layers():
    sources = {source.source_id: source for source in builtin_sources()}

    assert set(sources) >= {
        "cvm-rss",
        "bcb-rss",
        "bcb-copom-comunicados",
        "b3-rss-news",
        "ibge-rss-news",
        "agencia-brasil-economia",
    }
    assert sources["cvm-rss"].reliability_layer == "official"
    assert sources["ibge-rss-news"].allow_content_storage is True
    assert sources["agencia-brasil-economia"].allow_content_storage is False


def test_parse_malformed_feed_raises_explicit_error():
    try:
        parse_feed_bytes(b"<rss><channel><item></rss>", feed_url="https://example.com/feed.xml")
    except NewsFeedParseError as exc:
        assert "Malformed feed XML" in str(exc)
    else:
        raise AssertionError("Expected NewsFeedParseError")


def test_parse_rejects_dtd_entities():
    try:
        parse_feed_bytes(
            b'<!DOCTYPE rss [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]><rss />',
            feed_url="https://example.com/feed.xml",
        )
    except NewsFeedParseError as exc:
        assert "DTD/entity" in str(exc)
    else:
        raise AssertionError("Expected NewsFeedParseError")


def test_canonicalize_url_removes_tracking_parameters():
    assert (
        canonicalize_url("HTTPS://Example.COM/path/?utm_source=x&b=2&fbclid=abc&a=1#frag")
        == "https://example.com/path?a=1&b=2"
    )
    assert (
        canonicalize_url("https://news.google.com/rss/articles/x?oc=5&hl=en-US&gl=US&ceid=US:en")
        == "https://news.google.com/rss/articles/x"
    )


def test_collect_feed_payload_upserts_source_articles_health_and_dedupes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    service = NewsCollectionService(NewsRepository(engine))
    first = service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    second = service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)

    assert first.status == "success"
    assert first.articles_inserted == 1
    assert second.articles_inserted == 0
    assert second.articles_updated == 1
    with engine.connect() as conn:
        article_count = conn.execute(text("SELECT count(*) FROM news_articles")).scalar()
        health = conn.execute(
            text("SELECT last_status, consecutive_failures FROM news_source_health WHERE source_id = 'fixture-source'")
        ).fetchone()
    assert article_count == 1
    assert tuple(health) == ("success", 0)


def test_collect_feed_payload_classifies_keywords_topics_and_events(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-classified.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    result = service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    service.collect_feed_payload(source=_source(), payload=VALID_ATOM, http_status=200)
    articles = repository.list_articles(include_hidden=True)["items"]
    dividend_article_id = next(article["article_id"] for article in articles if "dividendos" in article["title"])
    commodity_article_id = next(article["article_id"] for article in articles if "commodities" in article["title"])
    dividend_classification = repository.get_article_classification(dividend_article_id)
    commodity_classification = repository.get_article_classification(commodity_article_id)
    listed_dividend = next(article for article in articles if article["article_id"] == dividend_article_id)

    assert result.status == "success"
    assert any(match["keyword_rule_id"] == "kw_dividends_jcp" for match in dividend_classification["keywords"])
    assert any(match["event_type_id"] == "event_dividends_approved" for match in dividend_classification["event_types"])
    assert any(match["topic_id"] == "topic_markets_commodities" for match in commodity_classification["topics"])
    assert all("Matched keyword rule" in match["match_reason"] for match in dividend_classification["keywords"])
    assert dividend_classification["score"]["priority_level"] in {"Normal", "High", "Critical"}
    assert "source_reliability" in dividend_classification["score"]["components"]
    assert listed_dividend["priority_level"] == dividend_classification["score"]["priority_level"]
    assert listed_dividend["relevance_reasons"]


def test_collect_feed_payload_stores_feed_content_only_when_source_allows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-selective-content.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    service.collect_feed_payload(source=_content_source(), payload=VALID_ATOM, http_status=200)

    articles = repository.list_articles(include_hidden=True)["items"]
    regular_article = next(article for article in articles if "Petrobras" in article["title"])
    official_article = next(article for article in articles if "China" in article["title"])
    summary = repository.get_content_storage_summary()
    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT article_id, content_format, source_policy FROM news_article_content")
        ).mappings().fetchall()

    assert regular_article["content_status"] == "summary_available"
    assert official_article["content_status"] == "full_text_available"
    assert summary["content_count"] == 1
    assert stored[0]["article_id"] == official_article["article_id"]
    assert stored[0]["content_format"] == "feed"
    assert stored[0]["source_policy"] == "feed_content_allowed"


def test_repository_top_news_orders_by_score_not_chronology(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-top-order.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    service.collect_feed_payload(source=_source(), payload=VALID_ATOM, http_status=200)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE news_article_scores SET total_score = 9.0, priority_level = 'Critical' WHERE article_id IN (SELECT article_id FROM news_articles WHERE title LIKE '%Petrobras%')")
        )
        conn.execute(
            text("UPDATE news_article_scores SET total_score = 1.0, priority_level = 'Normal' WHERE article_id IN (SELECT article_id FROM news_articles WHERE title LIKE '%China%')")
        )

    top = repository.list_articles(order="top")
    latest = repository.list_articles(order="latest")

    assert top["order"] == "top"
    assert latest["order"] == "latest"
    assert "Petrobras" in top["items"][0]["title"]
    assert "China" in latest["items"][0]["title"]


def test_repository_large_history_caps_pages_and_keeps_top_order(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-large-history.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    source = _source()
    repository.upsert_source(source)
    with engine.begin() as conn:
        for index in range(1500):
            article_id = f"bulk-{index:04d}"
            published_day = (index % 28) + 1
            published_hour = index % 24
            conn.execute(
                text("""
                    INSERT INTO news_articles (
                        article_id, source_id, source_item_id, title, source_name,
                        original_url, canonical_url, published_at, discovered_at,
                        fetched_at, summary, language, content_status, created_at, updated_at
                    )
                    VALUES (
                        :article_id, :source_id, :source_item_id, :title, :source_name,
                        :original_url, :canonical_url, :published_at, :discovered_at,
                        :fetched_at, :summary, 'pt-BR', 'summary_available',
                        datetime('now'), datetime('now')
                    )
                """),
                {
                    "article_id": article_id,
                    "source_id": source.source_id,
                    "source_item_id": article_id,
                    "title": f"Bulk market article {index:04d}",
                    "source_name": source.name,
                    "original_url": f"https://example.com/bulk/{index}?utm_source=test",
                    "canonical_url": f"https://example.com/bulk/{index}",
                    "published_at": f"2026-06-{published_day:02d}T{published_hour:02d}:00:00+00:00",
                    "discovered_at": f"2026-06-{published_day:02d}T{published_hour:02d}:05:00+00:00",
                    "fetched_at": f"2026-06-{published_day:02d}T{published_hour:02d}:10:00+00:00",
                    "summary": "Volume smoke fixture",
                },
            )
            conn.execute(
                text("""
                    INSERT INTO news_article_scores (
                        article_id, total_score, priority_level, components_json, reasons_json, updated_at
                    )
                    VALUES (
                        :article_id, :total_score, :priority_level, '{}', '[]', datetime('now')
                    )
                """),
                {
                    "article_id": article_id,
                    "total_score": 999.0 if index == 777 else float(index % 100),
                    "priority_level": "Critical" if index == 777 else "Normal",
                },
            )

    started = time.perf_counter()
    latest = repository.list_articles(limit=50, offset=100, order="latest")
    top = repository.list_articles(limit=999, offset=0, order="top")
    elapsed = time.perf_counter() - started

    assert latest["limit"] == 50
    assert latest["offset"] == 100
    assert latest["count"] == 50
    assert latest["total"] == 1500
    assert top["limit"] == 200
    assert top["count"] == 200
    assert top["total"] == 1500
    assert top["items"][0]["article_id"] == "bulk-0777"
    assert top["items"][0]["priority_level"] == "Critical"
    assert elapsed < 5.0


def test_repository_overview_sections_use_ranked_and_classified_articles(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-overview.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    service.collect_feed_payload(source=_source(), payload=VALID_ATOM, http_status=200)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE news_article_scores SET total_score = 9.0, priority_level = 'Critical' WHERE article_id IN (SELECT article_id FROM news_articles WHERE title LIKE '%Petrobras%')")
        )

    overview = repository.list_overview(limit_per_section=2)
    sections = {section["section_id"]: section for section in overview["sections"]}

    assert overview["limit_per_section"] == 2
    assert set(sections) >= {
        "critical_news",
        "top_market_news",
        "macro_watch",
        "keyword_alerts",
        "all_news",
    }
    assert "Petrobras" in sections["critical_news"]["items"][0]["title"]
    assert sections["keyword_alerts"]["items"]
    assert sections["all_news"]["items"][0]["published_at"] >= sections["all_news"]["items"][-1]["published_at"]


def test_repository_news_company_scope_overrides_drive_my_companies_only(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-company-scope.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    article_id = repository.list_articles()["items"][0]["article_id"]
    repository.apply_classification_correction(
        article_id=article_id,
        target_type="company",
        target_id="9512",
        action="add",
        user_value={"match_reason": "Manual Petrobras association"},
    )

    empty_scope = repository.list_overview(company_scope_ids=set())
    included_scope = repository.list_overview(company_scope_ids={9512})
    repository.set_company_scope_override(cd_cvm=9512, action="exclude", reason="News-only exclusion")
    overrides = repository.list_company_scope_overrides()

    empty_sections = {section["section_id"]: section for section in empty_scope["sections"]}
    included_sections = {section["section_id"]: section for section in included_scope["sections"]}
    assert empty_sections["my_companies"]["items"] == []
    assert included_sections["my_companies"]["items"][0]["article_id"] == article_id
    assert overrides == [overrides[0]]
    assert overrides[0]["cd_cvm"] == 9512
    assert overrides[0]["action"] == "exclude"


def test_repository_classification_corrections_are_article_scoped_and_audited(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-corrections.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    article_id = repository.list_articles()["items"][0]["article_id"]

    added = repository.apply_classification_correction(
        article_id=article_id,
        target_type="company",
        target_id="9512",
        action="add",
        user_value={"match_reason": "Manual Petrobras association"},
    )
    after_add = repository.get_article_classification(article_id)
    removed = repository.apply_classification_correction(
        article_id=article_id,
        target_type="company",
        target_id="9512",
        action="remove",
        user_value={"match_reason": "Removed after review"},
    )
    after_remove = repository.get_article_classification(article_id)

    assert added["status"] == "success"
    assert after_add["companies"][0]["cd_cvm"] == 9512
    assert after_add["companies"][0]["match_method"] == "manual"
    assert removed["status"] == "success"
    assert after_remove["companies"] == []
    assert len(after_remove["corrections"]) == 2
    remove_correction = next(
        correction
        for correction in after_remove["corrections"]
        if correction["correction_action"] == "remove"
    )
    assert remove_correction["original_match_reason"] == "Manual Petrobras association"


def test_collect_feed_payload_classifies_company_matches_from_main_company_table(tmp_path):
    news_engine = create_engine(f"sqlite:///{tmp_path / 'news-company-match.db'}")
    company_engine = create_engine(f"sqlite:///{tmp_path / 'main-company-match.db'}")
    with news_engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
    with company_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE companies (
                cd_cvm INTEGER PRIMARY KEY,
                company_name TEXT NOT NULL,
                nome_comercial TEXT,
                cnpj TEXT,
                ticker_b3 TEXT,
                gics_sector TEXT,
                gics_sector_slug TEXT,
                gics_sub_industry TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """))
        conn.execute(text("""
            INSERT INTO companies (
                cd_cvm, company_name, nome_comercial, cnpj, ticker_b3,
                gics_sector, gics_sector_slug, gics_sub_industry, is_active
            )
            VALUES (
                9512, 'PETROLEO BRASILEIRO S.A. PETROBRAS', 'PETROBRAS', '33000167000101', 'PETR4',
                'Energy', 'energy', 'Integrated Oil & Gas', 1
            )
        """))

    repository = NewsRepository(news_engine)
    service = NewsCollectionService(repository, company_engine=company_engine)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    article_id = repository.list_articles()["items"][0]["article_id"]
    classification = repository.get_article_classification(article_id)

    assert classification["companies"][0]["cd_cvm"] == 9512
    assert classification["companies"][0]["match_method"] == "trade_name"
    assert "PETROBRAS" in classification["companies"][0]["match_reason"]
    assert any(match["sector_slug"] == "energy" for match in classification["sectors"])
    assert any(
        match["sector_slug"] == "integrated-oil-gas" and match["parent_sector_slug"] == "energy"
        for match in classification["sectors"]
    )


def test_collect_feed_payload_ignores_inactive_company_matches(tmp_path):
    news_engine = create_engine(f"sqlite:///{tmp_path / 'news-inactive-company.db'}")
    company_engine = create_engine(f"sqlite:///{tmp_path / 'main-inactive-company.db'}")
    with news_engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
    with company_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE companies (
                cd_cvm INTEGER PRIMARY KEY,
                company_name TEXT NOT NULL,
                nome_comercial TEXT,
                cnpj TEXT,
                ticker_b3 TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """))
        conn.execute(text("""
            INSERT INTO companies (cd_cvm, company_name, nome_comercial, cnpj, ticker_b3, is_active)
            VALUES (9512, 'PETROLEO BRASILEIRO S.A. PETROBRAS', 'PETROBRAS', '33000167000101', 'PETR4', 0)
        """))

    repository = NewsRepository(news_engine)
    service = NewsCollectionService(repository, company_engine=company_engine)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    article_id = repository.list_articles()["items"][0]["article_id"]
    classification = repository.get_article_classification(article_id)

    assert classification["companies"] == []


def test_collect_feed_payload_skips_inactive_keyword_rules(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-inactive-keyword.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
        conn.execute(text("UPDATE news_keyword_rules SET active = 0 WHERE keyword_rule_id = 'kw_dividends_jcp'"))

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    article_id = repository.list_articles()["items"][0]["article_id"]
    classification = repository.get_article_classification(article_id)

    assert not any(match["keyword_rule_id"] == "kw_dividends_jcp" for match in classification["keywords"])
    assert not any(match["event_type_id"] == "event_dividends_approved" for match in classification["event_types"])


def test_collect_feed_payload_records_source_error(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    service = NewsCollectionService(NewsRepository(engine))
    result = service.collect_feed_payload(
        source=_source(),
        payload=b"<not-feed />",
        http_status=200,
    )

    assert result.status == "error"
    assert result.error_count == 1
    with engine.connect() as conn:
        health = conn.execute(
            text("SELECT last_status, consecutive_failures, last_error FROM news_source_health WHERE source_id = 'fixture-source'")
        ).fetchone()
    assert health[0] == "error"
    assert health[1] == 1
    assert "Unsupported feed root" in health[2]


def test_collect_source_sends_conditional_headers_and_updates_fetch_state(tmp_path):
    session = _FakeSession(
        _FakeResponse(
            status_code=200,
            body=VALID_RSS,
            headers={"ETag": '"v2"', "Last-Modified": "Tue, 16 Jun 2026 10:00:00 GMT"},
        )
    )
    service, engine = _service_with_fake_fetcher(tmp_path, session)
    source = _source()
    repository = service.repository
    repository.upsert_source(source)
    repository.update_source_fetch_state(
        source_id=source.source_id,
        etag='"v1"',
        last_modified="Mon, 15 Jun 2026 10:00:00 GMT",
    )

    result = service.collect_source(source=source)

    headers = session.calls[0]["headers"]
    assert result.status == "success"
    assert headers["If-None-Match"] == '"v1"'
    assert headers["If-Modified-Since"] == "Mon, 15 Jun 2026 10:00:00 GMT"
    with engine.connect() as conn:
        source_row = conn.execute(
            text("SELECT etag, last_modified FROM news_sources WHERE source_id = 'fixture-source'")
        ).fetchone()
        health = conn.execute(
            text("SELECT last_status, consecutive_failures, last_http_status FROM news_source_health WHERE source_id = 'fixture-source'")
        ).fetchone()
    assert tuple(source_row) == ('"v2"', "Tue, 16 Jun 2026 10:00:00 GMT")
    assert tuple(health) == ("success", 0, 200)


def test_collect_aggregator_source_resolves_original_url_without_full_text_extraction(tmp_path):
    session = _FakeSession(
        _FakeResponse(
            status_code=200,
            body=GOOGLE_NEWS_RSS,
            url="https://example.com/original/petrobras-investimento",
        )
    )
    service, engine = _service_with_fake_fetcher(tmp_path, session)

    result = service.collect_source(source=_aggregator_source())

    assert result.status == "success"
    assert any(call.get("method") == "HEAD" for call in session.calls)
    with engine.connect() as conn:
        article = conn.execute(
            text("SELECT original_url, canonical_url, summary, content_status FROM news_articles LIMIT 1")
        ).mappings().fetchone()
        content_count = conn.execute(text("SELECT count(*) FROM news_article_content")).scalar()
    assert article["original_url"] == "https://example.com/original/petrobras-investimento"
    assert article["canonical_url"] == "https://example.com/original/petrobras-investimento"
    assert article["content_status"] == "summary_available"
    assert "Original source resolved" in article["summary"]
    assert content_count == 0


def test_collect_aggregator_source_preserves_publisher_when_google_url_is_not_resolved(tmp_path):
    session = _FakeSession(
        _FakeResponse(
            status_code=200,
            body=GOOGLE_NEWS_RSS,
            url="https://news.google.com/rss/articles/CBMiExample?oc=5",
        )
    )
    service, engine = _service_with_fake_fetcher(tmp_path, session)

    result = service.collect_source(source=_aggregator_source())

    assert result.status == "success"
    with engine.connect() as conn:
        article = conn.execute(
            text("SELECT source_name, original_url, summary FROM news_articles LIMIT 1")
        ).mappings().fetchone()
    assert article["source_name"] == "Money Times"
    assert article["original_url"].startswith("https://news.google.com/rss/articles/")
    assert "Aggregator article URL was not resolved" in article["summary"]


def test_collect_aggregator_source_updates_existing_google_article_publisher(tmp_path):
    session = _FakeSession(
        _FakeResponse(
            status_code=200,
            body=GOOGLE_NEWS_RSS,
            url="https://news.google.com/rss/articles/CBMiExample?oc=5&hl=en-US",
        )
    )
    service, engine = _service_with_fake_fetcher(tmp_path, session)
    repository = service.repository
    old_entry = parse_feed_bytes(GOOGLE_NEWS_RSS, feed_url="https://news.google.com/rss/search?q=PETR4").entries[0]
    repository.upsert_article(source=_aggregator_source(), entry=old_entry)
    with engine.begin() as conn:
        conn.execute(text("UPDATE news_articles SET source_name = 'Google News - PETR4'"))

    result = service.collect_source(source=_aggregator_source())

    assert result.status == "success"
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT source_name, canonical_url FROM news_articles")
        ).mappings().fetchall()
    assert len(rows) == 1
    assert rows[0]["source_name"] == "Money Times"
    assert rows[0]["canonical_url"] == "https://news.google.com/rss/articles/CBMiExample"


def test_collect_source_handles_not_modified_without_failure(tmp_path):
    session = _FakeSession(_FakeResponse(status_code=304, headers={"ETag": '"v1"'}))
    service, engine = _service_with_fake_fetcher(tmp_path, session)

    result = service.collect_source(source=_source())

    assert result.status == "not_modified"
    assert result.error_count == 0
    with engine.connect() as conn:
        health = conn.execute(
            text("SELECT last_status, consecutive_failures, last_http_status FROM news_source_health WHERE source_id = 'fixture-source'")
        ).fetchone()
        article_count = conn.execute(text("SELECT count(*) FROM news_articles")).scalar()
    assert tuple(health) == ("not_modified", 0, 304)
    assert article_count == 0


def test_collect_source_records_http_429_error(tmp_path):
    session = _FakeSession(_FakeResponse(status_code=429, body=b"rate limited"))
    service, engine = _service_with_fake_fetcher(tmp_path, session)

    result = service.collect_source(source=_source())

    assert result.status == "error"
    assert "HTTP 429" in result.error_message
    with engine.connect() as conn:
        health = conn.execute(
            text("SELECT last_status, consecutive_failures, last_http_status, last_error FROM news_source_health WHERE source_id = 'fixture-source'")
        ).fetchone()
    assert health[0] == "error"
    assert health[1] == 1
    assert health[2] == 429
    assert "HTTP 429" in health[3]


def test_collect_source_records_timeout_error(tmp_path):
    session = _FakeSession(exception=requests.Timeout())
    service, engine = _service_with_fake_fetcher(tmp_path, session)

    result = service.collect_source(source=_source())

    assert result.status == "error"
    assert "timed out" in result.error_message
    with engine.connect() as conn:
        health = conn.execute(
            text("SELECT last_status, consecutive_failures, last_error FROM news_source_health WHERE source_id = 'fixture-source'")
        ).fetchone()
    assert health[0] == "error"
    assert health[1] == 1
    assert "timed out" in health[2]


def test_collect_source_rejects_oversized_payload(tmp_path):
    session = _FakeSession(_FakeResponse(status_code=200, body=b"x" * 501))
    service, engine = _service_with_fake_fetcher(tmp_path, session)

    result = service.collect_source(source=_source())

    assert result.status == "error"
    assert "exceeds 500 bytes" in result.error_message
    with engine.connect() as conn:
        article_count = conn.execute(text("SELECT count(*) FROM news_articles")).scalar()
        health = conn.execute(
            text("SELECT last_status, consecutive_failures, last_error FROM news_source_health WHERE source_id = 'fixture-source'")
        ).fetchone()
    assert article_count == 0
    assert health[0] == "error"
    assert health[1] == 1
    assert "exceeds 500 bytes" in health[2]


def test_repository_lists_articles_sources_and_collection_runs(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    result = service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)

    sources = repository.list_sources()
    articles = repository.list_articles(limit=10)
    runs = repository.list_collection_runs(limit=5)

    assert result.status == "success"
    assert sources[0]["source_id"] == "fixture-source"
    assert sources[0]["last_status"] == "success"
    assert articles["count"] == 1
    assert articles["total"] == 1
    assert articles["items"][0]["title"] == "Petrobras aprova dividendos"
    assert articles["items"][0]["read"] == 0
    assert runs[0]["status"] == "success"
    assert runs[0]["articles_inserted"] == 1


def test_repository_article_listing_filters_hidden_items(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-hidden.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    article_id = repository.list_articles()["items"][0]["article_id"]
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO news_user_state (article_id, hidden, created_at, updated_at)
                VALUES (:article_id, 1, datetime('now'), datetime('now'))
            """),
            {"article_id": article_id},
        )

    visible = repository.list_articles()
    all_items = repository.list_articles(include_hidden=True)

    assert visible["count"] == 0
    assert visible["total"] == 0
    assert all_items["count"] == 1
    assert all_items["items"][0]["hidden"] == 1


def test_repository_updates_article_user_state(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-user-state.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    article_id = repository.list_articles()["items"][0]["article_id"]

    state = repository.update_article_user_state(
        article_id=article_id,
        read=True,
        saved=True,
        read_later=True,
        notes="Review earnings impact",
    )
    missing = repository.update_article_user_state(article_id="missing", read=True)

    assert missing is None
    assert state["article_id"] == article_id
    assert state["read"] == 1
    assert state["saved"] == 1
    assert state["hidden"] == 0
    assert state["read_later"] == 1
    assert state["notes"] == "Review earnings impact"
    cleared = repository.update_article_user_state(article_id=article_id, notes="")
    assert cleared["notes"] == ""
    listed = repository.list_articles(include_hidden=True)["items"][0]
    assert listed["saved"] == 1
    assert listed["read_later"] == 1


def test_repository_retention_cleanup_preserves_saved_and_clears_extracted_content_only(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-retention.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_source(), payload=VALID_RSS, http_status=200)
    service.collect_feed_payload(source=_source(), payload=VALID_ATOM, http_status=200)
    articles = repository.list_articles(include_hidden=True)["items"]
    saved_article_id = articles[0]["article_id"]
    removable_article_id = articles[1]["article_id"]
    repository.store_article_content(article_id=saved_article_id, content_text="saved text")
    repository.store_article_content(article_id=removable_article_id, content_text="removable text")
    repository.update_article_user_state(article_id=saved_article_id, saved=True)
    repository.update_retention_policy(extracted_text_retention_days=1, total_storage_limit_mb=16)
    with engine.begin() as conn:
        conn.execute(text("UPDATE news_article_content SET extracted_at = datetime('now', '-2 days')"))
        conn.execute(text("UPDATE news_articles SET extracted_at = datetime('now', '-2 days')"))

    preview = repository.cleanup_extracted_content(dry_run=True)
    cleanup = repository.cleanup_extracted_content()
    summary = repository.get_content_storage_summary()
    listed = repository.list_articles(include_hidden=True)["items"]
    saved_article = next(article for article in listed if article["article_id"] == saved_article_id)
    removable_article = next(article for article in listed if article["article_id"] == removable_article_id)

    assert preview["deleted_content_count"] == 1
    assert cleanup["deleted_content_count"] == 1
    assert cleanup["freed_bytes"] == len("removable text".encode("utf-8"))
    assert summary["content_count"] == 1
    assert saved_article["content_status"] == "full_text_available"
    assert removable_article["content_status"] == "summary_available"
    assert repository.list_articles(include_hidden=True)["total"] == 2


def test_repository_retention_cleanup_does_not_touch_main_database(tmp_path):
    news_engine = create_engine(f"sqlite:///{tmp_path / 'news.db'}")
    main_engine = create_engine(f"sqlite:///{tmp_path / 'cvm_financials.db'}")
    with news_engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
    with main_engine.begin() as conn:
        conn.execute(text("CREATE TABLE sentinel(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO sentinel(value) VALUES ('keep')"))

    repository = NewsRepository(news_engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_content_source(), payload=VALID_RSS, http_status=200)
    repository.update_retention_policy(extracted_text_retention_days=1)
    with news_engine.begin() as conn:
        conn.execute(text("UPDATE news_article_content SET extracted_at = datetime('now', '-2 days')"))

    cleanup = repository.cleanup_extracted_content()
    with main_engine.connect() as conn:
        value = conn.execute(text("SELECT value FROM sentinel WHERE id = 1")).scalar()

    assert cleanup["deleted_content_count"] == 1
    assert value == "keep"


def test_repository_get_article_content_returns_local_copy_without_network(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-content-read.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)

    repository = NewsRepository(engine)
    service = NewsCollectionService(repository)
    service.collect_feed_payload(source=_content_source(), payload=VALID_RSS, http_status=200)
    article = repository.list_articles(include_hidden=True)["items"][0]
    content = repository.get_article_content(article["article_id"])
    missing = repository.get_article_content("missing")

    assert missing is None
    assert content["available"] is True
    assert content["article_id"] == article["article_id"]
    assert content["content_text"] == "Conselho aprovou nova distribuicao."
    assert content["content_format"] == "feed"


def test_repository_updates_source_settings_and_user_source_id_is_stable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-settings.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
    repository = NewsRepository(engine)
    repository.upsert_source(_source())

    assert user_source_id_for_url("https://example.com/feed.xml?utm_source=x") == user_source_id_for_url(
        "https://example.com/feed.xml"
    )
    assert repository.set_source_enabled(source_id="fixture-source", enabled=False) is True
    assert repository.set_source_priority(source_id="fixture-source", priority=7) is True
    assert repository.set_source_enabled(source_id="missing", enabled=True) is False

    row = repository.get_source("fixture-source")
    assert row["enabled"] == 0
    assert row["priority"] == 7


def test_repository_google_company_feed_settings_are_local_and_bounded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-google-settings.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
    repository = NewsRepository(engine)

    defaults = repository.get_google_company_feed_settings()
    updated = repository.update_google_company_feed_settings(
        enabled=True,
        max_companies=999,
        priority=0,
        locale="pt-BR",
        country="br",
    )

    assert defaults["enabled"] == 0
    assert updated["enabled"] == 1
    assert updated["max_companies"] == 250
    assert updated["priority"] == 1
    assert updated["country"] == "BR"
    assert google_company_source_id(9512) == "google_company_9512"


def test_repository_news_company_scope_settings_are_local(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'news-company-scope-settings.db'}")
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)
    repository = NewsRepository(engine)

    defaults = repository.get_company_scope_settings()
    updated = repository.update_company_scope_settings(coverage_universe_id="universe-1")
    cleared = repository.update_company_scope_settings(coverage_universe_id=None)

    assert defaults["coverage_universe_id"] is None
    assert updated["coverage_universe_id"] == "universe-1"
    assert cleared["coverage_universe_id"] is None


def test_validate_feed_url_fetches_and_parses_without_ingesting_articles(tmp_path):
    session = _FakeSession(_FakeResponse(status_code=200, body=VALID_ATOM, url="https://example.com/atom.xml"))
    service, engine = _service_with_fake_fetcher(tmp_path, session)

    result = service.validate_feed_url("https://example.com/atom.xml")

    assert result.status == "success"
    assert result.title == "Global Markets"
    assert result.entry_count == 1
    with engine.connect() as conn:
        article_count = conn.execute(text("SELECT count(*) FROM news_articles")).scalar()
        run_count = conn.execute(text("SELECT count(*) FROM news_collection_runs")).scalar()
    assert article_count == 0
    assert run_count == 0


def test_validate_feed_url_returns_parse_error():
    session = _FakeSession(_FakeResponse(status_code=200, body=b"<not-feed />"))
    fetcher = NewsFeedFetcher(session=session)
    service = NewsCollectionService(NewsRepository(create_engine("sqlite:///:memory:")), fetcher=fetcher)

    result = service.validate_feed_url("https://example.com/feed.xml")

    assert result.status == "error"
    assert "Unsupported feed root" in result.error_message
