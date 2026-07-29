# -*- coding: utf-8 -*-
"""
src/platform/db.py — Factory de conexão ao banco com 3-tier fallback:
  1. os.getenv("DATABASE_URL")  → Supabase / PostgreSQL remoto
  2. SQLite local               → desenvolvimento sem configuração extra

Sem dependencias de framework UI — pode ser importado por CLI,
desktop bridge e API.
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, event, Engine

from src.platform.settings import AppSettings, get_settings


def build_engine(settings: AppSettings | None = None) -> Engine:
    cfg = settings or get_settings()
    url = _resolve_url(cfg)
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})
        configure_sqlite_foreign_keys(engine)
        return engine
    return create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300,
    )


def configure_sqlite_foreign_keys(engine: Engine) -> None:
    """Enable SQLite foreign-key enforcement for every connection in an engine."""
    if engine.dialect.name != "sqlite" or getattr(engine, "_cvm_fk_hook", False):
        return

    def _enable_foreign_keys(dbapi_connection) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys_on_connect(dbapi_connection, _connection_record) -> None:
        _enable_foreign_keys(dbapi_connection)

    @event.listens_for(engine, "checkout")
    def _enable_foreign_keys_on_checkout(dbapi_connection, _connection_record, _connection_proxy) -> None:
        _enable_foreign_keys(dbapi_connection)

    setattr(engine, "_cvm_fk_hook", True)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return build_engine(get_settings())


def _resolve_url(settings: AppSettings) -> str:
    if settings.database_url:
        return settings.database_url
    return settings.paths.sqlite_url
