from __future__ import annotations

from src.gics_manual_mapping import resolve_gics_classification, resolve_gics_sector_name


def test_resolve_gics_prefers_persisted_fields_and_keeps_sub_industry_separate():
    gics = resolve_gics_classification(
        sector_name="Energia",
        setor_analitico="Energia",
        setor_cvm="Energia",
        gics_sector="Energy",
        gics_sector_slug="energy",
        gics_industry_group="Energy",
        gics_industry="Oil, Gas & Consumable Fuels",
        gics_sub_industry="Integrated Oil & Gas",
    )

    assert gics is not None
    assert gics.gics_sector == "Energy"
    assert gics.gics_sector_slug == "energy"
    assert gics.gics_industry == "Oil, Gas & Consumable Fuels"
    assert gics.gics_sub_industry == "Integrated Oil & Gas"


def test_resolve_gics_derives_from_legacy_sector_when_no_persisted_gics():
    gics = resolve_gics_classification(
        sector_name="Saneamento",
        setor_analitico=None,
        setor_cvm="Saneamento",
    )

    assert gics is not None
    assert gics.gics_sector == "Utilities"
    assert gics.gics_sub_industry == "Electric Utilities"


def test_resolve_gics_sector_name_returns_only_known_gics_sector():
    assert (
        resolve_gics_sector_name(
            sector_name="Energia",
            setor_analitico="Energia",
            setor_cvm="Energia",
        )
        == "Energy"
    )
    assert resolve_gics_sector_name(sector_name="Nao classificado") is None


def test_resolve_gics_canonicalizes_persisted_sector_case():
    gics = resolve_gics_classification(gics_sector="energy")
    assert gics is not None
    assert gics.gics_sector == "Energy"


def test_resolve_gics_maps_non_hub_persisted_sector_via_manual_rules():
    """Persisted Portuguese labels must still roll up to a GICS 11 hub."""
    gics = resolve_gics_classification(
        sector_name=None,
        setor_analitico=None,
        setor_cvm=None,
        gics_sector="Materiais",
        gics_sub_industry="Steel",
    )
    assert gics is not None
    assert gics.gics_sector == "Materials"
    assert gics.gics_sub_industry == "Steel"
