from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import pytest
import json
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError

from src.companies.entity_registry import EntityRegistryRepository
from src.companies.entity_registry_schema import ensure_entity_registry_schema
from src.companies.entity_relationships import EntityRelationshipRepository
from src.companies.entity_resolution import (
    EntityResolutionConcurrencyError,
    EntityResolutionRepository,
    EntityResolutionValidationError,
)


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


def _policy(resolution, *, effective_to=None):
    return resolution.create_policy(
        domain="company.display", attribute="legal_name", consumer_scope=None,
        eligible_assertion_states=("accepted",), eligible_origins=("user", "reviewer", "source_ingestion"),
        eligible_evidence_statuses=("available", "none"), origin_precedence=("user", "reviewer", "source_ingestion"),
        allows_user_override=True, effective_from="2024-01-01T00:00:00+00:00", effective_to=effective_to,
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
    with resolution._engine.connect() as conn:
        conflict_id = conn.execute(text("SELECT conflict_id FROM entity_registry_conflicts")).scalar_one()
    resolved = resolution.transition_conflict(conflict_id, actor_id="reviewer", reason="review completed")
    reversed_ = resolution.transition_conflict(resolved, actor_id="reviewer", reason="reopened", reverses_conflict_id=resolved)
    with resolution._engine.connect() as conn:
        states = conn.execute(text("SELECT resolution_status FROM entity_registry_conflicts ORDER BY system_from")).scalars().all()
    assert states == ["unresolved", "resolved", "reversed"]


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
        origin_precedence=("source_ingestion", "reviewer", "user"),
    )
    current = resolution.resolve(entity.entity_id, domain="company.display", attribute="legal_name", effective_as_of="2025-06-01T00:00:00+00:00")
    historical = resolution.resolve(
        entity.entity_id, domain="company.display", attribute="legal_name", effective_as_of="2024-06-01T00:00:00+00:00",
        system_as_of=v1.system_from,
    )
    current_past = resolution.resolve(
        entity.entity_id, domain="company.display", attribute="legal_name", effective_as_of="2024-06-01T00:00:00+00:00",
    )
    assert current.policy_id == v2.policy_id and current.policy_version == 2
    assert historical.policy_id == v1.policy_id and historical.policy_version == 1
    assert current_past.policy_id == v1.policy_id and current_past.policy_version == 1
    assert v2.origin_precedence == ("source_ingestion", "reviewer", "user")

    with pytest.raises(EntityResolutionValidationError, match="successor versions require activation"):
        resolution.create_policy(
            domain="company.display", attribute="legal_name", consumer_scope=None,
            eligible_assertion_states=("accepted",), eligible_origins=("user",),
            eligible_evidence_statuses=("available",), origin_precedence=("user",),
            allows_user_override=False, effective_from="2025-01-01T00:00:00+00:00",
            policy_id=v1.policy_id, version=3,
        )


