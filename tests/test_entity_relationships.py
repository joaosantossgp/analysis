from __future__ import annotations

import pytest
from sqlalchemy import create_engine

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
        origin="reviewer",
        actor_id="reviewer-1",
        evidence_id=None,
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
