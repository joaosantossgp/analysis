"""Typed local repository for the canonical entity registry foundation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import re
import time
from uuid import uuid4

from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from src.companies.entity_registry_schema import (
    ALIAS_TYPES,
    ENTITY_KINDS,
    IDENTIFIER_CLAIM_STATUSES,
    IDENTIFIER_STRENGTHS,
    LIFECYCLE_STATUSES,
    ORGANIZATION_FACETS,
    ORIGINS,
    SOURCE_CLASSES,
    SOURCE_STATUSES,
    validate_entity_registry_schema,
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
    source_authority: str | None
    qualified_namespace: str | None
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


@dataclass(frozen=True)
class OrganizationFacetRecord:
    facet_id: str
    entity_id: str
    facet: str
    eligibility_status: str
    origin: str
    evidence_id: str | None
    evidence_status: str
    effective_from: str
    effective_to: str | None
    system_from: str
    system_to: str | None


@dataclass(frozen=True)
class LifecycleEventRecord:
    lifecycle_event_id: str
    entity_id: str
    lifecycle_status: str
    reason: str
    origin: str
    evidence_id: str
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
    required_scopes: tuple[str, ...]
    required_organization_facet: str | None
    strong_requires_official_evidence: bool
    expected_scope_authority: str | None = None
    expected_scope_country: str | None = None
    expected_evidence_authorities: tuple[str, ...] = ()
    overlap_requires_review: bool = False


_NAMESPACE_RULES = {
    "br.cvm.cd_cvm": _NamespaceRule(
        "trim-exact/v1", "organization", ("authority",), "issuer", True,
        expected_scope_authority="CVM", expected_evidence_authorities=("CVM",),
    ),
    "br.cnpj": _NamespaceRule(
        "digits-only/v1", "organization", ("country",), "legal_entity", True,
        expected_scope_country="BR", expected_evidence_authorities=("CVM", "RECEITA_FEDERAL"),
        overlap_requires_review=True,
    ),
    "br.b3.ticker": _NamespaceRule(
        "trim-exact/v1", "security_class", ("authority", "context"), None, False,
        expected_scope_authority="B3", overlap_requires_review=True,
    ),
    "br.aneel.ceg": _NamespaceRule(
        "trim-exact/v1", "plant_or_asset", ("authority",), None, True,
        expected_scope_authority="ANEEL", expected_evidence_authorities=("ANEEL",),
        overlap_requires_review=True,
    ),
    "br.ccee.plant_parcel": _NamespaceRule(
        "trim-exact/v1", "market_parcel", ("authority",), None, True,
        expected_scope_authority="CCEE", expected_evidence_authorities=("CCEE",),
        overlap_requires_review=True,
    ),
}
_DYNAMIC_NAMESPACE_PATTERN = re.compile(
    r"^br\.([a-z][a-z0-9_]*)\.(regulated_agent_code|concession_code)$"
)


class EntityRegistryRepository:
    """Repository with no remote lookup or legacy-table fallback behavior."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        validate_entity_registry_schema(engine)

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
                text("""
                    SELECT entity_id, entity_kind,
                           COALESCE((
                               SELECT lifecycle_status
                               FROM entity_registry_lifecycle_events
                               WHERE entity_id = entity_registry_entities.entity_id
                                 AND system_to IS NULL
                               ORDER BY system_from DESC, lifecycle_event_id DESC
                               LIMIT 1
                           ), lifecycle_status) AS lifecycle_status,
                           COALESCE((
                               SELECT reason
                               FROM entity_registry_lifecycle_events
                               WHERE entity_id = entity_registry_entities.entity_id
                                 AND system_to IS NULL
                               ORDER BY system_from DESC, lifecycle_event_id DESC
                               LIMIT 1
                           ), lifecycle_reason) AS lifecycle_reason,
                           created_origin, created_at, updated_at
                    FROM entity_registry_entities
                    WHERE entity_id = :entity_id
                """),
                {"entity_id": entity_id},
            ).mappings().one_or_none()
        return EntityRecord(**dict(row)) if row else None

    def change_lifecycle(
        self,
        entity_id: str,
        *,
        lifecycle_status: str,
        reason: str,
        evidence_id: str | None = None,
        origin: str = "source_ingestion",
        effective_from: str | None = None,
        effective_to: str | None = None,
        replacement_entity_id: str | None = None,
    ) -> EntityRecord:
        if replacement_entity_id is not None:
            raise EntityRegistryValidationError("entity_id is immutable and cannot be replaced")
        self._require_allowed("lifecycle status", lifecycle_status, LIFECYCLE_STATUSES)
        self._require_allowed("origin", origin, ORIGINS)
        if not reason.strip():
            raise EntityRegistryValidationError("lifecycle reason is required")
        evidence = self._get_evidence(evidence_id)
        if evidence is None:
            raise EntityRegistryValidationError("lifecycle change requires evidence")
        now = _utc_now()
        effective_from, effective_to = self._canonicalize_effective_interval(
            effective_from, effective_to, now
        )
        event = LifecycleEventRecord(
            lifecycle_event_id=uuid4().hex,
            entity_id=entity_id,
            lifecycle_status=lifecycle_status,
            reason=reason,
            origin=origin,
            evidence_id=evidence.evidence_id,
            evidence_status=evidence.source_status,
            effective_from=effective_from,
            effective_to=effective_to,
            system_from=now,
            system_to=None,
        )
        with self._engine.begin() as conn:
            self._serialize_entity_lifecycle_guard(conn, entity_id)
            result = conn.execute(
                text("""
                    INSERT INTO entity_registry_lifecycle_events (
                        lifecycle_event_id, entity_id, lifecycle_status, reason, origin,
                        evidence_id, evidence_status, effective_from, effective_to,
                        system_from, system_to
                    ) VALUES (
                        :lifecycle_event_id, :entity_id, :lifecycle_status, :reason, :origin,
                        :evidence_id, :evidence_status, :effective_from, :effective_to,
                        :system_from, :system_to
                    )
                """),
                event.__dict__,
            )
            if result.rowcount not in (None, 1):
                raise EntityRegistryValidationError(f"unknown entity_id: {entity_id}")
        entity = self.get_entity(entity_id)
        assert entity is not None
        return entity

    def get_lifecycle_events(self, entity_id: str) -> list[LifecycleEventRecord]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT * FROM entity_registry_lifecycle_events
                    WHERE entity_id = :entity_id
                    ORDER BY system_from, lifecycle_event_id
                """),
                {"entity_id": entity_id},
            ).mappings().all()
        return [LifecycleEventRecord(**dict(row)) for row in rows]

    def record_evidence(
        self,
        *,
        source_class: str,
        source_reference: str,
        source_status: str = "available",
        source_authority: str | None = None,
        qualified_namespace: str | None = None,
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
            source_authority=source_authority.strip().upper() if source_authority else None,
            qualified_namespace=qualified_namespace,
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
                        evidence_id, source_class, source_status, source_authority, qualified_namespace, source_reference,
                        source_snapshot_reference, raw_payload_reference, observed_at,
                        retrieved_at, created_at
                    ) VALUES (
                        :evidence_id, :source_class, :source_status, :source_authority, :qualified_namespace, :source_reference,
                        :source_snapshot_reference, :raw_payload_reference, :observed_at,
                        :retrieved_at, :created_at
                    )
                """),
                evidence.__dict__,
            )
        return evidence

    def add_organization_facet(
        self,
        *,
        entity_id: str,
        facet: str,
        evidence_id: str | None,
        effective_from: str | None = None,
        effective_to: str | None = None,
        origin: str = "source_ingestion",
        eligibility_status: str = "active",
    ) -> OrganizationFacetRecord:
        entity = self.get_entity(entity_id)
        if entity is None:
            raise EntityRegistryValidationError(f"unknown entity_id: {entity_id}")
        if entity.entity_kind != "organization":
            raise EntityRegistryValidationError("organization facets require an organization")
        self._require_allowed("organization facet", facet, ORGANIZATION_FACETS)
        self._require_allowed("origin", origin, ORIGINS)
        if eligibility_status not in {"active", "inactive"}:
            raise EntityRegistryValidationError(f"invalid facet eligibility status: {eligibility_status}")
        evidence = self._get_evidence(evidence_id)
        if evidence_id is not None and evidence is None:
            raise EntityRegistryValidationError(f"unknown evidence_id: {evidence_id}")
        now = _utc_now()
        effective_from, effective_to = self._canonicalize_effective_interval(
            effective_from, effective_to, now
        )
        record = OrganizationFacetRecord(
            facet_id=uuid4().hex,
            entity_id=entity_id,
            facet=facet,
            eligibility_status=eligibility_status,
            origin=origin,
            evidence_id=evidence_id,
            evidence_status=evidence.source_status if evidence else "none",
            effective_from=effective_from,
            effective_to=effective_to,
            system_from=now,
            system_to=None,
        )
        with self._engine.begin() as conn:
            self._serialize_entity_lifecycle_guard(conn, entity_id)
            self._require_attachment_allowed(conn, entity_id, effective_from, effective_to)
            conn.execute(
                text("""
                    INSERT INTO entity_registry_organization_facets (
                        facet_id, entity_id, facet, eligibility_status, origin, evidence_id,
                        evidence_status, effective_from, effective_to, system_from, system_to
                    ) VALUES (
                        :facet_id, :entity_id, :facet, :eligibility_status, :origin, :evidence_id,
                        :evidence_status, :effective_from, :effective_to, :system_from, :system_to
                    )
                """),
                record.__dict__,
            )
        return record

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
        rule = self._get_namespace_rule(namespace)
        if rule is None:
            raise EntityRegistryValidationError(f"unknown namespace: {namespace}")
        entity = self.get_entity(entity_id)
        if entity is None:
            raise EntityRegistryValidationError(f"unknown entity_id: {entity_id}")
        if entity.entity_kind != rule.eligible_kind:
            raise EntityRegistryValidationError(
                f"namespace {namespace} is ineligible for entity kind {entity.entity_kind}"
            )
        scope_authority, scope_country, scope_context = self._canonicalize_scope(
            rule, scope_authority, scope_country, scope_context
        )
        normalized_value = self._normalize(namespace, raw_value)
        evidence = self._get_evidence(evidence_id)
        if identifier_strength == "strong":
            if (
                evidence is None
                or not rule.strong_requires_official_evidence
                or evidence.source_class not in {"official_primary", "official_external"}
                or evidence.source_status != "available"
            ):
                raise EntityRegistryValidationError(
                    "strong identifier requires available official evidence"
                )
            if (
                evidence.qualified_namespace != namespace
                or evidence.source_authority not in rule.expected_evidence_authorities
            ):
                raise EntityRegistryValidationError(
                    "strong identifier requires qualifying official evidence"
                )
        elif evidence is None and evidence_id is not None:
            raise EntityRegistryValidationError(f"unknown evidence_id: {evidence_id}")

        now = _utc_now()
        effective_from, effective_to = self._canonicalize_effective_interval(
            effective_from, effective_to, now
        )
        if rule.required_organization_facet is not None:
            self._require_active_organization_facet(
                entity_id,
                rule.required_organization_facet,
                effective_from,
                effective_to,
            )
        claim_id = uuid4().hex
        claim = self._build_identifier_claim(
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
            origin=origin,
            evidence_id=evidence_id,
            evidence_status=evidence.source_status if evidence else "none",
            effective_from=effective_from,
            effective_to=effective_to,
            system_from=now,
        )
        claim, collision = self._write_identifier_claim_atomically(claim)
        if collision:
            code = "duplicate_strong_id" if identifier_strength == "strong" else "identifier_overlap"
            raise EntityRegistryConflictError(code, claim_id)
        return claim

    def find_identifier_claims(
        self,
        namespace: str,
        raw_value: str,
        scope_authority: str | None = None,
        scope_country: str | None = None,
        scope_context: str | None = None,
    ) -> list[IdentifierClaimRecord]:
        rule = self._get_namespace_rule(namespace)
        if rule is None:
            raise EntityRegistryValidationError(f"unknown namespace: {namespace}")
        scope_authority, scope_country, scope_context = self._canonicalize_scope(
            rule, scope_authority, scope_country, scope_context
        )
        normalized_value = self._normalize(namespace, raw_value)
        with self._engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT * FROM entity_registry_identifier_claims
                    WHERE namespace = :namespace
                      AND normalized_value = :normalized_value
                      AND ((scope_authority = :scope_authority)
                           OR (scope_authority IS NULL AND :scope_authority IS NULL))
                      AND ((scope_country = :scope_country)
                           OR (scope_country IS NULL AND :scope_country IS NULL))
                      AND ((scope_context = :scope_context)
                           OR (scope_context IS NULL AND :scope_context IS NULL))
                    ORDER BY claim_id
                """),
                {
                    "namespace": namespace,
                    "normalized_value": normalized_value,
                    "scope_authority": scope_authority,
                    "scope_country": scope_country,
                    "scope_context": scope_context,
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
        effective_from, effective_to = self._canonicalize_effective_interval(
            effective_from, effective_to, now
        )
        alias = AliasClaimRecord(
            alias_id=uuid4().hex,
            entity_id=entity_id,
            alias_type=alias_type,
            raw_value=raw_value,
            locale=locale,
            origin=origin,
            evidence_id=evidence_id,
            evidence_status=evidence.source_status if evidence else "none",
            effective_from=effective_from,
            effective_to=effective_to,
            system_from=now,
            system_to=None,
        )
        with self._engine.begin() as conn:
            self._serialize_entity_lifecycle_guard(conn, entity_id)
            self._require_attachment_allowed(conn, entity_id, effective_from, effective_to)
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
        self,
        namespace: str,
        raw_value: str,
        scope_authority: str | None = None,
        scope_country: str | None = None,
        scope_context: str | None = None,
    ) -> list[EntityRecord]:
        claims = self.find_identifier_claims(
            namespace, raw_value, scope_authority, scope_country, scope_context
        )
        entities = [self.get_entity(claim.entity_id) for claim in claims if claim.claim_status == "accepted"]
        return [entity for entity in entities if entity is not None]

    def _build_identifier_claim(self, **values) -> IdentifierClaimRecord:
        return IdentifierClaimRecord(claim_status="accepted", system_to=None, **values)

    def _write_identifier_claim_atomically(
        self, claim: IdentifierClaimRecord
    ) -> tuple[IdentifierClaimRecord, bool]:
        for attempt in range(3):
            try:
                with self._engine.begin() as conn:
                    collision = False
                    rule = self._get_namespace_rule(claim.namespace)
                    policy_collision = bool(rule and rule.overlap_requires_review)
                    self._serialize_entity_lifecycle_guard(conn, claim.entity_id)
                    self._require_attachment_allowed(
                        conn, claim.entity_id, claim.effective_from, claim.effective_to
                    )
                    if claim.identifier_strength == "strong" or policy_collision:
                        self._serialize_strong_identifier_guard(conn, claim)
                        collision = self._find_active_strong_collision(
                            conn, claim, policy_collision=policy_collision
                        )
                    persisted = replace(claim, claim_status="conflicted" if collision else "accepted")
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
                        persisted.__dict__,
                    )
                return persisted, collision
            except OperationalError as error:
                if not self._is_retryable_write_conflict(error) or attempt == 2:
                    raise
                time.sleep(0.05 * (attempt + 1))
        raise AssertionError("unreachable retry state")

    def _serialize_strong_identifier_guard(self, conn, claim: IdentifierClaimRecord) -> None:
        conn.execute(
            text("""
                INSERT INTO entity_registry_identifier_guards (guard_key, updated_at)
                VALUES (:guard_key, :updated_at)
                ON CONFLICT (guard_key) DO UPDATE SET updated_at = :updated_at
            """),
            {
                "guard_key": self._strong_identifier_guard_key(claim),
                "updated_at": claim.system_from,
            },
        )

    @staticmethod
    def _strong_identifier_guard_key(claim: IdentifierClaimRecord) -> str:
        return "\x1f".join(
            value or "<null>"
            for value in (
                claim.namespace,
                claim.normalized_value,
                claim.scope_authority,
                claim.scope_country,
                claim.scope_context,
            )
        )

    def _find_active_strong_collision(
        self,
        conn,
        claim: IdentifierClaimRecord,
        *,
        policy_collision: bool,
    ) -> bool:
        row = conn.execute(
            text("""
                SELECT 1 FROM entity_registry_identifier_claims
                WHERE namespace = :namespace
                  AND normalized_value = :normalized_value
                  AND (:policy_collision = 1 OR identifier_strength = :identifier_strength)
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
                "namespace": claim.namespace,
                "normalized_value": claim.normalized_value,
                "scope_authority": claim.scope_authority,
                "scope_country": claim.scope_country,
                "scope_context": claim.scope_context,
                "entity_id": claim.entity_id,
                "identifier_strength": claim.identifier_strength,
                "policy_collision": int(policy_collision),
                "effective_from": claim.effective_from,
                "effective_to": claim.effective_to,
            },
        ).first()
        return row is not None

    def _require_active_organization_facet(
        self, entity_id: str, facet: str, effective_from: str, effective_to: str | None
    ) -> None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT 1 FROM entity_registry_organization_facets
                    WHERE entity_id = :entity_id
                      AND facet = :facet
                      AND eligibility_status = 'active'
                      AND system_to IS NULL
                      AND (effective_to IS NULL OR effective_to > :effective_from)
                      AND (:effective_to IS NULL OR effective_from < :effective_to)
                    LIMIT 1
                """),
                {
                    "entity_id": entity_id,
                    "facet": facet,
                    "effective_from": effective_from,
                    "effective_to": effective_to,
                },
            ).first()
        if row is None:
            raise EntityRegistryValidationError(f"namespace requires active {facet} facet")

    def _serialize_entity_lifecycle_guard(self, conn, entity_id: str) -> None:
        result = conn.execute(
            text("UPDATE entity_registry_entities SET updated_at = updated_at WHERE entity_id = :entity_id"),
            {"entity_id": entity_id},
        )
        if result.rowcount not in (None, 1):
            raise EntityRegistryValidationError(f"unknown entity_id: {entity_id}")

    def _require_attachment_allowed(
        self, conn, entity_id: str, effective_from: str, effective_to: str | None
    ) -> None:
        row = conn.execute(
            text("""
                SELECT 1 FROM entity_registry_lifecycle_events
                WHERE entity_id = :entity_id
                  AND lifecycle_status IN ('retired', 'deprecated')
                  AND system_to IS NULL
                  AND (effective_to IS NULL OR effective_to > :effective_from)
                  AND (:effective_to IS NULL OR effective_from < :effective_to)
                LIMIT 1
            """),
            {
                "entity_id": entity_id,
                "effective_from": effective_from,
                "effective_to": effective_to,
            },
        ).first()
        if row is not None:
            raise EntityRegistryValidationError(
                "retired or deprecated entity rejects forward attachment without lineage authorization"
            )

    def _get_namespace_rule(self, namespace: str) -> _NamespaceRule | None:
        rule = _NAMESPACE_RULES.get(namespace)
        if rule is not None:
            return rule
        return self._get_dynamic_namespace_rule(namespace)

    @staticmethod
    def _is_retryable_write_conflict(error: OperationalError) -> bool:
        return "locked" in str(error).lower() or "serialization" in str(error).lower()

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
        if EntityRegistryRepository._get_namespace_rule_static(namespace) is None:
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
        rule: _NamespaceRule,
        authority: str | None,
        country: str | None,
        context: str | None,
    ) -> None:
        values = {"authority": authority, "country": country, "context": context}
        for required_scope in rule.required_scopes:
            if not values[required_scope] or not str(values[required_scope]).strip():
                raise EntityRegistryValidationError(f"namespace requires scope {required_scope}")
        for scope_name, value in values.items():
            if scope_name not in rule.required_scopes and value is not None:
                raise EntityRegistryValidationError(f"namespace does not use scope {scope_name}")
        if rule.expected_scope_authority and str(authority).strip().upper() != rule.expected_scope_authority:
            raise EntityRegistryValidationError(
                f"namespace requires authority {rule.expected_scope_authority}"
            )
        if rule.expected_scope_country and str(country).strip().upper() != rule.expected_scope_country:
            raise EntityRegistryValidationError(
                f"namespace requires country {rule.expected_scope_country}"
            )

    @classmethod
    def _canonicalize_scope(
        cls,
        rule: _NamespaceRule,
        authority: str | None,
        country: str | None,
        context: str | None,
    ) -> tuple[str | None, str | None, str | None]:
        canonical_scope = (
            cls._canonicalize_scope_value(authority, uppercase=True),
            cls._canonicalize_scope_value(country, uppercase=True),
            cls._canonicalize_scope_value(context, uppercase=False),
        )
        cls._validate_scope(rule, *canonical_scope)
        return canonical_scope

    @staticmethod
    def _canonicalize_scope_value(value: str | None, *, uppercase: bool) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise EntityRegistryValidationError("scope values must be strings")
        canonical = value.strip()
        return canonical.upper() if uppercase else canonical

    @staticmethod
    def _require_allowed(label: str, value: str, allowed: tuple[str, ...]) -> None:
        if value not in allowed:
            raise EntityRegistryValidationError(f"invalid {label}: {value}")

    @staticmethod
    def _get_namespace_rule_static(namespace: str) -> _NamespaceRule | None:
        rule = _NAMESPACE_RULES.get(namespace)
        if rule is not None:
            return rule
        return EntityRegistryRepository._get_dynamic_namespace_rule(namespace)

    @staticmethod
    def _get_dynamic_namespace_rule(namespace: str) -> _NamespaceRule | None:
        match = _DYNAMIC_NAMESPACE_PATTERN.fullmatch(namespace)
        if match is None:
            return None
        authority, value_class = match.groups()
        authority = authority.upper()
        if value_class == "regulated_agent_code":
            return _NamespaceRule(
                "trim-exact/v1", "organization", ("authority", "context"), "regulated_agent", False,
                expected_scope_authority=authority, expected_evidence_authorities=(authority,),
                overlap_requires_review=True,
            )
        return _NamespaceRule(
            "trim-exact/v1", "concession", ("authority", "context"), None, False,
            expected_scope_authority=authority, expected_evidence_authorities=(authority,),
            overlap_requires_review=True,
        )

    @staticmethod
    def _canonicalize_utc_instant(value: str) -> str:
        if not isinstance(value, str) or "T" not in value:
            raise EntityRegistryValidationError("UTC instant is required")
        try:
            instant = datetime.fromisoformat(value)
        except ValueError as error:
            raise EntityRegistryValidationError("UTC instant is required") from error
        if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
            raise EntityRegistryValidationError("UTC instant is required")
        return instant.astimezone(timezone.utc).isoformat()

    @classmethod
    def _canonicalize_effective_interval(
        cls, effective_from: str | None, effective_to: str | None, now: str
    ) -> tuple[str, str | None]:
        canonical_from = cls._canonicalize_utc_instant(effective_from or now)
        canonical_to = cls._canonicalize_utc_instant(effective_to) if effective_to is not None else None
        if canonical_to is not None and canonical_from >= canonical_to:
            raise EntityRegistryValidationError("invalid effective interval")
        return canonical_from, canonical_to


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
