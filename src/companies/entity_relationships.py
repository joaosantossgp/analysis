"""Bitemporal assertion, relationship, and lineage repository.

This module is an explicit fresh/sandbox registry surface.  It neither creates
the schema nor consults legacy tables or remote sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import json
from uuid import uuid4

from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from src.companies.entity_registry_schema import (
    ASSERTION_STATES,
    LINEAGE_STATUSES,
    LINEAGE_PREDICATES,
    OPERATIONAL_ROLES,
    ORIGINS,
    RELATIONSHIP_DIMENSIONS,
    RELATIONSHIP_STATUSES,
    REVIEW_STATUSES,
    validate_entity_registry_schema,
)


class EntityRelationshipError(ValueError):
    """Base typed failure for relationship commands."""


class EntityRelationshipValidationError(EntityRelationshipError):
    """A relationship command violates the registry contract."""


class EntityRelationshipConcurrencyError(EntityRelationshipError):
    """A serialized relationship command can be safely retried by its caller."""


class EntityRelationshipTraversalBlockedError(EntityRelationshipError):
    """A bounded graph validation could not complete within its safety limit."""


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
    reason: str | None
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
    lineage_status: str
    effective_from: str
    effective_to: str | None
    system_from: str
    system_to: str | None


class EntityRelationshipRepository:
    """Persist auditable bitemporal claims without implicit latest reads."""

    MAX_TRAVERSAL_DEPTH = 16
    MAX_TRAVERSAL_NODES = 128
    MAX_TRAVERSAL_EDGES = 256

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        validate_entity_registry_schema(engine)

    @contextmanager
    def _write_connection(self, *lock_keys: str):
        """Serialize graph writes without relying on a check-then-insert race."""
        with self._engine.connect() as conn:
            if self._engine.dialect.name == "sqlite":
                try:
                    conn.exec_driver_sql("BEGIN IMMEDIATE")
                    yield conn
                except OperationalError as error:
                    conn.rollback()
                    self._raise_retryable_concurrency_error(error)
                except Exception:
                    conn.rollback()
                    raise
                else:
                    conn.commit()
                return
            try:
                with conn.begin():
                    if self._engine.dialect.name == "postgresql":
                        for key in sorted(set(lock_keys)):
                            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"entity-registry:{key}"})
                    yield conn
            except OperationalError as error:
                self._raise_retryable_concurrency_error(error)

    @staticmethod
    def _raise_retryable_concurrency_error(error: OperationalError) -> None:
        message = str(error).lower()
        if "database is locked" in message or "serialize" in message or "deadlock" in message:
            raise EntityRelationshipConcurrencyError("concurrent relationship write conflict; retry the command") from error
        raise error

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
        reason: str | None = None,
        supersedes_assertion_id: str | None = None,
    ) -> AssertionRecord:
        self._require_nonempty("domain", domain)
        self._require_nonempty("attribute", attribute)
        self._require_nonempty("actor_id", actor_id)
        self._require_allowed("origin", origin, ORIGINS)
        self._require_allowed("assertion state", assertion_state, ASSERTION_STATES)
        self._require_allowed("review status", review_status, REVIEW_STATUSES)
        effective_from, effective_to = self._interval(effective_from, effective_to)
        value_json = self._serialize_json(value, "assertion value")
        now = _utc_now()
        with self._write_connection(subject_entity_id) as conn:
            self._require_entity(conn, subject_entity_id)
            self._require_attachment_allowed(conn, subject_entity_id, effective_from, effective_to)
            evidence_status = self._evidence_status(conn, evidence_id)
            if evidence_id is None and origin != "user":
                raise EntityRelationshipValidationError("evidence-free assertion requires origin=user")
            if evidence_id is None and (not isinstance(reason, str) or not reason.strip()):
                raise EntityRelationshipValidationError("evidence-free assertion requires reason")
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
                reason=reason.strip() if isinstance(reason, str) and reason.strip() else None,
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
                    review_status, origin, actor_id, evidence_id, evidence_status, reason, supersedes_assertion_id,
                    effective_from, effective_to, system_from, system_to
                ) VALUES (
                    :assertion_id, :subject_entity_id, :domain, :attribute, :value_json, :assertion_state,
                    :review_status, :origin, :actor_id, :evidence_id, :evidence_status, :reason, :supersedes_assertion_id,
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
        self._require_allowed("relationship status", relationship_status, RELATIONSHIP_STATUSES)
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
        with self._write_connection(subject_entity_id, object_entity_id) as conn:
            self._require_entity(conn, subject_entity_id)
            self._require_entity(conn, object_entity_id)
            self._require_attachment_allowed(conn, subject_entity_id, effective_from, effective_to)
            self._require_attachment_allowed(conn, object_entity_id, effective_from, effective_to)
            assertion = self._assertion_row(conn, assertion_id)
            if assertion is None or assertion["subject_entity_id"] != subject_entity_id or assertion["assertion_state"] != "accepted" or assertion["system_to"] is not None:
                raise EntityRelationshipValidationError("relationship assertion must belong to its subject entity")
            if not self._covers_interval(assertion["effective_from"], assertion["effective_to"], effective_from, effective_to):
                raise EntityRelationshipValidationError("assertion must cover edge interval")
            if dimension == "control" and relationship_status == "accepted":
                self._reject_exclusive_overlap(conn, subject_entity_id, effective_from, effective_to)
                self._reject_relationship_cycle(conn, subject_entity_id, object_entity_id, "control", effective_from, effective_to)
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
                SELECT relationship.* FROM entity_registry_relationships relationship
                JOIN entity_registry_assertions assertion ON assertion.assertion_id = relationship.assertion_id
                WHERE (relationship.subject_entity_id = :entity_id OR relationship.object_entity_id = :entity_id)
                  AND (:dimension IS NULL OR relationship.dimension = :dimension)
                  AND relationship.relationship_status = 'accepted' AND assertion.assertion_state = 'accepted'
                  AND relationship.effective_from <= :effective_as_of AND (relationship.effective_to IS NULL OR relationship.effective_to > :effective_as_of)
                  AND relationship.system_from <= :system_as_of AND (relationship.system_to IS NULL OR relationship.system_to > :system_as_of)
                  AND assertion.system_from <= :system_as_of AND (assertion.system_to IS NULL OR assertion.system_to > :system_as_of)
                  AND assertion.effective_from <= :effective_as_of AND (assertion.effective_to IS NULL OR assertion.effective_to > :effective_as_of)
                ORDER BY relationship.dimension, relationship.relationship_id
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
        lineage_status: str = "accepted",
    ) -> LineageRecord:
        self._require_allowed("lineage predicate", predicate, LINEAGE_PREDICATES)
        self._require_allowed("lineage status", lineage_status, LINEAGE_STATUSES)
        if predicate == "legal_continuation":
            if predecessor_entity_id != successor_entity_id:
                raise EntityRelationshipValidationError("legal_continuation requires the same entity")
        elif predecessor_entity_id == successor_entity_id:
            raise EntityRelationshipValidationError("lineage requires distinct entities")
        effective_from, effective_to = self._interval(effective_from, effective_to)
        record = LineageRecord(
            lineage_id=uuid4().hex, predecessor_entity_id=predecessor_entity_id,
            successor_entity_id=successor_entity_id, predicate=predicate, assertion_id=assertion_id,
            effective_from=effective_from, effective_to=effective_to, lineage_status=lineage_status, system_from=_utc_now(), system_to=None,
        )
        with self._write_connection(predecessor_entity_id, successor_entity_id) as conn:
            self._require_entity(conn, predecessor_entity_id)
            self._require_entity(conn, successor_entity_id)
            self._require_attachment_allowed(conn, predecessor_entity_id, effective_from, effective_to)
            self._require_attachment_allowed(conn, successor_entity_id, effective_from, effective_to)
            assertion = self._assertion_row(conn, assertion_id)
            if assertion is None or assertion["subject_entity_id"] != predecessor_entity_id or assertion["assertion_state"] != "accepted" or assertion["system_to"] is not None:
                raise EntityRelationshipValidationError("lineage assertion must belong to predecessor entity")
            if not self._covers_interval(assertion["effective_from"], assertion["effective_to"], effective_from, effective_to):
                raise EntityRelationshipValidationError("assertion must cover edge interval")
            if predicate != "legal_continuation" and lineage_status == "accepted":
                self._reject_lineage_cycle(conn, predecessor_entity_id, successor_entity_id, effective_from, effective_to)
            conn.execute(text("""
                INSERT INTO entity_registry_lineage (
                    lineage_id, predecessor_entity_id, successor_entity_id, predicate, assertion_id, lineage_status,
                    effective_from, effective_to, system_from, system_to
                ) VALUES (
                    :lineage_id, :predecessor_entity_id, :successor_entity_id, :predicate, :assertion_id, :lineage_status,
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
                SELECT lineage.* FROM entity_registry_lineage lineage
                JOIN entity_registry_assertions assertion ON assertion.assertion_id = lineage.assertion_id
                WHERE (lineage.predecessor_entity_id = :entity_id OR lineage.successor_entity_id = :entity_id)
                  AND lineage.lineage_status = 'accepted' AND assertion.assertion_state = 'accepted'
                  AND lineage.effective_from <= :effective_as_of AND (lineage.effective_to IS NULL OR lineage.effective_to > :effective_as_of)
                  AND lineage.system_from <= :system_as_of AND (lineage.system_to IS NULL OR lineage.system_to > :system_as_of)
                  AND assertion.system_from <= :system_as_of AND (assertion.system_to IS NULL OR assertion.system_to > :system_as_of)
                  AND assertion.effective_from <= :effective_as_of AND (assertion.effective_to IS NULL OR assertion.effective_to > :effective_as_of)
                ORDER BY lineage.lineage_id
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
            SELECT 1 FROM entity_registry_relationships relationship
            JOIN entity_registry_assertions assertion ON assertion.assertion_id = relationship.assertion_id
            WHERE relationship.subject_entity_id = :subject_entity_id AND relationship.dimension = 'control'
              AND relationship.relationship_status = 'accepted' AND relationship.system_to IS NULL
              AND assertion.assertion_state = 'accepted' AND assertion.system_to IS NULL
              AND (relationship.effective_to IS NULL OR relationship.effective_to > :effective_from)
              AND (:effective_to IS NULL OR relationship.effective_from < :effective_to)
            LIMIT 1
        """), {
            "subject_entity_id": subject_entity_id, "effective_from": effective_from, "effective_to": effective_to,
        }).first()
        if overlap is not None:
            raise EntityRelationshipValidationError("exclusive relationship overlap")

    @staticmethod
    def _reject_relationship_cycle(conn, subject_entity_id: str, object_entity_id: str, dimension: str, effective_from: str, effective_to: str | None) -> None:
        if subject_entity_id == object_entity_id:
            raise EntityRelationshipValidationError("cycle detected")
        if EntityRelationshipRepository._has_relationship_path(
            conn, object_entity_id, subject_entity_id, dimension, effective_from, effective_to,
        ):
            raise EntityRelationshipValidationError("cycle detected")

    @staticmethod
    def _reject_lineage_cycle(conn, predecessor_entity_id: str, successor_entity_id: str, effective_from: str, effective_to: str | None) -> None:
        if EntityRelationshipRepository._has_lineage_path(
            conn, successor_entity_id, predecessor_entity_id, effective_from, effective_to,
        ):
            raise EntityRelationshipValidationError("cycle detected")

    @classmethod
    def _has_relationship_path(cls, conn, start, target, dimension, effective_from, effective_to) -> bool:
        stack = [(start, effective_from, effective_to, {start})]
        traversed_nodes = {start}
        traversed_edges = 0
        while stack:
            entity_id, window_start, window_to, visited = stack.pop()
            if len(visited) > cls.MAX_TRAVERSAL_DEPTH:
                raise EntityRelationshipTraversalBlockedError("relationship traversal limit exceeded")
            remaining_edges = cls.MAX_TRAVERSAL_EDGES - traversed_edges
            if remaining_edges < 0:
                raise EntityRelationshipTraversalBlockedError("relationship traversal limit exceeded")
            rows = conn.execute(text("""
                SELECT relationship.object_entity_id, relationship.effective_from, relationship.effective_to
                FROM entity_registry_relationships relationship
                JOIN entity_registry_assertions assertion ON assertion.assertion_id = relationship.assertion_id
                WHERE relationship.subject_entity_id = :entity_id AND relationship.dimension = :dimension
                  AND relationship.relationship_status = 'accepted' AND relationship.system_to IS NULL
                  AND assertion.assertion_state = 'accepted' AND assertion.system_to IS NULL
                  AND (relationship.effective_to IS NULL OR relationship.effective_to > :window_start)
                  AND (:window_to IS NULL OR relationship.effective_from < :window_to)
                ORDER BY relationship.relationship_id
                LIMIT :fetch_limit
            """), {"entity_id": entity_id, "dimension": dimension,
                    "window_start": window_start, "window_to": window_to,
                    "fetch_limit": remaining_edges + 1}).mappings().all()
            if len(rows) > remaining_edges:
                raise EntityRelationshipTraversalBlockedError("relationship traversal limit exceeded")
            traversed_edges += len(rows)
            for row in rows:
                overlap = cls._intersect_intervals(
                    window_start, window_to, row["effective_from"], row["effective_to"],
                )
                if overlap is None:
                    continue
                next_entity = row["object_entity_id"]
                if next_entity == target:
                    return True
                if next_entity not in visited:
                    traversed_nodes.add(next_entity)
                    if len(traversed_nodes) > cls.MAX_TRAVERSAL_NODES:
                        raise EntityRelationshipTraversalBlockedError("relationship traversal limit exceeded")
                    stack.append((next_entity, overlap[0], overlap[1], visited | {next_entity}))
        return False

    @classmethod
    def _has_lineage_path(cls, conn, start, target, effective_from, effective_to) -> bool:
        stack = [(start, effective_from, effective_to, {start})]
        traversed_nodes = {start}
        traversed_edges = 0
        while stack:
            entity_id, window_start, window_to, visited = stack.pop()
            if len(visited) > cls.MAX_TRAVERSAL_DEPTH:
                raise EntityRelationshipTraversalBlockedError("lineage traversal limit exceeded")
            remaining_edges = cls.MAX_TRAVERSAL_EDGES - traversed_edges
            if remaining_edges < 0:
                raise EntityRelationshipTraversalBlockedError("lineage traversal limit exceeded")
            rows = conn.execute(text("""
                SELECT lineage.successor_entity_id AS object_entity_id, lineage.effective_from, lineage.effective_to
                FROM entity_registry_lineage lineage
                JOIN entity_registry_assertions assertion ON assertion.assertion_id = lineage.assertion_id
                WHERE lineage.predecessor_entity_id = :entity_id AND lineage.predicate <> 'legal_continuation'
                  AND lineage.lineage_status = 'accepted' AND lineage.system_to IS NULL
                  AND assertion.assertion_state = 'accepted' AND assertion.system_to IS NULL
                  AND (lineage.effective_to IS NULL OR lineage.effective_to > :window_start)
                  AND (:window_to IS NULL OR lineage.effective_from < :window_to)
                ORDER BY lineage.lineage_id
                LIMIT :fetch_limit
            """), {"entity_id": entity_id, "window_start": window_start,
                    "window_to": window_to, "fetch_limit": remaining_edges + 1}).mappings().all()
            if len(rows) > remaining_edges:
                raise EntityRelationshipTraversalBlockedError("lineage traversal limit exceeded")
            traversed_edges += len(rows)
            for row in rows:
                overlap = cls._intersect_intervals(window_start, window_to, row["effective_from"], row["effective_to"])
                if overlap is None:
                    continue
                next_entity = row["object_entity_id"]
                if next_entity == target:
                    return True
                if next_entity not in visited:
                    traversed_nodes.add(next_entity)
                    if len(traversed_nodes) > cls.MAX_TRAVERSAL_NODES:
                        raise EntityRelationshipTraversalBlockedError("lineage traversal limit exceeded")
                    stack.append((next_entity, overlap[0], overlap[1], visited | {next_entity}))
        return False

    @staticmethod
    def _intersect_intervals(start_a: str, end_a: str | None, start_b: str, end_b: str | None):
        start = max(start_a, start_b)
        ends = [end for end in (end_a, end_b) if end is not None]
        end = min(ends) if ends else None
        return None if end is not None and start >= end else (start, end)

    @staticmethod
    def _covers_interval(start, end, requested_start, requested_end) -> bool:
        return start <= requested_start and (end is None or (requested_end is not None and requested_end <= end))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _after(previous: str, candidate: str) -> str:
    prior = datetime.fromisoformat(previous)
    current = datetime.fromisoformat(candidate)
    if current <= prior:
        return (prior + timedelta(microseconds=1)).isoformat()
    return candidate
