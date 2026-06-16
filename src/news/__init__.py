"""Local-first financial news ingestion and storage."""

from src.news.schema import ensure_news_tables, ensure_news_tables_for_connection, get_news_engine

__all__ = [
    "ensure_news_tables",
    "ensure_news_tables_for_connection",
    "get_news_engine",
]
