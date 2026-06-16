from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltInTopic:
    topic_id: str
    label: str
    topic_type: str


@dataclass(frozen=True)
class BuiltInEventType:
    event_type_id: str
    category: str
    sub_event: str | None = None


@dataclass(frozen=True)
class BuiltInKeywordRule:
    keyword_rule_id: str
    group_name: str
    term: str
    aliases: tuple[str, ...] = ()
    priority: int = 100
    cd_cvm: int | None = None
    sector_slug: str | None = None
    topic_ids: tuple[str, ...] = ()
    event_type_ids: tuple[str, ...] = ()


BUILT_IN_TOPICS: tuple[BuiltInTopic, ...] = (
    BuiltInTopic("topic_macro_rates", "Interest rates", "macro"),
    BuiltInTopic("topic_macro_fx", "FX", "macro"),
    BuiltInTopic("topic_macro_inflation", "Inflation", "macro"),
    BuiltInTopic("topic_macro_china", "China", "macro"),
    BuiltInTopic("topic_markets_equities", "Equities", "markets"),
    BuiltInTopic("topic_markets_credit", "Credit", "markets"),
    BuiltInTopic("topic_markets_commodities", "Commodities", "markets"),
    BuiltInTopic("topic_regulation_cvm", "CVM regulation", "regulation"),
    BuiltInTopic("topic_governance", "Governance", "company"),
)


BUILT_IN_EVENT_TYPES: tuple[BuiltInEventType, ...] = (
    BuiltInEventType("event_earnings_results", "Earnings", "Results"),
    BuiltInEventType("event_dividends_approved", "Dividends", "Approved distribution"),
    BuiltInEventType("event_ma_transaction", "M&A", "Transaction"),
    BuiltInEventType("event_debt_issuance", "Debt", "Issuance"),
    BuiltInEventType("event_debt_covenant_breach", "Debt", "Covenant breach"),
    BuiltInEventType("event_credit_rating", "Credit", "Rating action"),
    BuiltInEventType("event_regulatory_filing", "Regulation", "Filing"),
    BuiltInEventType("event_governance_management", "Governance", "Management change"),
    BuiltInEventType("event_risk_liquidity", "Financial risk", "Liquidity"),
)


BUILT_IN_KEYWORD_RULES: tuple[BuiltInKeywordRule, ...] = (
    BuiltInKeywordRule(
        "kw_macro_selic",
        "Macro",
        "Selic",
        ("taxa Selic", "juros basicos", "basic interest rate"),
        20,
        topic_ids=("topic_macro_rates",),
    ),
    BuiltInKeywordRule(
        "kw_macro_inflation",
        "Macro",
        "inflation",
        ("IPCA", "IGP-M", "inflacao"),
        30,
        topic_ids=("topic_macro_inflation",),
    ),
    BuiltInKeywordRule(
        "kw_macro_fx",
        "Macro",
        "FX",
        ("dolar", "real", "cambio", "exchange rate", "USD/BRL"),
        30,
        topic_ids=("topic_macro_fx",),
    ),
    BuiltInKeywordRule(
        "kw_capital_markets_equity",
        "Capital markets",
        "follow-on",
        ("IPO", "oferta de acoes", "equity offering"),
        40,
        topic_ids=("topic_markets_equities",),
    ),
    BuiltInKeywordRule(
        "kw_credit_debenture",
        "Credit",
        "debenture",
        ("debentures", "CRI", "CRA"),
        40,
        topic_ids=("topic_markets_credit",),
        event_type_ids=("event_debt_issuance",),
    ),
    BuiltInKeywordRule(
        "kw_earnings_results",
        "Earnings",
        "results",
        ("resultado trimestral", "earnings", "lucro liquido", "EBITDA"),
        35,
        event_type_ids=("event_earnings_results",),
    ),
    BuiltInKeywordRule(
        "kw_ma_acquisition",
        "M&A",
        "acquisition",
        ("fusao", "aquisicao", "merger", "takeover"),
        35,
        event_type_ids=("event_ma_transaction",),
    ),
    BuiltInKeywordRule(
        "kw_dividends_jcp",
        "Dividends",
        "dividends",
        ("JCP", "juros sobre capital proprio", "dividendos"),
        30,
        event_type_ids=("event_dividends_approved",),
    ),
    BuiltInKeywordRule(
        "kw_regulation_cvm",
        "Regulation",
        "CVM",
        ("oficio CVM", "fato relevante", "comunicado ao mercado"),
        25,
        topic_ids=("topic_regulation_cvm",),
        event_type_ids=("event_regulatory_filing",),
    ),
    BuiltInKeywordRule(
        "kw_governance_management",
        "Governance",
        "management change",
        ("renuncia", "eleicao", "CEO", "CFO", "diretor de relacoes com investidores"),
        35,
        topic_ids=("topic_governance",),
        event_type_ids=("event_governance_management",),
    ),
    BuiltInKeywordRule(
        "kw_financial_risk_covenant",
        "Financial risk",
        "covenant",
        ("waiver", "liquidez", "alavancagem", "risco de credito"),
        25,
        topic_ids=("topic_markets_credit",),
        event_type_ids=("event_debt_covenant_breach", "event_risk_liquidity"),
    ),
    BuiltInKeywordRule(
        "kw_sector_commodities_iron_ore",
        "Sector-specific events",
        "iron ore",
        ("minerio de ferro", "China steel", "steel demand"),
        45,
        topic_ids=("topic_markets_commodities", "topic_macro_china"),
    ),
    BuiltInKeywordRule(
        "kw_sector_energy_power",
        "Sector-specific events",
        "electricity",
        ("ANEEL", "energia eletrica", "tarifa", "geracao", "transmissao"),
        45,
        topic_ids=("topic_regulation_cvm",),
    ),
    BuiltInKeywordRule(
        "kw_sector_oil_brent",
        "Sector-specific events",
        "oil",
        ("Brent", "petroleo", "OPEC", "refino"),
        45,
        topic_ids=("topic_markets_commodities",),
    ),
)


KEYWORD_TOPIC_LINKS: dict[str, tuple[str, ...]] = {
    rule.keyword_rule_id: rule.topic_ids for rule in BUILT_IN_KEYWORD_RULES if rule.topic_ids
}


KEYWORD_EVENT_TYPE_LINKS: dict[str, tuple[str, ...]] = {
    rule.keyword_rule_id: rule.event_type_ids for rule in BUILT_IN_KEYWORD_RULES if rule.event_type_ids
}
