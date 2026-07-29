"""Bitemporal assertion, relationship, and lineage repository.

This module is an explicit fresh/sandbox registry surface.  It neither creates
the schema nor consults legacy tables or remote sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from sqlalchemy import Engine, text

from src.companies.entity_registry_schema import (
    ASSERTION_STATES,
    LINEAGE_PREDICATES,
    OPERATIONAL_ROLES,
    ORIGINS,
    RELATIONSHIP_DIMENSIONS,
    validate_entity_registry_schema,
)


class EntityRelationshipError(ValueError):
    """Base typed failure for relationship commands."""


class EntityRelationshipValidationError(EntityRelationshipError):
    """A relationship command violates the registry contract."""


@dataclass(frozen=True)
class AssertionRecord:
    assertion_id: str
    subject_entity_id: str
    domain: str
    attribute: str
    value: object
    assertion_state: str
    review_status: str
    origin: str
    actor_id: str
    evidence_id: str | None
    evidence_status: str
    supersedes_assertion_id: str | None
    effective_from: str
    effective_to: str | None
    system_from: str
    system_to: str | None


@dataclass(frozen=True)
class RelationshipRecord:
    relationship_id: str
    subject_entity_id: str
    object_entity_id: str
    dimension: str
    operational_role: str | None
    payload: object
    assertion_id: str
    relationship_status: str
    effective_from: str
    effective_to: str | None
    system_from: str
    system_to: str | None


@dataclass(frozen=True)
class LineageRecord:
    lineage_id: str
    predecessor_entity_id: str
    successor_entity_id: str
    predicate: str
    assertion_id: str
    effective_from: str
    effective_to: str | None
    system_from: str
    system_to: str | None


class EntityRelationshipRepository:
    """Persist auditable bitemporal claims without implicit latest reads."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        validate_entity_registry_schema(engine)

    def record_assertion(
        self,
        *,
        subject_entity_id: str,
        domain: str,
        attribute: str,
        value: object,
        origin: str,
        actor_id: str,
        evidence_id: str | None,
        effective_from: str,
        effective_to: str | None = None,
        assertion_state: str = "accepted",
        review_status: str = "accepted",
        supersedes_assertion_id: str | None = None,
    ) -> AssertionRecord:
        self._require_nonempty("domain", domain)
        self._require_nonempty("attribute", attribute)
        self._require_nonempty("actor_id", actor_id)
        self._require_allowed("origin", origin, ORIGINS)
        self._require_allowed("assertion state", assertion_state, ASSERTION_STATES)
        effective_from, effective_to = self._interval(effective_from, effective_to)
        value_json = self._serialize_json(value, "assertion value")
        now = _utc_now()
        with self._engine.begin() as conn:
            self._require_entity(conn, subject_entity_id)
            self._require_attachment_allowed(conn, subject_entity_id, effective_from, effective_to)
            evidence_status = self._evidence_status(conn, evidence_id)
            if supersedes_assertion_id is not None:
                prior = self._assertion_row(conn, supersedes_assertion_id)
                if prior is None:
                    raise EntityRelationshipValidationError("unknown superseded assertion")
                if (prior["subject_entity_id"], prior["domain"], prior["attribute"]) != (
                    subject_entity_id, domain, attribute,
                ):
                    raise EntityRelationshipValidationError("correction must preserve assertion subject and attribute")
                now = _after(prior["system_from"], now)
                if prior["system_to"] is not None:
                    raise EntityRelationshipValidationError("assertion is already superseded")
                conn.execute(
                    text("UPDATE entity_registry_assertions SET system_to = :system_to WHERE assertion_id = :assertion_id"),
                    {"system_to": now, "assertion_id": supersedes_assertion_id},
                )
            record = AssertionRecord(
                assertion_id=uuid4().hex,
                subject_entity_id=subject_entity_id,
                domain=domain.strip(),
                attribute=attribute.strip(),
                value=value,
                assertion_state=assertion_state,
                review_status=review_status.strip() or "accepted",
                origin=origin,
                actor_id=actor_id.strip(),
                evidence_id=evidence_id,
                evidence_status=evidence_status,
                supersedes_assertion_id=supersedes_assertion_id,
                effective_from=effective_from,
                effective_to=effective_to,
                system_from=now,
                system_to=None,
            )
            values = {**record.__dict__, "value_json": value_json}
            values.pop("value")
            conn.execute(text("""
                INSERT INTO entity_registry_assertions (
                    assertion_id, subject_entity_id, domain, attribute, value_json, assertion_state,
                    review_status, origin, actor_id, evidence_id, evidence_status, supersedes_assertion_id,
                    effective_from, effective_to, system_from, system_to
                ) VALUES (
                    :assertion_id, :subject_entity_id, :domain, :attribute, :value_json, :assertion_state,
                    :review_status, :origin, :actor_id, :evidence_id, :evidence_status, :supersedes_assertion_id,
                    :effective_from, :effective_to, :system_from, :system_to
                )
            """), values)
        return record

    def find_assertions(
        self,
        entity_id: str,
        *,
        domain: str,
        attribute: str,
        effective_as_of: str,
        system_as_of: str | None = None,
    ) -> list[AssertionRecord]:
        effective_as_of = self._as_of("effective_as_of", effective_as_of)
        system_as_of = self._as_of("system_as_of", system_as_of or _utc_now())
        with self._engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT * FROM entity_registry_assertions
                WHERE subject_entity_id = :entity_id AND domain = :domain AND attribute = :attribute
                  AND effective_from <= :effective_as_of
                  AND (effective_to IS NULL OR effective_to > :effective_as_of)
                  AND system_from <= :system_as_of
                  AND (system_to IS NULL OR system_to > :system_as_of)
                ORDER BY system_from, assertion_id
            """), {
                "entity_id": entity_id, "domain": domain, "attribute": attribute,
                "effective_as_of": effective_as_of, "system_as_of": system_as_of,
            }).mappings().all()
        return [self._assertion_record(row) for row in rows]

    def record_relationship(
        self,
        *,
        subject_entity_id: str,
        object_entity_id: str,
        dimension: str,
        payload: object,
        assertion_id: str,
        effective_from: str,
        effective_to: str | None = None,
        operational_role: str | None = None,
        relationship_status: str = "accepted",
    ) -> RelationshipRecord:
        self._require_allowed("relationship dimension", dimension, RELATIONSHIP_DIMENSIONS)
        if dimension == "operational_role":
            if operational_role is None:
                raise EntityRelationshipValidationError("operational role is required")
            self._require_allowed("operational role", operational_role, OPERATIONAL_ROLES)
        elif operational_role is not None:
            raise EntityRelationshipValidationError("operational role is only valid for operational_role")
        effective_from, effective_to = self._interval(effective_from, effective_to)
        payload_json = self._serialize_json(payload, "relationship payload")
        self._require_interest_metadata(payload)
        record = RelationshipRecord(
            relationship_id=uuid4().hex, subject_entity_id=subject_entity_id,
            object_entity_id=object_entity_id, dimension=dimension, operational_role=operational_role,
            payload=payload, assertion_id=assertion_id, relationship_status=relationship_status,
            effective_from=effective_from, effective_to=effective_to, system_from=_utc_now(), system_to=None,
        )
        with self._engine.begin() as conn:
            self._require_entity(conn, subject_entity_id)
            self._require_entity(conn, object_entity_id)
            self._require_attachment_allowed(conn, subject_entity_id, effective_from, effective_to)
            self._require_attachment_allowed(conn, object_entity_id, effective_from, effective_to)
            assertion = self._assertion_row(conn, assertion_id)
            if assertion is None or assertion["subject_entity_id"] != subject_entity_id:
                raise EntityRelationshipValidationError("relationship assertion must belong to its subject entity")
            if dimension == "control":
                self._reject_exclusive_overlap(conn, subject_entity_id, effective_from, effective_to)
                self._reject_relationship_cycle(conn, subject_entity_id, object_entity_id, "control")
            values = {**record.__dict__, "payload_json": payload_json}
            values.pop("payload")
            conn.execute(text("""
                INSERT INTO entity_registry_relationships (
                    relationship_id, subject_entity_id, object_entity_id, dimension, operational_role,
                    payload_json, assertion_id, relationship_status, effective_from, effective_to, system_from, system_to
                ) VALUES (
                    :relationship_id, :subject_entity_id, :object_entity_id, :dimension, :operational_role,
                    :payload_json, :assertion_id, :relationship_status, :effective_from, :effective_to, :system_from, :system_to
                )
            """), values)
        return record

    def find_relationships(
        self,
        entity_id: str,
        *,
        effective_as_of: str,
        system_as_of: str | None = None,
        dimension: str | None = None,
    ) -> list[RelationshipRecord]:
        effective_as_of = self._as_of("effective_as_of", effective_as_of)
        system_as_of = self._as_of("system_as_of", system_as_of or _utc_now())
        with self._engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT * FROM entity_registry_relationships
                WHERE (subject_entity_id = :entity_id OR object_entity_id = :entity_id)
                  AND (:dimension IS NULL OR dimension = :dimension)
                  AND effective_from <= :effective_as_of AND (effective_to IS NULL OR effective_to > :effective_as_of)
                  AND system_from <= :system_as_of AND (system_to IS NULL OR system_to > :system_as_of)
                ORDER BY dimension, relationship_id
            """), {
                "entity_id": entity_id, "dimension": dimension, "effective_as_of": effective_as_of,
                "system_as_of": system_as_of,
            }).mappings().all()
        return [self._relationship_record(row) for row in rows]

    def record_lineage(
        self,
        *,
        predecessor_entity_id: str,
        successor_entity_id: str,
        predicate: str,
        assertion_id: str,
        effective_from: str,
        effective_to: str | None = None,
    ) -> LineageRecord:
        self._require_allowed("lineage predicate", predicate, LINEAGE_PREDICATES)
        if predicate == "legal_continuation":
            if predecessor_entity_id != successor_entity_id:
                raise EntityRelationshipValidationError("legal_continuation requires the same entity")
        elif predecessor_entity_id == successor_entity_id:
            raise EntityRelationshipValidationError("lineage requires distinct entities")
        effective_from, effective_to = self._interval(effective_from, effective_to)
        record = LineageRecord(
            lineage_id=uuid4().hex, predecessor_entity_id=predecessor_entity_id,
            successor_entity_id=successor_entity_id, predicate=predicate, assertion_id=assertion_id,
            effective_from=effective_from, effective_to=effective_to, system_from=_utc_now(), system_to=None,
        )
        with self._engine.begin() as conn:
            self._require_entity(conn, predecessor_entity_id)
            self._require_entity(conn, successor_entity_id)
            self._require_attachment_allowed(conn, predecessor_entity_id, effective_from, effective_to)
            self._require_attachment_allowed(conn, successor_entity_id, effective_from, effective_to)
            assertion = self._assertion_row(conn, assertion_id)
            if assertion is None or assertion["subject_entity_id"] != predecessor_entity_id:
                raise EntityRelationshipValidationError("lineage assertion must belong to predecessor entity")
            if predicate != "legal_continuation":
                self._reject_lineage_cycle(conn, predecessor_entity_id, successor_entity_id)
            conn.execute(text("""
                INSERT INTO entity_registry_lineage (
                    lineage_id, predecessor_entity_id, successor_entity_id, predicate, assertion_id,
                    effective_from, effective_to, system_from, system_to
                ) VALUES (
                    :lineage_id, :predecessor_entity_id, :successor_entity_id, :predicate, :assertion_id,
                    :effective_from, :effective_to, :system_from, :system_to
                )
            """), record.__dict__)
        return record

    def find_lineage(
        self, entity_id: str, *, effective_as_of: str, system_as_of: str | None = None
    ) -> list[LineageRecord]:
        effective_as_of = self._as_of("effective_as_of", effective_as_of)
        system_as_of = self._as_of("system_as_of", system_as_of or _utc_now())
        with self._engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT * FROM entity_registry_lineage
                WHERE (predecessor_entity_id = :entity_id OR successor_entity_id = :entity_id)
                  AND effective_from <= :effective_as_of AND (effective_to IS NULL OR effective_to > :effective_as_of)
                  AND system_from <= :system_as_of AND (system_to IS NULL OR system_to > :system_as_of)
                ORDER BY lineage_id
            """), {
                "entity_id": entity_id, "effective_as_of": effective_as_of, "system_as_of": system_as_of,
            }).mappings().all()
        return [LineageRecord(**dict(row)) for row in rows]

    @staticmethod
    def _assertion_record(row) -> AssertionRecord:
        values = dict(row)
        values["value"] = json.loads(values.pop("value_json"))
        return AssertionRecord(**values)

    @staticmethod
    def _relationship_record(row) -> RelationshipRecord:
        values = dict(row)
        values["payload"] = json.loads(values.pop("payload_json"))
        return RelationshipRecord(**values)

    @staticmethod
    def _require_nonempty(label: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise EntityRelationshipValidationError(f"{label} is required")

    @staticmethod
    def _require_allowed(label: str, value: str, allowed: tuple[str, ...]) -> None:
        if value not in allowed:
            raise EntityRelationshipValidationError(f"invalid {label}: {value}")

    @staticmethod
    def _serialize_json(value: object, label: str) -> str:
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise EntityRelationshipValidationError(f"{label} must be JSON serializable") from error

    @classmethod
    def _as_of(cls, label: str, value: str | None) -> str:
        if value is None:
            raise EntityRelationshipValidationError(f"{label} is required")
        return cls._instant(value)

    @classmethod
    def _interval(cls, effective_from: str, effective_to: str | None) -> tuple[str, str | None]:
        start = cls._instant(effective_from)
        end = cls._instant(effective_to) if effective_to is not None else None
        if end is not None and start >= end:
            raise EntityRelationshipValidationError("invalid temporal interval")
        return start, end

    @staticmethod
    def _instant(value: str) -> str:
        try:
            instant = datetime.fromisoformat(value)
        except (TypeError, ValueError) as error:
            raise EntityRelationshipValidationError("UTC instant is required") from error
        if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
            raise EntityRelationshipValidationError("UTC instant is required")
        return instant.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _require_interest_metadata(payload: object) -> None:
        if not isinstance(payload, dict) or not any(key in payload for key in ("interest", "percentage", "value")):
            return
        required = {"unit", "basis", "precision"}
        if not required.issubset(payload):
            raise EntityRelationshipValidationError("numeric interest requires unit, basis, and precision")

    @staticmethod
    def _require_entity(conn, entity_id: str) -> None:
        if conn.execute(text("SELECT 1 FROM entity_registry_entities WHERE entity_id = :entity_id"), {"entity_id": entity_id}).first() is None:
            raise EntityRelationshipValidationError(f"unknown entity_id: {entity_id}")

    @staticmethod
    def _evidence_status(conn, evidence_id: str | None) -> str:
        if evidence_id is None:
            return "none"
        status = conn.execute(text("SELECT source_status FROM entity_registry_evidence WHERE evidence_id = :evidence_id"), {"evidence_id": evidence_id}).scalar_one_or_none()
        if status is None:
            raise EntityRelationshipValidationError("unknown evidence_id")
        return status

    @staticmethod
    def _assertion_row(conn, assertion_id: str):
        return conn.execute(text("SELECT * FROM entity_registry_assertions WHERE assertion_id = :assertion_id"), {"assertion_id": assertion_id}).mappings().one_or_none()

    @staticmethod
    def _require_attachment_allowed(conn, entity_id: str, effective_from: str, effective_to: str | None) -> None:
        retired = conn.execute(text("""
            SELECT 1 FROM entity_registry_lifecycle_events
            WHERE entity_id = :entity_id AND lifecycle_status IN ('retired', 'deprecated') AND system_to IS NULL
              AND (effective_to IS NULL OR effective_to > :effective_from)
              AND (:effective_to IS NULL OR effective_from < :effective_to)
            LIMIT 1
        """), {"entity_id": entity_id, "effective_from": effective_from, "effective_to": effective_to}).first()
        if retired is not None:
            raise EntityRelationshipValidationError("retired or deprecated entity rejects forward attachment")

    @staticmethod
    def _reject_exclusive_overlap(conn, subject_entity_id: str, effective_from: str, effective_to: str | None) -> None:
        overlap = conn.execute(text("""
            SELECT 1 FROM entity_registry_relationships
            WHERE subject_entity_id = :subject_entity_id AND dimension = 'control' AND system_to IS NULL
              AND (effective_to IS NULL OR effective_to > :effective_from)
              AND (:effective_to IS NULL OR effective_from < :effective_to)
            LIMIT 1
        """), {
            "subject_entity_id": subject_entity_id, "effective_from": effective_from, "effective_to": effective_to,
        }).first()
        if overlap is not None:
            raise EntityRelationshipValidationError("exclusive relationship overlap")

    @staticmethod
    def _reject_relationship_cycle(conn, subject_entity_id: str, object_entity_id: str, dimension: str) -> None:
        if subject_entity_id == object_entity_id:
            raise EntityRelationshipValidationError("cycle detected")
        cycle = conn.execute(text("""
            WITH RECURSIVE reachable(entity_id) AS (
                SELECT object_entity_id FROM entity_registry_relationships
                WHERE subject_entity_id = :object_entity_id AND dimension = :dimension AND system_to IS NULL
                UNION
                SELECT relationship.object_entity_id FROM entity_registry_relationships relationship
                JOIN reachable ON relationship.subject_entity_id = reachable.entity_id
                WHERE relationship.dimension = :dimension AND relationship.system_to IS NULL
            ) SELECT 1 FROM reachable WHERE entity_id = :subject_entity_id LIMIT 1
        """), {
            "subject_entity_id": subject_entity_id, "object_entity_id": object_entity_id, "dimension": dimension,
        }).first()
        if cycle is not None:
            raise EntityRelationshipValidationError("cycle detected")

    @staticmethod
    def _reject_lineage_cycle(conn, predecessor_entity_id: str, successor_entity_id: str) -> None:
        cycle = conn.execute(text("""
            WITH RECURSIVE reachable(entity_id) AS (
                SELECT successor_entity_id FROM entity_registry_lineage
                WHERE predecessor_entity_id = :successor_entity_id AND system_to IS NULL
                  AND predicate <> 'legal_continuation'
                UNION
                SELECT lineage.successor_entity_id FROM entity_registry_lineage lineage
                JOIN reachable ON lineage.predecessor_entity_id = reachable.entity_id
                WHERE lineage.system_to IS NULL AND lineage.predicate <> 'legal_continuation'
            ) SELECT 1 FROM reachable WHERE entity_id = :predecessor_entity_id LIMIT 1
        """), {
            "predecessor_entity_id": predecessor_entity_id, "successor_entity_id": successor_entity_id,
        }).first()
        if cycle is not None:
            raise EntityRelationshipValidationError("cycle detected")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _after(previous: str, candidate: str) -> str:
    prior = datetime.fromisoformat(previous)
    current = datetime.fromisoformat(candidate)
    if current <= prior:
        return (prior + timedelta(microseconds=1)).isoformat()
    return candidate
