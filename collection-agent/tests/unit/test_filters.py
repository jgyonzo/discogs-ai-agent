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


def test_text_criterion_defaults_to_contains_when_op_omitted(incident_shaped_tool, session):
    """FR-010: the LLM often omits op; a silent eq default on title would
    recreate the false-absence failure."""
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "title", "value": "focus on"}])  # no op
    assert res["count"] == 1
    assert res["matches"][0]["title"] == "Focus On Guido Schneider"
    assert res["criteria_applied"] == [
        {"attribute": "title", "op": "contains", "value": "focus on"}
    ]


def test_text_criterion_explicit_eq_stays_exact(incident_shaped_tool, session):
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "title", "op": "eq", "value": "focus on"}])
    assert res["count"] == 0
    res2 = run_filter(incident_shaped_tool, session,
                      [{"attribute": "title", "op": "eq",
                        "value": "focus on guido schneider"}])
    assert res2["count"] == 1


def test_non_text_criterion_keeps_eq_default(incident_shaped_tool, session):
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "artist", "value": "Troy Pierce"}])  # no op
    assert res["criteria_applied"][0]["op"] == "eq"
    assert res["count"] == 2


def test_zero_match_with_text_criterion_note_says_loosen(incident_shaped_tool, session):
    """FR-009: a zero-match listing whose only criterion is text-kind must
    steer the LLM toward loosening the search, not toward declaring absence.
    (Mixed text+non-text zero-matches take the FR-011 fallback path instead.)"""
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "title", "op": "contains", "value": "gone astral 2x12"}])
    assert res["count"] == 0
    note = res["note"]
    assert "no records matched" in note
    assert "shorter" in note and "drop" in note  # loosen-before-absence
    assert "do not invent" in note               # anti-hallucination stays


def test_zero_match_without_text_criterion_keeps_plain_note(incident_shaped_tool, session):
    """FR-009: non-text zero-matches keep the FR-013b 'say so explicitly' note."""
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "genre", "value": "Polka"}])
    assert res["count"] == 0
    assert "say so explicitly" in res["note"]
    assert "shorter" not in res["note"]


def test_zero_match_with_mixed_criteria_returns_fallback(incident_shaped_tool, session):
    """FR-011: near-miss titles land IN the payload — the LLM never has to
    choose to re-query."""
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "artist", "value": "Troy Pierce"},
                      {"attribute": "title", "op": "contains", "value": "gone astral"}])
    assert res["count"] == 0 and res["matches"] == []
    assert res["fallback_count"] == 2
    titles = {m["title"] for m in res["fallback_matches"]}
    assert titles == {"25 Bitches Vol. II", "Gone Astray EP"}
    assert {"artist", "title", "year", "instance_id"} <= set(res["fallback_matches"][0])
    assert "near-miss" in res["note"] and "do not invent" in res["note"]
    # follow-ups ("show me details") work off the fallback listing
    assert set(session.last_listing_instance_ids) == {
        m["instance_id"] for m in res["fallback_matches"]
    }


def test_zero_match_text_only_has_no_fallback(incident_shaped_tool, session):
    """FR-011: text-only searches don't fall back to the whole collection."""
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "title", "op": "contains", "value": "zzz"}])
    assert res["count"] == 0
    assert "fallback_matches" not in res
    assert "shorter" in res["note"]  # FR-009 loosen note stays


def test_zero_match_non_text_has_no_fallback(incident_shaped_tool, session):
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "genre", "value": "Polka"}])
    assert res["count"] == 0
    assert "fallback_matches" not in res
    assert "say so explicitly" in res["note"]  # FR-013b plain note stays


def test_fallback_respects_limit(settings, store, session):
    from tests.conftest import make_record, make_snapshot

    store.save(make_snapshot(
        [make_record(i, artist="Prolific", title=f"Vol {i}") for i in range(1, 9)]
    ))
    (tool,) = make_browse_tools(settings, store)
    res = run_filter(tool, session,
                     [{"attribute": "artist", "value": "Prolific"},
                      {"attribute": "title", "op": "contains", "value": "nope"}],
                     limit=3)
    assert res["fallback_count"] == 8
    assert len(res["fallback_matches"]) == 3


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


# --- 019 listing link integrity (delta 6): release_url on every entry --------


def test_matches_carry_release_url_in_release_id_space(settings, store, session):
    """019: the listing's URL embeds release_id — NEVER instance_id (the
    018-replay invented-URL incident was exactly that id-space confusion)."""
    from tests.conftest import make_record, make_snapshot

    store.save(make_snapshot([
        make_record(987654321, release_id=1234, artist="Guido Schneider",
                    title="Focus On Guido Schneider", genres=["Electronic"]),
    ]))
    (tool,) = make_browse_tools(settings, store)
    res = run_filter(tool, session, [{"attribute": "genre", "value": "Electronic"}])
    (m,) = res["matches"]
    assert m["release_url"] == "https://www.discogs.com/release/1234"
    assert "987654321" not in m["release_url"]
    assert m["instance_id"] == 987654321  # opaque follow-up ref unchanged


