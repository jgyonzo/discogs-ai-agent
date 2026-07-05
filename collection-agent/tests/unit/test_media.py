"""US3 media_links (T030): verbatim URIs, per-record grouping, explicit
none flag, ref resolution (id / name mention / last listing), not-found."""

from __future__ import annotations

import pytest

from collection_agent.agent import AgentSession
from collection_agent.models import MediaLink
from collection_agent.tools.media import make_media_tools
from tests.conftest import make_record, make_snapshot

SIGNED_URI = "https://www.youtube.com/watch?v=abc123&signature=DO-NOT-TOUCH"


@pytest.fixture()
def media_snapshot():
    return make_snapshot([
        make_record(1, title="Simple Things", artist="Alex Smoke",
                    videos=[MediaLink(uri=SIGNED_URI, title="Video A", duration_s=300),
                            MediaLink(uri="https://youtu.be/second", title=None)]),
        make_record(2, title="Navigation EP", artist="Noah Pred", videos=[]),
        make_record(3, title="Blue Album", artist="Jazz Cat",
                    videos=[MediaLink(uri="https://youtu.be/jazz", title="Jazz vid")]),
    ])


@pytest.fixture()
def tool(settings, store, media_snapshot):
    store.save(media_snapshot)
    (t,) = make_media_tools(settings, store)
    return t


def run(tool, session, **kwargs):
    return tool.fn(session, tool.params_model(**kwargs))


def test_links_returned_verbatim(tool):
    res = run(tool, AgentSession(), record_refs=["1"])
    links = res["per_record"][0]["links"]
    assert links[0]["uri"] == SIGNED_URI  # byte-for-byte, no URL edits
    assert len(links) == 2
    assert res["per_record"][0]["none"] is False


def test_no_links_flagged_explicitly(tool):
    res = run(tool, AgentSession(), record_refs=["2"])
    rec = res["per_record"][0]
    assert rec["none"] is True and rec["links"] == []
    assert res["records_without_links"] == 1


def test_list_of_records_grouped_per_record(tool):
    res = run(tool, AgentSession(), record_refs=["1", "2", "3"])
    assert [p["instance_id"] for p in res["per_record"]] == [1, 2, 3]
    assert res["records_with_links"] == 2
    assert res["records_without_links"] == 1


def test_name_mention_resolution(tool):
    res = run(tool, AgentSession(), record_refs=["alex smoke simple things"])
    assert res["per_record"][0]["instance_id"] == 1


def test_last_listing_refs(tool):
    session = AgentSession()
    session.last_listing_instance_ids = [3, 1]
    res = run(tool, session, use_last_listing=True)
    assert [p["instance_id"] for p in res["per_record"]] == [3, 1]


def test_unknown_record_reported_not_fabricated(tool):
    res = run(tool, AgentSession(), record_refs=["totally unknown record"])
    assert res["not_found"] == ["totally unknown record"]
    assert res["per_record"] == []


def test_no_refs_and_no_listing_is_an_error(tool):
    res = run(tool, AgentSession(), use_last_listing=True)
    assert "no previous listing" in str(res.get("not_found", res))


def test_no_snapshot_blocks(settings, store):
    (t,) = make_media_tools(settings, store)
    res = run(t, AgentSession(), record_refs=["1"])
    assert res["error"] == "sync_required"


# --- 019 listing link integrity (deltas 6+8): release_url alongside media ----


def test_per_record_carries_release_url_in_release_id_space(settings, store):
    store.save(make_snapshot([
        make_record(987654321, release_id=1234, title="Focus On",
                    artist="Guido Schneider",
                    videos=[MediaLink(uri=SIGNED_URI, title="Video A")]),
    ]))
    (tool,) = make_media_tools(settings, store)
    res = run(tool, AgentSession(), record_refs=["987654321"])
    (rec,) = res["per_record"]
    assert rec["release_url"] == "https://www.discogs.com/release/1234"
    assert "987654321" not in rec["release_url"]
    # media answer shape unchanged (FR-014/015/016)
    assert rec["links"][0]["uri"] == SIGNED_URI
    assert rec["none"] is False


def test_release_url_present_even_with_no_media(tool):
    res = run(tool, AgentSession(), record_refs=["2"])
    (rec,) = res["per_record"]
    assert rec["none"] is True  # explicit no-media flag unchanged
    assert rec["release_url"].startswith("https://www.discogs.com/release/")


def test_note_distinguishes_release_page_from_playable_media(tool):
    res = run(tool, AgentSession(), record_refs=["1"])
    note = res["note"].lower()
    assert "verbatim" in note                 # FR-014 wording preserved
    assert "release_url" in res["note"]
    assert "page" in note and "not" in note   # page ≠ playable media
