from __future__ import annotations

import logging
import threading
from json import dumps
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from src.news.taxonomy import BUILT_IN_EVENT_TYPES, BUILT_IN_KEYWORD_RULES, BUILT_IN_TOPICS
from src.platform.settings import AppSettings

logger = logging.getLogger(__name__)
_ENGINE_BUILD_LOCK = threading.RLock()


def _is_sqlite_locked_error(exc: Exception) -> bool:
    return "database is locked" in str(exc).lower()


def _configure_news_connection(conn, *, enable_wal: bool) -> None:
    conn.execute(text("PRAGMA busy_timeout = 250"))
    if enable_wal:
        try:
            conn.execute(text("PRAGMA journal_mode = WAL"))
        except Exception as exc:
            if not _is_sqlite_locked_error(exc):
                raise
            logger.debug("news WAL setup skipped because database is locked")
    try:
        conn.execute(text("PRAGMA synchronous = OFF"))
    except Exception as exc:
        if not _is_sqlite_locked_error(exc):
            raise
        logger.debug("news synchronous setup skipped because database is locked")
    conn.execute(text("PRAGMA busy_timeout = 5000"))


def _ensure_columns(conn, table_name: str, columns: dict[str, str]) -> None:
    existing = {
        str(row[1])
        for row in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    }
    for column_name, column_type in columns.items():
        if column_name not in existing:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def _has_fts5(conn) -> bool:
    try:
        conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS news_fts5_probe USING fts5(value)"))
        conn.execute(text("DROP TABLE IF EXISTS news_fts5_probe"))
        return True
    except Exception:
        return False


def _seed_classification_catalog(conn) -> None:
    for topic in BUILT_IN_TOPICS:
        conn.execute(
            text("""
                INSERT INTO news_topics (topic_id, label, topic_type, active)
                VALUES (:topic_id, :label, :topic_type, 1)
                ON CONFLICT(topic_id) DO UPDATE SET
                    label = excluded.label,
                    topic_type = excluded.topic_type,
                    active = news_topics.active
            """),
            {
                "topic_id": topic.topic_id,
                "label": topic.label,
                "topic_type": topic.topic_type,
            },
        )

    for event_type in BUILT_IN_EVENT_TYPES:
        conn.execute(
            text("""
                INSERT INTO news_event_types (event_type_id, category, sub_event, active)
                VALUES (:event_type_id, :category, :sub_event, 1)
                ON CONFLICT(event_type_id) DO UPDATE SET
                    category = excluded.category,
                    sub_event = excluded.sub_event,
                    active = news_event_types.active
            """),
            {
                "event_type_id": event_type.event_type_id,
                "category": event_type.category,
                "sub_event": event_type.sub_event,
            },
        )

    for rule in BUILT_IN_KEYWORD_RULES:
        conn.execute(
            text("""
                INSERT INTO news_keyword_rules (
                    keyword_rule_id, group_name, term, aliases_json, priority,
                    cd_cvm, sector_slug, active, user_defined, created_at, updated_at
                )
                VALUES (
                    :keyword_rule_id, :group_name, :term, :aliases_json, :priority,
                    :cd_cvm, :sector_slug, 1, 0, datetime('now'), datetime('now')
                )
                ON CONFLICT(keyword_rule_id) DO UPDATE SET
                    group_name = excluded.group_name,
                    term = excluded.term,
                    aliases_json = excluded.aliases_json,
                    priority = news_keyword_rules.priority,
                    cd_cvm = excluded.cd_cvm,
                    sector_slug = excluded.sector_slug,
                    active = news_keyword_rules.active,
                    user_defined = 0,
                    updated_at = datetime('now')
            """),
            {
                "keyword_rule_id": rule.keyword_rule_id,
                "group_name": rule.group_name,
                "term": rule.term,
                "aliases_json": dumps(list(rule.aliases), ensure_ascii=True),
                "priority": int(rule.priority),
                "cd_cvm": rule.cd_cvm,
                "sector_slug": rule.sector_slug,
            },
        )


