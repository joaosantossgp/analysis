from __future__ import annotations

from queue import Queue
from threading import Barrier, Thread

import pytest
from sqlalchemy import create_engine

from src.companies.entity_registry import (
    EntityRegistryConflictError,
    EntityRegistryRepository,
    EntityRegistryValidationError,
)
from src.companies.entity_registry_schema import ensure_entity_registry_schema


@pytest.fixture
def repository():
    engine = create_engine("sqlite:///:memory:")
    ensure_entity_registry_schema(engine)
    return EntityRegistryRepository(engine)


def _add_organization_facet(repository, entity_id, facet, evidence_id):
    repository.add_organization_facet(
        entity_id=entity_id,
        facet=facet,
        evidence_id=evidence_id,
        effective_from="2020-01-01T00:00:00+00:00",
    )


def _official_evidence(repository, namespace="br.cvm.cd_cvm", authority="CVM", **kwargs):
    return repository.record_evidence(
        source_class="official_primary",
        source_reference=f"{authority.lower()}://registry",
        source_authority=authority,
        qualified_namespace=namespace,
        **kwargs,
    )


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
    evidence = _official_evidence(repository)
    _add_organization_facet(repository, entity.entity_id, "issuer", evidence.evidence_id)

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
    evidence = _official_evidence(repository)
    _add_organization_facet(repository, first.entity_id, "issuer", evidence.evidence_id)
    _add_organization_facet(repository, second.entity_id, "issuer", evidence.evidence_id)
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
    evidence = _official_evidence(repository)
    _add_organization_facet(repository, first.entity_id, "issuer", evidence.evidence_id)
    _add_organization_facet(repository, second.entity_id, "issuer", evidence.evidence_id)
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
    if namespace == "br.cvm.cd_cvm":
        _add_organization_facet(repository, entity.entity_id, "issuer", evidence.evidence_id)
    elif namespace == "br.cnpj":
        _add_organization_facet(repository, entity.entity_id, "legal_entity", evidence.evidence_id)

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
    evidence = _official_evidence(repository)
    _add_organization_facet(repository, entity.entity_id, "issuer", evidence.evidence_id)
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


def test_repository_requires_explicit_schema_creation():
    engine = create_engine("sqlite:///:memory:")

    with pytest.raises(ValueError, match="schema"):
        EntityRegistryRepository(engine)


