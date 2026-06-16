from __future__ import annotations

from src.news.repository import NewsSource


BUILTIN_SOURCE_CATALOG: tuple[NewsSource, ...] = (
    NewsSource(
        source_id="bcb-rss",
        name="Banco Central do Brasil",
        source_type="official",
        reliability_layer="official",
        feed_url="https://www.bcb.gov.br/acessoinformacao/rss",
        homepage_url="https://www.bcb.gov.br/",
        priority=10,
    ),
    NewsSource(
        source_id="b3-rss-news",
        name="B3 RSS News",
        source_type="official",
        reliability_layer="official",
        feed_url="https://www.b3.com.br/data/rss/suporteanegociacao.xml",
        homepage_url="https://www.b3.com.br/",
        priority=20,
    ),
)


def builtin_sources() -> tuple[NewsSource, ...]:
    return BUILTIN_SOURCE_CATALOG
