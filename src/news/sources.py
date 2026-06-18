from __future__ import annotations

from urllib.parse import quote_plus

from src.news.repository import NewsSource


def _google_news_search_url(query: str) -> str:
    encoded_query = quote_plus(query.strip())
    return f"https://news.google.com/rss/search?q={encoded_query}&hl=pt-BR&gl=BR&ceid=BR:pt-BR"


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
    NewsSource(
        source_id="google-topic-brazil-markets",
        name="Google News - Brazil Markets",
        source_type="aggregator_search",
        reliability_layer="aggregator",
        feed_url=_google_news_search_url(
            '("mercado financeiro" OR Ibovespa OR B3 OR bolsa) Brasil ações economia'
        ),
        homepage_url="https://news.google.com/",
        priority=120,
        allow_content_storage=False,
    ),
    NewsSource(
        source_id="google-topic-brazil-macro",
        name="Google News - Brazil Macro",
        source_type="aggregator_search",
        reliability_layer="aggregator",
        feed_url=_google_news_search_url(
            '(Selic OR Copom OR inflação OR IPCA OR "juros" OR câmbio OR dólar) Brasil economia'
        ),
        homepage_url="https://news.google.com/",
        priority=121,
        allow_content_storage=False,
    ),
    NewsSource(
        source_id="google-topic-brazil-business",
        name="Google News - Brazil Companies",
        source_type="aggregator_search",
        reliability_layer="aggregator",
        feed_url=_google_news_search_url(
            'empresas brasileiras resultados dividendos fusões aquisições investimento mercado'
        ),
        homepage_url="https://news.google.com/",
        priority=122,
        allow_content_storage=False,
    ),
    NewsSource(
        source_id="google-topic-commodities",
        name="Google News - Commodities",
        source_type="aggregator_search",
        reliability_layer="aggregator",
        feed_url=_google_news_search_url(
            'petróleo minério de ferro soja commodities China Brasil mercado'
        ),
        homepage_url="https://news.google.com/",
        priority=123,
        allow_content_storage=False,
    ),
    NewsSource(
        source_id="google-topic-global-macro",
        name="Google News - Global Macro",
        source_type="aggregator_search",
        reliability_layer="aggregator",
        feed_url=_google_news_search_url(
            'Fed China juros dólar commodities mercados emergentes Brasil'
        ),
        homepage_url="https://news.google.com/",
        priority=124,
        allow_content_storage=False,
    ),
    NewsSource(
        source_id="google-topic-regulation",
        name="Google News - Regulation",
        source_type="aggregator_search",
        reliability_layer="aggregator",
        feed_url=_google_news_search_url(
            'CVM Banco Central CADE ANEEL ANP regulação empresas Brasil mercado'
        ),
        homepage_url="https://news.google.com/",
        priority=125,
        allow_content_storage=False,
    ),
    NewsSource(
        source_id="google-topic-sector-energy-utilities",
        name="Google News - Energy and Utilities",
        source_type="aggregator_search",
        reliability_layer="aggregator",
        feed_url=_google_news_search_url(
            'energia elétrica saneamento óleo gás utilities empresas Brasil'
        ),
        homepage_url="https://news.google.com/",
        priority=126,
        allow_content_storage=False,
    ),
    NewsSource(
        source_id="google-topic-sector-financials",
        name="Google News - Financials",
        source_type="aggregator_search",
        reliability_layer="aggregator",
        feed_url=_google_news_search_url(
            'bancos seguradoras fintechs crédito inadimplência mercado financeiro Brasil'
        ),
        homepage_url="https://news.google.com/",
        priority=127,
        allow_content_storage=False,
    ),
)


def builtin_sources() -> tuple[NewsSource, ...]:
    return BUILTIN_SOURCE_CATALOG
