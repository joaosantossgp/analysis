from __future__ import annotations

import pytest
import json
from sqlalchemy import create_engine, event, text

from src.companies.entity_registry import EntityRegistryRepository
from src.companies.entity_registry_schema import ensure_entity_registry_schema
from src.companies.entity_relationships import EntityRelationshipRepository
from src.companies.entity_resolution import EntityResolutionRepository, EntityResolutionValidationError


@pytest.fixture
def repositories():
    engine = create_engine("sqlite:///:memory:")
    ensure_entity_registry_schema(engine)
    return EntityRegistryRepository(engine), EntityRelationshipRepository(engine), EntityResolutionRepository(engine)


def _assertion(registry, relationships, entity_id, *, value, origin="source_ingestion"):
    evidence = registry.record_evidence(source_class="official_primary", source_reference="cvm://filing")
    return relationships.record_assertion(
        subject_entity_id=entity_id, domain="company.display", attribute="legal_name",
        value={"name": value}, origin=origin, actor_id=f"{origin}-actor", evidence_id=evidence.evidence_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )


def _policy(resolution):
    return resolution.create_policy(
        domain="company.display", attribute="legal_name", consumer_scope=None,
        eligible_assertion_states=("accepted",), eligible_origins=("user", "reviewer", "source_ingestion"),
        eligible_evidence_statuses=("available", "none"), origin_precedence=("user", "reviewer", "source_ingestion"),
        allows_user_override=True, effective_from="2024-01-01T00:00:00+00:00",
    )


