"""US2 filter_records (T027): launch filters, AND-combination, other-attribute
contract, unsupported naming, empty result, truncation, multi-value any-match,
and the SC-003a extensibility proof (new attribute by declaration only)."""

from __future__ import annotations

import pytest

from collection_agent.agent import AgentSession
from collection_agent.registry import AttributeRegistry, AttributeSpec, build_registry
from collection_agent.tools.analytics import make_analytics_tools
from collection_agent.tools.browse import make_browse_tools


@pytest.fixture()
def session():
    return AgentSession()


@pytest.fixture()
def filter_tool(settings, store, complete_snapshot):
    store.save(complete_snapshot)
    (tool,) = make_browse_tools(settings, store)
    return tool


def run_filter(tool, session, criteria, limit=None):
    args = tool.params_model(criteria=criteria, limit=limit)
    return tool.fn(session, args)


# --- launch filters (FR-011/012) ---------------------------------------------


def test_genre_filter(filter_tool, session):
    res = run_filter(filter_tool, session, [{"attribute": "genre", "value": "Jazz"}])
    assert res["count"] == 1
    assert res["matches"][0]["title"] == "Test Record"
    assert res["matches"][0]["artist"] == "Test Artist"
    assert res["matches"][0]["year"] == 1974
    assert res["criteria_applied"] == [{"attribute": "genre", "op": "eq", "value": "Jazz"}]


def test_genre_plus_decade_and_combination(filter_tool, session):
    res = run_filter(
        filter_tool, session,
        [{"attribute": "género", "value": "Electronic"},
         {"attribute": "década", "value": "los 2000"}],
    )
    # electronic 2000s: instances 1 and 4 (the duplicate) — not 2 (2011)
    assert res["count"] == 2
    assert {m["instance_id"] for m in res["matches"]} == {1, 4}


def test_decade_value_phrasings_normalize(filter_tool, session):
    for phrasing in ("1970s", "70s", "los 70", "the 70s", "1974"):
        res = run_filter(filter_tool, session, [{"attribute": "decade", "value": phrasing}])
        assert res["count"] == 1, phrasing


def test_other_attribute_same_contract(filter_tool, session):
    """SC-003: a non-genre attribute honors the same list contract."""
    res = run_filter(filter_tool, session, [{"attribute": "label", "value": "Blue Note"}])
    assert res["count"] == 1
    m = res["matches"][0]
    assert {"artist", "title", "year", "instance_id"} <= set(m)

    res2 = run_filter(filter_tool, session,
                      [{"attribute": "country", "value": "canada"}])  # case-insensitive
    assert res2["count"] == 1


def test_numeric_ops(filter_tool, session):
    res = run_filter(filter_tool, session,
                     [{"attribute": "year", "op": "between", "value": [2000, 2010]}])
    assert res["count"] == 2  # 2005 twice
    res2 = run_filter(filter_tool, session,
                      [{"attribute": "my_rating", "op": "gte", "value": 4}])
    assert res2["count"] == 1
    res3 = run_filter(filter_tool, session,
                      [{"attribute": "year", "op": "missing"}])
    assert res3["count"] == 1  # record 5


def test_multi_valued_any_match(settings, store, session):
    from tests.conftest import make_record, make_snapshot

    store.save(make_snapshot([
        make_record(1, genres=["Electronic", "Pop"]),
        make_record(2, genres=["Rock"]),
    ]))
    (tool,) = make_browse_tools(settings, store)
    res = run_filter(tool, session, [{"attribute": "genre", "value": "Pop"}])
    assert res["count"] == 1  # any-of the record's genres matches


# --- unsupported / empty / truncation (FR-013a/b) -------------------------------


def test_unknown_attribute_named_with_supported_list(filter_tool, session):
    res = run_filter(filter_tool, session,
                     [{"attribute": "catno", "value": "TL-1"},
                      {"attribute": "genre", "value": "Jazz"}])
    assert res["unsupported_criteria"][0]["attribute"] == "catno"
    assert "genre" in res["unsupported_criteria"][0]["supported"]
    # the supported criterion is still applied and disclosed:
    assert res["criteria_applied"] == [{"attribute": "genre", "op": "eq", "value": "Jazz"}]
    assert res["count"] == 1


def test_invalid_op_named(filter_tool, session):
    res = run_filter(filter_tool, session,
                     [{"attribute": "genre", "op": "gte", "value": 3}])
    assert "not valid" in res["unsupported_criteria"][0]["reason"]
    assert res["count"] == 0 and res["matches"] == []


def test_empty_result_explicit(filter_tool, session):
    res = run_filter(filter_tool, session, [{"attribute": "genre", "value": "Polka"}])
    assert res["count"] == 0
    assert "no records matched" in res["note"]