def ensure_news_tables_for_connection(conn, *, enable_wal: bool = True) -> None:
    """Create the local News schema. Safe to call repeatedly."""
    _configure_news_connection(conn, enable_wal=enable_wal)

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_schema_capabilities (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_sources (
            source_id        TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            source_type      TEXT NOT NULL,
            reliability_layer TEXT NOT NULL,
            feed_url         TEXT NOT NULL,
            homepage_url     TEXT,
            enabled          INTEGER NOT NULL DEFAULT 1,
            priority         INTEGER NOT NULL DEFAULT 100,
            user_defined     INTEGER NOT NULL DEFAULT 0,
            allow_content_storage INTEGER NOT NULL DEFAULT 0,
            etag             TEXT,
            last_modified    TEXT,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    _ensure_columns(conn, "news_sources", {
        "allow_content_storage": "INTEGER NOT NULL DEFAULT 0",
    })

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_articles (
            article_id       TEXT PRIMARY KEY,
            source_id        TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
            source_item_id   TEXT,
            title            TEXT NOT NULL,
            source_name      TEXT NOT NULL,
            original_url     TEXT NOT NULL,
            canonical_url    TEXT NOT NULL,
            published_at     TEXT,
            discovered_at    TEXT NOT NULL,
            fetched_at       TEXT,
            extracted_at     TEXT,
            summary          TEXT,
            language         TEXT,
            content_status   TEXT NOT NULL DEFAULT 'metadata_only',
            paywall_status   TEXT,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(canonical_url)
        )
    """))

    _ensure_columns(conn, "news_articles", {
        "source_item_id": "TEXT",
        "language": "TEXT",
        "paywall_status": "TEXT",
    })

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_article_content (
            article_id      TEXT PRIMARY KEY REFERENCES news_articles(article_id) ON DELETE CASCADE,
            content_text    TEXT NOT NULL,
            content_format  TEXT NOT NULL DEFAULT 'text',
            source_policy   TEXT,
            storage_bytes   INTEGER NOT NULL DEFAULT 0,
            extracted_at    TEXT NOT NULL DEFAULT (datetime('now')),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_retention_policy (
            policy_id                    TEXT PRIMARY KEY DEFAULT 'default',
            metadata_retention_days       INTEGER NOT NULL DEFAULT 1825,
            extracted_text_retention_days INTEGER NOT NULL DEFAULT 90,
            total_storage_limit_mb        INTEGER NOT NULL DEFAULT 512,
            preserve_saved                INTEGER NOT NULL DEFAULT 1,
            preserve_official_documents   INTEGER NOT NULL DEFAULT 1,
            updated_at                    TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    conn.execute(text("""
        INSERT OR IGNORE INTO news_retention_policy (policy_id)
        VALUES ('default')
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_events (
            event_id        TEXT PRIMARY KEY,
            canonical_title TEXT NOT NULL,
            event_key       TEXT NOT NULL UNIQUE,
            main_article_id TEXT,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_event_articles (
            event_id   TEXT NOT NULL REFERENCES news_events(event_id) ON DELETE CASCADE,
            article_id TEXT NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
            role       TEXT NOT NULL DEFAULT 'related',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (event_id, article_id)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_article_companies (
            article_id       TEXT NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
            cd_cvm           INTEGER NOT NULL,
            match_method     TEXT NOT NULL,
            match_reason     TEXT NOT NULL,
            relevance_score  REAL,
            rule_strength    REAL,
            is_primary       INTEGER NOT NULL DEFAULT 0,
            manually_reviewed INTEGER NOT NULL DEFAULT 0,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (article_id, cd_cvm, match_method, match_reason)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_article_sectors (
            article_id       TEXT NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
            sector_slug      TEXT NOT NULL,
            sector_name      TEXT NOT NULL,
            parent_sector_slug TEXT,
            parent_sector_name TEXT,
            match_method     TEXT NOT NULL,
            match_reason     TEXT NOT NULL,
            relevance_score  REAL,
            rule_strength    REAL,
            is_primary       INTEGER NOT NULL DEFAULT 0,
            manually_reviewed INTEGER NOT NULL DEFAULT 0,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (article_id, sector_slug, match_method, match_reason)
        )
    """))
    _ensure_columns(conn, "news_article_sectors", {
        "parent_sector_slug": "TEXT",
        "parent_sector_name": "TEXT",
    })

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_topics (
            topic_id   TEXT PRIMARY KEY,
            label      TEXT NOT NULL,
            topic_type TEXT NOT NULL,
            active     INTEGER NOT NULL DEFAULT 1
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_article_topics (
            article_id      TEXT NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
            topic_id        TEXT NOT NULL REFERENCES news_topics(topic_id),
            match_method    TEXT NOT NULL,
            match_reason    TEXT NOT NULL,
            relevance_score REAL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (article_id, topic_id, match_method)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_event_types (
            event_type_id TEXT PRIMARY KEY,
            category      TEXT NOT NULL,
            sub_event     TEXT,
            active        INTEGER NOT NULL DEFAULT 1,
            UNIQUE(category, sub_event)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_article_event_types (
            article_id      TEXT NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
            event_type_id   TEXT NOT NULL REFERENCES news_event_types(event_type_id),
            match_method    TEXT NOT NULL,
            match_reason    TEXT NOT NULL,
            relevance_score REAL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (article_id, event_type_id, match_method)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_keyword_rules (
            keyword_rule_id TEXT PRIMARY KEY,
            group_name      TEXT NOT NULL,
            term            TEXT NOT NULL,
            aliases_json    TEXT,
            priority        INTEGER NOT NULL DEFAULT 100,
            cd_cvm          INTEGER,
            sector_slug     TEXT,
            active          INTEGER NOT NULL DEFAULT 1,
            user_defined    INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_article_keyword_matches (
            article_id       TEXT NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
            keyword_rule_id  TEXT NOT NULL REFERENCES news_keyword_rules(keyword_rule_id),
            matched_term     TEXT NOT NULL,
            match_method     TEXT NOT NULL,
            match_reason     TEXT NOT NULL,
            relevance_score  REAL,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (article_id, keyword_rule_id, matched_term)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_user_state (
            article_id TEXT PRIMARY KEY REFERENCES news_articles(article_id) ON DELETE CASCADE,
            read       INTEGER NOT NULL DEFAULT 0,
            saved      INTEGER NOT NULL DEFAULT 0,
            hidden     INTEGER NOT NULL DEFAULT 0,
            read_later INTEGER NOT NULL DEFAULT 0,
            notes      TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_article_scores (
            article_id      TEXT PRIMARY KEY REFERENCES news_articles(article_id) ON DELETE CASCADE,
            total_score     REAL NOT NULL DEFAULT 0,
            priority_level  TEXT NOT NULL DEFAULT 'Normal',
            components_json TEXT NOT NULL,
            reasons_json    TEXT NOT NULL,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_classification_corrections (
            correction_id       TEXT PRIMARY KEY,
            article_id          TEXT NOT NULL REFERENCES news_articles(article_id) ON DELETE CASCADE,
            target_type         TEXT NOT NULL,
            target_id           TEXT NOT NULL,
            original_value_json TEXT,
            original_match_reason TEXT,
            user_value_json     TEXT NOT NULL,
            correction_action   TEXT NOT NULL,
            rule_suggestion     TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_company_scope_overrides (
            cd_cvm     INTEGER PRIMARY KEY,
            action     TEXT NOT NULL CHECK(action IN ('include', 'exclude')),
            reason     TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_collection_runs (
            run_id          TEXT PRIMARY KEY,
            trigger         TEXT NOT NULL,
            status          TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            source_count    INTEGER NOT NULL DEFAULT 0,
            articles_seen   INTEGER NOT NULL DEFAULT 0,
            articles_inserted INTEGER NOT NULL DEFAULT 0,
            articles_updated INTEGER NOT NULL DEFAULT 0,
            error_count     INTEGER NOT NULL DEFAULT 0,
            error_message   TEXT
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS news_source_health (
            source_id          TEXT PRIMARY KEY REFERENCES news_sources(source_id) ON DELETE CASCADE,
            last_attempt_at    TEXT,
            last_success_at    TEXT,
            last_status        TEXT,
            last_error         TEXT,
            last_http_status   INTEGER,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_article_count INTEGER NOT NULL DEFAULT 0,
            updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    indexes = (
        "CREATE INDEX IF NOT EXISTS idx_news_articles_source_published ON news_articles(source_id, published_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_news_articles_published ON news_articles(published_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_news_articles_discovered ON news_articles(discovered_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_news_articles_canonical_url ON news_articles(canonical_url)",
        "CREATE INDEX IF NOT EXISTS idx_news_article_content_extracted ON news_article_content(extracted_at, storage_bytes)",
        "CREATE INDEX IF NOT EXISTS idx_news_article_companies_cd_cvm ON news_article_companies(cd_cvm, article_id)",
        "CREATE INDEX IF NOT EXISTS idx_news_article_sectors_slug ON news_article_sectors(sector_slug, article_id)",
        "CREATE INDEX IF NOT EXISTS idx_news_user_state_saved ON news_user_state(saved, article_id)",
        "CREATE INDEX IF NOT EXISTS idx_news_user_state_hidden ON news_user_state(hidden, article_id)",
        "CREATE INDEX IF NOT EXISTS idx_news_keyword_active ON news_keyword_rules(active, group_name)",
        "CREATE INDEX IF NOT EXISTS idx_news_article_scores_priority ON news_article_scores(priority_level, total_score DESC)",
        "CREATE INDEX IF NOT EXISTS idx_news_company_scope_overrides_action ON news_company_scope_overrides(action, cd_cvm)",
    )
    for ddl in indexes:
        conn.execute(text(ddl))

    _seed_classification_catalog(conn)

    fts_available = _has_fts5(conn)
    conn.execute(
        text("""
            INSERT OR REPLACE INTO news_schema_capabilities (key, value, updated_at)
            VALUES ('fts5', :value, datetime('now'))
        """),
        {"value": "1" if fts_available else "0"},
    )
    if fts_available:
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS news_articles_fts
            USING fts5(article_id UNINDEXED, title, summary, tokenize='unicode61 remove_diacritics 2')
        """))


def ensure_news_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        ensure_news_tables_for_connection(conn)


@lru_cache(maxsize=1)
def _build_news_engine(db_url: str) -> Engine:
    engine = create_engine(db_url, connect_args={"check_same_thread": False, "timeout": 5.0})
    ensure_news_tables(engine)
    return engine


def get_news_engine(settings: AppSettings) -> Engine:
    settings.paths.news_db_path.parent.mkdir(parents=True, exist_ok=True)
    with _ENGINE_BUILD_LOCK:
        return _build_news_engine(settings.paths.news_sqlite_url)
