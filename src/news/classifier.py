from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from src.companies.sector_taxonomy import sector_slugify
from src.news.taxonomy import KEYWORD_EVENT_TYPE_LINKS, KEYWORD_TOPIC_LINKS


@dataclass(frozen=True)
class KeywordMatch:
    keyword_rule_id: str
    matched_term: str
    match_method: str
    match_reason: str
    relevance_score: float


@dataclass(frozen=True)
class TopicMatch:
    topic_id: str
    match_method: str
    match_reason: str
    relevance_score: float


@dataclass(frozen=True)
class EventTypeMatch:
    event_type_id: str
    match_method: str
    match_reason: str
    relevance_score: float


@dataclass(frozen=True)
class CompanyMatch:
    cd_cvm: int
    match_method: str
    match_reason: str
    relevance_score: float
    rule_strength: float
    is_primary: bool


@dataclass(frozen=True)
class SectorMatch:
    sector_slug: str
    sector_name: str
    match_method: str
    match_reason: str
    relevance_score: float
    rule_strength: float
    is_primary: bool
    parent_sector_slug: str | None = None
    parent_sector_name: str | None = None


@dataclass(frozen=True)
class ArticleClassification:
    keyword_matches: tuple[KeywordMatch, ...]
    topic_matches: tuple[TopicMatch, ...]
    event_type_matches: tuple[EventTypeMatch, ...]
    company_matches: tuple[CompanyMatch, ...] = ()
    sector_matches: tuple[SectorMatch, ...] = ()


def classify_article_text(
    *,
    title: str,
    summary: str | None,
    keyword_rules: list[dict[str, Any]],
    company_rows: list[dict[str, Any]] | None = None,
) -> ArticleClassification:
    title_text = _normalize(title)
    summary_text = _normalize(summary or "")
    keyword_matches: list[KeywordMatch] = []
    topic_matches_by_id: dict[str, TopicMatch] = {}
    event_matches_by_id: dict[str, EventTypeMatch] = {}

    for rule in keyword_rules:
        matched = _match_rule(rule, title_text=title_text, summary_text=summary_text)
        if matched is None:
            continue
        matched_term, location = matched
        score = _score_rule(rule, location)
        reason = f"Matched keyword rule {rule['keyword_rule_id']} term '{matched_term}' in {location}"
        keyword_matches.append(
            KeywordMatch(
                keyword_rule_id=str(rule["keyword_rule_id"]),
                matched_term=matched_term,
                match_method="keyword_exact",
                match_reason=reason,
                relevance_score=score,
            )
        )
        for topic_id in KEYWORD_TOPIC_LINKS.get(str(rule["keyword_rule_id"]), ()):
            topic_matches_by_id[topic_id] = TopicMatch(
                topic_id=topic_id,
                match_method="keyword_rule",
                match_reason=reason,
                relevance_score=score,
            )
        for event_type_id in KEYWORD_EVENT_TYPE_LINKS.get(str(rule["keyword_rule_id"]), ()):
            event_matches_by_id[event_type_id] = EventTypeMatch(
                event_type_id=event_type_id,
                match_method="keyword_rule",
                match_reason=reason,
                relevance_score=score,
            )

    company_matches = tuple(_match_companies(title=title, summary=summary, company_rows=company_rows or []))
    return ArticleClassification(
        keyword_matches=tuple(keyword_matches),
        topic_matches=tuple(topic_matches_by_id.values()),
        event_type_matches=tuple(event_matches_by_id.values()),
        company_matches=company_matches,
        sector_matches=tuple(_sector_matches_from_companies(company_matches, company_rows or [])),
    )


def _match_companies(
    *,
    title: str,
    summary: str | None,
    company_rows: list[dict[str, Any]],
) -> list[CompanyMatch]:
    title_text = _normalize(title)
    summary_text = _normalize(summary or "")
    matches_by_company: dict[int, CompanyMatch] = {}
    for row in company_rows:
        cd_cvm = int(row["cd_cvm"])
        candidates = _company_candidates(row)
        for candidate in candidates:
            location = _candidate_location(candidate["value"], title_text=title_text, summary_text=summary_text)
            if location is None:
                continue
            match = CompanyMatch(
                cd_cvm=cd_cvm,
                match_method=str(candidate["method"]),
                match_reason=f"Matched company CVM {cd_cvm} by {candidate['method']} '{candidate['value']}' in {location}",
                relevance_score=1.0 if location == "title" else 0.75,
                rule_strength=float(candidate["strength"]),
                is_primary=location == "title",
            )
            previous = matches_by_company.get(cd_cvm)
            if previous is None or (match.relevance_score, match.rule_strength) > (
                previous.relevance_score,
                previous.rule_strength,
            ):
                matches_by_company[cd_cvm] = match
    return sorted(
        matches_by_company.values(),
        key=lambda item: (not item.is_primary, -item.relevance_score, -item.rule_strength, item.cd_cvm),
    )


