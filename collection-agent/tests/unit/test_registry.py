"""Attribute registry (T011): alias lookup es/en, derived extractors,
unknown bucketing, supported-list on unknown attribute."""

from __future__ import annotations

import pytest

from collection_agent.registry import build_registry, fold, render_attribute_block
from tests.conftest import make_record


@pytest.fixture()
def registry(settings):
    return build_registry(settings)


# --- alias lookup ---------------------------------------------------------


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("genre", "genre"),
        ("género", "genre"),
        ("GENERO", "genre"),  # case + diacritic insensitive
        ("géneros", "genre"),
        ("sello", "label"),
        ("país", "country"),
        ("pais", "country"),
        ("década", "decade"),
        ("decada", "decade"),
        ("carpeta", "folder"),
        ("rareza", "scarcity"),
        ("año", "year"),
        ("formato", "format"),
        ("artista", "artist"),
    ],
)
def test_alias_resolution(registry, alias, expected):
    spec = registry.resolve(alias)
    assert spec is not None and spec.name == expected


def test_unknown_attribute_returns_none_and_supported_list(registry):
    assert registry.resolve("catno") is None
    supported = registry.supported_names()
    assert "genre" in supported and "scarcity" in supported
    assert len(supported) == 16  # launch set (contracts/agent-tools.md §3)


def test_fold():
    assert fold("Década") == "decada"
    assert fold("  GÉNERO ") == "genero"


# --- derived extractors -----------------------------------------------------


def test_decade_derivation(registry):
    decade = registry.resolve("decade").extract
    assert decade(make_record(1, year=1994)) == "1990s"
    assert decade(make_record(2, year=2005)) == "2000s"
    assert decade(make_record(3, year=None)) is None  # → unknown bucket


def test_scarcity_thresholds(registry, settings):
    scarcity = registry.resolve("scarcity").extract
    # rare by sale count (≤ RARITY_MAX_FOR_SALE=2)
    assert scarcity(make_record(1, community_have=100, community_want=50,
                                num_for_sale=1)) == "rare"
    # rare by want/have ratio (≥2.0, have ≥10)
    assert scarcity(make_record(2, community_have=40, community_want=200,
                                num_for_sale=30)) == "rare"
    # both → very rare
    assert scarcity(make_record(3, community_have=40, community_want=200,
                                num_for_sale=0)) == "very rare"
    # neither → common
    assert scarcity(make_record(4, community_have=500, community_want=80,
                                num_for_sale=25)) == "common"
    # below have floor: ratio alone must not fire (small-sample noise)
    assert scarcity(make_record(5, community_have=3, community_want=30,
                                num_for_sale=10)) == "common"
    # missing community stats → None (never falsely rare)
    assert scarcity(make_record(6, community_have=None, community_want=None)) is None


def test_multi_valued_extracts_lists(registry):
    rec = make_record(1, genres=["Electronic", "Pop"], labels=["A", "B"])
    assert registry.resolve("genre").extract(rec) == ["Electronic", "Pop"]
    assert registry.resolve("label").extract(rec) == ["A", "B"]
    assert registry.resolve("genre").multi is True


def test_null_extract_for_unknown_bucket(registry):
    rec = make_record(1, genres=[], country=None, year=None)
    assert registry.resolve("genre").extract(rec) is None
    assert registry.resolve("country").extract(rec) is None
    assert registry.resolve("genre").unknown_label == "unknown genre"


def test_zero_rating_normalized_to_null(registry):
    rec = make_record(1, my_rating=0)
    assert registry.resolve("my_rating").extract(rec) is None


# --- prompt rendering (VII(b) analog) ----------------------------------------


def test_attribute_block_rendered_from_registry(registry):
    block = render_attribute_block(registry)
    for name in registry.supported_names():
        assert f"`{name}`" in block
    assert "género" in block  # aliases surface for the LLM
    assert "ops:" in block
