from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import Engine, inspect, text

from src.news.classifier import classify_article_text
from src.news.fetcher import NewsFeedFetcher
from src.news.feed_parser import NewsFeedParseError, ParsedFeedEntry, parse_feed_bytes
from src.news.repository import NewsRepository, NewsSource, utc_now_iso
from src.news.scoring import score_article

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionResult:
    run_id: str
    status: str
    articles_seen: int
    articles_inserted: int
    articles_updated: int
    error_count: int
    error_message: str | None = None


@dataclass(frozen=True)
class FeedValidationResult:
    status: str
    feed_url: str
    title: str | None = None
    entry_count: int = 0
    http_status: int | None = None
    final_url: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    error_message: str | None = None


class NewsCollectionService:
    def __init__(
        self,
        repository: NewsRepository,
        fetcher: NewsFeedFetcher | None = None,
        company_engine: Engine | None = None,
    ) -> None:
        self.repository = repository
        self.fetcher = fetcher or NewsFeedFetcher()
        self.company_engine = company_engine

    def collect_source(self, *, source: NewsSource, trigger: str = "manual") -> CollectionResult:
        self.repository.upsert_source(source)
        run_id = self.repository.start_collection_run(trigger=trigger)
        state = self.repository.get_source_fetch_state(source.source_id)
        fetch_result = self.fetcher.fetch(
            source.feed_url,
            etag=state["etag"],
            last_modified=state["last_modified"],
        )
        if fetch_result.etag or fetch_result.last_modified:
            self.repository.update_source_fetch_state(
                source_id=source.source_id,
                etag=fetch_result.etag,
                last_modified=fetch_result.last_modified,
            )
        if fetch_result.status == "success":
            return self._ingest_payload(
                run_id=run_id,
                source=source,
                payload=fetch_result.payload,
                http_status=fetch_result.http_status,
            )
        if fetch_result.status == "not_modified":
            self.repository.record_source_health(
                source_id=source.source_id,
                status="not_modified",
                article_count=0,
                http_status=fetch_result.http_status,
            )
            self.repository.finish_collection_run(
                run_id=run_id,
                status="not_modified",
                source_count=1,
                articles_seen=0,
                articles_inserted=0,
                articles_updated=0,
                error_count=0,
            )
            return CollectionResult(
                run_id=run_id,
                status="not_modified",
                articles_seen=0,
                articles_inserted=0,
                articles_updated=0,
                error_count=0,
            )
        return self._finish_error(
            run_id=run_id,
            source=source,
            message=fetch_result.error_message or "Feed request failed",
            http_status=fetch_result.http_status,
        )

    def collect_feed_payload(
        self,
        *,
        source: NewsSource,
        payload: bytes,
        trigger: str = "manual",
        http_status: int | None = None,
    ) -> CollectionResult:
        self.repository.upsert_source(source)
        run_id = self.repository.start_collection_run(trigger=trigger)
        return self._ingest_payload(
            run_id=run_id,
            source=source,
            payload=payload,
            http_status=http_status,
        )

    def validate_feed_url(self, feed_url: str) -> FeedValidationResult:
        fetch_result = self.fetcher.fetch(feed_url)
        if fetch_result.status != "success":
            return FeedValidationResult(
                status="error",
                feed_url=feed_url,
                http_status=fetch_result.http_status,
                final_url=fetch_result.final_url,
                etag=fetch_result.etag,
                last_modified=fetch_result.last_modified,
                error_message=fetch_result.error_message or "Feed validation failed",
            )
        try:
            parsed = parse_feed_bytes(fetch_result.payload, feed_url=feed_url)
        except NewsFeedParseError as exc:
            return FeedValidationResult(
                status="error",
                feed_url=feed_url,
                http_status=fetch_result.http_status,
                final_url=fetch_result.final_url,
                etag=fetch_result.etag,
                last_modified=fetch_result.last_modified,
                error_message=str(exc),
            )
        return FeedValidationResult(
            status="success",
            feed_url=feed_url,
            title=parsed.title,
            entry_count=len(parsed.entries),
            http_status=fetch_result.http_status,
            final_url=fetch_result.final_url,
            etag=fetch_result.etag,
            last_modified=fetch_result.last_modified,
        )

    def _ingest_payload(
        self,
        *,
        run_id: str,
        source: NewsSource,
        payload: bytes,
        http_status: int | None,
    ) -> CollectionResult:
        try:
            parsed = parse_feed_bytes(payload, feed_url=source.feed_url)
            inserted = 0
            updated = 0
            keyword_rules = self.repository.list_keyword_rules(active_only=True)
            company_rows = self._load_company_rows()
            for entry in parsed.entries:
                resolved_entry = self._resolve_aggregator_entry(source=source, entry=entry)
                result = self.repository.upsert_article(source=source, entry=resolved_entry)
                classification = classify_article_text(
                    title=resolved_entry.title,
                    summary=resolved_entry.summary,
                    keyword_rules=keyword_rules,
                    company_rows=company_rows,
                )
                self.repository.replace_article_classification(
                    article_id=result.article_id,
                    classification=classification,
                )
                score = score_article(
                    source=source,
                    published_at=resolved_entry.published_at,
                    discovered_at=utc_now_iso(),
                    classification=classification,
                )
                self.repository.replace_article_score(article_id=result.article_id, score=score)
                self._store_selective_feed_content(
                    article_id=result.article_id,
                    source=source,
                    entry=resolved_entry,
                    priority_level=score.priority_level,
                )
                inserted += 1 if result.inserted else 0
                updated += 1 if result.updated else 0
            self.repository.record_source_health(
                source_id=source.source_id,
                status="success",
                article_count=len(parsed.entries),
                http_status=http_status,
            )
            self.repository.finish_collection_run(
                run_id=run_id,
                status="success",
                source_count=1,
                articles_seen=len(parsed.entries),
                articles_inserted=inserted,
                articles_updated=updated,
                error_count=0,
            )
            return CollectionResult(
                run_id=run_id,
                status="success",
                articles_seen=len(parsed.entries),
                articles_inserted=inserted,
                articles_updated=updated,
                error_count=0,
            )
        except NewsFeedParseError as exc:
            message = str(exc)
            self.repository.record_source_health(
                source_id=source.source_id,
                status="error",
                error=message,
                http_status=http_status,
            )
            self.repository.finish_collection_run(
                run_id=run_id,
                status="error",
                source_count=1,
                articles_seen=0,
                articles_inserted=0,
                articles_updated=0,
                error_count=1,
                error_message=message,
            )
            return CollectionResult(
                run_id=run_id,
                status="error",
                articles_seen=0,
                articles_inserted=0,
                articles_updated=0,
                error_count=1,
                error_message=message,
            )

    def _resolve_aggregator_entry(self, *, source: NewsSource, entry: ParsedFeedEntry) -> ParsedFeedEntry:
        if source.source_type != "aggregator_search":
            return entry
        resolution = self.fetcher.resolve_url(entry.url)
        if resolution.status != "success" or not resolution.final_url:
            logger.info("news aggregator URL resolution skipped: %s", resolution.error_message)
            return _with_aggregator_note(entry, "Aggregator article URL was not resolved.")
        if resolution.final_url == entry.url or _is_google_news_url(resolution.final_url):
            return _with_aggregator_note(entry, "Aggregator article URL was not resolved.")
        summary = entry.summary
        if summary:
            summary = f"{summary}\n\nOriginal source resolved from aggregator URL."
        else:
            summary = "Original source resolved from aggregator URL."
        return ParsedFeedEntry(
            title=entry.title,
            url=resolution.final_url,
            source_item_id=entry.source_item_id or entry.url,
            published_at=entry.published_at,
            summary=summary,
            language=entry.language,
            publisher_name=entry.publisher_name,
            publisher_homepage_url=entry.publisher_homepage_url,
        )

    def _store_selective_feed_content(
        self,
        *,
        article_id: str,
        source: NewsSource,
        entry,
        priority_level: str,
    ) -> None:
        if not source.allow_content_storage:
            return
        content = str(entry.summary or "").strip()
        if not content:
            return
        eligible = (
            source.reliability_layer == "official"
            or source.source_type == "official"
            or priority_level in {"High", "Critical"}
        )
        if not eligible:
            return
        status = "official_document" if _looks_like_official_document(entry.url, entry.title) else "full_text_available"
        self.repository.store_article_content(
            article_id=article_id,
            content_text=content,
            content_format="feed",
            source_policy="feed_content_allowed",
            content_status=status,
        )

    def _load_company_rows(self) -> list[dict]:
        if self.company_engine is None:
            return []
        try:
            with self.company_engine.connect() as conn:
                inspector = inspect(conn)
                if not inspector.has_table("companies"):
                    return []
                columns = {str(column["name"]) for column in inspector.get_columns("companies")}
                select_parts = [
                    "cd_cvm",
                    "company_name",
                    _select_company_column(columns, "nome_comercial"),
                    _select_company_column(columns, "cnpj"),
                    _select_company_column(columns, "ticker_b3"),
                    _select_company_column(columns, "setor_cvm"),
                    _select_company_column(columns, "setor_analitico"),
                    _select_company_column(columns, "gics_sector"),
                    _select_company_column(columns, "gics_sector_slug"),
                    _select_company_column(columns, "gics_sub_industry"),
                ]
                active_filter = "WHERE COALESCE(is_active, 1) = 1" if "is_active" in columns else ""
                rows = conn.execute(
                    text(f"""
                        SELECT {", ".join(select_parts)}
                        FROM companies
                        {active_filter}
                    """)
                ).mappings().fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            logger.warning("failed to load company rows for news classification: %s", exc, exc_info=True)
            return []

    def _finish_error(
        self,
        *,
        run_id: str,
        source: NewsSource,
        message: str,
        http_status: int | None = None,
    ) -> CollectionResult:
        self.repository.record_source_health(
            source_id=source.source_id,
            status="error",
            error=message,
            http_status=http_status,
        )
        self.repository.finish_collection_run(
            run_id=run_id,
            status="error",
            source_count=1,
            articles_seen=0,
            articles_inserted=0,
            articles_updated=0,
            error_count=1,
            error_message=message,
        )
        return CollectionResult(
            run_id=run_id,
            status="error",
            articles_seen=0,
            articles_inserted=0,
            articles_updated=0,
            error_count=1,
            error_message=message,
        )


def _select_company_column(columns: set[str], column_name: str) -> str:
    if column_name in columns:
        return column_name
    return f"NULL AS {column_name}"


def _with_aggregator_note(entry: ParsedFeedEntry, note: str) -> ParsedFeedEntry:
    summary = str(entry.summary or "").strip()
    if note in summary:
        next_summary = summary or None
    elif summary:
        next_summary = f"{summary}\n\n{note}"
    else:
        next_summary = note
    return ParsedFeedEntry(
        title=entry.title,
        url=entry.url,
        source_item_id=entry.source_item_id,
        published_at=entry.published_at,
        summary=next_summary,
        language=entry.language,
        publisher_name=entry.publisher_name,
        publisher_homepage_url=entry.publisher_homepage_url,
    )


def _is_google_news_url(url: str) -> bool:
    host = urlsplit(str(url)).netloc.lower()
    return host == "news.google.com" or host.endswith(".news.google.com")


def _looks_like_official_document(url: str, title: str) -> bool:
    value = f"{url} {title}".lower()
    return any(marker in value for marker in (".pdf", "comunicado", "fato relevante", "oficio", "deliberacao"))