def _company_candidates(row: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    ticker = str(row.get("ticker_b3") or "").strip().upper().replace(".SA", "")
    if ticker:
        candidates.append({"method": "ticker", "value": ticker, "strength": 1.0})
    cnpj = "".join(char for char in str(row.get("cnpj") or "") if char.isdigit())
    if len(cnpj) == 14:
        candidates.append({"method": "cnpj", "value": cnpj, "strength": 1.0})
    for field_name, method, strength in (
        ("nome_comercial", "trade_name", 0.85),
        ("company_name", "legal_name", 0.75),
    ):
        value = str(row.get(field_name) or "").strip()
        if _is_usable_company_name(value):
            candidates.append({"method": method, "value": value, "strength": strength})
    return candidates


def _candidate_location(value: str, *, title_text: str, summary_text: str) -> str | None:
    normalized = _normalize(value)
    if not normalized:
        return None
    pattern = re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)")
    if pattern.search(title_text):
        return "title"
    if summary_text and pattern.search(summary_text):
        return "summary"
    if value.isdigit() and value in re.sub(r"\D", "", title_text + " " + summary_text):
        return "text"
    return None


def _is_usable_company_name(value: str) -> bool:
    normalized = _normalize(value).strip()
    if len(normalized) < 5:
        return False
    if not any(char.isalpha() for char in normalized):
        return False
    return normalized not in {"companhia", "cia", "banco", "brasil", "holding", "participacoes"}


def _sector_matches_from_companies(
    company_matches: tuple[CompanyMatch, ...],
    company_rows: list[dict[str, Any]],
) -> list[SectorMatch]:
    rows_by_cvm = {int(row["cd_cvm"]): row for row in company_rows}
    matches_by_key: dict[tuple[str, str | None], SectorMatch] = {}
    for company_match in company_matches:
        row = rows_by_cvm.get(company_match.cd_cvm)
        if not row:
            continue
        sector_name = _first_text(row.get("gics_sector"), row.get("setor_analitico"), row.get("setor_cvm"))
        if not sector_name:
            continue
        sector_slug = str(row.get("gics_sector_slug") or sector_slugify(sector_name)).strip()
        sub_industry = _first_text(row.get("gics_sub_industry"))
        reason = (
            f"Matched sector from company CVM {company_match.cd_cvm}: "
            f"{company_match.match_reason}"
        )
        sector_match = SectorMatch(
            sector_slug=sector_slug,
            sector_name=sector_name,
            match_method="company_sector",
            match_reason=reason,
            relevance_score=round(company_match.relevance_score * 0.8, 4),
            rule_strength=company_match.rule_strength,
            is_primary=company_match.is_primary,
        )
        matches_by_key[(sector_match.sector_slug, None)] = _prefer_sector_match(
            matches_by_key.get((sector_match.sector_slug, None)),
            sector_match,
        )
        if sub_industry:
            sub_match = SectorMatch(
                sector_slug=sector_slugify(sub_industry),
                sector_name=sub_industry,
                parent_sector_slug=sector_slug,
                parent_sector_name=sector_name,
                match_method="company_sub_industry",
                match_reason=reason,
                relevance_score=round(company_match.relevance_score * 0.85, 4),
                rule_strength=company_match.rule_strength,
                is_primary=company_match.is_primary,
            )
            matches_by_key[(sub_match.sector_slug, sub_match.parent_sector_slug)] = _prefer_sector_match(
                matches_by_key.get((sub_match.sector_slug, sub_match.parent_sector_slug)),
                sub_match,
            )
    return sorted(
        matches_by_key.values(),
        key=lambda item: (not item.is_primary, -item.relevance_score, item.parent_sector_slug or "", item.sector_slug),
    )


def _prefer_sector_match(existing: SectorMatch | None, candidate: SectorMatch) -> SectorMatch:
    if existing is None:
        return candidate
    if (candidate.relevance_score, candidate.rule_strength) > (existing.relevance_score, existing.rule_strength):
        return candidate
    return existing


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _match_rule(
    rule: dict[str, Any],
    *,
    title_text: str,
    summary_text: str,
) -> tuple[str, str] | None:
    terms = [str(rule["term"]), *[str(alias) for alias in rule.get("aliases", [])]]
    for term in terms:
        pattern = _term_pattern(term)
        if pattern.search(title_text):
            return term, "title"
        if summary_text and pattern.search(summary_text):
            return term, "summary"
    return None


def _score_rule(rule: dict[str, Any], location: str) -> float:
    priority = int(rule.get("priority") or 100)
    priority_component = max(0.0, min(1.0, (120 - priority) / 100))
    location_component = 1.0 if location == "title" else 0.7
    return round(priority_component * location_component, 4)


def _term_pattern(term: str) -> re.Pattern[str]:
    normalized = _normalize(term)
    return re.compile(rf"(?<!\w){re.escape(normalized)}(?!\w)")


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return without_marks.casefold()