def test_override_requires_policy_activation_to_cover_its_complete_interval(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    assertion = _assertion(registry, relationships, entity.entity_id, value="Source", origin="user")
    policy = _policy(resolution)
    with pytest.raises(EntityResolutionValidationError, match="policy must cover override interval"):
        resolution.record_override(
            entity_id=entity.entity_id, domain="company.display", attribute="legal_name", policy_id=policy.policy_id,
            policy_version=policy.version, assertion_id=assertion.assertion_id, actor_id="analyst", reason="choice",
            effective_from="2023-01-01T00:00:00+00:00",
        )
    resolution.activate_policy_version(
        prior_policy_id=policy.policy_id, prior_version=policy.version,
        effective_from="2025-01-01T00:00:00+00:00",
    )
    with pytest.raises(EntityResolutionValidationError, match="policy is not current"):
        resolution.record_override(
            entity_id=entity.entity_id, domain="company.display", attribute="legal_name", policy_id=policy.policy_id,
            policy_version=policy.version, assertion_id=assertion.assertion_id, actor_id="analyst", reason="stale",
            effective_from="2024-01-01T00:00:00+00:00",
        )


def test_policy_successor_cannot_fill_an_intentional_finite_gap(repositories):
    _registry, _relationships, resolution = repositories
    policy = _policy(resolution, effective_to="2025-01-01T00:00:00+00:00")
    with pytest.raises(EntityResolutionValidationError, match="within predecessor effective interval"):
        resolution.activate_policy_version(
            prior_policy_id=policy.policy_id, prior_version=policy.version,
            effective_from="2026-01-01T00:00:00+00:00",
        )


def test_policy_successor_at_finite_boundary_is_contiguous(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    _assertion(registry, relationships, entity.entity_id, value="Source")
    first = _policy(resolution, effective_to="2025-01-01T00:00:00+00:00")

    second = resolution.activate_policy_version(
        prior_policy_id=first.policy_id,
        prior_version=first.version,
        effective_from="2025-01-01T00:00:00+00:00",
    )

    before = resolution.resolve(
        entity.entity_id, domain="company.display", attribute="legal_name",
        effective_as_of="2024-12-31T23:59:59+00:00",
    )
    at_boundary = resolution.resolve(
        entity.entity_id, domain="company.display", attribute="legal_name",
        effective_as_of="2025-01-01T00:00:00+00:00",
    )
    assert before.policy_version == first.version
    assert at_boundary.policy_version == second.version


def test_historical_resolution_conflict_uses_detection_time_and_transition_matrix(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    first = _assertion(registry, relationships, entity.entity_id, value="A")
    second = _assertion(registry, relationships, entity.entity_id, value="B")
    policy = _policy(resolution)
    historical_system = policy.system_from
    resolution.resolve(entity.entity_id, domain="company.display", attribute="legal_name",
        effective_as_of="2024-06-01T00:00:00+00:00", system_as_of=historical_system)
    with resolution._engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM entity_registry_conflicts")).mappings().one()
    assert row["system_from"] > historical_system
    assert row["detected_actor"] == "system:resolution"
    resolved = resolution.transition_conflict(row["conflict_id"], actor_id="reviewer", reason="decided")
    with pytest.raises(EntityResolutionConcurrencyError, match="retry"):
        resolution.transition_conflict(row["conflict_id"], actor_id="reviewer", reason="repeat")
    reversed_ = resolution.transition_conflict(resolved, actor_id="supervisor", origin="reviewer", reason="reopen", reverses_conflict_id=resolved)
    with resolution._engine.connect() as conn:
        final = conn.execute(text("SELECT * FROM entity_registry_conflicts WHERE conflict_id = :conflict_id"), {"conflict_id": reversed_}).mappings().one()
    assert final["detected_actor"] == "system:resolution"
    assert (final["resolved_actor"], final["resolved_origin"]) == ("reviewer", "reviewer")
    assert (final["reversed_actor"], final["reversed_origin"]) == ("supervisor", "reviewer")


def _racers(engine):
    """Build both racing repositories up front: construction validates the
    schema and would otherwise contend with the winner's SQLite write lock."""
    return iter([EntityResolutionRepository(engine), EntityResolutionRepository(engine)])


def test_sqlite_concurrent_policy_activation_returns_one_successor(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'policy.db'}", connect_args={"timeout": 0.01})
    ensure_entity_registry_schema(engine)
    first = EntityResolutionRepository(engine).create_policy(
        domain="company.display", attribute="legal_name", consumer_scope=None,
        eligible_assertion_states=("accepted",), eligible_origins=("user",),
        eligible_evidence_statuses=("available",), origin_precedence=("user",),
        allows_user_override=True, effective_from="2024-01-01T00:00:00+00:00",
    )
    racers = _racers(engine)

    def activate():
        try:
            return next(racers).activate_policy_version(
                prior_policy_id=first.policy_id, prior_version=1, effective_from="2025-01-01T00:00:00+00:00"
            ).version
        except EntityResolutionValidationError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: activate(), range(2)))
    assert set(outcomes) == {"blocked", 2}


def test_sqlite_concurrent_override_reversal_creates_one_current_successor(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'override.db'}", connect_args={"timeout": 0.01})
    ensure_entity_registry_schema(engine)
    registry = EntityRegistryRepository(engine)
    relationships = EntityRelationshipRepository(engine)
    entity = registry.create_entity("organization", origin="source_ingestion")
    assertion = _assertion(registry, relationships, entity.entity_id, value="Source", origin="user")
    policy = _policy(EntityResolutionRepository(engine))
    first = EntityResolutionRepository(engine).record_override(
        entity_id=entity.entity_id, domain="company.display", attribute="legal_name",
        policy_id=policy.policy_id, policy_version=policy.version, assertion_id=assertion.assertion_id,
        actor_id="analyst", reason="choice", effective_from="2024-01-01T00:00:00+00:00",
    )
    racers = _racers(engine)

    def reverse():
        try:
            return next(racers).record_override(
                entity_id=entity.entity_id, domain="company.display", attribute="legal_name",
                policy_id=policy.policy_id, policy_version=policy.version, assertion_id=assertion.assertion_id,
                actor_id="analyst", reason="reversal", effective_from="2024-01-01T00:00:00+00:00",
                reverses_override_id=first.override_id,
            ).override_id
        except EntityResolutionConcurrencyError:
            return "retry"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: reverse(), range(2)))
    assert outcomes.count("retry") == 1
    with engine.connect() as conn:
        current = conn.execute(text("SELECT override_id FROM entity_registry_resolution_overrides WHERE system_to IS NULL")).scalars().all()
    assert len(current) == 1


