from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, event, text

from src.companies.entity_registry import EntityRegistryRepository
from src.companies.entity_registry_schema import ensure_entity_registry_schema
from src.companies.entity_relationships import (
    EntityRelationshipRepository,
    EntityRelationshipValidationError,
)


@pytest.fixture
def repositories():
    engine = create_engine("sqlite:///:memory:")
    ensure_entity_registry_schema(engine)
    return EntityRegistryRepository(engine), EntityRelationshipRepository(engine)


def _assertion(registry, relationships, entity_id, *, value="controller"):
    evidence = registry.record_evidence(
        source_class="official_primary",
        source_reference="aneel://decision/1",
        source_authority="ANEEL",
    )
    return relationships.record_assertion(
        subject_entity_id=entity_id,
        domain="energy.distribution",
        attribute="control",
        value={"status": value},
        origin="source_ingestion",
        actor_id="aneel-import",
        evidence_id=evidence.evidence_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )


def test_relationship_keeps_dimensions_distinct_and_reads_bitemporally(repositories):
    registry, relationships = repositories
    controlled = registry.create_entity("organization", origin="source_ingestion")
    controller = registry.create_entity("organization", origin="source_ingestion")
    assertion = _assertion(registry, relationships, controlled.entity_id)

    control = relationships.record_relationship(
        subject_entity_id=controlled.entity_id,
        object_entity_id=controller.entity_id,
        dimension="control",
        payload={"basis": "shareholder agreement"},
        assertion_id=assertion.assertion_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )
    ownership = relationships.record_relationship(
        subject_entity_id=controlled.entity_id,
        object_entity_id=controller.entity_id,
        dimension="legal_ownership",
        payload={"interest": 0.51, "unit": "percent", "basis": "issued capital", "precision": 2},
        assertion_id=assertion.assertion_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )

    assert control.dimension == "control"
    assert ownership.dimension == "legal_ownership"
    rows = relationships.find_relationships(
        controlled.entity_id, effective_as_of="2024-06-01T00:00:00+00:00"
    )
    assert {row.relationship_id for row in rows} == {control.relationship_id, ownership.relationship_id}


def test_correction_closes_prior_system_belief_without_erasing_assertion(repositories):
    registry, relationships = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")
    prior = _assertion(registry, relationships, entity.entity_id, value="old")
    correction = relationships.record_assertion(
        subject_entity_id=entity.entity_id,
        domain="energy.distribution",
        attribute="control",
        value={"status": "corrected"},
        origin="user",
        actor_id="reviewer-1",
        evidence_id=None,
        reason="reviewed correction without a source record",
        effective_from="2024-01-01T00:00:00+00:00",
        supersedes_assertion_id=prior.assertion_id,
    )

    history = relationships.find_assertions(
        entity.entity_id,
        domain="energy.distribution",
        attribute="control",
        effective_as_of="2024-06-01T00:00:00+00:00",
        system_as_of=prior.system_from,
    )
    current = relationships.find_assertions(
        entity.entity_id,
        domain="energy.distribution",
        attribute="control",
        effective_as_of="2024-06-01T00:00:00+00:00",
    )
    assert [row.assertion_id for row in history] == [prior.assertion_id]
    assert [row.assertion_id for row in current] == [correction.assertion_id]


def test_evidence_free_assertion_requires_user_origin(repositories):
    registry, relationships = repositories
    entity = registry.create_entity("organization", origin="source_ingestion")

    with pytest.raises(EntityRelationshipValidationError, match="evidence-free assertion requires origin=user"):
        relationships.record_assertion(
            subject_entity_id=entity.entity_id,
            domain="company",
            attribute="status",
            value={"value": "unverified"},
            origin="source_ingestion",
            actor_id="importer",
            evidence_id=None,
            effective_from="2024-01-01T00:00:00+00:00",
        )

    with pytest.raises(EntityRelationshipValidationError, match="evidence-free assertion requires reason"):
        relationships.record_assertion(
            subject_entity_id=entity.entity_id,
            domain="company",
            attribute="status",
            value={"value": "unverified"},
            origin="user",
            actor_id="analyst",
            evidence_id=None,
            effective_from="2024-01-01T00:00:00+00:00",
        )


