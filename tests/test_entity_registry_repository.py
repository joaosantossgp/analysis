from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from src.companies.entity_registry import (
    EntityRegistryConflictError,
    EntityRegistryRepository,
    EntityRegistryValidationError,
)


@pytest.fixture
def repository():
    return EntityRegistryRepository(create_engine("sqlite:///:memory:"))


def test_creates_opaque_immutable_entity_id(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")

    assert entity.entity_id
    assert entity.entity_id != "organization"
    assert entity.entity_kind == "organization"
    assert repository.get_entity(entity.entity_id) == entity
    with pytest.raises(EntityRegistryValidationError, match="immutable"):
        repository.change_lifecycle(
            entity.entity_id,
            lifecycle_status="retired",
            reason="inactive registry record",
            replacement_entity_id="other",
        )


def test_identifier_claim_retains_raw_and_namespace_normalized_values(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="cvm://catalog/9512",
    )

    claim = repository.claim_identifier(
        entity_id=entity.entity_id,
        namespace="br.cvm.cd_cvm",
        raw_value=" 9512 ",
        scope_authority="CVM",
        identifier_strength="strong",
        evidence_id=evidence.evidence_id,
    )

    assert claim.raw_value == " 9512 "
    assert claim.normalized_value == "9512"
    assert claim.normalizer_version == "trim-exact/v1"


def test_duplicate_strong_identifier_is_preserved_as_conflicted_claim(repository):
    first = repository.create_entity("organization", origin="source_ingestion")
    second = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="cvm://catalog/9512",
    )
    repository.claim_identifier(
        entity_id=first.entity_id,
        namespace="br.cvm.cd_cvm",
        raw_value="9512",
        scope_authority="CVM",
        identifier_strength="strong",
        evidence_id=evidence.evidence_id,
    )

    with pytest.raises(EntityRegistryConflictError) as error:
        repository.claim_identifier(
            entity_id=second.entity_id,
            namespace="br.cvm.cd_cvm",
            raw_value="9512",
            scope_authority="CVM",
            identifier_strength="strong",
            evidence_id=evidence.evidence_id,
        )

    assert error.value.code == "duplicate_strong_id"
    claims = repository.find_identifier_claims("br.cvm.cd_cvm", "9512", "CVM")
    assert {claim.entity_id for claim in claims} == {first.entity_id, second.entity_id}
    assert {claim.claim_status for claim in claims} == {"accepted", "conflicted"}


def test_strong_identifier_reuse_is_allowed_for_non_overlapping_effective_intervals(repository):
    first = repository.create_entity("organization", origin="source_ingestion")
    second = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="cvm://catalog/9512",
    )
    repository.claim_identifier(
        entity_id=first.entity_id,
        namespace="br.cvm.cd_cvm",
        raw_value="9512",
        scope_authority="CVM",
        identifier_strength="strong",
        evidence_id=evidence.evidence_id,
        effective_from="2020-01-01T00:00:00+00:00",
        effective_to="2021-01-01T00:00:00+00:00",
    )

    claim = repository.claim_identifier(
        entity_id=second.entity_id,
        namespace="br.cvm.cd_cvm",
        raw_value="9512",
        scope_authority="CVM",
        identifier_strength="strong",
        evidence_id=evidence.evidence_id,
        effective_from="2021-01-01T00:00:00+00:00",
    )

    assert claim.claim_status == "accepted"


@pytest.mark.parametrize(
    ("namespace", "raw_value", "source_class", "expected"),
    [
        ("unknown.namespace", "x", "official_primary", "namespace"),
        ("br.cnpj", "12.345", "official_primary", "14 digits"),
        ("br.cvm.cd_cvm", "9512", "external", "official evidence"),
    ],
)
def test_rejects_unknown_or_malformed_identifier_claims(
    repository, namespace, raw_value, source_class, expected
):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class=source_class,
        source_reference="source://test",
    )

    with pytest.raises(EntityRegistryValidationError, match=expected):
        repository.claim_identifier(
            entity_id=entity.entity_id,
            namespace=namespace,
            raw_value=raw_value,
            scope_authority="CVM" if namespace == "br.cvm.cd_cvm" else None,
            scope_country="BR" if namespace == "br.cnpj" else None,
            identifier_strength="strong",
            evidence_id=evidence.evidence_id,
        )


def test_repository_reads_only_local_persisted_claims(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="cvm://catalog/9512",
    )
    repository.claim_identifier(
        entity_id=entity.entity_id,
        namespace="br.cvm.cd_cvm",
        raw_value="9512",
        scope_authority="CVM",
        identifier_strength="strong",
        evidence_id=evidence.evidence_id,
    )

    assert repository.find_entities_by_identifier("br.cvm.cd_cvm", "9512", "CVM") == [entity]


def test_alias_claim_retains_evidence_and_bitemporal_fields(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="cvm://issuer/9512",
    )

    alias = repository.claim_alias(
        entity_id=entity.entity_id,
        alias_type="trade_name",
        raw_value="PETROBRAS",
        evidence_id=evidence.evidence_id,
        effective_from="2026-01-01T00:00:00+00:00",
    )

    assert alias.entity_id == entity.entity_id
    assert alias.raw_value == "PETROBRAS"
    assert alias.evidence_id == evidence.evidence_id
    assert alias.system_from.endswith("+00:00")


def test_rejects_invalid_evidence_source_class(repository):
    with pytest.raises(EntityRegistryValidationError, match="source class"):
        repository.record_evidence(
            source_class="official",
            source_reference="source://invalid",
        )