def test_cvm_and_cnpj_claims_require_approved_organization_facets(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = _official_evidence(repository)

    with pytest.raises(EntityRegistryValidationError, match="issuer"):
        repository.claim_identifier(
            entity_id=entity.entity_id,
            namespace="br.cvm.cd_cvm",
            raw_value="9512",
            scope_authority="CVM",
            identifier_strength="strong",
            evidence_id=evidence.evidence_id,
        )

    _add_organization_facet(repository, entity.entity_id, "issuer", evidence.evidence_id)
    repository.claim_identifier(
        entity_id=entity.entity_id,
        namespace="br.cvm.cd_cvm",
        raw_value="9512",
        scope_authority="CVM",
        identifier_strength="strong",
        evidence_id=evidence.evidence_id,
    )

    cnpj_evidence = _official_evidence(repository, namespace="br.cnpj")
    with pytest.raises(EntityRegistryValidationError, match="legal_entity"):
        repository.claim_identifier(
            entity_id=entity.entity_id,
            namespace="br.cnpj",
            raw_value="33.000.167/0001-01",
            scope_country="BR",
            identifier_strength="strong",
            evidence_id=cnpj_evidence.evidence_id,
        )

    _add_organization_facet(repository, entity.entity_id, "legal_entity", evidence.evidence_id)
    assert repository.claim_identifier(
        entity_id=entity.entity_id,
        namespace="br.cnpj",
        raw_value="33.000.167/0001-01",
        scope_country="BR",
        identifier_strength="strong",
        evidence_id=cnpj_evidence.evidence_id,
    ).normalized_value == "33000167000101"


def test_regulated_agent_identifier_requires_facet_and_authority_program_scope(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="aneel://agent/123",
    )

    with pytest.raises(EntityRegistryValidationError, match="scope authority"):
        repository.claim_identifier(
            entity_id=entity.entity_id,
            namespace="br.aneel.regulated_agent_code",
            raw_value="123",
            scope_context="distribution",
            identifier_strength="weak",
            evidence_id=evidence.evidence_id,
        )

    _add_organization_facet(repository, entity.entity_id, "regulated_agent", evidence.evidence_id)
    assert repository.claim_identifier(
        entity_id=entity.entity_id,
        namespace="br.aneel.regulated_agent_code",
        raw_value="123",
        scope_authority="ANEEL",
        scope_context="distribution",
        identifier_strength="weak",
        evidence_id=evidence.evidence_id,
    ).namespace == "br.aneel.regulated_agent_code"


@pytest.mark.parametrize("source_status", ["unavailable", "failed", "unsupported"])
def test_non_available_evidence_cannot_authorize_strong_identifier(repository, source_status):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = _official_evidence(repository, source_status=source_status)
    _add_organization_facet(repository, entity.entity_id, "issuer", evidence.evidence_id)

    with pytest.raises(EntityRegistryValidationError, match="available official evidence"):
        repository.claim_identifier(
            entity_id=entity.entity_id,
            namespace="br.cvm.cd_cvm",
            raw_value="9512",
            scope_authority="CVM",
            identifier_strength="strong",
            evidence_id=evidence.evidence_id,
        )


def test_lifecycle_history_is_append_only_and_evidence_backed(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="cvm://issuer/9512",
    )

    repository.change_lifecycle(
        entity.entity_id,
        lifecycle_status="retired",
        reason="registry retirement",
        evidence_id=evidence.evidence_id,
        effective_from="2025-01-01T00:00:00+00:00",
    )
    repository.change_lifecycle(
        entity.entity_id,
        lifecycle_status="deprecated",
        reason="historical correction",
        evidence_id=evidence.evidence_id,
        effective_from="2024-01-01T00:00:00+00:00",
    )

    events = repository.get_lifecycle_events(entity.entity_id)
    assert {event.lifecycle_status for event in events} == {"retired", "deprecated"}
    assert all(event.evidence_id == evidence.evidence_id for event in events)


def test_concurrent_strong_identifier_writers_preserve_one_conflict(tmp_path):
    db_path = tmp_path / "registry.db"
    setup_engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 5})
    ensure_entity_registry_schema(setup_engine)
    setup = EntityRegistryRepository(setup_engine)
    evidence = _official_evidence(setup)
    first = setup.create_entity("organization", origin="source_ingestion")
    second = setup.create_entity("organization", origin="source_ingestion")
    _add_organization_facet(setup, first.entity_id, "issuer", evidence.evidence_id)
    _add_organization_facet(setup, second.entity_id, "issuer", evidence.evidence_id)

    barrier = Barrier(2)
    results: Queue[object] = Queue()

    def claim(entity_id: str) -> None:
        repository = EntityRegistryRepository(
            create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 5})
        )
        barrier.wait()
        try:
            results.put(
                repository.claim_identifier(
                    entity_id=entity_id,
                    namespace="br.cvm.cd_cvm",
                    raw_value="9512",
                    scope_authority="CVM",
                    identifier_strength="strong",
                    evidence_id=evidence.evidence_id,
                    effective_from="2025-01-01T00:00:00+00:00",
                )
            )
        except Exception as error:  # asserted below to retain both outcomes
            results.put(error)

    workers = [Thread(target=claim, args=(entity.entity_id,)) for entity in (first, second)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert not worker.is_alive()

    outcomes = [results.get_nowait(), results.get_nowait()]
    assert sum(isinstance(result, EntityRegistryConflictError) for result in outcomes) == 1
    assert sum(not isinstance(result, Exception) for result in outcomes) == 1
    claims = setup.find_identifier_claims("br.cvm.cd_cvm", "9512", "CVM")
    assert {claim.claim_status for claim in claims} == {"accepted", "conflicted"}


def test_retired_entity_blocks_forward_attachments_but_allows_historical_corrections(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="cvm://catalog/9512",
        source_authority="CVM",
        qualified_namespace="br.cvm.cd_cvm",
    )
    _add_organization_facet(repository, entity.entity_id, "issuer", evidence.evidence_id)
    repository.change_lifecycle(
        entity.entity_id,
        lifecycle_status="retired",
        reason="registry retirement",
        evidence_id=evidence.evidence_id,
        effective_from="2025-01-01T00:00:00+00:00",
    )

    with pytest.raises(EntityRegistryValidationError, match="retired or deprecated"):
        repository.claim_identifier(
            entity_id=entity.entity_id,
            namespace="br.cvm.cd_cvm",
            raw_value="9512",
            scope_authority="CVM",
            identifier_strength="strong",
            evidence_id=evidence.evidence_id,
            effective_from="2026-01-01T00:00:00+00:00",
        )
    with pytest.raises(EntityRegistryValidationError, match="retired or deprecated"):
        repository.claim_alias(
            entity_id=entity.entity_id,
            alias_type="trade_name",
            raw_value="PETROBRAS",
            evidence_id=evidence.evidence_id,
            effective_from="2026-01-01T00:00:00+00:00",
        )
    with pytest.raises(EntityRegistryValidationError, match="retired or deprecated"):
        repository.add_organization_facet(
            entity_id=entity.entity_id,
            facet="legal_entity",
            evidence_id=evidence.evidence_id,
            effective_from="2026-01-01T00:00:00+00:00",
        )

    assert repository.claim_alias(
        entity_id=entity.entity_id,
        alias_type="former_name",
        raw_value="PETROBRAS ANTIGA",
        evidence_id=evidence.evidence_id,
        effective_from="2024-01-01T00:00:00+00:00",
        effective_to="2025-01-01T00:00:00+00:00",
    ).raw_value == "PETROBRAS ANTIGA"


@pytest.mark.parametrize(
    ("namespace", "authority", "country", "expected"),
    [
        ("br.cvm.cd_cvm", "ANEEL", None, "authority CVM"),
        ("br.cnpj", None, "US", "country BR"),
        ("br.aneel.ceg", "CCEE", None, "authority ANEEL"),
        ("br.ccee.plant_parcel", "ANEEL", None, "authority CCEE"),
    ],
)
def test_fixed_namespace_scope_rejects_wrong_authority_or_country(
    repository, namespace, authority, country, expected
):
    kind = {
        "br.cvm.cd_cvm": "organization",
        "br.cnpj": "organization",
        "br.aneel.ceg": "plant_or_asset",
        "br.ccee.plant_parcel": "market_parcel",
    }[namespace]
    entity = repository.create_entity(kind, origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="source://test",
        source_authority="CVM",
        qualified_namespace=namespace,
    )
    if namespace == "br.cvm.cd_cvm":
        _add_organization_facet(repository, entity.entity_id, "issuer", evidence.evidence_id)
    elif namespace == "br.cnpj":
        _add_organization_facet(repository, entity.entity_id, "legal_entity", evidence.evidence_id)

    with pytest.raises(EntityRegistryValidationError, match=expected):
        repository.claim_identifier(
            entity_id=entity.entity_id,
            namespace=namespace,
            raw_value="33.000.167/0001-01" if namespace == "br.cnpj" else "9512",
            scope_authority=authority,
            scope_country=country,
            identifier_strength="strong",
            evidence_id=evidence.evidence_id,
        )


def test_strong_identifier_rejects_wrong_authority_evidence(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(
        source_class="official_primary",
        source_reference="aneel://record/9512",
        source_authority="ANEEL",
        qualified_namespace="br.cvm.cd_cvm",
    )
    _add_organization_facet(repository, entity.entity_id, "issuer", evidence.evidence_id)

    with pytest.raises(EntityRegistryValidationError, match="qualifying official evidence"):
        repository.claim_identifier(
            entity_id=entity.entity_id,
            namespace="br.cvm.cd_cvm",
            raw_value="9512",
            scope_authority="CVM",
            identifier_strength="strong",
            evidence_id=evidence.evidence_id,
        )


def test_overlapping_weak_ticker_claim_is_preserved_as_review_conflict(repository):
    first = repository.create_entity("security_class", origin="source_ingestion")
    second = repository.create_entity("security_class", origin="source_ingestion")
    evidence = repository.record_evidence(source_class="external", source_reference="source://ticker")
    repository.claim_identifier(
        entity_id=first.entity_id,
        namespace="br.b3.ticker",
        raw_value="PETR4",
        scope_authority="B3",
        scope_context="ON",
        identifier_strength="weak",
        evidence_id=evidence.evidence_id,
        effective_from="2025-01-01T00:00:00+00:00",
    )

    with pytest.raises(EntityRegistryConflictError, match="identifier_overlap"):
        repository.claim_identifier(
            entity_id=second.entity_id,
            namespace="br.b3.ticker",
            raw_value="PETR4",
            scope_authority="B3",
            scope_context="ON",
            identifier_strength="weak",
            evidence_id=evidence.evidence_id,
            effective_from="2025-01-01T00:00:00+00:00",
        )

    claims = repository.find_identifier_claims("br.b3.ticker", "PETR4", "B3")
    assert {claim.claim_status for claim in claims} == {"accepted", "conflicted"}


def test_dynamic_regulated_agent_namespace_binds_scope_authority(repository):
    entity = repository.create_entity("organization", origin="source_ingestion")
    evidence = repository.record_evidence(source_class="external", source_reference="source://agent")
    _add_organization_facet(repository, entity.entity_id, "regulated_agent", evidence.evidence_id)

    with pytest.raises(EntityRegistryValidationError, match="authority ANEEL"):
        repository.claim_identifier(
            entity_id=entity.entity_id,
            namespace="br.aneel.regulated_agent_code",
            raw_value="123",
            scope_authority="CCEE",
            scope_context="distribution",
            identifier_strength="weak",
            evidence_id=evidence.evidence_id,
        )


def test_overlapping_weak_regulated_agent_claim_is_review_conflict(repository):
    evidence = repository.record_evidence(source_class="external", source_reference="source://agent")
    first = repository.create_entity("organization", origin="source_ingestion")
    second = repository.create_entity("organization", origin="source_ingestion")
    for entity in (first, second):
        _add_organization_facet(repository, entity.entity_id, "regulated_agent", evidence.evidence_id)
    repository.claim_identifier(
        entity_id=first.entity_id,
        namespace="br.aneel.regulated_agent_code",
        raw_value="123",
        scope_authority="ANEEL",
        scope_context="distribution",
        identifier_strength="weak",
        evidence_id=evidence.evidence_id,
    )

    with pytest.raises(EntityRegistryConflictError, match="identifier_overlap"):
        repository.claim_identifier(
            entity_id=second.entity_id,
            namespace="br.aneel.regulated_agent_code",
            raw_value="123",
            scope_authority="ANEEL",
            scope_context="distribution",
            identifier_strength="weak",
            evidence_id=evidence.evidence_id,
        )
