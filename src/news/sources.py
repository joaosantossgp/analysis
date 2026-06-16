from __future__ import annotations

from src.news.repository import NewsSource


BUILTIN_SOURCE_CATALOG: tuple[NewsSource, ...] = (
    NewsSource(
        source_id="cvm-rss",
        name="Comissao de Valores Mobiliarios",
        source_type="official",
        reliability_layer="official",
        feed_url="https://www.gov.br/cvm/RSS",
        homepage_url="https://www.gov.br/cvm/",
        priority=5,
        allow_content_storage=True,
    ),
    NewsSource(
        source_id="bcb-rss",
        name="Banco Central Noticias",
        source_type="official",
        reliability_layer="official",
        feed_url="https://www.bcb.gov.br/api/feed/sitebcb/sitefeeds/noticias",
        homepage_url="https://www.bcb.gov.br/",
        priority=10,
        allow_content_storage=True,
    ),
    NewsSource(
        source_id="bcb-copom-comunicados",
        name="Banco Central Comunicados Copom",
        source_type="official",
        reliability_layer="official",
        feed_url="https://www.bcb.gov.br/api/feed/sitebcb/sitefeeds/comunicadoscopom",
        homepage_url="https://www.bcb.gov.br/controleinflacao/copom",
        priority=11,
        allow_content_storage=True,
    ),
    NewsSource(
        source_id="b3-rss-news",
        name="B3 RSS News",
        source_type="official",
        reliability_layer="official",
        feed_url="https://www.b3.com.br/data/rss/suporteanegociacao.xml",
        homepage_url="https://www.b3.com.br/",
        priority=20,
        allow_content_storage=True,
    ),
    NewsSource(
        source_id="ibge-rss-news",
        name="IBGE Agencia de Noticias",
        source_type="official",
        reliability_layer="official",
        feed_url="https://agenciadenoticias.ibge.gov.br/agencia-rss",
        homepage_url="https://agenciadenoticias.ibge.gov.br/",
        priority=30,
        allow_content_storage=True,
    ),
    NewsSource(
        source_id="agencia-brasil-economia",
        name="Agencia Brasil Economia",
        source_type="general_press",
        reliability_layer="general_press",
        feed_url="https://agenciabrasil.ebc.com.br/rss/economia/feed.xml",
        homepage_url="https://agenciabrasil.ebc.com.br/economia",
        priority=60,
        allow_content_storage=False,
    ),
)


def builtin_sources() -> tuple[NewsSource, ...]:
    return BUILTIN_SOURCE_CATALOG
