from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.news.classifier import ArticleClassification


@dataclass(frozen=True)
class ArticleScore:
    total_score: float
    priority_level: str
    components: dict[str, float]
    reasons: tuple[str, ...]


SOURCE_RELIABILITY_WEIGHTS = {
    "official": 1.0,
    "agency": 0.85,
    "financial_press": 0.75,
    "specialized": 0.7,
    "general_press": 0.55,
    "user_provided": 0.45,
}


def score_article(
    *,
    source: Any,
    published_at: str | None,
    discovered_at: str,
    classification: ArticleClassification,
) -> ArticleScore:
    components: dict[str, float] = {
        "company_relevance": _bounded_sum(match.relevance_score for match in classification.company_matches),
        "sector_relevance": _bounded_sum(match.relevance_score for match in classification.sector_matches) * 0.7,
        "keyword_relevance": _bounded_sum(match.relevance_score for match in classification.keyword_matches),
        "event_relevance": _bounded_sum(match.relevance_score for match in classification.event_type_matches),
        "source_reliability": _source_reliability(source),
        "freshness": _freshness_score(published_at or discovered_at),
        "user_relevance": 0.0,
    }
    total = round(sum(components.values()), 4)
    priority = _priority_level(total=total, classification=classification)
    return ArticleScore(
        total_score=total,
        priority_level=priority,
        components=components,
        reasons=tuple(_score_reasons(source=source, classification=classification, components=components, priority=priority)),
    )


def _bounded_sum(values) -> float:
    return round(min(1.0, sum(float(value or 0.0) for value in values)), 4)


def _source_reliability(source: Any) -> float:
    layer = str(source.reliability_layer or "").strip().lower()
    if layer in SOURCE_RELIABILITY_WEIGHTS:
        return SOURCE_RELIABILITY_WEIGHTS[layer]
    source_type = str(source.source_type or "").strip().lower()
    return SOURCE_RELIABILITY_WEIGHTS.get(source_type, 0.5)


def _freshness_score(value: str | None) -> float:
    if not value:
        return 0.25
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0.25
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600)
    if age_hours <= 6:
        return 1.0
    if age_hours <= 24:
        return 0.8
    if age_hours <= 72:
        return 0.55
    if age_hours <= 168:
        return 0.35
    return 0.15


def _priority_level(*, total: float, classification: ArticleClassification) -> str:
    has_critical_event = any(
        match.event_type_id in {"event_debt_covenant_breach", "event_risk_liquidity"}
        for match in classification.event_type_matches
    )
    if has_critical_event and classification.company_matches:
        return "Critical"
    if total >= 4.2:
        return "Critical"
    if total >= 2.6:
        return "High"
    return "Normal"


def _score_reasons(
    *,
    source: Any,
    classification: ArticleClassification,
    components: dict[str, float],
    priority: str,
) -> list[str]:
    reasons = [
        f"Source reliability component {components['source_reliability']:.2f} from {source.reliability_layer}",
        f"Freshness component {components['freshness']:.2f}",
    ]
    if classification.company_matches:
        reasons.append(f"{len(classification.company_matches)} company match(es) contributed {components['company_relevance']:.2f}")
    if classification.sector_matches:
        reasons.append(f"{len(classification.sector_matches)} sector match(es) contributed {components['sector_relevance']:.2f}")
    if classification.keyword_matches:
        reasons.append(f"{len(classification.keyword_matches)} keyword match(es) contributed {components['keyword_relevance']:.2f}")
    if classification.event_type_matches:
        reasons.append(f"{len(classification.event_type_matches)} event match(es) contributed {components['event_relevance']:.2f}")
    reasons.append(f"Priority set to {priority} by deterministic score rules")
    return reasons