def test_rejects_control_overlap_cycles_and_retired_entity_attachments(repositories):
    registry, relationships = repositories
    first = registry.create_entity("organization", origin="source_ingestion")
    second = registry.create_entity("organization", origin="source_ingestion")
    third = registry.create_entity("organization", origin="source_ingestion")
    first_assertion = _assertion(registry, relationships, first.entity_id)
    second_assertion = _assertion(registry, relationships, second.entity_id)
    relationships.record_relationship(
        subject_entity_id=first.entity_id, object_entity_id=second.entity_id,
        dimension="control", payload={"basis": "contract"}, assertion_id=first_assertion.assertion_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )
    with pytest.raises(EntityRelationshipValidationError, match="exclusive relationship overlap"):
        relationships.record_relationship(
            subject_entity_id=first.entity_id, object_entity_id=third.entity_id,
            dimension="control", payload={"basis": "contract"}, assertion_id=first_assertion.assertion_id,
            effective_from="2024-02-01T00:00:00+00:00",
        )
    with pytest.raises(EntityRelationshipValidationError, match="cycle"):
        relationships.record_relationship(
            subject_entity_id=second.entity_id, object_entity_id=first.entity_id,
            dimension="control", payload={"basis": "contract"}, assertion_id=second_assertion.assertion_id,
            effective_from="2024-01-01T00:00:00+00:00",
        )
    evidence = registry.record_evidence(source_class="official_primary", source_reference="cvm://retired")
    registry.change_lifecycle(
        first.entity_id, lifecycle_status="retired", reason="dissolution", evidence_id=evidence.evidence_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )
    with pytest.raises(EntityRelationshipValidationError, match="retired or deprecated"):
        relationships.record_assertion(
            subject_entity_id=first.entity_id, domain="company", attribute="status", value={"value": "x"},
            origin="reviewer", actor_id="reviewer-1", evidence_id=None,
            effective_from="2025-01-01T00:00:00+00:00",
        )


def test_lineage_requires_distinct_entities_except_legal_continuation(repositories):
    registry, relationships = repositories
    first = registry.create_entity("organization", origin="source_ingestion")
    second = registry.create_entity("organization", origin="source_ingestion")
    assertion = _assertion(registry, relationships, first.entity_id)
    second_assertion = _assertion(registry, relationships, second.entity_id)

    continuation = relationships.record_lineage(
        predecessor_entity_id=first.entity_id, successor_entity_id=first.entity_id,
        predicate="legal_continuation", assertion_id=assertion.assertion_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )
    merger = relationships.record_lineage(
        predecessor_entity_id=first.entity_id, successor_entity_id=second.entity_id,
        predicate="merged_into", assertion_id=assertion.assertion_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )
    assert continuation.predecessor_entity_id == continuation.successor_entity_id
    assert merger.predecessor_entity_id != merger.successor_entity_id
    with pytest.raises(EntityRelationshipValidationError, match="cycle"):
        relationships.record_lineage(
            predecessor_entity_id=second.entity_id, successor_entity_id=first.entity_id,
            predicate="succeeded_by", assertion_id=second_assertion.assertion_id,
            effective_from="2024-01-01T00:00:00+00:00",
        )


def test_holder_is_distinct_from_operational_role_and_rejected_status_is_not_exclusive(repositories):
    registry, relationships = repositories
    subject = registry.create_entity("concession", origin="source_ingestion")
    holder = registry.create_entity("organization", origin="source_ingestion")
    operator = registry.create_entity("organization", origin="source_ingestion")
    assertion = _assertion(registry, relationships, subject.entity_id)

    holder_relation = relationships.record_relationship(
        subject_entity_id=subject.entity_id, object_entity_id=holder.entity_id,
        dimension="holder", payload={"basis": "concession grant"}, assertion_id=assertion.assertion_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )
    operator_relation = relationships.record_relationship(
        subject_entity_id=subject.entity_id, object_entity_id=operator.entity_id,
        dimension="operational_role", operational_role="operator", payload={"basis": "O&M"},
        assertion_id=assertion.assertion_id, effective_from="2024-01-01T00:00:00+00:00",
    )
    assert holder_relation.dimension == "holder"
    assert operator_relation.dimension == "operational_role"


def test_sequential_inverse_control_and_current_assertion_corrections_keep_bitemporal_history(repositories):
    registry, relationships = repositories
    first = registry.create_entity("organization", origin="source_ingestion")
    second = registry.create_entity("organization", origin="source_ingestion")
    first_assertion = _assertion(registry, relationships, first.entity_id)
    second_assertion = _assertion(registry, relationships, second.entity_id)
    first_relationship = relationships.record_relationship(
        subject_entity_id=first.entity_id, object_entity_id=second.entity_id, dimension="control",
        payload={"basis": "old"}, assertion_id=first_assertion.assertion_id,
        effective_from="2020-01-01T00:00:00+00:00", effective_to="2021-01-01T00:00:00+00:00",
    )
    successor = registry.create_entity("organization", origin="source_ingestion")
    first_lineage = relationships.record_lineage(
        predecessor_entity_id=first.entity_id, successor_entity_id=successor.entity_id,
        predicate="merged_into", assertion_id=first_assertion.assertion_id,
        effective_from="2020-01-01T00:00:00+00:00", effective_to="2021-01-01T00:00:00+00:00",
    )
    relationships.record_relationship(
        subject_entity_id=second.entity_id, object_entity_id=first.entity_id, dimension="control",
        payload={"basis": "new"}, assertion_id=second_assertion.assertion_id,
        effective_from="2021-01-01T00:00:00+00:00",
    )
    corrected = relationships.record_assertion(
        subject_entity_id=first.entity_id, domain="energy.distribution", attribute="control",
        value={"status": "corrected"}, origin="user", actor_id="analyst", evidence_id=None,
        reason="correct control evidence", effective_from="2020-01-01T00:00:00+00:00",
        supersedes_assertion_id=first_assertion.assertion_id,
    )
    assert not relationships.find_relationships(first.entity_id, effective_as_of="2020-06-01T00:00:00+00:00")
    history = relationships.find_relationships(
        first.entity_id, effective_as_of="2020-06-01T00:00:00+00:00", system_as_of=first_relationship.system_from
    )
    assert [row.relationship_id for row in history] == [first_relationship.relationship_id]
    assert not relationships.find_lineage(first.entity_id, effective_as_of="2020-06-01T00:00:00+00:00")
    lineage_history = relationships.find_lineage(
        first.entity_id, effective_as_of="2020-06-01T00:00:00+00:00", system_as_of=first_lineage.system_from
    )
    assert [row.lineage_id for row in lineage_history] == [first_lineage.lineage_id]
    assert corrected.supersedes_assertion_id == first_assertion.assertion_id


