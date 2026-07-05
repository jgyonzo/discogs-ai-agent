"""Attribute registry (T011): alias lookup es/en, derived extractors,
unknown bucketing, supported-list on unknown attribute."""

from __future__ import annotations

import pytest

from collection_agent.registry import (
    UnsupportedOp,
    build_registry,
    fold,
    matches,
    render_attribute_block,
)
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
    # launch set (017 agent-tools §3) + title (018 amendment)
    assert len(supported) == 17


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


# --- title attribute (018-title-locate-postmortem) ----------------------------


@pytest.mark.parametrize("alias", ["title", "titulo", "título", "titles", "TÍTULOS"])
def test_title_alias_resolution(registry, alias):
    spec = registry.resolve(alias)
    assert spec is not None and spec.name == "title"


def test_title_spec_shape(registry):
    spec = registry.resolve("title")
    assert spec.kind == "text"
    assert spec.ops == ("contains", "eq")
    assert spec.multi is False
    assert spec.unknown_label == "unknown title"


def test_title_contains_folds_case_and_diacritics(registry):
    spec = registry.resolve("title")
    focus = make_record(1, title="Focus On Guido Schneider")
    assert matches(spec, focus, "contains", "focus on")
    assert matches(spec, focus, "contains", "FOCUS ON")
    assert not matches(spec, focus, "contains", "styleways")
    espaco = make_record(2, title="Espaço E Tempo")
    assert matches(spec, espaco, "contains", "espaco tempo") is False  # substring, not tokens
    assert matches(spec, espaco, "contains", "espaco e tempo")
    assert matches(spec, espaco, "contains", "Espaço")


def test_title_eq_exact_modulo_folding(registry):
    spec = registry.resolve("title")
    rec = make_record(1, title="Gone Astray EP")
    assert matches(spec, rec, "eq", "gone astray ep")
    assert not matches(spec, rec, "eq", "gone astray")


def test_title_empty_matches_nothing(registry):
    """FR-007: empty title normalizes to missing — never matches, never errors."""
    spec = registry.resolve("title")
    rec = make_record(1, title="")
    assert spec.extract(rec) is None
    assert not matches(spec, rec, "contains", "anything")
    # a bare `contains ""` must not match an empty-title record either
    assert not matches(spec, rec, "contains", "")


def test_title_unsupported_op_raises(registry):
    spec = registry.resolve("title")
    with pytest.raises(UnsupportedOp):
        matches(spec, make_record(1, title="X"), "between", [1, 2])


# --- prompt rendering (VII(b) analog) ----------------------------------------


def test_attribute_block_rendered_from_registry(registry):
    block = render_attribute_block(registry)
    for name in registry.supported_names():
        assert f"`{name}`" in block
    assert "género" in block  # aliases surface for the LLM
    assert "ops:" in block
