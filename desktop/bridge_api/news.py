from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus, urlsplit

from sqlalchemy import text

from src.news.repository import NewsRepository, NewsSource, google_company_source_id, user_source_id_for_url
from src.news.schema import ensure_news_tables, get_news_engine
from src.news.service import NewsCollectionService
from src.news.sources import builtin_sources
from src.platform.db import build_engine

logger = logging.getLogger("desktop.bridge.news")


def _sqlite_table_exists(conn, table_name: str) -> bool:
    return bool(conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
        {"table_name": table_name},
    ).scalar())


class NewsBridgeMixin:
    @staticmethod
    def _is_release_data_write_block() -> bool:
        if getattr(sys, "frozen", False):
            return False
        use_release = os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {
            "1", "true", "yes",
        }
        allow_release_writes = os.environ.get("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", "").strip().lower() in {
            "1", "true", "yes",
        }
        concurrent = os.environ.get("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", "").strip() == "1"
        return use_release and not allow_release_writes and not concurrent

    def _is_news_write_allowed(self) -> bool:
        if self._is_write_allowed():
            return True
        return self._is_release_data_write_block()

    def _news_refresh_status(self) -> dict[str, Any]:
        if not hasattr(self, "_news_refresh_state"):
            self._news_refresh_state = {
                "status": "idle",
                "error": None,
                "started_at": None,
                "finished_at": None,
                "source_count": 0,
                "completed_sources": 0,
                "articles_seen": 0,
                "articles_inserted": 0,
                "articles_updated": 0,
                "error_count": 0,
                "sources": [],
            }
        return dict(self._news_refresh_state)

    def _news_repository(self) -> NewsRepository:
        settings = self._svc().settings
        engine = get_news_engine(settings)
        ensure_news_tables(engine)
        return NewsRepository(engine)

    def _news_collection_service(self) -> NewsCollectionService:
        settings = self._svc().settings
        return NewsCollectionService(self._news_repository(), company_engine=build_engine(settings))

    def _news_company_scope(self, repository: NewsRepository) -> dict[str, Any]:
        settings = self._svc().settings
        company_engine = build_engine(settings)
        selected_preset: str | None = None
        selected_coverage_universe_id: str | None = None
        selected_coverage_universe_name: str | None = None
        available_coverage_universes: list[dict[str, Any]] = []
        coverage_rows: list[dict[str, Any]] = []
        with company_engine.connect() as conn:
            has_app_settings = _sqlite_table_exists(conn, "app_settings")
            has_company_universe = _sqlite_table_exists(conn, "company_universe")
            has_companies = _sqlite_table_exists(conn, "companies")
            has_coverage_universes = _sqlite_table_exists(conn, "coverage_universes")
            has_universe_companies = _sqlite_table_exists(conn, "universe_companies")
            scope_settings = repository.get_company_scope_settings()
            selected_coverage_universe_id = str(scope_settings.get("coverage_universe_id") or "").strip() or None
            if has_coverage_universes:
                available_coverage_universes = [dict(row) for row in conn.execute(
                    text("""
                        SELECT
                            u.id,
                            u.name,
                            u.status,
                            u.updated_at,
                            COALESCE(c.company_count, 0) AS company_count
                        FROM coverage_universes u
                        LEFT JOIN (
                            SELECT universe_id, COUNT(*) AS company_count
                            FROM universe_companies
                            GROUP BY universe_id
                        ) c ON c.universe_id = u.id
                        ORDER BY u.updated_at DESC, u.name ASC
                    """)
                ).mappings().fetchall()]
            if selected_coverage_universe_id and has_coverage_universes and has_universe_companies:
                universe = conn.execute(
                    text("SELECT id, name FROM coverage_universes WHERE id = :id"),
                    {"id": selected_coverage_universe_id},
                ).mappings().fetchone()
                if universe:
                    selected_coverage_universe_name = str(universe["name"])
                    coverage_rows = [dict(row) for row in conn.execute(
                        text("""
                            SELECT
                                uc.cd_cvm,
                                COALESCE(c.company_name, 'CVM ' || uc.cd_cvm) AS company_name,
                                c.ticker_b3 AS ticker,
                                uc.tier AS coverage_tier,
                                c.coverage_rank AS market_cap_rank
                            FROM universe_companies uc
                            LEFT JOIN companies c ON c.cd_cvm = uc.cd_cvm
                            WHERE uc.universe_id = :universe_id
                              AND uc.tier NOT IN ('excluded', 'inappropriate')
                            ORDER BY
                                CASE uc.tier
                                    WHEN 'must_cover' THEN 1
                                    WHEN 'core' THEN 2
                                    WHEN 'watchlist' THEN 3
                                    WHEN 'opportunistic' THEN 4
                                    ELSE 5
                                END,
                                c.coverage_rank ASC,
                                company_name ASC
                        """),
                        {"universe_id": selected_coverage_universe_id},
                    ).mappings().fetchall()]
            if has_app_settings:
                selected_preset = conn.execute(
                    text("SELECT value FROM app_settings WHERE key = 'selected_company_universe'")
                ).scalar()
            if not selected_coverage_universe_id and selected_preset and has_company_universe:
                coverage_rows = [dict(row) for row in conn.execute(
                    text("""
                        SELECT cu.cd_cvm, cu.company_name, cu.ticker, cu.market_cap_rank
                        FROM company_universe cu
                        WHERE cu.selected_preset = :preset
                        ORDER BY cu.market_cap_rank ASC, cu.company_name ASC
                    """),
                    {"preset": selected_preset},
                ).mappings().fetchall()]
            if not selected_coverage_universe_id and not coverage_rows and has_companies:
                coverage_rows = [dict(row) for row in conn.execute(
                    text("""
                        SELECT cd_cvm, company_name, ticker_b3 AS ticker, coverage_rank AS market_cap_rank
                        FROM companies
                        WHERE coverage_rank IS NOT NULL
                        ORDER BY coverage_rank ASC, company_name ASC
                    """)
                ).mappings().fetchall()]

        overrides = repository.list_company_scope_overrides()
        included_ids = {int(row["cd_cvm"]) for row in coverage_rows}
        for row in overrides:
            cd_cvm = int(row["cd_cvm"])
            if row["action"] == "include":
                included_ids.add(cd_cvm)
            elif row["action"] == "exclude":
                included_ids.discard(cd_cvm)
        return {
            "company_ids": included_ids,
            "selected_preset": selected_preset,
            "selected_coverage_universe_id": selected_coverage_universe_id,
            "selected_coverage_universe_name": selected_coverage_universe_name,
            "available_coverage_universes": available_coverage_universes,
            "coverage_companies": coverage_rows,
            "overrides": overrides,
        }

    @staticmethod
    def _google_news_query_for_company(company: dict[str, Any]) -> str:
        terms: list[str] = []
        ticker = str(company.get("ticker") or "").strip()
        company_name = str(company.get("company_name") or "").strip()
        if ticker:
            terms.append(ticker)
        if company_name:
            terms.append(f'"{company_name}"')
        if not terms:
            terms.append(str(company.get("cd_cvm") or "companhia aberta"))
        return " OR ".join(terms)

    @staticmethod
    def _google_news_feed_url(query: str, *, locale: str, country: str) -> str:
        language = locale.split("-", 1)[0] if locale else "pt"
        ceid = f"{country}:{language}"
        return (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query)}&hl={quote_plus(locale)}&gl={quote_plus(country)}&ceid={quote_plus(ceid)}"
        )

    def _register_google_company_sources(self, repository: NewsRepository) -> dict[str, Any]:
        settings = repository.get_google_company_feed_settings()
        if not bool(int(settings.get("enabled") or 0)):
            scope = self._news_company_scope(repository)
            return {**settings, "generated_count": 0, "eligible_company_count": len(scope["company_ids"])}
        scope = self._news_company_scope(repository)
        companies_by_id = self._news_company_rows_by_id(scope["company_ids"])
        max_companies = self._bounded_int(settings.get("max_companies"), default=50, minimum=1, maximum=250)
        priority = self._bounded_int(settings.get("priority"), default=140, minimum=1, maximum=1000)
        locale = str(settings.get("locale") or "pt-BR")
        country = str(settings.get("country") or "BR")
        generated = 0
        for cd_cvm in sorted(scope["company_ids"]):
            if generated >= max_companies:
                break
            company = companies_by_id.get(int(cd_cvm))
            if not company:
                continue
            query = self._google_news_query_for_company(company)
            source = NewsSource(
                source_id=google_company_source_id(int(cd_cvm)),
                name=f"Google News - {company.get('ticker') or company.get('company_name') or cd_cvm}",
                source_type="aggregator_search",
                reliability_layer="aggregator",
                feed_url=self._google_news_feed_url(query, locale=locale, country=country),
                homepage_url="https://news.google.com/",
                enabled=True,
                priority=priority,
                user_defined=False,
                allow_content_storage=False,
            )
            repository.register_source(source)
            generated += 1
        return {**settings, "generated_count": generated, "eligible_company_count": len(scope["company_ids"])}

    def _news_company_rows_by_id(self, company_ids: set[int]) -> dict[int, dict[str, Any]]:
        if not company_ids:
            return {}
        settings = self._svc().settings
        company_engine = build_engine(settings)
        params = {f"cd_cvm_{idx}": int(cd_cvm) for idx, cd_cvm in enumerate(sorted(company_ids))}
        placeholders = ", ".join(f":{key}" for key in params)
        with company_engine.connect() as conn:
            if not _sqlite_table_exists(conn, "companies"):
                return {}
            rows = conn.execute(
                text(f"""
                    SELECT cd_cvm, company_name, ticker_b3 AS ticker, coverage_rank AS market_cap_rank
                    FROM companies
                    WHERE cd_cvm IN ({placeholders})
                    ORDER BY coverage_rank ASC, company_name ASC
                """),
                params,
            ).mappings().fetchall()
        return {int(row["cd_cvm"]): dict(row) for row in rows if row.get("cd_cvm") is not None}

    def _news_coverage_universe_exists(self, universe_id: str) -> bool:
        company_engine = build_engine(self._svc().settings)
        with company_engine.connect() as conn:
            if not _sqlite_table_exists(conn, "coverage_universes"):
                return False
            return bool(conn.execute(
                text("SELECT 1 FROM coverage_universes WHERE id = :id"),
                {"id": universe_id},
            ).scalar())

    @staticmethod
    def _news_source_from_row(row: dict[str, Any], fallback: NewsSource) -> NewsSource:
        return NewsSource(
            source_id=str(row.get("source_id") or fallback.source_id),
            name=str(row.get("name") or fallback.name),
            source_type=str(row.get("source_type") or fallback.source_type),
            reliability_layer=str(row.get("reliability_layer") or fallback.reliability_layer),
            feed_url=str(row.get("feed_url") or fallback.feed_url),
            homepage_url=row.get("homepage_url") or fallback.homepage_url,
            enabled=bool(int(row.get("enabled") if row.get("enabled") is not None else fallback.enabled)),
            priority=int(row.get("priority") if row.get("priority") is not None else fallback.priority),
            user_defined=bool(int(row.get("user_defined") if row.get("user_defined") is not None else fallback.user_defined)),
            allow_content_storage=bool(int(row.get("allow_content_storage") if row.get("allow_content_storage") is not None else fallback.allow_content_storage)),
        )

    @staticmethod
    def _news_source_from_db_row(row: dict[str, Any]) -> NewsSource:
        return NewsSource(
            source_id=str(row.get("source_id") or ""),
            name=str(row.get("name") or row.get("source_id") or "News source"),
            source_type=str(row.get("source_type") or "user_provided_rss"),
            reliability_layer=str(row.get("reliability_layer") or "user_provided"),
            feed_url=str(row.get("feed_url") or ""),
            homepage_url=row.get("homepage_url"),
            enabled=bool(int(row.get("enabled") if row.get("enabled") is not None else 1)),
            priority=int(row.get("priority") if row.get("priority") is not None else 100),
            user_defined=bool(int(row.get("user_defined") if row.get("user_defined") is not None else 0)),
            allow_content_storage=bool(int(row.get("allow_content_storage") if row.get("allow_content_storage") is not None else 0)),
        )

    def _enabled_builtin_news_sources(self, repository: NewsRepository) -> list[NewsSource]:
        enabled: list[NewsSource] = []
        for source in builtin_sources():
            repository.register_source(source)
            row = repository.get_source(source.source_id) or {}
            resolved = self._news_source_from_row(row, source)
            if resolved.enabled:
                enabled.append(resolved)
        enabled.sort(key=lambda item: (int(item.priority), item.name.lower()))
        return enabled

    def _enabled_news_sources(self, repository: NewsRepository) -> list[NewsSource]:
        for source in builtin_sources():
            repository.register_source(source)
        self._register_google_company_sources(repository)
        enabled = [
            self._news_source_from_db_row(row)
            for row in repository.list_enabled_sources()
            if str(row.get("feed_url") or "").strip()
        ]
        enabled.sort(key=lambda item: (int(item.priority), item.name.lower()))
        return enabled

    def get_news_refresh_status(self, params=None) -> dict:
        return self._sanitize_for_json(self._news_refresh_status())

    def get_news_sources(self, params=None) -> dict:
        try:
            repository = self._news_repository()
            for source in builtin_sources():
                repository.register_source(source)
            self._register_google_company_sources(repository)
            sources = repository.list_sources()
            return self._sanitize_for_json({
                "items": sources,
                "count": len(sources),
            })
        except Exception as exc:
            logger.error("failed to load news sources: %s", exc, exc_info=True)
            return self._sanitize_for_json({"items": [], "count": 0, "error": str(exc)})

    def get_news_articles(self, params=None) -> dict:
        params = params or {}
        try:
            repository = self._news_repository()
            payload = repository.list_articles(
                limit=self._bounded_int(params.get("limit"), default=50, minimum=1, maximum=200),
                offset=self._bounded_int(params.get("offset"), default=0, minimum=0, maximum=1_000_000),
                source_id=str(params.get("source_id") or "") or None,
                include_hidden=bool(params.get("include_hidden")),
                order="top" if str(params.get("order") or "").strip().lower() == "top" else "latest",
            )
            return self._sanitize_for_json(payload)
        except Exception as exc:
            logger.error("failed to load news articles: %s", exc, exc_info=True)
            return self._sanitize_for_json({
                "items": [],
                "count": 0,
                "total": 0,
                "limit": 50,
                "offset": 0,
                "error": str(exc),
            })

    def get_news_google_company_feed_settings(self, params=None) -> dict:
        try:
            repository = self._news_repository()
            payload = self._register_google_company_sources(repository)
            return self._sanitize_for_json(payload)
        except Exception as exc:
            logger.error("failed to load Google News company feed settings: %s", exc, exc_info=True)
            return self._sanitize_for_json({
                "settings_id": "default",
                "enabled": 0,
                "max_companies": 50,
                "priority": 140,
                "locale": "pt-BR",
                "country": "BR",
                "generated_count": 0,
                "eligible_company_count": 0,
                "error": str(exc),
            })

    def save_news_google_company_feed_settings(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("save_news_google_company_feed_settings"))
        params = params or {}
        try:
            repository = self._news_repository()
            settings = repository.update_google_company_feed_settings(
                enabled=bool(params["enabled"]) if "enabled" in params else None,
                max_companies=params.get("max_companies"),
                priority=params.get("priority"),
                locale=str(params.get("locale") or "").strip() or None,
                country=str(params.get("country") or "").strip() or None,
            )
            if not bool(int(settings.get("enabled") or 0)):
                disabled_count = repository.disable_google_company_sources()
                return self._sanitize_for_json({
                    "status": "success",
                    "settings": {**settings, "generated_count": 0, "eligible_company_count": 0, "disabled_count": disabled_count},
                })
            payload = self._register_google_company_sources(repository)
            return self._sanitize_for_json({"status": "success", "settings": {**settings, **payload}})
        except Exception as exc:
            logger.error("failed to save Google News company feed settings: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def get_news_overview(self, params=None) -> dict:
        params = params or {}
        try:
            repository = self._news_repository()
            scope = self._news_company_scope(repository)
            payload = repository.list_overview(
                limit_per_section=self._bounded_int(
                    params.get("limit_per_section"), default=6, minimum=1, maximum=20
                ),
                company_scope_ids=scope["company_ids"],
            )
            return self._sanitize_for_json(payload)
        except Exception as exc:
            logger.error("failed to load news overview: %s", exc, exc_info=True)
            return self._sanitize_for_json({
                "sections": [],
                "limit_per_section": 6,
                "error": str(exc),
            })

    def get_news_company_scope(self, params=None) -> dict:
        try:
            scope = self._news_company_scope(self._news_repository())
            included_count = len(scope["company_ids"])
            excluded_ids = {
                int(row["cd_cvm"])
                for row in scope["overrides"]
                if row.get("action") == "exclude"
            }
            return self._sanitize_for_json({
                "selected_preset": scope["selected_preset"],
                "selected_coverage_universe_id": scope["selected_coverage_universe_id"],
                "selected_coverage_universe_name": scope["selected_coverage_universe_name"],
                "available_coverage_universes": scope["available_coverage_universes"],
                "coverage_count": len(scope["coverage_companies"]),
                "included_count": included_count,
                "excluded_count": len(excluded_ids),
                "overrides": scope["overrides"],
            })
        except Exception as exc:
            logger.error("failed to load news company scope: %s", exc, exc_info=True)
            return self._sanitize_for_json({
                "selected_preset": None,
                "selected_coverage_universe_id": None,
                "selected_coverage_universe_name": None,
                "available_coverage_universes": [],
                "coverage_count": 0,
                "included_count": 0,
                "excluded_count": 0,
                "overrides": [],
                "error": str(exc),
            })

    def set_news_company_scope_universe(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("set_news_company_scope_universe"))
        params = params or {}
        universe_id = str(params.get("coverage_universe_id") or "").strip() or None
        try:
            repository = self._news_repository()
            if universe_id:
                if not self._news_coverage_universe_exists(universe_id):
                    return {"status": "not_found", "error": f"Coverage universe {universe_id} not found"}
            settings = repository.update_company_scope_settings(coverage_universe_id=universe_id)
            scope = self._news_company_scope(repository)
            return self._sanitize_for_json({
                "status": "success",
                "settings": settings,
                "selected_coverage_universe_id": scope["selected_coverage_universe_id"],
                "selected_coverage_universe_name": scope["selected_coverage_universe_name"],
                "coverage_count": len(scope["coverage_companies"]),
            })
        except Exception as exc:
            logger.error("failed to update News company scope universe: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def set_news_company_scope_override(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("set_news_company_scope_override"))
        params = params or {}
        try:
            cd_cvm = self._bounded_int(params.get("cd_cvm"), default=0, minimum=1, maximum=999999)
            action = str(params.get("action") or "").strip().lower() or None
            reason = str(params.get("reason") or "").strip() or None
            result = self._news_repository().set_company_scope_override(
                cd_cvm=cd_cvm,
                action=action,
                reason=reason,
            )
            return self._sanitize_for_json(result)
        except Exception as exc:
            logger.error("failed to update news company scope override: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def get_news_retention_status(self, params=None) -> dict:
        try:
            return self._sanitize_for_json(self._news_repository().get_content_storage_summary())
        except Exception as exc:
            logger.error("failed to load news retention status: %s", exc, exc_info=True)
            return {"content_count": 0, "storage_bytes": 0, "saved_content_count": 0, "error": str(exc)}

    def save_news_retention_policy(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("save_news_retention_policy"))
        params = params or {}
        try:
            policy = self._news_repository().update_retention_policy(
                metadata_retention_days=params.get("metadata_retention_days"),
                extracted_text_retention_days=params.get("extracted_text_retention_days"),
                total_storage_limit_mb=params.get("total_storage_limit_mb"),
                preserve_saved=bool(params["preserve_saved"]) if "preserve_saved" in params else None,
                preserve_official_documents=(
                    bool(params["preserve_official_documents"])
                    if "preserve_official_documents" in params
                    else None
                ),
            )
            return self._sanitize_for_json({"status": "success", "policy": policy})
        except Exception as exc:
            logger.error("failed to save news retention policy: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def cleanup_news_extracted_content(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("cleanup_news_extracted_content"))
        params = params or {}
        try:
            payload = self._news_repository().cleanup_extracted_content(
                dry_run=bool(params.get("dry_run", False))
            )
            return self._sanitize_for_json(payload)
        except Exception as exc:
            logger.error("failed to cleanup news extracted content: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def get_news_article_classification(self, params=None) -> dict:
        params = params or {}
        article_id = str(params.get("article_id") or "").strip()
        if not article_id:
            return {"keywords": [], "topics": [], "event_types": [], "error": "article_id is required"}
        try:
            payload = self._news_repository().get_article_classification(article_id)
            return self._sanitize_for_json(payload)
        except Exception as exc:
            logger.error("failed to load news article classification: %s", exc, exc_info=True)
            return self._sanitize_for_json({
                "keywords": [],
                "topics": [],
                "event_types": [],
                "error": str(exc),
            })

    def get_news_article_content(self, params=None) -> dict:
        params = params or {}
        article_id = str(params.get("article_id") or "").strip()
        if not article_id:
            return {"available": False, "error": "article_id is required"}
        try:
            payload = self._news_repository().get_article_content(article_id)
            if payload is None:
                return {"available": False, "error": f"News article {article_id} not found"}
            return self._sanitize_for_json(payload)
        except Exception as exc:
            logger.error("failed to load news article content: %s", exc, exc_info=True)
            return {"available": False, "error": str(exc)}

    def apply_news_classification_correction(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("apply_news_classification_correction"))
        params = params or {}
        article_id = str(params.get("article_id") or "").strip()
        target_type = str(params.get("target_type") or "").strip()
        target_id = str(params.get("target_id") or "").strip()
        action = str(params.get("action") or "").strip()
        if not article_id:
            return {"status": "error", "error": "article_id is required"}
        try:
            payload = self._news_repository().apply_classification_correction(
                article_id=article_id,
                target_type=target_type,
                target_id=target_id,
                action=action,
                user_value=params.get("user_value") if isinstance(params.get("user_value"), dict) else {},
                rule_suggestion=str(params.get("rule_suggestion") or "").strip() or None,
            )
            return self._sanitize_for_json(payload)
        except Exception as exc:
            logger.error("failed to apply news classification correction: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def get_news_collection_runs(self, params=None) -> dict:
        params = params or {}
        try:
            repository = self._news_repository()
            runs = repository.list_collection_runs(
                limit=self._bounded_int(params.get("limit"), default=20, minimum=1, maximum=100)
            )
            return self._sanitize_for_json({
                "items": runs,
                "count": len(runs),
            })
        except Exception as exc:
            logger.error("failed to load news collection runs: %s", exc, exc_info=True)
            return self._sanitize_for_json({"items": [], "count": 0, "error": str(exc)})

    def set_news_source_enabled(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("set_news_source_enabled"))
        params = params or {}
        source_id = str(params.get("source_id") or "").strip()
        if not source_id:
            return {"status": "error", "error": "source_id is required"}
        try:
            updated = self._news_repository().set_source_enabled(
                source_id=source_id,
                enabled=bool(params.get("enabled")),
            )
            if not updated:
                return {"status": "not_found", "error": f"News source {source_id} not found"}
            return {"status": "success", "source_id": source_id, "enabled": bool(params.get("enabled"))}
        except Exception as exc:
            logger.error("failed to update news source enabled state: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def set_news_source_priority(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("set_news_source_priority"))
        params = params or {}
        source_id = str(params.get("source_id") or "").strip()
        if not source_id:
            return {"status": "error", "error": "source_id is required"}
        priority = self._bounded_int(params.get("priority"), default=100, minimum=1, maximum=1000)
        try:
            updated = self._news_repository().set_source_priority(source_id=source_id, priority=priority)
            if not updated:
                return {"status": "not_found", "error": f"News source {source_id} not found"}
            return {"status": "success", "source_id": source_id, "priority": priority}
        except Exception as exc:
            logger.error("failed to update news source priority: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def add_custom_news_source(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("add_custom_news_source"))
        params = params or {}
        feed_url = str(params.get("feed_url") or "").strip()
        parsed_url = urlsplit(feed_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            return {"status": "error", "error": "feed_url must be an HTTP or HTTPS URL"}

        requested_name = str(params.get("name") or "").strip()
        priority = self._bounded_int(params.get("priority"), default=100, minimum=1, maximum=1000)
        enabled = bool(params.get("enabled", True))
        try:
            service = self._news_collection_service()
            validation = service.validate_feed_url(feed_url)
            if validation.status != "success":
                return self._sanitize_for_json({
                    "status": "error",
                    "error": validation.error_message or "Feed validation failed",
                    "http_status": validation.http_status,
                    "final_url": validation.final_url,
                })
            source = NewsSource(
                source_id=user_source_id_for_url(validation.final_url or feed_url),
                name=requested_name or validation.title or feed_url,
                source_type="user_provided_rss",
                reliability_layer="user_provided",
                feed_url=validation.final_url or feed_url,
                homepage_url=None,
                enabled=enabled,
                priority=priority,
                user_defined=True,
                allow_content_storage=False,
            )
            repository = self._news_repository()
            repository.upsert_source(source)
            repository.update_source_fetch_state(
                source_id=source.source_id,
                etag=validation.etag,
                last_modified=validation.last_modified,
            )
            return self._sanitize_for_json({
                "status": "success",
                "source": repository.get_source(source.source_id),
                "validation": {
                    "title": validation.title,
                    "entry_count": validation.entry_count,
                    "http_status": validation.http_status,
                    "final_url": validation.final_url,
                },
            })
        except Exception as exc:
            logger.error("failed to add custom news source: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def update_news_article_state(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("update_news_article_state"))
        params = params or {}
        article_id = str(params.get("article_id") or "").strip()
        if not article_id:
            return {"status": "error", "error": "article_id is required"}
        allowed = {"read", "saved", "hidden", "read_later", "notes"}
        updates = {key: params[key] for key in allowed if key in params}
        if not updates:
            return {"status": "error", "error": "At least one article state field is required"}
        try:
            state = self._news_repository().update_article_user_state(
                article_id=article_id,
                read=bool(updates["read"]) if "read" in updates else None,
                saved=bool(updates["saved"]) if "saved" in updates else None,
                hidden=bool(updates["hidden"]) if "hidden" in updates else None,
                read_later=bool(updates["read_later"]) if "read_later" in updates else None,
                notes=str(updates["notes"] or "") if "notes" in updates else None,
            )
            if state is None:
                return {"status": "not_found", "error": f"News article {article_id} not found"}
            return self._sanitize_for_json({"status": "success", "state": state})
        except Exception as exc:
            logger.error("failed to update news article state: %s", exc, exc_info=True)
            return {"status": "error", "error": str(exc)}

    def refresh_news_sources(self, params=None) -> dict:
        if not self._is_news_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("refresh_news_sources"))

        if not hasattr(self, "_news_refresh_lock"):
            self._news_refresh_lock = threading.Lock()
        if self._news_refresh_status().get("status") == "running":
            return self._sanitize_for_json({"status": "already_running", "error": None})
        if not self._news_refresh_lock.acquire(blocking=False):
            return self._sanitize_for_json({"status": "already_running", "error": None})

        started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self._news_refresh_state = {
            "status": "running",
            "error": None,
            "started_at": started_at,
            "finished_at": None,
            "source_count": 0,
            "completed_sources": 0,
            "articles_seen": 0,
            "articles_inserted": 0,
            "articles_updated": 0,
            "error_count": 0,
            "sources": [],
        }

        def _run() -> None:
            try:
                repository = self._news_repository()
                service = self._news_collection_service()
                sources = self._enabled_news_sources(repository)
                self._news_refresh_state.update({"source_count": len(sources)})
                for source in sources:
                    try:
                        result = service.collect_source(source=source, trigger="manual")
                        source_result = {
                            "source_id": source.source_id,
                            "name": source.name,
                            "status": result.status,
                            "articles_seen": result.articles_seen,
                            "articles_inserted": result.articles_inserted,
                            "articles_updated": result.articles_updated,
                            "error_count": result.error_count,
                            "error_message": result.error_message,
                        }
                    except Exception as exc:
                        logger.error(
                            "news refresh source failed: %s: %s",
                            source.source_id,
                            exc,
                            exc_info=True,
                        )
                        source_result = {
                            "source_id": source.source_id,
                            "name": source.name,
                            "status": "error",
                            "articles_seen": 0,
                            "articles_inserted": 0,
                            "articles_updated": 0,
                            "error_count": 1,
                            "error_message": str(exc),
                        }
                        repository.record_source_health(
                            source_id=source.source_id,
                            status="error",
                            error=str(exc),
                        )
                    self._news_refresh_state["sources"].append(source_result)
                    self._news_refresh_state["completed_sources"] += 1
                    self._news_refresh_state["articles_seen"] += source_result["articles_seen"]
                    self._news_refresh_state["articles_inserted"] += source_result["articles_inserted"]
                    self._news_refresh_state["articles_updated"] += source_result["articles_updated"]
                    self._news_refresh_state["error_count"] += source_result["error_count"]
                final_status = "error" if self._news_refresh_state["error_count"] else "success"
                self._news_refresh_state.update({
                    "status": final_status,
                    "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                })
            except Exception as exc:
                logger.error("news refresh failed: %s", exc, exc_info=True)
                self._news_refresh_state.update({
                    "status": "error",
                    "error": str(exc),
                    "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                })
            finally:
                self._news_refresh_lock.release()

        threading.Thread(target=_run, name="news-manual-refresh", daemon=True).start()
        return self._sanitize_for_json({
            "status": "started",
            "error": None,
            "started_at": started_at,
        })