def test_policy_resolution_selects_explicit_policy_and_precedence(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    source = _assertion(registry, relationships, entity.entity_id, value="Original")
    reviewed = _assertion(registry, relationships, entity.entity_id, value="Reviewed", origin="reviewer")
    policy = _policy(resolution)

    result = resolution.resolve(
        entity.entity_id, domain="company.display", attribute="legal_name",
        effective_as_of="2024-06-01T00:00:00+00:00",
    )
    assert result.status == "resolved"
    assert result.policy_id == policy.policy_id
    assert result.assertion_ids == (reviewed.assertion_id,)
    assert source.assertion_id not in result.assertion_ids


def test_conflicted_candidates_are_not_arbitrarily_resolved(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    first = _assertion(registry, relationships, entity.entity_id, value="A")
    second = _assertion(registry, relationships, entity.entity_id, value="B")
    _policy(resolution)

    result = resolution.resolve(
        entity.entity_id, domain="company.display", attribute="legal_name",
        effective_as_of="2024-06-01T00:00:00+00:00",
    )
    assert result.status == "conflicted"
    assert set(result.assertion_ids) == {first.assertion_id, second.assertion_id}
    with resolution._engine.connect() as conn:
        conflict = conn.execute(
            text("SELECT assertion_ids_json, resolution_status FROM entity_registry_conflicts")
        ).mappings().one()
    assert conflict["resolution_status"] == "unresolved"
    assert set(json.loads(conflict["assertion_ids_json"])) == {first.assertion_id, second.assertion_id}


def test_override_is_scoped_and_unknown_policy_is_rejected(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    assertion = _assertion(registry, relationships, entity.entity_id, value="Source", origin="user")
    policy = _policy(resolution)
    override = resolution.record_override(
        entity_id=entity.entity_id, domain="company.display", attribute="legal_name",
        policy_id=policy.policy_id, policy_version=policy.version, assertion_id=assertion.assertion_id,
        actor_id="analyst-1", reason="reviewed local correction",
        effective_from="2024-01-01T00:00:00+00:00",
    )
    result = resolution.resolve(
        entity.entity_id, domain="company.display", attribute="legal_name",
        effective_as_of="2024-06-01T00:00:00+00:00",
    )
    assert result.status == "resolved"
    assert result.override_id == override.override_id
    with pytest.raises(EntityResolutionValidationError, match="unknown policy"):
        resolution.record_override(
            entity_id=entity.entity_id, domain="company.display", attribute="legal_name",
            policy_id="missing", policy_version=1, assertion_id=assertion.assertion_id,
            actor_id="analyst-1", reason="no policy", effective_from="2024-01-01T00:00:00+00:00",
        )


def test_effective_as_of_is_required_and_ambiguous_policy_is_blocked(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    _assertion(registry, relationships, entity.entity_id, value="Source")
    _policy(resolution)
    _policy(resolution)

    with pytest.raises(EntityResolutionValidationError, match="effective_as_of is required"):
        resolution.resolve(entity.entity_id, domain="company.display", attribute="legal_name", effective_as_of=None)
    result = resolution.resolve(
        entity.entity_id, domain="company.display", attribute="legal_name",
        effective_as_of="2024-06-01T00:00:00+00:00",
    )
    assert result.status == "blocked"
    assert result.reason == "policy_ambiguous"


def test_policy_activation_preserves_prior_system_as_of_and_replaces_current_version(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    _assertion(registry, relationships, entity.entity_id, value="Source")
    v1 = _policy(resolution)
    v2 = resolution.activate_policy_version(
        prior_policy_id=v1.policy_id, prior_version=v1.version,
        effective_from="2025-01-01T00:00:00+00:00",
    )
    current = resolution.resolve(entity.entity_id, domain="company.display", attribute="legal_name", effective_as_of="2025-06-01T00:00:00+00:00")
    historical = resolution.resolve(
        entity.entity_id, domain="company.display", attribute="legal_name", effective_as_of="2024-06-01T00:00:00+00:00",
        system_as_of=v1.system_from,
    )
    assert current.policy_id == v2.policy_id and current.policy_version == 2
    assert historical.policy_id == v1.policy_id and historical.policy_version == 1


def test_override_rejects_cross_scope_reversal_and_policy_ineligible_assertion(repositories):
    registry, relationships, resolution = repositories
    first = registry.create_entity("organization", origin="source_ingestion")
    second = registry.create_entity("organization", origin="source_ingestion")
    first_assertion = _assertion(registry, relationships, first.entity_id, value="A", origin="user")
    second_assertion = _assertion(registry, relationships, second.entity_id, value="B", origin="user")
    policy = _policy(resolution)
    override = resolution.record_override(
        entity_id=first.entity_id, domain="company.display", attribute="legal_name", policy_id=policy.policy_id,
        policy_version=policy.version, assertion_id=first_assertion.assertion_id, actor_id="analyst", reason="choice",
        effective_from="2024-01-01T00:00:00+00:00",
    )
    with pytest.raises(EntityResolutionValidationError, match="reversal must match override scope"):
        resolution.record_override(
            entity_id=second.entity_id, domain="company.display", attribute="legal_name", policy_id=policy.policy_id,
            policy_version=policy.version, assertion_id=second_assertion.assertion_id, actor_id="analyst", reason="bad",
            effective_from="2024-01-01T00:00:00+00:00", reverses_override_id=override.override_id,
        )
    assert resolution.resolve(first.entity_id, domain="company.display", attribute="legal_name", effective_as_of="2024-06-01T00:00:00+00:00").override_id == override.override_id
    rejected = relationships.record_assertion(
        subject_entity_id=second.entity_id, domain="company.display", attribute="legal_name", value={"name": "bad"},
        origin="user", actor_id="analyst", evidence_id=None, reason="manual", assertion_state="rejected",
        effective_from="2024-01-01T00:00:00+00:00",
    )
    with pytest.raises(EntityResolutionValidationError, match="eligible under policy"):
        resolution.record_override(
            entity_id=second.entity_id, domain="company.display", attribute="legal_name", policy_id=policy.policy_id,
            policy_version=policy.version, assertion_id=rejected.assertion_id, actor_id="analyst", reason="bad",
            effective_from="2024-01-01T00:00:00+00:00",
        )


def test_sqlite_actual_override_read_uses_override_lookup_index(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    assertion = _assertion(registry, relationships, entity.entity_id, value="Source", origin="user")
    policy = _policy(resolution)
    resolution.record_override(
        entity_id=entity.entity_id, domain="company.display", attribute="legal_name", policy_id=policy.policy_id,
        policy_version=policy.version, assertion_id=assertion.assertion_id, actor_id="analyst", reason="choice",
        effective_from="2024-01-01T00:00:00+00:00",
    )
    captured = []

    def capture(_conn, _cursor, statement, parameters, _context, _executemany):
        if "SELECT override.* FROM entity_registry_resolution_overrides override" in statement:
            captured.append((statement, parameters))

    event.listen(resolution._engine, "before_cursor_execute", capture)
    try:
        resolution.resolve(entity.entity_id, domain="company.display", attribute="legal_name", effective_as_of="2024-06-01T00:00:00+00:00")
    finally:
        event.remove(resolution._engine, "before_cursor_execute", capture)
    statement, parameters = captured[0]
    with resolution._engine.connect() as conn:
        details = [row[-1] for row in conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", parameters)]
    assert any("idx_er_override_lookup" in detail for detail in details)
