"""Typed local repository for the canonical entity registry foundation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Engine, text

from src.companies.entity_registry_schema import (
    ALIAS_TYPES,
    ENTITY_KINDS,
    IDENTIFIER_CLAIM_STATUSES,
    IDENTIFIER_STRENGTHS,
    LIFECYCLE_STATUSES,
    ORIGINS,
    SOURCE_CLASSES,
    SOURCE_STATUSES,
    ensure_entity_registry_schema,
)


@dataclass(frozen=True)
class EntityRecord:
    entity_id: str
    entity_kind: str
    lifecycle_status: str
    lifecycle_reason: str | None
    created_origin: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_class: str
    source_status: str
    source_reference: str
    source_snapshot_reference: str | None
    raw_payload_reference: str | None
    observed_at: str | None
    retrieved_at: str | None
    created_at: str


@dataclass(frozen=True)
class IdentifierClaimRecord:
    claim_id: str
    entity_id: str
    namespace: str
    raw_value: str
    normalized_value: str
    normalizer_version: str
    scope_authority: str | None
    scope_country: str | None
    scope_context: str | None
    identifier_strength: str
    claim_status: str
    origin: str
    evidence_id: str | None
    evidence_status: str
    effective_from: str
    effective_to: str | None
    system_from: str
    system_to: str | None


@dataclass(frozen=True)
class AliasClaimRecord:
    alias_id: str
    entity_id: str
    alias_type: str
    raw_value: str
    locale: str | None
    origin: str
    evidence_id: str | None
    evidence_status: str
    effective_from: str
    effective_to: str | None
    system_from: str
    system_to: str | None


class EntityRegistryError(ValueError):
    """Base typed failure for registry commands."""


class EntityRegistryValidationError(EntityRegistryError):
    """A command conflicts with the approved registry contract."""


class EntityRegistryConflictError(EntityRegistryError):
    """A preserved competing claim blocks automatic identity action."""

    def __init__(self, code: str, claim_id: str) -> None:
        self.code = code
        self.claim_id = claim_id
        super().__init__(f"{code}: registry claim {claim_id} requires review")


@dataclass(frozen=True)
class _NamespaceRule:
    normalizer_version: str
    eligible_kind: str
    required_scope: str
    strong_requires_official_evidence: bool


_NAMESPACE_RULES = {
    "br.cvm.cd_cvm": _NamespaceRule("trim-exact/v1", "organization", "authority", True),
    "br.cnpj": _NamespaceRule("digits-only/v1", "organization", "country", True),
    "br.b3.ticker": _NamespaceRule("trim-exact/v1", "security_class", "context", False),
    "br.aneel.ceg": _NamespaceRule("trim-exact/v1", "plant_or_asset", "authority", True),
    "br.ccee.plant_parcel": _NamespaceRule("trim-exact/v1", "market_parcel", "authority", True),
    "br.aneel.regulated_agent_code": _NamespaceRule("trim-exact/v1", "organization", "context", False),
    "br.aneel.concession_code": _NamespaceRule("trim-exact/v1", "concession", "context", False),
}


class EntityRegistryRepository:
    """Repository with no remote lookup or legacy-table fallback behavior."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        ensure_entity_registry_schema(engine)

    def create_entity(self, entity_kind: str, *, origin: str) -> EntityRecord:
        self._require_allowed("entity kind", entity_kind, ENTITY_KINDS)
        self._require_allowed("origin", origin, ORIGINS)
        now = _utc_now()
        entity = EntityRecord(
            entity_id=uuid4().hex,
            entity_kind=entity_kind,
            lifecycle_status="active",
            lifecycle_reason=None,
            created_origin=origin,
            created_at=now,
            updated_at=now,
        )
        with self._engine.begin() as conn:
            self._enable_sqlite_foreign_keys(conn)
            conn.execute(
                text("""
                    INSERT INTO entity_registry_entities (
                        entity_id, entity_kind, lifecycle_status, lifecycle_reason,
                        created_origin, created_at, updated_at
                    ) VALUES (
                        :entity_id, :entity_kind, :lifecycle_status, :lifecycle_reason,
                        :created_origin, :created_at, :updated_at
                    )
                """),
                entity.__dict__,
            )
        return entity

    def get_entity(self, entity_id: str) -> EntityRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM entity_registry_entities WHERE entity_id = :entity_id"),
                {"entity_id": entity_id},
            ).mappings().one_or_none()
        return EntityRecord(**dict(row)) if row else None

    def change_lifecycle(
        self,
        entity_id: str,
        *,
        lifecycle_status: str,
        reason: str,
        replacement_entity_id: str | None = None,
    ) -> EntityRecord:
        if replacement_entity_id is not None:
            raise EntityRegistryValidationError("entity_id is immutable and cannot be replaced")
        self._require_allowed("lifecycle status", lifecycle_status, LIFECYCLE_STATUSES)
        if not reason.strip():
            raise EntityRegistryValidationError("lifecycle reason is required")
        updated_at = _utc_now()
        with self._engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE entity_registry_entities
                    SET lifecycle_status = :lifecycle_status,
                        lifecycle_reason = :reason,
                        updated_at = :updated_at
                    WHERE entity_id = :entity_id
                """),
                {
                    "entity_id": entity_id,
                    "lifecycle_status": lifecycle_status,
                    "reason": reason,
                    "updated_at": updated_at,
                },
            )
            if result.rowcount != 1:
                raise EntityRegistryValidationError(f"unknown entity_id: {entity_id}")
        entity = self.get_entity(entity_id)
        assert entity is not None
        return entity

    def record_evidence(
        self,
        *,
        source_class: str,
        source_reference: str,
        source_status: str = "available",
        source_snapshot_reference: str | None = None,
        raw_payload_reference: str | None = None,
        observed_at: str | None = None,
        retrieved_at: str | None = None,
    ) -> EvidenceRecord:
        self._require_allowed("source class", source_class, SOURCE_CLASSES)
        self._require_allowed("source status", source_status, SOURCE_STATUSES)
        if not source_reference.strip():
            raise EntityRegistryValidationError("source reference is required")
        evidence = EvidenceRecord(
            evidence_id=uuid4().hex,
            source_class=source_class,
            source_status=source_status,
            source_reference=source_reference,
            source_snapshot_reference=source_snapshot_reference,
            raw_payload_reference=raw_payload_reference,
            observed_at=observed_at,
            retrieved_at=retrieved_at,
            created_at=_utc_now(),
        )
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO entity_registry_evidence (
                        evidence_id, source_class, source_status, source_reference,
                        source_snapshot_reference, raw_payload_reference, observed_at,
                        retrieved_at, created_at
                    ) VALUES (
                        :evidence_id, :source_class, :source_status, :source_reference,
                        :source_snapshot_reference, :raw_payload_reference, :observed_at,
                        :retrieved_at, :created_at
                    )
                """),
                evidence.__dict__,
            )
        return evidence

    def claim_identifier(
        self,
        *,
        entity_id: str,
        namespace: str,
        raw_value: str,
        scope_authority: str | None = None,
        scope_country: str | None = None,
        scope_context: str | None = None,
        identifier_strength: str,
        evidence_id: str | None,
        origin: str = "source_ingestion",
        effective_from: str | None = None,
        effective_to: str | None = None,
    ) -> IdentifierClaimRecord:
        self._require_allowed("identifier strength", identifier_strength, IDENTIFIER_STRENGTHS)
        self._require_allowed("origin", origin, ORIGINS)
        rule = _NAMESPACE_RULES.get(namespace)
        if rule is None:
            raise EntityRegistryValidationError(f"unknown namespace: {namespace}")
        entity = self.get_entity(entity_id)
        if entity is None:
            raise EntityRegistryValidationError(f"unknown entity_id: {entity_id}")
        if entity.entity_kind != rule.eligible_kind:
            raise EntityRegistryValidationError(
                f"namespace {namespace} is ineligible for entity kind {entity.entity_kind}"
            )
        self._validate_scope(rule.required_scope, scope_authority, scope_country, scope_context)
        normalized_value = self._normalize(namespace, raw_value)
        evidence = self._get_evidence(evidence_id)
        if identifier_strength == "strong":
            if evidence is None or not rule.strong_requires_official_evidence or evidence.source_class not in {
                "official_primary", "official_external"
            }:
                raise EntityRegistryValidationError("strong identifier requires qualifying official evidence")
        elif evidence is None and evidence_id is not None:
            raise EntityRegistryValidationError(f"unknown evidence_id: {evidence_id}")

        now = _utc_now()
        effective_from = effective_from or now
        if effective_to is not None and effective_from >= effective_to:
            raise EntityRegistryValidationError("invalid effective interval")
        claim_id = uuid4().hex
        collision = identifier_strength == "strong" and self._find_active_strong_collision(
            namespace,
            normalized_value,
            scope_authority,
            scope_country,
            scope_context,
            entity_id,
            effective_from,
            effective_to,
        )
        claim_status = "conflicted" if collision else "accepted"
        claim = IdentifierClaimRecord(
            claim_id=claim_id,
            entity_id=entity_id,
            namespace=namespace,
            raw_value=raw_value,
            normalized_value=normalized_value,
            normalizer_version=rule.normalizer_version,
            scope_authority=scope_authority,
            scope_country=scope_country,
            scope_context=scope_context,
            identifier_strength=identifier_strength,
            claim_status=claim_status,
            origin=origin,
            evidence_id=evidence_id,
            evidence_status="linked" if evidence else "none",
            effective_from=effective_from,
            effective_to=effective_to,
            system_from=now,
            system_to=None,
        )
        with self._engine.begin() as conn:
            self._enable_sqlite_foreign_keys(conn)
            conn.execute(
                text("""
                    INSERT INTO entity_registry_identifier_claims (
                        claim_id, entity_id, namespace, raw_value, normalized_value,
                        normalizer_version, scope_authority, scope_country, scope_context,
                        identifier_strength, claim_status, origin, evidence_id, evidence_status,
                        effective_from, effective_to, system_from, system_to
                    ) VALUES (
                        :claim_id, :entity_id, :namespace, :raw_value, :normalized_value,
                        :normalizer_version, :scope_authority, :scope_country, :scope_context,
                        :identifier_strength, :claim_status, :origin, :evidence_id, :evidence_status,
                        :effective_from, :effective_to, :system_from, :system_to
                    )
                """),
                claim.__dict__,
            )
        if collision:
            raise EntityRegistryConflictError("duplicate_strong_id", claim_id)
        return claim

    def find_identifier_claims(
        self, namespace: str, raw_value: str, scope_authority: str | None = None
    ) -> list[IdentifierClaimRecord]:
        normalized_value = self._normalize(namespace, raw_value)
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT * FROM entity_registry_identifier_claims
                    WHERE namespace = :namespace
                      AND normalized_value = :normalized_value
                      AND ((scope_authority = :scope_authority)
                           OR (scope_authority IS NULL AND :scope_authority IS NULL))
                    ORDER BY claim_id
                """),
                {
                    "namespace": namespace,
                    "normalized_value": normalized_value,
                    "scope_authority": scope_authority,
                },
            ).mappings().all()
        return [IdentifierClaimRecord(**dict(row)) for row in rows]

    def claim_alias(
        self,
        *,
        entity_id: str,
        alias_type: str,
        raw_value: str,
        evidence_id: str | None,
        origin: str = "source_ingestion",
        locale: str | None = None,
        effective_from: str | None = None,
        effective_to: str | None = None,
    ) -> AliasClaimRecord:
        self._require_allowed("alias type", alias_type, ALIAS_TYPES)
        self._require_allowed("origin", origin, ORIGINS)
        if self.get_entity(entity_id) is None:
            raise EntityRegistryValidationError(f"unknown entity_id: {entity_id}")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise EntityRegistryValidationError("alias value is required")
        evidence = self._get_evidence(evidence_id)
        if evidence_id is not None and evidence is None:
            raise EntityRegistryValidationError(f"unknown evidence_id: {evidence_id}")
        now = _utc_now()
        effective_from = effective_from or now
        if effective_to is not None and effective_from >= effective_to:
            raise EntityRegistryValidationError("invalid effective interval")
        alias = AliasClaimRecord(
            alias_id=uuid4().hex,
            entity_id=entity_id,
            alias_type=alias_type,
            raw_value=raw_value,
            locale=locale,
            origin=origin,
            evidence_id=evidence_id,
            evidence_status="linked" if evidence else "none",
            effective_from=effective_from,
            effective_to=effective_to,
            system_from=now,
            system_to=None,
        )
        with self._engine.begin() as conn:
            self._enable_sqlite_foreign_keys(conn)
            conn.execute(
                text("""
                    INSERT INTO entity_registry_alias_claims (
                        alias_id, entity_id, alias_type, raw_value, locale, origin,
                        evidence_id, evidence_status, effective_from, effective_to,
                        system_from, system_to
                    ) VALUES (
                        :alias_id, :entity_id, :alias_type, :raw_value, :locale, :origin,
                        :evidence_id, :evidence_status, :effective_from, :effective_to,
                        :system_from, :system_to
                    )
                """),
                alias.__dict__,
            )
        return alias

    def find_entities_by_identifier(
        self, namespace: str, raw_value: str, scope_authority: str | None = None
    ) -> list[EntityRecord]:
        claims = self.find_identifier_claims(namespace, raw_value, scope_authority)
        entities = [self.get_entity(claim.entity_id) for claim in claims if claim.claim_status == "accepted"]
        return [entity for entity in entities if entity is not None]

    def _find_active_strong_collision(
        self,
        namespace: str,
        normalized_value: str,
        scope_authority: str | None,
        scope_country: str | None,
        scope_context: str | None,
        entity_id: str,
        effective_from: str,
        effective_to: str | None,
    ) -> bool:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT 1 FROM entity_registry_identifier_claims
                    WHERE namespace = :namespace
                      AND normalized_value = :normalized_value
                      AND identifier_strength = 'strong'
                      AND claim_status = 'accepted'
                      AND entity_id <> :entity_id
                      AND ((scope_authority = :scope_authority)
                           OR (scope_authority IS NULL AND :scope_authority IS NULL))
                      AND ((scope_country = :scope_country)
                           OR (scope_country IS NULL AND :scope_country IS NULL))
                      AND ((scope_context = :scope_context)
                           OR (scope_context IS NULL AND :scope_context IS NULL))
                      AND (effective_to IS NULL OR effective_to > :effective_from)
                      AND (:effective_to IS NULL OR effective_from < :effective_to)
                    LIMIT 1
                """),
                {
                    "namespace": namespace,
                    "normalized_value": normalized_value,
                    "scope_authority": scope_authority,
                    "scope_country": scope_country,
                    "scope_context": scope_context,
                    "entity_id": entity_id,
                    "effective_from": effective_from,
                    "effective_to": effective_to,
                },
            ).first()
        return row is not None

    def _get_evidence(self, evidence_id: str | None) -> EvidenceRecord | None:
        if evidence_id is None:
            return None
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM entity_registry_evidence WHERE evidence_id = :evidence_id"),
                {"evidence_id": evidence_id},
            ).mappings().one_or_none()
        return EvidenceRecord(**dict(row)) if row else None

    @staticmethod
    def _normalize(namespace: str, raw_value: str) -> str:
        if namespace not in _NAMESPACE_RULES:
            raise EntityRegistryValidationError(f"unknown namespace: {namespace}")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise EntityRegistryValidationError("malformed identifier value")
        if namespace == "br.cnpj":
            normalized = raw_value.strip().replace(".", "").replace("/", "").replace("-", "")
            if not normalized.isdigit() or len(normalized) != 14:
                raise EntityRegistryValidationError("CNPJ must contain 14 digits")
            return normalized
        return raw_value.strip()

    @staticmethod
    def _validate_scope(
        required_scope: str,
        authority: str | None,
        country: str | None,
        context: str | None,
    ) -> None:
        values = {"authority": authority, "country": country, "context": context}
        if not values[required_scope] or not str(values[required_scope]).strip():
            raise EntityRegistryValidationError(f"namespace requires scope {required_scope}")

    @staticmethod
    def _require_allowed(label: str, value: str, allowed: tuple[str, ...]) -> None:
        if value not in allowed:
            raise EntityRegistryValidationError(f"invalid {label}: {value}")

    def _enable_sqlite_foreign_keys(self, conn) -> None:
        if self._engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA foreign_keys = ON"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