def test_sqlite_concurrent_conflict_detection_returns_conflicted_without_database_error(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'conflict.db'}", connect_args={"timeout": 0.01})
    ensure_entity_registry_schema(engine)
    registry = EntityRegistryRepository(engine)
    relationships = EntityRelationshipRepository(engine)
    entity = registry.create_entity("organization", origin="source_ingestion")
    _assertion(registry, relationships, entity.entity_id, value="A")
    _assertion(registry, relationships, entity.entity_id, value="B")
    _policy(EntityResolutionRepository(engine))
    first_insert = Barrier(2)
    insert_count = 0
    insert_lock = Lock()
    racers = _racers(engine)

    def synchronize_first_inserts(_conn, _cursor, statement, _parameters, _context, _executemany):
        nonlocal insert_count
        if "INSERT INTO entity_registry_conflicts" not in statement:
            return
        with insert_lock:
            insert_count += 1
            synchronize = insert_count <= 2
        if synchronize:
            first_insert.wait(timeout=3)

    def resolve():
        try:
            return next(racers).resolve(
                entity.entity_id, domain="company.display", attribute="legal_name",
                effective_as_of="2024-06-01T00:00:00+00:00",
            ).status
        except Exception as error:  # Regression: no raw SQLite lock/index error may escape resolve.
            return type(error).__name__

    event.listen(engine, "before_cursor_execute", synchronize_first_inserts)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: resolve(), range(2)))
    finally:
        event.remove(engine, "before_cursor_execute", synchronize_first_inserts)
    assert outcomes == ["conflicted", "conflicted"]


def test_unexpected_conflict_integrity_error_is_not_masked(repositories):
    registry, relationships, resolution = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    _assertion(registry, relationships, entity.entity_id, value="A")
    _assertion(registry, relationships, entity.entity_id, value="B")
    _policy(resolution)

    def fail_conflict_insert(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "INSERT INTO entity_registry_conflicts" in statement:
            raise IntegrityError("INSERT", {}, Exception("foreign key constraint failed"))

    event.listen(resolution._engine, "before_cursor_execute", fail_conflict_insert)
    try:
        with pytest.raises(IntegrityError, match="foreign key constraint failed"):
            resolution.resolve(
                entity.entity_id, domain="company.display", attribute="legal_name",
                effective_as_of="2024-06-01T00:00:00+00:00",
            )
    finally:
        event.remove(resolution._engine, "before_cursor_execute", fail_conflict_insert)


def test_sqlite_concurrent_conflict_resolution_returns_typed_retry_for_loser(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'resolve-conflict.db'}", connect_args={"timeout": 0.01})
    ensure_entity_registry_schema(engine)
    registry = EntityRegistryRepository(engine)
    relationships = EntityRelationshipRepository(engine)
    entity = registry.create_entity("organization", origin="source_ingestion")
    _assertion(registry, relationships, entity.entity_id, value="A")
    _assertion(registry, relationships, entity.entity_id, value="B")
    resolution = EntityResolutionRepository(engine)
    _policy(resolution)
    resolution.resolve(entity.entity_id, domain="company.display", attribute="legal_name", effective_as_of="2024-06-01T00:00:00+00:00")
    with engine.connect() as conn:
        conflict_id = conn.execute(text("SELECT conflict_id FROM entity_registry_conflicts WHERE system_to IS NULL")).scalar_one()
    racers = _racers(engine)

    def resolve_conflict():
        try:
            return next(racers).transition_conflict(conflict_id, actor_id="reviewer", reason="decided")
        except EntityResolutionConcurrencyError:
            return "retry"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: resolve_conflict(), range(2)))
    assert outcomes.count("retry") == 1
    with engine.connect() as conn:
        current_statuses = conn.execute(text("SELECT resolution_status FROM entity_registry_conflicts WHERE system_to IS NULL")).scalars().all()
    assert current_statuses == ["resolved"]


def test_sqlite_concurrent_conflict_reversal_returns_typed_retry_for_loser(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reverse-conflict.db'}", connect_args={"timeout": 0.01})
    ensure_entity_registry_schema(engine)
    registry = EntityRegistryRepository(engine)
    relationships = EntityRelationshipRepository(engine)
    entity = registry.create_entity("organization", origin="source_ingestion")
    _assertion(registry, relationships, entity.entity_id, value="A")
    _assertion(registry, relationships, entity.entity_id, value="B")
    resolution = EntityResolutionRepository(engine)
    _policy(resolution)
    resolution.resolve(entity.entity_id, domain="company.display", attribute="legal_name", effective_as_of="2024-06-01T00:00:00+00:00")
    with engine.connect() as conn:
        unresolved_id = conn.execute(text("SELECT conflict_id FROM entity_registry_conflicts WHERE system_to IS NULL")).scalar_one()
    resolved_id = resolution.transition_conflict(unresolved_id, actor_id="reviewer", reason="decided")
    racers = _racers(engine)

    def reverse_conflict():
        try:
            return next(racers).transition_conflict(
                resolved_id, actor_id="reviewer", reason="reopen", reverses_conflict_id=resolved_id,
            )
        except EntityResolutionConcurrencyError:
            return "retry"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: reverse_conflict(), range(2)))
    assert outcomes.count("retry") == 1
    with engine.connect() as conn:
        current_statuses = conn.execute(text("SELECT resolution_status FROM entity_registry_conflicts WHERE system_to IS NULL")).scalars().all()
    assert current_statuses == ["reversed"]


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
