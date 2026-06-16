from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from json import dumps, loads
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import Engine, text

from src.news.classifier import ArticleClassification
from src.news.feed_parser import ParsedFeedEntry
from src.news.scoring import ArticleScore

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_NAMES = {
    "fbclid",
    "gclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "yclid",
}


@dataclass(frozen=True)
class NewsSource:
    source_id: str
    name: str
    source_type: str
    reliability_layer: str
    feed_url: str
    homepage_url: str | None = None
    enabled: bool = True
    priority: int = 100
    user_defined: bool = False


@dataclass(frozen=True)
class ArticleUpsertResult:
    article_id: str
    inserted: bool
    updated: bool


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(str(url).strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_QUERY_NAMES or any(lowered.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items))
    return urlunsplit((scheme, netloc, path, query, ""))


def article_id_for_url(canonical_url: str) -> str:
    return "art_" + sha256(canonical_url.encode("utf-8")).hexdigest()[:32]


def user_source_id_for_url(feed_url: str) -> str:
    return "user_" + sha256(canonicalize_url(feed_url).encode("utf-8")).hexdigest()[:24]


def _decode_aliases(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        decoded = loads(value)
    except Exception:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded if str(item).strip()]


def _decode_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = loads(value)
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _decode_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        decoded = loads(value)
    except Exception:
        return []
    if not isinstance(decoded, list):
        return []
    return [str(item) for item in decoded]