def test_truncation_disclosed_and_session_refs_set(settings, store, session):
    from tests.conftest import make_record, make_snapshot

    store.save(make_snapshot([make_record(i) for i in range(1, 21)]))
    (tool,) = make_browse_tools(settings, store)
    res = run_filter(tool, session, [{"attribute": "genre", "value": "Electronic"}], limit=5)
    assert res["count"] == 20 and len(res["matches"]) == 5
    assert res["truncated"] is True and "5 of 20" in res["truncation_note"]
    assert session.last_listing_instance_ids == [1, 2, 3, 4, 5]


# --- title attribute (018-title-locate-postmortem) -------------------------------


@pytest.fixture()
def incident_shaped_tool(settings, store):
    """Multi-record artists in the 2026-07-05 incident shape: the target
    title is NOT the artist's first record in snapshot order."""
    from tests.conftest import make_record, make_snapshot

    records = [
        make_record(1, artist="Guido Schneider", title="Styleways", year=2005),
        make_record(2, artist="Guido Schneider",
                    title="Focus On Guido Schneider", year=2006),
        make_record(3, artist="Troy Pierce", title="25 Bitches Vol. II", year=2006),
        make_record(4, artist="Troy Pierce", title="Gone Astray EP"),
        make_record(5, artist="Click Box", title="Espaço E Tempo", year=2008),
    ]
    store.save(make_snapshot(records))
    (tool,) = make_browse_tools(settings, store)
    return tool


def test_artist_and_title_contains_combination(incident_shaped_tool, session):
    """FR-002/FR-004 + SC-002: findable regardless of snapshot ordering."""
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "artist", "value": "Guido Schneider"},
                      {"attribute": "title", "op": "contains", "value": "focus on"}])
    assert res["count"] == 1
    assert res["matches"][0]["title"] == "Focus On Guido Schneider"


def test_title_only_search_across_collection(incident_shaped_tool, session):
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "title", "op": "contains", "value": "gone astr"}])
    assert res["count"] == 1
    assert res["matches"][0]["title"] == "Gone Astray EP"


def test_title_contains_folds_diacritics_in_filter(incident_shaped_tool, session):
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "título", "op": "contains", "value": "espaco e tempo"}])
    assert res["count"] == 1
    assert res["matches"][0]["instance_id"] == 5


def test_title_reads_title_field_only(incident_shaped_tool, session):
    """Spec edge case: a substring that appears in the artist name must not
    make that artist's other records match on title."""
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "title", "op": "contains", "value": "guido"}])
    assert {m["instance_id"] for m in res["matches"]} == {2}  # not Styleways (1)


def test_title_in_attribute_block(settings):
    """FR-005: title auto-renders into the prompt attribute block."""
    from collection_agent.registry import render_attribute_block

    block = render_attribute_block(build_registry(settings))
    assert "`title`" in block
    assert "título" in block
    assert "contains" in block


# --- extensibility proof (SC-003a / FR-013) --------------------------------------


def _extended_registry(settings) -> AttributeRegistry:
    """Add a brand-new attribute by DECLARATION ONLY — no tool-code changes."""
    base = build_registry(settings).specs()
    catno = AttributeSpec(
        "catno", ("número de catálogo", "numero de catalogo", "catalog number"),
        "text", lambda r: [l.catno for l in r.labels if l.catno] or None, multi=True,
        unknown_label="no catno", description="label catalog number(s)",
    )
    return AttributeRegistry([*base, catno])


def test_new_attribute_filters_and_aggregates_without_tool_changes(
    settings, store, session
):
    from collection_agent.models import LabelRef

    from tests.conftest import make_record, make_snapshot

    records = [make_record(i) for i in range(1, 4)]
    for i, rec in enumerate(records, start=1):
        rec.labels = [LabelRef(name="Test Label", catno=f"TL-{i:03d}")]
    store.save(make_snapshot(records))
    registry = _extended_registry(settings)

    (filter_tool,) = make_browse_tools(settings, store, registry=registry)
    res = run_filter(filter_tool, session,
                     [{"attribute": "catno", "op": "contains", "value": "TL-"}])
    assert res["count"] == 3  # every record carries a TL-* catno

    agg = next(t for t in make_analytics_tools(settings, store, registry=registry)
               if t.name == "aggregate_by")
    out = agg.fn(session, agg.params_model(attribute="catalog number"))
    assert out["attribute"] == "catno" and out["buckets"]


def test_previously_passing_filters_unchanged_after_extension(
    settings, store, complete_snapshot, session
):
    """SC-003a: the old filters produce identical results with the extended registry."""
    store.save(complete_snapshot)
    (base_tool,) = make_browse_tools(settings, store)
    (ext_tool,) = make_browse_tools(settings, store, registry=_extended_registry(settings))

    for criteria in (
        [{"attribute": "genre", "value": "Jazz"}],
        [{"attribute": "genre", "value": "Electronic"},
         {"attribute": "decade", "value": "2000s"}],
        [{"attribute": "label", "value": "Blue Note"}],
        [{"attribute": "year", "op": "missing"}],
    ):
        before = run_filter(base_tool, AgentSession(), criteria)
        after = run_filter(ext_tool, AgentSession(), criteria)
        assert before["count"] == after["count"], criteria
        assert before["matches"] == after["matches"], criteria
