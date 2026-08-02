"""Versioned, point-in-time canonical resolution for registry assertions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from sqlalchemy import Engine, text

from src.companies.entity_registry_schema import (
    ASSERTION_STATES,
    ORIGINS,
    SOURCE_STATUSES,
    validate_entity_registry_schema,
)
from src.companies.entity_relationships import EntityRelationshipRepository, AssertionRecord


class EntityResolutionError(ValueError):
    """Base typed failure for resolution commands."""


class EntityResolutionValidationError(EntityResolutionError):
    """A policy or override is invalid under the registry contract."""


@dataclass(frozen=True)
class ResolutionPolicyRecord:
    policy_id: str
    version: int
    domain: str
    attribute: str
    consumer_scope: str | None
    eligible_assertion_states: tuple[str, ...]
    eligible_origins: tuple[str, ...]
    eligible_evidence_statuses: tuple[str, ...]
    origin_precedence: tuple[str, ...]
    allows_user_override: bool
    effective_from: str
    effective_to: str | None
    system_from: str
    system_to: str | None


@dataclass(frozen=True)
class ResolutionOverrideRecord:
    override_id: str
    entity_id: str
    domain: str
    attribute: str
    consumer_scope: str | None
    policy_id: str
    policy_version: int
    assertion_id: str
    actor_id: str
    reason: str
    reverses_override_id: str | None
    effective_from: str
    effective_to: str | None
    system_from: str
    system_to: str | None


@dataclass(frozen=True)
class ResolutionResult:
    status: str
    reason: str | None
    entity_id: str
    domain: str
    attribute: str
    consumer_scope: str | None
    effective_as_of: str
    system_as_of: str
    policy_id: str | None
    policy_version: int | None
    assertion_ids: tuple[str, ...]
    override_id: str | None


class EntityResolutionRepository:
    """Resolves from persisted local assertions; no implicit policy or source fallback."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._relationships = EntityRelationshipRepository(engine)
        validate_entity_registry_schema(engine)

    def create_policy(
        self,
        *,
        domain: str,
        attribute: str,
        consumer_scope: str | None,
        eligible_assertion_states: tuple[str, ...],
        eligible_origins: tuple[str, ...],
        eligible_evidence_statuses: tuple[str, ...],
        origin_precedence: tuple[str, ...],
        allows_user_override: bool,
        effective_from: str,
        effective_to: str | None = None,
        policy_id: str | None = None,
        version: int = 1,
    ) -> ResolutionPolicyRecord:
        self._nonempty("domain", domain)
        self._nonempty("attribute", attribute)
        if not isinstance(version, int) or version < 1:
            raise EntityResolutionValidationError("policy version must be positive")
        states = self._allowed_values("eligible assertion state", eligible_assertion_states, ASSERTION_STATES)
        origins = self._allowed_values("eligible origin", eligible_origins, ORIGINS)
        evidence_statuses = self._allowed_values(
            "eligible evidence status", eligible_evidence_statuses, ("none", *SOURCE_STATUSES)
        )
        precedence = self._allowed_values("origin precedence", origin_precedence, origins)
        if set(precedence) != set(origins):
            raise EntityResolutionValidationError("origin precedence must cover every eligible origin exactly once")
        effective_from, effective_to = self._interval(effective_from, effective_to)
        record = ResolutionPolicyRecord(
            policy_id=policy_id or uuid4().hex, version=version, domain=domain.strip(), attribute=attribute.strip(),
            consumer_scope=self._scope(consumer_scope), eligible_assertion_states=states,
            eligible_origins=origins, eligible_evidence_statuses=evidence_statuses,
            origin_precedence=precedence, allows_user_override=bool(allows_user_override),
            effective_from=effective_from, effective_to=effective_to, system_from=_utc_now(), system_to=None,
        )
        with self._engine.begin() as conn:
            duplicate = conn.execute(text("""
                SELECT 1 FROM entity_registry_resolution_policies
                WHERE policy_id = :policy_id AND version = :version
            """), {"policy_id": record.policy_id, "version": record.version}).first()
            if duplicate is not None:
                raise EntityResolutionValidationError("policy id and version are immutable")
            conn.execute(text("""
                INSERT INTO entity_registry_resolution_policies (
                    policy_id, version, domain, attribute, consumer_scope, eligible_assertion_states_json,
                    eligible_origins_json, eligible_evidence_statuses_json, origin_precedence_json,
                    allows_user_override, effective_from, effective_to, system_from, system_to
                ) VALUES (
                    :policy_id, :version, :domain, :attribute, :consumer_scope, :states, :origins,
                    :evidence_statuses, :precedence, :allows_user_override, :effective_from, :effective_to,
                    :system_from, :system_to
                )
            """), {
                **record.__dict__, "states": json.dumps(record.eligible_assertion_states),
                "origins": json.dumps(record.eligible_origins),
                "evidence_statuses": json.dumps(record.eligible_evidence_statuses),
                "precedence": json.dumps(record.origin_precedence),
                "allows_user_override": int(record.allows_user_override),
            })
        return record

    def activate_policy_version(
        self, *, prior_policy_id: str, prior_version: int, effective_from: str
    ) -> ResolutionPolicyRecord:
        """Append a successor policy and close the prior system belief atomically."""
        effective_from = self._as_of("effective_from", effective_from)
        with self._engine.begin() as conn:
            prior = self._policy_by_id(conn, prior_policy_id, prior_version)
            if prior is None or prior.system_to is not None:
                raise EntityResolutionValidationError("prior policy is not active")
            if effective_from <= prior.effective_from:
                raise EntityResolutionValidationError("successor policy must start after prior policy")
            now = _after(prior.system_from, _utc_now())
            record = ResolutionPolicyRecord(
                policy_id=prior.policy_id, version=prior.version + 1, domain=prior.domain,
                attribute=prior.attribute, consumer_scope=prior.consumer_scope,
                eligible_assertion_states=prior.eligible_assertion_states,
                eligible_origins=prior.eligible_origins,
                eligible_evidence_statuses=prior.eligible_evidence_statuses,
                origin_precedence=prior.origin_precedence,
                allows_user_override=prior.allows_user_override,
                effective_from=effective_from, effective_to=None, system_from=now, system_to=None,
            )
            duplicate = self._policy_by_id(conn, record.policy_id, record.version)
            if duplicate is not None:
                raise EntityResolutionValidationError("successor policy version already exists")
            conn.execute(text("""
                UPDATE entity_registry_resolution_policies
                SET system_to = :system_to
                WHERE policy_id = :policy_id AND version = :version AND system_to IS NULL
            """), {"system_to": now, "policy_id": prior.policy_id, "version": prior.version})
            self._insert_policy(conn, record)
        return record

    def record_override(
        self,
        *,
        entity_id: str,
        domain: str,
        attribute: str,
        policy_id: str,
        policy_version: int,
        assertion_id: str,
        actor_id: str,
        reason: str,
        effective_from: str,
        consumer_scope: str | None = None,
        effective_to: str | None = None,
        reverses_override_id: str | None = None,
    ) -> ResolutionOverrideRecord:
        self._nonempty("actor_id", actor_id)
        self._nonempty("reason", reason)
        effective_from, effective_to = self._interval(effective_from, effective_to)
        scope = self._scope(consumer_scope)
        with self._engine.begin() as conn:
            policy = self._policy_by_id(conn, policy_id, policy_version)
            if policy is None:
                raise EntityResolutionValidationError("unknown policy")
            if (policy.domain, policy.attribute, policy.consumer_scope) != (domain, attribute, scope):
                raise EntityResolutionValidationError("override must match policy domain, attribute, and consumer scope")
            if not policy.allows_user_override:
                raise EntityResolutionValidationError("policy does not allow user override")
            assertion = conn.execute(text("SELECT * FROM entity_registry_assertions WHERE assertion_id = :assertion_id"), {"assertion_id": assertion_id}).mappings().one_or_none()
            if assertion is None or (assertion["subject_entity_id"], assertion["domain"], assertion["attribute"]) != (entity_id, domain, attribute):
                raise EntityResolutionValidationError("override assertion must match entity and policy attribute")
            assertion_record = self._relationships._assertion_record(assertion)
            if assertion_record.origin != "user" or not self._eligible(assertion_record, policy):
                raise EntityResolutionValidationError("override assertion must be eligible under policy")
            if not self._covers(assertion_record.effective_from, assertion_record.effective_to, effective_from, effective_to) or assertion_record.system_to is not None:
                raise EntityResolutionValidationError("override assertion must be active for override interval")
            if reverses_override_id is not None:
                prior = conn.execute(text("SELECT * FROM entity_registry_resolution_overrides WHERE override_id = :override_id"), {"override_id": reverses_override_id}).mappings().one_or_none()
                if prior is None:
                    raise EntityResolutionValidationError("unknown reversed override")
                if prior["system_to"] is not None:
                    raise EntityResolutionValidationError("override is already reversed")
                prior_scope = (
                    prior["entity_id"], prior["domain"], prior["attribute"], prior["consumer_scope"],
                    prior["policy_id"], prior["policy_version"],
                )
                if prior_scope != (entity_id, domain, attribute, scope, policy_id, policy_version):
                    raise EntityResolutionValidationError("reversal must match override scope")
                now = _after(prior["system_from"], _utc_now())
                conn.execute(text("UPDATE entity_registry_resolution_overrides SET system_to = :now WHERE override_id = :override_id"), {"now": now, "override_id": reverses_override_id})
            else:
                now = _utc_now()
            record = ResolutionOverrideRecord(
                override_id=uuid4().hex, entity_id=entity_id, domain=domain, attribute=attribute,
                consumer_scope=scope, policy_id=policy_id, policy_version=policy_version,
                assertion_id=assertion_id, actor_id=actor_id.strip(), reason=reason.strip(),
                reverses_override_id=reverses_override_id, effective_from=effective_from, effective_to=effective_to,
                system_from=now, system_to=None,
            )
            conn.execute(text("""
                INSERT INTO entity_registry_resolution_overrides (
                    override_id, entity_id, domain, attribute, consumer_scope, policy_id, policy_version,
                    assertion_id, actor_id, reason, reverses_override_id, effective_from, effective_to, system_from, system_to
                ) VALUES (
                    :override_id, :entity_id, :domain, :attribute, :consumer_scope, :policy_id, :policy_version,
                    :assertion_id, :actor_id, :reason, :reverses_override_id, :effective_from, :effective_to, :system_from, :system_to
                )
            """), record.__dict__)
        return record

    def resolve(
        self,
        entity_id: str,
        *,
        domain: str,
        attribute: str,
        effective_as_of: str | None,
        system_as_of: str | None = None,
        consumer_scope: str | None = None,
        policy_id: str | None = None,
        policy_version: int | None = None,
    ) -> ResolutionResult:
        effective = self._as_of("effective_as_of", effective_as_of)
        system = self._as_of("system_as_of", system_as_of or _utc_now())
        scope = self._scope(consumer_scope)
        with self._engine.connect() as conn:
            if policy_id is not None or policy_version is not None:
                if policy_id is None or policy_version is None:
                    raise EntityResolutionValidationError("policy_id and policy_version must be pinned together")
                policy = self._policy_by_id(conn, policy_id, policy_version)
                policies = [policy] if policy and self._is_applicable(policy, domain, attribute, scope, effective, system) else []
            else:
                policies = self._applicable_policies(conn, domain, attribute, scope, effective, system)
        base = dict(
            entity_id=entity_id, domain=domain, attribute=attribute, consumer_scope=scope,
            effective_as_of=effective, system_as_of=system,
        )
        if not policies:
            return ResolutionResult(status="blocked", reason="policy_missing", policy_id=None, policy_version=None, assertion_ids=(), override_id=None, **base)
        if len(policies) != 1:
            return ResolutionResult(status="blocked", reason="policy_ambiguous", policy_id=None, policy_version=None, assertion_ids=(), override_id=None, **base)
        policy = policies[0]
        with self._engine.connect() as conn:
            overrides = self._active_overrides(conn, entity_id, policy, effective, system)
        if overrides:
            if len(overrides) == 1:
                override = overrides[0]
                return ResolutionResult(status="resolved", reason="user_override", policy_id=policy.policy_id, policy_version=policy.version, assertion_ids=(override.assertion_id,), override_id=override.override_id, **base)
            return ResolutionResult(status="ambiguous", reason="override_ambiguous", policy_id=policy.policy_id, policy_version=policy.version, assertion_ids=tuple(item.assertion_id for item in overrides), override_id=None, **base)
        assertions = self._relationships.find_assertions(
            entity_id, domain=domain, attribute=attribute, effective_as_of=effective, system_as_of=system
        )
        eligible = [item for item in assertions if self._eligible(item, policy)]
        if not eligible:
            status = "unavailable" if assertions else "blocked"
            reason = "evidence_unavailable" if assertions else "no_eligible_assertion"
            return ResolutionResult(status=status, reason=reason, policy_id=policy.policy_id, policy_version=policy.version, assertion_ids=(), override_id=None, **base)
        rankings = {origin: index for index, origin in enumerate(policy.origin_precedence)}
        best_rank = min(rankings[item.origin] for item in eligible)
        candidates = [item for item in eligible if rankings[item.origin] == best_rank]
        if len(candidates) != 1:
            self._record_conflict(entity_id, domain, attribute, candidates, effective)
            return ResolutionResult(status="conflicted", reason="conflict_unresolved", policy_id=policy.policy_id, policy_version=policy.version, assertion_ids=tuple(item.assertion_id for item in candidates), override_id=None, **base)
        return ResolutionResult(status="resolved", reason=None, policy_id=policy.policy_id, policy_version=policy.version, assertion_ids=(candidates[0].assertion_id,), override_id=None, **base)

    def _applicable_policies(self, conn, domain, attribute, scope, effective, system) -> list[ResolutionPolicyRecord]:
        rows = conn.execute(text("""
            SELECT * FROM entity_registry_resolution_policies
            WHERE domain = :domain AND attribute = :attribute
              AND ((consumer_scope = :scope) OR (consumer_scope IS NULL AND :scope IS NULL))
              AND effective_from <= :effective AND (effective_to IS NULL OR effective_to > :effective)
              AND system_from <= :system AND (system_to IS NULL OR system_to > :system)
            ORDER BY policy_id, version
        """), {"domain": domain, "attribute": attribute, "scope": scope, "effective": effective, "system": system}).mappings().all()
        return [self._policy_record(row) for row in rows]

    def _active_overrides(self, conn, entity_id, policy, effective, system) -> list[ResolutionOverrideRecord]:
        if not policy.allows_user_override:
            return []
        rows = conn.execute(text("""
            SELECT override.* FROM entity_registry_resolution_overrides override
            WHERE entity_id = :entity_id AND policy_id = :policy_id AND policy_version = :policy_version
              AND override.effective_from <= :effective AND (override.effective_to IS NULL OR override.effective_to > :effective)
              AND override.system_from <= :system AND (override.system_to IS NULL OR override.system_to > :system)
        """), {"entity_id": entity_id, "policy_id": policy.policy_id, "policy_version": policy.version, "effective": effective, "system": system}).mappings().all()
        records = []
        for row in rows:
            assertion_row = conn.execute(text("SELECT * FROM entity_registry_assertions WHERE assertion_id = :assertion_id"), {"assertion_id": row["assertion_id"]}).mappings().one_or_none()
            if assertion_row is None:
                continue
            assertion = self._relationships._assertion_record(assertion_row)
            if (
                assertion.origin == "user" and self._eligible(assertion, policy)
                and assertion.effective_from <= effective
                and (assertion.effective_to is None or assertion.effective_to > effective)
                and assertion.system_from <= system
                and (assertion.system_to is None or assertion.system_to > system)
            ):
                records.append(ResolutionOverrideRecord(**{key: row[key] for key in ResolutionOverrideRecord.__dataclass_fields__}))
        return records

    def _insert_policy(self, conn, record: ResolutionPolicyRecord) -> None:
        conn.execute(text("""
            INSERT INTO entity_registry_resolution_policies (
                policy_id, version, domain, attribute, consumer_scope, eligible_assertion_states_json,
                eligible_origins_json, eligible_evidence_statuses_json, origin_precedence_json,
                allows_user_override, effective_from, effective_to, system_from, system_to
            ) VALUES (:policy_id, :version, :domain, :attribute, :consumer_scope, :states, :origins,
                :evidence_statuses, :precedence, :allows_user_override, :effective_from, :effective_to,
                :system_from, :system_to)
        """), {
            **record.__dict__, "states": json.dumps(record.eligible_assertion_states),
            "origins": json.dumps(record.eligible_origins), "evidence_statuses": json.dumps(record.eligible_evidence_statuses),
            "precedence": json.dumps(record.origin_precedence), "allows_user_override": int(record.allows_user_override),
        })

    def _record_conflict(self, entity_id, domain, attribute, candidates, effective_from) -> None:
        assertion_ids = tuple(sorted(item.assertion_id for item in candidates))
        with self._engine.begin() as conn:
            existing = conn.execute(text("""
                SELECT 1 FROM entity_registry_conflicts
                WHERE entity_id = :entity_id AND domain = :domain AND attribute = :attribute
                  AND assertion_ids_json = :assertion_ids AND resolution_status = 'unresolved'
            """), {"entity_id": entity_id, "domain": domain, "attribute": attribute, "assertion_ids": json.dumps(assertion_ids)}).first()
            if existing is None:
                conn.execute(text("""
                    INSERT INTO entity_registry_conflicts (
                        conflict_id, entity_id, domain, attribute, assertion_ids_json, effective_from,
                        effective_to, detected_at, resolution_status, resolved_at
                    ) VALUES (:conflict_id, :entity_id, :domain, :attribute, :assertion_ids, :effective_from,
                        NULL, :detected_at, 'unresolved', NULL)
                """), {"conflict_id": uuid4().hex, "entity_id": entity_id, "domain": domain,
                    "attribute": attribute, "assertion_ids": json.dumps(assertion_ids), "effective_from": effective_from,
                    "detected_at": _utc_now()})

    def _policy_by_id(self, conn, policy_id, version) -> ResolutionPolicyRecord | None:
        row = conn.execute(text("SELECT * FROM entity_registry_resolution_policies WHERE policy_id = :policy_id AND version = :version"), {"policy_id": policy_id, "version": version}).mappings().one_or_none()
        return self._policy_record(row) if row else None

    @staticmethod
    def _policy_record(row) -> ResolutionPolicyRecord:
        data = dict(row)
        data["eligible_assertion_states"] = tuple(json.loads(data.pop("eligible_assertion_states_json")))
        data["eligible_origins"] = tuple(json.loads(data.pop("eligible_origins_json")))
        data["eligible_evidence_statuses"] = tuple(json.loads(data.pop("eligible_evidence_statuses_json")))
        data["origin_precedence"] = tuple(json.loads(data.pop("origin_precedence_json")))
        data["allows_user_override"] = bool(data["allows_user_override"])
        return ResolutionPolicyRecord(**data)

    @staticmethod
    def _eligible(assertion: AssertionRecord, policy: ResolutionPolicyRecord) -> bool:
        return (
            assertion.assertion_state in policy.eligible_assertion_states
            and assertion.origin in policy.eligible_origins
            and assertion.evidence_status in policy.eligible_evidence_statuses
        )

    @staticmethod
    def _is_applicable(policy, domain, attribute, scope, effective, system) -> bool:
        return (
            (policy.domain, policy.attribute, policy.consumer_scope) == (domain, attribute, scope)
            and policy.effective_from <= effective
            and (policy.effective_to is None or policy.effective_to > effective)
            and policy.system_from <= system
            and (policy.system_to is None or policy.system_to > system)
        )

    @staticmethod
    def _covers(start, end, requested_start, requested_end) -> bool:
        return start <= requested_start and (end is None or (requested_end is not None and requested_end <= end))

    @staticmethod
    def _nonempty(label: str, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise EntityResolutionValidationError(f"{label} is required")

    @staticmethod
    def _scope(scope: str | None) -> str | None:
        if scope is None:
            return None
        if not isinstance(scope, str) or not scope.strip():
            raise EntityResolutionValidationError("consumer_scope must be a nonempty string")
        return scope.strip()

    @staticmethod
    def _allowed_values(label, values, allowed) -> tuple[str, ...]:
        if not isinstance(values, tuple) or not values:
            raise EntityResolutionValidationError(f"{label} list is required")
        if len(set(values)) != len(values) or any(value not in allowed for value in values):
            raise EntityResolutionValidationError(f"invalid {label}")
        return values

    @classmethod
    def _as_of(cls, label, value) -> str:
        if value is None:
            raise EntityResolutionValidationError(f"{label} is required")
        return cls._instant(value)

    @classmethod
    def _interval(cls, start, end):
        start = cls._instant(start)
        end = cls._instant(end) if end is not None else None
        if end is not None and start >= end:
            raise EntityResolutionValidationError("invalid temporal interval")
        return start, end

    @staticmethod
    def _instant(value):
        try:
            instant = datetime.fromisoformat(value)
        except (TypeError, ValueError) as error:
            raise EntityResolutionValidationError("UTC instant is required") from error
        if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
            raise EntityResolutionValidationError("UTC instant is required")
        return instant.astimezone(timezone.utc).isoformat()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _after(previous: str, candidate: str) -> str:
    prior, current = datetime.fromisoformat(previous), datetime.fromisoformat(candidate)
    return (prior + timedelta(microseconds=1)).isoformat() if current <= prior else candidate