def _decode_article_row(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["relevance_components"] = _decode_json_object(item.pop("relevance_components_json", None))
    item["relevance_reasons"] = _decode_json_list(item.pop("relevance_reasons_json", None))
    return item


def _decode_score_row(row: Any | None) -> dict[str, Any] | None:
    if not row:
        return None
    item = dict(row)
    item["components"] = _decode_json_object(item.pop("components_json", None))
    item["reasons"] = _decode_json_list(item.pop("reasons_json", None))
    return item


def _decode_correction_row(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["original_value"] = _decode_json_list_or_object(item.pop("original_value_json", None))
    item["user_value"] = _decode_json_object(item.pop("user_value_json", None))
    return item


def _decode_json_list_or_object(value: str | None) -> list[Any] | dict[str, Any]:
    if not value:
        return []
    try:
        decoded = loads(value)
    except Exception:
        return []
    return decoded if isinstance(decoded, (list, dict)) else []


def _first_match_reason(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        reason = row.get("match_reason")
        if reason:
            return str(reason)
    return None


def _company_scope_filter(company_scope_ids: set[int] | None) -> tuple[str, dict[str, Any]]:
    if company_scope_ids is None:
        return (
            "EXISTS (SELECT 1 FROM news_article_companies c WHERE c.article_id = a.article_id)",
            {},
        )
    if not company_scope_ids:
        return ("0 = 1", {})
    params = {f"company_scope_{idx}": int(cd_cvm) for idx, cd_cvm in enumerate(sorted(company_scope_ids))}
    placeholders = ", ".join(f":{key}" for key in params)
    return (
        f"""
            EXISTS (
                SELECT 1
                FROM news_article_companies c
                WHERE c.article_id = a.article_id
                  AND c.cd_cvm IN ({placeholders})
            )
        """,
        params,
    )


class NewsRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def upsert_source(self, source: NewsSource) -> None:
        now = utc_now_iso()
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO news_sources (
                        source_id, name, source_type, reliability_layer, feed_url,
                        homepage_url, enabled, priority, user_defined, created_at, updated_at
                    )
                    VALUES (
                        :source_id, :name, :source_type, :reliability_layer, :feed_url,
                        :homepage_url, :enabled, :priority, :user_defined, :now, :now
                    )
                    ON CONFLICT(source_id) DO UPDATE SET
                        name = excluded.name,
                        source_type = excluded.source_type,
                        reliability_layer = excluded.reliability_layer,
                        feed_url = excluded.feed_url,
                        homepage_url = excluded.homepage_url,
                        enabled = excluded.enabled,
                        priority = excluded.priority,
                        user_defined = excluded.user_defined,
                        updated_at = excluded.updated_at
                """),
                {
                    "source_id": source.source_id,
                    "name": source.name,
                    "source_type": source.source_type,
                    "reliability_layer": source.reliability_layer,
                    "feed_url": source.feed_url,
                    "homepage_url": source.homepage_url,
                    "enabled": 1 if source.enabled else 0,
                    "priority": int(source.priority),
                    "user_defined": 1 if source.user_defined else 0,
                    "now": now,
                },
            )

    def register_source(self, source: NewsSource) -> None:
        now = utc_now_iso()
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO news_sources (
                        source_id, name, source_type, reliability_layer, feed_url,
                        homepage_url, enabled, priority, user_defined, created_at, updated_at
                    )
                    VALUES (
                        :source_id, :name, :source_type, :reliability_layer, :feed_url,
                        :homepage_url, :enabled, :priority, :user_defined, :now, :now
                    )
                    ON CONFLICT(source_id) DO UPDATE SET
                        name = excluded.name,
                        source_type = excluded.source_type,
                        reliability_layer = excluded.reliability_layer,
                        feed_url = excluded.feed_url,
                        homepage_url = excluded.homepage_url,
                        user_defined = excluded.user_defined,
                        updated_at = excluded.updated_at
                """),
                {
                    "source_id": source.source_id,
                    "name": source.name,
                    "source_type": source.source_type,
                    "reliability_layer": source.reliability_layer,
                    "feed_url": source.feed_url,
                    "homepage_url": source.homepage_url,
                    "enabled": 1 if source.enabled else 0,
                    "priority": int(source.priority),
                    "user_defined": 1 if source.user_defined else 0,
                    "now": now,
                },
            )

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM news_sources WHERE source_id = :source_id"),
                {"source_id": source_id},
            ).mappings().fetchone()
        return dict(row) if row else None

    def list_sources(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        s.source_id,
                        s.name,
                        s.source_type,
                        s.reliability_layer,
                        s.feed_url,
                        s.homepage_url,
                        s.enabled,
                        s.priority,
                        s.user_defined,
                        s.etag,
                        s.last_modified,
                        s.updated_at,
                        h.last_attempt_at,
                        h.last_success_at,
                        h.last_status,
                        h.last_error,
                        h.last_http_status,
                        h.consecutive_failures,
                        h.last_article_count
                    FROM news_sources s
                    LEFT JOIN news_source_health h ON h.source_id = s.source_id
                    ORDER BY s.priority ASC, s.name ASC
                """)
            ).mappings().fetchall()
        return [dict(row) for row in rows]

    def list_articles(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        source_id: str | None = None,
        include_hidden: bool = False,
        order: str = "latest",
    ) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 200))
        bounded_offset = max(0, int(offset))
        filters = []
        params: dict[str, Any] = {
            "limit": bounded_limit,
            "offset": bounded_offset,
        }
        if source_id:
            filters.append("a.source_id = :source_id")
            params["source_id"] = source_id
        if not include_hidden:
            filters.append("COALESCE(u.hidden, 0) = 0")
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        if order == "top":
            order_sql = """
                ORDER BY
                    COALESCE(sc.total_score, 0) DESC,
                    CASE COALESCE(sc.priority_level, 'Normal')
                        WHEN 'Critical' THEN 3
                        WHEN 'High' THEN 2
                        ELSE 1
                    END DESC,
                    COALESCE(a.published_at, a.discovered_at) DESC,
                    a.discovered_at DESC
            """
        else:
            order_sql = "ORDER BY COALESCE(a.published_at, a.discovered_at) DESC, a.discovered_at DESC"
        with self.engine.connect() as conn:
            total = conn.execute(
                text(f"""
                    SELECT COUNT(*)
                    FROM news_articles a
                    LEFT JOIN news_user_state u ON u.article_id = a.article_id
                    {where_sql}
                """),
                params,
            ).scalar()
            rows = conn.execute(
                text(f"""
                    SELECT
                        a.article_id,
                        a.source_id,
                        a.source_item_id,
                        a.title,
                        a.source_name,
                        a.original_url,
                        a.canonical_url,
                        a.published_at,
                        a.discovered_at,
                        a.fetched_at,
                        a.summary,
                        a.language,
                        a.content_status,
                        a.paywall_status,
                        COALESCE(u.read, 0) AS read,
                        COALESCE(u.saved, 0) AS saved,
                        COALESCE(u.hidden, 0) AS hidden,
                        COALESCE(u.read_later, 0) AS read_later,
                        u.notes,
                        COALESCE(sc.total_score, 0) AS relevance_score,
                        COALESCE(sc.priority_level, 'Normal') AS priority_level,
                        sc.components_json AS relevance_components_json,
                        sc.reasons_json AS relevance_reasons_json
                    FROM news_articles a
                    LEFT JOIN news_user_state u ON u.article_id = a.article_id
                    LEFT JOIN news_article_scores sc ON sc.article_id = a.article_id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """),
                params,
            ).mappings().fetchall()
        return {
            "items": [_decode_article_row(row) for row in rows],
            "count": len(rows),
            "total": int(total or 0),
            "limit": bounded_limit,
            "offset": bounded_offset,
            "order": "top" if order == "top" else "latest",
        }

    def list_overview(
        self,
        *,
        limit_per_section: int = 6,
        company_scope_ids: set[int] | None = None,
    ) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit_per_section), 20))
        company_scope_where, company_scope_params = _company_scope_filter(company_scope_ids)
        sections = [
            {
                "section_id": "critical_news",
                "title": "Critical News",
                "reason": "Articles with Critical priority from deterministic scoring.",
                "items": self._list_overview_articles(
                    extra_where="COALESCE(sc.priority_level, 'Normal') = 'Critical'",
                    limit=bounded_limit,
                    order="top",
                ),
            },
            {
                "section_id": "top_market_news",
                "title": "Top Market News",
                "reason": "Highest ranked local articles using explainable score components.",
                "items": self._list_overview_articles(limit=bounded_limit, order="top"),
            },
            {
                "section_id": "macro_watch",
                "title": "Macro Watch",
                "reason": "Articles matched to macro topics or macro keyword rules.",
                "items": self._list_overview_articles(
                    extra_where="""
                        EXISTS (
                            SELECT 1
                            FROM news_article_topics at
                            JOIN news_topics t ON t.topic_id = at.topic_id
                            WHERE at.article_id = a.article_id
                              AND t.topic_type = 'macro'
                        )
                        OR EXISTS (
                            SELECT 1
                            FROM news_article_keyword_matches km
                            JOIN news_keyword_rules kr ON kr.keyword_rule_id = km.keyword_rule_id
                            WHERE km.article_id = a.article_id
                              AND lower(kr.group_name) = 'macro'
                        )
                    """,
                    limit=bounded_limit,
                    order="top",
                ),
            },
            {
                "section_id": "my_companies",
                "title": "My Companies",
                "reason": "Articles matched to the coverage universe plus News-specific inclusions, excluding News-specific exclusions.",
                "items": self._list_overview_articles(
                    extra_where=company_scope_where,
                    extra_params=company_scope_params,
                    limit=bounded_limit,
                    order="top",
                ),
            },
            {
                "section_id": "my_sectors",
                "title": "My Sectors",
                "reason": "Articles with deterministic sector associations.",
                "items": self._list_overview_articles(
                    extra_where="EXISTS (SELECT 1 FROM news_article_sectors s WHERE s.article_id = a.article_id)",
                    limit=bounded_limit,
                    order="top",
                ),
            },
            {
                "section_id": "keyword_alerts",
                "title": "Keyword Alerts",
                "reason": "Articles matched to active keyword rules.",
                "items": self._list_overview_articles(
                    extra_where="EXISTS (SELECT 1 FROM news_article_keyword_matches k WHERE k.article_id = a.article_id)",
                    limit=bounded_limit,
                    order="top",
                ),
            },
            {
                "section_id": "all_news",
                "title": "All News",
                "reason": "Most recent local articles, without ranking.",
                "items": self._list_overview_articles(limit=bounded_limit, order="latest"),
            },
        ]
        return {"sections": sections, "limit_per_section": bounded_limit}

    def _list_overview_articles(
        self,
        *,
        limit: int,
        order: str,
        extra_where: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        filters = ["COALESCE(u.hidden, 0) = 0"]
        if extra_where:
            filters.append(f"({extra_where})")
        where_sql = f"WHERE {' AND '.join(filters)}"
        if order == "top":
            order_sql = """
                ORDER BY
                    COALESCE(sc.total_score, 0) DESC,
                    CASE COALESCE(sc.priority_level, 'Normal')
                        WHEN 'Critical' THEN 3
                        WHEN 'High' THEN 2
                        ELSE 1
                    END DESC,
                    COALESCE(a.published_at, a.discovered_at) DESC,
                    a.discovered_at DESC
            """
        else:
            order_sql = "ORDER BY COALESCE(a.published_at, a.discovered_at) DESC, a.discovered_at DESC"
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT
                        a.article_id,
                        a.source_id,
                        a.source_item_id,
                        a.title,
                        a.source_name,
                        a.original_url,
                        a.canonical_url,
                        a.published_at,
                        a.discovered_at,
                        a.fetched_at,
                        a.summary,
                        a.language,
                        a.content_status,
                        a.paywall_status,
                        COALESCE(u.read, 0) AS read,
                        COALESCE(u.saved, 0) AS saved,
                        COALESCE(u.hidden, 0) AS hidden,
                        COALESCE(u.read_later, 0) AS read_later,
                        u.notes,
                        COALESCE(sc.total_score, 0) AS relevance_score,
                        COALESCE(sc.priority_level, 'Normal') AS priority_level,
                        sc.components_json AS relevance_components_json,
                        sc.reasons_json AS relevance_reasons_json
                    FROM news_articles a
                    LEFT JOIN news_user_state u ON u.article_id = a.article_id
                    LEFT JOIN news_article_scores sc ON sc.article_id = a.article_id
                    {where_sql}
                    {order_sql}
                    LIMIT :limit
                """),
                {"limit": limit, **(extra_params or {})},
            ).mappings().fetchall()
        return [_decode_article_row(row) for row in rows]

    def list_company_scope_overrides(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT cd_cvm, action, reason, created_at, updated_at
                    FROM news_company_scope_overrides
                    ORDER BY action ASC, cd_cvm ASC
                """)
            ).mappings().fetchall()
        return [dict(row) for row in rows]

    def set_company_scope_override(
        self,
        *,
        cd_cvm: int,
        action: str | None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        company_id = int(cd_cvm)
        normalized_action = str(action or "").strip().lower()
        with self.engine.begin() as conn:
            if not normalized_action:
                deleted = conn.execute(
                    text("DELETE FROM news_company_scope_overrides WHERE cd_cvm = :cd_cvm"),
                    {"cd_cvm": company_id},
                ).rowcount
                return {"status": "success", "cd_cvm": company_id, "action": None, "deleted": bool(deleted)}
            if normalized_action not in {"include", "exclude"}:
                return {"status": "error", "error": "action must be include, exclude, or empty"}
            conn.execute(
                text("""
                    INSERT INTO news_company_scope_overrides (
                        cd_cvm, action, reason, created_at, updated_at
                    )
                    VALUES (:cd_cvm, :action, :reason, datetime('now'), datetime('now'))
                    ON CONFLICT(cd_cvm) DO UPDATE SET
                        action = excluded.action,
                        reason = excluded.reason,
                        updated_at = excluded.updated_at
                """),
                {"cd_cvm": company_id, "action": normalized_action, "reason": reason},
            )
        return {"status": "success", "cd_cvm": company_id, "action": normalized_action}

    def list_topics(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        where_sql = "WHERE active = 1" if active_only else ""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT topic_id, label, topic_type, active
                    FROM news_topics
                    {where_sql}
                    ORDER BY topic_type ASC, label ASC
                """)
            ).mappings().fetchall()
        return [dict(row) for row in rows]

    def list_event_types(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        where_sql = "WHERE active = 1" if active_only else ""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT event_type_id, category, sub_event, active
                    FROM news_event_types
                    {where_sql}
                    ORDER BY category ASC, COALESCE(sub_event, '') ASC
                """)
            ).mappings().fetchall()
        return [dict(row) for row in rows]

    def list_keyword_rules(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        where_sql = "WHERE active = 1" if active_only else ""
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"""
                    SELECT
                        keyword_rule_id,
                        group_name,
                        term,
                        aliases_json,
                        priority,
                        cd_cvm,
                        sector_slug,
                        active,
                        user_defined
                    FROM news_keyword_rules
                    {where_sql}
                    ORDER BY priority ASC, group_name ASC, term ASC
                """)
            ).mappings().fetchall()
        rules: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["aliases"] = _decode_aliases(item.pop("aliases_json", None))
            rules.append(item)
        return rules

    def replace_article_classification(
        self,
        *,
        article_id: str,
        classification: ArticleClassification,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    DELETE FROM news_article_keyword_matches
                    WHERE article_id = :article_id AND match_method = 'keyword_exact'
                """),
                {"article_id": article_id},
            )
            conn.execute(
                text("""
                    DELETE FROM news_article_topics
                    WHERE article_id = :article_id AND match_method = 'keyword_rule'
                """),
                {"article_id": article_id},
            )
            conn.execute(
                text("""
                    DELETE FROM news_article_event_types
                    WHERE article_id = :article_id AND match_method = 'keyword_rule'
                """),
                {"article_id": article_id},
            )
            conn.execute(
                text("""
                    DELETE FROM news_article_companies
                    WHERE article_id = :article_id
                      AND match_method IN ('ticker', 'cnpj', 'trade_name', 'legal_name')
                """),
                {"article_id": article_id},
            )
            conn.execute(
                text("""
                    DELETE FROM news_article_sectors
                    WHERE article_id = :article_id
                      AND match_method IN ('company_sector', 'company_sub_industry')
                """),
                {"article_id": article_id},
            )
            for match in classification.keyword_matches:
                conn.execute(
                    text("""
                        INSERT INTO news_article_keyword_matches (
                            article_id, keyword_rule_id, matched_term, match_method,
                            match_reason, relevance_score, created_at
                        )
                        VALUES (
                            :article_id, :keyword_rule_id, :matched_term, :match_method,
                            :match_reason, :relevance_score, datetime('now')
                        )
                    """),
                    {
                        "article_id": article_id,
                        "keyword_rule_id": match.keyword_rule_id,
                        "matched_term": match.matched_term,
                        "match_method": match.match_method,
                        "match_reason": match.match_reason,
                        "relevance_score": match.relevance_score,
                    },
                )
            for match in classification.topic_matches:
                conn.execute(
                    text("""
                        INSERT INTO news_article_topics (
                            article_id, topic_id, match_method, match_reason,
                            relevance_score, created_at
                        )
                        VALUES (
                            :article_id, :topic_id, :match_method, :match_reason,
                            :relevance_score, datetime('now')
                        )
                    """),
                    {
                        "article_id": article_id,
                        "topic_id": match.topic_id,
                        "match_method": match.match_method,
                        "match_reason": match.match_reason,
                        "relevance_score": match.relevance_score,
                    },
                )
            for match in classification.event_type_matches:
                conn.execute(
                    text("""
                        INSERT INTO news_article_event_types (
                            article_id, event_type_id, match_method, match_reason,
                            relevance_score, created_at
                        )
                        VALUES (
                            :article_id, :event_type_id, :match_method, :match_reason,
                            :relevance_score, datetime('now')
                        )
                    """),
                    {
                        "article_id": article_id,
                        "event_type_id": match.event_type_id,
                        "match_method": match.match_method,
                        "match_reason": match.match_reason,
                        "relevance_score": match.relevance_score,
                    },
                )
            for match in classification.company_matches:
                conn.execute(
                    text("""
                        INSERT INTO news_article_companies (
                            article_id, cd_cvm, match_method, match_reason,
                            relevance_score, rule_strength, is_primary,
                            manually_reviewed, created_at
                        )
                        VALUES (
                            :article_id, :cd_cvm, :match_method, :match_reason,
                            :relevance_score, :rule_strength, :is_primary,
                            0, datetime('now')
                        )
                    """),
                    {
                        "article_id": article_id,
                        "cd_cvm": int(match.cd_cvm),
                        "match_method": match.match_method,
                        "match_reason": match.match_reason,
                        "relevance_score": match.relevance_score,
                        "rule_strength": match.rule_strength,
                        "is_primary": 1 if match.is_primary else 0,
                    },
                )
            for match in classification.sector_matches:
                conn.execute(
                    text("""
                        INSERT INTO news_article_sectors (
                            article_id, sector_slug, sector_name,
                            parent_sector_slug, parent_sector_name,
                            match_method, match_reason, relevance_score,
                            rule_strength, is_primary, manually_reviewed, created_at
                        )
                        VALUES (
                            :article_id, :sector_slug, :sector_name,
                            :parent_sector_slug, :parent_sector_name,
                            :match_method, :match_reason, :relevance_score,
                            :rule_strength, :is_primary, 0, datetime('now')
                        )
                    """),
                    {
                        "article_id": article_id,
                        "sector_slug": match.sector_slug,
                        "sector_name": match.sector_name,
                        "parent_sector_slug": match.parent_sector_slug,
                        "parent_sector_name": match.parent_sector_name,
                        "match_method": match.match_method,
                        "match_reason": match.match_reason,
                        "relevance_score": match.relevance_score,
                        "rule_strength": match.rule_strength,
                        "is_primary": 1 if match.is_primary else 0,
                    },
                )

    def get_article_classification(self, article_id: str) -> dict[str, list[dict[str, Any]]]:
        with self.engine.connect() as conn:
            keyword_matches = conn.execute(
                text("""
                    SELECT
                        m.keyword_rule_id,
                        r.group_name,
                        r.term,
                        m.matched_term,
                        m.match_method,
                        m.match_reason,
                        m.relevance_score
                    FROM news_article_keyword_matches m
                    JOIN news_keyword_rules r ON r.keyword_rule_id = m.keyword_rule_id
                    WHERE m.article_id = :article_id
                    ORDER BY m.relevance_score DESC, r.priority ASC, r.term ASC
                """),
                {"article_id": article_id},
            ).mappings().fetchall()
            topics = conn.execute(
                text("""
                    SELECT
                        t.topic_id,
                        t.label,
                        t.topic_type,
                        at.match_method,
                        at.match_reason,
                        at.relevance_score
                    FROM news_article_topics at
                    JOIN news_topics t ON t.topic_id = at.topic_id
                    WHERE at.article_id = :article_id
                    ORDER BY at.relevance_score DESC, t.topic_type ASC, t.label ASC
                """),
                {"article_id": article_id},
            ).mappings().fetchall()
            event_types = conn.execute(
                text("""
                    SELECT
                        et.event_type_id,
                        et.category,
                        et.sub_event,
                        aet.match_method,
                        aet.match_reason,
                        aet.relevance_score
                    FROM news_article_event_types aet
                    JOIN news_event_types et ON et.event_type_id = aet.event_type_id
                    WHERE aet.article_id = :article_id
                    ORDER BY aet.relevance_score DESC, et.category ASC, et.sub_event ASC
                """),
                {"article_id": article_id},
            ).mappings().fetchall()
            companies = conn.execute(
                text("""
                    SELECT
                        cd_cvm,
                        match_method,
                        match_reason,
                        relevance_score,
                        rule_strength,
                        is_primary,
                        manually_reviewed
                    FROM news_article_companies
                    WHERE article_id = :article_id
                    ORDER BY is_primary DESC, relevance_score DESC, rule_strength DESC, cd_cvm ASC
                """),
                {"article_id": article_id},
            ).mappings().fetchall()
            sectors = conn.execute(
                text("""
                    SELECT
                        sector_slug,
                        sector_name,
                        parent_sector_slug,
                        parent_sector_name,
                        match_method,
                        match_reason,
                        relevance_score,
                        rule_strength,
                        is_primary,
                        manually_reviewed
                    FROM news_article_sectors
                    WHERE article_id = :article_id
                    ORDER BY is_primary DESC, relevance_score DESC, rule_strength DESC, sector_name ASC
                """),
                {"article_id": article_id},
            ).mappings().fetchall()
            score = conn.execute(
                text("""
                    SELECT total_score, priority_level, components_json, reasons_json, updated_at
                    FROM news_article_scores
                    WHERE article_id = :article_id
                """),
                {"article_id": article_id},
            ).mappings().fetchone()
            corrections = conn.execute(
                text("""
                    SELECT
                        correction_id,
                        article_id,
                        target_type,
                        target_id,
                        original_value_json,
                        original_match_reason,
                        user_value_json,
                        correction_action,
                        rule_suggestion,
                        created_at
                    FROM news_classification_corrections
                    WHERE article_id = :article_id
                    ORDER BY created_at DESC
                """),
                {"article_id": article_id},
            ).mappings().fetchall()
        return {
            "keywords": [dict(row) for row in keyword_matches],
            "topics": [dict(row) for row in topics],
            "event_types": [dict(row) for row in event_types],
            "companies": [dict(row) for row in companies],
            "sectors": [dict(row) for row in sectors],
            "score": _decode_score_row(score),
            "corrections": [_decode_correction_row(row) for row in corrections],
        }

    def apply_classification_correction(
        self,
        *,
        article_id: str,
        target_type: str,
        target_id: str,
        action: str,
        user_value: dict[str, Any] | None = None,
        rule_suggestion: str | None = None,
    ) -> dict[str, Any]:
        normalized_type = str(target_type).strip().lower()
        normalized_action = str(action).strip().lower()
        if normalized_type not in {"company", "sector", "topic", "event_type", "keyword"}:
            return {"status": "error", "error": "Unsupported correction target_type"}
        if normalized_action not in {"add", "remove"}:
            return {"status": "error", "error": "Unsupported correction action"}
        clean_target_id = str(target_id).strip()
        if not clean_target_id:
            return {"status": "error", "error": "target_id is required"}

        payload = dict(user_value or {})
        with self.engine.begin() as conn:
            article_exists = conn.execute(
                text("SELECT 1 FROM news_articles WHERE article_id = :article_id"),
                {"article_id": article_id},
            ).scalar()
            if not article_exists:
                return {"status": "not_found", "error": f"News article {article_id} not found"}

            original_rows = self._classification_target_rows(
                conn,
                article_id=article_id,
                target_type=normalized_type,
                target_id=clean_target_id,
            )
            original_reason = _first_match_reason(original_rows)

            if normalized_action == "remove":
                self._remove_classification_target(
                    conn,
                    article_id=article_id,
                    target_type=normalized_type,
                    target_id=clean_target_id,
                )
            else:
                insert_error = self._add_manual_classification_target(
                    conn,
                    article_id=article_id,
                    target_type=normalized_type,
                    target_id=clean_target_id,
                    payload=payload,
                )
                if insert_error:
                    return {"status": "error", "error": insert_error}

            correction_id = f"corr_{uuid4().hex}"
            conn.execute(
                text("""
                    INSERT INTO news_classification_corrections (
                        correction_id,
                        article_id,
                        target_type,
                        target_id,
                        original_value_json,
                        original_match_reason,
                        user_value_json,
                        correction_action,
                        rule_suggestion,
                        created_at
                    )
                    VALUES (
                        :correction_id,
                        :article_id,
                        :target_type,
                        :target_id,
                        :original_value_json,
                        :original_match_reason,
                        :user_value_json,
                        :correction_action,
                        :rule_suggestion,
                        datetime('now')
                    )
                """),
                {
                    "correction_id": correction_id,
                    "article_id": article_id,
                    "target_type": normalized_type,
                    "target_id": clean_target_id,
                    "original_value_json": dumps(original_rows, ensure_ascii=True, sort_keys=True),
                    "original_match_reason": original_reason,
                    "user_value_json": dumps(payload, ensure_ascii=True, sort_keys=True),
                    "correction_action": normalized_action,
                    "rule_suggestion": str(rule_suggestion).strip() if rule_suggestion else None,
                },
            )
        return {
            "status": "success",
            "correction_id": correction_id,
            "article_id": article_id,
            "target_type": normalized_type,
            "target_id": clean_target_id,
            "correction_action": normalized_action,
        }

    def _classification_target_rows(
        self,
        conn,
        *,
        article_id: str,
        target_type: str,
        target_id: str,
    ) -> list[dict[str, Any]]:
        query_map = {
            "company": ("SELECT * FROM news_article_companies WHERE article_id = :article_id AND cd_cvm = :target_id", {"target_id": int(target_id)}),
            "sector": ("SELECT * FROM news_article_sectors WHERE article_id = :article_id AND sector_slug = :target_id", {"target_id": target_id}),
            "topic": ("SELECT * FROM news_article_topics WHERE article_id = :article_id AND topic_id = :target_id", {"target_id": target_id}),
            "event_type": ("SELECT * FROM news_article_event_types WHERE article_id = :article_id AND event_type_id = :target_id", {"target_id": target_id}),
            "keyword": ("SELECT * FROM news_article_keyword_matches WHERE article_id = :article_id AND keyword_rule_id = :target_id", {"target_id": target_id}),
        }
        sql, params = query_map[target_type]
        rows = conn.execute(text(sql), {"article_id": article_id, **params}).mappings().fetchall()
        return [dict(row) for row in rows]

    def _remove_classification_target(
        self,
        conn,
        *,
        article_id: str,
        target_type: str,
        target_id: str,
    ) -> None:
        delete_map = {
            "company": ("DELETE FROM news_article_companies WHERE article_id = :article_id AND cd_cvm = :target_id", {"target_id": int(target_id)}),
            "sector": ("DELETE FROM news_article_sectors WHERE article_id = :article_id AND sector_slug = :target_id", {"target_id": target_id}),
            "topic": ("DELETE FROM news_article_topics WHERE article_id = :article_id AND topic_id = :target_id", {"target_id": target_id}),
            "event_type": ("DELETE FROM news_article_event_types WHERE article_id = :article_id AND event_type_id = :target_id", {"target_id": target_id}),
            "keyword": ("DELETE FROM news_article_keyword_matches WHERE article_id = :article_id AND keyword_rule_id = :target_id", {"target_id": target_id}),
        }
        sql, params = delete_map[target_type]
        conn.execute(text(sql), {"article_id": article_id, **params})

    def _add_manual_classification_target(
        self,
        conn,
        *,
        article_id: str,
        target_type: str,
        target_id: str,
        payload: dict[str, Any],
    ) -> str | None:
        reason = str(payload.get("match_reason") or "Manual user correction").strip()
        if target_type == "company":
            conn.execute(
                text("""
                    INSERT OR REPLACE INTO news_article_companies (
                        article_id, cd_cvm, match_method, match_reason,
                        relevance_score, rule_strength, is_primary, manually_reviewed, created_at
                    )
                    VALUES (:article_id, :cd_cvm, 'manual', :reason, 1.0, 1.0, :is_primary, 1, datetime('now'))
                """),
                {"article_id": article_id, "cd_cvm": int(target_id), "reason": reason, "is_primary": 1 if payload.get("is_primary") else 0},
            )
            return None
        if target_type == "sector":
            sector_name = str(payload.get("sector_name") or "").strip()
            if not sector_name:
                return "sector_name is required for manual sector corrections"
            conn.execute(
                text("""
                    INSERT OR REPLACE INTO news_article_sectors (
                        article_id, sector_slug, sector_name, parent_sector_slug, parent_sector_name,
                        match_method, match_reason, relevance_score, rule_strength,
                        is_primary, manually_reviewed, created_at
                    )
                    VALUES (
                        :article_id, :sector_slug, :sector_name, :parent_sector_slug, :parent_sector_name,
                        'manual', :reason, 1.0, 1.0, :is_primary, 1, datetime('now')
                    )
                """),
                {
                    "article_id": article_id,
                    "sector_slug": target_id,
                    "sector_name": sector_name,
                    "parent_sector_slug": payload.get("parent_sector_slug"),
                    "parent_sector_name": payload.get("parent_sector_name"),
                    "reason": reason,
                    "is_primary": 1 if payload.get("is_primary") else 0,
                },
            )
            return None
        if target_type == "topic":
            exists = conn.execute(text("SELECT 1 FROM news_topics WHERE topic_id = :target_id"), {"target_id": target_id}).scalar()
            if not exists:
                return "topic_id must reference an existing News topic"
            conn.execute(
                text("""
                    INSERT OR REPLACE INTO news_article_topics (
                        article_id, topic_id, match_method, match_reason, relevance_score, created_at
                    )
                    VALUES (:article_id, :target_id, 'manual', :reason, 1.0, datetime('now'))
                """),
                {"article_id": article_id, "target_id": target_id, "reason": reason},
            )
            return None
        if target_type == "event_type":
            exists = conn.execute(text("SELECT 1 FROM news_event_types WHERE event_type_id = :target_id"), {"target_id": target_id}).scalar()
            if not exists:
                return "event_type_id must reference an existing News event type"
            conn.execute(
                text("""
                    INSERT OR REPLACE INTO news_article_event_types (
                        article_id, event_type_id, match_method, match_reason, relevance_score, created_at
                    )
                    VALUES (:article_id, :target_id, 'manual', :reason, 1.0, datetime('now'))
                """),
                {"article_id": article_id, "target_id": target_id, "reason": reason},
            )
            return None
        exists = conn.execute(text("SELECT 1 FROM news_keyword_rules WHERE keyword_rule_id = :target_id"), {"target_id": target_id}).scalar()
        if not exists:
            return "keyword_rule_id must reference an existing News keyword rule"
        matched_term = str(payload.get("matched_term") or target_id).strip()
        conn.execute(
            text("""
                INSERT OR REPLACE INTO news_article_keyword_matches (
                    article_id, keyword_rule_id, matched_term, match_method,
                    match_reason, relevance_score, created_at
                )
                VALUES (:article_id, :target_id, :matched_term, 'manual', :reason, 1.0, datetime('now'))
            """),
            {"article_id": article_id, "target_id": target_id, "matched_term": matched_term, "reason": reason},
        )
        return None

    def replace_article_score(self, *, article_id: str, score: ArticleScore) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO news_article_scores (
                        article_id, total_score, priority_level,
                        components_json, reasons_json, updated_at
                    )
                    VALUES (
                        :article_id, :total_score, :priority_level,
                        :components_json, :reasons_json, datetime('now')
                    )
                    ON CONFLICT(article_id) DO UPDATE SET
                        total_score = excluded.total_score,
                        priority_level = excluded.priority_level,
                        components_json = excluded.components_json,
                        reasons_json = excluded.reasons_json,
                        updated_at = excluded.updated_at
                """),
                {
                    "article_id": article_id,
                    "total_score": float(score.total_score),
                    "priority_level": score.priority_level,
                    "components_json": dumps(score.components, ensure_ascii=True, sort_keys=True),
                    "reasons_json": dumps(list(score.reasons), ensure_ascii=True),
                },
            )

    def list_collection_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 100))
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        run_id,
                        trigger,
                        status,
                        started_at,
                        finished_at,
                        source_count,
                        articles_seen,
                        articles_inserted,
                        articles_updated,
                        error_count,
                        error_message
                    FROM news_collection_runs
                    ORDER BY started_at DESC
                    LIMIT :limit
                """),
                {"limit": bounded_limit},
            ).mappings().fetchall()
        return [dict(row) for row in rows]

    def get_source_fetch_state(self, source_id: str) -> dict[str, str | None]:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT etag, last_modified FROM news_sources WHERE source_id = :source_id"),
                {"source_id": source_id},
            ).mappings().fetchone()
        if not row:
            return {"etag": None, "last_modified": None}
        return {"etag": row["etag"], "last_modified": row["last_modified"]}

    def update_source_fetch_state(
        self,
        *,
        source_id: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        if etag is None and last_modified is None:
            return
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE news_sources
                    SET etag = COALESCE(:etag, etag),
                        last_modified = COALESCE(:last_modified, last_modified),
                        updated_at = :updated_at
                    WHERE source_id = :source_id
                """),
                {
                    "source_id": source_id,
                    "etag": etag,
                    "last_modified": last_modified,
                    "updated_at": utc_now_iso(),
                },
        )

    def set_source_enabled(self, *, source_id: str, enabled: bool) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE news_sources
                    SET enabled = :enabled,
                        updated_at = :updated_at
                    WHERE source_id = :source_id
                """),
                {
                    "source_id": source_id,
                    "enabled": 1 if enabled else 0,
                    "updated_at": utc_now_iso(),
                },
            )
        return int(result.rowcount or 0) > 0

    def set_source_priority(self, *, source_id: str, priority: int) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE news_sources
                    SET priority = :priority,
                        updated_at = :updated_at
                    WHERE source_id = :source_id
                """),
                {
                    "source_id": source_id,
                    "priority": int(priority),
                    "updated_at": utc_now_iso(),
                },
            )
        return int(result.rowcount or 0) > 0

    def update_article_user_state(
        self,
        *,
        article_id: str,
        read: bool | None = None,
        saved: bool | None = None,
        hidden: bool | None = None,
        read_later: bool | None = None,
        notes: str | None = None,
    ) -> dict[str, Any] | None:
        updates = {
            "read": read,
            "saved": saved,
            "hidden": hidden,
            "read_later": read_later,
            "notes": notes,
        }
        if all(value is None for value in updates.values()):
            return self.get_article_user_state(article_id)
        now = utc_now_iso()
        with self.engine.begin() as conn:
            article_exists = conn.execute(
                text("SELECT 1 FROM news_articles WHERE article_id = :article_id"),
                {"article_id": article_id},
            ).fetchone()
            if not article_exists:
                return None
            conn.execute(
                text("""
                    INSERT INTO news_user_state (
                        article_id, read, saved, hidden, read_later, notes, created_at, updated_at
                    )
                    VALUES (
                        :article_id, :read_insert, :saved_insert, :hidden_insert, :read_later_insert, :notes_insert, :now, :now
                    )
                    ON CONFLICT(article_id) DO UPDATE SET
                        read = COALESCE(:read, news_user_state.read),
                        saved = COALESCE(:saved, news_user_state.saved),
                        hidden = COALESCE(:hidden, news_user_state.hidden),
                        read_later = COALESCE(:read_later, news_user_state.read_later),
                        notes = COALESCE(:notes, news_user_state.notes),
                        updated_at = :now
                """),
                {
                    "article_id": article_id,
                    "read": None if read is None else 1 if read else 0,
                    "saved": None if saved is None else 1 if saved else 0,
                    "hidden": None if hidden is None else 1 if hidden else 0,
                    "read_later": None if read_later is None else 1 if read_later else 0,
                    "notes": notes,
                    "read_insert": 0 if read is None else 1 if read else 0,
                    "saved_insert": 0 if saved is None else 1 if saved else 0,
                    "hidden_insert": 0 if hidden is None else 1 if hidden else 0,
                    "read_later_insert": 0 if read_later is None else 1 if read_later else 0,
                    "notes_insert": notes,
                    "now": now,
                },
            )
        return self.get_article_user_state(article_id)

    def get_article_user_state(self, article_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            article_exists = conn.execute(
                text("SELECT 1 FROM news_articles WHERE article_id = :article_id"),
                {"article_id": article_id},
            ).fetchone()
            if not article_exists:
                return None
            row = conn.execute(
                text("""
                    SELECT
                        a.article_id,
                        COALESCE(u.read, 0) AS read,
                        COALESCE(u.saved, 0) AS saved,
                        COALESCE(u.hidden, 0) AS hidden,
                        COALESCE(u.read_later, 0) AS read_later,
                        u.notes
                    FROM news_articles a
                    LEFT JOIN news_user_state u ON u.article_id = a.article_id
                    WHERE a.article_id = :article_id
                """),
                {"article_id": article_id},
            ).mappings().fetchone()
        return dict(row) if row else None

    def upsert_article(self, *, source: NewsSource, entry: ParsedFeedEntry, fetched_at: str | None = None) -> ArticleUpsertResult:
        canonical_url = canonicalize_url(entry.url)
        article_id = article_id_for_url(canonical_url)
        now = utc_now_iso()
        fetched = fetched_at or now
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT article_id, title, summary FROM news_articles WHERE canonical_url = :canonical_url"),
                {"canonical_url": canonical_url},
            ).mappings().fetchone()
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
                        :fetched_at, :summary, :language, 'summary_available', :now, :now
                    )
                    ON CONFLICT(canonical_url) DO UPDATE SET
                        source_item_id = COALESCE(excluded.source_item_id, news_articles.source_item_id),
                        title = excluded.title,
                        summary = COALESCE(excluded.summary, news_articles.summary),
                        published_at = COALESCE(excluded.published_at, news_articles.published_at),
                        fetched_at = excluded.fetched_at,
                        updated_at = excluded.updated_at
                """),
                {
                    "article_id": article_id,
                    "source_id": source.source_id,
                    "source_item_id": entry.source_item_id,
                    "title": entry.title,
                    "source_name": source.name,
                    "original_url": entry.url,
                    "canonical_url": canonical_url,
                    "published_at": entry.published_at,
                    "discovered_at": now,
                    "fetched_at": fetched,
                    "summary": entry.summary,
                    "language": entry.language,
                    "now": now,
                },
            )
            self._sync_fts(conn, article_id=article_id, title=entry.title, summary=entry.summary)
        return ArticleUpsertResult(article_id=article_id, inserted=existing is None, updated=existing is not None)

    def start_collection_run(self, *, trigger: str) -> str:
        run_id = "run_" + uuid4().hex
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO news_collection_runs (run_id, trigger, status, started_at)
                    VALUES (:run_id, :trigger, 'running', :started_at)
                """),
                {"run_id": run_id, "trigger": trigger, "started_at": utc_now_iso()},
            )
        return run_id

    def finish_collection_run(
        self,
        *,
        run_id: str,
        status: str,
        source_count: int,
        articles_seen: int,
        articles_inserted: int,
        articles_updated: int,
        error_count: int,
        error_message: str | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE news_collection_runs
                    SET status = :status,
                        finished_at = :finished_at,
                        source_count = :source_count,
                        articles_seen = :articles_seen,
                        articles_inserted = :articles_inserted,
                        articles_updated = :articles_updated,
                        error_count = :error_count,
                        error_message = :error_message
                    WHERE run_id = :run_id
                """),
                {
                    "run_id": run_id,
                    "status": status,
                    "finished_at": utc_now_iso(),
                    "source_count": int(source_count),
                    "articles_seen": int(articles_seen),
                    "articles_inserted": int(articles_inserted),
                    "articles_updated": int(articles_updated),
                    "error_count": int(error_count),
                    "error_message": error_message,
                },
            )

    def record_source_health(
        self,
        *,
        source_id: str,
        status: str,
        article_count: int = 0,
        error: str | None = None,
        http_status: int | None = None,
    ) -> None:
        now = utc_now_iso()
        successful_status = status in {"success", "not_modified"}
        success_at = now if successful_status else None
        with self.engine.begin() as conn:
            previous = conn.execute(
                text("SELECT consecutive_failures FROM news_source_health WHERE source_id = :source_id"),
                {"source_id": source_id},
            ).mappings().fetchone()
            previous_failures = int(previous["consecutive_failures"]) if previous else 0
            failures = 0 if successful_status else previous_failures + 1
            conn.execute(
                text("""
                    INSERT INTO news_source_health (
                        source_id, last_attempt_at, last_success_at, last_status,
                        last_error, last_http_status, consecutive_failures,
                        last_article_count, updated_at
                    )
                    VALUES (
                        :source_id, :now, :success_at, :status,
                        :error, :http_status, :failures, :article_count, :now
                    )
                    ON CONFLICT(source_id) DO UPDATE SET
                        last_attempt_at = excluded.last_attempt_at,
                        last_success_at = COALESCE(excluded.last_success_at, news_source_health.last_success_at),
                        last_status = excluded.last_status,
                        last_error = excluded.last_error,
                        last_http_status = excluded.last_http_status,
                        consecutive_failures = excluded.consecutive_failures,
                        last_article_count = excluded.last_article_count,
                        updated_at = excluded.updated_at
                """),
                {
                    "source_id": source_id,
                    "now": now,
                    "success_at": success_at,
                    "status": status,
                    "error": error,
                    "http_status": http_status,
                    "failures": failures,
                    "article_count": int(article_count),
                },
            )

    @staticmethod
    def _sync_fts(conn, *, article_id: str, title: str, summary: str | None) -> None:
        fts_enabled = conn.execute(
            text("SELECT value FROM news_schema_capabilities WHERE key = 'fts5'")
        ).scalar()
        if fts_enabled != "1":
            return
        conn.execute(text("DELETE FROM news_articles_fts WHERE article_id = :article_id"), {"article_id": article_id})
        conn.execute(
            text("""
                INSERT INTO news_articles_fts (article_id, title, summary)
                VALUES (:article_id, :title, :summary)
            """),
            {"article_id": article_id, "title": title, "summary": summary or ""},
        )