def test_invalid_relationship_and_assertion_statuses_are_rejected(repositories):
    registry, relationships = repositories
    subject = registry.create_entity("organization", origin="source_ingestion")
    object_ = registry.create_entity("organization", origin="source_ingestion")
    assertion = _assertion(registry, relationships, subject.entity_id)
    with pytest.raises(EntityRelationshipValidationError, match="review status"):
        relationships.record_assertion(
            subject_entity_id=subject.entity_id, domain="company", attribute="status", value={"x": 1},
            origin="source_ingestion", actor_id="import", evidence_id=assertion.evidence_id,
            effective_from="2024-01-01T00:00:00+00:00", review_status="anything",
        )
    with pytest.raises(EntityRelationshipValidationError, match="relationship status"):
        relationships.record_relationship(
            subject_entity_id=subject.entity_id, object_entity_id=object_.entity_id, dimension="control",
            payload={"basis": "x"}, assertion_id=assertion.assertion_id,
            effective_from="2024-01-01T00:00:00+00:00", relationship_status="anything",
        )


def test_sqlite_concurrent_control_writes_leave_only_one_accepted_overlap(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'relationships.db'}")
    ensure_entity_registry_schema(engine)
    registry = EntityRegistryRepository(engine)
    subject = registry.create_entity("organization", origin="source_ingestion")
    first = registry.create_entity("organization", origin="source_ingestion")
    second = registry.create_entity("organization", origin="source_ingestion")
    relationships = EntityRelationshipRepository(engine)
    assertion = _assertion(registry, relationships, subject.entity_id)

    def write(object_id):
        try:
            EntityRelationshipRepository(engine).record_relationship(
                subject_entity_id=subject.entity_id, object_entity_id=object_id, dimension="control",
                payload={"basis": "contract"}, assertion_id=assertion.assertion_id,
                effective_from="2024-01-01T00:00:00+00:00",
            )
            return "written"
        except EntityRelationshipValidationError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, (first.entity_id, second.entity_id)))
    assert sorted(outcomes) == ["blocked", "written"]


def test_existing_foundation_requires_explicit_migration_authorization(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'foundation.db'}")
    ensure_entity_registry_schema(engine)
    with engine.begin() as conn:
        for table_name in (
            "entity_registry_conflicts", "entity_registry_resolution_overrides",
            "entity_registry_resolution_policies", "entity_registry_lineage",
            "entity_registry_relationships", "entity_registry_assertions",
        ):
            conn.execute(text(f"DROP TABLE {table_name}"))

    with pytest.raises(ValueError, match="migration_authorized=True"):
        ensure_entity_registry_schema(engine)
    ensure_entity_registry_schema(engine, migration_authorized=True)


def test_sqlite_actual_relationship_read_uses_subject_and_object_indexes(repositories):
    registry, relationships = repositories
    subject = registry.create_entity("organization", origin="source_ingestion")
    object_ = registry.create_entity("organization", origin="source_ingestion")
    assertion = _assertion(registry, relationships, subject.entity_id)
    relationships.record_relationship(
        subject_entity_id=subject.entity_id, object_entity_id=object_.entity_id, dimension="control",
        payload={"basis": "contract"}, assertion_id=assertion.assertion_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )
    captured = []

    def capture(_conn, _cursor, statement, parameters, _context, _executemany):
        if "SELECT relationship.* FROM entity_registry_relationships relationship" in statement:
            captured.append((statement, parameters))

    event.listen(relationships._engine, "before_cursor_execute", capture)
    try:
        relationships.find_relationships(subject.entity_id, effective_as_of="2024-06-01T00:00:00+00:00")
    finally:
        event.remove(relationships._engine, "before_cursor_execute", capture)
    assert len(captured) == 1
    statement, parameters = captured[0]
    with relationships._engine.connect() as conn:
        details = [row[-1] for row in conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {statement}", parameters)]
    assert any("idx_er_relationship_subject" in detail for detail in details)
    assert any("idx_er_relationship_object" in detail for detail in details)