def test_copies_of_same_release_share_release_url(filter_tool, session):
    res = run_filter(filter_tool, session,
                     [{"attribute": "genre", "value": "Electronic"},
                      {"attribute": "decade", "value": "2000s"}])
    urls = {m["instance_id"]: m["release_url"] for m in res["matches"]}
    assert urls[1] == urls[4]  # instances 1+4 are copies of release 1


def test_fallback_matches_carry_release_url(incident_shaped_tool, session):
    """019: the FR-011 fallback listing is a listing — its entries carry the
    link so a follow-up 'give me its link' works without invention."""
    res = run_filter(incident_shaped_tool, session,
                     [{"attribute": "artist", "value": "Troy Pierce"},
                      {"attribute": "title", "op": "contains", "value": "gone astral"}])
    assert res["fallback_matches"]
    for m in res["fallback_matches"]:
        assert m["release_url"].startswith("https://www.discogs.com/release/")


# --- 020 replay finding 6: lean listing entries (payload beats prompt) --------


DEFAULT_ENTRY_KEYS = {"instance_id", "artist", "title", "year", "country", "release_url"}


def test_default_entry_carries_exactly_the_lean_fields(filter_tool, session):
    res = run_filter(filter_tool, session, [{"attribute": "genre", "value": "Jazz"}])
    (entry,) = res["matches"]
    assert set(entry) == DEFAULT_ENTRY_KEYS  # no format, no folder
    assert entry["country"] == "US"


def test_include_adds_requested_attributes(filter_tool, session):
    args = filter_tool.params_model(
        criteria=[{"attribute": "genre", "value": "Jazz"}], include=["format"]
    )
    (entry,) = filter_tool.fn(session, args)["matches"]
    assert entry["format"] == 'Vinyl, 12"'


def test_include_resolves_aliases_and_folder_shows_name(filter_tool, session):
    args = filter_tool.params_model(
        criteria=[{"attribute": "genre", "value": "Jazz"}], include=["carpeta"]
    )
    (entry,) = filter_tool.fn(session, args)["matches"]
    assert entry["folder"] == "Uncategorized"  # name, never the raw id


def test_unknown_include_reported_not_dropped(filter_tool, session):
    args = filter_tool.params_model(
        criteria=[{"attribute": "genre", "value": "Jazz"}], include=["bogus"]
    )
    res = filter_tool.fn(session, args)
    assert any(
        u["attribute"] == "bogus" and "include" in u["reason"]
        for u in res["unsupported_criteria"]
    )
    assert res["count"] == 1  # the filter itself still ran


def test_non_eq_criterion_auto_includes_its_attribute(filter_tool, session):
    res = run_filter(
        filter_tool, session, [{"attribute": "my_rating", "op": "gte", "value": 4}]
    )
    (entry,) = res["matches"]
    assert entry["my_rating"] == 4  # values vary across records → informative


def test_eq_criterion_does_not_add_a_redundant_column(filter_tool, session):
    res = run_filter(filter_tool, session, [{"attribute": "genre", "value": "Electronic"}])
    for entry in res["matches"]:
        assert "genre" not in entry  # every row would say "Electronic"


def test_include_of_default_attribute_is_a_noop(filter_tool, session):
    args = filter_tool.params_model(
        criteria=[{"attribute": "genre", "value": "Jazz"}], include=["title"]
    )
    (entry,) = filter_tool.fn(session, args)["matches"]
    assert set(entry) == DEFAULT_ENTRY_KEYS


def test_long_titles_truncated_with_ellipsis(settings, store, session):
    from tests.conftest import make_record, make_snapshot

    long_title = "A" * 100
    store.save(make_snapshot([make_record(1, title=long_title)]))
    (tool,) = make_browse_tools(settings, store)
    res = run_filter(tool, session, [{"attribute": "genre", "value": "Electronic"}])
    (entry,) = res["matches"]
    assert len(entry["title"]) == settings.listing_title_max_chars
    assert entry["title"].endswith("…")
    # short titles pass through untouched
    store.save(make_snapshot([make_record(1, title="Short Title")]))
    (tool,) = make_browse_tools(settings, store)
    res = run_filter(tool, session, [{"attribute": "genre", "value": "Electronic"}])
    assert res["matches"][0]["title"] == "Short Title"


def test_arg_descriptions_disambiguate_rows_from_columns(filter_tool):
    """020 replay finding 8: 'show ALL records' was misread as 'all
    attributes' and routed into include. The guardrail lives in the arg
    schema — the decision point for argument choices."""
    fields = filter_tool.params_model.model_fields
    include_desc = fields["include"].description
    limit_desc = fields["limit"].description
    assert "NAMES them" in include_desc
    assert "row count" in include_desc and "leave this empty" in include_desc
    assert "MORE ROWS" in limit_desc and "never" in limit_desc
